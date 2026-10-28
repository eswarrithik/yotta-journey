import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "dashboard"))
from sample_data import anomaly_summary, filtered_sessions, funnel_counts, generate_demo_data, validate_sample


def test_demo_is_reproducible_and_structural_checks_pass():
    first = generate_demo_data()
    second = generate_demo_data()
    for name in first:
        assert first[name].equals(second[name])
    assert len(first["sessions"]) == 100
    assert 1500 <= len(first["events"]) <= 2600
    assert first["events"].event_id.is_unique
    result = validate_sample(first, first["sessions"])
    assert result["status"] == "PASS"


def test_demo_contains_all_four_anomalies_without_using_truth_as_input():
    data = generate_demo_data()
    sessions = filtered_sessions(data)
    funnel = funnel_counts(data, sessions)
    assert funnel.sessions.tolist() == sorted(funnel.sessions.tolist(), reverse=True)
    signals = anomaly_summary(data, sessions)
    assert not signals["duplicates"].empty
    assert not signals["bots"].empty
    assert not signals["delayed"].empty
    assert not signals["out_of_order"].empty
    assert not signals["identity"].empty
    assert {"out_of_order_arrival", "identity_stitching", "duplicate_conversion", "bot_traffic"}.issubset(set(signals["ground_truth"].issue_type))
    assert signals["scores"]["precision"] == 1.0
    assert signals["scores"]["recall"] == 1.0
    assert signals["scores"]["f1"] == 1.0


def test_support_events_and_tickets_exist_and_share_sessions():
    data = generate_demo_data()
    support_event_sessions = set(data["events"].loc[data["events"].event_type.eq("support_contacted"), "session_id"])
    support_ticket_sessions = set(data["support"].session_id)
    assert support_event_sessions
    assert support_event_sessions == support_ticket_sessions


def test_channel_filter_changes_actual_cohort_and_funnel_denominator():
    data = generate_demo_data()
    website = filtered_sessions(data, channel="Website")
    mobile = filtered_sessions(data, channel="Mobile app")
    assert len(website) + len(mobile) == len(data["sessions"])
    assert set(website.channel) == {"Website"}
    assert set(mobile.channel) == {"Mobile app"}
    assert funnel_counts(data, website).iloc[0].sessions == len(website[~website.is_bot])
    assert funnel_counts(data, mobile).iloc[0].sessions == len(mobile[~mobile.is_bot])
