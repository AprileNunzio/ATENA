export const ZONES = [
  { id: "home", title: "Plancia", glyph: "◉", min: "explorer", group: "Inizia", lead: "Lo stato di Atena a colpo d'occhio." },
  { id: "brain", title: "Cervello", glyph: "◈", min: "explorer", group: "Intelligenza", lead: "Chi pensa, cosa ricorda e cosa sta imparando Atena.",
    classic: [["models", "Cervello e modelli"], ["f/mind", "Mente"], ["study", "Studio autonomo"]] },
  { id: "flows", title: "Flussi", glyph: "⟁", min: "explorer", group: "Intelligenza", lead: "Come ragiona Atena, passo per passo, e quali algoritmi usa.", added: "2026-10-09",
    classic: [["models", "Catene di cervelli"], ["skills", "Algoritmi"]] },
  { id: "tools", title: "Strumenti", glyph: "▦", min: "explorer", group: "Intelligenza", lead: "Tutti gli strumenti di Atena in un solo posto.", added: "2026-10-09",
    classic: [["features", "Funzionalità"]] },
  { id: "trust", title: "Regole e Fiducia", glyph: "⚖", min: "explorer", group: "Protezione", lead: "Cosa Atena può fare da sola e cosa deve chiederti prima.",
    classic: [["laws", "Leggi"], ["autonomy", "Autonomia"], ["capabilities", "Capacità"]] },
  { id: "network", title: "Rete e Sicurezza", glyph: "⌬", min: "pilot", group: "Protezione", lead: "Porte, connessioni e dispositivi della tua rete.",
    classic: [["firewall", "Firewall"], ["vpn", "VPN"], ["network", "Esploratore della rete"], ["shares", "Cartella condivisa"]] },
  { id: "system", title: "Sistema", glyph: "⚙", min: "pilot", group: "Macchina", lead: "Pacchetti, installazione, aggiornamenti e risorse della macchina.",
    classic: [["packages", "Pacchetti"], ["steps", "Installazione"], ["config", "Configurazione"], ["updates", "Aggiornamenti"], ["nodes", "Nodi e server"]] },
  { id: "observatory", title: "Osservatorio", glyph: "◷", min: "pilot", group: "Macchina", lead: "Cosa è successo, quando e perché.",
    classic: [["logs", "Log"], ["events", "Eventi"]] },
  { id: "awakening", title: "Risveglio", glyph: "✦", min: "explorer", group: "Inizia", accent: true, added: "2026-10-09", lead: "La procedura guidata per configurare Atena in pochi passi." },
];

export const GROUPS = ["Inizia", "Intelligenza", "Protezione", "Macchina"];

export const zone = (id) => ZONES.find((z) => z.id === id);
