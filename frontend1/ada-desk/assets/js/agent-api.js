// FastAPI adapter for the Ada Desk UI. The dashboard keeps its display model,
// while this module maps real agent records into that model.
const BACKEND_AGENT_KEY = "ada_backend_agent_id";
const DEFAULT_PERSONA = { name: "Ada Primary", domain: "AI Research" };

const AdaAgentAPI = {
  get config() {
    return window.adaEngine ? window.adaEngine.getSettings() : {
      useRealApi: true, apiUrl: "http://127.0.0.1:8000/api", apiKey: null
    };
  },

  async _request(path, options = {}) {
    const baseUrl = (this.config.apiUrl || "http://127.0.0.1:8000/api").replace(/\/$/, "");
    const response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(this.config.apiKey ? { Authorization: `Bearer ${this.config.apiKey}` } : {}),
        ...(options.headers || {})
      }
    });
    if (!response.ok) throw new Error(`Backend request failed (${response.status}): ${await response.text()}`);
    return response.json();
  },

  async initiateCycle(persona = DEFAULT_PERSONA) {
    const agent = { ...DEFAULT_PERSONA, ...(persona.persona || persona) };
    const result = await this._request("/agent/init", {
      method: "POST", body: JSON.stringify({ persona: agent })
    });
    localStorage.setItem(BACKEND_AGENT_KEY, result.agentId);
    await this.sync(result.agentId);
    return { id: result.agentId, agentId: result.agentId };
  },

  async sync(agentId = localStorage.getItem(BACKEND_AGENT_KEY)) {
    const status = await this._request("/agent/status");
    const agent = status.agents.find(item => item.agentId === agentId) || status.agents[0];
    if (!agent) return { status, posts: [], rejectedTopics: [] };
    localStorage.setItem(BACKEND_AGENT_KEY, agent.agentId);
    const [feed, rejected, activity] = await Promise.all([
      this._request(`/agent/feed?agentId=${encodeURIComponent(agent.agentId)}`),
      this._request(`/agent/rejected?agentId=${encodeURIComponent(agent.agentId)}`),
      this._request(`/agent/activity?agentId=${encodeURIComponent(agent.agentId)}`)
    ]);
    const published = (feed.posts || []).map(post => ({
      id: post.id, title: post.text.split(/\n|\. /)[0].slice(0, 100) || "Published post",
      category: "LINKEDIN POST", type: "analysis", timestamp: post.createdAt,
      confidence: 100, status: "published", author: agent.name,
      summary: post.rationale || post.text, content: post.text, vectors: post.sources || [], logs: []
    }));
    const spiked = (rejected.rejectedTopics || []).map(item => ({
      id: item.id, title: item.title, category: "Rejected Topic", cause: item.reason,
      timestamp: item.createdAt, node: agent.name, confidence: 0,
      summary: item.reason, heuristic: item.judgeScores ? Object.entries(item.judgeScores).map(([key, value]) => `${key}: ${value}`) : []
    }));
    const cycles = [{
      id: `AGENT-${agent.agentId.slice(0, 8)}`, timestamp: agent.nextRunAt || agent.createdAt,
      status: agent.active ? "RUNNING" : "STOPPED",
      headline: `${agent.name} has completed ${agent.cycleCount} autonomous cycle(s).`,
      details: [`Domain: ${agent.domain}`, `Next run: ${agent.nextRunAt || "not scheduled"}`]
    }];
    window.adaEngine?.replaceBackendState({
      published, spiked, cycles,
      metrics: {
        ...window.adaEngine.getMetrics(), articles24h: published.length,
        cadence: agent.nextRunAt || "scheduled", activity
      },
      feed: activity.articleTitle ? [{
        tag: activity.state.toUpperCase(), tagColor: "text-primary",
        text: `${activity.detail} Article: ${activity.articleTitle}`
      }] : [{ tag: activity.state.toUpperCase(), tagColor: "text-on-surface-variant", text: activity.detail }]
    });
    return { status, posts: feed.posts || [], rejectedTopics: rejected.rejectedTopics || [] };
  },

  async fetchFeed() { return this.sync(); },
  async fetchPublished() { await this.sync(); return window.adaEngine.getPublished(); },
  async fetchSpiked() { await this.sync(); return window.adaEngine.getSpiked(); },
  async fetchCycleLog() { await this.sync(); return window.adaEngine.getCycles(); },
  async reEvaluateSpike() { throw new Error("Re-evaluation is not exposed by the current backend API."); },
  async mergeSpike() { throw new Error("Merging rejected topics is not exposed by the current backend API."); }
};

window.AdaAgentAPI = AdaAgentAPI;
