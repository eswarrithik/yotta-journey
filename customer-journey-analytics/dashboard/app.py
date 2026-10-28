from __future__ import annotations

from pathlib import Path
import json
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sample_data import (
    STAGES,
    anomaly_summary,
    channel_funnel,
    filtered_sessions,
    funnel_counts,
    generate_demo_data,
    page_friction,
    validate_sample,
)

st.set_page_config(page_title="JourneyIQ · Demo Analytics", page_icon="↗", layout="wide", initial_sidebar_state="expanded")
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
    :root{--teal:#087f8c;--ink:#20313b;--muted:#77868d;--line:#e8edef;--canvas:#f5f8f8}
    .stApp{background:var(--canvas);font-family:'DM Sans',sans-serif;color:var(--ink)}
    [data-testid="stHeader"]{background:rgba(245,248,248,.94)}
    .block-container{max-width:1480px;padding-top:1.4rem;padding-bottom:2rem}
    [data-testid="stSidebar"]{background:#fff;border-right:1px solid var(--line)}
    [data-testid="stSidebar"] .block-container{padding-top:1.35rem}
    [data-testid="stMetric"]{background:#fff;border:1px solid var(--line);border-radius:14px;padding:17px 18px;box-shadow:0 2px 8px #19343d06}
    [data-testid="stMetricLabel"]{color:#78868c;font-size:.82rem}
    [data-testid="stMetricValue"]{color:var(--ink);font-family:'Manrope',sans-serif;font-weight:700;letter-spacing:-.04em}
    [data-testid="stPlotlyChart"]{background:#fff;border:1px solid var(--line);border-radius:14px;padding:8px 8px 0}
    [data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:12px;overflow:hidden}
    h1,h2,h3{font-family:'Manrope',sans-serif!important;letter-spacing:-.035em!important;color:var(--ink)!important}
    h1{font-size:2rem!important;font-weight:750!important;margin-bottom:.25rem!important}
    h2{font-size:1.25rem!important}
    .demo-banner{display:flex;align-items:center;gap:10px;border:1px solid #f0d9a2;background:#fff8e8;border-radius:12px;padding:10px 14px;margin:0 0 18px;color:#775720;font-size:13px}
    .demo-pill{background:#edb947;color:#3d2d0b;border-radius:5px;padding:3px 7px;font-size:10px;font-weight:800;letter-spacing:.08em}
    .brand{display:flex;align-items:center;gap:10px;margin:0 0 1.1rem;padding:0 3px}
    .brandmark{width:38px;height:38px;border-radius:12px;background:#e7f4f2;color:var(--teal);display:grid;place-items:center;font-size:22px;font-weight:800}
    .brandname{font-family:'Manrope',sans-serif;font-weight:800;font-size:17px;color:#19323a;line-height:1.1}
    .brandname span{color:var(--teal)}.brandcaption{font-size:9px;letter-spacing:.16em;color:#829097;font-weight:700;margin-top:4px}
    .section-intro{color:var(--muted);font-size:13px;margin:0 0 1rem}
    .quality-pass{border:1px solid #cde8dc;background:#edf8f2;color:#267352;border-radius:12px;padding:14px 16px;font-size:14px}
    .quality-warn{border:1px solid #f0dbb0;background:#fff8e9;color:#795d25;border-radius:12px;padding:14px 16px;font-size:14px}
    .small-note{color:#859198;font-size:11px}
    div[data-testid="stTabs"] button{font-weight:600}
    @media(max-width:700px){.block-container{padding-left:1rem;padding-right:1rem}.demo-banner{align-items:flex-start}}
    </style>
    """,
    unsafe_allow_html=True,
)


data = generate_demo_data()

st.sidebar.markdown(
    '<div class="brand"><div class="brandmark">↗</div><div><div class="brandname">Journey<span>IQ</span></div><div class="brandcaption">JOURNEYIQ · ANALYTICS</div></div></div>',
    unsafe_allow_html=True,
)
st.sidebar.markdown("#### Analytics workspace")
section = st.sidebar.radio(
    "Explore",
    ["Executive overview", "Journey funnel", "Friction analysis", "Anomaly monitoring", "Data quality"],
    label_visibility="collapsed",
)
st.sidebar.divider()
st.sidebar.markdown("#### Filters")
channel_filter = st.sidebar.selectbox("Channel", ["All channels", "Website", "Mobile app"])
device_filter = st.sidebar.selectbox("Device", ["All devices", "Desktop", "Mobile", "Tablet"])
product_names = dict(zip(data["products"].product_id, data["products"].product_name))
product_filter = st.sidebar.selectbox("Product", ["All products", *product_names], format_func=lambda value: value if value == "All products" else product_names[value])
days_filter = st.sidebar.select_slider("Date range", options=[7, 14, 30], value=30, format_func=lambda days: f"Last {days} days")
st.sidebar.caption("Filters update every metric and chart in this view.")
st.sidebar.divider()
st.sidebar.markdown("**Source profile**")
st.sidebar.caption(f"DEMO DATA · {len(data['sessions']):,} generated sessions · {len(data['events']):,} generated events · seed 20261022")

sessions = filtered_sessions(data, channel_filter, device_filter, product_filter)
cutoff = data["sessions"].started_at.max() - pd.Timedelta(days=days_filter)
sessions = sessions[sessions.started_at >= cutoff].copy()
eligible_ids = set(sessions.session_id)
filtered_data = {
    **data,
    "events": data["events"][data["events"].session_id.isin(eligible_ids)].copy(),
    "orders": data["orders"][data["orders"].session_id.isin(eligible_ids)].copy(),
    "support": data["support"][data["support"].session_id.isin(eligible_ids)].copy(),
}
funnel = funnel_counts(filtered_data, sessions)
anomalies = anomaly_summary(filtered_data, sessions)
validation = validate_sample(data, sessions)
entry_ids = set(sessions.loc[~sessions.is_bot, "session_id"])
entry_ids &= set(filtered_data["events"].loc[filtered_data["events"].event_type.eq("session_started"), "session_id"])
paid_orders = filtered_data["orders"].query("status == 'paid'")
purchase_ids = set(paid_orders.session_id) & entry_ids
purchases = len(purchase_ids)
customer_count = int(sessions.customer_id.nunique())
session_count = int(sessions.session_id.nunique())
eligible_session_count = len(entry_ids)
cart_ids = set(filtered_data["events"].loc[filtered_data["events"].event_type.eq("added_to_cart") & filtered_data["events"].session_id.isin(entry_ids), "session_id"])
last_activity = filtered_data["events"].groupby("session_id").event_timestamp.max()
as_of = data["events"].event_timestamp.max()
mature_cart_ids = {sid for sid in cart_ids if pd.notna(last_activity.get(sid)) and as_of - last_activity[sid] >= pd.Timedelta(minutes=30)} if pd.notna(as_of) else set()
abandoned_carts = len(mature_cart_ids - purchase_ids)
abandonment_rate = abandoned_carts / len(mature_cart_ids) if mature_cart_ids else 0.0
conversion_rate = purchases / eligible_session_count if eligible_session_count else 0.0
support_rate = filtered_data["support"].session_id.nunique() / session_count if session_count else 0.0

st.markdown(
    '<div class="demo-banner"><span class="demo-pill">DEMO DATA</span><span>Preview uses a deterministic JourneyIQ sample. Filtered metrics and source-event rows are derived from the generated demo records.</span></div>',
    unsafe_allow_html=True,
)
st.title(section)
st.markdown(
    f'<p class="section-intro">Customer journey intelligence · filtered {session_count:,}/{len(data["sessions"]):,} sessions · {len(filtered_data["events"]):,}/{len(data["events"]):,} events · product {product_filter}</p>',
    unsafe_allow_html=True,
)
if session_count == 0:
    st.info("No sessions match the active date, channel, device, and product filters. Widen the date range or reset the cohort filters.")


def show_kpis():
    columns = st.columns(5)
    values = [
        ("Total sessions", f"{session_count:,}"),
        ("Unique customers", f"{customer_count:,}"),
        ("Purchases", f"{purchases:,}"),
        ("Conversion rate", f"{conversion_rate:.1%}"),
        ("Abandonment rate", f"{abandonment_rate:.1%}"),
    ]
    for column, (label, value) in zip(columns, values):
        column.metric(label, value)


def chart_layout(fig, height=330):
    fig.update_layout(
        height=height,
        margin=dict(l=18, r=18, t=30, b=18),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family="DM Sans, sans-serif", color="#586970", size=12),
        hoverlabel=dict(bgcolor="white", font_size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="#edf1f2", zeroline=False)
    return fig


if section == "Executive overview":
    show_kpis()
    left, right = st.columns([1.35, 1])
    with left:
        st.subheader("Journey funnel")
        funnel_fig = go.Figure(go.Funnel(
            y=funnel.stage,
            x=funnel.sessions,
            textinfo="value+percent initial",
            marker=dict(color=["#087f8c", "#159c98", "#53b6a7", "#8178c7", "#5955a7"]),
            connector=dict(line=dict(color="#e8edef", width=1)),
            hovertemplate="%{y}<br>%{x} sessions<extra></extra>",
        ))
        funnel_fig.update_layout(margin=dict(l=10, r=15, t=16, b=5), height=330, paper_bgcolor="white", font=dict(family="DM Sans", color="#586970"))
        st.plotly_chart(funnel_fig, use_container_width=True, config={"displayModeBar": False})
    with right:
        st.subheader("Stage drop-off")
        drops = funnel.iloc[1:].copy()
        drops["dropoff_percent"] = drops.dropoff_rate * 100
        bar = px.bar(drops, x="dropoff_percent", y="stage", orientation="h", text=drops.dropoff_percent.map(lambda x: f"{x:.0f}%"), color="dropoff_percent", color_continuous_scale=["#72c2b4", "#087f8c", "#db8666"])
        bar.update_layout(coloraxis_showscale=False, yaxis={"categoryorder": "array", "categoryarray": drops.stage.tolist()})
        st.plotly_chart(chart_layout(bar, 330), use_container_width=True, config={"displayModeBar": False})
    st.caption(f"Conversion = {purchases:,} distinct converting sessions ÷ {eligible_session_count:,} eligible human session entries. Mature-cart abandonment = {abandoned_carts:,} abandoned ÷ {len(mature_cart_ids):,} carts idle for at least 30 minutes.")
    st.subheader("Channel journey comparison")
    by_channel = channel_funnel(filtered_data, sessions)
    by_channel["stage_rate"] = by_channel.apply(lambda row: row.sessions / max(1, int(row.channel_eligible_sessions)) * 100, axis=1)
    channel_chart = px.bar(by_channel, x="stage", y="stage_rate", color="channel", barmode="group", color_discrete_map={"Website": "#087f8c", "Mobile app": "#8178c7"}, labels={"stage_rate": "% of channel sessions", "stage": "Funnel stage", "channel": "Channel"}, hover_data={"sessions": True, "channel_eligible_sessions": True, "stage_rate": ":.1f"})
    st.plotly_chart(chart_layout(channel_chart, 320), use_container_width=True)
    st.metric("Support contact rate", f"{support_rate:.1%}", help=f"{filtered_data['support'].session_id.nunique():,} distinct support sessions ÷ {session_count:,} filtered sessions.")
    if filtered_data["support"].empty:
        st.info("No support contacts occur in this filtered cohort; the generated sample may contain support sessions outside these filters.")

elif section == "Journey funnel":
    show_kpis()
    funnel_tab, channel_tab = st.tabs(["Overall funnel", "Compare channels"])
    with funnel_tab:
        left, right = st.columns([1.2, 1])
        with left:
            fig = go.Figure(go.Funnel(y=funnel.stage, x=funnel.sessions, textinfo="value+percent initial", marker=dict(color=["#087f8c", "#159c98", "#53b6a7", "#8178c7", "#5955a7"])))
            st.plotly_chart(chart_layout(fig, 370), use_container_width=True)
        with right:
            st.markdown("##### Stage detail")
            table = funnel[["stage", "sessions", "conversion_from_previous", "dropoff_count", "dropoff_rate"]].copy()
            table["conversion_from_previous"] = table.conversion_from_previous.map(lambda value: f"{value:.1%}")
            table["dropoff_rate"] = table.dropoff_rate.map(lambda value: f"{value:.1%}")
            st.dataframe(table, hide_index=True, use_container_width=True)
        st.caption("Stage counts are distinct eligible human sessions with the event. Stage conversion divides by the preceding stage; first-stage eligibility is a non-bot session-start event.")
    with channel_tab:
        by_channel = channel_funnel(filtered_data, sessions)
        by_channel["session_share"] = by_channel.apply(lambda row: row.sessions / max(1, int(row.channel_eligible_sessions)) * 100, axis=1)
        fig = px.bar(by_channel, x="stage", y="session_share", color="channel", barmode="group", text=by_channel.session_share.map(lambda value: f"{value:.0f}%"), color_discrete_map={"Website": "#087f8c", "Mobile app": "#8178c7"}, labels={"session_share": "% of channel sessions", "stage": "Stage"})
        st.plotly_chart(chart_layout(fig, 380), use_container_width=True)

elif section == "Friction analysis":
    st.subheader("Pages with the most journey friction")
    friction = page_friction(filtered_data, sessions)
    if friction.empty:
        st.info("No page activity matches the current filters. Widen the date range or choose a different channel/device.")
    else:
        left, right = st.columns([1.1, 1])
        with left:
            chart = px.bar(friction, x="dropoff_rate", y="page", orientation="h", color="dropoff_rate", color_continuous_scale=["#7ac4b7", "#0b8790", "#d9795b"], labels={"dropoff_rate": "Drop-off rate", "page": "Page"}, hover_data={"sessions": True, "dropoff_count": True, "page_views": True, "median_latency_seconds": True})
            chart.update_xaxes(tickformat=".0%")
            st.plotly_chart(chart_layout(chart, 350), use_container_width=True)
        with right:
            st.markdown("##### Page-level signals")
            display = friction.copy()
            display["dropoff_rate"] = display.dropoff_rate.map(lambda value: f"{value:.1%}")
            display["median_latency_seconds"] = display.median_latency_seconds.map(lambda value: f"{value:.0f}s")
            st.dataframe(display.rename(columns={"page": "Page", "page_views": "Views", "sessions": "Sessions", "median_latency_seconds": "Median latency", "dropoff_rate": "Drop-off"}), hide_index=True, use_container_width=True)
    st.info("Drop-off is calculated from unique eligible sessions entering a stage-specific page and not reaching the next funnel stage. Page latency is the median source-event ingestion delay.")
    failures = filtered_data["events"][filtered_data["events"].event_type.eq("purchase_failed")]
    st.metric("Failed payment attempts", f"{len(failures):,}")

elif section == "Anomaly monitoring":
    scores = anomalies["scores"]
    score_cols = st.columns(6)
    for column, key in zip(score_cols, ["true_positives", "false_positives", "false_negatives", "precision", "recall", "f1"]):
        value = f"{scores[key]:.1%}" if key in ("precision", "recall", "f1") else f"{scores[key]:,}"
        column.metric(key.replace("_", " ").title(), value)
    st.caption("Predictions are generated only from filtered source events and session fields. Ground-truth labels are loaded separately and used only for these evaluation scores.")
    tabs = st.tabs(["Duplicate conversions", "Bot traffic", "Out-of-order arrival", "Identity stitching", "Delayed ingestion"])
    with tabs[0]:
        if anomalies["duplicates"].empty:
            st.success("No repeated order conversion events occur in this filtered cohort.")
        else:
            st.dataframe(anomalies["duplicates"][["event_id", "session_id", "order_id", "event_timestamp", "ingestion_timestamp"]], hide_index=True, use_container_width=True)
    with tabs[1]:
        if anomalies["bots"].empty:
            st.info("No bot-classified sessions occur in this filtered cohort.")
        else:
            st.dataframe(anomalies["bots"][["session_id", "channel", "device", "started_at", "is_bot"]], hide_index=True, use_container_width=True)
    with tabs[2]:
        if anomalies["out_of_order"].empty:
            st.success("No out-of-order arrivals were detected in this filtered cohort.")
        else:
            st.dataframe(anomalies["out_of_order"][["event_id", "session_id", "event_type", "event_timestamp", "ingestion_timestamp"]], hide_index=True, use_container_width=True)
    with tabs[3]:
        if anomalies["identity"].empty:
            st.success("No consent-invalid identity links were detected in this filtered cohort.")
        else:
            st.dataframe(anomalies["identity"][["event_id", "session_id", "customer_id", "event_type"]], hide_index=True, use_container_width=True)
    with tabs[4]:
        if anomalies["delayed"].empty:
            st.success("No events exceeded the 10-minute ingestion-delay threshold.")
        else:
            st.dataframe(anomalies["delayed"][["event_id", "session_id", "event_type", "event_timestamp", "ingestion_timestamp", "latency_seconds"]], hide_index=True, use_container_width=True)

elif section == "Data quality":
    st.subheader("Validation status")
    if validation["status"] == "PASS":
        st.markdown(f'<div class="quality-pass"><b>✓ PASS</b> · {len(validation["checks"])} integrity checks succeeded for the filtered dataset.</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="quality-warn"><b>⚠ REVIEW</b> · {len(validation["errors"])} validation checks failed.</div>', unsafe_allow_html=True)
    st.write("")
    left, right = st.columns([1.15, 1])
    with left:
        st.markdown("##### Validation checks")
        checks = pd.DataFrame([{"Check": name.replace("_", " ").title(), "Result": "PASS" if result else "FAIL"} for name, result in validation["checks"].items()])
        st.dataframe(checks, hide_index=True, use_container_width=True)
    with right:
        st.markdown("##### Source row counts")
        filtered_counts = {"customers": len(data["customers"]), "sessions": len(sessions), "events": len(filtered_data["events"]), "orders": len(filtered_data["orders"]), "support tickets": len(filtered_data["support"]), "ground truth labels": len(anomalies["ground_truth"])}
        source_counts = {"customers": len(data["customers"]), "sessions": len(data["sessions"]), "events": len(data["events"]), "orders": len(data["orders"]), "support tickets": len(data["support"]), "ground truth labels": len(data["ground_truth"])}
        row_counts = pd.DataFrame([{"Dataset": name.title(), "Filtered rows": filtered_counts[name], "Generated rows": source_counts[name]} for name in filtered_counts])
        st.dataframe(row_counts, hide_index=True, use_container_width=True)
        st.metric("Grounded purchase sessions", f"{filtered_data['orders'].session_id.nunique():,}", help="Distinct sessions with a generated paid order.")
    st.subheader("Quality notes")
    st.info("The sample intentionally contains traceable duplicate, bot, and delayed-event cases. These are monitored anomalies, not referential-integrity failures; source rows are preserved and all validation results are computed from the current sample.")
    if validation["errors"]:
        st.error("Failed checks: " + ", ".join(validation["errors"]))

st.divider()
filtered_event_json = json.dumps({"dataset": "JourneyIQ DEMO DATA", "filters": {"channel": channel_filter, "device": device_filter, "product": product_filter, "days": days_filter}, "generated_sessions": len(data["sessions"]), "filtered_sessions": len(sessions), "generated_events": len(data["events"]), "filtered_events": len(filtered_data["events"]), "events": json.loads(filtered_data["events"].to_json(orient="records", date_format="iso"))}, indent=2)
left_export, right_export = st.columns(2)
left_export.download_button("Export filtered events CSV", filtered_data["events"].to_csv(index=False).encode("utf-8"), file_name="journeyiq_demo_filtered_events.csv", mime="text/csv")
right_export.download_button("Export filtered events JSON", filtered_event_json.encode("utf-8"), file_name="journeyiq_demo_filtered_events.json", mime="application/json")
st.caption("JourneyIQ · Customer Journey Analytics · DEMO DATA · Deterministic sample seed 20261022")
