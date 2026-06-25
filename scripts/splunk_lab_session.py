from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local Splunk session token for ImpactIQ.")
    parser.add_argument("--base-url", default="https://localhost:18089", help="Splunk management API base URL")
    parser.add_argument("--username", default="admin", help="Splunk username")
    parser.add_argument("--password", default="ImpactIQ-lab-12345", help="Splunk password")
    args = parser.parse_args()

    body = urllib.parse.urlencode(
        {
            "username": args.username,
            "password": args.password,
            "output_mode": "json",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/services/auth/login",
        data=body,
        method="POST",
    )
    context = None
    if args.base_url.startswith("https://localhost") or args.base_url.startswith("https://127.0.0.1"):
        import ssl

        context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=15, context=context) as response:
        payload = json.loads(response.read().decode("utf-8"))
    print(payload["sessionKey"])


if __name__ == "__main__":
    main()
