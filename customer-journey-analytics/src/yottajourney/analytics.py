from __future__ import annotations
import json
import pandas as pd

FUNNEL = [("Session Started", "session_started"), ("Product Viewed", "product_viewed"), ("Added to Cart", "added_to_cart"), ("Checkout Started", "checkout_started"), ("Purchase Completed", "purchase_completed")]

def analyze(tables: dict[str, pd.DataFrame], channel: str = "All", device: str = "All") -> dict:
    sessions=tables["sessions"].copy()
    if channel!="All": sessions=sessions[sessions.channel.eq(channel)]
    if device!="All": sessions=sessions[sessions.device_type.eq(device)]
    eligible=set(sessions.session_id)
    ev=tables["journey_events"][tables["journey_events"].session_id.isin(eligible)].copy()
    # Idempotent conversion: each session contributes at most one purchase.
    counts=[int(ev.loc[ev.event_type.eq(event),"session_id"].nunique()) for _,event in FUNNEL]
    rows=[]
    for i,((stage,_),count) in enumerate(zip(FUNNEL,counts)):
        prior=counts[i-1] if i else counts[0]
        rows.append({"stage":stage,"sessions":count,"conversion_rate":count/prior if prior else 0,"dropoff_rate":(prior-count)/prior if prior else 0})
    orders=tables["orders"][tables["orders"].session_id.isin(eligible)]
    carts=tables["carts"][tables["carts"].session_id.isin(eligible)]
    support=tables["support_tickets"][tables["support_tickets"].session_id.isin(eligible)]
    event_times=pd.to_datetime(ev.event_timestamp,utc=True); ingest=pd.to_datetime(ev.ingestion_timestamp,utc=True)
    ev["latency_seconds"]=(ingest-event_times).dt.total_seconds()
    page_events=ev[ev.page_id.notna()]
    friction=page_events.groupby("page_id").agg(events=("event_id","count"),sessions=("session_id","nunique"),median_latency_seconds=("latency_seconds","median")).reset_index()
    friction=friction.merge(tables["pages"][["page_id","page_name"]],on="page_id",how="left").sort_values("median_latency_seconds",ascending=False)
    return {"funnel":rows,"sessions":len(eligible),"unique_customers":sessions.customer_id.nunique(),"purchases":orders.session_id.nunique(),"conversion_rate":orders.session_id.nunique()/len(eligible) if eligible else 0,"abandonment_rate":(len(carts)-orders.session_id.nunique())/len(carts) if len(carts) else 0,"support_contact_rate":support.session_id.nunique()/len(eligible) if eligible else 0,"friction":friction,"checkout_failures":int(ev.event_type.eq("purchase_failed").sum()),"median_latency_seconds":float(ev.latency_seconds.median()) if len(ev) else 0,"anonymous_sessions":int(sessions.customer_id.isna().sum()),"identified_sessions":int(sessions.customer_id.notna().sum()),"channel_sessions":sessions.groupby("channel").session_id.nunique().to_dict()}

def detect_anomalies(tables: dict[str,pd.DataFrame]) -> pd.DataFrame:
    ev=tables["journey_events"].copy(); sess=tables["sessions"].set_index("session_id")
    ev["event_timestamp"]=pd.to_datetime(ev.event_timestamp,utc=True); ev["ingestion_timestamp"]=pd.to_datetime(ev.ingestion_timestamp,utc=True)
    found=[]
    for sid,g in ev.groupby("session_id"):
        if list(g.sort_values("ingestion_timestamp").event_id)!=list(g.sort_values("event_timestamp").event_id): found.append((sid,"out_of_order_arrival"))
        if g.customer_id.notna().any() and sess.loc[sid,"consent_status"]!="granted": found.append((sid,"identity_stitching"))
        if g.event_type.eq("purchase_completed").sum()>1: found.append((sid,"duplicate_conversion"))
        if any(json.loads(p).get("bot_signal",False) for p in g.event_properties): found.append((sid,"bot_traffic"))
    return pd.DataFrame(found,columns=["entity_id","issue_type"])

def evaluate_detection(predictions: pd.DataFrame, ground_truth: pd.DataFrame) -> dict:
    predicted=set(map(tuple,predictions[["entity_id","issue_type"]].to_numpy().tolist())); actual=set(map(tuple,ground_truth[["entity_id","issue_type"]].to_numpy().tolist()))
    tp=len(predicted&actual); fp=len(predicted-actual); fn=len(actual-predicted); p=tp/(tp+fp) if tp+fp else 0; r=tp/(tp+fn) if tp+fn else 0
    return {"true_positives":tp,"false_positives":fp,"false_negatives":fn,"precision":p,"recall":r,"f1":2*p*r/(p+r) if p+r else 0}
