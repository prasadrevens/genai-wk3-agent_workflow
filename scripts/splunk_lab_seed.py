from __future__ import annotations

import argparse
import base64
import json
import ssl
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed local Splunk with Mini Shop logs and change events.")
    parser.add_argument("--data-dir", default="mini_shop_with_ui/data", help="Mini Shop telemetry data directory")
    parser.add_argument("--hec-url", default="https://localhost:18088/services/collector/event", help="Splunk HEC URL")
    parser.add_argument("--hec-token", default="impactiq-hec-token", help="Splunk HEC token")
    parser.add_argument("--index", default="impactiq", help="Splunk index")
    parser.add_argument("--management-url", default="https://localhost:18089", help="Splunk management API URL")
    parser.add_argument("--username", default="admin", help="Splunk admin username")
    parser.add_argument("--password", default="ImpactIQ-lab-12345", help="Splunk admin password")
    args = parser.parse_args()

    _ensure_index(args.management_url, args.username, args.password, args.index)
    data_dir = Path(args.data_dir)
    logs = _load_json(data_dir / "logs.json", default=[])
    changes = _load_json(data_dir / "changes.json", default=[])
    events = [
        *_to_hec_events(logs, index=args.index, sourcetype="impactiq:logs", source="minishop:logs"),
        *_to_hec_events(changes, index=args.index, sourcetype="impactiq:changes", source="minishop:changes"),
    ]
    for event in events:
        _post_hec(args.hec_url, args.hec_token, event)
    print(f"Seeded {len(events)} event(s) into Splunk index={args.index}")


def _ensure_index(management_url: str, username: str, password: str, index: str) -> None:
    body = urllib.parse.urlencode({"name": index, "output_mode": "json"}).encode("utf-8")
    credentials = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        f"{management_url.rstrip('/')}/services/data/indexes",
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    context = None
    if management_url.startswith("https://localhost") or management_url.startswith("https://127.0.0.1"):
        context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            return
        raise SystemExit(f"Could not create Splunk index {index!r}: HTTP {exc.code} {exc.reason}") from exc
    except OSError as exc:
        raise SystemExit(f"Could not reach Splunk management API at {management_url}: {exc}") from exc


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        raise SystemExit(f"{path} not found. Run the Mini Shop demo flow before seeding Splunk.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} contains invalid JSON: {exc}") from exc


def _to_hec_events(rows: Iterable[Dict[str, Any]], index: str, sourcetype: str, source: str) -> List[Dict[str, Any]]:
    events = []
    for row in rows:
        event = dict(row)
        events.append(
            {
                "index": index,
                "sourcetype": sourcetype,
                "source": source,
                "event": event,
                "fields": {
                    "service": event.get("service"),
                    "level": event.get("level"),
                    "change_type": event.get("change_type"),
                    "error_type": event.get("error_type"),
                },
            }
        )
    return events


def _post_hec(url: str, token: str, event: Dict[str, Any]) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(event).encode("utf-8"),
        headers={
            "Authorization": f"Splunk {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    context = None
    if url.startswith("https://localhost") or url.startswith("https://127.0.0.1"):
        context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=15, context=context) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Splunk HEC HTTP {exc.code}: {exc.reason}") from exc
    except OSError as exc:
        raise SystemExit(f"Could not reach Splunk HEC at {url}: {exc}") from exc


if __name__ == "__main__":
    main()
