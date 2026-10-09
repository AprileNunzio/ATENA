(() => {
  const A = window.AtenaAdmin;
  const PROVIDERS = [
    { value: "deepgram", icon: "⚡", title: "Deepgram", text: "Velocissimo, ottimo in italiano", link: "https://console.deepgram.com/signup" },
    { value: "groq", icon: "🚀", title: "Groq Whisper", text: "Whisper large-v3 con latenza minima", link: "https://console.groq.com/keys" },
    { value: "openai", icon: "◎", title: "OpenAI Whisper", text: "Affidabile, a pagamento a consumo", link: "https://platform.openai.com/api-keys" },
    { value: "gemini", icon: "✦", title: "Google Gemini", text: "Audio nativo, piano gratuito", link: "https://aistudio.google.com/apikey" },
    { value: "custom", icon: "🖧", title: "Server personalizzato", text: "Whisper o Gemma su un tuo computer (vLLM, LocalAI)", link: "" },
  ];

  const STEPS = [
    {
      id: "listen", icon: "🎧", title: "Come trascrive", hint: "Dove viene trasformata la voce in testo.",
      fields: [
        { key: "ATENA_EAR_MODE", kind: "cards", label: "Modalità", options: [
          { value: "offline", icon: "🔒", title: "Offline", text: "Tutto su questo server: privato e gratuito" },
          { value: "hybrid", icon: "⚖️", title: "Ibrido", text: "Online quando c'è rete, altrimenti offline" },
          { value: "online", icon: "☁️", title: "Online", text: "Massima precisione con un servizio cloud" }] },
        { key: "ATENA_ONLINE_STT_PROVIDER", kind: "cards", label: "Servizio online", options: PROVIDERS, when: (v) => v.ATENA_EAR_MODE !== "offline" },
        { key: "ATENA_ONLINE_STT_KEY", kind: "apikey", label: "Chiave API del servizio", when: (v) => v.ATENA_EAR_MODE !== "offline" },
        { key: "ATENA_ONLINE_STT_URL", kind: "text", label: "Indirizzo del server", placeholder: "http://192.168.1.50:8000", when: (v) => v.ATENA_EAR_MODE !== "offline" && v.ATENA_ONLINE_STT_PROVIDER === "custom" },
        { key: "ATENA_ONLINE_STT_MODEL", kind: "text", label: "Nome del modello", placeholder: "whisper-large-v3", when: (v) => v.ATENA_EAR_MODE !== "offline" && v.ATENA_ONLINE_STT_PROVIDER === "custom" },
        { key: "ATENA_STT_MODEL", kind: "select", label: "Modello offline", when: (v) => v.ATENA_EAR_MODE !== "online", options: [
          { value: "", title: "Automatico, in base al processore (consigliato)" }, { value: "base", title: "Veloce" },
          { value: "small", title: "Bilanciato" }, { value: "medium", title: "Preciso (più lento)" }, { value: "large-v3-turbo", title: "Massima precisione" }] },
        { key: "ATENA_EAR_MULTILANG", kind: "toggle", label: "Capisce e risponde nella lingua in cui parli", on: "1", off: "0" },
      ],
    },
    {
      id: "who", icon: "🗣", title: "Chi può parlare", hint: "Quando Atena si attiva e chi ascolta.",
      fields: [
        { key: "ATENA_VOICEPRINT_ENFORCE", kind: "toggle", label: "Rispondi solo alle voci registrate (niente TV o estranei)", on: "1", off: "0" },
        { key: "ATENA_WAKEWORD_THRESHOLD", kind: "slider", label: "Sensibilità di «Atena»", min: 0.25, max: 0.8, step: 0.05, left: "Sente anche da lontano", right: "Meno attivazioni per errore" },
        { key: "ATENA_EAR_CONVERSATION_S", kind: "slider", label: "Conversazione continua dopo una risposta", min: 5, max: 120, step: 5, unit: "s", left: "Breve", right: "Lunga" },
        { key: "ATENA_EAR_AUTO_FOLLOWUP", kind: "slider", label: "Ascolto senza ripetere «Atena»", min: 0, max: 60, step: 5, unit: "s", left: "Mai", right: "A lungo", expert: true },
        { key: "ATENA_VOICE_ADAPTIVE", kind: "toggle", label: "Soglia di riconoscimento su misura per ogni persona", on: "1", off: "0", expert: true },
        { key: "ATENA_VOICE_AUTOIMPROVE", kind: "toggle", label: "Migliora da sola l'impronta vocale", on: "1", off: "0", expert: true },
        { key: "ATENA_VOICEPRINT_MATCH", kind: "slider", label: "Somiglianza minima della voce", min: 0.3, max: 0.95, step: 0.05, expert: true },
        { key: "ATENA_VOICE_MARGIN", kind: "slider", label: "Distacco dalla seconda voce più simile", min: 0, max: 0.5, step: 0.05, expert: true },
        { key: "ATENA_VOICE_TWIN_SIM", kind: "slider", label: "Voci considerate simili oltre", min: 0.2, max: 0.95, step: 0.05, expert: true },
        { key: "ATENA_VOICE_TWIN_MARGIN", kind: "slider", label: "Distacco tra voci simili (es. gemelli)", min: 0, max: 0.6, step: 0.05, expert: true },
      ],
    },
    {
      id: "mic", icon: "🎙", title: "Microfono e distanza", hint: "Quanto lontano parli dal microfono.",
      fields: [
        { kind: "preset", label: "Da dove parli di solito", options: [
          { value: "near", icon: "🪑", title: "Vicino", text: "Alla scrivania, entro un metro", set: { ATENA_EAR_MAX_GAIN: "10", ATENA_EAR_WAKE_GAIN: "4", ATENA_EAR_TARGET_RMS: "0.08", ATENA_EAR_ENHANCE_ENGINE: "spectral" } },
          { value: "room", icon: "🛋", title: "Nella stanza", text: "Dal divano o dal tavolo", set: { ATENA_EAR_MAX_GAIN: "30", ATENA_EAR_WAKE_GAIN: "10", ATENA_EAR_TARGET_RMS: "0.1", ATENA_EAR_ENHANCE_ENGINE: "auto" } },
          { value: "far", icon: "🏛", title: "Lontano", text: "Stanze grandi o con eco", set: { ATENA_EAR_MAX_GAIN: "60", ATENA_EAR_WAKE_GAIN: "20", ATENA_EAR_TARGET_RMS: "0.12", ATENA_EAR_ENHANCE_ENGINE: "deepfilternet" } }] },
        { key: "ATENA_EAR_END_SILENCE", kind: "slider", label: "Pausa che chiude la frase", min: 0.3, max: 1.5, step: 0.1, unit: "s", left: "Risponde prima", right: "Aspetta chi parla piano" },
        { key: "ATENA_MIC_EC", kind: "toggle", label: "Elimina l'eco delle casse vicine", on: "1", off: "0" },
        { key: "ATENA_MIC_AGC", kind: "select", label: "Livello del microfono", options: [
          { value: "auto", title: "Automatico (consigliato)" }, { value: "1", title: "Sempre gestito dal browser" }, { value: "0", title: "Mai" }] },
        { key: "ATENA_MIC_NS", kind: "toggle", label: "Riduzione del rumore del browser", on: "1", off: "0", expert: true },
        { key: "ATENA_EAR_ENHANCE_ENGINE", kind: "select", label: "Pulizia dell'audio", expert: true, options: [
          { value: "auto", title: "Automatica" }, { value: "deepfilternet", title: "DeepFilterNet (stanze grandi)" }, { value: "spectral", title: "Filtro spettrale" }] },
        { key: "ATENA_EAR_MAX_GAIN", kind: "slider", label: "Amplificazione massima", min: 2, max: 80, step: 1, expert: true },
        { key: "ATENA_EAR_WAKE_GAIN", kind: "slider", label: "Amplificazione di «Atena» da lontano", min: 1, max: 30, step: 1, expert: true },
        { key: "ATENA_EAR_TARGET_RMS", kind: "slider", label: "Livello vocale obiettivo", min: 0.03, max: 0.2, step: 0.01, expert: true },
      ],
    },
    {
      id: "learn", icon: "🧠", title: "Apprendimento e privacy", hint: "Cosa conserva per migliorare e per quanto.",
      fields: [
        { key: "ATENA_EAR_RECORD", kind: "toggle", label: "Registra i tratti con voce per imparare (solo su questo server)", on: "1", off: "0" },
        { key: "ATENA_EAR_RECORD_HOURS", kind: "slider", label: "Conserva le registrazioni per", min: 1, max: 168, step: 1, unit: "h", when: (v) => v.ATENA_EAR_RECORD !== "0" },
        { key: "ATENA_EAR_REVIEW", kind: "toggle", label: "Ricontrolla a riposo se aveva capito bene", on: "1", off: "0" },
        { key: "ATENA_EAR_AUTOTUNE", kind: "toggle", label: "Regola da sola sensibilità e amplificazione", on: "1", off: "0" },
        { key: "ATENA_EAR_RECORD_MAX_MB", kind: "slider", label: "Spazio massimo per le registrazioni", min: 50, max: 5000, step: 50, unit: "MB", expert: true },
        { key: "ATENA_EAR_RECORD_CHUNK", kind: "slider", label: "Durata di ogni blocco registrato", min: 20, max: 300, step: 10, unit: "s", expert: true },
        { key: "ATENA_EAR_KEEP_REVIEWED_H", kind: "slider", label: "Conserva l'audio già analizzato", min: 0, max: 72, step: 1, unit: "h", expert: true },
        { key: "ATENA_EAR_REVIEW_IDLE", kind: "slider", label: "«A riposo» dopo secondi di silenzio", min: 10, max: 3600, step: 10, unit: "s", expert: true },
        { key: "ATENA_EAR_REVIEW_LOAD", kind: "slider", label: "Analizza solo se il carico per core è sotto", min: 0.1, max: 2, step: 0.1, expert: true },
        { key: "ATENA_EAR_REVIEW_MODEL", kind: "select", label: "Modello per ricontrollare", expert: true, options: [
          { value: "same", title: "Lo stesso dell'ascolto" }, { value: "base", title: "Veloce" }, { value: "small", title: "Più preciso" }, { value: "medium", title: "Molto preciso" }] },
        { kind: "actions" },
      ],
    },
  ];

  A.earSchema = { STEPS, PROVIDERS };
})();
