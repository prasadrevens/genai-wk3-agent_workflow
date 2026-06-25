# Sprint 3 Validation - Local Splunk Enterprise Lab

## Status

Sprint 3 is complete as an optional local lab for the Sprint 2 Splunk Platform API connector.

## What Sprint 3 Added

- Local Splunk Enterprise Docker Compose lab.
- Dedicated `impactiq` Splunk index.
- Host ports that do not conflict with Mini Shop:
  - Splunk Web: `http://localhost:18000`
  - Splunk management API: `https://localhost:18089`
  - Splunk HEC: `https://localhost:18088`
- Mini Shop log/change seeding script.
- Splunk session token helper script.
- Documentation for using `AIOPS_DATA_SOURCE=splunk_api` with the local lab.

## What Was Preserved

- Mini Shop remains the default connector.
- React + FastAPI remains the supported demo path.
- `aiops_agent.py` behavior is unchanged.
- Mini Shop behavior is unchanged.
- React dashboard behavior is unchanged.
- Remediation approval behavior is unchanged.

## Lab Flow

```bash
cd splunk_lab
docker compose up -d
cd ..

python scripts/splunk_lab_seed.py
python scripts/splunk_lab_session.py
```

Then set:

```text
AIOPS_DATA_SOURCE=splunk_api
SPLUNK_BASE_URL=https://localhost:18089
SPLUNK_TOKEN=<printed-session-token>
SPLUNK_INDEX=impactiq
SPLUNK_VERIFY_SSL=false
SPLUNK_AUTH_SCHEME=Splunk
```

## Validation Commands

```bash
.venv/bin/python -m unittest tests.test_sentinel_api tests.test_connectors -v
.venv/bin/python -m compileall aiops_tools.py connectors scripts
cd sentinel-dashboard
npm run build
```

If Docker is available:

```bash
cd splunk_lab
docker compose config
```

## Acceptance Decision

Accepted for Sprint 3:

- Local Splunk lab scaffold exists.
- Splunk index configuration exists.
- Seed script sends Mini Shop logs and changes through HEC.
- Session script creates a Splunk management API session token for the connector.
- No LangGraph, Mini Shop, React, or remediation behavior changes were introduced.
