"""Discord webhook poster — stdlib only, no requests dependency.

Reads DISCORD_WEBHOOK_URL from environment (or .env). Posts plain text or
markdown content. Discord limits content to 2000 chars per message; longer
messages are split on line boundaries.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional
from urllib import request, error

DISCORD_MAX_CHARS = 2000
ENV_VAR = "DISCORD_WEBHOOK_URL"


def _load_dotenv() -> None:
    """Load .env from project root if DISCORD_WEBHOOK_URL not already set."""
    if os.getenv(ENV_VAR):
        return
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and v and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


def _split_for_discord(content: str) -> list[str]:
    """Split content into <=2000 char chunks on line boundaries."""
    if len(content) <= DISCORD_MAX_CHARS:
        return [content]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in content.splitlines(keepends=True):
        if current_len + len(line) > DISCORD_MAX_CHARS and current:
            chunks.append("".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def post_message(content: str, webhook_url: Optional[str] = None, username: Optional[str] = None) -> bool:
    """Post a message to Discord. Returns True on success.

    Splits long messages automatically. Logs errors to stderr but does not raise.
    """
    _load_dotenv()
    url = webhook_url or os.getenv(ENV_VAR)
    if not url:
        print(f"ERROR: {ENV_VAR} not set in env or .env", file=sys.stderr)
        return False
    if not content.strip():
        print("ERROR: empty content; nothing to post", file=sys.stderr)
        return False

    chunks = _split_for_discord(content)
    ok = True
    for i, chunk in enumerate(chunks):
        payload: dict = {"content": chunk}
        if username:
            payload["username"] = username
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "stock-picker-briefing/1.0 (+local)",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=10) as resp:
                if resp.status >= 300:
                    print(f"ERROR: Discord returned {resp.status}", file=sys.stderr)
                    ok = False
        except error.HTTPError as e:
            print(f"ERROR: Discord HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}", file=sys.stderr)
            ok = False
        except Exception as e:
            print(f"ERROR: Discord post failed: {e}", file=sys.stderr)
            ok = False
        if i < len(chunks) - 1:
            time.sleep(0.5)  # avoid Discord rate limit on multi-chunk
    return ok


if __name__ == "__main__":
    # CLI: echo to stdin → post to Discord. Useful for ad-hoc testing.
    msg = sys.stdin.read()
    if not msg.strip():
        print("Usage: echo 'message' | python3 -m src.discord_notify", file=sys.stderr)
        sys.exit(1)
    sys.exit(0 if post_message(msg) else 1)
