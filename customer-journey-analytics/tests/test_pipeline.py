import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from yottajourney.analytics import analyze, detect_anomalies, evaluate_detection
from yottajourney.pipeline import Config, generate


@pytest.fixture(scope="module")
def starter(tmp_path_factory):
    output = tmp_path_factory.mktemp("journeyiq-starter")
    return generate(Config(), output), output


def csv_hashes(directory):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(directory.glob("*.csv"))}


def test_default_starter_profile_and_entity_contract(starter):
    result, output = starter
    tables = result["tables"]
    assert len(tables["sessions"]) == 100
    assert 1500 <= len(tables["journey_events"]) <= 2600
    assert len(tables) == 12
    assert result["validation"]["status"] == "passed"
    assert all(result["validation"]["checks"].values())
    for table_name, key in {
        "customers": "customer_id", "sessions": "session_id", "journey_events": "event_id", "pages": "page_id",
        "products": "product_id", "carts": "cart_id", "cart_items": "cart_item_id", "orders": "order_id",
        "support_tickets": "ticket_id", "experiments": "experiment_id", "experiment_assignments": "assignment_id",
        "journey_outcomes": "outcome_id",
    }.items():
        assert tables[table_name][key].is_unique
        assert (output / f"{table_name}.csv").exists()


def test_all_foreign_keys_enums_and_lifecycles_are_valid(starter):
    result, _ = starter
    tables = result["tables"]
    report = result["validation"]
    assert report["checks"]["event_session_fk_valid"]
    assert report["checks"]["event_page_fk_valid"]
    assert report["checks"]["event_product_fk_valid"]
    assert report["checks"]["cart_item_cart_fk_valid"]
    assert report["checks"]["cart_item_product_fk_valid"]
    assert report["checks"]["assignment_experiment_fk_valid"]
    assert tables["sessions"].lifecycle_state.isin(["active", "completed", "expired"]).all()
    assert tables["carts"].state.isin(["open", "abandoned", "converted", "expired"]).all()
    assert tables["orders"].status.isin(["pending", "paid", "failed", "refunded"]).all()
    assert tables["support_tickets"].status.isin(["open", "pending", "resolved", "closed"]).all()
    assert tables["journey_outcomes"].outcome_type.isin(["converted", "checkout_abandoned", "cart_abandoned", "browsed", "bot"]).all()


def test_support_channel_failures_and_abandoned_journeys_are_present(starter):
    result, _ = starter
    tables = result["tables"]
    events = tables["journey_events"]
    assert set(tables["sessions"].channel) == {"website", "mobile_app"}
    assert events.event_type.eq("support_contacted").sum() > 0
    assert len(tables["support_tickets"]) > 0
    assert set(events.loc[events.event_type.eq("support_contacted"), "session_id"]) == set(tables["support_tickets"].session_id)
    assert events.event_type.eq("purchase_failed").sum() > 0
    assert tables["journey_outcomes"].outcome_type.isin(["cart_abandoned", "checkout_abandoned"]).any()


def test_timestamp_contract_timeout_and_funnel_denominators(starter):
    result, _ = starter
    tables = result["tables"]
    events = tables["journey_events"]
    assert (pd.to_datetime(events.ingestion_timestamp, utc=True) >= pd.to_datetime(events.event_timestamp, utc=True)).all()
    session_times = tables["sessions"].set_index("session_id")
    grouped = events.groupby("session_id").event_timestamp.agg(["min", "max"])
    assert (pd.to_datetime(grouped["min"], utc=True) == pd.to_datetime(session_times.loc[grouped.index, "started_at"], utc=True)).all()
    assert (pd.to_datetime(session_times.loc[grouped.index, "ended_at"], utc=True) >= pd.to_datetime(grouped["max"], utc=True)).all()
    result_metrics = analyze(tables)
    eligible = tables["sessions"].loc[~tables["sessions"].is_bot, "session_id"].nunique()
    assert result_metrics["eligible_sessions"] == eligible
    assert result_metrics["funnel"][0]["eligible_sessions"] == eligible
    assert result_metrics["funnel"][-1]["sessions"] == result_metrics["purchases"]
    assert result_metrics["conversion_rate"] == pytest.approx(result_metrics["purchases"] / eligible)
    assert result_metrics["abandonment_rate"] == pytest.approx(
        result_metrics["abandoned_cart_sessions"] / result_metrics["eligible_cart_sessions"]
        if result_metrics["eligible_cart_sessions"] else 0.0
    )


def test_duplicate_source_events_do_not_inflate_order_or_conversion_counts(starter):
    result, _ = starter
    tables = result["tables"]
    metrics = analyze(tables)
    purchases = tables["journey_events"].query("event_type == 'purchase_completed'")
    assert purchases.event_id.is_unique
    assert purchases.order_id.nunique() < len(purchases)
    assert metrics["purchase_order_count"] == tables["orders"].query("status == 'paid'").order_id.nunique()
    assert metrics["purchases"] <= metrics["eligible_sessions"]


def test_injected_anomalies_are_separate_from_structural_integrity(starter):
    result, output = starter
    predicted = detect_anomalies(result["tables"])
    truth = result["ground_truth"]
    expected = {"out_of_order_arrival", "identity_stitching", "duplicate_conversion", "bot_traffic"}
    assert expected.issubset(set(truth.issue_type))
    assert set(predicted.columns) == {"entity_id", "issue_type"}
    scores = evaluate_detection(predicted, truth)
    assert scores["precision"] == pytest.approx(1.0)
    assert scores["recall"] == pytest.approx(1.0)
    assert scores["f1"] == pytest.approx(1.0)
    assert result["validation"]["status"] == "passed"
    assert (output / "ground_truth.csv").exists()
    event_properties = result["tables"]["journey_events"].event_properties
    assert all("ground_truth" not in json.loads(value) for value in event_properties)


def test_identity_stitching_exception_is_detected_but_fk_remains_valid(starter):
    result, _ = starter
    tables = result["tables"]
    invalid_links = tables["journey_events"].merge(
        tables["sessions"][["session_id", "consent_status"]], on="session_id"
    ).query("consent_status != 'granted' and customer_id.notna()")
    assert len(invalid_links) > 0
    assert result["validation"]["checks"]["event_customer_fk_valid"]
    assert (result["ground_truth"].issue_type == "identity_stitching").any()


def test_cart_order_reconciliation_and_lifecycle_outcomes(starter):
    result, _ = starter
    tables = result["tables"]
    lines = tables["cart_items"].assign(line_total=lambda frame: frame.quantity * frame.unit_price)
    totals = lines.groupby("cart_id").line_total.sum()
    for order in tables["orders"].dropna(subset=["cart_id"]).itertuples():
        assert order.total_amount == pytest.approx(totals[order.cart_id])
    bot_sessions = set(tables["sessions"].loc[tables["sessions"].is_bot, "session_id"])
    bot_outcomes = set(tables["journey_outcomes"].loc[tables["journey_outcomes"].outcome_type.eq("bot"), "session_id"])
    assert bot_sessions.issubset(bot_outcomes)


def test_reproducibility_compares_same_full_profile_and_serialized_datasets(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    config = Config(seed=20261022, sessions=30, customers=20)
    first = generate(config, first_dir)
    second = generate(config, second_dir)
    assert csv_hashes(first_dir) == csv_hashes(second_dir)
    assert first["validation"]["funnel_counts"] == second["validation"]["funnel_counts"]
    first_manifest = json.loads((first_dir / "reproducibility.json").read_text())
    assert first_manifest["comparison_scope"].startswith("Full generated profile")
    assert "generated ground_truth.csv" in first_manifest["compared_datasets"]
    assert first_manifest["entity_row_counts"]["sessions"] == 30


def test_date_and_channel_filters_propagate_to_funnel_and_support(starter):
    tables = starter[0]["tables"]
    website = analyze(tables, channel="website")
    mobile = analyze(tables, channel="mobile_app")
    assert website["sessions"] + mobile["sessions"] == len(tables["sessions"])
    assert website["funnel"][0]["sessions"] <= website["eligible_sessions"]
    assert mobile["funnel"][0]["sessions"] <= mobile["eligible_sessions"]
    recent = analyze(tables, start_at="2026-01-01", end_at="2026-01-02")
    assert recent["sessions"] <= len(tables["sessions"])
    assert recent["support_sessions"] <= recent["sessions"]


def test_full_profile_configuration_is_exact_but_not_performance_claim():
    config = Config.full(seed=20261022)
    assert config.sessions == 100_000
    assert config.seed == 20261022
    assert config.chunk_size > 0
