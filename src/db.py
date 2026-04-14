"""Centralized SQLite database for time-series operational data.

Tables:
- signal_history: daily signal snapshots (replaces signal_history.json)
- alerts: system alerts log (replaces alerts.json)
- trade_history: BUY/SELL record (replaces trade_history.json)

scan_results are handled separately by scan_results_service.py.
"""
import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_FILE = DATA_DIR / "app.db"

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist and migrate legacy JSON files."""
    DATA_DIR.mkdir(exist_ok=True)
    with _lock:
        conn = _connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS signal_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    date        TEXT NOT NULL,
                    ticker      TEXT NOT NULL,
                    signal      TEXT,
                    score       REAL,
                    price_at_signal REAL,
                    strategy    TEXT,
                    UNIQUE(date, ticker, strategy)
                );
                CREATE INDEX IF NOT EXISTS idx_sh_ticker ON signal_history(ticker);
                CREATE INDEX IF NOT EXISTS idx_sh_date   ON signal_history(date);

                CREATE TABLE IF NOT EXISTS alerts (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    type      TEXT,
                    ticker    TEXT,
                    message   TEXT,
                    severity  TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_al_ticker    ON alerts(ticker);
                CREATE INDEX IF NOT EXISTS idx_al_timestamp ON alerts(timestamp);

                CREATE TABLE IF NOT EXISTS trade_history (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    ticker    TEXT NOT NULL,
                    action    TEXT,
                    shares    REAL,
                    price     REAL,
                    reason    TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_th_ticker ON trade_history(ticker);
            """)
            conn.commit()
        finally:
            conn.close()

    _migrate_legacy_json()


def _migrate_legacy_json() -> None:
    """One-time migration of existing JSON files into SQLite. Safe to call repeatedly."""
    _migrate_signal_history()
    _migrate_alerts()
    _migrate_trade_history()


def _migrate_signal_history() -> None:
    legacy = DATA_DIR / "signal_history.json"
    if not legacy.exists():
        return
    try:
        records = json.loads(legacy.read_text())
        if not records:
            return
        with _lock:
            conn = _connect()
            try:
                conn.executemany(
                    """INSERT OR IGNORE INTO signal_history
                       (date, ticker, signal, score, price_at_signal, strategy)
                       VALUES (:date, :ticker, :signal, :score, :price_at_signal, :strategy)""",
                    [
                        {
                            "date": r.get("date", ""),
                            "ticker": r.get("ticker", ""),
                            "signal": r.get("signal"),
                            "score": r.get("score"),
                            "price_at_signal": r.get("price_at_signal"),
                            "strategy": r.get("strategy", "balanced"),
                        }
                        for r in records
                        if isinstance(r, dict)
                    ],
                )
                conn.commit()
                logger.info("Migrated %d signal_history records to SQLite", len(records))
            finally:
                conn.close()
        legacy.rename(legacy.with_suffix(".json.bak"))
    except Exception:
        logger.exception("signal_history migration failed")


def _migrate_alerts() -> None:
    legacy = DATA_DIR / "alerts.json"
    if not legacy.exists():
        return
    try:
        records = json.loads(legacy.read_text())
        if not records:
            return
        with _lock:
            conn = _connect()
            try:
                conn.executemany(
                    """INSERT INTO alerts (timestamp, type, ticker, message, severity)
                       VALUES (:timestamp, :type, :ticker, :message, :severity)""",
                    [
                        {
                            "timestamp": r.get("timestamp", datetime.now().isoformat()),
                            "type": r.get("type"),
                            "ticker": r.get("ticker"),
                            "message": r.get("message"),
                            "severity": r.get("severity", "info"),
                        }
                        for r in records
                        if isinstance(r, dict)
                    ],
                )
                conn.commit()
                logger.info("Migrated %d alerts to SQLite", len(records))
            finally:
                conn.close()
        legacy.rename(legacy.with_suffix(".json.bak"))
    except Exception:
        logger.exception("alerts migration failed")


def _migrate_trade_history() -> None:
    legacy = DATA_DIR / "trade_history.json"
    if not legacy.exists():
        return
    try:
        records = json.loads(legacy.read_text())
        if not records:
            return
        with _lock:
            conn = _connect()
            try:
                conn.executemany(
                    """INSERT INTO trade_history (timestamp, ticker, action, shares, price, reason)
                       VALUES (:timestamp, :ticker, :action, :shares, :price, :reason)""",
                    [
                        {
                            "timestamp": r.get("timestamp", datetime.now().isoformat()),
                            "ticker": r.get("ticker", ""),
                            "action": r.get("action"),
                            "shares": r.get("shares"),
                            "price": r.get("price"),
                            "reason": r.get("reason"),
                        }
                        for r in records
                        if isinstance(r, dict)
                    ],
                )
                conn.commit()
                logger.info("Migrated %d trade_history records to SQLite", len(records))
            finally:
                conn.close()
        legacy.rename(legacy.with_suffix(".json.bak"))
    except Exception:
        logger.exception("trade_history migration failed")


# ── Signal History ────────────────────────────────────────────────────────────

def insert_signal(date: str, ticker: str, signal: str, score: Optional[float],
                  price_at_signal: Optional[float], strategy: str) -> None:
    init_db()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO signal_history
                   (date, ticker, signal, score, price_at_signal, strategy)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (date, ticker, signal, score, price_at_signal, strategy),
            )
            conn.commit()
        finally:
            conn.close()


def get_signal_history(limit: int = 2000, strategy: Optional[str] = None) -> List[Dict]:
    init_db()
    with _lock:
        conn = _connect()
        try:
            if strategy:
                rows = conn.execute(
                    "SELECT * FROM signal_history WHERE strategy=? ORDER BY date DESC, id DESC LIMIT ?",
                    (strategy, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM signal_history ORDER BY date DESC, id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_signal_history_for_ticker(ticker: str) -> List[Dict]:
    init_db()
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM signal_history WHERE ticker=? ORDER BY date ASC",
                (ticker,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── Alerts ────────────────────────────────────────────────────────────────────

def insert_alerts(alerts: List[Dict]) -> None:
    init_db()
    with _lock:
        conn = _connect()
        try:
            conn.executemany(
                """INSERT INTO alerts (timestamp, type, ticker, message, severity)
                   VALUES (:timestamp, :type, :ticker, :message, :severity)""",
                [
                    {
                        "timestamp": a.get("timestamp", datetime.now().isoformat()),
                        "type": a.get("type"),
                        "ticker": a.get("ticker"),
                        "message": a.get("message"),
                        "severity": a.get("severity", "info"),
                    }
                    for a in alerts
                ],
            )
            conn.commit()
        finally:
            conn.close()


def get_alerts(limit: int = 200, severity: Optional[str] = None,
               ticker: Optional[str] = None) -> List[Dict]:
    init_db()
    clauses, params = [], []
    if severity:
        clauses.append("severity=?"); params.append(severity)
    if ticker:
        clauses.append("ticker=?"); params.append(ticker)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM alerts {where} ORDER BY timestamp DESC LIMIT ?", params
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── Trade History ─────────────────────────────────────────────────────────────

def insert_trade(ticker: str, action: str, shares: Optional[float],
                 price: Optional[float], reason: Optional[str]) -> None:
    init_db()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO trade_history (timestamp, ticker, action, shares, price, reason)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (datetime.now().isoformat(), ticker, action, shares, price, reason),
            )
            conn.commit()
        finally:
            conn.close()


def get_trade_history(ticker: Optional[str] = None) -> List[Dict]:
    init_db()
    with _lock:
        conn = _connect()
        try:
            if ticker:
                rows = conn.execute(
                    "SELECT * FROM trade_history WHERE ticker=? ORDER BY timestamp DESC",
                    (ticker,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM trade_history ORDER BY timestamp DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
