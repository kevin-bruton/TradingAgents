import json
from datetime import datetime
from .alpha_vantage_common import _make_api_request


def _parse_report_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _filter_reports_by_date(payload: dict, curr_date: str) -> dict:
    if not isinstance(payload, dict):
        return payload
    cutoff = _parse_report_date(curr_date)
    if not cutoff:
        return payload
    for key in ("annualReports", "quarterlyReports"):
        reports = payload.get(key)
        if isinstance(reports, list):
            payload[key] = [
                report
                for report in reports
                if _parse_report_date(report.get("fiscalDateEnding")) and _parse_report_date(report.get("fiscalDateEnding")) <= cutoff
            ]
    return payload


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    """
    Retrieve comprehensive fundamental data for a given ticker symbol using Alpha Vantage.

    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd (not used for Alpha Vantage)

    Returns:
        str: Company overview data including financial ratios and key metrics
    """
    if curr_date:
        cutoff = _parse_report_date(curr_date)
        if cutoff and cutoff < datetime.now().date():
            return (
                "Alpha Vantage company overview does not support historical snapshots; "
                f"skipping request for {curr_date} to avoid look-ahead bias."
            )

    params = {
        "symbol": ticker,
    }

    return _make_api_request("OVERVIEW", params)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """
    Retrieve balance sheet data for a given ticker symbol using Alpha Vantage.

    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly) - not used for Alpha Vantage
        curr_date (str): Current date you are trading at, yyyy-mm-dd (not used for Alpha Vantage)

    Returns:
        str: Balance sheet data with normalized fields
    """
    params = {
        "symbol": ticker,
    }

    response = _make_api_request("BALANCE_SHEET", params)
    if not curr_date:
        return response
    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        return response
    return json.dumps(_filter_reports_by_date(payload, curr_date))


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """
    Retrieve cash flow statement data for a given ticker symbol using Alpha Vantage.

    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly) - not used for Alpha Vantage
        curr_date (str): Current date you are trading at, yyyy-mm-dd (not used for Alpha Vantage)

    Returns:
        str: Cash flow statement data with normalized fields
    """
    params = {
        "symbol": ticker,
    }

    response = _make_api_request("CASH_FLOW", params)
    if not curr_date:
        return response
    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        return response
    return json.dumps(_filter_reports_by_date(payload, curr_date))


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """
    Retrieve income statement data for a given ticker symbol using Alpha Vantage.

    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly) - not used for Alpha Vantage
        curr_date (str): Current date you are trading at, yyyy-mm-dd (not used for Alpha Vantage)

    Returns:
        str: Income statement data with normalized fields
    """
    params = {
        "symbol": ticker,
    }

    response = _make_api_request("INCOME_STATEMENT", params)
    if not curr_date:
        return response
    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        return response
    return json.dumps(_filter_reports_by_date(payload, curr_date))

