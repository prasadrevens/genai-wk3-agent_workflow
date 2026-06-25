import React, { useCallback, useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_SENTINEL_API_BASE ?? "http://localhost:8000";
const STAGES = ["commander", "metrics", "logs", "trace", "changes", "business", "rca"];
const STAGE_LABELS = {
  commander: "Commander",
  metrics: "Metrics",
  logs: "Logs",
  trace: "Trace",
  changes: "Changes",
  business: "Business",
  rca: "RCA",
};
const AGENT_META = {
  commander: { label: "Commander", icon: "⊙" },
  metrics: { label: "Metrics", icon: "📈" },
  logs: { label: "Logs", icon: "📄" },
  trace: { label: "Trace", icon: "🔎" },
  changes: { label: "Changes", icon: "🔧" },
  business: { label: "Business", icon: "💰" },
  rca: { label: "RCA", icon: "🎯" },
};
const VOICE_COMMANDS = [
  "What is the incident status?",
  "What is the root cause?",
  "What is the business impact?",
  "What is the confidence?",
  "What is the recommendation?",
  "Is approval ready?",
];

const initialPipeline = () =>
  Object.fromEntries(STAGES.map((stage) => [stage, "pending"]));

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
    ...options,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.detail || data.message || `Request failed: ${response.status}`);
  }
  return data;
}

function money(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(
    Number(value || 0),
  );
}

function pct(value) {
  return `${clamp(value).toFixed(1)}%`;
}

function dateTime(value) {
  const parsed = value ? new Date(value) : new Date();
  if (Number.isNaN(parsed.getTime())) return new Date().toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  return parsed.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function clamp(value) {
  return Math.max(0, Math.min(100, Number(value || 0)));
}

export function answer_voice_question(question, incident_state) {
  const normalized = question.trim().toLowerCase();
  const incident = incident_state.incident;
  const rca = incident_state.rca;
  const approvalStatus = incident_state.confirmationRequired
    ? "Approval is recorded, but rollback still requires the explicit second confirmation gate."
    : incident_state.decisionReady
      ? "Approval controls are available. Any change must still be made through the gated UI controls."
      : "Approval is not available yet. Triage must reach the human approval gate first.";

  // TODO: ELEVENLABS_API_KEY integration belongs in a future voice I/O layer.
  // Phase 2 intentionally returns text only and never triggers remediation.
  if (!normalized) return "Enter a voice transcript to ask about the current incident.";
  if (normalized.includes("status") || normalized.includes("healthy") || normalized.includes("degraded")) {
    if (!incident) return "Incident telemetry is still loading.";
    return `The incident is currently ${incident.status} with ${incident.severity} severity and ${incident.confidence} confidence.`;
  }
  if (normalized.includes("root") || normalized.includes("cause") || normalized.includes("rca")) {
    return rca?.root_cause || "Root cause is not available yet. Run triage to synthesize RCA.";
  }
  if (normalized.includes("business") || normalized.includes("impact") || normalized.includes("revenue")) {
    return rca?.business_impact || "Business impact is not available yet.";
  }
  if (normalized.includes("confidence")) {
    return rca?.confidence
      ? `The RCA confidence is ${rca.confidence}.`
      : "Confidence is not available yet.";
  }
  if (normalized.includes("recommend") || normalized.includes("action") || normalized.includes("fix")) {
    return rca?.gated_action
      ? `Recommended action: ${rca.gated_action} This remains gated through the existing approval controls.`
      : "No recommendation is available yet.";
  }
  if (normalized.includes("approval") || normalized.includes("approve") || normalized.includes("reject") || normalized.includes("rollback")) {
    return approvalStatus;
  }
  return "I can answer questions about incident status, root cause, business impact, confidence, recommendation, and approval status.";
}

function ErrorNotice({ message, onDismiss }) {
  if (!message) return null;
  return (
    <div className="error">
      <span>{message}</span>
      <button type="button" onClick={onDismiss} aria-label="Dismiss error">
        ×
      </button>
    </div>
  );
}

function Skeleton({ lines = 3 }) {
  return (
    <div className="skeleton" aria-label="Loading">
      {Array.from({ length: lines }).map((_, index) => (
        <i key={index} />
      ))}
    </div>
  );
}

function TopBar({ view, setView, theme, setTheme }) {
  return (
    <div className="topbar">
      <div className="brand">
        <div className="shield">🛡️</div>
        <div>
          <h1>ImpactIQ</h1>
          <p>Business-Aware AIOps</p>
        </div>
      </div>
      <ViewToggle view={view} setView={setView} />
      <ThemeToggle theme={theme} setTheme={setTheme} />
    </div>
  );
}

function ViewToggle({ view, setView }) {
  return (
    <div className="seg" role="group" aria-label="Audience view">
      <button type="button" aria-pressed={view === "exec"} onClick={() => setView("exec")}>
        👔 Executive
      </button>
      <button type="button" aria-pressed={view === "eng"} onClick={() => setView("eng")}>
        🛠️ Engineer
      </button>
    </div>
  );
}

function ThemeToggle({ theme, setTheme }) {
  return (
    <div className="seg" role="group" aria-label="Theme">
      <button type="button" aria-pressed={theme === "light"} onClick={() => setTheme("light")}>
        ☀️ Light
      </button>
      <button type="button" aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}>
        🌙 Dark
      </button>
    </div>
  );
}

function IncidentBanner({ incident, loading }) {
  if (loading || !incident) return <Skeleton lines={2} />;
  return (
    <div className="banner">
      <span className={`chip ${incident.severity === "critical" ? "crit" : "ok"}`}>● {incident.severity}</span>
      <span className="chip ok">✓ Confidence: {incident.confidence}</span>
      <div className="title">
        {incident.title} <span className="muted">· service</span> <code>{incident.service}</code>{" "}
        <span className="muted">· workflow</span> <code>{incident.workflow}</code>
      </div>
      <div className="meta-row">
        <span>
          Mini Shop: <code>{incident.mini_shop_url ?? API_BASE}</code>
        </span>
        <span>
          Alert received: <span className="path">{dateTime(incident.alert_received_at)}</span>
        </span>
      </div>
    </div>
  );
}

function ActionBar({ runState, onRun, children }) {
  return (
    <div className="actions">
      <button type="button" className="btn primary" disabled={runState === "running"} onClick={onRun}>
        ▶ {runState === "running" ? "Running triage" : "Run triage"}
      </button>
      {children}
    </div>
  );
}

function LiveTelemetryStatus({ lastChecked, polling, error }) {
  const label = lastChecked
    ? `Last checked ${lastChecked.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`
    : "Waiting for first check";

  return (
    <div className="live-telemetry" aria-live="polite">
      <span className={`live-dot ${error ? "error" : polling ? "polling" : ""}`} />
      <span>Live telemetry</span>
      <span className="muted">{error ? "polling error" : label}</span>
    </div>
  );
}

function VoiceIncidentCommander({
  incident,
  rca,
  runState,
  decisionReady,
  confirmationRequired,
  statusMessage,
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("Ask a question or choose a suggested command.");
  const [voiceStatus, setVoiceStatus] = useState(null);
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    let cancelled = false;
    request("/api/voice/status")
      .then((status) => {
        if (!cancelled) setVoiceStatus(status);
      })
      .catch(() => {
        if (!cancelled) setVoiceStatus({ audio_enabled: false, provider: "local" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const ask = async (nextQuestion = question) => {
    const incidentState = {
      incident,
      rca,
      runState,
      decisionReady,
      confirmationRequired,
      statusMessage,
    };
    setQuestion(nextQuestion);
    setAsking(true);
    try {
      const data = await request("/api/voice/ask", {
        method: "POST",
        body: JSON.stringify({ question: nextQuestion, include_audio: false }),
      });
      setAnswer(data.answer);
    } catch {
      setAnswer(answer_voice_question(nextQuestion, incidentState));
    } finally {
      setAsking(false);
    }
  };

  const badge = voiceStatus?.audio_enabled ? "ElevenLabs ready" : "Text mode";

  return (
    <section className="panel voice-panel" aria-labelledby="voice-commander-title">
      <div className="voice-head">
        <div>
          <h2 id="voice-commander-title">
            <span className="ico">🎙️</span> Voice Incident Commander
          </h2>
          <p>Simulated transcript with backend voice guardrails.</p>
        </div>
        <span className="voice-badge">{badge}</span>
      </div>
      <div className="voice-commands" aria-label="Suggested voice commands">
        {VOICE_COMMANDS.map((command) => (
          <button type="button" key={command} onClick={() => ask(command)}>
            {command}
          </button>
        ))}
      </div>
      <form
        className="voice-input-row"
        onSubmit={(event) => {
          event.preventDefault();
          ask();
        }}
      >
        <label htmlFor="voice-transcript">Voice transcript</label>
        <input
          id="voice-transcript"
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask about status, RCA, impact, confidence, recommendation, or approval"
        />
        <button type="submit" className="btn primary" disabled={asking}>
          {asking ? "Asking" : "Ask"}
        </button>
      </form>
      <div className="voice-answer" aria-live="polite">
        {answer}
      </div>
    </section>
  );
}

function KpiGrid({ incident, loading }) {
  if (loading || !incident) return <Skeleton lines={4} />;
  const kpis = incident.kpis;
  const failPct = kpis.total_transactions ? (kpis.failed_transactions / kpis.total_transactions) * 100 : 0;
  const statusTone = incident.status === "healthy" ? "ok" : "crit";
  return (
    <div className="kpis">
      <KpiCard
        critical={statusTone === "crit"}
        label="Incident Status"
        value={incident.status}
        sub={`Severity: ${incident.severity}`}
        tag={incident.severity}
        tone={statusTone}
      />
      <KpiCard
        label="Payment Success"
        value={pct(kpis.payment_success_pct)}
        sub="Mini Shop checkout"
        bar={kpis.payment_success_pct}
        tone={kpis.payment_success_pct < 95 ? "crit" : "ok"}
      />
      <KpiCard
        label="Failed Transactions"
        value={kpis.failed_transactions}
        sub={`of ${kpis.total_transactions} in last 24 hours`}
        bar={failPct}
        tone="warn"
      />
      <KpiCard
        label="Revenue Impact"
        value={money(kpis.estimated_impact)}
        sub={`Revenue last 24h: ${money(kpis.revenue_24h)}`}
        tag="Est."
        tone="accent"
      />
    </div>
  );
}

function KpiCard({ label, value, sub, tag, bar, tone = "crit", critical = false }) {
  return (
    <div className={`kpi ${critical ? "crit" : ""}`}>
      <div className="label">{label}</div>
      <div className="value" data-tone={tone}>
        {value}
      </div>
      <div className="sub">{sub}</div>
      {tag && (
        <span className="tag" data-tone={tone}>
          {tag}
        </span>
      )}
      {bar !== undefined && (
        <div className="bar">
          <i style={{ width: `${clamp(bar)}%` }} data-tone={tone} />
        </div>
      )}
    </div>
  );
}

function AgentNode({ id, label, status, variant = "" }) {
  return (
    <div className={`agent-node agent-card ${variant} ${status ?? "pending"}`} data-agent={id}>
      {id === "rca" ? (
        <span className="rca-icon" aria-hidden="true">
          <span className="rca-lines">
            <i />
            <i />
            <i />
          </span>
          <span className="rca-core" />
          <span className="rca-arrow">→</span>
        </span>
      ) : (
        <span className="bot-icon" aria-hidden="true">
          <span className="bot-ear left" />
          <span className="bot-ear right" />
          <span className="bot-head">
            <span className="bot-face">
              <i />
              <i />
            </span>
          </span>
          <span className="bot-shadow" />
        </span>
      )}
      <span className="agent-label">{label}</span>
    </div>
  );
}

function AgentPipeline({ pipeline }) {
  const specialists = [
    ["metrics", "📈", "Metrics"],
    ["logs", "📄", "Logs"],
    ["trace", "🔎", "Traces"],
    ["changes", "🔧", "Changes"],
  ];

  return (
    <div className="panel pipeline-wrap">
      <h2>
        <span className="ico">🤖</span> Agent workflow
      </h2>
      <div className="agent-map-subtitle">Commander-led supervisor pattern</div>
      <div className="agent-map" aria-label="Commander-led agent workflow map">
        <div className="specialist-stack" aria-label="Specialist agents">
          {specialists.map(([stage, , label]) => (
            <AgentNode
              id={stage}
              label={label}
              status={pipeline[stage]}
              variant="specialist-card"
              key={stage}
            />
          ))}
        </div>
        <div className="feed-bundle" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
        </div>
        <AgentNode id="commander" label={STAGE_LABELS.commander} status={pipeline.commander} variant="workflow-card commander" />
        <div className="evidence-flow" aria-hidden="true">
          <i />
        </div>
        <div className="decision-chain">
          <AgentNode id="business" label="Business Impact" status={pipeline.business} variant="workflow-card analysis business" />
          <div className="chain-flow" aria-hidden="true">
            <i />
          </div>
          <AgentNode id="rca" label={STAGE_LABELS.rca} status={pipeline.rca} variant="workflow-card analysis rca" />
        </div>
      </div>
    </div>
  );
}

function DependencyTree({ incident, loading }) {
  if (loading || !incident) return <Panel title="Service dependency" icon="🌐"><Skeleton lines={5} /></Panel>;
  return (
    <Panel title="Service dependency" icon="🌐">
      <div className="tree">
        <div className="node root">
          <span className="name">{incident.workflow} · workflow</span>
          <span className="pill">root</span>
        </div>
        {incident.dependencies.map((dep, index) => (
          <div key={`${dep.name}-${index}`} className={`node indent-${dep.depth} ${dep.state === "bottleneck" ? "affected" : dep.state === "timeout" ? "warn" : ""}`}>
            <span className="conn">{index === incident.dependencies.length - 1 ? "└─" : "├─"}</span>
            <span className="name">{dep.name}</span>
            <span className="pill">{dep.state}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function BusinessMetrics({ incident, loading }) {
  if (loading || !incident) return <Panel title="Business metrics" icon="📊"><Skeleton lines={5} /></Panel>;
  const kpis = incident.kpis;
  const paymentTone = kpis.payment_success_pct < 95 ? "crit" : "ok";
  return (
    <Panel title="Business metrics" icon="📊">
      <Stat label="Transactions" value={kpis.total_transactions} />
      <Stat label="Payment success" value={pct(kpis.payment_success_pct)} tone={paymentTone} />
      <Stat label="Failed transactions" value={kpis.failed_transactions} />
      <Stat label="Revenue (last 24h)" value={money(kpis.revenue_24h)} />
      <Stat label="Estimated impact" value={money(kpis.estimated_impact)} tone="accent" />
    </Panel>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div className="stat-row">
      <span className="k">{label}</span>
      <span className="v" data-tone={tone}>
        {value}
      </span>
    </div>
  );
}

function InvestigationTimeline({ timeline }) {
  return (
    <div className="panel timeline-panel">
      <h2>
        <span className="ico">🕑</span> Investigation timeline
      </h2>
      <div className="tl">
        {timeline.length === 0 ? (
          <p className="empty">Run triage to see the Commander and specialist agents investigate.</p>
        ) : (
          timeline.map((item, index) => {
            const agent = AGENT_META[item.agent] ? item.agent : "commander";
            const meta = AGENT_META[agent];
            return (
              <div className="tl-item" key={`${item.ts}-${item.agent}-${index}`}>
                <div className="tl-time">{item.ts}</div>
                <div className="tl-rail">
                  <div className={`tl-dot d-${agent}`} />
                  <div className="tl-line" />
                </div>
                <div className="tl-body">
                  <div className={`who ag-${agent}`}>
                    {meta.icon} {meta.label}
                  </div>
                  <div className="what">{item.message}</div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function CommanderEvidenceTrail({ evidenceTrail }) {
  const [isEvidenceTrailMaximized, setIsEvidenceTrailMaximized] = useState(false);

  return (
    <>
      <div className="panel evidence-panel">
        <div className="panel-title-row">
          <h2>
            <span className="ico">🧾</span> Commander Evidence Trail
          </h2>
          <button
            className="btn panel-icon-btn"
            type="button"
            onClick={() => setIsEvidenceTrailMaximized(true)}
            disabled={evidenceTrail.length === 0}
            title="Maximize evidence trail"
            aria-label="Maximize evidence trail"
          >
            ⛶ Maximize
          </button>
        </div>
        {evidenceTrail.length === 0 ? (
          <p className="empty">Run triage to stream raw evidence and extracted findings from each agent.</p>
        ) : (
          <EvidenceTrailCards evidenceTrail={evidenceTrail} />
        )}
      </div>
      {isEvidenceTrailMaximized && (
        <div className="evidence-modal" role="dialog" aria-modal="true" aria-labelledby="evidence-modal-title">
          <div className="evidence-modal-shell">
            <div className="evidence-modal-head">
              <div>
                <h2 id="evidence-modal-title">Commander Evidence Trail</h2>
                <p>{evidenceTrail.length} evidence events captured during this triage run.</p>
              </div>
              <button className="btn" type="button" onClick={() => setIsEvidenceTrailMaximized(false)}>
                Close
              </button>
            </div>
            <div className="evidence-modal-body">
              <EvidenceTrailCards evidenceTrail={evidenceTrail} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function EvidenceTrailCards({ evidenceTrail }) {
  return (
    <div className="evidence-list">
      {evidenceTrail.map((item, index) => {
        const agent = AGENT_META[item.agent] ? item.agent : "commander";
        const meta = AGENT_META[agent];
        const raw = item.raw ?? item.finding ?? item;
        return (
          <article className={`evidence-card ev-${agent}`} key={`${item.ts}-${item.agent}-${item.type}-${index}`}>
            <div className="evidence-top">
              <div className={`evidence-agent ag-${agent}`}>
                {meta.icon} {meta.label}
              </div>
              <span className="evidence-type">{formatEvidenceType(item.type)}</span>
            </div>
            <p className="evidence-summary">{item.summary || item.message || "Evidence captured."}</p>
            <div className="evidence-meta">
              {item.tool && <span>tool <code>{item.tool}</code></span>}
              {item.signal && <span>signal <code>{item.signal}</code></span>}
              {item.confidence !== undefined && <span>confidence <b>{String(item.confidence)}</b></span>}
              {item.alignment !== undefined && <span>aligned <b>{String(item.alignment)}</b></span>}
              {item.revenue_impact !== undefined && <span>impact <b>{money(item.revenue_impact)}</b></span>}
              {item.next_step && <span>next <code>{item.next_step}</code></span>}
            </div>
            {item.reasoning?.length > 0 && (
              <ul className="evidence-reasons">
                {item.reasoning.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            )}
            {item.query && (
              <details className="evidence-raw">
                <summary>Query</summary>
                <pre>{prettyJson(item.query)}</pre>
              </details>
            )}
            <details className="evidence-raw">
              <summary>Raw payload</summary>
              <pre>{prettyJson(raw)}</pre>
            </details>
          </article>
        );
      })}
    </div>
  );
}

function formatEvidenceType(type = "evidence") {
  return String(type).replaceAll("_", " ");
}

function prettyJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function RcaPanel({
  rca,
  loading,
  view,
  onApprove,
  onReject,
  confirmationRequired,
  onConfirmRollback,
  decisionReady,
}) {
  if (loading || !rca) return <Panel title="Root-cause analysis" icon="🎯" className="rca"><Skeleton lines={5} /></Panel>;
  return (
    <Panel title="Root-cause analysis" icon="🎯" className="rca">
      <div className="block">
        <div className="h">Summary</div>
        <p>{rca.root_cause}</p>
      </div>
      <div className="block">
        <div className="h">Business impact</div>
        <p>{rca.business_impact}</p>
      </div>
      {view === "eng" && (
        <>
          <div className="block">
            <div className="h">Confidence</div>
            <div className="conf" data-tone={rca.confidence?.toLowerCase() === "high" ? "ok" : "warn"}>
              {rca.confidence}
            </div>
          </div>
          <div className="block">
            <div className="h">Reasoning</div>
            {(rca.reasoning ?? [`${rca.reasoning_signals} independent technical signals above threshold`]).map((line) => (
              <div className="reason" key={line}>
                ✓ {line}
              </div>
            ))}
          </div>
          <GatedAction
            action={rca.gated_action}
            onApprove={onApprove}
            onReject={onReject}
            confirmationRequired={confirmationRequired}
            onConfirmRollback={onConfirmRollback}
            decisionReady={decisionReady}
          />
        </>
      )}
    </Panel>
  );
}

function GatedAction({ action, onApprove, onReject, confirmationRequired, onConfirmRollback, decisionReady }) {
  return (
    <div className="gated">
      <div className="g-head">🔒 Gated recommended action</div>
      <p>{action}</p>
      {!decisionReady && (
        <p className="gate-note">Approval controls unlock only after triage reaches the human approval gate.</p>
      )}
      <div className="g-actions">
        <button type="button" className="btn approve" disabled={!decisionReady} onClick={onApprove}>
          ✓ Approve
        </button>
        <button type="button" className="btn reject" disabled={!decisionReady} onClick={onReject}>
          Reject
        </button>
      </div>
      {confirmationRequired && (
        <div className="confirm">
          <p>Approval is recorded. A second human confirmation is required before rollback integration runs.</p>
          <button type="button" className="btn approve" onClick={onConfirmRollback}>
            Confirm rollback gate
          </button>
        </div>
      )}
    </div>
  );
}

function StatusBar({ message }) {
  if (!message) return null;
  return <div className="status-bar">✓ {message}</div>;
}

function Panel({ title, icon, className = "", children }) {
  return (
    <div className={`panel ${className}`}>
      <h2>
        <span className="ico">{icon}</span> {title}
      </h2>
      {children}
    </div>
  );
}

export default function SentinelDashboard() {
  const [theme, setTheme] = useState("light");
  const [view, setView] = useState("eng");
  const [incident, setIncident] = useState(null);
  const [rca, setRca] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [evidenceTrail, setEvidenceTrail] = useState([]);
  const [pipeline, setPipeline] = useState(initialPipeline);
  const [runState, setRunState] = useState("idle");
  const [runId, setRunId] = useState(null);
  const [confirmationRequired, setConfirmationRequired] = useState(false);
  const [decisionReady, setDecisionReady] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [loading, setLoading] = useState({ incident: true, rca: true, telemetry: false, reset: false });
  const [lastTelemetryCheck, setLastTelemetryCheck] = useState(null);
  const [isPollingTelemetry, setIsPollingTelemetry] = useState(false);
  const [errors, setErrors] = useState({});

  const setError = useCallback((key, error) => {
    setErrors((current) => ({ ...current, [key]: error ? error.message : "" }));
  }, []);

  const loadIncident = useCallback(async () => {
    setLoading((current) => ({ ...current, incident: true }));
    try {
      setIncident(await request("/api/incident"));
      setError("incident", null);
    } catch (error) {
      setError("incident", error);
    } finally {
      setLoading((current) => ({ ...current, incident: false }));
    }
  }, [setError]);

  const loadRca = useCallback(async () => {
    setLoading((current) => ({ ...current, rca: true }));
    try {
      setRca(await request("/api/rca"));
      setError("rca", null);
    } catch (error) {
      setError("rca", error);
    } finally {
      setLoading((current) => ({ ...current, rca: false }));
    }
  }, [setError]);

  useEffect(() => {
    loadIncident();
    loadRca();
  }, [loadIncident, loadRca]);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;

    const pollIncident = async () => {
      if (inFlight) return;
      inFlight = true;
      setIsPollingTelemetry(true);
      try {
        const nextIncident = await request("/api/incident");
        if (!cancelled) {
          setIncident(nextIncident);
          setLastTelemetryCheck(new Date());
          setError("incident", null);
        }
      } catch (error) {
        if (!cancelled) {
          setError("incident", error);
        }
      } finally {
        inFlight = false;
        if (!cancelled) {
          setIsPollingTelemetry(false);
        }
      }
    };

    pollIncident();
    const timer = window.setInterval(pollIncident, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [setError]);

  useEffect(() => {
    if (!runId) return undefined;
    const source = new EventSource(`${API_BASE}/api/triage/stream?run_id=${encodeURIComponent(runId)}`);

    source.onmessage = (event) => {
      const item = JSON.parse(event.data);
      setTimeline((current) => [...current, item]);
      const completedStage = item.stage_done ?? (STAGES.includes(item.agent) ? item.agent : null);
      if (completedStage) {
        setPipeline((current) => ({ ...current, [completedStage]: "done" }));
      }
    };

    source.addEventListener("evidence", (event) => {
      const item = JSON.parse(event.data);
      setEvidenceTrail((current) => [...current, item]);
    });

    source.addEventListener("done", (event) => {
      const payload = JSON.parse(event.data);
      setRunState("completed");
      setRunId(null);
      setDecisionReady(payload.status === "awaiting_decision");
      source.close();
      if (payload.rca) {
        setRca({
          root_cause: payload.rca.root_cause,
          business_impact: payload.rca.business_impact,
          confidence: payload.rca.confidence_band,
          reasoning: payload.rca.confidence_reasoning,
          reasoning_signals: payload.rca.confidence_reasoning?.length ?? 0,
          gated_action: payload.rca.proposed_fix,
        });
      } else {
        loadRca();
      }
    });

    source.addEventListener("error", (event) => {
      if (event.data) {
        const payload = JSON.parse(event.data);
        setError("triage", new Error(payload.message));
      }
      setRunState("completed");
      setRunId(null);
      setDecisionReady(false);
      source.close();
    });

    return () => source.close();
  }, [loadRca, runId, setError]);

  const runTriage = async () => {
    setTimeline([]);
    setEvidenceTrail([]);
    setPipeline({ ...initialPipeline(), commander: "active" });
    setRunState("running");
    setConfirmationRequired(false);
    setDecisionReady(false);
    setStatusMessage("");
    try {
      const data = await request("/api/triage/run", { method: "POST" });
      setRunId(data.run_id);
      setError("triage", null);
    } catch (error) {
      setRunState("idle");
      setError("triage", error);
    }
  };

  const resetUi = async () => {
    setLoading((current) => ({ ...current, reset: true }));
    try {
      await request("/api/triage/reset", { method: "POST" });
      setTimeline([]);
      setEvidenceTrail([]);
      setPipeline(initialPipeline());
      setRunState("idle");
      setRunId(null);
      setConfirmationRequired(false);
      setDecisionReady(false);
      setRca(await request("/api/rca"));
      setStatusMessage("UI reset. Timeline and agent pipeline are clear; no production telemetry was changed.");
      setError("triage", null);
    } catch (error) {
      setError("triage", error);
    } finally {
      setLoading((current) => ({ ...current, reset: false }));
    }
  };

  const reloadTelemetry = async () => {
    setLoading((current) => ({ ...current, telemetry: true }));
    try {
      setIncident(await request("/api/telemetry/reload", { method: "POST" }));
      setRca(await request("/api/rca"));
      setLastTelemetryCheck(new Date());
      setStatusMessage("Telemetry reloaded from Mini Shop data. KPI cards, dependency tree, and RCA snapshot are refreshed.");
      setError("incident", null);
      setError("rca", null);
    } catch (error) {
      setError("incident", error);
    } finally {
      setLoading((current) => ({ ...current, telemetry: false }));
    }
  };

  const decide = async (decision) => {
    try {
      const data = await request("/api/triage/decision", {
        method: "POST",
        body: JSON.stringify({ decision }),
      });
      if (decision === "reject") {
        setConfirmationRequired(false);
        setDecisionReady(false);
        setStatusMessage("Fix rejected. RCA + recommended actions handed off to the team; no automated change was made.");
      } else {
        setConfirmationRequired(true);
        setDecisionReady(false);
        setStatusMessage(data.message);
      }
      setError("triage", null);
    } catch (error) {
      setError("triage", error);
    }
  };

  const confirmRollbackGate = async () => {
    try {
      const data = await request("/api/triage/confirm-rollback", { method: "POST" });
      if (data.incident) {
        setIncident(data.incident);
        setLastTelemetryCheck(new Date());
      }
      setConfirmationRequired(false);
      setDecisionReady(false);
      setStatusMessage(`${data.message} Approved by ${data.confirmed_by} at ${new Date(data.confirmed_at).toLocaleTimeString()}.`);
      setError("triage", null);
    } catch (error) {
      setError("triage", error);
    }
  };

  const viewNote = useMemo(
    () =>
      view === "exec"
        ? "👔 Executive view — headline status, impact & the decision that needs sign-off."
        : "🛠️ Engineer view — full investigation detail shown below.",
    [view],
  );

  return (
    <main className="sentinel-dashboard" data-theme={theme} data-view={view}>
      <div className="wrap">
        <TopBar view={view} setView={setView} theme={theme} setTheme={setTheme} />
        <ErrorNotice message={errors.incident} onDismiss={() => setError("incident", null)} />
        <IncidentBanner incident={incident} loading={loading.incident} />
        <ErrorNotice message={errors.triage} onDismiss={() => setError("triage", null)} />
        <ActionBar
          runState={runState}
          onRun={runTriage}
        >
          <LiveTelemetryStatus lastChecked={lastTelemetryCheck} polling={isPollingTelemetry} error={Boolean(errors.incident)} />
        </ActionBar>
        <KpiGrid incident={incident} loading={loading.incident} />
        <VoiceIncidentCommander
          incident={incident}
          rca={rca}
          runState={runState}
          decisionReady={decisionReady}
          confirmationRequired={confirmationRequired}
          statusMessage={statusMessage}
        />
        {view === "eng" && <AgentPipeline pipeline={pipeline} />}
        <p className="view-note">{viewNote}</p>
        <div className="grid">
          {view === "eng" && (
            <div className="left-stack">
              <DependencyTree incident={incident} loading={loading.incident} />
              <BusinessMetrics incident={incident} loading={loading.incident} />
            </div>
          )}
          {view === "eng" && (
            <div className="middle-stack">
              <InvestigationTimeline timeline={timeline} />
              <CommanderEvidenceTrail evidenceTrail={evidenceTrail} />
            </div>
          )}
          <div className="rca-column">
            <ErrorNotice message={errors.rca} onDismiss={() => setError("rca", null)} />
            <RcaPanel
              rca={rca}
              loading={loading.rca}
              view={view}
              onApprove={() => decide("approve")}
              onReject={() => decide("reject")}
              confirmationRequired={confirmationRequired}
              onConfirmRollback={confirmRollbackGate}
              decisionReady={decisionReady}
            />
          </div>
        </div>
        <StatusBar message={statusMessage} />
      </div>
    </main>
  );
}
