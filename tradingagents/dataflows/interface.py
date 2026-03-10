from typing import Annotated
from datetime import datetime, date, timedelta

# Import from vendor-specific modules
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .alpha_vantage_common import AlphaVantageRateLimitError

# Configuration and routing logic
from .config import get_config

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    }
}

VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
]

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    # technical_indicators
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    # fundamental_data
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    # news_data
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
}


def _parse_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _clamp_date(value: str, as_of_date: date, inclusive: bool = True) -> str:
    parsed = _parse_date(value)
    if not parsed:
        return value

    limit = as_of_date
    if not inclusive:
        limit = as_of_date + timedelta(days=1)

    return min(parsed, limit).isoformat()


def _apply_as_of_date(method: str, args: list, as_of_date: date):
    as_of_str = as_of_date.isoformat()
    today = datetime.now().date()

    if method == "get_insider_transactions" and as_of_date < today:
        return args, (
            f"Insider transactions are only available as of today; "
            f"skipping historical request for {as_of_str} to avoid look-ahead bias."
        )

    if method in {"get_stock_data", "get_news"} and len(args) >= 3:
        start_date = args[1]
        # yfinance end_date is exclusive; allow clamping to as_of_date + 1
        # so that data for as_of_date itself can be retrieved.
        end_date = _clamp_date(args[2], as_of_date, inclusive=False)
        start_dt = _parse_date(start_date)
        end_dt = _parse_date(end_date)
        if start_dt and end_dt and start_dt > end_dt:
            return args, f"No data available between {start_date} and {end_date}."
        args[2] = end_date
        return args, None

    if method == "get_indicators" and len(args) >= 3:
        curr_date = args[2] or as_of_str
        curr_dt = _parse_date(curr_date)
        if not curr_dt or curr_dt > as_of_date:
            curr_date = as_of_str
        args[2] = curr_date
        return args, None

    if method == "get_global_news" and len(args) >= 1:
        curr_date = args[0] or as_of_str
        curr_dt = _parse_date(curr_date)
        if not curr_dt or curr_dt > as_of_date:
            curr_date = as_of_str
        args[0] = curr_date
        return args, None

    if method == "get_fundamentals" and len(args) >= 2:
        curr_date = args[1] or as_of_str
        curr_dt = _parse_date(curr_date)
        if not curr_dt or curr_dt > as_of_date:
            curr_date = as_of_str
        args[1] = curr_date
        return args, None

    if method in {"get_balance_sheet", "get_cashflow", "get_income_statement"} and len(args) >= 3:
        curr_date = args[2] or as_of_str
        curr_dt = _parse_date(curr_date)
        if not curr_dt or curr_dt > as_of_date:
            curr_date = as_of_str
        args[2] = curr_date
        return args, None

    return args, None

def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")

def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]
    config = get_config()
    as_of_date = _parse_date(config.get("as_of_date")) if config else None
    if as_of_date:
        adjusted_args, early_result = _apply_as_of_date(method, list(args), as_of_date)
        if early_result is not None:
            return early_result
        args = tuple(adjusted_args)

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    # Build fallback chain: primary vendors first, then remaining available vendors
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return impl_func(*args, **kwargs)
        except AlphaVantageRateLimitError:
            continue  # Only rate limits trigger fallback

    raise RuntimeError(f"No available vendor for '{method}'")
