from dataclasses import dataclass, field

VIEW_W, VIEW_H = 1240, 540


@dataclass(frozen=True)
class Algorithm:
    id: str
    name: str
    description: str
    speed: int
    quality: int
    privacy: int
    saving: int
    default: bool = False
    available: bool = True
    effects: dict = field(default_factory=dict)

    @property
    def traits(self) -> dict:
        return {"speed": self.speed, "quality": self.quality, "privacy": self.privacy, "saving": self.saving}

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description, "traits": self.traits,
                "default": self.default, "available": self.available}


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    glyph: str
    description: str
    x: int
    y: int
    base_seconds: float
    algorithms: tuple[Algorithm, ...]
    locked: bool = False

    @property
    def default(self) -> Algorithm:
        return next(a for a in self.algorithms if a.default)

    def algorithm(self, aid: str) -> Algorithm | None:
        return next((a for a in self.algorithms if a.id == aid), None)

    @property
    def editable(self) -> bool:
        return sum(1 for a in self.algorithms if a.available) > 1

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "glyph": self.glyph, "description": self.description,
                "x": self.x, "y": self.y, "locked": self.locked, "editable": self.editable,
                "algorithms": [a.as_dict() for a in self.algorithms]}


A = Algorithm
NODES: tuple[Node, ...] = (
    Node("input", "Ingresso", "◎", "La frase arriva dalla voce, dalla chat o da Telegram.", 120, 130, 0.03,
         (A("input.multi", "Voce e testo", "Trascrizione e pulizia della frase.", 5, 4, 5, 5, default=True),)),
    Node("laws", "Leggi", "⚖", "Controlla che la richiesta rispetti le Leggi di Atena. Non si può togliere.", 320, 130, 0.02,
         (A("laws.guard", "Guardia delle Leggi", "Le leggi fondamentali più quelle che hai aggiunto.", 5, 4, 5, 5, default=True),),
         locked=True),
    Node("understanding", "Comprensione", "⌖", "Capisce quale funzione vuoi davvero, leggendo frase, contesto e conversazione.",
         520, 130, 0.08, (
             A("understanding.arbiter", "Punteggio + arbitro", "Tutte le funzioni danno un punteggio; nei casi dubbi decide il modello.",
               3, 5, 4, 3, default=True, effects={"understanding.enabled": "1", "understanding.arbiter": "1"}),
             A("understanding.score", "Solo punteggio", "Sceglie la funzione col punteggio più alto, senza chiedere al modello.",
               4, 4, 5, 4, effects={"understanding.enabled": "1", "understanding.arbiter": "0"}),
             A("understanding.keywords", "Parole chiave", "Il più rapido: confronta solo parole note, sbaglia con frasi complesse.",
               5, 2, 5, 5, effects={"understanding.enabled": "0", "understanding.arbiter": "0"}),
         )),
    Node("skills", "Algoritmi", "∑", "Calcoli e procedure come algoritmi Python verificati, riusati in millisecondi.", 720, 130, 0.05, (
        A("skills.generate", "Riusa e crea", "Usa gli algoritmi che conosce e ne scrive di nuovi quando servono.", 3, 5, 5, 3,
          default=True, effects={"skills.enabled": "1", "skills.generate": "1"}),
        A("skills.reuse", "Solo quelli che conosce", "Usa gli algoritmi già verificati, senza scriverne di nuovi.", 5, 3, 5, 5,
          effects={"skills.enabled": "1", "skills.generate": "0"}),
        A("skills.off", "Spenti", "Non usa algoritmi: risponde sempre il modello.", 4, 2, 5, 3, effects={"skills.enabled": "0"}),
    )),
    Node("brain", "Scelta cervello", "◈", "Sceglie quale modello risponde, tra locali, altri computer e cloud.", 920, 130, 0.04, (
        A("brain.order", "Ordine di priorità", "Il primo disponibile della tua lista, ovunque si trovi.", 3, 4, 3, 3, default=True,
          effects={"brain.strategy": "order", "brain.scope": "anywhere"}),
        A("brain.fastest", "Il più veloce", "Quello con il tempo di risposta misurato più basso.", 5, 3, 3, 3,
          effects={"brain.strategy": "fastest", "brain.scope": "anywhere"}),
        A("brain.home_first", "Prima in casa", "Prova prima i modelli di casa e usa il cloud solo se servono.", 3, 4, 4, 4,
          effects={"brain.strategy": "order", "brain.scope": "home_first"}),
        A("brain.home", "Solo in casa", "Nessun dato esce dalla rete di casa.", 3, 3, 5, 5,
          effects={"brain.strategy": "order", "brain.scope": "home"}),
    )),
    Node("memory", "Memoria", "◉", "Ricorda fatti e preferenze e li aggiunge al contesto.", 1120, 130, 0.06, (
        A("memory.on", "Ricorda", "Usa i ricordi più vicini alla domanda.", 4, 5, 4, 4, default=True, effects={"memory.enabled": "1"}),
        A("memory.off", "Non ricordare", "Ogni domanda parte da zero.", 5, 2, 5, 5, effects={"memory.enabled": "0"}),
    )),
    Node("reasoning", "Ragionamento", "∴", "Come il modello arriva alla risposta.", 1120, 400, 0.9, (
        A("reasoning.react", "ReAct con strumenti", "Alterna pensiero e uso degli strumenti.", 3, 4, 5, 3, default=True),
        A("reasoning.cot", "Catena di pensiero", "Ragiona passo per passo prima di rispondere.", 3, 4, 5, 3, available=False),
        A("reasoning.tot", "Albero di pensieri", "Esplora più strade e sceglie la migliore.", 1, 5, 5, 1, available=False),
        A("reasoning.vote", "Voto a maggioranza", "Più risposte indipendenti, vince la più frequente.", 2, 5, 5, 2, available=False),
    )),
    Node("agent", "Strumenti", "⚒", "L'agente usa gli strumenti di Atena: casa, file, rete, computer.", 920, 400, 0.4, (
        A("agent.full", "Accesso completo", "Può usare tutti gli strumenti, comprese le azioni sul sistema.", 4, 5, 3, 4, default=True,
          effects={"agent.enabled": "1", "agent.access": "completo"}),
        A("agent.standard", "Accesso standard", "Solo strumenti sicuri: niente comandi di sistema.", 4, 4, 5, 4,
          effects={"agent.enabled": "1", "agent.access": "standard"}),
        A("agent.off", "Senza strumenti", "Solo conversazione, nessuna azione.", 5, 2, 5, 5, effects={"agent.enabled": "0"}),
    )),
    Node("verify", "Verifica", "✓", "Controlla la risposta prima di dartela.", 720, 400, 0.3, (
        A("verify.critic", "Autocritica", "Il modello rilegge e corregge la propria risposta.", 3, 4, 5, 3, default=True),
        A("verify.jury", "Giuria", "Più modelli votano la risposta migliore.", 1, 5, 4, 1, available=False),
    )),
    Node("widgets", "Widget", "▣", "Mostra sul display widget, schede e immagini che accompagnano la risposta.", 520, 400, 0.2, (
        A("widgets.smart", "Quando servono", "Widget per spiegazioni, confronti e risposte lunghe; voce per il resto.", 4, 4, 5, 4,
          default=True, effects={"presentation.mode": "smart"}),
        A("widgets.rich", "Sempre visivo", "Accompagna con un widget anche le risposte brevi.", 3, 5, 5, 3,
          effects={"presentation.mode": "rich"}),
        A("widgets.voice", "Solo voce", "Nessun widget generato: risposte solo a voce e testo.", 5, 2, 5, 5,
          effects={"presentation.mode": "voice"}),
    )),
    Node("answer", "Risposta", "❝", "Parla, scrive o mostra un widget sul display.", 320, 400, 0.05,
         (A("answer.multi", "Voce, testo e widget", "Sceglie il formato più adatto.", 5, 4, 5, 5, default=True),)),
)
NODE_BY_ID = {n.id: n for n in NODES}
EDGES = tuple((a.id, b.id) for a, b in zip(NODES, NODES[1:]))

TEMPLATES = {
    "default": {"name": "Predefinito", "hint": "Come ragiona oggi", "pick": {}},
    "fast": {"name": "Fulmine", "hint": "Risposte istantanee",
             "pick": {"understanding": "understanding.score", "skills": "skills.reuse", "brain": "brain.fastest",
                      "widgets": "widgets.voice"}},
    "precise": {"name": "Precisione", "hint": "Massima qualità",
                "pick": {"understanding": "understanding.arbiter", "brain": "brain.order", "widgets": "widgets.rich"}},
    "private": {"name": "Fortezza privata", "hint": "Niente esce di casa", "pick": {"brain": "brain.home", "agent": "agent.standard"}},
    "eco": {"name": "Risparmio", "hint": "Costo minimo",
            "pick": {"understanding": "understanding.score", "brain": "brain.home_first", "skills": "skills.reuse"}},
    "kids": {"name": "Bambini", "hint": "Sicuro e semplice",
             "pick": {"brain": "brain.home", "agent": "agent.standard", "skills": "skills.reuse", "widgets": "widgets.rich"}},
}


def defaults() -> dict[str, str]:
    return {n.id: n.default.id for n in NODES}


def template(name: str) -> dict[str, str]:
    if name not in TEMPLATES:
        raise ValueError("Modello di flusso sconosciuto")
    return {**defaults(), **TEMPLATES[name]["pick"]}
