export class AudioControlsManager {
  constructor(micBtnId = "btn-mic", speakerBtnId = "btn-speaker", inputTargetId = "query-input") {
    this.micBtn = document.getElementById(micBtnId);
    this.speakerBtn = document.getElementById(speakerBtnId);
    this.inputTarget = document.getElementById(inputTargetId);
    this.isRecording = false;
    this.isSpeakerMuted = false;
    this.recognition = null;
    this.audioContext = null;
    this.init();
  }

  init() {
    this.setupSpeechRecognition();
    if (this.micBtn) {
      this.micBtn.addEventListener("click", () => this.toggleMicrophone());
    }
    if (this.speakerBtn) {
      this.speakerBtn.addEventListener("click", () => this.toggleSpeaker());
    }
  }

  setupSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      this.recognition = new SpeechRecognition();
      this.recognition.continuous = false;
      this.recognition.interimResults = true;
      this.recognition.lang = "it-IT";

      this.recognition.onstart = () => {
        this.isRecording = true;
        this.updateMicUI();
      };

      this.recognition.onresult = (event) => {
        let transcript = "";
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          transcript += event.results[i][0].transcript;
        }
        if (this.inputTarget) {
          this.inputTarget.value = transcript;
        }
      };

      this.recognition.onend = () => {
        this.isRecording = false;
        this.updateMicUI();
        const submitBtn = document.getElementById("submit-btn");
        if (submitBtn && this.inputTarget && this.inputTarget.value.trim().length > 0) {
          submitBtn.click();
        }
      };

      this.recognition.onerror = () => {
        this.isRecording = false;
        this.updateMicUI();
      };
    }
  }

  toggleMicrophone() {
    if (!this.recognition) {
      const statusEl = document.getElementById("mic-status-label");
      if (statusEl) statusEl.textContent = "Web Speech non supportato";
      return;
    }

    if (this.isRecording) {
      this.recognition.stop();
    } else {
      try {
        this.recognition.start();
      } catch (_) {}
    }
  }

  updateMicUI() {
    const statusEl = document.getElementById("mic-status-label");
    if (!this.micBtn) return;
    if (this.isRecording) {
      this.micBtn.classList.add("recording");
      this.micBtn.innerHTML = `<span>&#128308;</span><span>In ascolto...</span>`;
      if (statusEl) statusEl.textContent = "Microfono attivo – Parla ora";
    } else {
      this.micBtn.classList.remove("recording");
      this.micBtn.innerHTML = `<span>&#127908;</span><span>Attiva Microfono</span>`;
      if (statusEl) statusEl.textContent = "In attesa di comando vocale";
    }
  }

  toggleSpeaker() {
    this.isSpeakerMuted = !this.isSpeakerMuted;
    const statusEl = document.getElementById("speaker-status-label");
    if (!this.speakerBtn) return;

    if (this.isSpeakerMuted) {
      this.speakerBtn.style.borderColor = "#64748b";
      this.speakerBtn.style.color = "#64748b";
      this.speakerBtn.innerHTML = `<span>&#128263;</span><span>Altoparlante Disattivo</span>`;
      if (statusEl) statusEl.textContent = "Sintesi vocale disattivata";
    } else {
      this.speakerBtn.style.borderColor = "#00f0ff";
      this.speakerBtn.style.color = "#00f0ff";
      this.speakerBtn.innerHTML = `<span>&#128266;</span><span>Altoparlante Attivo</span>`;
      if (statusEl) statusEl.textContent = "Audio vocale abilitato";
    }
  }

  speak(text) {
    if (this.isSpeakerMuted || !text) return;
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "it-IT";
      utterance.rate = 1.05;
      window.speechSynthesis.speak(utterance);
    }
  }
}
