from pathlib import Path
import sys
import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
from yottajourney.analytics import analyze, detect_anomalies, evaluate_detection

st.set_page_config(page_title="YottaJourney · Analytics", page_icon="↗", layout="wide")
st.markdown("<style>.block-container{padding-top:2rem}.stMetric{background:#fff;border:1px solid #e4e9ed;padding:16px;border-radius:16px}.stApp{background:#f6f8f8}</style>",unsafe_allow_html=True)
st.title("YottaJourney")
st.caption("Customer journey intelligence · YottaFlex.ai")
root=Path(__file__).parent/"data"
if not (root/"sessions.csv").exists():
    st.info("No dataset found yet. Generate the starter dataset to populate the analytics workspace.")
    if st.button("Generate starter dataset",type="primary"):
        from yottajourney.pipeline import generate, Config
        with st.spinner("Generating deterministic customer journeys…"): generate(Config(),root)
        st.rerun()
    st.stop()
names=["customers","sessions","journey_events","pages","products","carts","cart_items","orders","support_tickets","experiments","experiment_assignments","journey_outcomes"]
tables={name:pd.read_csv(root/f"{name}.csv") for name in names}
for name in ("sessions", "journey_events", "orders", "carts", "support_tickets"):
    for col in tables[name].columns:
        if col.endswith("_at") or col in ("event_timestamp","ingestion_timestamp"): tables[name][col]=pd.to_datetime(tables[name][col],utc=True,errors="coerce")
st.sidebar.title("YottaJourney")
page=st.sidebar.radio("Workspace",["Executive Overview","Customer Journey Funnel","Friction Analysis","Channel Analysis","Anomaly Monitoring","Data Quality"])
channel=st.sidebar.selectbox("Channel",["All","website","mobile_app"])
device=st.sidebar.selectbox("Device",["All","desktop","mobile","tablet"])
result=analyze(tables,channel,device)

def kpis():
    cols=st.columns(5)
    values=[("Sessions",f"{result['sessions']:,}"),("Customers",f"{result['unique_customers']:,}"),("Purchases",f"{result['purchases']:,}"),("Conversion",f"{result['conversion_rate']:.1%}"),("Support rate",f"{result['support_contact_rate']:.1%}")]
    for col,(label,value) in zip(cols,values): col.metric(label,value)

if page=="Executive Overview":
    st.subheader("Executive Overview"); kpis(); left,right=st.columns([1.6,1])
    with left:
        st.markdown("#### Journey conversion")
        f=pd.DataFrame(result["funnel"]); st.plotly_chart(px.funnel(f,x="sessions",y="stage",color_discrete_sequence=["#087F8C"]),use_container_width=True)
    with right:
        st.markdown("#### Journey health")
        st.metric("Cart abandonment",f"{result['abandonment_rate']:.1%}"); st.metric("Median ingestion delay",f"{result['median_latency_seconds']:.0f}s"); st.metric("Data quality", "Review" if (root/"ground_truth.csv").exists() else "Passed", "Injected exceptions are traceable")
    st.caption("Conversion denominator: filtered sessions. Purchase is idempotently counted once per session. Support rate is filtered sessions with ≥1 associated support ticket.")
elif page=="Customer Journey Funnel":
    st.subheader("Customer Journey Funnel"); kpis(); f=pd.DataFrame(result["funnel"])
    st.plotly_chart(px.funnel(f,x="sessions",y="stage",color_discrete_sequence=["#087F8C"]),use_container_width=True)
    st.dataframe(f.assign(conversion_rate=f.conversion_rate.map(lambda x:f"{x:.1%}"),dropoff_rate=f.dropoff_rate.map(lambda x:f"{x:.1%}")),hide_index=True,use_container_width=True)
    st.caption("Each stage count is distinct eligible sessions reaching the event. Stage conversion denominator is the immediately preceding stage; first-stage conversion is 100%.")
elif page=="Friction Analysis":
    st.subheader("Friction Analysis"); left,right=st.columns(2)
    with left: st.metric("Payment failures",result["checkout_failures"]); st.metric("Checkout abandonment",f"{result['abandonment_rate']:.1%}")
    with right: st.metric("Median event latency",f"{result['median_latency_seconds']:.0f}s"); st.metric("High-latency events",int((pd.to_datetime(tables['journey_events'].ingestion_timestamp,utc=True)-pd.to_datetime(tables['journey_events'].event_timestamp,utc=True)).dt.total_seconds().gt(600).sum()))
    st.markdown("#### Pages with highest observed ingestion latency")
    if len(result["friction"]): st.dataframe(result["friction"].head(10),hide_index=True,use_container_width=True)
    else: st.info("No page activity in this filter selection.")
elif page=="Channel Analysis":
    st.subheader("Channel Analysis"); kpis(); channel_counts=pd.DataFrame([{"Channel":k,"Sessions":v} for k,v in result["channel_sessions"].items()])
    if len(channel_counts): st.plotly_chart(px.bar(channel_counts,x="Channel",y="Sessions",color="Channel",color_discrete_sequence=["#087F8C","#4f46a5"]),use_container_width=True)
    a,b=st.columns(2); a.metric("Anonymous sessions",result["anonymous_sessions"]); b.metric("Consent-linked sessions",result["identified_sessions"])
    st.info("Cross-channel journeys are attributed by source session; customer identity is linked only where consent permits.")
elif page=="Anomaly Monitoring":
    st.subheader("Anomaly Monitoring"); pred=detect_anomalies(tables); truth=pd.read_csv(root/"ground_truth.csv")
    scores=evaluate_detection(pred,truth); cols=st.columns(5)
    for col,key in zip(cols,["true_positives","false_positives","false_negatives","precision","recall"]): col.metric(key.replace("_"," ").title(),f"{scores[key]:.1%}" if key in ("precision","recall") else scores[key])
    st.metric("F1 score",f"{scores['f1']:.1%}"); st.dataframe(pred,hide_index=True,use_container_width=True)
    st.caption("Detection uses event arrival order, consent/session state, repeated purchase events, and source event bot signals. Ground truth is loaded only for evaluation.")
elif page=="Data Quality":
    st.subheader("Data Quality & Reproducibility"); report_path=root/"validation_report.json"
    if report_path.exists():
        import json
        report=json.loads(report_path.read_text()); st.success(f"Validation status: {report['status']}"); st.json(report["checks"]); st.dataframe(pd.DataFrame([{"Entity":k,"Rows":v} for k,v in report["entity_row_counts"].items()]),hide_index=True,use_container_width=True)
    st.markdown("#### Integrity exceptions")
    if len(pred:=detect_anomalies(tables)): st.dataframe(pred,hide_index=True,use_container_width=True)
    else: st.success("No anomalies detected in the selected source data.")
    st.caption("Ground-truth labels are separated from detector input and are used only for model evaluation.")
