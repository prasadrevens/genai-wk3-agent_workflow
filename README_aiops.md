# AIOps multi-agent triage — Week 3 project

A LangGraph **supervisor** system: an orchestrator delegates to four specialist
agents to triage an incident, synthesizes a root-cause brief, and gates any
remediation behind human approval. Demoed on a synthetic, Splunk-shaped incident
(a bad deploy → embedding-API 429s → latency spike on your RAG bot's `generate` node).

## Files
| File | Role |
|---|---|
| `aiops_scenarios.py` | generates the incident fixtures (logs, metrics, deploys, runbooks, alert) |
| `aiops_tools.py` | the 5 tools the agents call; reads fixtures, supports failure injection |
| `aiops_agent.py` | the multi-agent graph (`build_app()`) |
| `run_incident.py` | CLI harness: streams the timeline, pauses at the human gate |
| `aiops_logging.py` | writes the step-by-step runtime trace to `logs/aiops_triage.log` |

## Setup
Same `.venv` as Week 2 (Python 3.12). In a `.env` next to these files:
```
OPENAI_API_KEY=<your Nebius key>
```
```
pip install langgraph langchain-openai langchain-core python-dotenv
python aiops_scenarios.py        # write fixtures (once)
python run_incident.py           # run the incident
```
Runtime trace:
```
cat logs/aiops_triage.log
```
Demo graceful degradation (a tool "fails", the agent degrades instead of crashing):
```
AIOPS_FAIL=metrics python run_incident.py
cat logs/aiops_triage.log
```

## How it maps to the 10 requirements
- **Decides what to do next** — `orchestrator` picks the next specialist each turn.
- **Calls tools** — 4 read tools + 1 gated write (`aiops_tools.py`).
- **Agent-to-agent** — supervisor delegate → specialist → report back loop.
- **Holds state** — `IncidentState` + `MemorySaver`; `findings`/`timeline` accumulate via `operator.add`.
- **Recovers from errors** — each specialist retries once, then degrades and lowers confidence.
- **Hands off to a human** — `human_gate` uses `interrupt()`.
- **Autonomous vs human boundary** — reads run free; `remediate` (the write) only runs after approval.
- **End-to-end** — alert in → RCA + outcome out.

## Runtime log
The project now writes a human-readable execution trace to `logs/aiops_triage.log`.
This is the "what happened in the background" log for demos. It records fixture
generation, alert loading, orchestrator decisions, specialist tool calls, retries,
graceful degradation, RCA synthesis, the human approval gate, and the final
remediation or handoff outcome.

This file is separate from `incident_data/logs.jsonl`. The `incident_data` file
is synthetic application evidence that the logs agent investigates; `logs/aiops_triage.log`
is the operational trace of the agentic workflow itself.

## Friday build order (de-risk in this sequence)
1. Run it as-is with **logs + metrics only** consulted (the orchestrator will
   naturally do this if you trim `ORDER` to `["logs","metrics","resolver"]`).
   Prove delegate → report → synthesize → gate works.
2. Prove the failure path: `AIOPS_FAIL=metrics`.
3. Add `changes` back into `ORDER`. Re-run.
4. Only then think about the UI (Streamlit or the custom dashboard).

## Notes / honest gaps
- Each specialist is "ReAct-lite": one tool call + an LLM summary. To make it a
  full ReAct loop (specialist re-queries on its own), swap the node body for
  `langgraph.prebuilt.create_react_agent` — drop-in, same report shape.
- The tool/metric *shapes* match Splunk output, so "go live" later is just
  swapping each tool body from "read file" to "run a Splunk search".
- LLM-driven nodes need your Nebius key to run; the graph structure, tools, and
  fixtures are verified.
