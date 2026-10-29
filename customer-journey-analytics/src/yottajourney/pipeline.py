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
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects.postgresql import JSONB

from .analytics import analyze, detect_anomalies, evaluate_detection
from .streaming import analyze_csv, detect_anomalies_csv, validate_events_csv

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

def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()

def generate(config: Config = Config(), output: str | Path = "data", database_url: str | None = None, retain_tables: bool = True) -> dict:
    """Generate baseline rows, then isolated traceable anomalies; export stable files and report."""
    if min(config.sessions, config.customers, config.pages, config.products, config.chunk_size) < 1:
        raise ValueError("sessions, customers, pages, products, and chunk_size must be positive")
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(config.seed)
    start = pd.Timestamp(config.start_date, tz="UTC")
    page_catalog=[("Home", "landing"), ("Search", "discovery"), ("Product", "product"), ("Cart", "cart"), ("Checkout", "checkout"), ("Payment", "payment"), ("Help", "support")]
    page_catalog += [(f"Campaign {i+1}", "campaign") for i in range(max(0,config.pages-7))]
    pages = pd.DataFrame([{"page_id": f"PAG-{i+1:06d}", "page_name": name, "page_type": kind, "is_active": True, "effective_from": start.isoformat(), "effective_to": (start+pd.Timedelta(days=366)).isoformat()} for i, (name, kind) in enumerate(page_catalog[:config.pages])])
    products = pd.DataFrame([{"product_id": f"PRD-{i+1:06d}", "product_name": f"JourneyIQ product {i+1}", "category": ["Fitness", "Wellness", "Accessories"][i%3], "unit_price": round(float(rng.uniform(19, 450)),2), "is_active": True, "effective_from": start.isoformat(), "effective_to": (start+pd.Timedelta(days=366)).isoformat()} for i in range(config.products)])
    customers = pd.DataFrame([{"customer_id": f"CUS-{i+1:06d}", "created_at": (start-pd.Timedelta(days=int(rng.integers(1,700)))).isoformat(), "consent_status": ["granted", "denied", "unknown"][int(rng.choice(3,p=[.68,.2,.12]))], "lifecycle_state": "active", "country": ["US","GB","CA","AU"][i%4]} for i in range(config.customers)])
    experiments=pd.DataFrame([{"experiment_id":f"EXP-2026-{i:06d}","name":name,"status":"completed","start_at":start.isoformat(),"end_at":(start+pd.Timedelta(days=365)).isoformat()} for i,name in enumerate(["Checkout clarity","Product recommendations","Payment copy"],1)])
    sessions=[]; carts=[]; cartitems=[]; orders=[]; tickets=[]; assignments=[]; outcomes=[]; ground=[]
    event_path=out/"journey_events.csv"
    event_path.unlink(missing_ok=True)
    event_buffer=[]
    for si in range(config.sessions):
        n=si+1; sid=deterministic_id("SES", n); cust_index=int(rng.integers(config.customers)); cust=customers.iloc[cust_index]
        consent="denied" if config.sessions>=4 and n==2 else cust.consent_status; linked=consent=="granted" and rng.random()>.22
        anon=f"AN-{rng.integers(1,max(2,config.sessions//2)):08d}"
        channel="website" if n==1 else "mobile_app" if n==2 else str(rng.choice(["website","mobile_app"],p=[.7,.3])); device=str(rng.choice(["desktop","mobile","tablet"],p=[.38,.52,.10]))
        bot=n==4 or (n not in (1,2) and bool(rng.random()<.035)); converted=bool((not bot) and (n==1 or rng.random()<.58))
        began=start+pd.Timedelta(minutes=int(rng.integers(0,max(1,365*24*60))))
        sessions.append({"session_id":sid,"customer_id":cust.customer_id if linked else None,"anonymous_id":anon,"started_at":began.isoformat(),"ended_at":None,"channel":channel,"device_type":device,"consent_status":consent,"is_bot":bot,"lifecycle_state":"completed"})
        page=pages.iloc[int(rng.integers(len(pages)))].page_id; product=products.iloc[int(rng.integers(len(products)))]; cartid=f"CRT-{n:06d}"
        has_support=bool((not bot) and (n%12==0 or rng.random()<0.04))
        sequence=["session_started"]
        if not bot:
            sequence += ["product_viewed"]
            if n==1 or rng.random()<.58: sequence += ["added_to_cart"]
            has_cart="added_to_cart" in sequence
            if has_cart and (n==1 or rng.random()<.64): sequence += ["checkout_started","payment_attempted", "purchase_completed" if converted else "purchase_failed"]
        converted="purchase_completed" in sequence
        if has_support: sequence.append("support_contacted")
        session_event_target=20
        sequence[1:1]=["page_viewed"]*(session_event_target-len(sequence))
        duplicate_position=None
        original_purchase_position=None
        if config.sessions>=4 and n==1:
            original_purchase_position=sequence.index("purchase_completed")
            sequence.pop(1)
            duplicate_position=original_purchase_position
            sequence.insert(duplicate_position,"purchase_completed")
            ground.append({"entity_id":sid,"issue_type":"duplicate_conversion"})
        elapsed_seconds=0; last_occurred=began
        support_page=next((row.page_id for row in pages.itertuples() if row.page_type=="support"),pages.iloc[0].page_id)
        for ei, etype in enumerate(sequence,1):
            if ei > 1: elapsed_seconds += int(rng.integers(8,50))
            occurred=began+pd.Timedelta(seconds=elapsed_seconds); last_occurred=occurred
            delay=1800 if config.sessions>=4 and n==1 and ei==1 else 2 if config.sessions>=4 and n==1 and ei==2 else int(rng.integers(1,6))
            properties={"device_type":device,"bot_signal":bot,"schema_version":"1.0","attempt":1 if etype.startswith("purchase") else None,"order_id":f"ORD-{n:06d}" if etype=="purchase_completed" else None}
            if duplicate_position is not None and ei==duplicate_position+1:
                properties["duplicate_source_event_id"]=f"EVT-{sid}-{duplicate_position:06d}"; properties["duplicate_source"]=True
            ev={"event_id":f"EVT-{sid}-{ei:06d}","session_id":sid,"customer_id":cust.customer_id if linked else None,"anonymous_id":anon,"event_type":etype,"event_timestamp":occurred.isoformat(),"ingestion_timestamp":(occurred+pd.Timedelta(seconds=delay)).isoformat(),"channel":channel,"page_id":support_page if etype=="support_contacted" else page if etype in ("page_viewed","product_viewed","checkout_started","payment_attempted") else None,"product_id":product.product_id if etype in ("product_viewed","added_to_cart","purchase_completed") else None,"event_properties":_json(properties),"event_version":"1.0"}
            if config.sessions>=4 and n==2 and ei==1:
                ev["customer_id"]=customers.iloc[0].customer_id
            event_buffer.append(ev)
            if len(event_buffer)>=config.chunk_size:
                pd.DataFrame(event_buffer).reindex(sorted(event_buffer[0]),axis=1).to_csv(event_path,mode="a",header=not event_path.exists(),index=False,lineterminator="\n",na_rep="")
                event_buffer.clear()
        sessions[-1]["ended_at"]=last_occurred.isoformat()
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
        outcome_type="bot" if bot else "converted" if funnel_complete else "checkout_abandoned" if "checkout_started" in sequence else "cart_abandoned" if "added_to_cart" in sequence else "support_contacted" if has_support else "browsed"
        outcomes.append({"outcome_id":deterministic_id("OUT",n),"session_id":sid,"outcome_type":outcome_type,"outcome_at":(began+pd.Timedelta(minutes=10)).isoformat(),"rule_version":"1.0"})
    if config.sessions >= 4:
        s1=deterministic_id("SES",1); s2=deterministic_id("SES",2); s4=deterministic_id("SES",4)
        ground.extend([{"entity_id":s1,"issue_type":"out_of_order_arrival"},{"entity_id":s2,"issue_type":"identity_stitching"},{"entity_id":s4,"issue_type":"bot_traffic"}])
    if event_buffer:
        pd.DataFrame(event_buffer).reindex(sorted(event_buffer[0]),axis=1).to_csv(event_path,mode="a",header=not event_path.exists(),index=False,lineterminator="\n",na_rep="")
        event_buffer.clear()
    event_dtypes={"session_id":"category","customer_id":"category","anonymous_id":"category","event_type":"category","channel":"category","event_version":"category"}
    tables={"customers":customers,"sessions":pd.DataFrame(sessions),"pages":pages,"products":products,"carts":pd.DataFrame(carts,columns=["cart_id","session_id","customer_id","created_at","state"]),"cart_items":pd.DataFrame(cartitems,columns=["cart_item_id","cart_id","product_id","quantity","unit_price"]),"orders":pd.DataFrame(orders,columns=["order_id","session_id","customer_id","cart_id","ordered_at","status","total_amount","currency"]),"support_tickets":pd.DataFrame(tickets,columns=["ticket_id","session_id","customer_id","created_at","status","reason"]),"experiments":experiments,"experiment_assignments":pd.DataFrame(assignments),"journey_outcomes":pd.DataFrame(outcomes)}
    if retain_tables:
        tables["journey_events"]=pd.read_csv(event_path,dtype=event_dtypes)
    tables["sessions"]["session_id"]=tables["sessions"]["session_id"].astype("category")
    for name,df in tables.items():
        df=df.reindex(sorted(df.columns),axis=1).sort_values(df.columns[0],kind="stable").reset_index(drop=True); tables[name]=df
        df.to_csv(out/f"{name}.csv",index=False,lineterminator="\n",na_rep="")
    for session in sessions:
        if session["is_bot"]: ground.append({"entity_id":session["session_id"],"issue_type":"bot_traffic"})
    ground_df=pd.DataFrame(ground,columns=["entity_id","issue_type"]).drop_duplicates().sort_values(["entity_id","issue_type"],kind="stable").reset_index(drop=True)
    ground_df.to_csv(out/"ground_truth.csv",index=False,lineterminator="\n")
    if retain_tables:
        pred=detect_anomalies(tables)
        metrics=analyze(tables)
    else:
        pred=detect_anomalies_csv(event_path,tables["sessions"],set(tables["sessions"].session_id.astype(str)),config.chunk_size)
        metrics=analyze_csv(event_path,tables,chunk_size=config.chunk_size)
    evaluation=evaluate_detection(pred,ground_df)
    event_checks,event_row_count=validate_events_csv(event_path,tables,TAXONOMY,config.sessions*20,config.chunk_size)
    primary_keys={"customers":"customer_id","sessions":"session_id","pages":"page_id","products":"product_id","carts":"cart_id","cart_items":"cart_item_id","orders":"order_id","support_tickets":"ticket_id","experiments":"experiment_id","experiment_assignments":"assignment_id","journey_outcomes":"outcome_id"}
    checks={f"{table}_pk_unique":bool(tables[table][key].is_unique) for table,key in primary_keys.items()}
    checks.update({
        "session_customer_fk_valid":bool(tables["sessions"].customer_id.dropna().isin(tables["customers"].customer_id).all()),
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
        "allowed_channel_values":bool(tables["sessions"].channel.isin(["website","mobile_app"]).all()),
        "allowed_device_values":bool(tables["sessions"].device_type.isin(["desktop","mobile","tablet"]).all()),
        "allowed_consent_values":bool(tables["sessions"].consent_status.isin(["granted","denied","unknown"]).all() and tables["customers"].consent_status.isin(["granted","denied","unknown"]).all()),
        "allowed_customer_lifecycle":bool(tables["customers"].lifecycle_state.isin(["active","inactive","deleted"]).all()),
        "allowed_session_lifecycle":bool(tables["sessions"].lifecycle_state.isin(["active","completed","expired"]).all()),
        "allowed_page_types":bool(tables["pages"].page_type.isin(["landing","discovery","product","cart","checkout","payment","support","campaign"]).all()),
        "allowed_catalog_lifecycle":bool(tables["pages"].is_active.isin([True,False]).all() and tables["products"].is_active.isin([True,False]).all()),
        "nonnegative_product_prices":bool((tables["products"].unit_price>=0).all()),
        "allowed_cart_lifecycle":bool(tables["carts"].state.isin(["open","abandoned","converted","expired"]).all()),
        "positive_cart_item_quantities":bool((tables["cart_items"].quantity>0).all()),
        "nonnegative_cart_item_prices":bool((tables["cart_items"].unit_price>=0).all()),
        "allowed_order_lifecycle":bool(tables["orders"].status.isin(["pending","paid","failed","refunded"]).all()),
        "allowed_support_lifecycle":bool(tables["support_tickets"].status.isin(["open","pending","resolved","closed"]).all()),
        "allowed_experiment_lifecycle":bool(tables["experiments"].status.isin(["draft","active","completed","paused"]).all()),
        "allowed_outcome_types":bool(tables["journey_outcomes"].outcome_type.isin(["converted","checkout_abandoned","cart_abandoned","support_contacted","browsed","bot"]).all()),
        "outcome_one_per_session":bool(tables["journey_outcomes"].session_id.is_unique),
        "session_timestamp_order":bool((pd.to_datetime(tables["sessions"].ended_at,utc=True)>=pd.to_datetime(tables["sessions"].started_at,utc=True)).all()),
        "sessionization_timeout":bool(((pd.to_datetime(tables["sessions"].ended_at,utc=True)-pd.to_datetime(tables["sessions"].started_at,utc=True))<pd.Timedelta(minutes=30)).all()),
        "assignment_effective_dates":bool(tables["experiment_assignments"].merge(tables["experiments"],on="experiment_id").assign(valid=lambda frame:(pd.to_datetime(frame.assigned_at,utc=True)>=pd.to_datetime(frame.start_at,utc=True))&(pd.to_datetime(frame.assigned_at,utc=True)<=pd.to_datetime(frame.end_at,utc=True))).valid.all()),
        "cart_order_totals_reconcile":bool(tables["orders"].merge(tables["cart_items"].assign(line_total=lambda frame:frame.quantity*frame.unit_price).groupby("cart_id",as_index=False).line_total.sum(),on="cart_id",how="left").dropna(subset=["cart_id"]).eval("total_amount == line_total").all()),
    })
    checks.update(event_checks)
    errors=[name for name,passed in checks.items() if not passed]
    validation={"status":"passed" if not errors else "failed","entity_row_counts":({name:len(frame) for name,frame in tables.items()} | {"journey_events":event_row_count}),"errors":errors,"warnings":["Injected anomalies are retained in source events and evaluated separately against ground_truth.csv."],"reconciliation":{"generated_sessions":len(tables["sessions"]),"generated_events":event_row_count,"filtered_sessions":metrics["sessions"],"paid_order_ids":metrics["purchase_order_count"],"converting_sessions":metrics["purchases"],"conversion_numerator":metrics["purchases"],"conversion_denominator":metrics["eligible_sessions"],"conversion_rate":metrics["conversion_rate"],"eligible_mature_carts":metrics["eligible_cart_sessions"],"abandoned_carts":metrics["abandoned_cart_sessions"],"abandonment_rate":metrics["abandonment_rate"],"support_contact_rate":metrics["support_contact_rate"]},"funnel_counts":{row["stage"]:row["sessions"] for row in metrics["funnel"]},"anomaly_evaluation":evaluation,"checks":checks,"check_categories":{"structural_integrity":list(checks),"anomaly_detection_metrics":["true_positives","false_positives","false_negatives","precision","recall","f1"]}}
    (out/"validation_report.json").write_text(json.dumps(validation,indent=2,sort_keys=True)+"\n")
    dataset_files=sorted({f"{name}.csv" for name in tables}|{"journey_events.csv","ground_truth.csv"})
    checksums={name:_sha256_file(out/name) for name in dataset_files}
    manifest={"seed":config.seed,"config":asdict(config),"datasets_fingerprinted":sorted(checksums),"comparison_scope":"Full generated profile for this seed/configuration; no filtered dashboard extract is included.","sha256":checksums,"entity_row_counts":validation["entity_row_counts"],"derived_metrics":{"funnel_counts":validation["funnel_counts"],"conversion_rate":metrics["conversion_rate"],"abandonment_rate":metrics["abandonment_rate"]},"anomaly_counts":ground_df.issue_type.value_counts().sort_index().to_dict(),"anomaly_evaluation":evaluation}
    (out/"reproducibility.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    if database_url:
        engine=create_engine(database_url)
        with engine.begin() as conn:
            missing=(set(tables)|{"journey_events"})-set(inspect(conn).get_table_names())
            if missing: raise ValueError(f"Apply schema.sql before loading generated rows; missing tables: {sorted(missing)}")
            for name in ("customers","pages","products","experiments","sessions","journey_events","carts","cart_items","orders","support_tickets","experiment_assignments","journey_outcomes"):
                if name=="journey_events":
                    reader=pd.read_csv(event_path,chunksize=config.chunk_size,dtype={"event_id":"string","session_id":"string","customer_id":"string","anonymous_id":"string","event_type":"string","channel":"string","page_id":"string","product_id":"string","event_version":"string","event_properties":"string"})
                    for batch in reader:
                        batch=batch.astype(object).where(pd.notna(batch),None)
                        batch["event_properties"]=batch["event_properties"].map(json.loads)
                        batch.to_sql(name,conn,if_exists="append",index=False,method="multi",chunksize=min(config.chunk_size,50),dtype={"event_properties":JSONB})
                else:
                    tables[name].to_sql(name,conn,if_exists="append",index=False,method="multi",chunksize=min(config.chunk_size,50))
    return {"tables":tables,"validation":validation,"ground_truth":ground_df,"detections":pred}


def verify_reproducibility(config: Config = Config(), output: str | Path = "data") -> dict:
    """Generate the same full profile twice and compare complete canonical CSV exports."""
    target = Path(output)
    first = generate(config, target, retain_tables=False)
    first_validation = first["validation"]
    del first
    with TemporaryDirectory(prefix="journeyiq-repro-") as temporary:
        second = generate(config, temporary, retain_tables=False)
        second_validation = second["validation"]
        del second
        first_report = json.loads((target / "reproducibility.json").read_text())
        second_report = json.loads((Path(temporary) / "reproducibility.json").read_text())
        dataset_files = first_report["datasets_fingerprinted"]
        first_hashes = {name: _sha256_file(target / name) for name in dataset_files}
        second_hashes = {name: _sha256_file(Path(temporary) / name) for name in dataset_files}
        first_metrics = first_validation["reconciliation"] | {"funnel_counts": first_validation["funnel_counts"]}
        second_metrics = second_validation["reconciliation"] | {"funnel_counts": second_validation["funnel_counts"]}
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
    result=verify_reproducibility(cfg,args.output) if args.verify_reproducibility else generate(cfg,args.output,args.database_url,retain_tables=False)["validation"]
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
