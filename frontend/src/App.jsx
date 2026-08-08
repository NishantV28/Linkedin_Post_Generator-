import { useCallback, useEffect, useState } from "react";

const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
const POLL_INTERVAL_MS = 20_000;

const DEFAULT_PERSONA = {
  name: "Ada",
  domain: "AI Security",
  bio: "An autonomous desk following the stories that matter before they become consensus.",
  stableInterests: ["prompt injection", "supply chain", "red-teaming", "evaluation"],
};

function ago(value) {
  const minutes = Math.floor((Date.now() - new Date(value).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;
  return `${Math.floor(minutes / 1440)}d ago`;
}

function nextRun(value) {
  if (!value) return "—";
  const minutes = Math.ceil((new Date(value).getTime() - Date.now()) / 60_000);
  if (minutes <= 0) return "due now";
  if (minutes < 60) return `in ${minutes}m`;
  return `in ${Math.ceil(minutes / 60)}h`;
}

function useAgentData(agentId) {
  const [data, setData] = useState({ posts: null, status: null, rejected: [], error: null });
  const refresh = useCallback(async () => {
    if (!agentId) return;
    try {
      const [feedResponse, statusResponse, rejectedResponse] = await Promise.all([
        fetch(`${API_BASE}/api/agent/feed?agentId=${encodeURIComponent(agentId)}`),
        fetch(`${API_BASE}/api/agent/status?agentId=${encodeURIComponent(agentId)}`),
        fetch(`${API_BASE}/api/agent/rejected?agentId=${encodeURIComponent(agentId)}`),
      ]);
      if (!feedResponse.ok) throw new Error(`Feed request failed (${feedResponse.status})`);
      const [feed, status, rejected] = await Promise.all([
        feedResponse.json(),
        statusResponse.ok ? statusResponse.json() : { agents: [] },
        rejectedResponse.ok ? rejectedResponse.json() : { rejectedTopics: [] },
      ]);
      setData({
        posts: feed.posts || [],
        status: status.agents?.[0] || null,
        rejected: rejected.rejectedTopics || [],
        error: null,
      });
    } catch (error) {
      setData((current) => ({ ...current, error: error.message }));
    }
  }, [agentId]);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);
  return { ...data, refresh };
}

function InitGate({ onInit }) {
  const [name, setName] = useState(DEFAULT_PERSONA.name);
  const [domain, setDomain] = useState(DEFAULT_PERSONA.domain);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/agent/init`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ persona: { name, domain } }),
      });
      if (!response.ok) throw new Error(`Initialization failed (${response.status})`);
      const { agentId } = await response.json();
      onInit(agentId, { ...DEFAULT_PERSONA, name, domain });
    } catch (requestError) {
      setError(`${requestError.message}. Start the backend at ${API_BASE} and try again.`);
    } finally {
      setSaving(false);
    }
  }

  return <div className="init-gate"><form className="init-card" onSubmit={submit}>
    <p className="kicker">INITIALIZE AGENT</p><h1>Autonomous desk</h1>
    <label>Persona name<input value={name} onChange={(e) => setName(e.target.value)} required /></label>
    <label>Domain<input value={domain} onChange={(e) => setDomain(e.target.value)} required /></label>
    <button disabled={saving}>{saving ? "Initializing…" : "Initialize"}</button>
    {error && <p className="error">{error}</p>}
  </form></div>;
}

function Post({ post, index }) {
  const [expanded, setExpanded] = useState(false);
  return <article className="dispatch">
    <div className="dispatch-meta"><span>P-{index + 1}</span><time>{ago(post.createdAt)}</time></div>
    <p className="dispatch-text">{post.text}</p>
    <button className="link-button" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
      {expanded ? "Hide editorial log" : "Show editorial log"}
    </button>
    {expanded && <div className="rationale"><b>Why this ran</b><p>{post.rationale}</p>
      {post.sources?.length > 0 && <><b>Sources</b><ul>{post.sources.map((source) => <li key={source}><a href={source} target="_blank" rel="noreferrer">{source}</a></li>)}</ul></>}
    </div>}
  </article>;
}

export default function App() {
  const [agentId, setAgentId] = useState(() => localStorage.getItem("agentId"));
  const [persona, setPersona] = useState(() => {
    try { return JSON.parse(localStorage.getItem("persona")) || null; } catch { return null; }
  });
  const { posts, status, rejected, error, refresh } = useAgentData(agentId);

  function initialize(id, personaInput) {
    localStorage.setItem("agentId", id);
    localStorage.setItem("persona", JSON.stringify(personaInput));
    setAgentId(id); setPersona(personaInput);
  }
  function reset() { localStorage.removeItem("agentId"); localStorage.removeItem("persona"); setAgentId(null); setPersona(null); }
  if (!agentId || !persona) return <InitGate onInit={initialize} />;

  const orderedPosts = [...(posts || [])].sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  return <><div className="ticker">{persona.name.toUpperCase()} — {persona.domain.toUpperCase()} DESK · {status?.cycleCount ?? 0} CYCLES RUN · NEXT DISPATCH {nextRun(status?.nextRunAt)}</div>
    <div className="layout"><aside className="masthead"><p className="kicker">AUTONOMOUS DESK</p><h1>{persona.name}</h1><div className="domain">{persona.domain}</div><p className="bio">{persona.bio}</p><div className="tags">{persona.stableInterests.map((interest) => <span key={interest}>{interest}</span>)}</div><button className="reset" onClick={reset}>Change persona</button></aside>
      <main className="feed"><header><h2>Dispatch feed</h2><button className="refresh" onClick={refresh}>Refresh</button></header>
        {error && <p className="error">{error} — showing the last successful result.</p>}
        {posts === null && <p className="empty">Loading live feed…</p>}
        {posts?.length === 0 && <p className="empty">No dispatches yet — the desk is still watching the wire.</p>}
        {orderedPosts.map((post, index) => <Post key={post.id} post={post} index={orderedPosts.length - index} />)}
        {rejected.length > 0 && <details className="rejected"><summary>Show spiked topics ({rejected.length})</summary>{rejected.map((item) => <div key={item.id}><b>{item.title}</b><p>{item.reason}</p></div>)}</details>}
      </main></div></>;
}
