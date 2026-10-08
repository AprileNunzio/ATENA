export class ProximityWidgetsManager {
  constructor(shelfId = "proximity-shelf", privacyController = null) {
    this.shelf = document.getElementById(shelfId);
    this.privacyController = privacyController;
    this.isOwnerApproaching = false;
    this.isVerified = false;
    this.hasActiveQuery = false;
    this.pollInterval = null;
    this.init();
  }

  init() {
    this.fetchStatus();
    this.fetchMetrics();
    this.pollInterval = setInterval(() => {
      this.fetchStatus();
      if (this.isOwnerApproaching) {
        this.fetchMetrics();
      }
    }, 3000);
  }

  setPrecedence(hasActiveQuery) {
    this.hasActiveQuery = hasActiveQuery;
    if (!this.shelf) return;
    if (hasActiveQuery) {
      this.shelf.classList.add("subordinate");
    } else {
      this.shelf.classList.remove("subordinate");
    }
  }

  async fetchStatus() {
    try {
      const res = await fetch("/api/v1/presence/status");
      if (!res.ok) return;
      const data = await res.json();
      this.isOwnerApproaching = Boolean(data.is_owner_approaching);
      this.isVerified = Boolean(data.is_biometrically_verified);

      if (this.privacyController) {
        this.privacyController.updateBiometricStatus(
          this.isVerified,
          data.detected_user,
          data.verification_method
        );
      }

      if (this.shelf) {
        if (this.isOwnerApproaching) {
          this.shelf.classList.add("visible");
        } else {
          this.shelf.classList.remove("visible");
        }
      }

      const presenceBadge = document.getElementById("presence-live-status");
      if (presenceBadge) {
        if (this.isOwnerApproaching && this.isVerified) {
          presenceBadge.innerHTML = `<span style="color:#10b981">&#9679;</span> Proprietario Identificato (${data.verification_method || "Biometrico"})`;
        } else if (this.isOwnerApproaching) {
          presenceBadge.innerHTML = `<span style="color:#f59e0b">&#9679;</span> Utente in avvicinamento (Non verificato)`;
        } else {
          presenceBadge.innerHTML = `<span style="color:#64748b">&#9679;</span> Nessuna presenza rilevata`;
        }
      }
    } catch (_) {}
  }

  async fetchMetrics() {
    try {
      const res = await fetch("/api/v1/system/metrics");
      if (!res.ok) return;
      const data = await res.json();
      this.renderMetrics(data);
    } catch (_) {}
  }

  renderMetrics(data) {
    const cpuEl = document.getElementById("metric-cpu-val");
    const cpuBar = document.getElementById("metric-cpu-bar");
    if (cpuEl) cpuEl.textContent = `${data.cpu_percent}%`;
    if (cpuBar) cpuBar.style.width = `${Math.min(data.cpu_percent, 100)}%`;

    const ramEl = document.getElementById("metric-ram-val");
    const ramBar = document.getElementById("metric-ram-bar");
    if (ramEl) ramEl.textContent = `${data.memory_percent}% (${data.memory_used_mb}MB)`;
    if (ramBar) ramBar.style.width = `${Math.min(data.memory_percent, 100)}%`;

    const ipEl = document.getElementById("metric-ip-val");
    if (ipEl) ipEl.textContent = data.local_ip;

    const agentsEl = document.getElementById("metric-agents-count");
    if (agentsEl) agentsEl.textContent = `${data.active_agents.length} Agenti`;

    const wattsEl = document.getElementById("metric-watts-val");
    if (wattsEl) wattsEl.textContent = `${data.estimated_power_watts} W`;

    const modeEl = document.getElementById("metric-power-mode");
    if (modeEl) modeEl.textContent = data.energy_mode;
  }

  async toggleMockPresence() {
    const nextState = !this.isOwnerApproaching;
    try {
      await fetch(`/api/v1/presence/toggle-mock?approaching=${nextState}&verified=${nextState}`, {
        method: "POST",
      });
      await this.fetchStatus();
      if (nextState) await this.fetchMetrics();
    } catch (_) {}
  }

  destroy() {
    if (this.pollInterval) clearInterval(this.pollInterval);
  }
}
