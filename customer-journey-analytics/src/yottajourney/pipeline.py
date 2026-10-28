from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, inspect, text

from .analytics import analyze, detect_anomalies, evaluate_detection

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
    def full(cls, seed: int = SEED):
        return cls(seed=seed, sessions=100000, customers=70000, pages=40, products=300, chunk_size=20000)

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
    pages = pd.DataFrame([{"page_id": f"PAG-{i+1:06d}", "page_name": name, "page_type": kind, "is_active": True, "effective_from": start.isoformat(), "effective_to": (start+pd.Timedelta(days=366)).isoformat()} for i, (name, kind) in enumerate(page_catalog[:config.pages])])
    products = pd.DataFrame([{"product_id": f"PRD-{i+1:06d}", "product_name": f"JourneyIQ product {i+1}", "category": ["Fitness", "Wellness", "Accessories"][i%3], "unit_price": round(float(rng.uniform(19, 450)),2), "is_active": True, "effective_from": start.isoformat(), "effective_to": (start+pd.Timedelta(days=366)).isoformat()} for i in range(config.products)])
    customers = pd.DataFrame([{"customer_id": f"CUS-{i+1:06d}", "created_at": (start-pd.Timedelta(days=int(rng.integers(1,700)))).isoformat(), "consent_status": ["granted", "denied", "unknown"][int(rng.choice(3,p=[.68,.2,.12]))], "lifecycle_state": "active", "country": ["US","GB","CA","AU"][i%4]} for i in range(config.customers)])
    sessions=[]; events=[]; carts=[]; cartitems=[]; orders=[]; tickets=[]; assignments=[]; outcomes=[]; ground=[]
    session_facts=[]
    for si in range(config.sessions):
        n=si+1; sid=deterministic_id("SES", n); cust_index=int(rng.integers(config.customers)); cust=customers.iloc[cust_index]
        consent=cust.consent_status; linked=consent=="granted" and rng.random()>.22
        anon=f"AN-{rng.integers(1,max(2,config.sessions//2)):08d}"
        channel="website" if n==1 else "mobile_app" if n==2 else str(rng.choice(["website","mobile_app"],p=[.7,.3])); device=str(rng.choice(["desktop","mobile","tablet"],p=[.38,.52,.10]))
        bot=bool(rng.random()<.035); bot=False if n==1 else bot; converted=bool((not bot) and (n==1 or rng.random()<.58))
        began=start+pd.Timedelta(minutes=int(rng.integers(0,max(1,365*24*60))))
        sessions.append({"session_id":sid,"customer_id":cust.customer_id if linked else None,"anonymous_id":anon,"started_at":began.isoformat(),"ended_at":None,"channel":channel,"device_type":device,"consent_status":consent,"is_bot":bot,"lifecycle_state":"completed"})
        page=pages.iloc[int(rng.integers(len(pages)))].page_id; product=products.iloc[int(rng.integers(len(products)))]; cartid=f"CRT-{n:06d}"
        has_support=bool((not bot) and (n%12==0 or rng.random()<0.04))
        sequence=["session_started"]+["page_viewed"]*int(rng.integers(12,20))
        if not bot:
            sequence += ["product_viewed"]
            if n==1 or rng.random()<.58: sequence += ["added_to_cart"]
            has_cart="added_to_cart" in sequence
            if has_cart and (n==1 or rng.random()<.64): sequence += ["checkout_started","payment_attempted", "purchase_completed" if converted else "purchase_failed"]
        converted="purchase_completed" in sequence
        if has_support: sequence.append("support_contacted")
        elapsed_seconds=0; last_occurred=began
        support_page=next((row.page_id for row in pages.itertuples() if row.page_type=="support"),pages.iloc[0].page_id)
        for ei, etype in enumerate(sequence,1):
            if ei > 1: elapsed_seconds += int(rng.integers(8,85))
            occurred=began+pd.Timedelta(seconds=elapsed_seconds); last_occurred=occurred
            delay=int(rng.integers(1,6))
            ev={"event_id":f"EVT-{sid}-{ei:06d}","session_id":sid,"customer_id":cust.customer_id if linked else None,"anonymous_id":anon,"event_type":etype,"event_timestamp":occurred.isoformat(),"ingestion_timestamp":(occurred+pd.Timedelta(seconds=delay)).isoformat(),"channel":channel,"page_id":support_page if etype=="support_contacted" else page if etype in ("page_viewed","product_viewed","checkout_started","payment_attempted") else None,"product_id":product.product_id if etype in ("product_viewed","added_to_cart","purchase_completed") else None,"event_properties":_json({"device_type":device,"bot_signal":bot,"schema_version":"1.0","attempt":1 if etype.startswith("purchase") else None}),"event_version":"1.0"}
            events.append(ev)
        sessions[-1]["ended_at"]=last_occurred.isoformat()
        session_facts.append((sid, sequence, product, cartid, converted, linked, cust, began, channel, page))
        if "added_to_cart" in sequence:
            carts.append({"cart_id":cartid,"session_id":sid,"customer_id":cust.customer_id if linked else None,"created_at":began.isoformat(),"state":"converted" if converted else "abandoned"})
            cartitems.append({"cart_item_id":f"CIT-{n:06d}","cart_id":cartid,"product_id":product.product_id,"quantity":1,"unit_price":product.unit_price})
        if converted:
            total=round(float(product.unit_price),2); oid=f"ORD-{n:06d}"
            orders.append({"order_id":oid,"session_id":sid,"customer_id":cust.customer_id if linked else None,"cart_id":cartid if "added_to_cart" in sequence else None,"ordered_at":began.isoformat(),"status":"paid","total_amount":total,"currency":"USD"})
        if has_support:
            tickets.append({"ticket_id":f"SUP-{n:06d}","session_id":sid,"customer_id":cust.customer_id if linked else None,"created_at":last_occurred.isoformat(),"status":"resolved","reason":str(rng.choice(["payment issue","delivery","product question"]))})
        assignments.append({"assignment_id":f"ASN-{n:06d}","experiment_id":f"EXP-2026-{(n%3)+1:06d}","session_id":sid,"variant":"control" if n%2 else "treatment","assigned_at":began.isoformat()})
        funnel_complete="purchase_completed" in sequence
        outcomes.append({"outcome_id":deterministic_id("OUT",n),"session_id":sid,"outcome_type":"converted" if funnel_complete else ("bot" if bot else "checkout_abandoned" if "checkout_started" in sequence else "cart_abandoned" if "added_to_cart" in sequence else "browsed"),"outcome_at":(began+pd.Timedelta(minutes=10)).isoformat(),"rule_version":"1.0"})
    if config.sessions >= 4:
        s1,s2,s3,s4=[session_facts[i][0] for i in range(4)]
        ix=[i for i,e in enumerate(events) if e["session_id"]==s1][:2]
        if len(ix)==2:
            events[ix[0]]["ingestion_timestamp"]=(pd.Timestamp(events[ix[0]]["event_timestamp"])+pd.Timedelta(seconds=1800)).isoformat()
            events[ix[1]]["ingestion_timestamp"]=(pd.Timestamp(events[ix[1]]["event_timestamp"])+pd.Timedelta(seconds=2)).isoformat()
            ground.append({"entity_id":s1,"issue_type":"out_of_order_arrival"})
        ix2=next(i for i,e in enumerate(events) if e["session_id"]==s2)
        sessions[int(s2.split("-")[-1])-1]["consent_status"]="denied"
        sessions[int(s2.split("-")[-1])-1]["customer_id"]=None
        events[ix2]["customer_id"]=customers.iloc[0].customer_id
        ground.append({"entity_id":s2,"issue_type":"identity_stitching"})
        purchase=next((e for e in events if e["event_type"]=="purchase_completed"),None)
        if purchase:
            conversion_session=purchase["session_id"]
            duplicate={**purchase,"event_id":f"EVT-{conversion_session}-999999"}
            duplicate_props=json.loads(duplicate["event_properties"]); duplicate_props["duplicate_source_event_id"]=purchase["event_id"]; duplicate_props["duplicate_source"]=True; duplicate["event_properties"]=_json(duplicate_props)
            events.append(duplicate); ground.append({"entity_id":conversion_session,"issue_type":"duplicate_conversion"})
        sessions[int(s4.split("-")[-1])-1]["is_bot"]=True
        outcomes[int(s4.split("-")[-1])-1]["outcome_type"]="bot"
        for e in events:
            if e["session_id"]==s4:
                props=json.loads(e["event_properties"]); props["bot_signal"]=True; e["event_properties"]=_json(props)
        ground.append({"entity_id":s4,"issue_type":"bot_traffic"})
    experiments=pd.DataFrame([{"experiment_id":f"EXP-2026-{i:06d}","name":name,"status":"completed","start_at":start.isoformat(),"end_at":(start+pd.Timedelta(days=365)).isoformat()} for i,name in enumerate(["Checkout clarity","Product recommendations","Payment copy"],1)])
    tables={"customers":customers,"sessions":pd.DataFrame(sessions),"journey_events":pd.DataFrame(events),"pages":pages,"products":products,"carts":pd.DataFrame(carts,columns=["cart_id","session_id","customer_id","created_at","state"]),"cart_items":pd.DataFrame(cartitems,columns=["cart_item_id","cart_id","product_id","quantity","unit_price"]),"orders":pd.DataFrame(orders,columns=["order_id","session_id","customer_id","cart_id","ordered_at","status","total_amount","currency"]),"support_tickets":pd.DataFrame(tickets,columns=["ticket_id","session_id","customer_id","created_at","status","reason"]),"experiments":experiments,"experiment_assignments":pd.DataFrame(assignments),"journey_outcomes":pd.DataFrame(outcomes)}
    for name,df in tables.items():
        df=df.reindex(sorted(df.columns),axis=1).sort_values(df.columns[0],kind="stable").reset_index(drop=True); tables[name]=df
        df.to_csv(out/f"{name}.csv",index=False,lineterminator="\n",na_rep="")
    for session in sessions:
        if session["is_bot"]: ground.append({"entity_id":session["session_id"],"issue_type":"bot_traffic"})
    ground_df=pd.DataFrame(ground,columns=["entity_id","issue_type"]).drop_duplicates().sort_values(["entity_id","issue_type"],kind="stable").reset_index(drop=True)
    ground_df.to_csv(out/"ground_truth.csv",index=False,lineterminator="\n")
    pred=detect_anomalies(tables); evaluation=evaluate_detection(pred,ground_df); metrics=analyze(tables)
    primary_keys={"customers":"customer_id","sessions":"session_id","journey_events":"event_id","pages":"page_id","products":"product_id","carts":"cart_id","cart_items":"cart_item_id","orders":"order_id","support_tickets":"ticket_id","experiments":"experiment_id","experiment_assignments":"assignment_id","journey_outcomes":"outcome_id"}
    checks={f"{table}_pk_unique":bool(tables[table][key].is_unique) for table,key in primary_keys.items()}
    page_usage=tables["journey_events"].dropna(subset=["page_id"]).merge(tables["pages"][["page_id","effective_from","effective_to"]],on="page_id")
    product_usage=tables["journey_events"].dropna(subset=["product_id"]).merge(tables["products"][["product_id","effective_from","effective_to"]],on="product_id")
    checks.update({
        "session_customer_fk_valid":bool(tables["sessions"].customer_id.dropna().isin(tables["customers"].customer_id).all()),
        "event_session_fk_valid":bool(tables["journey_events"].session_id.isin(tables["sessions"].session_id).all()),
        "event_customer_fk_valid":bool(tables["journey_events"].customer_id.dropna().isin(tables["customers"].customer_id).all()),
        "event_page_fk_valid":bool(tables["journey_events"].page_id.dropna().isin(tables["pages"].page_id).all()),
        "event_product_fk_valid":bool(tables["journey_events"].product_id.dropna().isin(tables["products"].product_id).all()),
        "page_effective_at_event":bool(((pd.to_datetime(page_usage.event_timestamp,utc=True)>=pd.to_datetime(page_usage.effective_from,utc=True))&(page_usage.effective_to.isna()|(pd.to_datetime(page_usage.event_timestamp,utc=True)<=pd.to_datetime(page_usage.effective_to,utc=True)))).all()),
        "product_effective_at_event":bool(((pd.to_datetime(product_usage.event_timestamp,utc=True)>=pd.to_datetime(product_usage.effective_from,utc=True))&(product_usage.effective_to.isna()|(pd.to_datetime(product_usage.event_timestamp,utc=True)<=pd.to_datetime(product_usage.effective_to,utc=True)))).all()),
        "cart_session_fk_valid":bool(tables["carts"].session_id.isin(tables["sessions"].session_id).all()),
        "cart_customer_fk_valid":bool(tables["carts"].customer_id.dropna().isin(tables["customers"].customer_id).all()),
        "cart_item_cart_fk_valid":bool(tables["cart_items"].cart_id.isin(tables["carts"].cart_id).all()),
        "cart_item_product_fk_valid":bool(tables["cart_items"].product_id.isin(tables["products"].product_id).all()),
        "order_session_fk_valid":bool(tables["orders"].session_id.isin(tables["sessions"].session_id).all()),
        "order_customer_fk_valid":bool(tables["orders"].customer_id.dropna().isin(tables["customers"].customer_id).all()),
        "order_cart_fk_valid":bool(tables["orders"].cart_id.dropna().isin(tables["carts"].cart_id).all()),
        "support_session_fk_valid":bool(tables["support_tickets"].session_id.isin(tables["sessions"].session_id).all()),
        "support_customer_fk_valid":bool(tables["support_tickets"].customer_id.dropna().isin(tables["customers"].customer_id).all()),
        "assignment_session_fk_valid":bool(tables["experiment_assignments"].session_id.isin(tables["sessions"].session_id).all()),
        "assignment_experiment_fk_valid":bool(tables["experiment_assignments"].experiment_id.isin(tables["experiments"].experiment_id).all()),
        "outcome_session_fk_valid":bool(tables["journey_outcomes"].session_id.isin(tables["sessions"].session_id).all()),
        "allowed_event_types":bool(tables["journey_events"].event_type.isin(TAXONOMY).all()),
        "allowed_channel_values":bool(tables["sessions"].channel.isin(["website","mobile_app"]).all()),
        "allowed_device_values":bool(tables["sessions"].device_type.isin(["desktop","mobile","tablet"]).all()),
        "allowed_session_lifecycle":bool(tables["sessions"].lifecycle_state.isin(["active","completed","expired"]).all()),
        "allowed_cart_lifecycle":bool(tables["carts"].state.isin(["open","abandoned","converted","expired"]).all()),
        "allowed_order_lifecycle":bool(tables["orders"].status.isin(["pending","paid","failed","refunded"]).all()),
        "allowed_support_lifecycle":bool(tables["support_tickets"].status.isin(["open","pending","resolved","closed"]).all()),
        "allowed_outcome_types":bool(tables["journey_outcomes"].outcome_type.isin(["converted","checkout_abandoned","cart_abandoned","browsed","bot"]).all()),
        "session_timestamp_order":bool((pd.to_datetime(tables["sessions"].ended_at,utc=True)>=pd.to_datetime(tables["sessions"].started_at,utc=True)).all()),
        "event_timestamp_latency_nonnegative":bool((pd.to_datetime(tables["journey_events"].ingestion_timestamp,utc=True)>=pd.to_datetime(tables["journey_events"].event_timestamp,utc=True)).all()),
        "assignment_effective_dates":bool(tables["experiment_assignments"].merge(tables["experiments"],on="experiment_id").assign(valid=lambda frame:(pd.to_datetime(frame.assigned_at,utc=True)>=pd.to_datetime(frame.start_at,utc=True))&(pd.to_datetime(frame.assigned_at,utc=True)<=pd.to_datetime(frame.end_at,utc=True))).valid.all()),
        "cart_order_totals_reconcile":bool(tables["orders"].merge(tables["cart_items"].assign(line_total=lambda frame:frame.quantity*frame.unit_price).groupby("cart_id",as_index=False).line_total.sum(),on="cart_id",how="left").dropna(subset=["cart_id"]).eval("total_amount == line_total").all()),
    })
    errors=[name for name,passed in checks.items() if not passed]
    validation={"status":"passed" if not errors else "failed","entity_row_counts":{name:len(frame) for name,frame in tables.items()},"errors":errors,"warnings":["Injected anomalies are retained in source events and evaluated separately against ground_truth.csv."],"reconciliation":{"generated_sessions":len(tables["sessions"]),"generated_events":len(tables["journey_events"]),"filtered_sessions":metrics["eligible_sessions"],"paid_order_ids":metrics["purchase_order_count"],"converting_sessions":metrics["purchases"],"conversion_numerator":metrics["purchases"],"conversion_denominator":metrics["eligible_sessions"],"eligible_mature_carts":metrics["eligible_cart_sessions"],"abandoned_carts":metrics["abandoned_cart_sessions"]},"funnel_counts":{row["stage"]:row["sessions"] for row in metrics["funnel"]},"anomaly_evaluation":evaluation,"checks":checks,"check_categories":{"structural_integrity":list(checks),"anomaly_detection_metrics":["true_positives","false_positives","false_negatives","precision","recall","f1"]}}
    (out/"validation_report.json").write_text(json.dumps(validation,indent=2,sort_keys=True)+"\n")
    checksums={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(out.glob("*.csv"))}
    manifest={"seed":config.seed,"config":asdict(config),"datasets_fingerprinted":sorted(checksums),"comparison_scope":"Full generated profile for this seed/configuration; no filtered dashboard extract is included.","sha256":checksums,"entity_row_counts":validation["entity_row_counts"],"derived_metrics":{"funnel_counts":validation["funnel_counts"],"conversion_rate":metrics["conversion_rate"],"abandonment_rate":metrics["abandonment_rate"]},"anomaly_counts":ground_df.issue_type.value_counts().sort_index().to_dict(),"anomaly_evaluation":evaluation}
    (out/"reproducibility.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    if database_url:
        engine=create_engine(database_url)
        with engine.begin() as conn:
            missing=set(tables)-set(inspect(conn).get_table_names())
            if missing: raise ValueError(f"Apply schema.sql before loading generated rows; missing tables: {sorted(missing)}")
            for name in ("customers","pages","products","experiments","sessions","journey_events","carts","cart_items","orders","support_tickets","experiment_assignments","journey_outcomes"):
                tables[name].to_sql(name,conn,if_exists="append",index=False,method="multi",chunksize=min(config.chunk_size,50))
    return {"tables":tables,"validation":validation,"ground_truth":ground_df,"detections":pred}


def verify_reproducibility(config: Config = Config(), output: str | Path = "data") -> dict:
    """Generate the same full profile twice and compare complete canonical CSV exports."""
    target = Path(output)
    first = generate(config, target)
    first_validation = first["validation"]
    del first
    with TemporaryDirectory(prefix="journeyiq-repro-") as temporary:
        second = generate(config, temporary)
        second_validation = second["validation"]
        del second
        first_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(target.glob("*.csv"))}
        second_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(Path(temporary).glob("*.csv"))}
        first_metrics = first_validation["reconciliation"] | {"funnel_counts": first_validation["funnel_counts"]}
        second_metrics = second_validation["reconciliation"] | {"funnel_counts": second_validation["funnel_counts"]}
        first_report = json.loads((target / "reproducibility.json").read_text())
        second_report = json.loads((Path(temporary) / "reproducibility.json").read_text())
        comparison = {
            "run_a": str(target),
            "run_b": "temporary second generation",
            "datasets_compared": sorted(first_hashes),
            "full_profile_only": True,
            "row_counts_match": first_validation["entity_row_counts"] == second_validation["entity_row_counts"],
            "sha256_match": first_hashes == second_hashes,
            "derived_metrics_match": first_metrics == second_metrics,
            "anomaly_counts_match": first_report["anomaly_counts"] == second_report["anomaly_counts"],
        }
        comparison["identical"] = all(value for key, value in comparison.items() if key.endswith("_match"))
    manifest = json.loads((target / "reproducibility.json").read_text())
    manifest["comparison"] = comparison
    (target / "reproducibility.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return comparison


def main():
    parser=argparse.ArgumentParser(description="Generate JourneyIQ synthetic customer journey data and analytics exports")
    parser.add_argument("--full",action="store_true"); parser.add_argument("--output",default="data")
    parser.add_argument("--database-url",default=os.getenv("DATABASE_URL")); parser.add_argument("--seed",type=int,default=SEED)
    parser.add_argument("--sessions",type=int); parser.add_argument("--customers",type=int); parser.add_argument("--chunk-size",type=int); parser.add_argument("--start-date")
    parser.add_argument("--verify-reproducibility",action="store_true",help="Generate a second same-profile dataset and compare row counts, checksums, metrics, and anomaly counts")
    args=parser.parse_args(); cfg=Config.full(args.seed) if args.full else Config(seed=args.seed)
    overrides={key:value for key,value in {"sessions":args.sessions,"customers":args.customers,"chunk_size":args.chunk_size,"start_date":args.start_date}.items() if value is not None}
    if overrides: cfg=replace(cfg,**overrides)
    if args.verify_reproducibility and args.database_url: parser.error("Reproducibility verification writes two independent CSV runs and cannot append to a database")
    result=verify_reproducibility(cfg,args.output) if args.verify_reproducibility else generate(cfg,args.output,args.database_url)["validation"]
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
