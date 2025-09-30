import datetime
from pathlib import Path
from typing import Tuple

def create_run_results_dirs(base_results_dir: str, ticker: str, analysis_date: str) -> Tuple[Path, Path, Path]:
    """Create and return (results_dir, reports_dir, log_file_path).

    Folder naming convention: results/{ticker}/{YYYY-MM-DD_HH.MM}/
    - reports/ (markdown reports)
    - message_tool.log (streamed messages & tool calls)

    If multiple runs start within the same minute, an incremental suffix _n is appended.
    """
    base = Path(base_results_dir)
    minute_stamp = datetime.datetime.now().strftime("%H.%M")
    run_folder = f"{analysis_date}_{minute_stamp}"
    ticker_dir = base / ticker

    candidate = ticker_dir / run_folder
    counter = 1
    while candidate.exists():
        candidate = ticker_dir / f"{run_folder}_{counter}"
        counter += 1

    reports_dir = candidate / "reports"
    log_file = candidate / "message_tool.log"
    reports_dir.mkdir(parents=True, exist_ok=True)
    log_file.touch(exist_ok=True)
    return candidate, reports_dir, log_file
