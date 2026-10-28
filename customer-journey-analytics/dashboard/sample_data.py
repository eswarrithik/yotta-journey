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
PAGES = ["Home", "Product details", "Cart", "Checkout", "Payment"]


def generate_demo_data(seed: int = 20261022, session_count: int = 80) -> dict[str, pd.DataFrame]:
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

    for number in range(1, session_count + 1):
        sid = f"SES-2026-{number:06d}"
        channel = "Website" if rng.random() < 0.68 else "Mobile app"
        device = str(rng.choice(["Desktop", "Mobile", "Tablet"], p=[0.34, 0.56, 0.10]))
        bot = number in {9, 31, 68} or rng.random() < 0.025
        customer = customers.iloc[int(rng.integers(0, len(customers)))]
        consent = str(customer.consent_status)
        identified = consent == "granted" and rng.random() < 0.78
        customer_id = str(customer.customer_id) if identified else None
        anonymous_id = f"AN-{int(rng.integers(1, 45)):06d}"
        started = anchor - timedelta(days=int(rng.integers(0, 30)), minutes=int(rng.integers(0, 1440)))
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
            sequence += ["page_viewed"] * int(rng.integers(4, 9))
        else:
            if rng.random() < 0.88:
                sequence.append("product_viewed")
                if rng.random() < 0.61:
                    sequence.append("added_to_cart")
                    if rng.random() < 0.72:
                        sequence.append("checkout_started")
                        sequence.append("payment_attempted")
                        sequence.append("purchase_completed" if rng.random() < 0.73 else "purchase_failed")
            sequence += ["page_viewed"] * int(rng.integers(1, 4))

        order_id = f"ORD-{number:06d}" if "purchase_completed" in sequence else None
        for position, event_type in enumerate(sequence, start=1):
            occurred = started + timedelta(seconds=position * int(rng.integers(22, 95)))
            latency = int(rng.integers(4, 240))
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
        if not bot and rng.random() < 0.09:
            support.append({"ticket_id": f"SUP-{number:06d}", "session_id": sid, "reason": str(rng.choice(["Payment question", "Delivery status", "Product help"]))})

    # Inject traceable source-level examples after generating the clean baseline.
    event_frame = pd.DataFrame(events)
    successful = event_frame.loc[event_frame.event_type.eq("purchase_completed")]
    if not successful.empty:
        original = successful.iloc[0].to_dict()
        duplicate = {**original, "event_id": f"EVT-{original['session_id']}-999999", "latency_seconds": 37}
        duplicate["ingestion_timestamp"] = duplicate["event_timestamp"] + timedelta(seconds=37)
        events.append(duplicate)

    delayed_candidates = [i for i, event in enumerate(events) if event["event_type"] == "product_viewed"]
    if delayed_candidates:
        delayed = events[delayed_candidates[0]]
        delayed["latency_seconds"] = 1_240
        delayed["ingestion_timestamp"] = delayed["event_timestamp"] + timedelta(seconds=1_240)

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
    eligible = set(sessions.session_id)
    events = data["events"][data["events"].session_id.isin(eligible)]
    rows = []
    previous = None
    for position, (label, event_type) in enumerate(STAGES):
        count = events.loc[events.event_type.eq(event_type), "session_id"].nunique()
        denominator = len(sessions) if position == 0 else previous
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
    eligible = set(sessions.session_id)
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
    }
    errors = [name for name, passed in checks.items() if not passed]
    return {"checks": checks, "errors": errors, "status": "PASS" if not errors else "FAIL", "rows": {name: len(frame) for name, frame in data.items()}}


def anomaly_summary(data: dict[str, pd.DataFrame], sessions: pd.DataFrame) -> dict[str, pd.DataFrame]:
    eligible = set(sessions.session_id)
    events = data["events"][data["events"].session_id.isin(eligible)]
    dupes = events[events.event_type.eq("purchase_completed")].groupby("order_id", dropna=True).filter(lambda group: len(group) > 1)
    bots = sessions[sessions.is_bot]
    delayed = events[events.latency_seconds.gt(600)]
    return {"duplicates": dupes, "bots": bots, "delayed": delayed}


def channel_funnel(data: dict[str, pd.DataFrame], sessions: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for channel in ("Website", "Mobile app"):
        cohort = sessions[sessions.channel.eq(channel)]
        counts = funnel_counts(data, cohort)
        counts["channel"] = channel
        parts.append(counts)
    return pd.concat(parts, ignore_index=True)
