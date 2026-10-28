import hashlib
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0,str(Path(__file__).parents[1]/"src"))
from yottajourney.pipeline import Config, generate
from yottajourney.analytics import analyze, detect_anomalies, evaluate_detection


def test_seed_reproduces_files_and_metrics(tmp_path):
    a=tmp_path/"a"; b=tmp_path/"b"
    x=generate(Config(sessions=30,customers=20),a); y=generate(Config(sessions=30,customers=20),b)
    checks=lambda p:{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(p.glob("*.csv"))}
    assert checks(a)==checks(b)
    assert x["validation"]["funnel_counts"]==y["validation"]["funnel_counts"]

def test_foreign_keys_consent_and_latency(tmp_path):
    result=generate(Config(sessions=20,customers=12),tmp_path)
    t=result["tables"]
    assert t["journey_events"].session_id.isin(t["sessions"].session_id).all()
    ev=t["journey_events"]
    latency=(pd.to_datetime(ev.ingestion_timestamp,utc=True)-pd.to_datetime(ev.event_timestamp,utc=True)).dt.total_seconds()
    assert latency.ge(0).all()
    joined=ev.merge(t["sessions"][["session_id","consent_status"]],on="session_id")
    assert not ((joined.consent_status!="granted") & joined.customer_id.notna()).any()

def test_funnel_is_monotone_and_conversions_idempotent(tmp_path):
    tables=generate(Config(sessions=50,customers=30),tmp_path)["tables"]
    result=analyze(tables)
    counts=[row["sessions"] for row in result["funnel"]]
    assert all(left>=right for left,right in zip(counts,counts[1:]))
    assert result["purchases"]==tables["orders"].session_id.nunique()

def test_ground_truth_is_not_detector_input_and_anomalies_evaluate(tmp_path):
    result=generate(Config(sessions=20,customers=15),tmp_path)
    pred=detect_anomalies(result["tables"]); truth=result["ground_truth"]
    assert set(pred.columns)=={"entity_id","issue_type"}
    assert len(truth)>=4
    scores=evaluate_detection(pred,truth)
    assert scores["true_positives"]>=3
    assert (tmp_path/"ground_truth.csv").exists()

def test_primary_keys_and_parent_relationships(tmp_path):
    t=generate(Config(sessions=25,customers=15),tmp_path)["tables"]
    for name,col in [("sessions","session_id"),("journey_events","event_id"),("customers","customer_id"),("orders","order_id")]: assert t[name][col].is_unique
    assert set(t["cart_items"].cart_id)<=set(t["carts"].cart_id)
    assert set(t["cart_items"].product_id)<=set(t["products"].product_id)
