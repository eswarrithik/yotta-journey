from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
from yottajourney.analytics import evaluate_detection
from yottajourney.streaming import analyze_csv, detect_anomalies_csv, export_filtered_events

st.set_page_config(page_title="JourneyIQ · Customer Analytics", page_icon="↗", layout="wide")
st.markdown("<style>.block-container{padding-top:1.5rem}.stMetric{background:#fff;border:1px solid #e4e9ed;padding:16px;border-radius:16px}.stApp{background:#f6f8fb}</style>", unsafe_allow_html=True)
root = Path(__file__).parent / "data"

if not (root / "sessions.csv").exists():
    st.title("JourneyIQ")
    st.info("No generated dataset was found. Generate the deterministic starter dataset to populate this analytics workspace.")
    if st.button("Generate starter dataset", type="primary"):
        from yottajourney.pipeline import Config, generate
        with st.spinner("Generating JourneyIQ starter data…"):
            generate(Config(), root)
        st.rerun()
    st.stop()

entity_names = ["customers", "sessions", "journey_events", "pages", "products", "carts", "cart_items", "orders", "support_tickets", "experiments", "experiment_assignments", "journey_outcomes"]
tables = {name: pd.read_csv(root / f"{name}.csv") for name in entity_names if name != "journey_events"}
event_path = root / "journey_events.csv"
for name, frame in tables.items():
    for column in frame.columns:
        if column.endswith("_at") or column in ("event_timestamp", "ingestion_timestamp"):
            frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
profile = "FULL DATA" if len(tables["sessions"]) >= 100_000 else "DEMO DATA"

st.sidebar.title("JourneyIQ")
st.sidebar.caption(f"{profile} · Seed {json.loads((root / 'reproducibility.json').read_text()).get('seed', 'unknown')}")
page = st.sidebar.radio("Workspace", ["Executive Overview", "Customer Journey Funnel", "Friction Analysis", "Channel Analysis", "Anomaly Monitoring", "Data Quality"])
channel = st.sidebar.selectbox("Channel", ["All", "website", "mobile_app"])
device = st.sidebar.selectbox("Device", ["All", "desktop", "mobile", "tablet"])
product_names = dict(zip(tables["products"].product_id, tables["products"].product_name))
product_id = st.sidebar.selectbox("Product", ["All", *product_names], format_func=lambda value: "All products" if value == "All" else product_names[value])
days = st.sidebar.selectbox("Date range", [7, 30, 90], index=1, format_func=lambda value: f"Last {value} days")
latest = tables["sessions"].started_at.max()
cutoff = latest - pd.Timedelta(days=days)
session_cohort = tables["sessions"]
if channel != "All":
    session_cohort = session_cohort[session_cohort.channel.eq(channel)]
if device != "All":
    session_cohort = session_cohort[session_cohort.device_type.eq(device)]
session_cohort = session_cohort[session_cohort.started_at.ge(cutoff)]
result = analyze_csv(event_path, tables, channel, device, product_id, start_at=cutoff, as_of=tables["sessions"].ended_at.max(), chunk_size=20_000)
filtered_ids = result["filtered_session_ids"]
filtered_sessions = session_cohort[session_cohort.session_id.astype(str).isin(filtered_ids)]
filtered_tables = dict(tables)
filtered_tables["sessions"] = filtered_sessions
filtered_tables["orders"] = tables["orders"][tables["orders"].session_id.astype(str).isin(filtered_ids)]
filtered_tables["carts"] = tables["carts"][tables["carts"].session_id.astype(str).isin(filtered_ids)]
filtered_tables["support_tickets"] = tables["support_tickets"][tables["support_tickets"].session_id.astype(str).isin(filtered_ids)]

st.markdown(f"**{profile}** · Seed 20261022 · active filters: {days} days, {channel}, {device}, {product_id}")
st.title(page)
st.caption(f"Filtered {result['sessions']:,} / {len(tables['sessions']):,} sessions · {result['filtered_event_count']:,} / {json.loads((root / 'validation_report.json').read_text())['entity_row_counts']['journey_events']:,} events")
if result["sessions"] == 0:
    st.info("No sessions match the active date, channel, device, and product filters. Broaden the date range or reset the cohort filters.")


def show_kpis():
    columns = st.columns(5)
    values = [
        ("Filtered sessions", f"{result['sessions']:,}"),
        ("Eligible funnel entries", f"{result['eligible_sessions']:,}"),
        ("Distinct converting sessions", f"{result['purchases']:,}"),
        ("Conversion rate", f"{result['conversion_rate']:.1%}"),
        ("Support contact rate", f"{result['support_contact_rate']:.1%}"),
    ]
    for column, (label, value) in zip(columns, values):
        column.metric(label, value)


if page == "Executive Overview":
    show_kpis()
    left, right = st.columns([1.4, 1])
    with left:
        st.subheader("Eligible-session journey funnel")
        funnel = pd.DataFrame(result["funnel"])
        st.plotly_chart(px.funnel(funnel, x="sessions", y="stage", color_discrete_sequence=["#4f46a5"]), use_container_width=True)
    with right:
        st.subheader("Journey health")
        st.metric("Mature-cart abandonment", f"{result['abandonment_rate']:.1%}", help=f"{result['abandoned_cart_sessions']:,} abandoned of {result['eligible_cart_sessions']:,} carts idle for at least 30 minutes.")
        st.metric("Support sessions", f"{result['support_sessions']:,}", help="Distinct filtered sessions with at least one support ticket.")
        st.metric("Median ingestion delay", f"{result['median_latency_seconds']:.0f}s")
        if result["support_sessions"] == 0:
            st.info("No support contacts occur in this filtered cohort; the full dataset may still contain support journeys.")
    st.caption(f"Conversion = {result['purchases']:,} distinct eligible converting sessions ÷ {result['eligible_sessions']:,} eligible human funnel entries. Bots and sessions without a session-start event are excluded.")

elif page == "Customer Journey Funnel":
    show_kpis()
    funnel = pd.DataFrame(result["funnel"])
    st.plotly_chart(px.funnel(funnel, x="sessions", y="stage", color_discrete_sequence=["#4f46a5"]), use_container_width=True)
    display = funnel.copy()
    for column in ("conversion_rate", "dropoff_rate"):
        display[column] = display[column].map(lambda value: f"{value:.1%}")
    st.dataframe(display, hide_index=True, use_container_width=True)
    st.caption("Stage counts are distinct eligible sessions. Each stage conversion/drop-off divides by the immediately preceding stage; overall conversion divides by eligible funnel-entry sessions.")

elif page == "Friction Analysis":
    st.subheader("High-friction pages")
    friction = result["friction"]
    if friction.empty:
        st.info("No page activity matches these filters. Broaden the date range or select another channel/device.")
    else:
        st.dataframe(friction.head(10), hide_index=True, use_container_width=True)
    st.metric("Failed payment events", f"{result['checkout_failures']:,}")
    st.metric("Median event ingestion delay", f"{result['median_latency_seconds']:.0f}s")
    st.caption("Page activity and payment failures use the active session cohort. Ingestion latency is not the same as out-of-order event arrival.")

elif page == "Channel Analysis":
    show_kpis()
    counts = pd.DataFrame([{"Channel": key, "Sessions": value} for key, value in result["channel_sessions"].items()])
    if counts.empty:
        st.info("No channel sessions match the active filters.")
    else:
        st.plotly_chart(px.bar(counts, x="Channel", y="Sessions", color="Channel", color_discrete_sequence=["#4f46a5", "#087f8c"]), use_container_width=True)
    st.metric("Support-contacting sessions", f"{result['support_sessions']:,}")
    st.info("A filtered channel can legitimately have zero support contacts; this is a cohort result, not missing data.")

elif page == "Anomaly Monitoring":
    prediction = detect_anomalies_csv(event_path, tables["sessions"], filtered_ids, chunk_size=20_000)
    truth_path = root / "ground_truth.csv"
    truth = pd.read_csv(truth_path) if truth_path.exists() else pd.DataFrame(columns=["entity_id", "issue_type"])
    truth = truth[truth.entity_id.isin(filtered_ids)]
    scores = evaluate_detection(prediction, truth)
    columns = st.columns(6)
    for column, key in zip(columns, ["true_positives", "false_positives", "false_negatives", "precision", "recall", "f1"]):
        value = f"{scores[key]:.1%}" if key in ("precision", "recall", "f1") else f"{scores[key]:,}"
        column.metric(key.replace("_", " ").title(), value)
    if prediction.empty:
        st.success("No anomalies detected in this filtered cohort.")
    else:
        st.dataframe(prediction, hide_index=True, use_container_width=True)
    st.caption("Predictions are computed from filtered source rows. Ground-truth labels are loaded only after detection, for scoring.")

elif page == "Data Quality":
    report_path = root / "validation_report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text())
        reproducibility = json.loads((root / "reproducibility.json").read_text()).get("comparison")
        if reproducibility is None:
            st.warning("Paired SHA-256 reproducibility has not been run for this output. Run `python -m yottajourney.pipeline --output data --seed 20261022 --verify-reproducibility` from the project folder.")
        elif reproducibility["identical"]:
            st.success(f"Paired reproducibility passed: {len(reproducibility['datasets_compared'])} canonical CSV files, row counts, derived metrics, and anomaly counts match.")
        else:
            st.error("Paired reproducibility comparison found a mismatch; see the report below.")
        if report["status"] == "passed":
            st.success("Structural integrity checks passed for the full generated dataset.")
        else:
            st.error(f"Structural integrity review required: {len(report['errors'])} failed checks.")
        structural, anomalies = st.columns(2)
        with structural:
            st.subheader("Structural integrity · full dataset")
            st.dataframe(pd.DataFrame([{"Check": name.replace("_", " ").title(), "Result": "PASS" if passed else "FAIL"} for name, passed in report["checks"].items()]), hide_index=True, use_container_width=True)
        with anomalies:
            st.subheader("Intentional anomaly evaluation · active filter")
            st.json(report["anomaly_evaluation"])
            st.caption("Injected anomalies are scored separately and do not automatically fail foreign-key or schema integrity checks.")
        st.subheader("Filtered vs generated row counts")
        filtered_count_rows = []
        for name in entity_names:
            if name == "journey_events":
                filtered_count = result["filtered_event_count"]
            elif name == "sessions":
                filtered_count = result["sessions"]
            else:
                filtered_count = len(filtered_tables[name]) if name in filtered_tables else "Not session-filtered"
            filtered_count_rows.append({"Entity": name, "Generated rows": report["entity_row_counts"][name], "Filtered sessions/events": filtered_count})
        st.dataframe(pd.DataFrame(filtered_count_rows), hide_index=True, use_container_width=True)
        with st.expander("Full-profile validation report"):
            st.json(report)
    else:
        st.error("Validation report is missing. Regenerate the dataset to produce structural checks and a reproducibility manifest.")

st.divider()
metadata = {
    "dataset": profile,
    "filters": {"days": days, "channel": channel, "device": device, "product_id": product_id},
    "generated_sessions": len(tables["sessions"]),
    "filtered_sessions": result["sessions"],
    "generated_events": json.loads((root / "validation_report.json").read_text())["entity_row_counts"]["journey_events"],
    "filtered_events": result["filtered_event_count"],
}
with TemporaryDirectory(prefix="journeyiq-export-") as temporary:
    csv_path = Path(temporary) / "journeyiq_filtered_events.csv"
    json_path = Path(temporary) / "journeyiq_filtered_events.json"
    export_filtered_events(event_path, csv_path, filtered_ids, chunk_size=20_000)
    export_filtered_events(event_path, json_path, filtered_ids, chunk_size=20_000, as_json=True, metadata=metadata)
    left_export, right_export = st.columns(2)
    with csv_path.open("rb") as csv_file:
        left_export.download_button("Export filtered events CSV", csv_file, file_name=csv_path.name, mime="text/csv", help=f"{profile}; {result['filtered_event_count']:,} filtered event rows.")
    with json_path.open("rb") as json_file:
        right_export.download_button("Export filtered events JSON", json_file, file_name=json_path.name, mime="application/json", help=f"{profile}; {result['filtered_event_count']:,} filtered event rows.")
st.caption("JourneyIQ · DEMO DATA or FULL DATA is determined from the generated profile row count; filtered dashboards never stand in for full-dataset verification.")
