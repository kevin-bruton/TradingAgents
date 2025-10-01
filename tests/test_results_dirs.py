from tradingagents.utils.results import create_run_results_dirs
from tradingagents.utils.run_manager import generate_run_id


def test_results_dir_seconds_and_marker(tmp_path):
    base = tmp_path / "results"
    rid = generate_run_id("AAPL")
    # analysis_date portion is first date in run id timestamp
    ts_part = rid.split('--')[1]
    analysis_date = ts_part.split('_')[0]
    results_dir, reports_dir, log_file = create_run_results_dirs(str(base), "AAPL", analysis_date, run_id=rid)
    assert results_dir.exists()
    assert reports_dir.exists()
    assert log_file.exists()
    marker = results_dir / "RUN_ID"
    assert marker.exists()
    assert marker.read_text().strip() == rid


def test_results_dir_collision_suffix(tmp_path, monkeypatch):
    # Force same second by patching datetime
    class DummyDT:
        @staticmethod
        def now():
            from datetime import datetime
            return datetime(2025, 9, 30, 12, 0, 0)
    import tradingagents.utils.results as resmod
    monkeypatch.setattr(resmod.datetime, 'datetime', DummyDT)

    base = tmp_path / "results"
    analysis_date = "2025-09-30"
    d1, _, _ = create_run_results_dirs(str(base), "AAPL", analysis_date)
    d2, _, _ = create_run_results_dirs(str(base), "AAPL", analysis_date)
    assert d1 != d2
