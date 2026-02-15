"""Track consecutive days each ticker has been in top 20."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STREAK_FILE = DATA_DIR / "streak_tracker.json"
HISTORY_FILE = DATA_DIR / "signal_history.json"


def _load_streaks() -> Dict[str, dict]:
    """Load streak tracker data."""
    if STREAK_FILE.exists():
        try:
            return json.loads(STREAK_FILE.read_text())
        except Exception:
            logger.warning("Failed to load streak tracker", exc_info=True)
    return {}


def _save_streaks(streaks: Dict[str, dict]) -> None:
    """Save streak tracker data."""
    DATA_DIR.mkdir(exist_ok=True)
    STREAK_FILE.write_text(json.dumps(streaks, indent=2, default=str))


def _load_history() -> List[Dict]:
    """Load signal history."""
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            logger.warning("Failed to load signal history", exc_info=True)
    return []


def _get_top20_by_date(history: List[Dict]) -> Dict[str, List[str]]:
    """
    Group signal history by date and get top 20 tickers for each date.
    Returns: {date: [list of top 20 tickers for that date]}
    """
    by_date = {}  # type: Dict[str, List[Dict]]
    
    for entry in history:
        date = entry.get("date")
        if not date:
            continue
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(entry)
    
    # Sort each date's entries by score and take top 20
    top20_by_date = {}
    for date, entries in by_date.items():
        sorted_entries = sorted(entries, key=lambda x: x.get("score", 0), reverse=True)
        top20_by_date[date] = [e["ticker"] for e in sorted_entries[:20]]
    
    return top20_by_date


def update_streaks(current_top20: List[str], current_date: Optional[str] = None) -> Dict[str, dict]:
    """
    Update streak tracking based on current top 20 tickers.
    
    Args:
        current_top20: List of ticker symbols currently in top 20 (in rank order)
        current_date: Current date string (YYYY-MM-DD), defaults to today
    
    Returns:
        Updated streak data dict
    """
    if current_date is None:
        current_date = datetime.now().strftime("%Y-%m-%d")
    
    streaks = _load_streaks()
    history = _load_history()
    
    # Get historical top 20 by date
    top20_by_date = _get_top20_by_date(history)
    
    # Get all unique dates sorted
    all_dates = sorted(top20_by_date.keys())
    
    # Current tickers in top 20
    current_tickers = set(current_top20)
    
    # Update streaks for current top 20
    for ticker in current_top20:
        if ticker not in streaks:
            # New ticker - calculate streak from history
            consecutive_days = 1
            first_seen = current_date
            
            # Count backwards from today to find how many consecutive days
            if len(all_dates) > 0:
                # Find dates where this ticker was in top 20
                dates_in_top20 = [d for d in all_dates if ticker in top20_by_date[d]]
                
                if dates_in_top20:
                    # Sort in reverse (most recent first)
                    dates_in_top20.sort(reverse=True)
                    
                    # Count consecutive days from most recent
                    consecutive_days = 0
                    expected_date = datetime.strptime(current_date, "%Y-%m-%d")
                    
                    for date_str in dates_in_top20:
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                        # Allow for weekends (2-3 day gaps)
                        days_diff = (expected_date - date_obj).days
                        if days_diff <= 3:  # Same day or within weekend gap
                            consecutive_days += 1
                            expected_date = date_obj
                            first_seen = date_str
                        else:
                            break
                    
                    # Include today
                    consecutive_days += 1
                    first_seen = dates_in_top20[-1] if dates_in_top20 else current_date
            
            streaks[ticker] = {
                "consecutive_days": consecutive_days,
                "first_seen": first_seen,
                "last_seen": current_date,
            }
        else:
            # Existing ticker - increment streak
            last_seen = streaks[ticker].get("last_seen", "")
            
            # Check if this is a new day
            if last_seen != current_date:
                # Verify it was in the top 20 continuously
                last_date = datetime.strptime(last_seen, "%Y-%m-%d") if last_seen else datetime.now()
                curr_date = datetime.strptime(current_date, "%Y-%m-%d")
                days_diff = (curr_date - last_date).days
                
                # If gap is too large (more than 3 days, accounting for weekends), reset
                if days_diff > 3:
                    streaks[ticker] = {
                        "consecutive_days": 1,
                        "first_seen": current_date,
                        "last_seen": current_date,
                    }
                else:
                    # Increment streak
                    streaks[ticker]["consecutive_days"] = streaks[ticker].get("consecutive_days", 0) + 1
                    streaks[ticker]["last_seen"] = current_date
    
    # Reset streaks for tickers that dropped out
    for ticker in list(streaks.keys()):
        if ticker not in current_tickers:
            # Ticker dropped out - reset to 0
            last_seen = streaks[ticker].get("last_seen", "")
            if last_seen != current_date or ticker not in current_tickers:
                streaks[ticker]["consecutive_days"] = 0
    
    # Clean up old entries (keep tickers with 0 streak for one more day for history)
    streaks_to_remove = []
    for ticker, data in streaks.items():
        if data.get("consecutive_days", 0) == 0:
            last_seen = data.get("last_seen", "")
            if last_seen:
                last_date = datetime.strptime(last_seen, "%Y-%m-%d")
                if (datetime.now() - last_date).days > 1:
                    streaks_to_remove.append(ticker)
    
    for ticker in streaks_to_remove:
        del streaks[ticker]
    
    _save_streaks(streaks)
    logger.info("Updated streaks for %d tickers", len(current_tickers))
    
    return streaks


def get_streak(ticker: str) -> Tuple[int, Optional[str], Optional[str]]:
    """
    Get streak info for a specific ticker.
    
    Returns:
        (consecutive_days, first_seen, last_seen)
    """
    streaks = _load_streaks()
    data = streaks.get(ticker, {})
    return (
        data.get("consecutive_days", 0),
        data.get("first_seen"),
        data.get("last_seen"),
    )


def get_all_streaks() -> Dict[str, dict]:
    """Get all current streaks."""
    return _load_streaks()


def add_streaks_to_results(results: List[dict]) -> List[dict]:
    """
    Add consecutive_days field to each stock in results.
    
    Args:
        results: List of stock dicts (scan results top list)
    
    Returns:
        Updated results list with consecutive_days added
    """
    streaks = _load_streaks()
    
    for stock in results:
        ticker = stock.get("ticker")
        if ticker:
            streak_data = streaks.get(ticker, {})
            stock["consecutive_days"] = streak_data.get("consecutive_days", 0)
            stock["first_seen"] = streak_data.get("first_seen")
    
    return results
