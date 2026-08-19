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

  async _requestRaw(urlPath, options = {}) {
    const apiBase = (this.config.apiUrl || "http://127.0.0.1:8000/api").replace(/\/$/, "");
    // If urlPath starts with http/https, use directly. Otherwise if path doesn't start with /api, compute origin.
    let fullUrl;
    if (urlPath.startsWith("http://") || urlPath.startsWith("https://")) {
      fullUrl = urlPath;
    } else if (urlPath.startsWith("/health")) {
      const origin = apiBase.replace(/\/api\/?$/, "");
      fullUrl = `${origin}${urlPath}`;
    } else {
      fullUrl = `${apiBase}${urlPath}`;
    }

    const response = await fetch(fullUrl, {
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

  async _request(path, options = {}) {
    return this._requestRaw(path, options);
  },

  async fetchHealth() {
    try {
      return await this._requestRaw("/health");
    } catch (e) {
      return { status: "unknown", canPublish: false, llm: { ok: false, model: "Unknown", detail: e.message } };
    }
  },

  async initiateCycle(persona) {
    const chosen = window.AdaPersona?.getPersona();
    const agent = { ...DEFAULT_PERSONA, ...(chosen || {}), ...((persona || {}).persona || persona || {}) };
    const result = await this._request("/agent/init", {
      method: "POST", body: JSON.stringify({ persona: { name: agent.name, domain: agent.domain } })
    });
    window.AdaPersona?.save(result.agentId, { name: agent.name, domain: agent.domain });
    localStorage.setItem(BACKEND_AGENT_KEY, result.agentId);
    await this.sync(result.agentId);
    return { id: result.agentId, agentId: result.agentId };
  },

  async sync(agentId = localStorage.getItem(BACKEND_AGENT_KEY)) {
    if (!agentId) {
      window.AdaPersona?.forget("Select a persona to begin.");
      return { status: { agents: [] }, posts: [], rejectedTopics: [] };
    }

    const status = await this._request(`/agent/status?agentId=${encodeURIComponent(agentId)}`);
    const agent = (status.agents || []).find(item => item.agentId === agentId);
    if (!agent) {
      window.AdaPersona?.forget("That agent no longer exists on the backend.");
      return { status, posts: [], rejectedTopics: [] };
    }

    const [feed, rejectedAgent, rejectedAll, activity, health] = await Promise.all([
      this._request(`/agent/feed?agentId=${encodeURIComponent(agent.agentId)}`),
      this._request(`/agent/rejected?agentId=${encodeURIComponent(agent.agentId)}`),
      this._request(`/agent/rejected`).catch(() => ({ rejectedTopics: [] })),
      this._request(`/agent/activity?agentId=${encodeURIComponent(agent.agentId)}`)
        .catch(() => ({
          state: agent.active ? "scheduled" : "stopped",
          detail: agent.nextRunAt
            ? `Next cycle at ${new Date(agent.nextRunAt).toLocaleString()}.`
            : "Waiting for the next scheduled cycle.",
          articleTitle: null,
          updatedAt: null
        })),
      this.fetchHealth()
    ]);

    const rejected = (rejectedAgent.rejectedTopics && rejectedAgent.rejectedTopics.length > 0) 
      ? rejectedAgent 
      : rejectedAll;

    const published = (feed.posts || []).map(post => ({
      id: post.id,
      title: post.text.split(/\n|\. /)[0].slice(0, 100) || "LinkedIn Post",
      category: "LINKEDIN POST",
      type: "analysis",
      timestamp: post.createdAt,
      confidence: 100,
      status: "published",
      author: agent.name,
      summary: post.rationale || post.text,
      content: post.text,
      vectors: post.sources || [],
      logs: []
    }));

    const spiked = (rejected.rejectedTopics || []).map(item => ({
      id: item.id,
      title: item.title,
      category: "Rejected Topic",
      cause: item.reason,
      timestamp: item.createdAt,
      node: agent.name,
      confidence: 0,
      summary: item.reason,
      sourceUrl: item.sourceUrl,
      heuristic: item.judgeScores ? Object.entries(item.judgeScores).map(([key, value]) => `${key}: ${value}`) : []
    }));

    // Generate real cycle timeline from database agent status and events
    const cycleList = [];
    
    // Active status / Next Run entry
    cycleList.push({
      id: `AGENT-${agent.agentId.slice(0, 8)}`,
      timestamp: agent.nextRunAt || agent.createdAt,
      status: agent.active ? "RUNNING" : "STOPPED",
      headline: `${agent.name} is currently ${agent.active ? 'Active & Scheduled' : 'Deactivated'}. Completed ${agent.cycleCount} cycle(s).`,
      details: [
        `Domain: ${agent.domain}`,
        `Next scheduled run: ${agent.nextRunAt ? new Date(agent.nextRunAt).toLocaleString() : 'None'}`,
        `LLM Status: ${health.canPublish ? 'Ready' : 'Configuration Error'} (${health.llm?.model || 'Unknown'})`
      ]
    });

    // Add entries for publications
    published.forEach(p => {
      cycleList.push({
        id: `PUB-${p.id.slice(0, 8)}`,
        timestamp: p.timestamp,
        status: "COMPLETE",
        headline: `Published post: "${p.title}"`,
        details: [
          `Rationale: ${p.summary.slice(0, 120)}...`,
          `Sources cited: ${p.vectors.length} URL(s)`
        ]
      });
    });

    // Add entries for spiked topics
    spiked.forEach(s => {
      cycleList.push({
        id: `SPK-${s.id.slice(0, 8)}`,
        timestamp: s.timestamp,
        status: "REJECTED",
        headline: `Spiked candidate topic: "${s.title}"`,
        details: [
          `Reason: ${s.cause}`,
          ...(s.heuristic || [])
        ]
      });
    });

    // Build terminal feed entries from real data
    const terminalFeed = [];
    if (activity.articleTitle) {
      terminalFeed.push({
        tag: (activity.state || "ACTIVE").toUpperCase(),
        tagColor: "text-primary",
        text: `Processing topic: "${activity.articleTitle}" — ${activity.detail}`
      });
    } else {
      terminalFeed.push({
        tag: (activity.state || "IDLE").toUpperCase(),
        tagColor: "text-on-surface-variant",
        text: activity.detail || "Waiting for next scheduled autonomous cycle."
      });
    }

    published.slice(0, 3).forEach(p => {
      terminalFeed.push({
        tag: "PUBLISHED",
        tagColor: "text-primary",
        text: `[${p.timestamp}] Successfully published post: "${p.title}"`
      });
    });

    spiked.slice(0, 3).forEach(s => {
      terminalFeed.push({
        tag: "REJECTED",
        tagColor: "text-error",
        text: `[${s.timestamp}] Spiked topic "${s.title}": ${s.cause}`
      });
    });

    window.adaEngine?.replaceBackendState({
      published,
      spiked,
      cycles: cycleList,
      metrics: {
        articles24h: published.length,
        spikedCount: spiked.length,
        cycleCount: agent.cycleCount,
        nextRunAt: agent.nextRunAt,
        active: agent.active,
        llmModel: health.llm?.model || "(Provider default)",
        canPublish: health.canPublish,
        llmDetail: health.llm?.detail || "",
        activity
      },
      feed: terminalFeed
    });

    return { status, posts: feed.posts || [], rejectedTopics: rejected.rejectedTopics || [] };
  },

  async fetchFeed() { return this.sync(); },
  async fetchPublished() { await this.sync(); return window.adaEngine.getPublished(); },
  async fetchSpiked() { await this.sync(); return window.adaEngine.getSpiked(); },
  async fetchCycleLog() { await this.sync(); return window.adaEngine.getCycles(); },
  async reEvaluateSpike() { throw new Error("Re-evaluation is not supported; rejected topics were filtered by LLM quality judges."); },
  async mergeSpike() { throw new Error("Merge operation is not supported for rejected topics."); },

  async reframePost(postId, feedback) {
    if (!postId || !feedback) throw new Error("Post ID and feedback text are required.");
    const result = await this._request("/agent/reframe", {
      method: "POST",
      body: JSON.stringify({ postId, feedback })
    });
    // Sync latest state
    await this.sync();
    return result;
  }
};

window.AdaAgentAPI = AdaAgentAPI;
