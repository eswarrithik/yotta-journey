import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "dashboard"))
from sample_data import anomaly_summary, filtered_sessions, funnel_counts, generate_demo_data, validate_sample


def test_demo_is_reproducible_and_integrity_checks_pass():
    first = generate_demo_data()
    second = generate_demo_data()
    assert first["sessions"].equals(second["sessions"])
    assert first["events"].equals(second["events"])
    assert first["events"].event_id.is_unique
    result = validate_sample(first, first["sessions"])
    assert result["status"] == "PASS"


def test_demo_contains_measurable_funnel_and_anomaly_examples():
    data = generate_demo_data()
    sessions = filtered_sessions(data)
    funnel = funnel_counts(data, sessions)
    assert funnel.sessions.tolist() == sorted(funnel.sessions.tolist(), reverse=True)
    signals = anomaly_summary(data, sessions)
    assert not signals["duplicates"].empty
    assert not signals["bots"].empty
    assert not signals["delayed"].empty


def test_channel_filter_changes_actual_cohort():
    data = generate_demo_data()
    website = filtered_sessions(data, channel="Website")
    mobile = filtered_sessions(data, channel="Mobile app")
    assert len(website) + len(mobile) == len(data["sessions"])
    assert set(website.channel) == {"Website"}
    assert set(mobile.channel) == {"Mobile app"}
