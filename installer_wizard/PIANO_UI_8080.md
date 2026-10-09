# Atena Nexus — Piano di implementazione del nuovo pannello :8080

> Obiettivo: trasformare il pannello di amministrazione da 44 schede piatte a un'esperienza **guidata, a step, futuristica**,
> usabile da un bambino e potente per un esperto, con un nuovo **Flow Studio** drag & drop per vedere e modificare
> come Atena ragiona.

---

## 0. Diagnosi dello stato attuale

| Problema | Evidenza nel codice | Effetto per l'utente |
|---|---|---|
| Navigazione piatta | `web/admin/admin.html`: 7 voci fisse + 44 schede iniettate da `features/*/admin.html` | Il nuovo utente non sa da dove iniziare |
| Categorie incoerenti | `feature.json → category`: `assistente`, `intelligenza`, `intrattenimento`, `casa`, ... (alcune non documentate in `features/README.md`) | Strumenti simili finiscono in posti diversi |
| Doppio livello rigido | `web/admin/uimode.js`: solo `simple` / `expert` | Nessun percorso per principianti assoluti |
| Il ragionamento è invisibile | `brain/stages.py`, `brain/journey.py`, `understanding/router.py`, `brain/scope.py (STRATEGIES = order, fastest)` | Le scelte di algoritmo sono sparse in variabili `.env` |
| Configurazione dispersa | `atena.env` + `registry.settings_of(id)` + schede dedicate | Nessuna visione d'insieme, nessun "annulla" |
| Sicurezza front-end migliorabile | script `type="module"` e stili inline in `admin.html` | Impedisce una CSP rigorosa senza `unsafe-inline` |

Punti di forza da **riusare** (non riscrivere):
- auto-scoperta delle funzionalità (`backend/feature_registry.py`, manifest `feature.json`);
- tracciamento del ragionamento (`JourneyTracker`, nodi `input → laws → cache → router → planner → agent → tool → jury → answer`, già colorati in `web/display/flow.js`);
- design token esistenti in `web/shared/atena.css` (ciano/viola/verde, vetro, griglia olografica);
- i18n per feature (`features/<id>/language/*.json`).

---

## 1. Visione: tre livelli di esperienza, un solo pannello

| Livello | Per chi | Cosa vede | Linguaggio |
|---|---|---|---|
| **Esploratore** | bambini, primo avvio, chi non è tecnico | Card grandi, 1 decisione per schermata, guida "Atena Orb" che parla, niente numeri tecnici | «Vuoi che Atena ti veda con la telecamera?» |
| **Pilota** | utente domestico evoluto | Zone, interruttori, preset, Flow Studio con template | «Riconoscimento volti: attivo — automatico» |
| **Architetto** | sistemisti, sviluppatori | Tutto: variabili `.env`, JSON dei flussi, log grezzi, API, metriche, diff | `ATENA_LLM_DEEP_STRATEGY=fastest` |

Principio: **progressive disclosure**. Ogni elemento dichiara `data-level="explorer|pilot|architect"`; il livello si
cambia in ogni momento, sostituisce `uimode.js` e viene salvato lato server per utente (non solo in `localStorage`).

---

## 2. Nuova architettura dell'informazione (8 zone)

Da 44 schede a **8 zone logiche**, ordinate come il percorso mentale dell'utente: *come sta → chi è → come pensa →
cosa sa fare → cosa può fare → cosa vede → come funziona sotto → cosa è successo*.

```
◉ Plancia          stato, salute, cose da fare, suggerimenti
🧠 Cervello         modelli, server, cloud, ruoli, catene
⟁ Flussi           Flow Studio (nuovo): ragionamenti e algoritmi drag & drop
▦ Strumenti        TUTTI i tool, raggruppati per famiglia
🛡 Regole e Fiducia leggi, autonomia, approvazioni, capacità, segreti
🌐 Rete e Sicurezza firewall, VPN, rete, condivisioni, accessi
⚙ Sistema          pacchetti, installazione, aggiornamenti, nodi, risorse, collaudo
◷ Osservatorio     log, eventi, viaggi del ragionamento, macchina del tempo
```

### 2.1 Mappatura delle funzionalità esistenti

| Zona | Funzionalità (id cartella) |
|---|---|
| Plancia | `hub`, `selftest` (sintesi), `auto_update` (sintesi) |
| Cervello | `brain`, `understanding`, `team`, `mind`, `vault`, `study`, `soup` |
| Flussi | **nuova** `flows` (orchestra `understanding`, `brain`, `team`, `agent`, `skills`) |
| Strumenti → Percezione | `vision`, `cameras`, `ear`, `hands`, `scene`, `bluetooth`, `location`, `devices`, `biometrics` |
| Strumenti → Casa | `home_assistant`, `places`, `people`, `habits`, `twin`, `nvr`, `redalert`, `printers` |
| Strumenti → Comunicazione | `chat`, `telegram`, `google`, `spotify`, `mcpclient` |
| Strumenti → Creatività e svago | `music`, `tv`, `sports`, `models3d`, `avatars`, `voices`, `voicestudio`, `sounds`, `appearance` |
| Strumenti → Produttività | `skills` (Algoritmi), `documents`, `whiteboard`, `automations`, `actions`, `agent`, `rpa`, `maps`, `forge`, `desktop` |
| Regole e Fiducia | `laws`, `autonomy`, `capabilities`, `authz`, `secure` |
| Rete e Sicurezza | `firewall`, `vpn`, `network`, `shares` |
| Sistema | Pacchetti, Installazione, Configurazione, `auto_update`, `nodes`, `proxmox`, `governor`, `scheduler`, `kiosk`, `locale`, `selftest` |
| Osservatorio | Log, Eventi, Journey (viaggi), Ledger |

### 2.2 Estensione del manifest (retro-compatibile)

```json
{
  "zone": "tools",
  "family": "perception",
  "level": "pilot",
  "keywords": ["webcam", "volto", "face"],
  "wizard": [
    { "id": "consent", "kind": "choice", "title": "Vuoi che Atena riconosca i volti?" },
    { "id": "camera",  "kind": "device-pick", "source": "/api/cameras" }
  ],
  "flow_nodes": ["vision.detector"]
}
```

- `zone`/`family` mancanti → derivati da `category` con una tabella di migrazione in `feature_registry.py`.
- `wizard` → step dichiarativi: il pannello genera da solo la procedura guidata (come oggi genera il form da `settings`).
- `flow_nodes` → la feature contribuisce nodi e algoritmi al Flow Studio.

Nessuna feature esistente deve essere modificata per funzionare: i nuovi campi sono opzionali.

---

## 3. Le pagine, una per una

Per ogni pagina: **scopo**, **cosa vede ciascun livello**, **componenti**, **API**.

### 3.1 Accesso (Login)
- **Scopo**: ingresso sicuro con PAM, già esistente.
- **Wow**: l'orb di Atena si "sveglia" e scansiona; il campo password ha un feedback a onda; errore = vibrazione glitch.
- **Sicurezza**: rate limit esponenziale per IP+utente, cookie `__Host-` `HttpOnly` `Secure` `SameSite=Strict`,
  rotazione dell'id di sessione al login, WebAuthn/passkey opzionale come secondo fattore, messaggio di errore uniforme.
- **API**: `POST /api/auth/login`, `POST /api/auth/webauthn/*`, `POST /api/auth/logout`.

### 3.2 Primo avvio — "Risveglio di Atena" (wizard a step)
Mostrato al primo login o finché la checklist non è completa. 7 step, ognuno una schermata piena con una sola domanda:

1. **Lingua e voce** — Atena parla e chiede «Come ti chiami?».
2. **Livello** — Esploratore / Pilota / Architetto, con tre card illustrate.
3. **Dove pensa Atena** — «Su questo computer / su un altro / nel cloud» (riusa `brain-mode` di `packages`), con test
   di velocità reale e risultato in "stelle".
4. **Sensi** — telecamera, microfono, mani: anteprima live, consenso esplicito per ogni senso.
5. **Casa** — rilevamento automatico di Home Assistant, stanze e persone.
6. **Regole** — scegli un profilo di fiducia (Prudente / Equilibrato / Autonomo) che imposta `laws` e `autonomy`.
7. **Pronto** — riepilogo animato, "Atena è pronta al 100 %", con anello che si chiude.

- Ogni step è **salvabile e ripristinabile** (bozza lato server), salto sempre possibile, «Rifai la procedura» dalla Plancia.
- **Componenti**: `<at-stepper>`, `<at-choice-card>`, `<at-device-preview>`, `<at-orb-guide>`.
- **API**: `GET/PUT /api/onboarding`, riuso delle API delle feature coinvolte.

### 3.3 Plancia (Home)
- **Esploratore**: un grande volto/orb con stato a parole («Sto bene, ho imparato 3 cose oggi»), 4 tessere grandi:
  *Parla con me*, *I miei sensi*, *La mia casa*, *Serve aiuto?*.
- **Pilota**: anello di salute globale, tessere CPU/RAM/disco/GPU, "Cose da fare" (aggiornamenti, step falliti,
  approvazioni in attesa), preferiti, ultime attività.
- **Architetto**: aggiunge componenti/servizi con stato systemd, coda in background, versioni, pulsanti di riparazione.
- **Wow**: **Mappa neurale viva** — il flusso di ragionamento attivo disegnato come costellazione; ogni richiesta reale
  fa scorrere particelle lungo i nodi (dati dal `JourneyTracker` via SSE).
- **API**: `GET /api/status` (esistente), `GET /api/nexus/summary` (nuova aggregazione), `GET /api/journeys/stream` (SSE).

### 3.4 Cervello
Sotto-pagine a schede orizzontali:
1. **Modelli** — catalogo con card (dimensione, velocità misurata, lingua, VRAM richiesta), installazione in un click.
2. **Server** — Ollama locali/remoti e endpoint compatibili OpenAI, test di connessione.
3. **Cloud** — 22 fornitori, chiavi in `vault` cifrate, mai rimostrate in chiaro (solo ultime 4 cifre).
4. **Ruoli** — i ruoli di `brain/roles.py` (Conversazione, Ragionamento, Ricercatore, Domotico, ...) come card
   con catena di cervelli ordinabile via drag & drop.
5. **Memoria** — `mind` + `vault`: cosa ricorda Atena, ricerca, oblio selettivo (diritto all'oblio).
6. **Studio** — `study` + `soup`: cosa sta imparando, calendario, risultati.

- **Esploratore**: vede solo «Quanto è intelligente / quanto è veloce / quanto è privata» con tre slider che scelgono un preset.
- **API**: riuso di `brain/*_api.py`, `mind/api.py`.

### 3.5 Flussi — Flow Studio (pagina chiave, vedi §4)

### 3.6 Strumenti
Un'unica pagina che contiene **tutti** i tool.
- **Vista "Costellazione"** (default Pilota): famiglie come pianeti, strumenti come satelliti; i satelliti accesi brillano.
- **Vista "Griglia"**: card con icona, stato (Automatico / Sempre attivo / Spento), motivo se spento
  («Manca una webcam»), pulsante preferito.
- **Filtri**: famiglia, stato, "consigliati per il mio hardware", ricerca fuzzy con sinonimi (`keywords`).
- **Pagina dello strumento** (template unico per tutti):
  1. intestazione con interruttore a tre stati e requisiti soddisfatti/mancanti;
  2. **"Configura con me"**: il wizard dichiarato in `feature.json → wizard`;
  3. impostazioni generate da `settings` (Pilota) + vista `.env`/JSON (Architetto);
  4. scheda dedicata esistente (`admin.html` della feature) incorporata come "Avanzate";
  5. attività recenti e test rapido («Prova adesso»).
- **Esploratore**: vede solo gli strumenti marcati `level: explorer`, con descrizioni in linguaggio semplice.

### 3.7 Regole e Fiducia
- **Leggi** (`laws`): elenco leggibile, le leggi fondamentali sono bloccate e mostrate con un lucchetto.
- **Autonomia** (`autonomy`): slider di fiducia per area (casa, computer, rete, acquisti), approvazioni in attesa
  con «Approva una volta / sempre / mai».
- **Capacità** (`capabilities`): token MCP, scadenze, audit.
- **Accessi** (`authz`): utenti, ruoli, sessioni attive, revoca.
- **Esploratore**: tre profili illustrati (Prudente / Equilibrato / Autonomo).

### 3.8 Rete e Sicurezza
- **Firewall** con mappa porte visuale e modalità "spiegami questa regola".
- **VPN**, **Rete** (dispositivi scoperti come radar), **Condivisioni**.
- Riepilogo **punteggio di sicurezza** con azioni consigliate (porte aperte, password deboli, aggiornamenti mancanti).

### 3.9 Sistema
- **Pacchetti**, **Installazione** (step di convergenza + coda in background), **Configurazione** (editor `.env`
  con validazione e diff prima del salvataggio), **Aggiornamenti** (canale, cronologia, rollback),
  **Nodi e server** (`nodes`, `proxmox`), **Risorse** (`governor`), **Pianificatore**, **Display** (`kiosk`), **Collaudo**.
- Visibile da Pilota (sintesi) e Architetto (completo). Nascosto all'Esploratore tranne «Aggiorna» e «Riavvia».

### 3.10 Osservatorio
- **Viaggi del ragionamento**: elenco delle ultime richieste, ogni viaggio riproducibile come animazione sul grafo.
- **Macchina del tempo**: scrubber temporale sul ledger degli eventi, confronto "prima/dopo" della configurazione.
- **Log** con filtri, livelli, ricerca, download firmato; **Eventi** con timeline.
- Solo Architetto (Pilota vede i viaggi).

### 3.11 Elementi globali
- **Command palette** `Ctrl/⌘ + K`: cerca pagine, strumenti, impostazioni, azioni («riavvia voce», «apri firewall»).
- **Comando vocale**: microfono nella barra, stesso motore della palette.
- **Atena Orb**: guida contestuale, pulsante «Spiegamelo semplice» su ogni schermata.
- **Centro notifiche** e **toast** con «Annulla» per 10 secondi su ogni modifica reversibile.
- **Selettore livello** e lingua sempre visibili.

---

## 4. Flow Studio — il diagramma di flusso dei ragionamenti

### 4.1 Concetto
Atena fornisce **flussi predefiniti** (come ragiona oggi). L'utente li vede come un grafo di nodi; può:
1. **scegliere un template** (Esploratore);
2. **cambiare l'algoritmo di un nodo** da un menu di alternative con pro/contro (Pilota);
3. **trascinare, aggiungere, collegare nodi** e creare flussi propri (Architetto).

Nessun codice arbitrario: ogni nodo esegue solo **algoritmi registrati e firmati** nel catalogo. L'utente compone,
non programma — questo è il cuore della sicurezza.

### 4.2 Nodi del flusso principale (allineati a `JourneyTracker` e `flow.js`)

```
[Ingresso] → [Leggi] → [Cache] → [Comprensione] → [Pianificazione] → [Scelta cervello]
          → [Ragionamento] → [Strumenti] → [Verifica] → [Memoria] → [Risposta]
```

| Nodo | Algoritmi disponibili (★ = default attuale) | Pro / contro mostrati |
|---|---|---|
| **Leggi** | ★ Guardia regole (`laws/guard.py`) — nodo **bloccato**, non rimovibile | sicurezza |
| **Cache** | ★ Esatta · Semantica (embedding, soglia) · Disattivata | velocità vs freschezza |
| **Comprensione** | ★ Punteggio per funzionalità + arbitro LLM se ambiguo (`understanding/router.py`) · Solo parole chiave · Solo embedding · Solo LLM | velocità vs precisione |
| **Pianificazione** | ★ Diretto · Plan-and-Execute · DAG di sotto-compiti | complessità |
| **Scelta cervello** | ★ Ordine di priorità (`order`) · Il più veloce (`fastest`) · Costo minimo · Qualità misurata (bandit UCB) · Solo locale | costo, privacy, latenza |
| **Ragionamento** | Risposta diretta · Chain-of-Thought · ★ ReAct con strumenti · Tree-of-Thoughts · Self-consistency (N voti) | qualità vs tempo |
| **Strumenti** | ★ Recupero per similarità top-k (`team/router.py`) · BM25 · Ibrido BM25+embedding · Lista fissa | pertinenza |
| **Verifica** | ★ Autocritica · Giuria/voto (`jury`, `voter`) · Nessuna | affidabilità vs tempo |
| **Memoria** | ★ Top-k per rilevanza · MMR (diversità) · Pesata per recenza | contesto |
| **Algoritmi (skills)** | ★ Riusa se esiste, genera se manca · Solo esistenti · Disattivato | autonomia |

Flussi secondari (ognuno un grafo selezionabile): **Domotica**, **Visione**, **Ascolto/voce**, **Studio autonomo**,
**Automazioni**, **Squadra di agenti** (delega tra agenti come sotto-grafo).

### 4.3 Template pronti
- ⚡ **Fulmine** — cache semantica, solo parole chiave, cervello più veloce, risposta diretta.
- 🎯 **Precisione** — arbitro LLM, Plan-and-Execute, self-consistency, giuria.
- 🔒 **Fortezza privata** — solo cervelli locali, nessun cloud, memoria cifrata.
- 🌱 **Risparmio** — costo minimo, niente verifica, cache aggressiva.
- 🧒 **Bambini** — leggi rafforzate, filtri contenuti, risposte brevi e semplici.

Ogni template mostra un **radar a 4 assi** (Velocità, Qualità, Privacy, Costo) e il badge «Consigliato per il tuo
hardware», calcolato da `governor/profile.py`.

### 4.4 Esperienza d'uso
- **Canvas infinito** con zoom/pan, griglia olografica, minimappa, snap, allineamento automatico (layout a strati).
- **Porte tipizzate** (testo, intenzione, piano, contesto, risposta): un collegamento non valido si colora di rosso e
  spiega il motivo.
- **Pannello Ispettore** a destra: algoritmo, parametri (slider con intervalli sicuri), radar del nodo, documentazione.
- **Banco di prova**: scrivi una frase → il flusso in bozza viene eseguito in **modalità simulazione** (nessuna azione
  reale) → animazione del percorso, tempi per nodo, token, costo stimato.
- **Confronto A/B**: stessa frase su due flussi affiancati, con differenze evidenziate e voto dell'utente.
- **Versioni**: bozza → validazione → pubblicazione; cronologia con diff visuale e **rollback in un click**;
  annulla/ripeti illimitato in sessione.
- **Rete di sicurezza**: se un flusso pubblicato produce errori sopra soglia, Atena torna da sola all'ultima versione
  stabile e lo notifica (stesso principio del rollback degli aggiornamenti).
- **Accessibilità**: ogni operazione è possibile anche da tastiera e da lista (vista "Elenco" alternativa al grafo).

### 4.5 Modello dati (JSON firmato)

```json
{
  "id": "main",
  "version": 7,
  "parent": 6,
  "nodes": [
    { "id": "n1", "type": "understanding", "algorithm": "understanding.hybrid_arbiter",
      "params": { "min": 0.4, "close": 0.25 }, "pos": [320, 120], "locked": false }
  ],
  "edges": [ { "from": ["n0", "out"], "to": ["n1", "in"] } ],
  "meta": { "author": "nunzio", "created": "2026-10-09T10:00:00Z", "template": "precision" },
  "signature": "hmac-sha256:…"
}
```

---

## 5. Architettura (Clean Architecture, SoC, SRP)

### 5.1 Backend — nuova feature `installer_wizard/features/flows/`

```
features/flows/
├── feature.json
├── domain/                     # puro Python, nessuna dipendenza da FastAPI o I/O
│   ├── graph.py                # FlowGraph, Node, Edge, Port (dataclass frozen)
│   ├── algorithm.py            # AlgorithmSpec: id, node_type, params schema, ports, traits (speed/quality/privacy/cost)
│   ├── rules.py                # invarianti: DAG, nodi obbligatori, nodo Leggi bloccato, porte compatibili, limiti dimensione
│   └── errors.py
├── application/                # casi d'uso, uno per file (SRP)
│   ├── list_catalog.py
│   ├── get_flow.py
│   ├── save_draft.py
│   ├── validate_flow.py
│   ├── publish_flow.py
│   ├── rollback_flow.py
│   ├── simulate_flow.py
│   └── ports.py                # interfacce (Protocol): FlowRepository, AlgorithmRegistry, Signer, Clock, EventLedger
├── infrastructure/
│   ├── json_repository.py      # /var/lib/atena/flows, scrittura atomica (tmp + fsync + rename), permessi 0600
│   ├── hmac_signer.py          # firma HMAC-SHA256 con chiave in vault, confronto a tempo costante
│   ├── registry.py             # catalogo algoritmi: adattatori verso brain.scope, understanding.router, team.router, …
│   ├── ledger.py               # ogni pubblicazione/rollback è un evento immutabile
│   └── runtime.py              # FlowRuntime: risolve l'algoritmo attivo per un nodo, con fallback al default sicuro
└── interface/
    ├── api.py                  # admin_routes (solo :8080)
    └── schemas.py              # modelli Pydantic v2 con `extra="forbid"`, limiti di lunghezza e range
```

Regola delle dipendenze: `interface → application → domain`; `infrastructure` implementa le porte di `application`.
Il dominio non importa nulla dall'esterno.

**Integrazione con il motore esistente** (minima e reversibile): i punti decisionali già esistenti chiedono la
strategia al runtime invece di leggere direttamente `.env`:

```python
strategy = flows.runtime.algorithm_for("brain.select", default=scope.strategy_of(role))
```

Se la feature `flows` è spenta o il flusso non è valido, il default è il comportamento di oggi: **nessuna regressione**.

**API** (`/api/flows`, tutte autenticate, CSRF, audit):

| Metodo | Percorso | Caso d'uso |
|---|---|---|
| GET | `/api/flows/catalog` | elenco nodi e algoritmi con tratti e schemi |
| GET | `/api/flows` · `/api/flows/{id}` | flussi e versione attiva |
| PUT | `/api/flows/{id}/draft` | salva bozza (ETag / `If-Match` contro le sovrascritture) |
| POST | `/api/flows/{id}/validate` | errori e avvisi per nodo |
| POST | `/api/flows/{id}/simulate` | esecuzione a secco, risposta in SSE |
| POST | `/api/flows/{id}/publish` | richiede ri-autenticazione recente (step-up) |
| POST | `/api/flows/{id}/rollback/{version}` | ritorno a versione firmata |
| GET | `/api/flows/{id}/history` | versioni e diff |

### 5.2 Backend — supporto alla shell

| Modulo | Responsabilità unica |
|---|---|
| `backend/nexus_api.py` | `GET /api/nexus/summary`, `/api/nexus/search` (indice per la command palette) |
| `backend/zones.py` | mappa `category → zone/family`, livello di visibilità |
| `backend/onboarding.py` | stato del wizard di primo avvio per utente |
| `backend/preferences.py` | livello, lingua, preferiti per utente (lato server) |
| `backend/journey_stream.py` | SSE dei viaggi del ragionamento per Plancia e Flow Studio |

### 5.3 Frontend — `installer_wizard/web/nexus/`

Scelta: **Web Components nativi + ES modules + import map**, senza bundler e senza dipendenze npm a runtime.
Motivi: coerente con l'attuale servizio statico, superficie della supply chain minima, compatibile con CSP rigorosa,
nessuna build da mantenere sul dispositivo.

```
web/nexus/
├── index.html                  # solo markup minimo, nessuno script/stile inline
├── importmap.json
├── core/                       # infrastruttura, nessuna UI
│   ├── http.js                 # fetch con CSRF, timeout, AbortController, errori tipizzati
│   ├── store.js                # stato reattivo a segnali
│   ├── router.js               # routing per hash/History, guardie per livello
│   ├── i18n.js                 # riusa i cataloghi esistenti
│   ├── sse.js                  # riconnessione con backoff
│   └── level.js                # explorer | pilot | architect
├── domain/                     # logica UI pura e testabile
│   ├── flow-graph.js           # copia lato client delle regole di validazione (feedback immediato)
│   ├── zones.js
│   └── search-index.js
├── design/                     # design system
│   ├── tokens.css              # evoluzione di shared/atena.css
│   ├── motion.css              # rispetta prefers-reduced-motion
│   └── components/             # at-card, at-stepper, at-toggle3, at-radar, at-orb, at-palette, at-toast, ...
├── features/                   # una cartella per pagina, ciascuna con view + controller
│   ├── login/
│   ├── onboarding/
│   ├── home/
│   ├── brain/
│   ├── flows/                  # canvas, inspector, testbench, history
│   ├── tools/
│   ├── trust/
│   ├── network/
│   ├── system/
│   └── observatory/
└── legacy/
    └── bridge.js               # incorpora le schede admin.html esistenti finché non vengono migrate
```

**Motore del canvas**: sviluppato in casa su **SVG + Pointer Events** (nodi come `foreignObject` o gruppi SVG,
collegamenti come curve di Bézier, layout automatico a strati tipo Sugiyama). Evita librerie esterne per la parte più
interattiva e mantiene il controllo totale su accessibilità e sicurezza. Per grafi oltre ~300 nodi si passa al
rendering su `<canvas>` con lo stesso modello.

### 5.4 Sicurezza (applicata a tutta la sezione :8080)
- **CSP rigorosa**: `default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none';
  frame-ancestors 'none'; require-trusted-types-for 'script'` — eliminando ogni script/stile inline.
- **Trusted Types** e nessun `innerHTML` con dati: rendering tramite `textContent`/template.
- **Header**: HSTS, `X-Content-Type-Options`, `Referrer-Policy: no-referrer`, `Permissions-Policy` minima,
  `Cross-Origin-Opener-Policy`/`Embedder-Policy`.
- **CSRF** con token sincronizzato + controllo `Origin` (riuso di `backend/origin_guard.py`).
- **Step-up authentication** (password o passkey negli ultimi 5 minuti) per: pubblicare un flusso, firewall, VPN,
  riavvio, gestione utenti, chiavi cloud.
- **Validazione server-side** di ogni payload (Pydantic `extra="forbid"`), limiti su nodi/archi/parametri,
  nessuna esecuzione di codice fornito dall'utente nei flussi.
- **Integrità**: flussi firmati HMAC; versioni immutabili; ogni modifica nel ledger con utente, ora, diff.
- **Segreti**: mai restituiti al client, solo mascherati; cifratura a riposo tramite `vault`.
- **Asset vendor** con hash SRI e versioni bloccate.
- **Rate limiting** su login, simulazione e pubblicazione.

---

## 6. Direzione visiva: come renderlo davvero "wow"

**Concept: "Nexus olografico"** — il pannello è la plancia di comando di un'intelligenza viva, non un gestionale.

1. **Atena Orb** — una sfera di luce (riuso del motore 3D del display, versione leggera in WebGL con fallback CSS)
   che respira, cambia colore con lo stato, parla e indica con un raggio luminoso l'elemento da toccare. È la guida
   dell'Esploratore e l'indicatore di salute del Pilota.
2. **Mappa neurale viva** — in Plancia e nel Flow Studio le richieste reali scorrono come particelle lungo il grafo:
   si *vede* Atena pensare.
3. **Transizioni spaziali** — passando da una zona all'altra la camera "vola" nella costellazione (View Transitions API);
   aprire uno strumento è uno zoom sul suo satellite.
4. **Materiali** — vetro scuro con bordi a luce ciano, aurora di sfondo che si muove lentamente, griglia olografica in
   prospettiva, tipografia Inter + JetBrains Mono per i dati, micro-glow sui valori che cambiano.
5. **Suono e aptica** — riuso di `shared/sfx.js` per conferme sottili; vibrazione su mobile; tutto disattivabile.
6. **Replay del ragionamento** — ogni risposta di Atena si può "riavvolgere" e riguardare nodo per nodo.
7. **Progressione** — per l'Esploratore: anello «Atena è pronta all'82 %», piccole medaglie quando si attiva un senso,
   linguaggio caldo e illustrato.
8. **Modalità "Spiegamelo"** — su qualsiasi elemento, l'Orb spiega in parole semplici cosa fa e cosa succede se lo cambi.
9. **Accessibile per davvero** — contrasto AA, focus visibile luminoso, navigazione da tastiera completa,
   `prefers-reduced-motion` che sostituisce le animazioni con dissolvenze, layout perfetto anche su telefono.

---

## 7. Roadmap a fasi

La nuova interfaccia vive su `/nexus` dietro l'impostazione `ATENA_NEXUS_UI`; il pannello attuale resta su `/` finché
non si raggiunge la parità. Nessuna rottura per gli utenti esistenti.

| Fase | Contenuto | Esito verificabile |
|---|---|---|
| **F0 — Fondamenta** (1 sett.) | design token, componenti base, `core/*`, CSP rigorosa su `/nexus`, livello lato server | pagina vuota con login, palette e cambio livello; test di sicurezza header |
| **F1 — Shell e Plancia** (1–2 sett.) | navigazione 8 zone, `nexus_api`, Plancia per i 3 livelli, ponte legacy | ogni scheda esistente raggiungibile dalla nuova shell |
| **F2 — Strumenti** (2 sett.) | catalogo unificato, pagina strumento a template, `zone/family/level/wizard` nel manifest, migrazione delle categorie | tutte le 63 feature visibili e configurabili; wizard su 5 feature pilota (vision, ear, home_assistant, telegram, brain) |
| **F3 — Primo avvio** (1 sett.) | wizard "Risveglio di Atena" a 7 step | un utente nuovo arriva a un sistema funzionante senza aprire altre pagine |
| **F4 — Flow Studio MVP** (3 sett.) | feature `flows` (dominio, casi d'uso, repository, firma), catalogo dagli algoritmi già esistenti, canvas sola lettura + cambio algoritmo per nodo, template | il flusso principale è visibile e modificabile; il motore legge le scelte dal runtime con fallback |
| **F5 — Flow Studio completo** (3 sett.) | drag & drop, porte tipizzate, banco di prova in simulazione, A/B, versioni, rollback automatico | un esperto crea un flusso personalizzato, lo prova, lo pubblica e lo annulla |
| **F6 — Nuovi algoritmi** (2–3 sett.) | cache semantica, bandit UCB, BM25/ibrido, Tree-of-Thoughts, self-consistency, MMR | ogni algoritmo con test e metriche reali nel radar |
| **F7 — Regole, Rete, Sistema, Osservatorio** (2 sett.) | migrazione delle schede restanti, macchina del tempo, punteggio di sicurezza | parità completa con il pannello attuale |
| **F8 — Rifinitura e passaggio** (1 sett.) | motion, suoni, accessibilità, prestazioni, traduzioni IT/EN/FR | `/nexus` diventa la pagina predefinita; il vecchio pannello resta raggiungibile per una versione |

---

## 8. Qualità e test
- **Dominio**: test unitari puri per `rules.py` (cicli, nodi obbligatori, porte, limiti) e per ogni caso d'uso con
  repository in memoria.
- **API**: test pytest nello stile di `installer_wizard/tests/` per autenticazione, CSRF, step-up, ETag, firma.
- **Algoritmi**: set di frasi di riferimento con risultati attesi; il radar mostra numeri misurati, non dichiarati.
- **End-to-end**: Playwright (Chromium già disponibile) per onboarding, cambio algoritmo, pubblicazione e rollback.
- **Accessibilità**: axe-core in CI su ogni pagina.
- **Regressioni visive**: screenshot per livello × tema × larghezza (telefono, tablet, desktop).
- **Prestazioni**: primo rendering < 1 s sulla LAN, canvas a 60 fps con 150 nodi, nessun asset > 200 KB non compresso.

## 9. Indicatori di successo
- Un nuovo utente completa la configurazione base in **meno di 5 minuti** senza documentazione.
- Il numero di clic per raggiungere qualsiasi impostazione scende a **≤ 3** (o 1 con la palette).
- Zero regressioni: il comportamento predefinito del ragionamento resta identico finché l'utente non cambia flusso.
- 100 % delle feature raggiungibili dalla zona Strumenti.
