export class WidgetPrivacyController {
  constructor() {
    this.widgets = new Map();
    this.isOwnerVerified = false;
    this.ownerUserId = null;
    this.verificationModality = null;
    this.intervalId = null;
    this.init();
  }

  init() {
    this.intervalId = setInterval(() => this.tick(), 1000);
  }

  registerWidget(elementId, options = {}) {
    const el = document.getElementById(elementId);
    if (!el) return;

    const maxSec = options.maxExposureSeconds || 30;
    const isPersonal = options.isPersonal !== false;

    this.widgets.set(elementId, {
      el,
      maxSec,
      remainingSec: maxSec,
      isPersonal,
      isLocked: false,
      title: options.title || "Widget Riservato",
    });

    el.classList.add("privacy-shield-container");
    this.evaluateWidget(elementId);
  }

  updateBiometricStatus(isVerified, userId = null, modality = null) {
    const statusChanged = this.isOwnerVerified !== isVerified;
    this.isOwnerVerified = isVerified;
    this.ownerUserId = userId;
    this.verificationModality = modality;

    if (statusChanged && isVerified) {
      for (const [id, item] of this.widgets.entries()) {
        item.remainingSec = item.maxSec;
        item.isLocked = false;
        this.unlockWidget(id);
      }
    } else if (!isVerified) {
      for (const [id, item] of this.widgets.entries()) {
        if (item.isPersonal) {
          this.lockWidget(id, "Assenza utente autorizzato (Viso/Voce non rilevati)");
        }
      }
    }
  }

  tick() {
    for (const [id, item] of this.widgets.entries()) {
      if (!item.isPersonal || item.isLocked) continue;

      if (!this.isOwnerVerified) {
        this.lockWidget(id, "Autenticazione biometrica necessaria");
        continue;
      }

      if (item.remainingSec > 0) {
        item.remainingSec -= 1;
        this.updateBadge(id, item.remainingSec);
      } else {
        item.isLocked = true;
        this.lockWidget(id, "Tempo massimo di esposizione superato");
      }
    }
  }

  evaluateWidget(id) {
    const item = this.widgets.get(id);
    if (!item) return;

    if (item.isPersonal && !this.isOwnerVerified) {
      this.lockWidget(id, "Autenticazione biometrica necessaria (Viso/Voce)");
    } else {
      this.unlockWidget(id);
    }
  }

  lockWidget(id, reason) {
    const item = this.widgets.get(id);
    if (!item) return;

    let overlay = item.el.querySelector(".privacy-shield-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "privacy-shield-overlay";
      item.el.appendChild(overlay);
    }

    overlay.innerHTML = `
      <div class="privacy-shield-icon">&#128274;</div>
      <div class="privacy-shield-text">DATO PERSONALE PROTETTO</div>
      <div class="privacy-shield-sub">${this.escapeHtml(reason)}</div>
    `;

    const contentArea = item.el.querySelector(".widget-content") || item.el;
    contentArea.classList.add("privacy-blurred");
  }

  unlockWidget(id) {
    const item = this.widgets.get(id);
    if (!item) return;

    const overlay = item.el.querySelector(".privacy-shield-overlay");
    if (overlay) overlay.remove();

    const contentArea = item.el.querySelector(".widget-content") || item.el;
    contentArea.classList.remove("privacy-blurred");
    this.updateBadge(id, item.remainingSec);
  }

  updateBadge(id, sec) {
    const badgeEl = document.getElementById(`${id}-privacy-timer`);
    if (badgeEl) {
      badgeEl.textContent = `Scadenza: ${sec}s`;
    }
  }

  escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  destroy() {
    if (this.intervalId) clearInterval(this.intervalId);
  }
}
