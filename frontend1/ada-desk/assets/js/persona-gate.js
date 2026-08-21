/**
 * Persona gate.
 *
 * Every page is bound to exactly one agent. Until a persona has been initialised the
 * dashboard shows nothing but this gate, and once it has, every request carries that
 * agent's id. The dashboard previously fell back to "whichever agent the backend
 * listed first", which meant it could display a different persona's feed entirely.
 */
(function () {
  const AGENT_KEY = "ada_backend_agent_id";
  const PERSONA_KEY = "ada_persona";

  const DOMAINS = [
    "AI Research & Machine Learning",
    "AI Security Research",
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

    /** Called when the backend no longer recognises the stored agent. */
    forget(reason) {
      this.clear();
      showGate(reason || "That agent no longer exists on the backend. Initialise a new one.");
    },

    async initialise(name, domain, voiceSamples) {
      const persona = { name, domain };
      // Only sent when the user actually pasted something. An empty array would
      // replace the preset's hand-written samples with nothing, leaving the writer
      // no examples at all.
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
      <div class="w-full max-w-md rounded-2xl border border-glass-stroke bg-surface-container-lowest p-8 shadow-2xl">
        <p class="font-mono text-xs tracking-[0.18em] text-on-surface-variant mb-2">INITIALISE PERSONA</p>
        <h1 class="font-headline-lg text-2xl font-bold text-primary mb-1">Autonomous desk</h1>
        <p class="text-sm text-on-surface-variant mb-6">
          The agent publishes only within the domain you choose here.
        </p>

        <label class="block text-xs font-mono tracking-wider text-on-surface-variant mb-1">PERSONA NAME</label>
        <input id="ada-gate-name" value="Distill" autocomplete="off"
          class="w-full mb-4 rounded-lg bg-surface-container px-3 py-2 text-on-surface border border-glass-stroke focus:border-primary outline-none" />

        <label class="block text-xs font-mono tracking-wider text-on-surface-variant mb-1">DOMAIN</label>
        <select id="ada-gate-domain"
          class="w-full mb-6 rounded-lg bg-surface-container px-3 py-2 text-on-surface border border-glass-stroke focus:border-primary outline-none">
          ${DOMAINS.map((d) => `<option value="${d}">${d}</option>`).join("")}
        </select>

        <details class="mb-4 rounded-lg border border-glass-stroke bg-surface-container/40 p-3">
          <summary class="cursor-pointer text-sm text-on-surface">
            Write in your own voice <span class="text-on-surface-variant">(optional)</span>
          </summary>
          <p class="mt-3 mb-2 text-xs text-on-surface-variant">
            Paste two or three posts you have written. The agent matches how you
            actually write far more closely from examples than from a description of
            your tone. Separate each post with a blank line.
          </p>
          <textarea id="ada-gate-voice" rows="6"
            class="w-full rounded-lg border border-glass-stroke bg-surface p-3 text-xs text-on-surface outline-none focus:border-primary focus:ring-1 focus:ring-primary placeholder:text-on-surface-variant/50"
            placeholder="Paste a post you have written...&#10;&#10;Paste another..."></textarea>
        </details>

        <button id="ada-gate-submit"
          class="w-full rounded-lg bg-primary px-4 py-2.5 font-semibold text-surface-container-lowest hover:opacity-90 disabled:opacity-50">
          Initialise agent
        </button>

        <p id="ada-gate-error" class="mt-4 text-sm text-red-400 hidden"></p>
        <p class="mt-4 text-xs text-on-surface-variant">
          Calling this once starts the autonomous loop. It is idempotent: the same name
          and domain returns the existing agent rather than creating a second one.
        </p>
      </div>`;
  }

  function showGate(message) {
    if (document.getElementById("ada-persona-gate")) return;

    const overlay = document.createElement("div");
    overlay.id = "ada-persona-gate";
    overlay.className =
      "fixed inset-0 z-[100] flex items-center justify-center bg-background/95 backdrop-blur-sm p-6";
    overlay.innerHTML = gateMarkup();
    document.body.appendChild(overlay);

    const nameInput = overlay.querySelector("#ada-gate-name");
    const domainInput = overlay.querySelector("#ada-gate-domain");
    const voiceInput = overlay.querySelector("#ada-gate-voice");
    const submit = overlay.querySelector("#ada-gate-submit");
    const error = overlay.querySelector("#ada-gate-error");

    if (message) {
      error.textContent = message;
      error.classList.remove("hidden");
    }

    async function go() {
      const name = nameInput.value.trim();
      const domain = domainInput.value;

      // Blank lines separate posts. Anything too short to show a voice is dropped
      // rather than sent, since a stray line would dilute the real samples.
      const voiceSamples = (voiceInput?.value || "")
        .split(/\n\s*\n/)
        .map((s) => s.trim())
        .filter((s) => s.split(/\s+/).length >= 30)
        .slice(0, 5);
      if (!name) {
        error.textContent = "Enter a persona name.";
        error.classList.remove("hidden");
        return;
      }

      submit.disabled = true;
      submit.textContent = "Initialising...";
      error.classList.add("hidden");
      try {
        await AdaPersona.initialise(name, domain, voiceSamples);
        window.location.reload();
      } catch (err) {
        error.textContent = `${err.message}. Is the backend running on ${apiBase()}?`;
        error.classList.remove("hidden");
        submit.disabled = false;
        submit.textContent = "Initialise agent";
      }
    }

    submit.addEventListener("click", go);
    nameInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") go();
    });
  }

  /** Put the active persona in the sidebar so the page states which agent it shows. */
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

  document.addEventListener("DOMContentLoaded", () => {
    if (!AdaPersona.getAgentId()) {
      showGate();
      return;
    }
    paintPersona();
    wireChangePersona();
  });
})();
