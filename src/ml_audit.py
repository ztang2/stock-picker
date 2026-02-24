"""ML Health Audit — Weekly checks to ensure ML is working as expected.

Run this weekly to verify:
1. ML model exists and is producing real predictions
2. Daily snapshots are being saved
3. ML weight is > 0 and affecting rankings
4. ML accuracy over recent periods
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ML_DIR = DATA_DIR / "ml"
SNAPSHOT_DIR = DATA_DIR / "daily_snapshots"
RESULTS_FILE = DATA_DIR / "scan_results.json"
ML_VALIDATION_LOG = DATA_DIR / "ml_validation_log.json"
AUDIT_LOG = DATA_DIR / "ml_audit_log.json"


def _load_json(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return None
    return None


def _save_json(path: Path, data):
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def audit_ml_health() -> dict:
    """Run comprehensive ML health audit."""
    
    issues = []
    warnings = []
    checks = []
    
    # Check 1: Does ML model exist?
    model_path = ML_DIR / "model.pkl"
    model_exists = model_path.exists()
    checks.append({
        "check": "ML model exists",
        "status": "✅ PASS" if model_exists else "❌ FAIL",
        "details": f"Model file: {model_path}",
    })
    if not model_exists:
        issues.append("ML model.pkl does not exist - run train_model() first")
    
    # Check 2: Are daily snapshots being saved?
    if SNAPSHOT_DIR.exists():
        snapshots = sorted(SNAPSHOT_DIR.glob("*.json"))
        snapshot_count = len(snapshots)
        
        # Check if snapshots exist
        if snapshot_count == 0:
            checks.append({
                "check": "Daily snapshots exist",
                "status": "❌ FAIL",
                "details": "No snapshots found",
            })
            issues.append("No daily snapshots found - snapshots should be saved after each scan")
        else:
            # Check recency of last snapshot
            last_snapshot = snapshots[-1]
            last_date = last_snapshot.stem  # YYYY-MM-DD
            try:
                last_dt = datetime.strptime(last_date, "%Y-%m-%d")
                days_since = (datetime.now() - last_dt).days
                
                if days_since > 7:
                    checks.append({
                        "check": "Recent snapshots",
                        "status": "⚠️ WARNING",
                        "details": f"Last snapshot is {days_since} days old ({last_date})",
                    })
                    warnings.append(f"Last snapshot is {days_since} days old - are daily scans running?")
                else:
                    checks.append({
                        "check": "Recent snapshots",
                        "status": "✅ PASS",
                        "details": f"{snapshot_count} snapshots, last: {last_date} ({days_since} days ago)",
                    })
            except Exception:
                checks.append({
                    "check": "Snapshot parsing",
                    "status": "❌ FAIL",
                    "details": f"Could not parse snapshot date: {last_date}",
                })
                issues.append("Snapshot date format invalid")
    else:
        checks.append({
            "check": "Daily snapshots directory",
            "status": "❌ FAIL",
            "details": "Snapshot directory does not exist",
        })
        issues.append("Snapshot directory missing - create data/daily_snapshots/")
    
    # Check 3: Is ML producing non-None scores in latest scan?
    scan_results = _load_json(RESULTS_FILE)
    if scan_results:
        top_stocks = scan_results.get("top", scan_results.get("stocks", []))
        ml_scores = [s.get("ml_score") for s in top_stocks if s.get("ml_score") is not None]
        ml_weight = top_stocks[0].get("ml_weight", 0) if top_stocks else 0
        
        if not ml_scores:
            checks.append({
                "check": "ML scores in scan results",
                "status": "⚠️ WARNING",
                "details": "No ml_score values found in latest scan results",
            })
            warnings.append("ML scores are None in scan results - model may not be predicting")
        else:
            # Check if scores are actually different (not all the same)
            unique_scores = len(set(ml_scores))
            if unique_scores == 1:
                checks.append({
                    "check": "ML score diversity",
                    "status": "⚠️ WARNING",
                    "details": f"All ML scores are identical: {ml_scores[0]}",
                })
                warnings.append("ML scores lack diversity - all predictions identical")
            else:
                checks.append({
                    "check": "ML scores in scan results",
                    "status": "✅ PASS",
                    "details": f"{len(ml_scores)} stocks have ML scores, {unique_scores} unique values",
                })
        
        # Check 4: Is ML weight > 0 and affecting rankings?
        if ml_weight > 0:
            # Compare base_score vs composite_score to see if ML is affecting rankings
            score_diffs = [
                abs(s.get("composite_score", 0) - s.get("base_score", 0))
                for s in top_stocks
                if s.get("base_score") is not None and s.get("composite_score") is not None
            ]
            
            if score_diffs and max(score_diffs) < 0.1:
                checks.append({
                    "check": "ML affecting rankings",
                    "status": "⚠️ WARNING",
                    "details": f"ML weight={ml_weight} but scores unchanged (max diff={max(score_diffs):.2f})",
                })
                warnings.append("ML weight > 0 but not affecting composite scores")
            elif score_diffs:
                avg_diff = sum(score_diffs) / len(score_diffs)
                checks.append({
                    "check": "ML affecting rankings",
                    "status": "✅ PASS",
                    "details": f"ML weight={ml_weight}, avg score change={avg_diff:.2f}",
                })
            else:
                checks.append({
                    "check": "ML affecting rankings",
                    "status": "⚠️ WARNING",
                    "details": "Cannot compare base_score vs composite_score",
                })
        else:
            checks.append({
                "check": "ML weight",
                "status": "ℹ️ INFO",
                "details": f"ML weight is {ml_weight} (ML not active yet)",
            })
    else:
        checks.append({
            "check": "Latest scan results",
            "status": "❌ FAIL",
            "details": "No scan results found",
        })
        issues.append("No scan_results.json found")
    
    # Check 5: ML accuracy over last 7 and 30 days
    ml_log = _load_json(ML_VALIDATION_LOG) or []
    if ml_log:
        # Last 7 days
        recent_7 = [r for r in ml_log if _days_ago(r.get("date", "")) <= 7]
        if recent_7:
            accuracies_7 = [r["ml_accuracy"] for r in recent_7 if r.get("ml_accuracy") is not None]
            avg_7 = sum(accuracies_7) / len(accuracies_7) if accuracies_7 else None
            
            if avg_7 is not None:
                status_7 = "✅ PASS" if avg_7 >= 50 else "❌ FAIL"
                checks.append({
                    "check": "ML accuracy (7 days)",
                    "status": status_7,
                    "details": f"{avg_7:.1f}% ({len(accuracies_7)} days)",
                })
                if avg_7 < 50:
                    issues.append(f"ML accuracy below 50% over last 7 days: {avg_7:.1f}%")
        
        # Last 30 days
        recent_30 = [r for r in ml_log if _days_ago(r.get("date", "")) <= 30]
        if recent_30:
            accuracies_30 = [r["ml_accuracy"] for r in recent_30 if r.get("ml_accuracy") is not None]
            avg_30 = sum(accuracies_30) / len(accuracies_30) if accuracies_30 else None
            
            if avg_30 is not None:
                status_30 = "✅ PASS" if avg_30 >= 50 else "⚠️ WARNING"
                checks.append({
                    "check": "ML accuracy (30 days)",
                    "status": status_30,
                    "details": f"{avg_30:.1f}% ({len(accuracies_30)} days)",
                })
                if avg_30 < 50:
                    warnings.append(f"ML accuracy below 50% over last 30 days: {avg_30:.1f}%")
    else:
        checks.append({
            "check": "ML validation log",
            "status": "ℹ️ INFO",
            "details": "No ML validation data yet",
        })
    
    # Overall verdict
    if issues:
        verdict = "CRITICAL"
    elif warnings:
        verdict = "WARNING"
    else:
        verdict = "HEALTHY"
    
    report = {
        "audit_date": datetime.now().isoformat(),
        "verdict": verdict,
        "issues": issues,
        "warnings": warnings,
        "checks": checks,
    }
    
    # Save to audit log
    audit_log = _load_json(AUDIT_LOG) or []
    audit_log.append(report)
    _save_json(AUDIT_LOG, audit_log[-52:])  # Keep 1 year of weekly audits
    
    return report


def _days_ago(date_str: str) -> int:
    """Calculate days between date_str and now."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return (datetime.now() - dt).days
    except Exception:
        return 999


def format_audit_report(report: dict) -> str:
    """Format audit report for display."""
    lines = []
    lines.append("=" * 60)
    lines.append("ML HEALTH AUDIT REPORT")
    lines.append("=" * 60)
    lines.append(f"Audit Date: {report['audit_date']}")
    lines.append(f"Verdict: {report['verdict']}")
    lines.append("")
    
    # Checks
    lines.append("CHECKS:")
    for check in report["checks"]:
        lines.append(f"  {check['status']} {check['check']}")
        lines.append(f"     → {check['details']}")
    
    lines.append("")
    
    # Issues
    if report["issues"]:
        lines.append("🚨 CRITICAL ISSUES:")
        for issue in report["issues"]:
            lines.append(f"  • {issue}")
        lines.append("")
    
    # Warnings
    if report["warnings"]:
        lines.append("⚠️  WARNINGS:")
        for warning in report["warnings"]:
            lines.append(f"  • {warning}")
        lines.append("")
    
    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    report = audit_ml_health()
    print(format_audit_report(report))
