"""Daily snapshot verification — ensures no data gaps.

Run after each snapshot save to verify integrity.
Reports missing days, incomplete data, and corruption.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
SNAPSHOT_DIR = DATA_DIR / "daily_snapshots"
VERIFY_FILE = DATA_DIR / "snapshot_verification.json"

# US market holidays 2026 (add more as needed)
MARKET_HOLIDAYS_2026 = {
    "2026-01-01",  # New Year
    "2026-01-19",  # MLK Day
    "2026-02-16",  # Presidents' Day
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-06-19",  # Juneteenth
    "2026-07-03",  # Independence Day (observed)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving
    "2026-12-25",  # Christmas
}

# First day we started collecting snapshots
COLLECTION_START = "2026-02-19"


def get_expected_trading_days(start: str, end: str) -> List[str]:
    """Return list of expected trading days between start and end (inclusive)."""
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    
    days = []
    current = start_dt
    while current <= end_dt:
        day_str = current.strftime("%Y-%m-%d")
        weekday = current.weekday()
        # Skip weekends (5=Sat, 6=Sun) and holidays
        if weekday < 5 and day_str not in MARKET_HOLIDAYS_2026:
            days.append(day_str)
        current += timedelta(days=1)
    
    return days


def verify_snapshot(filepath: Path) -> Dict:
    """Verify a single snapshot file for completeness."""
    issues = []
    try:
        data = json.loads(filepath.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return {"valid": False, "issues": [f"Corrupt/unreadable: {e}"], "stocks": 0}
    
    stocks = len(data.get("all_scores", []))
    top = len(data.get("top", []))
    
    if stocks < 400:
        issues.append(f"Low stock count: {stocks} (expected ~486)")
    if top < 20:
        issues.append(f"Incomplete top list: {top} (expected 20)")
    if not data.get("timestamp"):
        issues.append("Missing timestamp")
    if not data.get("market_regime"):
        issues.append("Missing market_regime")
    
    # Check top stocks have critical fields
    required_fields = ["composite_score", "entry_signal", "sector", "ticker"]
    for stock in data.get("top", [])[:5]:
        missing = [f for f in required_fields if f not in stock]
        if missing:
            issues.append(f"{stock.get('ticker','?')} missing: {missing}")
            break
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "stocks": stocks,
        "top": top,
    }


def run_verification() -> Dict:
    """Run full snapshot verification. Returns report dict."""
    today = datetime.now().strftime("%Y-%m-%d")
    expected_days = get_expected_trading_days(COLLECTION_START, today)
    
    existing_files = {f.stem for f in SNAPSHOT_DIR.glob("*.json")} if SNAPSHOT_DIR.exists() else set()
    
    missing_days = [d for d in expected_days if d not in existing_files]
    extra_days = [d for d in existing_files if d not in expected_days and d >= COLLECTION_START]
    
    # Verify each existing snapshot
    file_issues = {}
    total_valid = 0
    for day in sorted(existing_files):
        filepath = SNAPSHOT_DIR / f"{day}.json"
        result = verify_snapshot(filepath)
        if not result["valid"]:
            file_issues[day] = result
        else:
            total_valid += 1
    
    report = {
        "verified_at": datetime.now().isoformat(),
        "collection_start": COLLECTION_START,
        "expected_trading_days": len(expected_days),
        "snapshots_found": len(existing_files),
        "valid_snapshots": total_valid,
        "missing_days": missing_days,
        "file_issues": file_issues,
        "extra_days": extra_days,  # weekend/holiday snapshots (harmless)
        "status": "OK" if not missing_days and not file_issues else "ISSUES_FOUND",
        "completeness_pct": round(total_valid / max(len(expected_days), 1) * 100, 1),
    }
    
    # Save verification report
    VERIFY_FILE.write_text(json.dumps(report, indent=2))
    logger.info("Snapshot verification: %s (%d/%d days, %.1f%%)", 
                report["status"], total_valid, len(expected_days), report["completeness_pct"])
    
    return report


def format_verification_report(report: Dict) -> str:
    """Format verification report for Discord."""
    status_icon = "✅" if report["status"] == "OK" else "🚨"
    lines = [
        f"{status_icon} **Snapshot Verification** — {report['completeness_pct']}% complete",
        f"📅 {report['valid_snapshots']}/{report['expected_trading_days']} trading days captured (since {report['collection_start']})",
    ]
    
    if report["missing_days"]:
        lines.append(f"❌ **Missing days:** {', '.join(report['missing_days'])}")
    
    if report["file_issues"]:
        for day, info in report["file_issues"].items():
            lines.append(f"⚠️ **{day}:** {'; '.join(info['issues'])}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    report = run_verification()
    print(format_verification_report(report))
