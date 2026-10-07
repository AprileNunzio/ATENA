import { I18nManager } from './shared/i18n/manager.js';
const i18n = new I18nManager();
window.i18n = i18n;

document.addEventListener('DOMContentLoaded', async () => {
  await i18n.setLanguage('it', ['dashboard']);
  const langSelect = document.getElementById('lang-selector');
  if(langSelect) {
    langSelect.value = 'it';
    langSelect.addEventListener('change', async (e) => {
      await i18n.setLanguage(e.target.value, ['dashboard']);
    });
  }
});

const queryInput = document.getElementById("query-input");
const submitBtn = document.getElementById("submit-btn");
const thinkingPanel = document.getElementById("thinking-panel");
const thinkingHeader = document.getElementById("thinking-header");
const thinkingContent = document.getElementById("thinking-content");
const responsePanel = document.getElementById("response-panel");
const responseContent = document.getElementById("response-content");
const toolsCard = document.getElementById("tools-card");
const latencyMetric = document.getElementById("metric-latency");
const strategyMetric = document.getElementById("metric-strategy");
const chips = document.querySelectorAll(".chip");

const whiteboardSurface = document.getElementById("whiteboard-surface");
const whiteboardCanvas = document.getElementById("whiteboard-canvas");
const wbBtnBox = document.getElementById("wb-btn-box");
const wbBtnArrow = document.getElementById("wb-btn-arrow");
const wbBtnClear = document.getElementById("wb-btn-clear");
const wbBtnClose = document.getElementById("wb-btn-close");
const wbStatus = document.getElementById("wb-status");

let isStreaming = false;
let ctx = whiteboardCanvas ? whiteboardCanvas.getContext("2d") : null;
let isDrawing = false;
let lastX = 0;
let lastY = 0;
let shapes = [];

function initWhiteboard() {
  if (!whiteboardCanvas || !ctx) return;
  whiteboardCanvas.width = whiteboardCanvas.offsetWidth || 900;
  whiteboardCanvas.height = whiteboardCanvas.offsetHeight || 380;
  drawWhiteboardGrid();
}

function drawWhiteboardGrid() {
  if (!ctx) return;
  ctx.fillStyle = "#020617";
  ctx.fillRect(0, 0, whiteboardCanvas.width, whiteboardCanvas.height);
  ctx.strokeStyle = "rgba(0, 240, 255, 0.05)";
  ctx.lineWidth = 1;
  const step = 30;
  for (let x = 0; x < whiteboardCanvas.width; x += step) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, whiteboardCanvas.height);
    ctx.stroke();
  }
  for (let y = 0; y < whiteboardCanvas.height; y += step) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(whiteboardCanvas.width, y);
    ctx.stroke();
  }
}

function redrawShapes() {
  drawWhiteboardGrid();
  shapes.forEach(s => {
    if (s.type === "box") {
      ctx.fillStyle = "rgba(0, 240, 255, 0.12)";
      ctx.strokeStyle = "#00f0ff";
      ctx.lineWidth = 2;
      ctx.fillRect(s.x, s.y, s.w, s.h);
      ctx.strokeRect(s.x, s.y, s.w, s.h);
      ctx.fillStyle = "#ffffff";
      ctx.font = "13px monospace";
      ctx.fillText(s.label || "Modulo Atena", s.x + 12, s.y + 30);
    } else if (s.type === "arrow") {
      ctx.strokeStyle = "#10b981";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(s.x1, s.y1);
      ctx.lineTo(s.x2, s.y2);
      ctx.stroke();
      ctx.fillStyle = "#10b981";
      ctx.beginPath();
      ctx.arc(s.x2, s.y2, 5, 0, Math.PI * 2);
      ctx.fill();
    }
  });
}

if (whiteboardCanvas) {
  whiteboardCanvas.addEventListener("mousedown", (e) => {
    isDrawing = true;
    const rect = whiteboardCanvas.getBoundingClientRect();
    lastX = e.clientX - rect.left;
    lastY = e.clientY - rect.top;
  });

  whiteboardCanvas.addEventListener("mousemove", (e) => {
    if (!isDrawing || !ctx) return;
    const rect = whiteboardCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 2;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(lastX, lastY);
    ctx.lineTo(x, y);
    ctx.stroke();
    lastX = x;
    lastY = y;
  });

  window.addEventListener("mouseup", () => {
    isDrawing = false;
  });
}

if (wbBtnBox) {
  wbBtnBox.addEventListener("click", () => {
    const rx = 40 + (shapes.length * 50) % 600;
    const ry = 50 + (shapes.length * 35) % 200;
    shapes.push({ type: "box", x: rx, y: ry, w: 160, h: 50, label: `Service #${shapes.length + 1}` });
    redrawShapes();
    wbStatus.textContent = `Aggiunto componente architetturale #${shapes.length}`;
  });
}

if (wbBtnArrow) {
  wbBtnArrow.addEventListener("click", () => {
    shapes.push({ type: "arrow", x1: 60, y1: 100, x2: 240, y2: 100 });
    redrawShapes();
    wbStatus.textContent = i18n.translate('dashboard', 'dynamic.whiteboard_traced');
  });
}

if (wbBtnClear) {
  wbBtnClear.addEventListener("click", () => {
    shapes = [];
    drawWhiteboardGrid();
    wbStatus.textContent = i18n.translate('dashboard', 'dynamic.whiteboard_cleared');
  });
}

if (wbBtnClose) {
  wbBtnClose.addEventListener("click", () => {
    if (whiteboardSurface) whiteboardSurface.classList.remove("active");
  });
}

function openWhiteboardSurface() {
  if (whiteboardSurface) {
    whiteboardSurface.classList.add("active");
    initWhiteboard();
    if (shapes.length === 0) {
      shapes.push({ type: "box", x: 60, y: 60, w: 180, h: 50, label: "FastAPI Gateway" });
      shapes.push({ type: "box", x: 320, y: 60, w: 180, h: 50, label: "Cognitive Router" });
      shapes.push({ type: "arrow", x1: 240, y1: 85, x2: 320, y2: 85 });
      redrawShapes();
    }
  }
}

chips.forEach(chip => {
  chip.addEventListener("click", () => {
    queryInput.value = chip.dataset.prompt || chip.innerText;
    executeStreamingQuery();
  });
});

thinkingHeader.addEventListener("click", () => {
  thinkingPanel.classList.toggle("collapsed");
});

submitBtn.addEventListener("click", () => {
  executeStreamingQuery();
});

queryInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    executeStreamingQuery();
  }
});

async function executeStreamingQuery() {
  const query = queryInput.value.trim();
  if (!query || isStreaming) return;

  isStreaming = true;
  submitBtn.disabled = true;
  submitBtn.style.opacity = "0.5";

  thinkingPanel.classList.remove("collapsed");
  thinkingPanel.classList.remove("active");
  thinkingContent.textContent = "";
  
  responsePanel.classList.remove("active");
  responseContent.textContent = "";

  toolsCard.classList.remove("active");
  toolsCard.textContent = "";

  strategyMetric.textContent = i18n.translate('dashboard', 'dynamic.processing');
  latencyMetric.textContent = "--";

  const startTime = performance.now();

  try {
    const response = await fetch("/api/v1/stream/reasoning", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
      },
      body: JSON.stringify({ query: query })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop();

      for (const block of lines) {
        if (!block.trim()) continue;
        const eventLines = block.split("\n");
        let eventName = "message";
        let dataPayload = "";

        for (const line of eventLines) {
          if (line.startsWith("event:")) {
            eventName = line.substring(6).trim();
          } else if (line.startsWith("data:")) {
            dataPayload = line.substring(5).trim();
          }
        }

        handleServerEvent(eventName, dataPayload, startTime);
      }
    }
  } catch (err) {
    responsePanel.classList.add("active");
    responseContent.textContent = `Errore di connessione o inferenza: ${err.message}`;
    strategyMetric.textContent = "Error";
  } finally {
    isStreaming = false;
    submitBtn.disabled = false;
    submitBtn.style.opacity = "1";
  }
}

function handleServerEvent(event, rawData, startTime) {
  let data = {};
  try {
    data = JSON.parse(rawData);
  } catch (_) {
    data = { text: rawData };
  }

  if (event === "cache_hit") {
    const elapsed = (performance.now() - startTime).toFixed(1);
    strategyMetric.textContent = i18n.translate('dashboard', 'dynamic.semantic_fast_path');
    latencyMetric.textContent = `${elapsed} ms`;
    responsePanel.classList.add("active");
    responseContent.textContent = data.speech_output || "";
  } else if (event === "system1") {
    const intent = data.intent || "";
    const lat = data.latency_ms || 0;
    strategyMetric.textContent = `System 1: ${intent}`;
    latencyMetric.textContent = `${lat.toFixed(1)} ms`;
    if (intent === "whiteboard_canvas") {
      openWhiteboardSurface();
    }
  } else if (event === "thinking") {
    if (!thinkingPanel.classList.contains("active")) {
      thinkingPanel.classList.add("active");
      thinkingPanel.classList.remove("collapsed");
    }
    thinkingContent.textContent += (data.chunk || "");
    thinkingContent.scrollTop = thinkingContent.scrollHeight;
  } else if (event === "response") {
    if (thinkingPanel.classList.contains("active") && !thinkingPanel.classList.contains("collapsed")) {
      thinkingPanel.classList.add("collapsed");
    }
    if (!responsePanel.classList.contains("active")) {
      responsePanel.classList.add("active");
    }
    responseContent.textContent += (data.chunk || "");
    if (data.surface === "whiteboard") {
      openWhiteboardSurface();
    }
  } else if (event === "tool_call") {
    toolsCard.classList.add("active");
    toolsCard.textContent = JSON.stringify(data, null, 2);
  } else if (event === "done") {
    const totalElapsed = (performance.now() - startTime).toFixed(1);
    latencyMetric.textContent = `${totalElapsed} ms`;
    if (!responsePanel.classList.contains("active") && responseContent.textContent) {
      responsePanel.classList.add("active");
    }
  }
}

