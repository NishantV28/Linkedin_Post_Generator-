/**
 * Distill — Persona Gate & Onboarding Modal.
 *
 * Configures the user's autonomous AI publishing agent:
 * - Agent / Persona Name (the byline for generated posts)
 * - Domain (strictly curated AI fields or custom AI domain)
 * - Optional custom writing voice samples
 */
(function () {
  const AGENT_KEY = "ada_backend_agent_id";
  const PERSONA_KEY = "ada_persona";

  const AI_DOMAINS = [
    "AI Research & Machine Learning",
    "AI Agents & Autonomous Systems",
    "LLM Reasoning, Alignment & Fine-tuning",
    "Computer Vision & Multimodal AI",
    "Robotics & Embodied AI",
    "Generative Models & Diffusion",
    "AI Security & Red Teaming",
    "AI Infrastructure & Efficient Inference",
    "Custom AI Subfield..."
  ];

  function apiBase() {
    const configured = window.adaEngine && window.adaEngine.getSettings
      ? window.adaEngine.getSettings().apiUrl
      : null;
    return (configured || "http://127.0.0.1:8000/api").replace(/\/$/, "");
  }

  const AdaPersona = {
    getAgentId() {
      return localStorage.getItem(AGENT_KEY);
    },

    getPersona() {
      try {
        return JSON.parse(localStorage.getItem(PERSONA_KEY)) || null;
      } catch (_) {
        return null;
      }
    },

    save(agentId, persona) {
      localStorage.setItem(AGENT_KEY, agentId);
      localStorage.setItem(PERSONA_KEY, JSON.stringify(persona));
    },

    clear() {
      localStorage.removeItem(AGENT_KEY);
      localStorage.removeItem(PERSONA_KEY);
    },

    /** Called when the backend no longer recognises the stored agent or when switching personas. */
    forget(reason) {
      this.clear();
      showGate(reason || "Configure a new publishing agent to begin.");
    },

    async initialise(name, domain, voiceSamples) {
      const persona = { name, domain };
      if (voiceSamples && voiceSamples.length) persona.voiceSamples = voiceSamples;

      const response = await fetch(`${apiBase()}/agent/init`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ persona }),
      });
      if (!response.ok) {
        throw new Error(`Initialisation failed (${response.status}): ${await response.text()}`);
      }
      const { agentId } = await response.json();
      this.save(agentId, { name, domain });
      return agentId;
    },
  };

  function gateMarkup() {
    return `
      <div class="w-full max-w-lg rounded-2xl border border-glass-stroke bg-surface-container-lowest p-8 shadow-2xl space-y-5 animate-fade-in relative overflow-hidden">
        <div class="absolute -top-12 -right-12 w-36 h-36 bg-primary/15 rounded-full blur-3xl pointer-events-none"></div>
        <div class="flex items-center gap-2.5">
          <div class="w-7 h-7 rounded bg-primary/20 border border-primary/40 flex items-center justify-center text-primary">
            <span class="material-symbols-outlined text-base">auto_awesome</span>
          </div>
          <p class="font-code-sm text-xs font-bold tracking-[0.2em] text-primary uppercase">DISTILL • AGENT ONBOARDING</p>
        </div>
        
        <div>
          <h1 class="font-headline-lg text-2xl font-extrabold text-on-surface tracking-tight mb-1">Create Your Publishing Persona</h1>
          <p class="text-xs text-on-surface-variant leading-relaxed">
            Distill autonomously researches papers, repositories, and technical breakthroughs in your selected AI domain and drafts high-signal LinkedIn posts under your chosen agent identity.
          </p>
        </div>

        <div class="space-y-4 pt-1">
          <div>
            <label class="block text-[11px] font-label-caps tracking-wider text-on-surface uppercase font-bold mb-1.5 flex items-center justify-between">
              <span>Agent / Persona Name</span>
              <span class="text-on-surface-variant/70 lowercase font-normal">e.g. Distill, NeuroPulse, Alex Rivera</span>
            </label>
            <input id="ada-gate-name" value="Distill" autocomplete="off" placeholder="Enter your agent or brand name..."
              class="w-full rounded-lg bg-surface border border-glass-stroke px-3.5 py-2.5 text-sm text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all" />
          </div>

          <div>
            <label class="block text-[11px] font-label-caps tracking-wider text-on-surface uppercase font-bold mb-1.5 flex items-center justify-between">
              <span>Domain (AI Field)</span>
              <span class="text-primary text-[10px]">AI Focus Only</span>
            </label>
            <select id="ada-gate-domain"
              class="w-full rounded-lg bg-surface border border-glass-stroke px-3.5 py-2.5 text-sm text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all cursor-pointer">
              ${AI_DOMAINS.map((d) => `<option value="${d}">${d}</option>`).join("")}
            </select>
          </div>

          <div id="ada-gate-custom-domain-container" class="hidden">
            <label class="block text-[11px] font-label-caps tracking-wider text-primary uppercase font-bold mb-1.5">
              Specify Custom AI Subfield
            </label>
            <input id="ada-gate-custom-domain" autocomplete="off" placeholder="e.g. AI for Healthcare, Audio & Speech Generation, Neuromorphic AI..."
              class="w-full rounded-lg bg-surface border border-primary/40 px-3.5 py-2.5 text-sm text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all" />
          </div>

          <details class="rounded-lg border border-glass-stroke bg-surface/60 p-3.5 group">
            <summary class="cursor-pointer text-xs font-semibold text-on-surface flex items-center justify-between">
              <span class="flex items-center gap-1.5">
                <span class="material-symbols-outlined text-sm text-secondary">record_voice_over</span>
                Custom Voice & Tone Samples <span class="text-on-surface-variant font-normal">(optional)</span>
              </span>
              <span class="material-symbols-outlined text-xs text-on-surface-variant group-open:rotate-180 transition-transform">expand_more</span>
            </summary>
            <p class="mt-2.5 mb-2 text-[11px] text-on-surface-variant leading-relaxed">
              Paste 1 to 3 sample LinkedIn posts or paragraphs in your preferred tone. Separate each post with a blank line.
            </p>
            <textarea id="ada-gate-voice" rows="4"
              class="w-full rounded-lg border border-glass-stroke bg-surface p-2.5 text-xs text-on-surface outline-none focus:border-primary focus:ring-1 focus:ring-primary placeholder:text-on-surface-variant/40"
              placeholder="Paste a sample post you wrote...&#10;&#10;Paste another..."></textarea>
          </details>
        </div>

        <button id="ada-gate-submit"
          class="w-full rounded-lg bg-primary hover:bg-primary-fixed text-on-primary py-3 font-label-caps uppercase text-xs tracking-wider font-bold transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50">
          <span class="material-symbols-outlined text-sm">rocket_launch</span>
          Initialize Agent & Launch Desk
        </button>

        <p id="ada-gate-error" class="text-xs text-error hidden text-center bg-error/10 border border-error/20 p-2 rounded"></p>
        
        <p class="text-[10px] text-on-surface-variant text-center font-code-sm">
          Distill continuously scans arXiv, HackerNews, GitHub, and research feeds to match this domain.
        </p>
      </div>`;
  }

  function showGate(message) {
    if (document.getElementById("ada-persona-gate")) return;

    const overlay = document.createElement("div");
    overlay.id = "ada-persona-gate";
    overlay.className =
      "fixed inset-0 z-[100] flex items-center justify-center bg-background/90 backdrop-blur-md p-6";
    overlay.innerHTML = gateMarkup();
    document.body.appendChild(overlay);

    const nameInput = overlay.querySelector("#ada-gate-name");
    const domainSelect = overlay.querySelector("#ada-gate-domain");
    const customDomainContainer = overlay.querySelector("#ada-gate-custom-domain-container");
    const customDomainInput = overlay.querySelector("#ada-gate-custom-domain");
    const voiceInput = overlay.querySelector("#ada-gate-voice");
    const submit = overlay.querySelector("#ada-gate-submit");
    const error = overlay.querySelector("#ada-gate-error");

    domainSelect.addEventListener("change", () => {
      if (domainSelect.value === "Custom AI Subfield...") {
        customDomainContainer.classList.remove("hidden");
        customDomainInput.focus();
      } else {
        customDomainContainer.classList.add("hidden");
      }
    });

    if (message) {
      error.textContent = message;
      error.classList.remove("hidden");
    }

    async function go() {
      const name = nameInput.value.trim();
      let domain = domainSelect.value;

      if (domain === "Custom AI Subfield...") {
        domain = customDomainInput.value.trim();
        if (!domain) {
          error.textContent = "Please enter your custom AI subfield or domain.";
          error.classList.remove("hidden");
          return;
        }
      }

      const voiceSamples = (voiceInput?.value || "")
        .split(/\n\s*\n/)
        .map((s) => s.trim())
        .filter((s) => s.split(/\s+/).length >= 15)
        .slice(0, 5);

      if (!name) {
        error.textContent = "Please enter an agent / persona name.";
        error.classList.remove("hidden");
        return;
      }

      submit.disabled = true;
      submit.innerHTML = `<span class="material-symbols-outlined text-sm animate-spin">sync</span> Initializing Agent…`;
      error.classList.add("hidden");

      try {
        await AdaPersona.initialise(name, domain, voiceSamples);
        window.location.reload();
      } catch (err) {
        error.textContent = `${err.message}. Is the backend running on ${apiBase()}?`;
        error.classList.remove("hidden");
        submit.disabled = false;
        submit.innerHTML = `<span class="material-symbols-outlined text-sm">rocket_launch</span> Initialize Agent & Launch Desk`;
      }
    }

    submit.addEventListener("click", go);
    nameInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") go();
    });
    customDomainInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") go();
    });
  }

  /** Put the active persona in the sidebar, header, and profile cards. */
  function paintPersona() {
    const persona = AdaPersona.getPersona();
    if (!persona) return;

    document.querySelectorAll("[data-persona-name]").forEach((el) => {
      el.textContent = persona.name;
    });
    document.querySelectorAll("[data-persona-domain]").forEach((el) => {
      el.textContent = persona.domain;
    });

    const heading = document.querySelector("aside h2");
    if (heading) heading.textContent = persona.name;
    const domainLabel = document.querySelector("aside .ada-domain-label");
    if (domainLabel) domainLabel.textContent = persona.domain;
  }

  function wireChangePersona() {
    document.querySelectorAll("[data-change-persona]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        AdaPersona.clear();
        window.location.reload();
      });
    });
  }

  window.AdaPersona = AdaPersona;
  window.showPersonaGate = showGate;

  document.addEventListener("DOMContentLoaded", () => {
    if (!AdaPersona.getAgentId()) {
      showGate();
      return;
    }
    paintPersona();
    wireChangePersona();
  });
})();
