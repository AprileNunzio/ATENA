export class BrainModalManager {
  constructor(overlayId = "brain-modal-overlay", btnOpenId = "btn-show-brain") {
    this.overlay = document.getElementById(overlayId);
    this.btnOpen = document.getElementById(btnOpenId);
    this.canvas = document.getElementById("brain-network-canvas");
    this.ctx = null;
    this.nodes = [];
    this.edges = [];
    this.init();
  }

  init() {
    if (this.btnOpen) {
      this.btnOpen.addEventListener("click", () => this.open());
    }
    const closeBtn = document.getElementById("brain-modal-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => this.close());
    }
    if (this.overlay) {
      this.overlay.addEventListener("click", (e) => {
        if (e.target === this.overlay) this.close();
      });
    }
  }

  async open() {
    if (!this.overlay) return;
    this.overlay.classList.add("active");
    await this.loadGraphData();
    this.renderGraph();
  }

  close() {
    if (this.overlay) this.overlay.classList.remove("active");
  }

  async loadGraphData() {
    try {
      const res = await fetch("/api/v1/knowledge/graph");
      if (!res.ok) return;
      const data = await res.json();
      if (data && data.graph) {
        this.nodes = Object.values(data.graph.nodes || {});
        this.edges = data.graph.edges || [];
        const countEl = document.getElementById("brain-stats-label");
        if (countEl) {
          countEl.textContent = `${this.nodes.length} Nodi Conoscitivi | ${this.edges.length} Relazioni`;
        }
      }
    } catch (_) {}
  }

  renderGraph() {
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext("2d");
    this.canvas.width = this.canvas.offsetWidth || 850;
    this.canvas.height = this.canvas.offsetHeight || 380;

    const w = this.canvas.width;
    const h = this.canvas.height;
    this.ctx.clearRect(0, 0, w, h);

    if (this.nodes.length === 0) {
      this.nodes = [
        { id: "core_atena", label: "Atena Core", node_type: "SYSTEM" },
        { id: "system1", label: "System 1 Non-Autoregressive", node_type: "REASONING" },
        { id: "system2", label: "System 2 Latent Chain", node_type: "REASONING" },
        { id: "agent_pool", label: "Agent Pool Swarm", node_type: "EXECUTION" },
        { id: "semantic_memory", label: "Memoria Semantica", node_type: "MEMORY" },
      ];
      this.edges = [
        { source_id: "core_atena", target_id: "system1" },
        { source_id: "core_atena", target_id: "system2" },
        { source_id: "system1", target_id: "agent_pool" },
        { source_id: "system2", target_id: "semantic_memory" },
      ];
    }

    const posMap = new Map();
    const centerX = w / 2;
    const centerY = h / 2;
    const radius = Math.min(w, h) * 0.35;

    this.nodes.forEach((node, i) => {
      const angle = (i / this.nodes.length) * Math.PI * 2;
      const x = i === 0 ? centerX : centerX + Math.cos(angle) * radius;
      const y = i === 0 ? centerY : centerY + Math.sin(angle) * radius;
      posMap.set(node.id, { x, y, label: node.label || node.id });
    });

    this.ctx.strokeStyle = "rgba(0, 240, 255, 0.25)";
    this.ctx.lineWidth = 1.5;
    this.edges.forEach((edge) => {
      const p1 = posMap.get(edge.source_id);
      const p2 = posMap.get(edge.target_id);
      if (p1 && p2) {
        this.ctx.beginPath();
        this.ctx.moveTo(p1.x, p1.y);
        this.ctx.lineTo(p2.x, p2.y);
        this.ctx.stroke();
      }
    });

    posMap.forEach((p) => {
      this.ctx.fillStyle = "rgba(0, 240, 255, 0.15)";
      this.ctx.beginPath();
      this.ctx.arc(p.x, p.y, 22, 0, Math.PI * 2);
      this.ctx.fill();

      this.ctx.strokeStyle = "#00f0ff";
      this.ctx.lineWidth = 2;
      this.ctx.stroke();

      this.ctx.fillStyle = "#ffffff";
      this.ctx.font = "11px monospace";
      this.ctx.textAlign = "center";
      this.ctx.fillText(p.label, p.x, p.y + 36);
    });
  }
}
