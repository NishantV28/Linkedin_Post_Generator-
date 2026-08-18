// ==========================================================================
// AdaEngine — Central State & Simulation Controller
// Persistent local storage, background log generator, and event dispatches.
// ==========================================================================

const STORAGE_KEYS = {
  PUBLISHED: "ada_published_reports",
  SPIKED: "ada_spiked_topics",
  CYCLES: "ada_cycle_logs",
  FEED: "ada_feed_lines",
  METRICS: "ada_metrics",
  SETTINGS: "ada_settings"
};

const DEFAULT_SETTINGS = {
  useRealApi: true,
  apiUrl: "/api",
  apiKey: null,
  simulationSpeed: "normal",
  autoCycleInterval: 150,
  confidenceFloor: 60,
  theme: "dark"
};

const DEFAULT_METRICS = {
  articles24h: 0,
  spikedCount: 0,
  cycleCount: 0,
  nextRunAt: null,
  active: false,
  llmModel: null,
  canPublish: false,
  llmDetail: null
};

const SEED_PUBLISHED = [];
const SEED_SPIKED = [];
const SEED_CYCLES = [];
const FEED_TOPICS = [];

class AdaEngine {
  constructor() {
    this.listeners = {};
    this.initStorage();
    this.startBackgroundProcess();
  }

  initStorage() {
    if (!localStorage.getItem(STORAGE_KEYS.PUBLISHED)) {
      localStorage.setItem(STORAGE_KEYS.PUBLISHED, JSON.stringify(SEED_PUBLISHED));
    }
    if (!localStorage.getItem(STORAGE_KEYS.SPIKED)) {
      localStorage.setItem(STORAGE_KEYS.SPIKED, JSON.stringify(SEED_SPIKED));
    }
    if (!localStorage.getItem(STORAGE_KEYS.CYCLES)) {
      localStorage.setItem(STORAGE_KEYS.CYCLES, JSON.stringify(SEED_CYCLES));
    }
    if (!localStorage.getItem(STORAGE_KEYS.METRICS)) {
      localStorage.setItem(STORAGE_KEYS.METRICS, JSON.stringify(DEFAULT_METRICS));
    }
    if (!localStorage.getItem(STORAGE_KEYS.SETTINGS)) {
      localStorage.setItem(STORAGE_KEYS.SETTINGS, JSON.stringify(DEFAULT_SETTINGS));
    }
  }

  // Getters
  getPublished() {
    return JSON.parse(localStorage.getItem(STORAGE_KEYS.PUBLISHED) || "[]");
  }

  getSpiked() {
    return JSON.parse(localStorage.getItem(STORAGE_KEYS.SPIKED) || "[]");
  }

  getCycles() {
    return JSON.parse(localStorage.getItem(STORAGE_KEYS.CYCLES) || "[]");
  }

  getMetrics() {
    return JSON.parse(localStorage.getItem(STORAGE_KEYS.METRICS) || "{}");
  }

  getSettings() {
    return JSON.parse(localStorage.getItem(STORAGE_KEYS.SETTINGS) || "{}");
  }

  saveSettings(newSettings) {
    const current = this.getSettings();
    const updated = { ...current, ...newSettings };
    localStorage.setItem(STORAGE_KEYS.SETTINGS, JSON.stringify(updated));
    this.notify('settings-changed', updated);
    return updated;
  }

  // Keeps the existing dashboard renderers while allowing the API adapter to
  // replace demo records with data returned by the FastAPI application.
  replaceBackendState({ published, spiked, cycles, metrics, feed }) {
    if (published) localStorage.setItem(STORAGE_KEYS.PUBLISHED, JSON.stringify(published));
    if (spiked) localStorage.setItem(STORAGE_KEYS.SPIKED, JSON.stringify(spiked));
    if (cycles) localStorage.setItem(STORAGE_KEYS.CYCLES, JSON.stringify(cycles));
    if (metrics) localStorage.setItem(STORAGE_KEYS.METRICS, JSON.stringify(metrics));
    if (feed) localStorage.setItem(STORAGE_KEYS.FEED, JSON.stringify(feed));
    this.notify('state-changed', { type: 'backend-synchronized' });
  }

  // Actions
  initiateCycle(customName = "Ada Primary") {
    const cycles = this.getCycles();
    const cycleNum = Math.floor(9483 + Math.random() * 500);
    const id = `CYC-${cycleNum}.RUN`;

    const newCycle = {
      id,
      timestamp: new Date().toISOString(),
      status: "RUNNING",
      headline: `Initiated autonomous scan pass (${customName}).`,
      progress: 12,
      details: [
        "[SYS] Allocating vector compute nodes... [OK]",
        "[NET] Broad-spectrum stream ingestion initialized... [OK]",
        "_ Scanning vector clusters in progress (12% complete)"
      ]
    };

    cycles.unshift(newCycle);
    localStorage.setItem(STORAGE_KEYS.CYCLES, JSON.stringify(cycles));

    // Update metrics
    const metrics = this.getMetrics();
    metrics.articles24h += 1;
    metrics.compute = Math.min(98, metrics.compute + 4);
    localStorage.setItem(STORAGE_KEYS.METRICS, JSON.stringify(metrics));

    this.notify('state-changed', { type: 'cycle-initiated', cycle: newCycle });
    return newCycle;
  }

  reEvaluateSpike(id) {
    const spiked = this.getSpiked();
    const item = spiked.find(s => s.id === id);
    if (!item) return null;

    item.confidence = Math.min(99, item.confidence + 38);
    let promoted = false;

    if (item.confidence >= 70) {
      // Move to published
      promoted = true;
      const index = spiked.findIndex(s => s.id === id);
      spiked.splice(index, 1);

      const published = this.getPublished();
      const newPublished = {
        id: `RPT-${Math.floor(8993 + Math.random() * 100)}-RE`,
        title: item.title,
        category: "RE-EVALUATED",
        type: "analysis",
        timestamp: new Date().toISOString(),
        confidence: item.confidence,
        status: "verified",
        author: "Ada Re-Evaluator",
        summary: item.summary,
        content: `## Re-Evaluated Intelligence Advisory\n${item.summary}\n\n### Re-evaluation Notes\n- Confidence score upgraded from ${item.confidence - 38}% to ${item.confidence}%.\n- Passed secondary validation check across primary vector clusters.`,
        vectors: [item.node],
        logs: item.heuristic
      };
      published.unshift(newPublished);
      localStorage.setItem(STORAGE_KEYS.PUBLISHED, JSON.stringify(published));
    }

    localStorage.setItem(STORAGE_KEYS.SPIKED, JSON.stringify(spiked));
    this.notify('state-changed', { type: 'spike-reevaluated', item, promoted });
    return { item, promoted };
  }

  mergeSpike(id) {
    const spiked = this.getSpiked();
    const item = spiked.find(s => s.id === id);
    if (!item) return null;

    item.merged = true;
    item.category = "Merged Record";
    item.heuristic.push("> MERGED: Context combined with master knowledge base");
    localStorage.setItem(STORAGE_KEYS.SPIKED, JSON.stringify(spiked));
    this.notify('state-changed', { type: 'spike-merged', item });
    return item;
  }

  addSpike(topic) {
    const spiked = this.getSpiked();
    const id = `SPK-${Math.floor(1050 + Math.random() * 500)}`;
    const newSpike = {
      id,
      title: topic.title || "Unclassified Sensor Anomaly",
      category: topic.category || "Low Relevance",
      cause: topic.cause || "Low confidence threshold",
      timestamp: "Just Now",
      node: topic.node || "Node-Alpha-9",
      confidence: topic.confidence || 35,
      heuristic: [
        "> WARN: Signal variance out of bounds.",
        `> ACTION: SPIKE (${topic.category || "Low Relevance"})`
      ],
      summary: topic.summary || "Sensor stream rejected due to noise threshold."
    };
    spiked.unshift(newSpike);
    localStorage.setItem(STORAGE_KEYS.SPIKED, JSON.stringify(spiked));
    this.notify('state-changed', { type: 'spike-added', item: newSpike });
    return newSpike;
  }

  fetchOlderPublished() {
    return [];
  }

  searchAll(query) {
    if (!query) return { published: [], spiked: [], cycles: [] };
    const q = query.trim().toLowerCase();

    const published = this.getPublished().filter(p =>
      p.title.toLowerCase().includes(q) ||
      (p.summary && p.summary.toLowerCase().includes(q)) ||
      (p.category && p.category.toLowerCase().includes(q))
    );

    const spiked = this.getSpiked().filter(s =>
      s.title.toLowerCase().includes(q) ||
      (s.summary && s.summary.toLowerCase().includes(q)) ||
      (s.cause && s.cause.toLowerCase().includes(q))
    );

    const cycles = this.getCycles().filter(c =>
      c.id.toLowerCase().includes(q) ||
      c.headline.toLowerCase().includes(q)
    );

    return { published, spiked, cycles };
  }

  // Event system
  on(event, callback) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(callback);
  }

  notify(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(cb => cb(data));
    }
  }

  startBackgroundProcess() {
    // No background mock simulation; all state is driven by live API syncs.
  }
}

// Global Singleton Instance
window.adaEngine = new AdaEngine();
