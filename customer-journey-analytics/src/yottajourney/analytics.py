from __future__ import annotations

import json
import pandas as pd

FUNNEL = [
    ("Session Started", "session_started"),
    ("Product Viewed", "product_viewed"),
    ("Added to Cart", "added_to_cart"),
    ("Checkout Started", "checkout_started"),
    ("Purchase Completed", "purchase_completed"),
]
SESSION_TIMEOUT = pd.Timedelta(minutes=30)


def analyze(
    tables: dict[str, pd.DataFrame],
    channel: str = "All",
    device: str = "All",
    start_at=None,
    end_at=None,
    as_of=None,
) -> dict:
    sessions = tables["sessions"].copy()
    if channel != "All":
        sessions = sessions[sessions.channel.eq(channel)]
    if device != "All":
        sessions = sessions[sessions.device_type.eq(device)]
    if start_at is not None:
        sessions = sessions[pd.to_datetime(sessions.started_at, utc=True).ge(pd.Timestamp(start_at, tz="UTC") if pd.Timestamp(start_at).tzinfo is None else pd.Timestamp(start_at))]
    if end_at is not None:
        sessions = sessions[pd.to_datetime(sessions.started_at, utc=True).lt(pd.Timestamp(end_at, tz="UTC") if pd.Timestamp(end_at).tzinfo is None else pd.Timestamp(end_at))]

    session_ids = set(sessions.session_id)
    events = tables["journey_events"][tables["journey_events"].session_id.isin(session_ids)].copy()
    event_times = pd.to_datetime(events.event_timestamp, utc=True)
    ingestion_times = pd.to_datetime(events.ingestion_timestamp, utc=True)
    events["event_timestamp"] = event_times
    events["ingestion_timestamp"] = ingestion_times
    events["latency_seconds"] = (ingestion_times - event_times).dt.total_seconds()

    entries = set(events.loc[events.event_type.eq("session_started"), "session_id"])
    if "is_bot" in sessions:
        entries -= set(sessions.loc[sessions.is_bot, "session_id"])
    eligible = session_ids & entries
    eligible_events = events[events.session_id.isin(eligible)]

    counts = [int(eligible_events.loc[eligible_events.event_type.eq(event), "session_id"].nunique()) for _, event in FUNNEL]
    funnel = []
    for index, ((stage, _), count) in enumerate(zip(FUNNEL, counts)):
        prior = len(eligible) if index == 0 else counts[index - 1]
        funnel.append({
            "stage": stage,
            "sessions": count,
            "eligible_sessions": prior,
            "conversion_rate": count / prior if prior else 0.0,
            "dropoff_count": max(0, prior - count),
            "dropoff_rate": max(0, prior - count) / prior if prior else 0.0,
        })

    orders = tables["orders"][tables["orders"].session_id.isin(eligible)].copy()
    if "status" in orders:
        orders = orders[orders.status.eq("paid")]
    paid_order_ids = orders.order_id.dropna().drop_duplicates()
    purchase_sessions = set(orders.loc[orders.order_id.isin(paid_order_ids), "session_id"])
    converting_sessions = purchase_sessions & eligible
    carts = tables["carts"][tables["carts"].session_id.isin(eligible)].copy()
    cart_sessions = set(carts.session_id)
    if as_of is None:
        as_of_time = event_times.max() if not event_times.empty else pd.Timestamp.now(tz="UTC")
    else:
        as_of_time = pd.Timestamp(as_of)
        if as_of_time.tzinfo is None:
            as_of_time = as_of_time.tz_localize("UTC")
        else:
            as_of_time = as_of_time.tz_convert("UTC")
    if "ended_at" in sessions:
        last_activity = pd.to_datetime(sessions.set_index("session_id").loc[list(cart_sessions), "ended_at"], utc=True, errors="coerce") if cart_sessions else pd.Series(dtype="datetime64[ns, UTC]")
    else:
        last_activity = pd.Series(dtype="datetime64[ns, UTC]")
    event_last = events.groupby("session_id").event_timestamp.max()
    mature_carts = set()
    for session_id in cart_sessions:
        ended = last_activity.get(session_id, pd.NaT)
        if pd.isna(ended):
            ended = event_last.get(session_id, pd.NaT)
        if not pd.isna(ended) and as_of_time - ended >= SESSION_TIMEOUT:
            mature_carts.add(session_id)
    abandoned_carts = mature_carts - converting_sessions

    support = tables["support_tickets"][tables["support_tickets"].session_id.isin(session_ids)]
    support_sessions = set(support.session_id)
    page_events = eligible_events[eligible_events.page_id.notna()]
    friction = page_events.groupby("page_id").agg(
        events=("event_id", "count"),
        sessions=("session_id", "nunique"),
        median_latency_seconds=("latency_seconds", "median"),
    ).reset_index()
    friction = friction.merge(tables["pages"][["page_id", "page_name"]], on="page_id", how="left").sort_values(
        "median_latency_seconds", ascending=False
    )

    return {
        "funnel": funnel,
        "sessions": len(session_ids),
        "eligible_sessions": len(eligible),
        "unique_customers": sessions.customer_id.nunique(),
        "purchases": len(converting_sessions),
        "purchase_order_count": len(paid_order_ids),
        "conversion_rate": len(converting_sessions) / len(eligible) if eligible else 0.0,
        "abandonment_rate": len(abandoned_carts) / len(mature_carts) if mature_carts else 0.0,
        "abandoned_cart_sessions": len(abandoned_carts),
        "eligible_cart_sessions": len(mature_carts),
        "support_sessions": len(support_sessions),
        "support_contact_rate": len(support_sessions) / len(session_ids) if session_ids else 0.0,
        "friction": friction,
        "checkout_failures": int(eligible_events.event_type.eq("purchase_failed").sum()),
        "median_latency_seconds": float(eligible_events.latency_seconds.median()) if len(eligible_events) else 0.0,
        "anonymous_sessions": int(sessions.customer_id.isna().sum()),
        "identified_sessions": int(sessions.customer_id.notna().sum()),
        "channel_sessions": sessions.groupby("channel").session_id.nunique().to_dict(),
    }


def detect_anomalies(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    events = tables["journey_events"].copy()
    sessions = tables["sessions"].set_index("session_id")
    events["event_timestamp"] = pd.to_datetime(events.event_timestamp, utc=True)
    events["ingestion_timestamp"] = pd.to_datetime(events.ingestion_timestamp, utc=True)
    found = []
    for session_id, group in events.groupby("session_id", sort=True):
        source_order = list(group.sort_values(["event_timestamp", "event_id"], kind="stable").event_id)
        arrival_order = list(group.sort_values(["ingestion_timestamp", "event_id"], kind="stable").event_id)
        if source_order != arrival_order:
            found.append((session_id, "out_of_order_arrival"))
        session = sessions.loc[session_id]
        if session.consent_status != "granted" and (pd.notna(session.customer_id) or group.customer_id.notna().any()):
            found.append((session_id, "identity_stitching"))
        elif pd.notna(session.customer_id) and group.customer_id.dropna().ne(session.customer_id).any():
            found.append((session_id, "identity_stitching"))
        purchases = group[group.event_type.eq("purchase_completed")]
        if purchases.order_id.dropna().duplicated(keep=False).any():
            found.append((session_id, "duplicate_conversion"))
        bot_signal = any(json.loads(value).get("bot_signal", False) for value in group.event_properties)
        if bool(session.get("is_bot", False)) or bot_signal:
            found.append((session_id, "bot_traffic"))
    return pd.DataFrame(found, columns=["entity_id", "issue_type"]).drop_duplicates().reset_index(drop=True)


def evaluate_detection(predictions: pd.DataFrame, ground_truth: pd.DataFrame) -> dict:
    predicted = set(map(tuple, predictions[["entity_id", "issue_type"]].to_numpy().tolist()))
    actual = set(map(tuple, ground_truth[["entity_id", "issue_type"]].to_numpy().tolist()))
    true_positives = len(predicted & actual)
    false_positives = len(predicted - actual)
    false_negatives = len(actual - predicted)
    precision = true_positives / (true_positives + false_positives) if true_positives + false_positives else 0.0
    recall = true_positives / (true_positives + false_negatives) if true_positives + false_negatives else 0.0
    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }
