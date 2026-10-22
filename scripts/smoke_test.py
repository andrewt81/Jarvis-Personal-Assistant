from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def fetch_json(url: str) -> tuple[int, dict[str, object]]:
    try:
        with urlopen(url, timeout=5) as response:  # noqa: S310 - URL is operator supplied
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def main() -> int:
    base_url = os.environ.get("JARVIS_SMOKE_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    expected = {
        "/health/live": (200, "alive"),
        "/health/ready": (200, "ready"),
    }
    try:
        for path, (expected_status, expected_state) in expected.items():
            status, payload = fetch_json(f"{base_url}{path}")
            if status != expected_status or payload.get("status") != expected_state:
                print(f"Smoke test failed for {path}: HTTP {status}", file=sys.stderr)
                return 1
    except (URLError, TimeoutError, ValueError) as error:
        print(f"Smoke test failed: {type(error).__name__}", file=sys.stderr)
        return 1
    print("Jarvis backend smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
