export class SettingsModalManager {
  constructor(overlayId = "settings-modal-overlay", btnOpenId = "btn-settings") {
    this.overlay = document.getElementById(overlayId);
    this.btnOpen = document.getElementById(btnOpenId);
    this.init();
  }

  init() {
    if (this.btnOpen) {
      this.btnOpen.addEventListener("click", () => this.open());
    }
    const closeBtn = document.getElementById("settings-modal-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => this.close());
    }
    if (this.overlay) {
      this.overlay.addEventListener("click", (e) => {
        if (e.target === this.overlay) this.close();
      });
    }
    const btnSimulate = document.getElementById("btn-toggle-presence-sim");
    if (btnSimulate) {
      btnSimulate.addEventListener("click", async () => {
        if (window.proximityManager) {
          await window.proximityManager.toggleMockPresence();
        }
      });
    }
  }

  open() {
    if (this.overlay) this.overlay.classList.add("active");
  }

  close() {
    if (this.overlay) this.overlay.classList.remove("active");
  }
}
