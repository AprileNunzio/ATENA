from contextvars import Token

from features.brain import stages
from features.brain.journey import journeys


class ChatJourney:
    def __init__(self, said: str, text: str, device: str, who: str) -> None:
        self.tracker = journeys.start_journey(said or text, who=who)
        self.input = self.tracker.add_node("input", "Domanda Ricevuta", f"«{text}» · Origine: {device}", state="ok")
        self.laws = self.tracker.add_node("laws", "Leggi Fondamentali", "Verifica conformità etica e vincoli di sicurezza",
                                          state="running", parent=self.input)
        self.tracker.add_edge(self.input, self.laws, "flow", "conformità")
        self.token: Token | None = None

    def refused(self, answer: str) -> None:
        self.tracker.update_node(self.laws, state="fail", detail="Bloccato dalle Leggi Fondamentali: violazione vincoli")
        node = self.tracker.add_node("answer", "Rifiuto Etico", answer, state="fail", parent=self.laws)
        self.tracker.add_edge(self.laws, node, "flow", "blocco")
        self.tracker.finish(answer=answer, agent="leggi fondamentali", state="failed")

    def enrolled(self, answer: str) -> None:
        self._admit()
        voice = self.tracker.add_node("agent", "Impronta Vocale", "Riconoscimento e registrazione voce", state="ok", parent=self.laws)
        self.tracker.add_edge(self.laws, voice, "flow", "profilazione")
        node = self.tracker.add_node("answer", "Risposta", answer, state="ok", parent=voice)
        self.tracker.add_edge(voice, node, "flow", "output")
        self.tracker.finish(answer=answer, agent="impronta vocale", state="done")

    def begin(self) -> None:
        self._admit()
        memory = self.tracker.add_node("cache", "Memoria & Contesto", "Recupero contesto conversazionale e ricordi recenti",
                                       state="ok", parent=self.laws)
        self.tracker.add_edge(self.laws, memory, "flow", "contesto")
        self.token = stages.bind(self.tracker, memory)

    def answered(self, result: dict) -> None:
        self._release()
        reply, agent = result.get("reply", ""), str(result.get("agent", "core"))
        last = self.tracker.nodes[-1]["i"]
        node = self.tracker.add_node("answer", "Risposta Finale",
                                     f"{reply}\n\nIntento: {result.get('intent', 'conversazione')} · Agente: {agent}",
                                     state="ok", parent=last)
        self.tracker.add_edge(last, node, "flow", "output")
        self.tracker.finish(answer=reply, agent=agent, state="done")

    def failed(self, exc: BaseException) -> None:
        self._release()
        self.tracker.fail(f"{type(exc).__name__}: {exc}")

    def _admit(self) -> None:
        self.tracker.update_node(self.laws, state="ok", detail="Vincoli costituzionali rispettati: richiesta ammessa")

    def _release(self) -> None:
        if self.token is not None:
            stages.release(self.token)
            self.token = None
