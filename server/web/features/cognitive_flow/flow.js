export class CognitiveFlowViewer {
  constructor(panelId = "cognitive-flow-panel", trackId = "cognitive-flow-track", inspectorId = "flow-inspector") {
    this.panel = document.getElementById(panelId);
    this.track = document.getElementById(trackId);
    this.inspector = document.getElementById(inspectorId);
    this.currentData = null;
    this.selectedNodeId = null;
    this.isVisible = false;
    this.init();
  }

  init() {
    const toggleBtn = document.getElementById("btn-cognitive-flow");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => this.toggle());
    }
    const closeBtn = document.getElementById("flow-close-btn");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => this.hide());
    }
    const inspectClose = document.getElementById("flow-inspector-close");
    if (inspectClose) {
      inspectClose.addEventListener("click", () => this.hideInspector());
    }
    this.fetchFlow();
  }

  toggle() {
    if (this.isVisible) {
      this.hide();
    } else {
      this.show();
    }
  }

  show() {
    this.isVisible = true;
    if (this.panel) this.panel.classList.add("active");
    this.fetchFlow();
  }

  hide() {
    this.isVisible = false;
    if (this.panel) this.panel.classList.remove("active");
  }

  async fetchFlow() {
    try {
      const res = await fetch("/api/v1/cognitive/flow/active");
      if (!res.ok) return;
      const data = await res.json();
      this.renderFlow(data);
    } catch (_) {}
  }

  updateFromSnapshot(snapshot) {
    if (!snapshot) return;
    this.renderFlow(snapshot);
  }

  renderFlow(flowData) {
    this.currentData = flowData;
    if (!this.track || !flowData || !Array.isArray(flowData.nodes)) return;

    this.track.innerHTML = "";
    const nodes = flowData.nodes;

    nodes.forEach((node, index) => {
      const card = document.createElement("div");
      const stateClass = `state-${node.s || "ok"}`;
      card.className = `flow-node-card ${stateClass}`;
      if (this.selectedNodeId === node.i) card.classList.add("selected");

      const badgeClass = node.s === "ok" ? "ok" : (node.s === "running" ? "running" : "fail");
      const elapsed = node.b !== null && node.b !== undefined ? `${((node.b - (node.a || 0)) * 1000).toFixed(0)} ms` : "in corso";

      card.innerHTML = `
        <div class="flow-node-header">
          <span class="flow-node-kind">${this.escapeHtml(node.k || "stage")}</span>
          <span class="flow-node-badge ${badgeClass}">${(node.s || "ok").toUpperCase()}</span>
        </div>
        <div class="flow-node-name" title="${this.escapeHtml(node.n || "")}">${this.escapeHtml(node.n || "Blocco")}</div>
        <div class="flow-node-timing">+${((node.a || 0) * 1000).toFixed(0)}ms (${elapsed})</div>
      `;

      card.addEventListener("click", () => this.selectNode(node.i));
      this.track.appendChild(card);

      if (index < nodes.length - 1) {
        const connector = document.createElement("div");
        connector.className = "flow-connector";
        connector.innerHTML = "&#10140;";
        this.track.appendChild(connector);
      }
    });

    if (this.selectedNodeId !== null) {
      const found = nodes.find(n => n.i === this.selectedNodeId);
      if (found) this.renderInspector(found);
    }
  }

  selectNode(nodeId) {
    this.selectedNodeId = nodeId;
    const cards = this.track.querySelectorAll(".flow-node-card");
    cards.forEach(c => c.classList.remove("selected"));

    if (this.currentData && Array.isArray(this.currentData.nodes)) {
      const node = this.currentData.nodes.find(n => n.i === nodeId);
      if (node) {
        this.renderInspector(node);
      }
    }
  }

  renderInspector(node) {
    if (!this.inspector) return;
    this.inspector.style.display = "block";
    const titleEl = document.getElementById("flow-inspector-title");
    const thoughtBox = document.getElementById("flow-thought-box");

    if (titleEl) {
      titleEl.textContent = `[#${node.i}] ${node.n} (${(node.k || "").toUpperCase()})`;
    }
    if (thoughtBox) {
      const detailText = node.d && String(node.d).trim().length > 0 
        ? node.d 
        : "Nessun dettaglio o riflessione analitica registrata per questo blocco.";
      thoughtBox.textContent = detailText;
    }
  }

  hideInspector() {
    if (this.inspector) this.inspector.style.display = "none";
    this.selectedNodeId = null;
    if (this.track) {
      const cards = this.track.querySelectorAll(".flow-node-card");
      cards.forEach(c => c.classList.remove("selected"));
    }
  }

  escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }
}
