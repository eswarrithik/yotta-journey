from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .analytics import FUNNEL, SESSION_TIMEOUT


def _event_chunks(path: str | Path, chunk_size: int):
    return pd.read_csv(path, chunksize=chunk_size, dtype={"event_id": "string", "session_id": "string", "customer_id": "string", "anonymous_id": "string", "event_type": "string", "channel": "string", "page_id": "string", "product_id": "string", "event_version": "string", "event_properties": "string"})


def _bound(value):
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def analyze_csv(
    event_path: str | Path,
    tables: dict[str, pd.DataFrame],
    channel: str = "All",
    device: str = "All",
    product_id: str = "All",
    start_at=None,
    end_at=None,
    as_of=None,
    chunk_size: int = 20_000,
) -> dict:
    sessions = tables["sessions"].copy()
    if channel != "All":
        sessions = sessions[sessions.channel.eq(channel)]
    if device != "All":
        sessions = sessions[sessions.device_type.eq(device)]
    if start_at is not None:
        sessions = sessions[pd.to_datetime(sessions.started_at, utc=True).ge(_bound(start_at))]
    if end_at is not None:
        sessions = sessions[pd.to_datetime(sessions.started_at, utc=True).lt(_bound(end_at))]

    base_ids = set(sessions.session_id.astype(str))
    product_sessions = set() if product_id != "All" else base_ids.copy()
    entry_ids = set()
    for chunk in _event_chunks(event_path, chunk_size):
        chunk = chunk[chunk.session_id.isin(base_ids)]
        if chunk.empty:
            continue
        if product_id != "All":
            product_sessions.update(chunk.loc[chunk.product_id.eq(product_id), "session_id"].astype(str))
        entry_ids.update(chunk.loc[chunk.event_type.eq("session_started"), "session_id"].astype(str))

    sessions = sessions[sessions.session_id.astype(str).isin(product_sessions)].copy()
    session_ids = set(sessions.session_id.astype(str))
    entries = session_ids & entry_ids
    eligible = entries - set(sessions.loc[sessions.is_bot, "session_id"].astype(str))
    carts = tables["carts"][tables["carts"].session_id.astype(str).isin(eligible)]
    cart_sessions = set(carts.session_id.astype(str))
    session_ends = pd.to_datetime(sessions.set_index(sessions.session_id.astype(str)).ended_at, utc=True, errors="coerce")
    event_last = {}
    stage_sessions = {event: set() for _, event in FUNNEL}
    latency_parts = []
    page_latency_parts = {}
    page_sessions = {}
    page_event_counts = {}
    checkout_failures = 0
    filtered_event_count = 0
    filtered_event_max = None

    for chunk in _event_chunks(event_path, chunk_size):
        chunk = chunk[chunk.session_id.astype(str).isin(session_ids)]
        if chunk.empty:
            continue
        filtered_event_count += len(chunk)
        event_times = pd.to_datetime(chunk.event_timestamp, utc=True)
        chunk = chunk.assign(event_timestamp=event_times)
        chunk_max = event_times.max()
        if filtered_event_max is None or chunk_max > filtered_event_max:
            filtered_event_max = chunk_max
        for session_id, timestamp in chunk.loc[chunk.session_id.isin(cart_sessions)].groupby("session_id", observed=True).event_timestamp.max().items():
            key = str(session_id)
            if key not in event_last or timestamp > event_last[key]:
                event_last[key] = timestamp
        human = chunk[chunk.session_id.astype(str).isin(eligible)]
        if human.empty:
            continue
        latencies = (pd.to_datetime(human.ingestion_timestamp, utc=True) - human.event_timestamp).dt.total_seconds()
        latency_parts.append(latencies.to_numpy(dtype="float64"))
        checkout_failures += int(human.event_type.eq("purchase_failed").sum())
        for _, event_type in FUNNEL:
            stage_sessions[event_type].update(human.loc[human.event_type.eq(event_type), "session_id"].astype(str))
        page_events = human[human.page_id.notna()]
        if not page_events.empty:
            page_events = page_events.assign(_latency=latencies.loc[page_events.index])
            for page_id, group in page_events.groupby("page_id", observed=True):
                page_id = str(page_id)
                page_event_counts[page_id] = page_event_counts.get(page_id, 0) + len(group)
                page_sessions.setdefault(page_id, set()).update(group.session_id.astype(str))
                page_latency_parts.setdefault(page_id, []).append(group["_latency"].to_numpy(dtype="float64"))

    if as_of is None:
        as_of_time = filtered_event_max if filtered_event_max is not None else pd.Timestamp.now(tz="UTC")
    else:
        as_of_time = _bound(as_of)
    mature_carts = set()
    for session_id in cart_sessions:
        ended = session_ends.get(session_id, pd.NaT)
        if pd.isna(ended):
            ended = event_last.get(session_id, pd.NaT)
        if not pd.isna(ended) and as_of_time - ended >= SESSION_TIMEOUT:
            mature_carts.add(session_id)

    orders = tables["orders"]
    orders = orders[orders.session_id.astype(str).isin(eligible)]
    if "status" in orders:
        orders = orders[orders.status.eq("paid")]
    paid_order_ids = set(orders.order_id.dropna())
    converting_sessions = set(orders.loc[orders.order_id.isin(paid_order_ids), "session_id"].astype(str)) & eligible
    abandoned_carts = mature_carts - converting_sessions
    support = tables["support_tickets"][tables["support_tickets"].session_id.astype(str).isin(session_ids)]
    support_sessions = set(support.session_id.astype(str))
    counts = [len(stage_sessions[event] & eligible) for _, event in FUNNEL]
    funnel = []
    for index, ((stage, _), count) in enumerate(zip(FUNNEL, counts)):
        prior = len(eligible) if index == 0 else counts[index - 1]
        funnel.append({"stage": stage, "sessions": count, "eligible_sessions": prior, "conversion_rate": count / prior if prior else 0.0, "dropoff_count": max(0, prior - count), "dropoff_rate": max(0, prior - count) / prior if prior else 0.0})
    friction_rows = []
    for page_id, parts in page_latency_parts.items():
        friction_rows.append({"page_id": page_id, "events": page_event_counts[page_id], "sessions": len(page_sessions[page_id]), "median_latency_seconds": float(np.median(np.concatenate(parts)))})
    friction = pd.DataFrame(friction_rows, columns=["page_id", "events", "sessions", "median_latency_seconds"])
    friction = friction.merge(tables["pages"][["page_id", "page_name"]], on="page_id", how="left").sort_values("median_latency_seconds", ascending=False)
    all_latencies = np.concatenate(latency_parts) if latency_parts else np.array([], dtype="float64")
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
        "checkout_failures": checkout_failures,
        "median_latency_seconds": float(np.median(all_latencies)) if len(all_latencies) else 0.0,
        "anonymous_sessions": int(sessions.customer_id.isna().sum()),
        "identified_sessions": int(sessions.customer_id.notna().sum()),
        "channel_sessions": sessions.groupby("channel").session_id.nunique().to_dict(),
        "filtered_event_count": filtered_event_count,
        "filtered_session_ids": session_ids,
    }


def detect_anomalies_csv(event_path: str | Path, sessions: pd.DataFrame, session_ids: set, chunk_size: int = 20_000) -> pd.DataFrame:
    session_lookup = sessions.set_index("session_id")
    found = []

    def inspect_group(session_id, group):
        source_order = list(group.sort_values(["event_timestamp", "event_id"], kind="stable").event_id)
        arrival_order = list(group.sort_values(["ingestion_timestamp", "event_id"], kind="stable").event_id)
        if source_order != arrival_order:
            found.append((session_id, "out_of_order_arrival"))
        session = session_lookup.loc[session_id]
        if session.consent_status != "granted" and (pd.notna(session.customer_id) or group.customer_id.notna().any()):
            found.append((session_id, "identity_stitching"))
        elif pd.notna(session.customer_id) and group.customer_id.dropna().ne(session.customer_id).any():
            found.append((session_id, "identity_stitching"))
        purchases = group[group.event_type.eq("purchase_completed")]
        order_ids = purchases.event_properties.map(lambda value: json.loads(value).get("order_id"))
        if order_ids.dropna().duplicated(keep=False).any():
            found.append((session_id, "duplicate_conversion"))
        if bool(session.get("is_bot", False)) or any(json.loads(value).get("bot_signal", False) for value in group.event_properties):
            found.append((session_id, "bot_traffic"))

    carry = pd.DataFrame()
    for chunk in _event_chunks(event_path, chunk_size):
        chunk = chunk[chunk.session_id.isin(session_ids)]
        if carry.empty:
            current = chunk
        elif chunk.empty:
            current = carry
        else:
            current = pd.concat([carry, chunk], ignore_index=True)
        if current.empty:
            continue
        final_session = current.session_id.iloc[-1]
        complete = current[current.session_id.ne(final_session)]
        for session_id, group in complete.groupby("session_id", sort=False, observed=True):
            inspect_group(session_id, group)
        carry = current[current.session_id.eq(final_session)].copy()
    if not carry.empty:
        for session_id, group in carry.groupby("session_id", sort=False, observed=True):
            inspect_group(session_id, group)
    return pd.DataFrame(found, columns=["entity_id", "issue_type"]).drop_duplicates().reset_index(drop=True)


def export_filtered_events(event_path: str | Path, destination: str | Path, session_ids: set, chunk_size: int = 20_000, as_json: bool = False, metadata: dict | None = None):
    destination = Path(destination)
    header = True
    if not as_json:
        for chunk in _event_chunks(event_path, chunk_size):
            selected = chunk[chunk.session_id.isin(session_ids)]
            if selected.empty:
                continue
            selected.to_csv(destination, mode="w" if header else "a", header=header, index=False, lineterminator="\n")
            header = False
        if header:
            pd.read_csv(event_path, nrows=0).to_csv(destination, index=False, lineterminator="\n")
        return
    with destination.open("w", encoding="utf-8", newline="") as handle:
        payload = {key: value for key, value in (metadata or {}).items() if key != "events"}
        handle.write("{")
        if payload:
            handle.write(json.dumps(payload, ensure_ascii=False)[1:-1] + ",")
        handle.write('"events":[')
        first = True
        for chunk in _event_chunks(event_path, chunk_size):
            selected = chunk[chunk.session_id.isin(session_ids)]
            if selected.empty:
                continue
            records = json.loads(selected.to_json(orient="records", date_format="iso"))
            for record in records:
                if not first:
                    handle.write(",")
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                first = False
        handle.write("]}")


def validate_events_csv(event_path: str | Path, tables: dict[str, pd.DataFrame], taxonomy: dict, expected_rows: int, chunk_size: int = 20_000) -> tuple[dict[str, bool], int]:
    sessions = tables["sessions"].set_index("session_id")
    session_ids = set(sessions.index.astype(str))
    customers = set(tables["customers"].customer_id.astype(str))
    pages = tables["pages"].set_index("page_id")
    products = tables["products"].set_index("product_id")
    page_start = pd.to_datetime(pages.effective_from, utc=True)
    page_end = pd.to_datetime(pages.effective_to, utc=True)
    product_start = pd.to_datetime(products.effective_from, utc=True)
    product_end = pd.to_datetime(products.effective_to, utc=True)
    session_start = pd.to_datetime(sessions.started_at, utc=True)
    session_end = pd.to_datetime(sessions.ended_at, utc=True)
    checks = {"event_pk_unique": True, "event_id_ordering": True, "events_per_session_target": True, "event_timestamp_ordering": True, "event_session_fk_valid": True, "event_customer_fk_valid": True, "event_page_fk_valid": True, "event_product_fk_valid": True, "page_effective_at_event": True, "product_effective_at_event": True, "allowed_event_types": True, "event_volume_target": True, "event_page_requirements": True, "event_product_requirements": True, "allowed_event_channel_values": True, "event_session_time_bounds": True, "event_timestamp_latency_nonnegative": True}
    row_count = 0
    session_counts = {}
    previous_id = None
    previous_session = None
    previous_event_time = None
    for chunk in _event_chunks(event_path, chunk_size):
        row_count += len(chunk)
        event_ids = chunk.event_id.astype(str)
        ordered = not event_ids.duplicated().any() and (previous_id is None or event_ids.iloc[0] > previous_id)
        checks["event_pk_unique"] &= ordered
        checks["event_id_ordering"] &= ordered
        previous_id = event_ids.iloc[-1]
        for session_id, count in chunk.session_id.value_counts().items():
            key = str(session_id)
            session_counts[key] = session_counts.get(key, 0) + int(count)
        known_sessions = chunk.session_id.isin(session_ids)
        checks["event_session_fk_valid"] &= bool(known_sessions.all())
        checks["event_customer_fk_valid"] &= bool(chunk.customer_id.dropna().astype(str).isin(customers).all())
        checks["event_page_fk_valid"] &= bool(chunk.page_id.dropna().isin(pages.index).all())
        checks["event_product_fk_valid"] &= bool(chunk.product_id.dropna().isin(products.index).all())
        checks["allowed_event_types"] &= bool(chunk.event_type.isin(taxonomy).all())
        checks["allowed_event_channel_values"] &= bool(chunk.channel.isin(["website", "mobile_app"]).all())
        required_pages = [name for name, rules in taxonomy.items() if rules.get("page")]
        required_products = [name for name, rules in taxonomy.items() if rules.get("product")]
        checks["event_page_requirements"] &= bool(chunk.loc[chunk.event_type.isin(required_pages), "page_id"].notna().all())
        checks["event_product_requirements"] &= bool(chunk.loc[chunk.event_type.isin(required_products), "product_id"].notna().all())
        event_time = pd.to_datetime(chunk.event_timestamp, utc=True)
        ingestion_time = pd.to_datetime(chunk.ingestion_timestamp, utc=True)
        checks["event_timestamp_latency_nonnegative"] &= bool((ingestion_time >= event_time).all())
        within_chunk_order = pd.DataFrame({"session_id": chunk.session_id, "event_time": event_time}).groupby("session_id", sort=False, observed=True).event_time.diff().dropna().ge(pd.Timedelta(0)).all()
        checks["event_timestamp_ordering"] &= bool(within_chunk_order)
        if previous_session == str(chunk.session_id.iloc[0]):
            checks["event_timestamp_ordering"] &= bool(event_time.iloc[0] >= previous_event_time)
        previous_session = str(chunk.session_id.iloc[-1])
        previous_event_time = event_time.iloc[-1]
        bounds_start = chunk.session_id.map(session_start)
        bounds_end = chunk.session_id.map(session_end)
        checks["event_session_time_bounds"] &= bool(((event_time >= bounds_start).fillna(False) & (event_time <= bounds_end).fillna(False)).all())
        for key_column, keys, starts, ends, kind in (("page_id", set(pages.index.astype(str)), page_start, page_end, "page"), ("product_id", set(products.index.astype(str)), product_start, product_end, "product")):
            linked = chunk[chunk[key_column].notna()]
            if linked.empty:
                continue
            linked_time = pd.to_datetime(linked.event_timestamp, utc=True)
            starts_for_rows = linked[key_column].map(starts)
            ends_for_rows = linked[key_column].map(ends)
            valid = linked[key_column].astype(str).isin(keys) & (linked_time >= starts_for_rows) & (linked_time <= ends_for_rows)
            checks[f"{kind}_effective_at_event"] &= bool(valid.fillna(False).all())
    checks["event_volume_target"] = row_count == expected_rows
    per_session_target = expected_rows // len(sessions) if len(sessions) and expected_rows % len(sessions) == 0 else -1
    checks["events_per_session_target"] = len(session_counts) == len(sessions) and all(count == per_session_target for count in session_counts.values())
    return checks, row_count

