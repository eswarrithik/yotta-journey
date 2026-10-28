from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

STAGES = [
    ("Session Started", "session_started"),
    ("Product Viewed", "product_viewed"),
    ("Added to Cart", "added_to_cart"),
    ("Checkout", "checkout_started"),
    ("Purchase", "purchase_completed"),
]
PAGES = ["Home", "Product details", "Cart", "Checkout", "Payment", "Help"]
ALLOWED_EVENT_TYPES = {"session_started", "page_viewed", "product_viewed", "added_to_cart", "checkout_started", "payment_attempted", "purchase_completed", "purchase_failed", "support_contacted"}


def generate_demo_data(seed: int = 20261022, session_count: int = 100) -> dict[str, pd.DataFrame]:
    """Create a deterministic source-like demo dataset; all shown metrics derive from these rows."""
    rng = np.random.default_rng(seed)
    anchor = datetime(2026, 5, 1, 12, tzinfo=timezone.utc)
    customers = pd.DataFrame(
        {
            "customer_id": [f"CUS-{i:06d}" for i in range(1, 56)],
            "consent_status": ["granted" if i % 5 else "denied" for i in range(1, 56)],
            "lifecycle_state": ["active"] * 55,
        }
    )
    sessions: list[dict] = []
    events: list[dict] = []
    orders: list[dict] = []
    support: list[dict] = []
    ground_truth: list[dict] = []

    for number in range(1, session_count + 1):
        sid = f"SES-2026-{number:06d}"
        channel = "Website" if rng.random() < 0.68 else "Mobile app"
        device = str(rng.choice(["Desktop", "Mobile", "Tablet"], p=[0.34, 0.56, 0.10]))
        bot = False if number == 1 else number in {9, 31, 68} or rng.random() < 0.025
        customer = customers.iloc[int(rng.integers(0, len(customers)))]
        consent = str(customer.consent_status)
        identified = consent == "granted" and rng.random() < 0.78
        customer_id = str(customer.customer_id) if identified else None
        anonymous_id = f"AN-{int(rng.integers(1, 45)):06d}"
        started = anchor - timedelta(days=int(rng.integers(0, 30)), minutes=int(rng.integers(0, 1440)))
        has_support = not bot and (number % 12 == 0 or rng.random() < 0.04)
        sessions.append(
            {
                "session_id": sid,
                "customer_id": customer_id,
                "anonymous_id": anonymous_id,
                "started_at": started,
                "channel": channel,
                "device": device,
                "consent_status": consent,
                "is_bot": bot,
            }
        )

        sequence = ["session_started"]
        if bot:
            sequence += ["page_viewed"] * int(rng.integers(12, 20))
        else:
            if number == 1 or rng.random() < 0.88:
                sequence.append("product_viewed")
                if number == 1 or rng.random() < 0.61:
                    sequence.append("added_to_cart")
                    if number == 1 or rng.random() < 0.72:
                        sequence.append("checkout_started")
                        sequence.append("payment_attempted")
                        sequence.append("purchase_completed" if number == 1 or rng.random() < 0.73 else "purchase_failed")
            sequence += ["page_viewed"] * int(rng.integers(12, 20))
        if has_support:
            sequence.append("support_contacted")

        order_id = f"ORD-{number:06d}" if "purchase_completed" in sequence else None
        for position, event_type in enumerate(sequence, start=1):
            occurred = started + timedelta(seconds=position * 20)
            latency = 2
            events.append(
                {
                    "event_id": f"EVT-{sid}-{position:06d}",
                    "session_id": sid,
                    "customer_id": customer_id,
                    "anonymous_id": anonymous_id,
                    "event_type": event_type,
                    "event_timestamp": occurred,
                    "ingestion_timestamp": occurred + timedelta(seconds=latency),
                    "latency_seconds": latency,
                    "channel": channel,
                    "device": device,
                    "page": _page_for(event_type),
                    "is_bot": bot,
                    "order_id": order_id if event_type == "purchase_completed" else None,
                }
            )
        if order_id:
            orders.append(
                {
                    "order_id": order_id,
                    "session_id": sid,
                    "customer_id": customer_id,
                    "ordered_at": started + timedelta(minutes=4),
                    "status": "paid",
                    "total_amount": round(float(rng.uniform(39, 249)), 2),
                }
            )
        if has_support:
            support.append({"ticket_id": f"SUP-{number:06d}", "session_id": sid, "reason": str(rng.choice(["Payment question", "Delivery status", "Product help"]))})

    # Inject auditable source-level scenarios; expected labels stay in their own table.
    first_session = [event for event in events if event["session_id"] == "SES-2026-000001"]
    first_session.sort(key=lambda event: event["event_timestamp"])
    if len(first_session) > 1:
        first_session[0]["ingestion_timestamp"] = first_session[0]["event_timestamp"] + timedelta(seconds=1_800)
        first_session[0]["latency_seconds"] = 1_800
        first_session[1]["ingestion_timestamp"] = first_session[1]["event_timestamp"] + timedelta(seconds=2)
        first_session[1]["latency_seconds"] = 2
        ground_truth.append({"entity_id": "SES-2026-000001", "issue_type": "out_of_order_arrival"})

    identity_session = sessions[1]
    identity_session["customer_id"] = None
    identity_session["consent_status"] = "denied"
    identity_event = next(event for event in events if event["session_id"] == identity_session["session_id"])
    identity_event["customer_id"] = "CUS-000001"
    ground_truth.append({"entity_id": identity_session["session_id"], "issue_type": "identity_stitching"})

    bot_session = sessions[3]
    bot_session["is_bot"] = True
    for event in events:
        if event["session_id"] == bot_session["session_id"]:
            event["is_bot"] = True
    ground_truth.append({"entity_id": bot_session["session_id"], "issue_type": "bot_traffic"})

    successful = [event for event in events if event["event_type"] == "purchase_completed"]
    if successful:
        original = successful[0]
        duplicate = {**original, "event_id": f"EVT-{original['session_id']}-999999"}
        events.append(duplicate)
        ground_truth.append({"entity_id": original["session_id"], "issue_type": "duplicate_conversion"})

    delayed_candidates = [event for event in events if event["event_type"] == "product_viewed"]
    if delayed_candidates:
        delayed = delayed_candidates[0]
        delayed["latency_seconds"] = 1_240
        delayed["ingestion_timestamp"] = delayed["event_timestamp"] + timedelta(seconds=1_240)
    for session in sessions:
        if session["is_bot"]:
            ground_truth.append({"entity_id": session["session_id"], "issue_type": "bot_traffic"})
    ground_truth_frame = pd.DataFrame(ground_truth, columns=["entity_id", "issue_type"]).drop_duplicates().sort_values(["entity_id", "issue_type"], kind="stable").reset_index(drop=True)
    event_frame = pd.DataFrame(events).sort_values("event_id", kind="stable").reset_index(drop=True)
    session_frame = pd.DataFrame(sessions).sort_values("session_id", kind="stable").reset_index(drop=True)
    order_frame = pd.DataFrame(orders, columns=["order_id", "session_id", "customer_id", "ordered_at", "status", "total_amount"])
    support_frame = pd.DataFrame(support, columns=["ticket_id", "session_id", "reason"])
    return {
        "customers": customers,
        "sessions": session_frame,
        "events": event_frame,
        "orders": order_frame,
        "support": support_frame,
        "ground_truth": ground_truth_frame,
    }


def _page_for(event_type: str) -> str | None:
    return {
        "session_started": "Home",
        "product_viewed": "Product details",
        "added_to_cart": "Cart",
        "checkout_started": "Checkout",
        "payment_attempted": "Payment",
        "purchase_completed": "Payment",
        "purchase_failed": "Payment",
        "page_viewed": "Home",
        "support_contacted": "Help",
    }.get(event_type)


def filtered_sessions(data: dict[str, pd.DataFrame], channel: str = "All channels", device: str = "All devices") -> pd.DataFrame:
    sessions = data["sessions"]
    mask = pd.Series(True, index=sessions.index)
    if channel != "All channels":
        mask &= sessions.channel.eq(channel)
    if device != "All devices":
        mask &= sessions.device.eq(device)
    return sessions.loc[mask].copy()


def funnel_counts(data: dict[str, pd.DataFrame], sessions: pd.DataFrame) -> pd.DataFrame:
    eligible = set(sessions.loc[~sessions.is_bot, "session_id"])
    events = data["events"][data["events"].session_id.isin(eligible)]
    rows = []
    previous = None
    for position, (label, event_type) in enumerate(STAGES):
        count = events.loc[events.event_type.eq(event_type), "session_id"].nunique()
        denominator = len(eligible) if position == 0 else previous
        rows.append(
            {
                "stage": label,
                "event_type": event_type,
                "sessions": int(count),
                "conversion_from_previous": count / denominator if denominator else 0.0,
                "dropoff_count": int((denominator or 0) - count),
                "dropoff_rate": ((denominator - count) / denominator) if denominator else 0.0,
            }
        )
        previous = count
    return pd.DataFrame(rows)


def page_friction(data: dict[str, pd.DataFrame], sessions: pd.DataFrame) -> pd.DataFrame:
    eligible = set(sessions.loc[~sessions.is_bot, "session_id"])
    events = data["events"][data["events"].session_id.isin(eligible) & data["events"].page.notna()]
    stage_pairs = [
        ("Home", "session_started", "product_viewed"),
        ("Product details", "product_viewed", "added_to_cart"),
        ("Cart", "added_to_cart", "checkout_started"),
        ("Checkout", "checkout_started", "purchase_completed"),
        ("Payment", "payment_attempted", "purchase_completed"),
    ]
    rows = []
    for page, entry_event, next_event in stage_pairs:
        entry = events[events.event_type.eq(entry_event)]
        entrants = set(entry.session_id)
        progressed = set(events.loc[events.event_type.eq(next_event), "session_id"])
        rows.append({
            "page": page,
            "page_views": int(events.page.eq(page).sum()),
            "sessions": len(entrants),
            "median_latency_seconds": float(entry.latency_seconds.median()) if len(entry) else 0.0,
            "dropoff_count": len(entrants - progressed),
            "dropoff_rate": len(entrants - progressed) / len(entrants) if entrants else 0.0,
        })
    return pd.DataFrame(rows).sort_values(["dropoff_rate", "median_latency_seconds", "page_views"], ascending=[False, False, False]).reset_index(drop=True)


def validate_sample(data: dict[str, pd.DataFrame], sessions: pd.DataFrame) -> dict:
    events = data["events"][data["events"].session_id.isin(set(sessions.session_id))]
    funnel = funnel_counts(data, sessions)
    latency = (events.ingestion_timestamp - events.event_timestamp).dt.total_seconds()
    checks = {
        "session_ids_unique": bool(data["sessions"].session_id.is_unique),
        "event_ids_unique": bool(data["events"].event_id.is_unique),
        "event_session_foreign_keys": bool(data["events"].session_id.isin(data["sessions"].session_id).all()),
        "event_latency_nonnegative": bool(latency.ge(0).all()),
        "funnel_monotonic": bool(funnel.sessions.is_monotonic_decreasing),
        "order_session_foreign_keys": bool(data["orders"].session_id.isin(data["sessions"].session_id).all()),
        "support_session_foreign_keys": bool(data["support"].session_id.isin(data["sessions"].session_id).all()),
        "customer_foreign_keys": bool(data["events"].customer_id.dropna().isin(data["customers"].customer_id).all()),
        "event_enum_values": bool(data["events"].event_type.isin(ALLOWED_EVENT_TYPES).all()),
    }
    errors = [name for name, passed in checks.items() if not passed]
    return {"checks": checks, "errors": errors, "status": "PASS" if not errors else "FAIL", "rows": {name: len(frame) for name, frame in data.items()}}


def anomaly_summary(data: dict[str, pd.DataFrame], sessions: pd.DataFrame) -> dict[str, pd.DataFrame]:
    eligible = set(sessions.session_id)
    events = data["events"][data["events"].session_id.isin(eligible)]
    session_rows = sessions.set_index("session_id")
    duplicates = events[events.event_type.eq("purchase_completed")].groupby("order_id", dropna=True).filter(lambda group: len(group) > 1)
    bots = sessions[sessions.is_bot]
    delayed = events[events.latency_seconds.gt(600)]
    out_of_order_ids = []
    identity_ids = []
    detections = []
    for session_id, group in events.groupby("session_id", sort=True):
        occurred = list(group.sort_values(["event_timestamp", "event_id"], kind="stable").event_id)
        arrived = list(group.sort_values(["ingestion_timestamp", "event_id"], kind="stable").event_id)
        if occurred != arrived:
            out_of_order_ids.append(session_id)
            detections.append((session_id, "out_of_order_arrival"))
        session = session_rows.loc[session_id]
        if session.consent_status != "granted" and (pd.notna(session.customer_id) or group.customer_id.notna().any()):
            identity_ids.append(session_id)
            detections.append((session_id, "identity_stitching"))
        if group[group.event_type.eq("purchase_completed")].order_id.dropna().duplicated(keep=False).any():
            detections.append((session_id, "duplicate_conversion"))
        if bool(session.is_bot) or bool(group.is_bot.any()):
            detections.append((session_id, "bot_traffic"))
    predictions = pd.DataFrame(detections, columns=["entity_id", "issue_type"]).drop_duplicates()
    truth = data.get("ground_truth", pd.DataFrame(columns=["entity_id", "issue_type"]))
    truth = truth[truth.entity_id.isin(eligible)]
    predicted_set = set(map(tuple, predictions[["entity_id", "issue_type"]].to_numpy().tolist()))
    truth_set = set(map(tuple, truth[["entity_id", "issue_type"]].to_numpy().tolist()))
    true_positives = len(predicted_set & truth_set)
    false_positives = len(predicted_set - truth_set)
    false_negatives = len(truth_set - predicted_set)
    precision = true_positives / (true_positives + false_positives) if true_positives + false_positives else 0.0
    recall = true_positives / (true_positives + false_negatives) if true_positives + false_negatives else 0.0
    scores = {"true_positives": true_positives, "false_positives": false_positives, "false_negatives": false_negatives, "precision": precision, "recall": recall, "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}
    return {"duplicates": duplicates, "bots": bots, "delayed": delayed, "out_of_order": events[events.session_id.isin(out_of_order_ids)], "identity": events[events.session_id.isin(identity_ids)], "ground_truth": truth, "detections": predictions, "scores": scores}


def channel_funnel(data: dict[str, pd.DataFrame], sessions: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for channel in ("Website", "Mobile app"):
        cohort = sessions[sessions.channel.eq(channel)]
        counts = funnel_counts(data, cohort)
        counts["channel"] = channel
        counts["channel_eligible_sessions"] = int((~cohort.is_bot).sum())
        parts.append(counts)
    return pd.concat(parts, ignore_index=True)
