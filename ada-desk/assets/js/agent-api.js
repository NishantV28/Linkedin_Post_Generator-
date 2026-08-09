// ==========================================================================
// AdaAgentAPI — Unified Interface for Local Engine & Remote Agent API
// Supports seamless switching between simulated local state and live REST API.
// ==========================================================================

const AdaAgentAPI = {
  get config() {
    return window.adaEngine ? window.adaEngine.getSettings() : {
      useRealApi: false,
      apiUrl: "http://localhost:8000/api",
      apiKey: null
    };
  },

  async _request(path, options = {}) {
    const baseUrl = this.config.apiUrl || "http://localhost:8000/api";
    const apiKey = this.config.apiKey;

    const res = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
        ...(options.headers || {})
      }
    });

    if (!res.ok) {
      throw new Error(`Agent API error ${res.status}: ${await res.text()}`);
    }
    return res.json();
  },

  // POST /agent/init — start a new synthesis cycle
  async initiateCycle(config = { intensity: 0.8, auto_cycle: true }) {
    if (!this.config.useRealApi) {
      // Use Local AdaEngine
      await new Promise(r => setTimeout(r, 600)); // simulated latency
      return window.adaEngine.initiateCycle("Ada Primary");
    }
    return this._request("/agent/init", {
      method: "POST",
      body: JSON.stringify({ name: "Ada Primary", type: "research", config })
    });
  },

  // GET /agent/feed — poll the live analysis feed
  async fetchFeed(instanceId, limit = 20) {
    if (!this.config.useRealApi) {
      return { status: "ok", feed: window.adaEngine.getFeedLines ? window.adaEngine.getFeedLines() : [] };
    }
    return this._request(`/agent/feed?id=${instanceId || 'default'}&limit=${limit}`);
  },

  // GET /reports/published — list published intelligence reports
  async fetchPublished() {
    if (!this.config.useRealApi) {
      return window.adaEngine.getPublished();
    }
    return this._request("/reports/published");
  },

  // GET /reports/spiked — list rejected/spiked topics
  async fetchSpiked() {
    if (!this.config.useRealApi) {
      return window.adaEngine.getSpiked();
    }
    return this._request("/reports/spiked");
  },

  // GET /cycles — chronological cycle log
  async fetchCycleLog() {
    if (!this.config.useRealApi) {
      return window.adaEngine.getCycles();
    }
    return this._request("/cycles");
  },

  // POST /reports/spiked/reevaluate
  async reEvaluateSpike(id) {
    if (!this.config.useRealApi) {
      await new Promise(r => setTimeout(r, 800));
      return window.adaEngine.reEvaluateSpike(id);
    }
    return this._request("/reports/spiked/reevaluate", {
      method: "POST",
      body: JSON.stringify({ id })
    });
  },

  // POST /reports/spiked/merge
  async mergeSpike(id) {
    if (!this.config.useRealApi) {
      await new Promise(r => setTimeout(r, 500));
      return window.adaEngine.mergeSpike(id);
    }
    return this._request("/reports/spiked/merge", {
      method: "POST",
      body: JSON.stringify({ id })
    });
  }
};

window.AdaAgentAPI = AdaAgentAPI;
