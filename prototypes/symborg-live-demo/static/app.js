const scenarios = {
  dickens:
    "A: I think Great Expectations is less about class mobility and more about shame.\nB: Interesting. What do you think?",
  meeting:
    "A: We need to decide if this startup idea is an MVP or just a feature.\nB: The investor asked about pricing, user pain, and weekly usage.",
  clinical:
    "Doctor: Where is the pain worse?\nContext note: the patient has neck pain that increases at night and needs help changing position.",
};

const els = {
  transcript: document.querySelector("#transcript"),
  delivery: document.querySelector("#delivery"),
  userSignal: document.querySelector("#userSignal"),
  pauseMs: document.querySelector("#pauseMs"),
  minScore: document.querySelector("#minScore"),
  cognitiveLoad: document.querySelector("#cognitiveLoad"),
  loadValue: document.querySelector("#loadValue"),
  userSpeaking: document.querySelector("#userSpeaking"),
  walking: document.querySelector("#walking"),
  driving: document.querySelector("#driving"),
  assistiveMode: document.querySelector("#assistiveMode"),
  neuralResearch: document.querySelector("#neuralResearch"),
  runButton: document.querySelector("#runButton"),
  packetList: document.querySelector("#packetList"),
  routeList: document.querySelector("#routeList"),
  topicBadge: document.querySelector("#topicBadge"),
  gateBadge: document.querySelector("#gateBadge"),
  statusPill: document.querySelector("#statusPill"),
  meanScore: document.querySelector("#meanScore"),
  deliveredCount: document.querySelector("#deliveredCount"),
  suppressedCount: document.querySelector("#suppressedCount"),
  bestType: document.querySelector("#bestType"),
};

let activeScenario = "dickens";

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function normalizeModality(value) {
  return String(value || "suppress").replaceAll("_", " ");
}

function requestPayload() {
  const delivery = els.delivery.value;
  return {
    scenario: activeScenario,
    transcript: els.transcript.value,
    delivery,
    user_signal: els.userSignal.value,
    pause_ms: Number(els.pauseMs.value || 0),
    min_score: Number(els.minScore.value || 0.65),
    cognitive_load: Number(els.cognitiveLoad.value || 0.35),
    user_is_speaking: els.userSpeaking.checked,
    walking: els.walking.checked,
    driving: els.driving.checked,
    assistive_mode: els.assistiveMode.checked,
    neural_research_mode: els.neuralResearch.checked,
    has_audio: delivery === "audio_whisper" || delivery === "assistive",
    has_ar: delivery === "ar",
    has_haptics: delivery === "haptic",
    has_screen: delivery === "screen" || delivery === "assistive",
    has_assistive_ui: els.assistiveMode.checked,
    has_neural_research_output: els.neuralResearch.checked,
  };
}

function scoreCell(label, value) {
  return `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function renderPackets(items) {
  if (!items.length) {
    els.packetList.innerHTML = `<div class="empty">No packet delivered</div>`;
    return;
  }

  els.packetList.innerHTML = items
    .map((item) => {
      const packet = item.packet;
      const score = item.score || {};
      const warnings = score.warnings || packet.warnings || [];
      return `
        <article class="packet">
          <div class="packet-head">
            <span class="packet-type">${escapeHtml(packet.packet_type)}</span>
            <span class="score">${Number(score.total_score || 0).toFixed(3)}</span>
          </div>
          <div class="cue">${escapeHtml(packet.cue)}</div>
          <div class="meta-grid">
            ${scoreCell("Confidence", Number(packet.confidence || 0).toFixed(2))}
            ${scoreCell("Words", packet.word_count || 0)}
            ${scoreCell("Use", packet.expected_use || "think")}
            ${scoreCell("Load", packet.cognitive_load || 0)}
          </div>
          ${
            warnings.length
              ? `<div class="warning-list">${warnings
                  .map((warning) => `<span class="warning">${escapeHtml(warning)}</span>`)
                  .join("")}</div>`
              : ""
          }
        </article>
      `;
    })
    .join("");
}

function renderRoutes(items, suppressed) {
  const deliveredRoutes = items.map((item) => ({ packet: item.packet, route: item.route }));
  const suppressedRoutes = suppressed.map((item) => ({
    packet: item.packet,
    route: {
      modality: "suppress",
      reason: (item.reasons || []).join(", "),
      render_text: "",
      suppressed: true,
    },
  }));
  const routes = [...deliveredRoutes, ...suppressedRoutes];

  if (!routes.length) {
    els.routeList.innerHTML = `<div class="empty">No route decision</div>`;
    return;
  }

  els.routeList.innerHTML = routes
    .map(({ packet, route }) => `
      <article class="route-item ${route.suppressed ? "is-suppressed" : ""}">
        <div class="route-head">
          <span class="route-modality">${escapeHtml(normalizeModality(route.modality))}</span>
          <span class="packet-type">${escapeHtml(packet.packet_type)}</span>
        </div>
        <div class="route-reason">${escapeHtml(route.reason || "routed")}</div>
        ${
          route.render_text
            ? `<div class="route-text">${escapeHtml(route.render_text)}</div>`
            : ""
        }
      </article>
    `)
    .join("");
}

function renderTelemetry(data) {
  els.topicBadge.textContent = data.topic || "unknown";
  els.gateBadge.textContent = data.state?.gate_open ? "gate open" : "gate closed";
  els.gateBadge.style.color = data.state?.gate_open ? "var(--mint)" : "var(--amber)";
  els.meanScore.textContent = Number(data.summary?.mean_score || 0).toFixed(3);
  els.deliveredCount.textContent = String(data.delivered?.length || 0);
  els.suppressedCount.textContent = String(data.suppressed?.length || 0);
  els.bestType.textContent = data.summary?.best_packet_type || "none";
}

async function runPipeline() {
  els.statusPill.textContent = "Running";
  els.statusPill.style.color = "var(--amber)";
  els.runButton.disabled = true;

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload()),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.error || "Request failed");

    renderPackets(data.delivered || []);
    renderRoutes(data.delivered || [], data.suppressed || []);
    renderTelemetry(data);
    els.statusPill.textContent = "Ready";
    els.statusPill.style.color = "var(--mint)";
  } catch (error) {
    els.statusPill.textContent = "Error";
    els.statusPill.style.color = "var(--red)";
    els.packetList.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
    els.routeList.innerHTML = `<div class="empty">No route decision</div>`;
  } finally {
    els.runButton.disabled = false;
  }
}

document.querySelectorAll("[data-scenario]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-scenario]").forEach((item) => item.classList.remove("is-active"));
    button.classList.add("is-active");
    activeScenario = button.dataset.scenario;
    els.transcript.value = scenarios[activeScenario];
    els.assistiveMode.checked = activeScenario === "clinical";
    els.delivery.value = activeScenario === "clinical" ? "assistive" : "screen";
    runPipeline();
  });
});

els.cognitiveLoad.addEventListener("input", () => {
  els.loadValue.textContent = Number(els.cognitiveLoad.value).toFixed(2);
});

els.runButton.addEventListener("click", runPipeline);

els.transcript.value = scenarios.dickens;
runPipeline();
