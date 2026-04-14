"""Centralized access to scan results — SQLite backend with JSON file fallback."""
import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_FILE = DATA_DIR / "scan_results.json"
PREV_RESULTS_FILE = DATA_DIR / "prev_scan_results.json"
DB_FILE = DATA_DIR / "scan_results.db"


class ScanResultsService:
    """Single point of access for scan results. SQLite backend with in-memory caching."""

    _cache: Optional[dict] = None
    _cache_timestamp: Optional[str] = None
    _db_lock = threading.Lock()

    @classmethod
    def _get_db_connection(cls):
        """Get SQLite connection with thread-safety enabled."""
        return sqlite3.connect(str(DB_FILE), check_same_thread=False)

    @classmethod
    def _ensure_db_initialized(cls):
        """Initialize database and migrate from JSON if needed."""
        if DB_FILE.exists():
            return

        DATA_DIR.mkdir(exist_ok=True)

        with cls._db_lock:
            # Double-check after acquiring lock
            if DB_FILE.exists():
                return

            try:
                # Create table
                conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS scan_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        data TEXT,
                        created_at TEXT
                    )
                """)
                conn.commit()

                # Migrate from JSON file if it exists
                if RESULTS_FILE.exists():
                    try:
                        json_data = json.loads(RESULTS_FILE.read_text())
                        timestamp = json_data.get("timestamp", datetime.now().isoformat())
                        json_str = json.dumps(json_data, default=str)
                        created_at = datetime.now().isoformat()
                        cursor.execute(
                            "INSERT INTO scan_results (timestamp, data, created_at) VALUES (?, ?, ?)",
                            (timestamp, json_str, created_at),
                        )
                        conn.commit()
                        logger.info("Migrated existing scan_results.json to SQLite")
                    except Exception as e:
                        logger.error(f"Failed to migrate JSON data: {e}")

                conn.close()
            except Exception as e:
                logger.error(f"Failed to initialize scan_results database: {e}")
                raise

    @classmethod
    def get_latest(cls) -> Optional[dict]:
        """Get full scan results dict, with in-memory caching."""
        cls._ensure_db_initialized()

        try:
            with cls._db_lock:
                conn = cls._get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT timestamp, data FROM scan_results ORDER BY id DESC LIMIT 1"
                )
                row = cursor.fetchone()
                conn.close()

            if not row:
                return None

            db_timestamp = row[0]

            # Check cache validity: refresh if database has newer timestamp
            if cls._cache is None or cls._cache_timestamp != db_timestamp:
                cls._cache = json.loads(row[1])
                cls._cache_timestamp = db_timestamp

            return cls._cache
        except Exception as e:
            logger.error(f"Error reading from scan_results database: {e}")
            return None

    @classmethod
    def get_top_stocks(cls) -> List[dict]:
        """Get top-ranked stocks from latest scan."""
        data = cls.get_latest()
        if not data:
            return []
        return data.get("top", data.get("stocks", []))

    @classmethod
    def get_all_scores(cls) -> List[dict]:
        """Get all scored stocks from latest scan."""
        data = cls.get_latest()
        if not data:
            return []
        return data.get("all_scores", [])

    @classmethod
    def get_stock_score(cls, ticker: str) -> Optional[dict]:
        """Get score data for a specific ticker."""
        for stock in cls.get_all_scores():
            if stock.get("ticker") == ticker:
                return stock
        return None

    @classmethod
    def get_by_sector(cls, sector: str) -> List[dict]:
        """Get all scores filtered by sector."""
        return [s for s in cls.get_all_scores() if s.get("sector", "").lower() == sector.lower()]

    @classmethod
    def get_timestamp(cls) -> Optional[str]:
        """Get timestamp of latest scan."""
        data = cls.get_latest()
        return data.get("timestamp") if data else None

    @classmethod
    def invalidate_cache(cls):
        """Force cache refresh on next access."""
        cls._cache = None
        cls._cache_timestamp = None

    @classmethod
    def save_results(cls, output: dict):
        """Save scan results to SQLite and invalidate cache."""
        cls._ensure_db_initialized()

        try:
            with cls._db_lock:
                conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
                cursor = conn.cursor()

                timestamp = output.get("timestamp", datetime.now().isoformat())
                json_str = json.dumps(output, default=str)
                created_at = datetime.now().isoformat()

                cursor.execute(
                    "INSERT INTO scan_results (timestamp, data, created_at) VALUES (?, ?, ?)",
                    (timestamp, json_str, created_at),
                )
                conn.commit()
                conn.close()

                logger.debug(f"Saved scan results to SQLite with timestamp {timestamp}")
        except Exception as e:
            logger.error(f"Error saving to scan_results database: {e}")
            raise

        cls.invalidate_cache()

    @classmethod
    def rotate_results(cls):
        """Keep only last 10 entries in the database; maintain JSON file as backup."""
        cls._ensure_db_initialized()

        try:
            with cls._db_lock:
                conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
                cursor = conn.cursor()

                # Get the ID of the 10th most recent entry
                cursor.execute(
                    "SELECT id FROM scan_results ORDER BY id DESC LIMIT 1 OFFSET 9"
                )
                row = cursor.fetchone()

                if row:
                    cutoff_id = row[0]
                    cursor.execute("DELETE FROM scan_results WHERE id < ?", (cutoff_id,))
                    conn.commit()
                    logger.debug(f"Rotated scan_results database, keeping last 10 entries")

                conn.close()
        except Exception as e:
            logger.error(f"Error rotating scan_results database: {e}")
            raise
