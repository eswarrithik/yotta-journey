import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from yottajourney.analytics import analyze, detect_anomalies, evaluate_detection
from yottajourney.pipeline import Config, generate, verify_reproducibility
from yottajourney.streaming import analyze_csv, detect_anomalies_csv, export_filtered_events


@pytest.fixture(scope="module")
def starter(tmp_path_factory):
    output = tmp_path_factory.mktemp("journeyiq-starter")
    return generate(Config(), output), output


def test_default_starter_profile_and_entity_contract(starter):
    result, output = starter
    tables = result["tables"]
    assert len(tables["sessions"]) == 100
    assert len(tables["journey_events"]) == 2_000
    assert tables["journey_events"].groupby("session_id").size().eq(20).all()
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
    durations = pd.to_datetime(tables["sessions"].ended_at, utc=True) - pd.to_datetime(tables["sessions"].started_at, utc=True)
    assert durations.max() < pd.Timedelta(minutes=30)
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
    purchase_order_ids = purchases.event_properties.map(lambda value: json.loads(value).get("order_id"))
    assert purchases.event_id.is_unique
    assert purchase_order_ids.nunique() < len(purchases)
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


def test_csv_output_is_independent_of_event_buffer_size(tmp_path):
    import hashlib

    outputs = [tmp_path / "small-buffer", tmp_path / "large-buffer"]
    first = generate(Config(seed=20261022, sessions=30, customers=20, chunk_size=64), outputs[0])
    second = generate(Config(seed=20261022, sessions=30, customers=20, chunk_size=257), outputs[1], retain_tables=False)
    assert len(first["tables"]["journey_events"]) == 600
    assert second["validation"]["entity_row_counts"]["journey_events"] == 600
    for name in ["journey_events.csv", "sessions.csv", "ground_truth.csv"]:
        hashes = [hashlib.sha256((output / name).read_bytes()).hexdigest() for output in outputs]
        assert hashes[0] == hashes[1]


def test_reproducibility_compares_same_full_profile_and_serialized_datasets(tmp_path):
    output = tmp_path / "starter"
    comparison = verify_reproducibility(Config(seed=20261022, sessions=30, customers=20), output)
    assert comparison["row_counts_match"]
    assert comparison["sha256_match"]
    assert comparison["derived_metrics_match"]
    assert comparison["anomaly_counts_match"]
    assert comparison["identical"]
    assert comparison["full_profile_only"]
    assert "ground_truth.csv" in comparison["datasets_compared"]
    manifest = json.loads((output / "reproducibility.json").read_text())
    assert manifest["comparison"]["identical"]
    assert manifest["entity_row_counts"]["sessions"] == 30


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


def test_product_filter_changes_the_analytics_cohort(starter):
    tables = starter[0]["tables"]
    product_id = tables["products"].product_id.iloc[0]
    expected = set(tables["journey_events"].loc[tables["journey_events"].product_id.eq(product_id), "session_id"])
    filtered = analyze(tables, product_id=product_id)
    assert filtered["sessions"] == len(expected)
    assert filtered["funnel"][0]["sessions"] == filtered["eligible_sessions"]
    assert filtered["support_sessions"] <= filtered["sessions"]


def test_full_profile_configuration_is_exact_but_not_performance_claim():
    config = Config.full(seed=20261022)
    assert config.sessions == 100_000
    assert config.sessions * 20 == 2_000_000
    assert config.seed == 20261022
    assert config.chunk_size > 0


def test_chunked_analytics_matches_in_memory_filters_and_funnel(starter):
    result, output = starter
    tables = result["tables"]
    product_id = tables["products"].product_id.iloc[0]
    as_of = pd.to_datetime(tables["journey_events"].event_timestamp, utc=True).max()
    expected = analyze(tables, channel="website", product_id=product_id, start_at="2026-01-01", as_of=as_of)
    streamed = analyze_csv(
        output / "journey_events.csv", tables, channel="website", product_id=product_id,
        start_at="2026-01-01", as_of=as_of, chunk_size=17,
    )
    for key in [
        "sessions", "eligible_sessions", "unique_customers", "purchases", "purchase_order_count",
        "abandoned_cart_sessions", "eligible_cart_sessions", "support_sessions", "checkout_failures",
        "anonymous_sessions", "identified_sessions", "channel_sessions",
    ]:
        assert streamed[key] == expected[key]
    for key in ["conversion_rate", "abandonment_rate", "support_contact_rate", "median_latency_seconds"]:
        assert streamed[key] == pytest.approx(expected[key])
    assert streamed["funnel"] == expected["funnel"]
    assert streamed["filtered_event_count"] == len(
        tables["journey_events"][tables["journey_events"].session_id.astype(str).isin(streamed["filtered_session_ids"])]
    )
    pd.testing.assert_frame_equal(
        streamed["friction"].sort_values("page_id").reset_index(drop=True),
        expected["friction"].sort_values("page_id").reset_index(drop=True),
        check_dtype=False,
    )


def test_chunked_anomalies_and_filtered_csv_json_exports_match_full_data(starter, tmp_path):
    result, output = starter
    tables = result["tables"]
    selected_ids = set(tables["sessions"].head(20).session_id.astype(str))
    streamed = detect_anomalies_csv(output / "journey_events.csv", tables["sessions"], selected_ids, chunk_size=31)
    expected = detect_anomalies(tables)
    expected = expected[expected.entity_id.isin(selected_ids)].sort_values(["entity_id", "issue_type"]).reset_index(drop=True)
    streamed = streamed.sort_values(["entity_id", "issue_type"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(streamed, expected, check_dtype=False)

    csv_path = tmp_path / "filtered.csv"
    json_path = tmp_path / "filtered.json"
    export_filtered_events(output / "journey_events.csv", csv_path, selected_ids, chunk_size=37)
    export_filtered_events(output / "journey_events.csv", json_path, selected_ids, chunk_size=37, as_json=True, metadata={"filtered_sessions": len(selected_ids)})
    csv_events = pd.read_csv(csv_path)
    json_payload = json.loads(json_path.read_text())
    assert len(csv_events) == len(json_payload["events"]) == len(selected_ids) * 20
    assert json_payload["filtered_sessions"] == len(selected_ids)


def test_report_generation_can_omit_canonical_event_dataframe(tmp_path):
    result = generate(Config(seed=20261022, sessions=12, customers=9, chunk_size=11), tmp_path, retain_tables=False)
    assert "journey_events" not in result["tables"]
    report = result["validation"]
    assert report["entity_row_counts"]["sessions"] == 12
    assert report["entity_row_counts"]["journey_events"] == 240
    assert report["checks"]["event_volume_target"]
    assert report["status"] == "passed"
