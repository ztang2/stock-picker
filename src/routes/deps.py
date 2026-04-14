"""Shared dependencies and utilities for API routers."""

import logging
import os
from typing import Optional

from fastapi import HTTPException, Header

logger = logging.getLogger(__name__)


def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Check API key for mutating endpoints. If no API_KEY in .env, skip auth (backward compatible)."""
    required_key = os.getenv("API_KEY")
    if required_key is None:
        # No API key configured, skip auth
        return
    if x_api_key != required_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# Import shared constants from pipeline
from ..pipeline import load_config, RESULTS_FILE, DATA_DIR

__all__ = [
    "verify_api_key",
    "load_config",
    "RESULTS_FILE",
    "DATA_DIR",
    "logger",
]
