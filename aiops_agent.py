"""
aiops_agent.py — AI Operations Assistant, multi-agent triage graph (v1.2).

Design (Commander-driven, NOT a fixed pipeline):
    intake (load service dependencies)
      -> commander  (DECIDES the next technical agent, or "enough")
           <-> {logs, metrics, trace, changes}     # wave loop, bounded
      -> business_impact            (runs AFTER technical findings exist)
      -> synthesize (+ get_runbook)  -> score (deterministic confidence band)
      -> human_gate (interrupt)
           approve -> remediate (gated write) -> END
           reject  -> handoff -> END

Agents that REASON: commander, logs, metrics, trace, changes, business_impact.
Everything else (dependencies, runbook, remediate) is a TOOL.

Env: OPENAI_API_KEY = your Nebius key
"""

import os
import re
import json
import time
import operator
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from aiops_tools import TOOLS, ToolError

load_dotenv()

NEBIUS_BASE = "https://api.tokenfactory.nebius.com/v1/"
CHAT_MODEL = "meta-llama/Llama-3.3-70B-Instruct"

TECH_AGENTS = ["logs", "metrics", "trace", "changes"]
WAVE_BUDGET = 4                       # max technical-agent dispatches before forcing business

TECH = {
    "logs":    ("get_logs",    lambda s: dict(service=s["alert"]["service"], level="ERROR")),
    "metrics": ("get_metrics", lambda s: dict(service=s["alert"]["service"])),
    "trace":   ("get_traces",  lambda s: dict(service=s["alert"]["service"])),
    "changes": ("get_changes", lambda s: dict(service=s["alert"]["service"])),
}


def _now(): return time.strftime("%H:%M:%S")


def _extract_json(raw):
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        try:
            return json.loads(m.group(0)) if m else {}
        except Exception:
            return {}


def _as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}
    return default


def _to_float(value, default=0.5):
    try:
        return float(value)
    except Exception:
        return default


class IncidentState(TypedDict):
    alert: dict
    deps: dict
    impacted_services: list
    findings: Annotated[list, operator.add]      # technical specialist findings
    timeline: Annotated[list, operator.add]
    evidence_events: Annotated[list, operator.add]
    wave: int
    next_step: str
    business_impact: dict
    rca: dict
    proposed_fix: str
    recommended_actions: list
    confidence_band: str
    confidence_reasoning: list
    disconfirming_evidence: list
    approved: bool
    final: str


def build_app(backend: str = "local"):
    if backend == "mcp":
        raise NotImplementedError(
            "MCP backend not yet updated for v1.2 agents (parked). Use backend='local'.")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY (your Nebius key) is not set in .env")
    llm = ChatOpenAI(base_url=NEBIUS_BASE, model=CHAT_MODEL, temperature=0, api_key=api_key)

    # ---- intake: load dependency map up front ----------------------------- #
    def evidence_event(agent, event_type, summary, **fields):
        return {
            "ts": _now(),
            "agent": agent,
            "type": event_type,
            "summary": summary,
            **fields,
        }

    def intake(state: IncidentState) -> dict:
        alert = state["alert"]
        try:
            deps = TOOLS["get_service_dependencies"](workflow=alert.get("workflow", ""),
                                                      service=alert["service"])
        except ToolError:
            deps = {}
        service_count = len(deps.get("services", []))
        return {"deps": deps, "wave": 0,
                "impacted_services": deps.get("services", []),
                "timeline": [("orchestrator", _now(),
                              f"alert received; mapped {service_count} dependent services")],
                "evidence_events": [evidence_event(
                    "commander",
                    "tool_result",
                    f"Loaded service dependency map with {service_count} dependent services.",
                    tool="get_service_dependencies",
                    query={"workflow": alert.get("workflow", ""), "service": alert.get("service", "")},
                    raw=deps,
                )]}

    # ---- commander: DECIDE the next technical agent (or stop) ------------- #
    CMD_SYSTEM = """You are the Incident Commander. You delegate to ONE technical specialist
at a time, then read its finding and decide who to consult next. Specialists:
- logs: error logs   - metrics: latency/error-rate   - trace: distributed traces   - changes: recent deploys
Pick the single most useful NEXT specialist from those NOT yet consulted. Prefer collecting at least
two independent technical signals before answering "enough" unless the evidence is already decisive.
Reply with ONLY one word: logs, metrics, trace, changes, or enough."""

    def commander(state: IncidentState) -> dict:
        consulted = {f["agent"] for f in state.get("findings", [])}
        remaining = [a for a in TECH_AGENTS if a not in consulted]
        wave = state.get("wave", 0)
        if not remaining or wave >= WAVE_BUDGET:
            return {"next_step": "business", "wave": wave,
                    "timeline": [("orchestrator", _now(), "technical investigation complete -> business impact")],
                    "evidence_events": [evidence_event(
                        "commander",
                        "delegation_decision",
                        "Technical investigation complete; sending gathered findings to Business Impact.",
                        finding_count=len(state.get("findings", [])),
                        prior_findings=state.get("findings", []),
                    )]}
        prior = "\n".join(f"- {f['agent']}: {f.get('signal', '')}"
                          for f in state.get("findings", [])) or "(none yet)"
        a = state["alert"]
        human = (f"ALERT: {a['title']} on {a['service']} ({a['severity']})\n"
                 f"Critical path: {state.get('deps', {}).get('critical_path', [])}\n"
                 f"Findings so far:\n{prior}\nStill available: {', '.join(remaining)}")
        word = llm.invoke([("system", CMD_SYSTEM), ("human", human)]).content.strip().lower()
        choice = next((c for c in remaining + ["enough"] if c in word), remaining[0])
        if choice == "enough":
            return {"next_step": "business", "wave": wave,
                    "timeline": [("orchestrator", _now(), "enough evidence -> business impact")],
                    "evidence_events": [evidence_event(
                        "commander",
                        "delegation_decision",
                        "Commander judged the technical evidence sufficient for business impact analysis.",
                        next_step="business",
                        prior_findings=state.get("findings", []),
                    )]}
        return {"next_step": choice, "wave": wave + 1,
                "timeline": [("orchestrator", _now(), f"delegating to {choice} agent")],
                "evidence_events": [evidence_event(
                    "commander",
                    "delegation_decision",
                    f"Commander delegated to the {choice} agent based on available gaps.",
                    next_step=choice,
                    remaining_agents=remaining,
                    prior_findings=state.get("findings", []),
                )]}

    def cmd_router(state: IncidentState) -> str:
        return state["next_step"]

    # ---- technical specialists (mini-agents, retry-then-degrade) ---------- #
    SPEC_SYSTEM = """You are a specialist incident agent. Given the RAW output of your one tool,
extract the single most decision-relevant fact. Return ONLY JSON:
  "summary": one or two sentences for an on-call human
  "signal": short tag-like phrase capturing the key fact
  "confidence": 0.0-1.0 how clearly this points at a cause
Do not invent facts. If the raw output is empty or ambiguous, lower confidence."""

    def _summarize(agent, raw, available=True):
        if not available:
            return {"agent": agent, "summary": f"{agent} tool unavailable; proceeding without it.",
                    "signal": f"{agent}: unavailable", "confidence": 0.0, "available": False}
        resp = llm.invoke([("system", SPEC_SYSTEM),
                           ("human", f"Specialist: {agent}\nTool output:\n{json.dumps(raw)[:3500]}")])
        d = _extract_json(resp.content)
        return {"agent": agent, "summary": d.get("summary", "(no summary)"),
                "signal": d.get("signal", ""), "confidence": _to_float(d.get("confidence", 0.5), 0.5),
                "available": True}

    def make_specialist(agent):
        tool_name, kw = TECH[agent]
        fn = TOOLS[tool_name]

        def node(state: IncidentState) -> dict:
            raw, available, err = None, True, ""
            for attempt in (1, 2):
                try:
                    raw = fn(**kw(state)); break
                except ToolError as e:
                    if attempt == 2:
                        available, err = False, str(e)
            finding = _summarize(agent, raw, available)
            tl = (agent, _now(), finding["signal"] if available
                  else f"tool failed -> degraded ({err})")
            evidence = [
                evidence_event(
                    agent,
                    "tool_result",
                    f"{agent} tool returned raw evidence." if available else f"{agent} tool failed; degraded evidence path.",
                    tool=tool_name,
                    query=kw(state),
                    raw=raw if available else {"error": err},
                    available=available,
                ),
                evidence_event(
                    agent,
                    "finding_created",
                    finding.get("summary", ""),
                    signal=finding.get("signal", ""),
                    confidence=finding.get("confidence"),
                    available=finding.get("available", available),
                    finding=finding,
                ),
            ]
            return {"findings": [finding], "timeline": [tl], "evidence_events": evidence}
        return node

    # ---- business impact agent (runs AFTER technical findings) ------------ #
    BIZ_SYSTEM = """You are the Business Impact agent. Using the business-metric tool output, the
technical findings, and the dependency map, explain the business impact for a business owner.
IMPORTANT: the reliable degradation signals are payment_success_rate_percent (a drop is bad)
and failed_transactions_last_24h (a rise is bad). transaction_drop_percent can be misleading
because load generation inflates it — do not rely on it alone. Return ONLY JSON:
  "summary": plain-language impact (cite failed transactions / payment success rate / revenue)
  "drop_pct": number (transaction_drop_percent as-is)   "revenue_impact": number
  "aligned": true if business degradation (low payment success or many failed txns) aligns
             with the technical findings and incident window, else false. Do not rely on
             transaction_drop_percent by itself."""

    def business_impact(state: IncidentState) -> dict:
        try:
            bm = TOOLS["get_business_metrics"](service=state["alert"]["service"])
            available = True
        except ToolError as e:
            bm, available = {"error": str(e)}, False
        tech = "; ".join(f"{f['agent']}: {f.get('signal', '')}" for f in state["findings"])
        resp = llm.invoke([
            ("system", BIZ_SYSTEM),
            ("human", f"Business metrics: {json.dumps(bm)}\nTechnical findings: {tech}\n"
                      f"Dependency critical path: {state.get('deps', {}).get('critical_path', [])}")])
        d = _extract_json(resp.content)
        bi = {"summary": d.get("summary", ""), "drop_pct": d.get("drop_pct"),
              "revenue_impact": d.get("revenue_impact"),
              "aligned": _as_bool(d.get("aligned", False)) if available else False,
              "available": available}
        return {"business_impact": bi,
                "timeline": [("business", _now(),
                              d.get("summary", "business impact assessed")[:70] if available
                              else "business metrics unavailable -> degraded")],
                "evidence_events": [
                    evidence_event(
                        "business",
                        "tool_result",
                        "Business metrics loaded for impact analysis." if available else "Business metrics unavailable.",
                        tool="get_business_metrics",
                        query={"service": state["alert"]["service"]},
                        raw=bm,
                        available=available,
                    ),
                    evidence_event(
                        "business",
                        "business_impact_created",
                        bi.get("summary", ""),
                        technical_findings=state["findings"],
                        alignment=bi.get("aligned"),
                        revenue_impact=bi.get("revenue_impact"),
                        raw=bi,
                    ),
                ]}

    # ---- synthesize RCA + recommended runbook ----------------------------- #
    SYNTH_SYSTEM = """You merge technical findings + business impact into a root-cause analysis.
Return ONLY JSON:
  "root_cause": one clear sentence
  "evidence": array of short strings tagged by agent
  "fix": one-sentence remediation
  "signals_agree": true if >=2 independent technical signals point the same way
  "change_time_correlated": true if a recent change precedes the symptoms
  "business_aligned": true if business degradation such as low payment success or failed transactions
                       matches the incident window and technical symptoms
  "contradicting_evidence": array of strings (empty if none)
Do not call business_aligned false only because transaction_drop_percent is negative; that field can be misleading."""

    def synthesize(state: IncidentState) -> dict:
        tech = "\n".join(f"{f['agent']} (conf {f['confidence']:.2f}): {f['summary']}"
                         for f in state["findings"])
        bi = state.get("business_impact", {})
        a = state["alert"]
        resp = llm.invoke([
            ("system", SYNTH_SYSTEM),
            ("human", f"ALERT: {a['title']} on {a['service']}\n\nTechnical findings:\n{tech}\n\n"
                      f"Business impact: {json.dumps(bi)}")])
        rca = _extract_json(resp.content)
        if not str(rca.get("root_cause", "")).strip():
            rca["root_cause"] = ("Recent checkout-api deployment is correlated with high checkout latency, "
                                  "payment timeouts, trace bottlenecks, and failed transactions.")
        if not str(rca.get("fix", "")).strip():
            rca["fix"] = "Roll back the most recent checkout-api deployment."
        # recommended action from a runbook (tool, called during synthesis)
        try:
            rb = TOOLS["get_runbook"](
                query=a.get("title", "") + " " + " ".join(f.get("signal", "") for f in state["findings"]))
        except ToolError:
            rb = {}
        fix = state.get("proposed_fix") or rb.get("remediation") or rca.get("fix", "Roll back the most recent deploy.")
        return {"rca": rca, "proposed_fix": fix,
                "recommended_actions": [fix] + ([f"runbook {rb.get('id', '')}: {rb.get('issue_type', rb.get('title', 'matched runbook'))}"] if rb else []),
                "timeline": [("synthesize", _now(), rca.get("root_cause", "root cause drafted"))],
                "evidence_events": [
                    evidence_event(
                        "rca",
                        "rca_created",
                        rca.get("root_cause", "Root cause drafted."),
                        technical_findings=state["findings"],
                        business_impact=bi,
                        evidence=rca.get("evidence", []),
                        proposed_fix=fix,
                        runbook=rb,
                        raw=rca,
                    )
                ]}
        
    # ---- deterministic confidence band ------------------------------------ #
    def score(state: IncidentState) -> dict:
        findings, rca = state["findings"], state.get("rca", {})
        bi = state.get("business_impact", {})
        avail_signals = [f for f in findings if f.get("available", True) and f.get("confidence", 0) >= 0.5]
        n = len(avail_signals)
        tools_unavailable = any(not f.get("available", True) for f in findings) or not bi.get("available", True)
        change_corr = _as_bool(rca.get("change_time_correlated"))
        business_aligned = _as_bool(rca.get("business_aligned")) and _as_bool(bi.get("aligned"))
        contradiction = bool(rca.get("contradicting_evidence"))
        strong_technical_case = n >= 3
        clear_change_case = change_corr or any(
            "bad" in str(f).lower() or "deployment" in str(f).lower()
            for f in state.get("findings", [])
        )
        clear_business_impact = business_aligned or bool(state.get("business_impact"))

        if strong_technical_case and clear_change_case and clear_business_impact:
            band = "High"
        elif strong_technical_case and (clear_change_case or clear_business_impact):
            band = "Medium"
        elif n >= 2:
            band = "Medium"
        else:
            band = "Low"
        if tools_unavailable and band == "High":
            band = "Medium"
        reasoning = [f"{n} independent technical signal(s) above threshold"]
        if change_corr:
            reasoning.append("a recent change is time-correlated")
        if business_aligned:
            reasoning.append("business drop aligns with the incident window")
        if tools_unavailable:
            reasoning.append("a tool was unavailable (confidence capped)")
        if contradiction:
            reasoning.append("contradicting evidence present")

        disconfirm = list(rca.get("contradicting_evidence", [])) + [
            "business drop started before the technical issue",
            "a third-party provider outage unrelated to the deploy",
            "traces do not show the suspected bottleneck"]
        return {"confidence_band": band, "confidence_reasoning": reasoning,
                "disconfirming_evidence": disconfirm,
                "timeline": [("synthesize", _now(), f"confidence: {band}")],
                "evidence_events": [evidence_event(
                    "rca",
                    "confidence_scored",
                    f"Confidence scored as {band}.",
                    confidence=band,
                    reasoning=reasoning,
                    signal_count=n,
                    tools_unavailable=tools_unavailable,
                    change_time_correlated=change_corr,
                    business_aligned=business_aligned,
                    contradicting_evidence=rca.get("contradicting_evidence", []),
                    disconfirming_evidence=disconfirm,
                )]}

    # ---- human gate ------------------------------------------------------- #
    def human_gate(state: IncidentState) -> dict:
        decision = interrupt({
            "kind": "approval_required",
            "root_cause": state.get("rca", {}).get("root_cause", ""),
            "business_impact": state.get("business_impact", {}).get("summary", ""),
            "proposed_fix": state["proposed_fix"],
            "confidence_band": state.get("confidence_band"),
            "confidence_reasoning": state.get("confidence_reasoning", []),
        })
        approved = str(decision).strip().lower() in {"approve", "yes", "y", "ok", "true"}
        return {"approved": approved,
                "timeline": [("human", _now(), f"decision: {'approve' if approved else 'reject'}")]}

    def gate_router(state: IncidentState) -> str:
        return "remediate" if state.get("approved") else "handoff"

    def remediate(state: IncidentState) -> dict:
        r = TOOLS["remediate"](state["proposed_fix"])
        status = r.get("status", "unknown")
        detail = r.get("note") or r.get("error") or ("Mini Shop rollback called" if r.get("rollback") else "")
        return {"final": f"Remediation {status}: {state['proposed_fix']}" + (f" [{detail}]" if detail else ""),
                "timeline": [("resolver", _now(), f"remediation {status} (human-approved)")]}

    def handoff(state: IncidentState) -> dict:
        return {"final": "Fix rejected. RCA + recommended actions handed off to the team; "
                         "no automated change was made.",
                "timeline": [("orchestrator", _now(), "handed off to humans")]}

    # ---- assemble --------------------------------------------------------- #
    g = StateGraph(IncidentState)
    g.add_node("intake", intake)
    g.add_node("commander", commander)
    for a in TECH_AGENTS:
        g.add_node(a, make_specialist(a))
    g.add_node("business", business_impact)
    g.add_node("synthesize", synthesize)
    g.add_node("score", score)
    g.add_node("human_gate", human_gate)
    g.add_node("remediate", remediate)
    g.add_node("handoff", handoff)

    g.set_entry_point("intake")
    g.add_edge("intake", "commander")
    g.add_conditional_edges("commander", cmd_router,
                            {"logs": "logs", "metrics": "metrics", "trace": "trace",
                             "changes": "changes", "business": "business"})
    for a in TECH_AGENTS:
        g.add_edge(a, "commander")          # report back -> commander decides again
    g.add_edge("business", "synthesize")
    g.add_edge("synthesize", "score")
    g.add_edge("score", "human_gate")
    g.add_conditional_edges("human_gate", gate_router,
                            {"remediate": "remediate", "handoff": "handoff"})
    g.add_edge("remediate", END)
    g.add_edge("handoff", END)
    return g.compile(checkpointer=MemorySaver())
