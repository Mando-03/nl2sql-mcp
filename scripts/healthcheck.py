"""Container healthcheck: verify HTTP /health endpoint.

Uses stdlib only. Exit code 0 indicates healthy.
"""

from __future__ import annotations

import json
import sys
from typing import Final
from urllib.request import Request, urlopen

URL: Final[str] = "http://127.0.0.1:8000/health"


def main() -> int:
    try:
        req = Request(URL, headers={"User-Agent": "nl2sql-mcp/healthcheck"})  # noqa: S310
        with urlopen(req, timeout=4) as resp:  # noqa: S310 - fixed host/http
            if resp.status != 200:
                print(f"unexpected status: {resp.status}", file=sys.stderr)
                return 1
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") != "healthy":
                print(f"payload not healthy: {data}", file=sys.stderr)
                return 1
            return 0
    except Exception as exc:
        print(f"healthcheck error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - used by Docker
    raise SystemExit(main())
