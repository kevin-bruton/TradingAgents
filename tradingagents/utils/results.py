import datetime
from pathlib import Path
from typing import Tuple, Optional


def create_run_results_dirs(base_results_dir: str, ticker: str, analysis_date: str, run_id: Optional[str] = None) -> Tuple[Path, Path, Path]:
    """Create and return (results_dir, reports_dir, log_file_path).

    Backward compatible with previous minute-level naming but now includes seconds by default
    if run_id is provided use its timestamp portion after first '--' for folder naming fallback.

    New Folder naming convention (multi-run ready):
        results/{ticker}/{YYYY-MM-DD_HH.MM.SS}/
          reports/
          message_tool.log
          RUN_ID  (marker file containing the full run_id)

    If multiple runs start within the same second (rare), we still apply _n suffix.
    """
    base = Path(base_results_dir)
    # Derive timestamp component
    if run_id and '--' in run_id:
        # run_id pattern: <TICKER>--<YYYY-MM-DD_HH.MM.SS>--<suffix>
        parts = run_id.split('--')
        if len(parts) >= 3:
            ts_component = parts[1]
        else:
            ts_component = datetime.datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
    else:
        ts_component = f"{analysis_date}_{datetime.datetime.now().strftime('%H.%M.%S')}"

    # Maintain previous behavior of prefixing analysis_date; ensure ts_component already has date
    if not ts_component.startswith(analysis_date):
        folder_base = f"{analysis_date}_{datetime.datetime.now().strftime('%H.%M.%S')}"
    else:
        folder_base = ts_component

    ticker_dir = base / ticker
    candidate = ticker_dir / folder_base
    counter = 1
    while candidate.exists():
        candidate = ticker_dir / f"{folder_base}_{counter}"
        counter += 1

    reports_dir = candidate / "reports"
    log_file = candidate / "message_tool.log"
    reports_dir.mkdir(parents=True, exist_ok=True)
    log_file.touch(exist_ok=True)

    # Write marker file for multi-run introspection
    if run_id:
        try:
            (candidate / "RUN_ID").write_text(run_id, encoding="utf-8")
        except Exception:
            pass
    return candidate, reports_dir, log_file


__all__ = [
    "create_run_results_dirs",
]
