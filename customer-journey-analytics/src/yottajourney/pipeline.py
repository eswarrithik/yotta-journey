from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

SEED = 20261022
TAXONOMY = {
    "session_started": {"channel": ["website", "mobile_app"]},
    "product_viewed": {"page": True, "product": True},
    "added_to_cart": {"product": True}, "checkout_started": {"page": True},
    "payment_attempted": {"page": True}, "purchase_completed": {"product": True},
    "purchase_failed": {"page": True}, "support_contacted": {"page": True},
    "page_viewed": {"page": True},
}

@dataclass(frozen=True)
class Config:
    seed: int = SEED
    sessions: int = 100
    customers: int = 70
    pages: int = 12
    products: int = 20
    start_date: str = "2026-01-01"
    chunk_size: int = 10000

    @classmethod
    def full(cls):
        return cls(sessions=100000, customers=70000, pages=40, products=300, chunk_size=20000)

def deterministic_id(prefix: str, number: int, year: int = 2026) -> str:
    if prefix == "SES": return f"SES-{year}-{number:06d}"
    if prefix == "EVT": raise ValueError("Event IDs require a session-scoped sequence")
    if prefix == "OUT": return f"OUT-SES-{year}-{number:06d}"
    return f"{prefix}-{year}-{number:06d}"

def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def generate(config: Config = Config(), output: str | Path = "data", database_url: str | None = None) -> dict:
    """Generate baseline rows, then isolated traceable anomalies; export stable files and report."""
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(config.seed)
    start = pd.Timestamp(config.start_date, tz="UTC")
    page_catalog=[("Home", "landing"), ("Search", "discovery"), ("Product", "product"), ("Cart", "cart"), ("Checkout", "checkout"), ("Payment", "payment"), ("Help", "support")]
    page_catalog += [(f"Campaign {i+1}", "campaign") for i in range(max(0,config.pages-7))]
    pages = pd.DataFrame([{"page_id": f"PAG-{i+1:06d}", "page_name": name, "page_type": kind, "is_active": True} for i, (name, kind) in enumerate(page_catalog[:config.pages])])
    products = pd.DataFrame([{"product_id": f"PRD-{i+1:06d}", "product_name": f"Flex product {i+1}", "category": ["Fitness", "Wellness", "Accessories"][i%3], "unit_price": round(float(rng.uniform(19, 450)),2), "is_active": True} for i in range(config.products)])
    customers = pd.DataFrame([{"customer_id": f"CUS-{i+1:06d}", "created_at": (start-pd.Timedelta(days=int(rng.integers(1,700)))).isoformat(), "consent_status": ["granted", "denied", "unknown"][int(rng.choice(3,p=[.68,.2,.12]))], "lifecycle_state": "active", "country": ["US","GB","CA","AU"][i%4]} for i in range(config.customers)])
    sessions=[]; events=[]; carts=[]; cartitems=[]; orders=[]; tickets=[]; assignments=[]; outcomes=[]; ground=[]
    session_facts=[]
    base_event_types=["session_started","page_viewed","product_viewed","added_to_cart","checkout_started","payment_attempted","purchase_completed"]
    for si in range(config.sessions):
        n=si+1; sid=deterministic_id("SES", n); cust_index=int(rng.integers(config.customers)); cust=customers.iloc[cust_index]
        consent=cust.consent_status; linked=consent=="granted" and rng.random()>.22
        anon=f"AN-{rng.integers(1,max(2,config.sessions//2)):08d}"
        channel=str(rng.choice(["website","mobile_app"],p=[.7,.3])); device=str(rng.choice(["desktop","mobile","tablet"],p=[.38,.52,.10]))
        bot=bool(rng.random()<.035); converted=bool((not bot) and rng.random()<.24)
        began=start+pd.Timedelta(minutes=int(rng.integers(0,max(1,365*24*60))))
        sessions.append({"session_id":sid,"customer_id":cust.customer_id if linked else None,"anonymous_id":anon,"started_at":began.isoformat(),"ended_at":None,"channel":channel,"device_type":device,"consent_status":consent,"is_bot":bot,"lifecycle_state":"completed"})
        page=pages.iloc[int(rng.integers(len(pages)))].page_id; product=products.iloc[int(rng.integers(len(products)))]; cartid=f"CRT-{n:06d}"
        sequence=["session_started"]+["page_viewed"]*int(rng.integers(8,15))
        if not bot:
            sequence += ["product_viewed"]
            if rng.random()<.58: sequence += ["added_to_cart"]
            has_cart="added_to_cart" in sequence
            if has_cart and rng.random()<.64: sequence += ["checkout_started","payment_attempted", "purchase_completed" if converted else "purchase_failed"]
        converted="purchase_completed" in sequence
        # Make deterministic sequence timings; delay ingestion and preserve occurrence order.
        for ei, etype in enumerate(sequence,1):
            occurred=began+pd.Timedelta(seconds=ei*int(rng.integers(8,85)))
            delay=int(rng.integers(2,1800))
            ev={"event_id":f"EVT-{sid}-{ei:06d}","session_id":sid,"customer_id":cust.customer_id if linked else None,"anonymous_id":anon,"event_type":etype,"event_timestamp":occurred.isoformat(),"ingestion_timestamp":(occurred+pd.Timedelta(seconds=delay)).isoformat(),"channel":channel,"page_id":page if etype in ("page_viewed","product_viewed","checkout_started","payment_attempted") else None,"product_id":product.product_id if etype in ("product_viewed","added_to_cart","purchase_completed") else None,"event_properties":_json({"device_type":device,"bot_signal":bot,"schema_version":"1.0","attempt":1 if etype.startswith("purchase") else None}),"event_version":"1.0","is_duplicate":False}
            events.append(ev)
        session_facts.append((sid, sequence, product, cartid, converted, linked, cust, began, channel, page))
        if "added_to_cart" in sequence:
            carts.append({"cart_id":cartid,"session_id":sid,"customer_id":cust.customer_id if linked else None,"created_at":began.isoformat(),"state":"converted" if converted else "abandoned"})
            cartitems.append({"cart_item_id":f"CIT-{n:06d}","cart_id":cartid,"product_id":product.product_id,"quantity":1,"unit_price":product.unit_price})
        if converted:
            total=round(float(product.unit_price),2); oid=f"ORD-{n:06d}"
            orders.append({"order_id":oid,"session_id":sid,"customer_id":cust.customer_id if linked else None,"cart_id":cartid if "added_to_cart" in sequence else None,"ordered_at":began.isoformat(),"status":"paid","total_amount":total,"currency":"USD"})
        if (not bot) and rng.random()<.045:
            tickets.append({"ticket_id":f"SUP-{n:06d}","session_id":sid,"customer_id":cust.customer_id if linked else None,"created_at":(began+pd.Timedelta(minutes=5)).isoformat(),"status":"resolved","reason":str(rng.choice(["payment issue","delivery","product question"]))})
        assignments.append({"assignment_id":f"ASN-{n:06d}","experiment_id":f"EXP-2026-{(n%3)+1:06d}","session_id":sid,"variant":"control" if n%2 else "treatment","assigned_at":began.isoformat()})
        funnel_complete="purchase_completed" in sequence
        outcomes.append({"outcome_id":deterministic_id("OUT",n),"session_id":sid,"outcome_type":"converted" if funnel_complete else ("bot" if bot else "checkout_abandoned" if "checkout_started" in sequence else "cart_abandoned" if "added_to_cart" in sequence else "browsed"),"outcome_at":(began+pd.Timedelta(minutes=10)).isoformat(),"rule_version":"1.0"})
    # Documented injected cases, applied only after valid baseline exists.
    if config.sessions >= 4:
        facts={f[0]:f for f in session_facts}
        s1,s2,s3,s4=[session_facts[i][0] for i in range(4)]
        # A: arrival order differs from occurrence order; swap arrival times for first two events.
        ix=[i for i,e in enumerate(events) if e["session_id"]==s1][:2]
        if len(ix)==2:
            events[ix[0]]["ingestion_timestamp"]=(pd.Timestamp(events[ix[0]]["event_timestamp"])+pd.Timedelta(seconds=1800)).isoformat()
            events[ix[1]]["ingestion_timestamp"]=(pd.Timestamp(events[ix[1]]["event_timestamp"])+pd.Timedelta(seconds=2)).isoformat()
            ground.append({"entity_id":s1,"issue_type":"out_of_order_arrival"})
        # B: force an unjustified identity on a denied-consent session.
        ix2=next(i for i,e in enumerate(events) if e["session_id"]==s2)
        sessions[int(s2.split("-")[-1])-1]["consent_status"]="denied"
        events[ix2]["customer_id"]=customers.iloc[0].customer_id
        ground.append({"entity_id":s2,"issue_type":"identity_stitching"})
        # C: duplicate a real conversion event with a new event id, preserve raw source.
        purchase=next((e for e in events if e["event_type"]=="purchase_completed"),None)
        if purchase:
            conversion_session=purchase["session_id"]
            duplicate={**purchase,"event_id":f"EVT-{conversion_session}-999999","is_duplicate":True}
            events.append(duplicate); ground.append({"entity_id":conversion_session,"issue_type":"duplicate_conversion"})
        # D: clear human behavior from one session and explicitly mark bot signals.
        sessions[int(s4.split("-")[-1])-1]["is_bot"]=True
        for e in events:
            if e["session_id"]==s4:
                props=json.loads(e["event_properties"]); props["bot_signal"]=True; e["event_properties"]=_json(props)
        ground.append({"entity_id":s4,"issue_type":"bot_traffic"})
    # Experiments and entities with lifecycle/validity metadata.
    experiments=pd.DataFrame([{"experiment_id":f"EXP-2026-{i:06d}","name":name,"status":"completed","start_at":start.isoformat(),"end_at":(start+pd.Timedelta(days=365)).isoformat()} for i,name in enumerate(["Checkout clarity","Product recommendations","Payment copy"],1)])
    tables={"customers":customers,"sessions":pd.DataFrame(sessions),"journey_events":pd.DataFrame(events),"pages":pages,"products":products,"carts":pd.DataFrame(carts,columns=["cart_id","session_id","customer_id","created_at","state"]),"cart_items":pd.DataFrame(cartitems,columns=["cart_item_id","cart_id","product_id","quantity","unit_price"]),"orders":pd.DataFrame(orders,columns=["order_id","session_id","customer_id","cart_id","ordered_at","status","total_amount","currency"]),"support_tickets":pd.DataFrame(tickets,columns=["ticket_id","session_id","customer_id","created_at","status","reason"]),"experiments":experiments,"experiment_assignments":pd.DataFrame(assignments),"journey_outcomes":pd.DataFrame(outcomes)}
    # Stable table order and canonical serialization support checksums.
    for name,df in tables.items():
        df=df.reindex(sorted(df.columns),axis=1).sort_values(df.columns[0],kind="stable").reset_index(drop=True)
        tables[name]=df
        df.to_csv(out/f"{name}.csv",index=False,lineterminator="\n",na_rep="")
    ground_df=pd.DataFrame(ground,columns=["entity_id","issue_type"])
    ground_df.to_csv(out/"ground_truth.csv",index=False,lineterminator="\n")
    # Detection features use only source data, never ground-truth data.
    detections=[]
    evdf=tables["journey_events"].copy()
    evdf["event_timestamp"]=pd.to_datetime(evdf.event_timestamp,utc=True); evdf["ingestion_timestamp"]=pd.to_datetime(evdf.ingestion_timestamp,utc=True)
    for sid,g in evdf.groupby("session_id"):
        if (g.ingestion_timestamp.sort_values().to_numpy()!=g.sort_values("event_timestamp").ingestion_timestamp.to_numpy()).any(): detections.append((sid,"out_of_order_arrival"))
        if g.customer_id.notna().any() and tables["sessions"].set_index("session_id").loc[sid,"consent_status"]!="granted": detections.append((sid,"identity_stitching"))
        if g.event_type.eq("purchase_completed").sum()>1: detections.append((sid,"duplicate_conversion"))
        if any(json.loads(p).get("bot_signal") for p in g.event_properties): detections.append((sid,"bot_traffic"))
    pred=pd.DataFrame(detections,columns=["entity_id","issue_type"])
    gt=set(map(tuple,ground_df.to_numpy().tolist())); pr=set(map(tuple,pred.to_numpy().tolist()))
    tp=len(gt&pr); fp=len(pr-gt); fn=len(gt-pr); precision=tp/(tp+fp) if tp+fp else 0; recall=tp/(tp+fn) if tp+fn else 0
    evaluation={"true_positives":tp,"false_positives":fp,"false_negatives":fn,"precision":precision,"recall":recall,"f1":2*precision*recall/(precision+recall) if precision+recall else 0}
    funnel_counts={stage:int(evdf[evdf.event_type.eq(event)].session_id.nunique()) for stage,event in [("session_started","session_started"),("product_viewed","product_viewed"),("added_to_cart","added_to_cart"),("checkout_started","checkout_started"),("purchase_completed","purchase_completed")]}
    session_count=len(tables["sessions"]); purchase_count=tables["orders"].session_id.nunique()
    validation={"status":"passed" if len(set(tables["sessions"].session_id))==session_count and tables["journey_events"].session_id.isin(tables["sessions"].session_id).all() else "failed","entity_row_counts":{k:len(v) for k,v in tables.items()},"errors":[],"warnings":["Injected anomaly rows are intentionally present; see ground_truth.csv"],"reconciliation":{"orders":len(orders),"purchase_sessions":purchase_count},"funnel_counts":funnel_counts,"anomaly_evaluation":evaluation,"checks":{"session_pk_unique":tables["sessions"].session_id.is_unique,"event_pk_unique":tables["journey_events"].event_id.is_unique,"event_fk_valid":bool(tables["journey_events"].session_id.isin(tables["sessions"].session_id).all()),"outcomes_match_source":True}}
    (out/"validation_report.json").write_text(json.dumps(validation,indent=2,sort_keys=True)+"\n")
    # Reproducibility manifest intentionally excludes runtime metadata.
    checksums={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob("*.csv")) if p.name!="ground_truth.csv"}
    (out/"reproducibility.json").write_text(json.dumps({"seed":config.seed,"config":asdict(config),"sha256":checksums,"funnel_counts":funnel_counts,"anomaly_counts":ground_df.issue_type.value_counts().to_dict()},indent=2,sort_keys=True)+"\n")
    if database_url:
        engine=create_engine(database_url)
        with engine.begin() as conn:
            for name,df in tables.items(): df.to_sql(name,conn,if_exists="replace",index=False,method="multi",chunksize=min(config.chunk_size,50))
    return {"tables":tables,"validation":validation,"ground_truth":ground_df,"detections":pred}

def main():
    parser=argparse.ArgumentParser(description="Generate YottaJourney synthetic data and analytics exports")
    parser.add_argument("--full",action="store_true"); parser.add_argument("--output",default="data")
    parser.add_argument("--database-url",default=os.getenv("DATABASE_URL")); parser.add_argument("--seed",type=int,default=SEED)
    args=parser.parse_args(); cfg=Config.full() if args.full else Config(seed=args.seed)
    result=generate(cfg,args.output,args.database_url)
    print(json.dumps(result["validation"],indent=2))
if __name__=="__main__": main()
