# ImpactIQ Local Splunk Enterprise Lab

Sprint 3 adds a local Splunk Enterprise lab for validating the Sprint 2 `SplunkApiConnector`.

The lab is optional. Mini Shop remains the default supported demo path unless you set:

```text
AIOPS_DATA_SOURCE=splunk_api
```

## Ports

Mini Shop already uses port `8000`, so the lab maps Splunk to non-conflicting host ports:

| Service | URL |
|---|---|
| Splunk Web | `http://localhost:18000` |
| Splunk management API | `https://localhost:18089` |
| Splunk HEC | `https://localhost:18088` |

Default lab login:

```text
username: admin
password: ImpactIQ-lab-12345
```

## Start Splunk

On Apple Silicon Macs, Docker runs the Splunk Enterprise image with `linux/amd64`
emulation because Splunk does not publish this image as native `arm64`.

```bash
cd splunk_lab
docker compose up -d
cd ..
```

Wait until Splunk Web opens at:

```text
http://localhost:18000
```

## Seed Mini Shop Logs And Changes

Run the Mini Shop demo flow first so `mini_shop_with_ui/data/logs.json` and `changes.json` exist.

Then seed those files into Splunk HEC. The seed script creates the `impactiq`
index through the Splunk management API, so the Docker container does not need
any host-file bind mounts.

```bash
python scripts/splunk_lab_seed.py
```

The script writes events into:

```text
index=impactiq
sourcetype=impactiq:logs
sourcetype=impactiq:changes
```

## Create A Splunk Session Token

The connector uses Splunk's management API search export endpoint. For the local lab, generate a session token:

```bash
python scripts/splunk_lab_session.py
```

Copy the printed token into `.env`:

```text
AIOPS_DATA_SOURCE=splunk_api
SPLUNK_BASE_URL=https://localhost:18089
SPLUNK_TOKEN=<printed-session-token>
SPLUNK_INDEX=impactiq
SPLUNK_VERIFY_SSL=false
SPLUNK_TIMEOUT_SECONDS=10
SPLUNK_AUTH_SCHEME=Splunk
```

## Validate Connector Queries

Logs:

```bash
AIOPS_DATA_SOURCE=splunk_api \
SPLUNK_BASE_URL=https://localhost:18089 \
SPLUNK_TOKEN=<printed-session-token> \
SPLUNK_INDEX=impactiq \
SPLUNK_VERIFY_SSL=false \
.venv/bin/python -c 'from aiops_tools import get_logs; print(get_logs(service="checkout-api"))'
```

Changes:

```bash
AIOPS_DATA_SOURCE=splunk_api \
SPLUNK_BASE_URL=https://localhost:18089 \
SPLUNK_TOKEN=<printed-session-token> \
SPLUNK_INDEX=impactiq \
SPLUNK_VERIFY_SSL=false \
.venv/bin/python -c 'from aiops_tools import get_changes; print(get_changes(service="checkout-api"))'
```

## Sprint 3 Scope

Included:

- Local Splunk Enterprise Docker Compose lab.
- Dedicated `impactiq` index.
- HEC seeding of Mini Shop logs and changes.
- Session token helper for the Sprint 2 connector.
- Documentation for switching the tool layer to `AIOPS_DATA_SOURCE=splunk_api`.

Not included:

- Splunk Observability Cloud.
- Metrics or traces in Splunk.
- Hybrid connector routing.
- Changes to LangGraph agent behavior.
- Changes to Mini Shop.
- Changes to React dashboard behavior.
- Changes to approval or remediation behavior.
