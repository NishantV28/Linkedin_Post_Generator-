// ==========================================================================
// Ada Desk — Front-End Application Logic & Event Handlers
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initActiveNav();
  initMobileDrawer();
  initInitiateCycle();
  initCopyButtons();
  initSearch();
  initGlobalModals();
  initKeyboardShortcuts();

  // Page-specific renderers
  const page = document.body.dataset.page;
  if (page === "home") initHomePage();
  if (page === "published") initPublishedPage();
  if (page === "spiked") initSpikedPage();
  if (page === "cycle-log") initCycleLogPage();
  if (page === "api") initApiPage();

  // Populate the existing dashboard components from FastAPI on page load.
  // Demo records remain available only if the backend cannot be reached.
  if (window.AdaAgentAPI) {
    window.AdaAgentAPI.sync().catch((err) => {
      console.warn("Backend sync unavailable:", err.message);
      showToast("Backend unavailable — showing local fallback data");
    });
  }

  // Listen to engine state changes for reactive updates
  if (window.adaEngine) {
    window.adaEngine.on('state-changed', (e) => {
      if (page === "home") updateHomeMetrics();
      if (page === "published") renderPublishedList();
      if (page === "spiked") renderSpikedList();
      if (page === "cycle-log") renderCycleLogList();
    });
  }
});

/* ---------------------------------------------------------------------- */
/* Theme Controller (Light / Dark Classic UI Toggle)                      */
/* ---------------------------------------------------------------------- */
function initTheme() {
  const savedTheme = localStorage.getItem("ada-theme") || "dark";
  setTheme(savedTheme, false);

  document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      toggleTheme();
    });
  });
}

function toggleTheme() {
  const currentTheme = document.documentElement.classList.contains("light") ? "light" : "dark";
  const newTheme = currentTheme === "dark" ? "light" : "dark";
  setTheme(newTheme, true);
}

function setTheme(theme, announce = true) {
  if (theme === "light") {
    document.documentElement.classList.remove("dark");
    document.documentElement.classList.add("light");
    localStorage.setItem("ada-theme", "light");
  } else {
    document.documentElement.classList.remove("light");
    document.documentElement.classList.add("dark");
    localStorage.setItem("ada-theme", "dark");
  }

  updateThemeIcons(theme);

  if (announce) {
    showToast(`Switched to ${theme === "light" ? "Classic White Theme" : "Dark Futuristic Theme"}`);
  }
}

function updateThemeIcons(theme) {
  const isLight = theme === "light";
  document.querySelectorAll("[data-theme-icon]").forEach((icon) => {
    icon.textContent = isLight ? "dark_mode" : "light_mode";
  });
  document.querySelectorAll("[data-theme-label]").forEach((label) => {
    label.textContent = isLight ? "Dark Theme" : "Light Theme";
  });
}

window.toggleTheme = toggleTheme;
window.setTheme = setTheme;


/* ---------------------------------------------------------------------- */
/* Active Navigation Highlighting                                         */
/* ---------------------------------------------------------------------- */
function initActiveNav() {
  const page = document.body.dataset.page;
  if (!page) return;
  document.querySelectorAll("[data-page-link]").forEach((link) => {
    if (link.dataset.pageLink === page) {
      link.classList.add("active");
    } else {
      link.classList.remove("active");
    }
  });
}

/* ---------------------------------------------------------------------- */
/* Mobile Drawer Toggle                                                   */
/* ---------------------------------------------------------------------- */
function initMobileDrawer() {
  const openBtn = document.getElementById("menu-toggle");
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebar-overlay");
  if (!openBtn || !sidebar || !overlay) return;

  const close = () => {
    sidebar.classList.remove("open");
    overlay.classList.remove("open");
  };
  const open = () => {
    sidebar.classList.add("open");
    overlay.classList.add("open");
  };

  openBtn.addEventListener("click", () => {
    sidebar.classList.contains("open") ? close() : open();
  });
  overlay.addEventListener("click", close);
  sidebar.querySelectorAll("a").forEach((a) => a.addEventListener("click", close));
}

/* ---------------------------------------------------------------------- */
/* Toast Notifications                                                    */
/* ---------------------------------------------------------------------- */
function showToast(message) {
  let root = document.getElementById("toast-root");
  if (!root) {
    root = document.createElement("div");
    root.id = "toast-root";
    document.body.appendChild(root);
  }
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = message;
  root.appendChild(toast);
  setTimeout(() => toast.remove(), 2800);
}

/* ---------------------------------------------------------------------- */
/* Initiate Cycle Action                                                  */
/* ---------------------------------------------------------------------- */
function initInitiateCycle() {
  document.querySelectorAll("[data-initiate-cycle]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      const originalText = btn.innerHTML;
      btn.innerHTML = `<span class="material-symbols-outlined text-sm animate-spin">sync</span> Starting…`;

      try {
        const result = await window.AdaAgentAPI.initiateCycle();
        showToast(`⏵ Cycle ${result.id || 'started'} — Ada is scanning data vectors`);
      } catch (err) {
        showToast(`⚠️ Error initiating cycle: ${err.message}`);
      }

      setTimeout(() => {
        btn.disabled = false;
        btn.innerHTML = originalText;
      }, 1500);
    });
  });
}

/* ---------------------------------------------------------------------- */
/* Copy Buttons                                                            */
/* ---------------------------------------------------------------------- */
function initCopyButtons() {
  document.querySelectorAll("[data-copy-target]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const target = document.querySelector(btn.dataset.copyTarget);
      if (!target) return;
      try {
        await navigator.clipboard.writeText(target.innerText || target.value);
        showToast("✓ Copied to clipboard");
      } catch (err) {
        showToast("Couldn't copy — select manually");
      }
    });
  });
}

/* ---------------------------------------------------------------------- */
/* Global Search Auto-Suggest & Keyboard Shortcuts                         */
/* ---------------------------------------------------------------------- */
function initSearch() {
  const input = document.getElementById("global-search");
  if (!input) return;

  // Create auto-suggest container
  let dropdown = document.getElementById("search-dropdown");
  if (!dropdown) {
    dropdown = document.createElement("div");
    dropdown.id = "search-dropdown";
    dropdown.style.display = "none";
    input.parentElement.appendChild(dropdown);
  }

  input.addEventListener("input", (e) => {
    const q = e.target.value.trim();
    if (!q || q.length < 2) {
      dropdown.style.display = "none";
      return;
    }

    const results = window.adaEngine ? window.adaEngine.searchAll(q) : { published: [], spiked: [], cycles: [] };
    let html = "";

    if (results.published.length) {
      html += `<div class="px-3 py-1 text-[10px] font-label-caps text-primary uppercase border-b border-glass-stroke">Published Reports</div>`;
      results.published.slice(0, 3).forEach(p => {
        html += `<div class="search-result-item" onclick="openReportModal('${p.id}')">
          <div class="text-xs font-bold text-on-surface">${escapeHtml(p.title)}</div>
          <div class="text-[10px] text-on-surface-variant">${p.category} • ${p.confidence}%</div>
        </div>`;
      });
    }

    if (results.spiked.length) {
      html += `<div class="px-3 py-1 text-[10px] font-label-caps text-error uppercase border-b border-glass-stroke">Spiked Topics</div>`;
      results.spiked.slice(0, 3).forEach(s => {
        html += `<div class="search-result-item" onclick="openSpikeModal('${s.id}')">
          <div class="text-xs font-bold text-on-surface">${escapeHtml(s.title)}</div>
          <div class="text-[10px] text-on-surface-variant">${s.category} • Node: ${s.node}</div>
        </div>`;
      });
    }

    if (results.cycles.length) {
      html += `<div class="px-3 py-1 text-[10px] font-label-caps text-secondary uppercase border-b border-glass-stroke">Cycle Logs</div>`;
      results.cycles.slice(0, 2).forEach(c => {
        html += `<div class="search-result-item" onclick="openCycleModal('${c.id}')">
          <div class="text-xs font-bold text-on-surface">${c.id}</div>
          <div class="text-[10px] text-on-surface-variant">${escapeHtml(c.headline)}</div>
        </div>`;
      });
    }

    if (!html) {
      html = `<div class="p-3 text-xs text-on-surface-variant text-center">No matching intelligence items found</div>`;
    }

    dropdown.innerHTML = html;
    dropdown.style.display = "block";
  });

  document.addEventListener("click", (e) => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.style.display = "none";
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && input.value.trim()) {
      dropdown.style.display = "none";
      showToast(`Searching databank for "${input.value.trim()}"…`);
    }
  });
}

function initKeyboardShortcuts() {
  window.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      e.preventDefault();
      const searchInput = document.getElementById("global-search");
      if (searchInput) searchInput.focus();
    }
    if ((e.metaKey || e.ctrlKey) && e.key === "i") {
      e.preventDefault();
      const btn = document.querySelector("[data-initiate-cycle]");
      if (btn) btn.click();
    }
    if (e.key === "Escape") {
      closeAllModals();
    }
  });
}

/* ---------------------------------------------------------------------- */
/* Modal Infrastructure                                                  */
/* ---------------------------------------------------------------------- */
function createModalOverlay(id, title, bodyContent, footerBtns = "") {
  let existing = document.getElementById(id);
  if (existing) existing.remove();

  const overlay = document.createElement("div");
  overlay.id = id;
  overlay.className = "ada-modal-overlay";
  overlay.innerHTML = `
    <div class="ada-modal-container">
      <div class="ada-modal-header">
        <div class="font-headline-lg text-lg text-primary font-bold flex items-center gap-2">
          <span class="material-symbols-outlined text-xl">analytics</span>
          ${title}
        </div>
        <button onclick="closeModal('${id}')" class="text-on-surface-variant hover:text-on-surface p-1 rounded hover:bg-surface-container-high transition-colors">
          <span class="material-symbols-outlined">close</span>
        </button>
      </div>
      <div class="ada-modal-body">
        ${bodyContent}
      </div>
      ${footerBtns ? `<div class="ada-modal-footer">${footerBtns}</div>` : ''}
    </div>
  `;

  document.body.appendChild(overlay);
  setTimeout(() => overlay.classList.add("open"), 10);

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeModal(id);
  });

  return overlay;
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove("open");
    setTimeout(() => modal.remove(), 250);
  }
}

function closeAllModals() {
  document.querySelectorAll(".ada-modal-overlay").forEach(m => {
    m.classList.remove("open");
    setTimeout(() => m.remove(), 250);
  });
}

// Window global modal handlers
window.closeModal = closeModal;

/* ---------------------------------------------------------------------- */
/* Specific Modals                                                        */
/* ---------------------------------------------------------------------- */

// Helper to toggle Editorial Rationale in modal
window.toggleRationale = function(id) {
  const section = document.getElementById(`rationale-section-${id}`);
  const arrow = document.getElementById(`rationale-arrow-${id}`);
  if (!section) return;
  const isHidden = section.classList.contains('hidden');
  if (isHidden) {
    section.classList.remove('hidden');
    if (arrow) arrow.style.transform = 'rotate(180deg)';
  } else {
    section.classList.add('hidden');
    if (arrow) arrow.style.transform = 'rotate(0deg)';
  }
};

// 1. Report Reader Modal
window.openReportModal = function(id) {
  const published = window.adaEngine ? window.adaEngine.getPublished() : [];
  const r = published.find(item => item.id === id);
  if (!r) return;

  const sourcesList = (r.vectors || []).map(v => 
    `<a href="${escapeHtml(v)}" target="_blank" rel="noopener noreferrer" class="bg-surface-container border border-glass-stroke px-2.5 py-1 rounded font-code-sm text-xs text-primary hover:underline flex items-center gap-1 inline-block truncate max-w-full">
      <span class="material-symbols-outlined text-[12px]">link</span> ${escapeHtml(v)}
    </a>`
  ).join('') || '<span class="text-xs text-on-surface-variant">No direct web sources recorded</span>';

  const body = `
    <div class="space-y-6 font-body-md text-on-surface">
      <div class="flex flex-wrap items-center justify-between gap-4 border-b border-glass-stroke pb-4">
        <div>
          <div class="flex items-center gap-2 mb-1">
            <span class="font-code-sm text-xs text-primary">${r.id}</span>
            <span class="text-on-surface-variant">•</span>
            <span class="font-label-caps text-xs text-on-surface-variant">${r.category}</span>
          </div>
          <h2 class="text-xl font-bold text-on-surface">${escapeHtml(r.title)}</h2>
        </div>
        <div class="flex items-center gap-2 bg-primary/10 border border-primary/30 px-3 py-1.5 rounded text-primary font-code-sm text-sm">
          <span class="material-symbols-outlined text-sm">verified</span>
          Published
        </div>
      </div>

      <!-- 1. Display Generated LinkedIn Post FIRST -->
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <span class="font-label-caps text-xs text-primary uppercase font-bold tracking-wider flex items-center gap-1.5">
            <span class="material-symbols-outlined text-sm">post_add</span> Generated LinkedIn Post
          </span>
        </div>
        <div class="bg-surface-container-lowest p-5 rounded-xl border border-glass-stroke prose prose-invert max-w-none text-body-md whitespace-pre-wrap font-sans text-on-surface leading-relaxed select-text">
          ${escapeHtml(r.content)}
        </div>
      </div>

      <!-- 2. Interactive Button to Toggle Editorial Rationale & Sources -->
      <div class="border-t border-glass-stroke pt-4 space-y-3">
        <button id="toggle-rationale-btn-${r.id}" onclick="toggleRationale('${r.id}')" class="w-full py-2.5 px-4 bg-surface-container hover:bg-surface-container-high border border-glass-stroke rounded-lg font-label-caps text-xs text-on-surface hover:text-primary transition-colors flex items-center justify-between group">
          <span class="flex items-center gap-2">
            <span class="material-symbols-outlined text-primary text-base">psychology</span>
            <span class="font-bold">View Editorial Rationale & Sources</span>
          </span>
          <span class="material-symbols-outlined text-base transition-transform duration-200" id="rationale-arrow-${r.id}">expand_more</span>
        </button>

        <div id="rationale-section-${r.id}" class="hidden space-y-4 pt-2 transition-all">
          <div class="bg-surface-container-lowest/80 p-4 rounded-lg border border-glass-stroke font-code-sm text-sm text-on-surface-variant leading-relaxed">
            <strong class="text-primary block mb-1">Editorial Rationale:</strong>
            ${escapeHtml(r.summary)}
          </div>

          <div class="space-y-2">
            <h4 class="font-label-caps text-xs text-on-surface-variant uppercase">Discovery Sources</h4>
            <div class="flex flex-wrap gap-2">
              ${sourcesList}
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  const footer = `
    <button onclick="navigator.clipboard.writeText(\`${escapeHtml(r.content).replace(/`/g, '\\`').replace(/\${/g, '\\${')}\`); showToast('Post copied to clipboard');" class="px-4 py-2 bg-primary text-on-primary font-label-caps text-xs uppercase rounded hover:bg-primary-fixed transition-colors flex items-center gap-1.5">
      <span class="material-symbols-outlined text-sm">content_copy</span> Copy Post Text
    </button>
  `;

  createModalOverlay("report-modal", `LinkedIn Post Details — ${r.id}`, body, footer);
};

// 2. Cycle Log Detail Modal
window.openCycleModal = function(id) {
  const cycles = window.adaEngine ? window.adaEngine.getCycles() : [];
  const c = cycles.find(item => item.id === id) || {
    id,
    timestamp: new Date().toISOString(),
    status: "COMPLETE",
    headline: "Autonomous cycle execution detail",
    details: ["- Vector and source analysis completed"]
  };

  const body = `
    <div class="space-y-4 font-code-sm text-sm">
      <div class="flex items-center justify-between border-b border-glass-stroke pb-3">
        <span class="text-primary font-bold text-base">${c.id}</span>
        <span class="px-2.5 py-1 rounded text-xs font-label-caps ${c.status === 'RUNNING' ? 'bg-primary/10 text-primary border border-primary/30' : c.status === 'REJECTED' || c.status === 'FAILED' ? 'bg-error/10 text-error border border-error/30' : 'bg-surface-container text-on-surface-variant border border-glass-stroke'}">${c.status}</span>
      </div>
      <div class="text-on-surface font-bold">&gt; ${escapeHtml(c.headline)}</div>
      <div class="bg-surface-container-lowest p-4 rounded-lg border border-glass-stroke space-y-2 text-on-surface-variant max-h-64 overflow-y-auto">
        ${(c.details || []).map(d => `<div>${escapeHtml(d)}</div>`).join('')}
      </div>
      <div class="text-xs text-on-surface-variant">Timestamp: ${c.timestamp}</div>
    </div>
  `;

  createModalOverlay("cycle-modal", `Cycle Trace — ${c.id}`, body);
};

// 3. Spiked Detail Modal
window.openSpikeModal = function(id) {
  const spiked = window.adaEngine ? window.adaEngine.getSpiked() : [];
  const s = spiked.find(item => item.id === id);
  if (!s) return;

  const sourceLink = s.sourceUrl 
    ? `<a href="${escapeHtml(s.sourceUrl)}" target="_blank" rel="noopener noreferrer" class="text-primary hover:underline font-code-sm text-xs truncate block mt-1">${escapeHtml(s.sourceUrl)}</a>`
    : '';

  const body = `
    <div class="space-y-4">
      <div class="flex justify-between items-start border-b border-glass-stroke pb-3">
        <h3 class="text-lg font-bold text-on-surface">${escapeHtml(s.title)}</h3>
        <span class="bg-error/10 text-error border border-error/30 text-xs px-2.5 py-1 rounded font-label-caps">Spiked / Rejected</span>
      </div>
      <div>
        <strong class="font-label-caps text-xs text-on-surface-variant uppercase">Rejection Rationale:</strong>
        <p class="text-sm text-on-surface-variant mt-1">${escapeHtml(s.summary)}</p>
        ${sourceLink}
      </div>
      <div class="bg-surface p-3 rounded border border-glass-stroke font-code-sm text-xs text-error/90 space-y-1">
        <div class="font-label-caps text-[10px] text-on-surface-variant uppercase mb-1">Judge Evaluation Scores</div>
        ${(s.heuristic || []).map(h => `<div>${escapeHtml(h)}</div>`).join('')}
      </div>
      <div class="flex gap-4 text-xs text-on-surface-variant font-code-sm">
        <div>Agent: <span class="text-primary">${s.node}</span></div>
        <div>Date: <span class="text-on-surface">${s.timestamp}</span></div>
      </div>
    </div>
  `;

  createModalOverlay("spike-modal", `Rejected Topic Audit — ${s.id}`, body);
};

// Global top bar quick action triggers
function initGlobalModals() {
  // Settings Button in Sidebar & Header
  document.querySelectorAll('a[href="#"], button[title="Settings"]').forEach(el => {
    if (el.textContent.includes('Settings')) {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        openSettingsModal();
      });
    }
    if (el.textContent.includes('Support')) {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        openSupportModal();
      });
    }
  });

  // Header icons
  document.querySelectorAll('header button').forEach(btn => {
    const icon = btn.querySelector('.material-symbols-outlined');
    if (!icon) return;
    if (icon.textContent === 'memory') {
      btn.title = "Vector DB Memory Inspector";
      btn.addEventListener('click', openMemoryModal);
    }
    if (icon.textContent === 'sensors') {
      btn.title = "Sensor Stream Monitor";
      btn.addEventListener('click', openSensorModal);
    }
    if (icon.textContent === 'robot_2') {
      btn.title = "Agent Persona Status";
      btn.addEventListener('click', openDiagnosticsModal);
    }
  });
}

function openSettingsModal() {
  const settings = window.adaEngine ? window.adaEngine.getSettings() : {};
  const body = `
    <div class="space-y-4 font-body-md text-sm text-on-surface">
      <div class="space-y-2">
        <label class="font-label-caps text-xs text-primary block">Execution Mode</label>
        <select id="setting-mode" class="w-full bg-surface border border-glass-stroke rounded p-2 text-on-surface font-code-sm text-xs">
          <option value="local" ${!settings.useRealApi ? 'selected' : ''}>Embedded Autonomous Engine (Client Simulation)</option>
          <option value="api" ${settings.useRealApi ? 'selected' : ''}>Remote REST Agent API (Node.js Server)</option>
        </select>
      </div>

      <div class="space-y-2">
        <label class="font-label-caps text-xs text-on-surface-variant block">API Endpoint URL</label>
        <input id="setting-url" type="text" class="w-full bg-surface border border-glass-stroke rounded p-2 text-on-surface font-code-sm text-xs" value="${escapeHtml(settings.apiUrl || 'http://localhost:8000/api')}"/>
      </div>

      <div class="space-y-2">
        <label class="font-label-caps text-xs text-on-surface-variant block">API Secret Key</label>
        <input id="setting-key" type="password" class="w-full bg-surface border border-glass-stroke rounded p-2 text-on-surface font-code-sm text-xs" value="${escapeHtml(settings.apiKey || '')}"/>
      </div>

      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="font-label-caps text-xs text-on-surface-variant block">Cadence Interval</label>
          <input id="setting-interval" type="number" class="w-full bg-surface border border-glass-stroke rounded p-2 text-on-surface font-code-sm text-xs" value="${settings.autoCycleInterval || 150}"/>
        </div>
        <div>
          <label class="font-label-caps text-xs text-on-surface-variant block font-code-sm">Confidence Floor %</label>
          <input id="setting-floor" type="number" class="w-full bg-surface border border-glass-stroke rounded p-2 text-on-surface font-code-sm text-xs" value="${settings.confidenceFloor || 60}"/>
        </div>
      </div>
    </div>
  `;

  const footer = `
    <button onclick="saveSettingsFromModal()" class="px-4 py-2 bg-primary text-on-primary text-xs font-label-caps uppercase rounded hover:bg-primary-fixed transition-colors">Save Settings</button>
  `;

  createModalOverlay("settings-modal", "Engine & API Settings", body, footer);
}

window.saveSettingsFromModal = function() {
  const mode = document.getElementById("setting-mode").value;
  const apiUrl = document.getElementById("setting-url").value;
  const apiKey = document.getElementById("setting-key").value;
  const interval = parseInt(document.getElementById("setting-interval").value, 10);
  const floor = parseInt(document.getElementById("setting-floor").value, 10);

  if (window.adaEngine) {
    window.adaEngine.saveSettings({
      useRealApi: mode === "api",
      apiUrl,
      apiKey,
      autoCycleInterval: interval,
      confidenceFloor: floor
    });
  }

  closeModal("settings-modal");
  showToast("✓ Settings updated successfully");
};

function openSupportModal() {
  const body = `
    <div class="space-y-4 text-sm text-on-surface-variant">
      <p><strong>Ada Desk Documentation & Shortcuts:</strong></p>
      <ul class="list-disc pl-5 space-y-2 font-code-sm text-xs">
        <li><code class="text-primary">Ctrl + K</code> — Open global intelligence search</li>
        <li><code class="text-primary">Ctrl + I</code> — Initiate new vector analysis cycle</li>
        <li><code class="text-primary">Esc</code> — Close open overlay or drawer</li>
      </ul>
      <p>For API integration details, visit the <a href="api.html" class="text-primary hover:underline">API Reference page</a>.</p>
    </div>
  `;
  createModalOverlay("support-modal", "Ada Desk Support & Shortcuts", body);
}

function openMemoryModal() {
  const metrics = window.adaEngine ? window.adaEngine.getMetrics() : {};
  const body = `
    <div class="space-y-4 font-code-sm text-xs">
      <div class="flex justify-between items-center border-b border-glass-stroke pb-2">
        <span class="text-primary font-bold">SQLite & Chroma Vector Store</span>
        <span class="text-on-surface">Status: Persistent Database Active</span>
      </div>
      <div class="grid grid-cols-2 gap-4">
        <div class="bg-surface p-3 rounded border border-glass-stroke">
          <div class="text-on-surface-variant mb-1">LLM Model</div>
          <div class="text-primary font-bold">${escapeHtml(metrics.llmModel || 'Configured')}</div>
        </div>
        <div class="bg-surface p-3 rounded border border-glass-stroke">
          <div class="text-on-surface-variant mb-1">Publish Status</div>
          <div class="${metrics.canPublish ? 'text-primary' : 'text-error'} font-bold">${metrics.canPublish ? 'Ready to Publish' : 'Check LLM Key'}</div>
        </div>
      </div>
      <div class="text-on-surface-variant text-[11px]">
        Memory persistence stores embeddings in <code class="text-primary">./chroma_data</code> and agent state in SQLite database <code class="text-primary">post_generator.db</code>.
      </div>
    </div>
  `;
  createModalOverlay("memory-modal", "System Memory Inspector", body);
}

function openSensorModal() {
  const metrics = window.adaEngine ? window.adaEngine.getMetrics() : {};
  const body = `
    <div class="space-y-3 font-code-sm text-xs">
      <div class="flex items-center justify-between text-on-surface border-b border-glass-stroke pb-2">
        <span>Active Live Data Sources</span>
        <span class="status-dot text-primary"><span class="ping"></span><span class="dot"></span></span>
      </div>
      <div class="space-y-2">
        <div class="flex justify-between p-2 bg-surface rounded border border-glass-stroke">
          <span>Hacker News Algolia Feed</span>
          <span class="text-primary">ONLINE</span>
        </div>
        <div class="flex justify-between p-2 bg-surface rounded border border-glass-stroke">
          <span>arXiv Research Papers API</span>
          <span class="text-primary">ONLINE</span>
        </div>
        <div class="flex justify-between p-2 bg-surface rounded border border-glass-stroke">
          <span>GitHub Trending Repos API</span>
          <span class="text-primary">ONLINE</span>
        </div>
        <div class="flex justify-between p-2 bg-surface rounded border border-glass-stroke">
          <span>Tavily / Web Search</span>
          <span class="text-primary">ONLINE</span>
        </div>
      </div>
    </div>
  `;
  createModalOverlay("sensor-modal", "Live Discovery Sources", body);
}

function openDiagnosticsModal() {
  const metrics = window.adaEngine ? window.adaEngine.getMetrics() : {};
  const persona = window.AdaPersona?.getPersona() || { name: "Ada Engine", domain: "Autonomous Agent" };
  const body = `
    <div class="space-y-4 font-code-sm text-xs text-on-surface">
      <div class="flex items-center gap-3">
        <span class="material-symbols-outlined text-primary text-3xl">smart_toy</span>
        <div>
          <div class="font-bold text-base text-primary">${escapeHtml(persona.name)}</div>
          <div class="text-on-surface-variant">Domain: ${escapeHtml(persona.domain)} • AUTONOMOUS</div>
        </div>
      </div>
      <div class="grid grid-cols-3 gap-2 border-t border-glass-stroke pt-3 text-center">
        <div class="bg-surface p-2 rounded">
          <div class="text-[10px] text-on-surface-variant">Total Cycles</div>
          <div class="text-primary font-bold">${metrics.cycleCount || 0}</div>
        </div>
        <div class="bg-surface p-2 rounded">
          <div class="text-[10px] text-on-surface-variant">LLM Model</div>
          <div class="text-primary font-bold truncate">${escapeHtml(metrics.llmModel || 'Configured')}</div>
        </div>
        <div class="bg-surface p-2 rounded">
          <div class="text-[10px] text-on-surface-variant">Published Posts</div>
          <div class="text-on-surface font-bold">${metrics.articles24h || 0}</div>
        </div>
      </div>
    </div>
  `;
  createModalOverlay("diagnostics-modal", "Agent System Diagnostics", body);
}

/* ---------------------------------------------------------------------- */
/* Page Renderer Implementations                                          */
/* ---------------------------------------------------------------------- */

// Home Page
function initHomePage() {
  updateHomeMetrics();
}

function updateHomeMetrics() {
  if (!window.adaEngine) return;
  const metrics = window.adaEngine.getMetrics();
  const activity = metrics.activity || { state: "idle", detail: "Waiting for next scheduled cycle." };
  
  const focus = document.getElementById("current-focus");
  const drafted = document.getElementById("articles-drafted");
  const llmModelEl = document.getElementById("accuracy-confidence");
  const summary = document.getElementById("agent-activity-summary");
  const feed = document.getElementById("analysis-feed");

  const llmStatusVal = document.getElementById("llm-status-value");
  const nextRunVal = document.getElementById("next-run-value");
  const cyclesCountVal = document.getElementById("cycles-count-value");
  const spikedCountVal = document.getElementById("spiked-count-value");
  const llmModelVal = document.getElementById("llm-model-value");

  if (focus) focus.textContent = activity.articleTitle || "Idle / Monitoring sources";
  if (drafted) drafted.textContent = String(metrics.articles24h || 0);
  if (llmModelEl) llmModelEl.textContent = metrics.llmModel || "(Provider Default)";
  
  if (summary) {
    summary.textContent = activity.articleTitle
      ? `Currently ${activity.state}: "${activity.articleTitle}". ${activity.detail}`
      : activity.detail;
  }

  if (llmStatusVal) {
    llmStatusVal.textContent = metrics.canPublish ? "READY (Valid Key)" : "KEY ERROR";
    llmStatusVal.className = `font-code-sm text-code-sm ${metrics.canPublish ? 'text-primary' : 'text-error'}`;
  }

  if (nextRunVal) {
    if (metrics.nextRunAt) {
      const d = new Date(metrics.nextRunAt);
      nextRunVal.textContent = isNaN(d.getTime()) ? metrics.nextRunAt : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else {
      nextRunVal.textContent = metrics.active ? "Calculating..." : "Deactivated";
    }
  }

  if (cyclesCountVal) cyclesCountVal.textContent = String(metrics.cycleCount || 0);
  if (spikedCountVal) spikedCountVal.textContent = String(metrics.spikedCount || 0);
  if (llmModelVal) llmModelVal.textContent = metrics.llmModel ? metrics.llmModel.split('-')[0].toUpperCase() : "OK";

  if (feed) {
    const feedLines = window.adaEngine.getFeedLines ? window.adaEngine.getFeedLines() : (metrics.feed || []);
    let html = "";
    if (feedLines && feedLines.length > 0) {
      feedLines.forEach(line => {
        html += `<div class="flex gap-4 group hover:bg-surface-container-lowest/50 p-1 -ml-1 rounded transition-colors">
          <span class="text-on-surface-variant opacity-50 select-none">live</span>
          <span class="${line.tagColor || 'text-primary'}">[${escapeHtml(line.tag || 'INFO')}]</span>
          <span class="text-on-surface">${escapeHtml(line.text)}</span>
        </div>`;
      });
    } else {
      html = `<div class="flex gap-4 group hover:bg-surface-container-lowest/50 p-1 -ml-1 rounded transition-colors">
        <span class="text-on-surface-variant opacity-50 select-none">now</span>
        <span class="text-primary">[${escapeHtml((activity.state || "idle").toUpperCase())}]</span>
        <span class="text-on-surface">${escapeHtml(activity.detail || "Waiting for the next scheduled cycle.")}</span>
      </div>`;
    }
    html += `<div data-cursor class="flex gap-4 items-center mt-2"><span class="text-on-surface-variant opacity-50 select-none">live</span><span class="w-2 h-4 bg-primary animate-pulse"></span></div>`;
    feed.innerHTML = html;
  }
}

// Published Intelligence Page
function initPublishedPage() {
  renderPublishedList();

  // Filter toggle button & inputs
  const filterBtn = document.getElementById("published-filter-btn");
  const filterBar = document.getElementById("published-filter-bar");
  const searchInput = document.getElementById("published-search-input");
  const categorySelect = document.getElementById("published-category-select");
  const confidenceSelect = document.getElementById("published-confidence-select");
  const clearBtn = document.getElementById("published-clear-filter");

  if (filterBtn && filterBar) {
    filterBtn.addEventListener("click", () => {
      filterBar.classList.toggle("hidden");
    });
  }

  const triggerFilter = () => {
    renderPublishedList();
  };

  if (searchInput) searchInput.addEventListener("input", triggerFilter);
  if (categorySelect) categorySelect.addEventListener("change", triggerFilter);
  if (confidenceSelect) confidenceSelect.addEventListener("change", triggerFilter);

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      if (searchInput) searchInput.value = "";
      if (categorySelect) categorySelect.value = "ALL";
      if (confidenceSelect) confidenceSelect.value = "0";
      renderPublishedList();
    });
  }

  // View toggle
  document.querySelectorAll('[data-view-toggle]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('[data-view-toggle]').forEach(b => {
        b.classList.remove('bg-surface-container-high', 'text-on-surface');
        b.classList.add('text-on-surface-variant');
      });
      btn.classList.add('bg-surface-container-high', 'text-on-surface');
      btn.classList.remove('text-on-surface-variant');

      const mode = btn.dataset.viewToggle;
      const listContainer = document.querySelector('main .glass-panel .flex-col');
      if (listContainer) {
        if (mode === 'grid') {
          listContainer.classList.add('published-grid-view');
        } else {
          listContainer.classList.remove('published-grid-view');
        }
      }
    });
  });

  // Load older records
  const loadBtn = document.getElementById('load-older');
  if (loadBtn) {
    loadBtn.addEventListener('click', () => {
      loadBtn.innerHTML = '<span class="material-symbols-outlined text-sm animate-spin">sync</span> Loading older records…';
      setTimeout(() => {
        window.adaEngine.fetchOlderPublished();
        loadBtn.innerHTML = '[ ALL HISTORICAL RECORDS LOADED ]';
        showToast('Loaded archival records into Published stream');
      }, 700);
    });
  }
}

function renderPublishedList() {
  if (!window.adaEngine) return;
  const listContainer = document.querySelector('main .glass-panel .flex-col');
  if (!listContainer) return;

  const searchInput = document.getElementById("published-search-input");
  const categorySelect = document.getElementById("published-category-select");
  const badge = document.getElementById("active-filter-badge");

  const q = searchInput ? searchInput.value.trim().toLowerCase() : "";
  const cat = categorySelect ? categorySelect.value : "ALL";

  const isFiltered = Boolean(q || cat !== "ALL");
  if (badge) {
    if (isFiltered) badge.classList.remove("hidden");
    else badge.classList.add("hidden");
  }

  let published = window.adaEngine.getPublished();

  // Apply filtering
  if (q) {
    published = published.filter(r =>
      r.title.toLowerCase().includes(q) ||
      (r.summary && r.summary.toLowerCase().includes(q)) ||
      (r.vectors && r.vectors.some(v => v.toLowerCase().includes(q))) ||
      r.id.toLowerCase().includes(q)
    );
  }

  if (cat !== "ALL") {
    published = published.filter(r => r.category.toUpperCase() === cat.toUpperCase());
  }

  if (published.length === 0) {
    listContainer.innerHTML = `
      <div class="p-12 text-center space-y-3">
        <span class="material-symbols-outlined text-on-surface-variant text-4xl">article</span>
        <div class="text-on-surface font-headline-lg text-base">No Published Posts Found</div>
        <p class="text-on-surface-variant text-xs max-w-md mx-auto">No published LinkedIn posts match your current selection, or the backend agent cycle has not yet generated a post. Click "Initiate Cycle" to trigger post generation.</p>
        ${isFiltered ? `<button onclick="document.getElementById('published-clear-filter')?.click()" class="mt-2 px-4 py-2 bg-surface-container hover:bg-surface-container-high border border-glass-stroke rounded text-xs font-label-caps uppercase text-primary transition-colors">Clear Filters</button>` : ''}
      </div>
    `;
    return;
  }

  listContainer.innerHTML = published.map(r => `
    <div class="group relative grid grid-cols-1 md:grid-cols-[1fr_180px_140px_100px] gap-4 p-4 md:px-6 border-b border-glass-stroke hover:bg-surface-container-highest/30 transition-colors">
      <div class="absolute left-0 top-0 bottom-0 w-1 bg-primary scale-y-0 group-hover:scale-y-100 transition-transform origin-left"></div>
      <div class="flex flex-col justify-center min-w-0">
        <div class="flex items-center gap-2 mb-1">
          <span class="font-code-sm text-[10px] leading-none text-primary">${escapeHtml(r.id.slice(0, 12))}</span>
          <span class="w-1 h-1 rounded-full bg-glass-stroke"></span>
          <span class="font-label-caps text-[10px] leading-none text-on-surface-variant">${r.category}</span>
        </div>
        <h3 onclick="openReportModal('${r.id}')" class="font-body-md text-body-md text-on-surface truncate group-hover:text-primary transition-colors cursor-pointer">${escapeHtml(r.title)}</h3>
      </div>
      <div class="flex items-center font-code-sm text-code-sm text-on-surface-variant">${new Date(r.timestamp).toLocaleString()}</div>
      <div class="flex items-center">
        <div class="flex items-center gap-1.5 bg-primary/10 border border-primary/20 text-primary border px-2 py-1 rounded font-code-sm text-xs">
          <span class="material-symbols-outlined text-[14px]">link</span>
          ${(r.vectors || []).length} Sources
        </div>
      </div>
      <div class="hidden md:flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <button onclick="openReportModal('${r.id}')" class="p-1.5 text-on-surface-variant hover:text-on-surface rounded hover:bg-surface-container-lowest transition-colors" title="Open Post Rationale">
          <span class="material-symbols-outlined text-sm">open_in_new</span>
        </button>
      </div>
    </div>
  `).join('');
}

// Spiked Topics Page
function initSpikedPage() {
  renderSpikedList();
}

function renderSpikedList() {
  const container = document.getElementById("spike-list");
  if (!container || !window.adaEngine) return;

  const spiked = window.adaEngine.getSpiked();
  
  // Update header overview cards dynamically
  const totalSpikedEl = document.getElementById("total-spiked-count");
  const causeOverviewEl = document.getElementById("latest-rejection-cause");
  if (totalSpikedEl) totalSpikedEl.textContent = String(spiked.length);
  if (causeOverviewEl) {
    causeOverviewEl.textContent = spiked.length > 0 ? (spiked[0].cause || spiked[0].summary || "Rejected Topic") : "No Rejections";
  }

  if (spiked.length === 0) {
    container.innerHTML = `
      <div class="glass-panel p-12 text-center space-y-3 rounded-xl">
        <span class="material-symbols-outlined text-on-surface-variant text-4xl">check_circle</span>
        <div class="text-on-surface font-headline-lg text-base">No Rejected Topics Recorded</div>
        <p class="text-on-surface-variant text-xs max-w-md mx-auto">All evaluated topics in recent cycles passed quality assurance judges, or no cycles have run yet.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = spiked.map(s => `
    <article class="spike-item glass-panel p-6 rounded-xl pulse-border-error flex flex-col md:flex-row gap-6 relative overflow-hidden group">
      <div class="absolute left-0 top-0 bottom-0 w-1 bg-error/50"></div>
      <div class="flex-1 flex flex-col gap-3">
        <div class="flex items-start justify-between md:justify-start gap-4">
          <h3 onclick="openSpikeModal('${s.id}')" class="spike-title font-headline-lg-mobile text-headline-lg-mobile text-on-surface cursor-pointer hover:text-primary transition-colors">${escapeHtml(s.title)}</h3>
          <span class="font-label-caps text-label-caps px-2 py-1 rounded bg-error/10 text-error border border-error/20 whitespace-nowrap">${s.category}</span>
        </div>
        <p class="font-body-sm text-body-sm text-on-surface-variant line-clamp-2">${escapeHtml(s.summary)}</p>
        <div class="flex flex-wrap items-center gap-4 mt-2">
          <div class="flex items-center gap-1.5 text-on-surface-variant/70 font-code-sm text-xs">
            <span class="material-symbols-outlined text-[16px]">schedule</span> ${new Date(s.timestamp).toLocaleString()}
          </div>
          <div class="flex items-center gap-1.5 text-on-surface-variant/70 font-code-sm text-xs">
            <span class="material-symbols-outlined text-[16px]">smart_toy</span> Agent: ${escapeHtml(s.node)}
          </div>
        </div>
      </div>
      <div class="md:w-64 flex flex-col justify-between border-t md:border-t-0 md:border-l border-glass-stroke pt-4 md:pt-0 md:pl-6">
        <div class="mb-4">
          <span class="font-label-caps text-[10px] uppercase text-on-surface-variant block mb-1">Judge Evaluation</span>
          <div class="bg-surface p-2 rounded border border-glass-stroke font-code-sm text-[11px] text-error/80 leading-tight">
            ${(s.heuristic || []).join('<br>')}
          </div>
        </div>
        <button onclick="openSpikeModal('${s.id}')" class="w-full py-2 bg-surface-container hover:bg-surface-container-highest border border-glass-stroke rounded text-on-surface font-label-caps text-label-caps uppercase transition-colors flex items-center justify-center gap-2">
          <span class="material-symbols-outlined text-[16px]">visibility</span> View Details
        </button>
      </div>
    </article>
  `).join('');
}

window.handleReEvaluate = async function(id) {
  showToast(`Re-evaluation is disabled for LLM editorial rejections.`);
};

// Cycle Log Page
function initCycleLogPage() {
  renderCycleLogList();
}

function renderCycleLogList() {
  const container = document.querySelector(".terminal-scroll");
  if (!container || !window.adaEngine) return;

  const cycles = window.adaEngine.getCycles();

  if (cycles.length === 0) {
    container.innerHTML = `
      <div class="p-8 text-center text-on-surface-variant font-code-sm text-xs">
        [NO CYCLE LOGS PERSISTED IN CURRENT AGENT DATABASE]
      </div>
    `;
    return;
  }

  container.innerHTML = cycles.map(c => `
    <div onclick="openCycleModal('${c.id}')" class="group relative pl-6 border-l ${c.status === 'RUNNING' ? 'border-primary/30' : c.status === 'REJECTED' || c.status === 'FAILED' ? 'border-error/30' : 'border-glass-stroke'} hover:border-primary/50 transition-colors py-1 cursor-pointer">
      <div class="absolute -left-[5px] top-1.5 w-[9px] h-[9px] bg-surface border-2 ${c.status === 'RUNNING' ? 'border-primary shadow-[0_0_10px_rgba(78,222,163,0.5)]' : c.status === 'REJECTED' || c.status === 'FAILED' ? 'border-error' : 'border-glass-stroke'} rounded-full"></div>
      <div class="flex flex-col md:flex-row md:items-center gap-2 md:gap-4 mb-2">
        <span class="text-on-surface-variant font-semibold font-code-sm text-xs">${new Date(c.timestamp).toLocaleString()}</span>
        <span class="${c.status === 'RUNNING' ? 'text-primary font-bold' : c.status === 'REJECTED' || c.status === 'FAILED' ? 'text-error font-bold' : 'text-on-surface font-semibold'} font-code-sm">${c.id}</span>
        <span class="${c.status === 'RUNNING' ? 'bg-primary/10 text-primary border-primary/20' : c.status === 'REJECTED' || c.status === 'FAILED' ? 'bg-error/10 text-error border-error/20' : 'bg-outline-variant/30 text-on-surface-variant border-glass-stroke'} border px-2 py-0.5 rounded font-label-caps text-label-caps tracking-widest inline-flex items-center gap-1">
          <span class="material-symbols-outlined text-[14px]">${c.status === 'RUNNING' ? 'refresh' : c.status === 'REJECTED' || c.status === 'FAILED' ? 'error' : 'check_circle'}</span>
          ${c.status}
        </span>
      </div>
      <div class="text-on-surface font-semibold mb-1 font-code-sm">&gt; ${escapeHtml(c.headline)}</div>
      <div class="text-on-surface-variant pl-4 border-l border-glass-stroke ml-2 space-y-1 mt-2 font-code-sm text-xs">
        ${(c.details || []).map(d => `<div>${escapeHtml(d)}</div>`).join('')}
      </div>
    </div>
  `).join('');
}

// API Page Interactive Tester
function initApiPage() {
  const container = document.getElementById("init-agent");
  if (!container) return;

  let tester = document.getElementById("api-tester-widget");
  if (!tester) {
    tester = document.createElement("div");
    tester.id = "api-tester-widget";
    tester.className = "glass-panel p-6 rounded-xl border border-glass-stroke mt-8 space-y-4";
    tester.innerHTML = `
      <div class="flex items-center gap-2 text-primary font-label-caps text-xs">
        <span class="material-symbols-outlined text-sm">play_circle</span>
        Interactive FastAPI Endpoint Tester
      </div>
      <div class="flex gap-2">
        <select id="api-test-endpoint" class="bg-surface border border-glass-stroke rounded p-2 text-on-surface font-code-sm text-xs flex-1">
          <option value="health">GET /health — Service Health & LLM Status</option>
          <option value="init">POST /api/agent/init — Initialize/Trigger Agent</option>
          <option value="feed">GET /api/agent/feed — Read Published Posts</option>
          <option value="status">GET /api/agent/status — Read Agent Status</option>
          <option value="rejected">GET /api/agent/rejected — Read Spiked Topics Audit</option>
          <option value="activity">GET /api/agent/activity — Read Active Cycle Progress</option>
        </select>
        <button id="run-api-test" class="bg-primary text-on-primary font-label-caps text-xs px-4 py-2 rounded hover:bg-primary-fixed transition-colors">Send Request</button>
      </div>
      <div class="bg-black p-4 rounded-lg border border-glass-stroke font-code-sm text-xs overflow-x-auto text-primary">
        <pre><code id="api-test-result">// Select endpoint and click "Send Request" to test live execution</code></pre>
      </div>
    `;
    container.appendChild(tester);

    document.getElementById("run-api-test").addEventListener("click", async () => {
      const endpoint = document.getElementById("api-test-endpoint").value;
      const resultBox = document.getElementById("api-test-result");
      resultBox.textContent = "// Sending request to FastAPI backend…";

      try {
        let data;
        if (endpoint === "health") data = await window.AdaAgentAPI.fetchHealth();
        if (endpoint === "init") data = await window.AdaAgentAPI.initiateCycle();
        if (endpoint === "feed") data = await window.AdaAgentAPI._request(`/agent/feed?agentId=${encodeURIComponent(localStorage.getItem("ada_backend_agent_id") || "")}`);
        if (endpoint === "status") data = await window.AdaAgentAPI._request(`/agent/status?agentId=${encodeURIComponent(localStorage.getItem("ada_backend_agent_id") || "")}`);
        if (endpoint === "rejected") data = await window.AdaAgentAPI._request(`/agent/rejected?agentId=${encodeURIComponent(localStorage.getItem("ada_backend_agent_id") || "")}`);
        if (endpoint === "activity") data = await window.AdaAgentAPI._request(`/agent/activity?agentId=${encodeURIComponent(localStorage.getItem("ada_backend_agent_id") || "")}`);

        resultBox.textContent = JSON.stringify(data, null, 2);
      } catch (err) {
        resultBox.textContent = `// Error: ${err.message}`;
      }
    });
  }
}

/* Helper Utilities */
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatMarkdown(text) {
  if (!text) return '';
  return escapeHtml(text)
    .replace(/^## (.*$)/gim, '<h3 class="text-base font-bold text-primary mt-4 mb-2">$1</h3>')
    .replace(/^### (.*$)/gim, '<h4 class="text-sm font-bold text-on-surface mt-3 mb-1">$1</h4>')
    .replace(/^\- (.*$)/gim, '<li class="ml-4 list-disc text-on-surface-variant">$1</li>');
}
