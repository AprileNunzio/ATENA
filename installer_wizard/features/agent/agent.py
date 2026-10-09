import json
import time

from state import store

from features.agent import registry, tools_cameras, tools_comm, tools_display, tools_files, tools_media, tools_packages, tools_rpa, tools_system
from features.agent.paths import FILES, AccessDenied, layout, level
from features.automations import tools as tools_automations
from features.documents import tools as tools_documents
from features.firewall import tools as tools_firewall
from features.vpn import tools as tools_vpn
from features.proxmox import tools as tools_proxmox
from features.voicestudio import tools as tools_voicestudio
from features.network import tools as tools_network
from features.redalert import tools as tools_redalert
from features.autonomy import tools as tools_autonomy
from features.authz import gate
from features.authz.principal import SYSTEM, act_as, current
from features.brain.llm import BrainUnavailable, generate
from features.chat.context import session_key
from features.forge import tools as tools_forge
from features.team import runner
from features.team import tools as tools_team
from features.team.board import board
from features.shares import archive
from features.whiteboard import tools as tools_whiteboard

MODULES = (tools_cameras, tools_comm, tools_display, tools_files, tools_media, tools_packages, tools_rpa, tools_system, tools_autonomy, tools_automations, tools_documents, tools_team, tools_forge, tools_whiteboard, tools_firewall, tools_vpn, tools_proxmox, tools_voicestudio, tools_network, tools_redalert)
MAX_STEPS = 8
PENDING_TTL = 180

RULES = (
    "Sei Atena, l'assistente che agisce davvero sul server di casa usando gli strumenti qui sotto.\n"
    "Strumenti disponibili (ogni strumento appartiene a un agente della squadra; per cosa sa fare un agente usa agent_info, "
    "per passare un compito a un altro agente usa agent_ask o agent_tell):\n{tools}\n\n{team}\n\n"
    "Cartella di lavoro: {files} (i percorsi relativi partono da qui).\n"
    "Cartella condivisa: {share}, con le sottocartelle {layout}. I file lasciati dagli utenti di solito sono in "
    "«05 Scambio»: un percorso che inizia con il nome di una sottocartella (per esempio «Scambio/offerta.docx») "
    "punta lì; se non sai dove si trova un file cercalo con find_files.\n"
    "Rispondi SEMPRE e SOLO con un oggetto JSON, uno di questi due:\n"
    '{{"tool": "nome_strumento", "args": {{...}}}}  per usare UNO strumento e vederne l\'esito;\n'
    '{{"answer": "frase finale breve in italiano, da dire a voce, dando del Lei e chiamando «signore» chi parla"}}  quando hai finito, oppure per chiedere '
    "un'informazione che manca (per esempio l'indirizzo email).\n"
    "Regole: non inventare esiti, aspetta il risultato di ogni strumento; non ripetere uno strumento già riuscito; "
    "per mandare un progetto usa i percorsi restituiti dagli strumenti; se un destinatario è un nome, cercalo con "
    "find_contact; se uno strumento fallisce prova un'alternativa o spiega il problema. Esegui SUBITO ciò che "
    "viene chiesto con gli strumenti diretti (create_site, write_file, make_dir, create_3d, share_folder…): crea "
    "automazioni o compiti programmati solo se l'utente chiede esplicitamente qualcosa di ricorrente, programmato "
    "o condizionato. Tutto ciò che crei va nella cartella condivisa di Atena, già organizzata in sottocartelle."
)


def _summary(name: str, args: dict) -> str:
    a = registry.clean_args(name, args)
    if name == "send_email":
        att = a.get("attachments")
        extra = f" con allegati {att}" if att else ""
        return f"invio l'email a {a.get('to')} con oggetto «{a.get('subject', '')}»{extra}"
    if name == "delete":
        return f"sposto nel cestino {a.get('path')}"
    if name == "run_command":
        return f"eseguo il comando «{a.get('command')}»"
    if name in ("write_file", "make_dir"):
        return f"scrivo in {a.get('path')}, fuori dalla cartella di lavoro"
    if name in ("copy", "move"):
        return f"{'copio' if name == 'copy' else 'sposto'} {a.get('src')} in {a.get('dst')}"
    return f"eseguo {name} con {json.dumps(a, ensure_ascii=False)[:200]}"


class Agent:
    def __init__(self) -> None:
        self.pending: dict[str, dict] = {}
        self.last_steps: list[dict] = []

    async def tools(self, request: str) -> str:
        try:
            from features.team.router import tool_router
            relevant_agents = await tool_router.retrieve(request, top_k=7)
        except Exception as exc:
            store.event("WARN", f"Selezione strumenti per agente non riuscita: {exc}", "agent")
            relevant_agents = None
        return registry.describe_for_agents(level(), relevant_agents, gate.within_role)

    async def _decide(self, request: str, steps: list[dict]) -> dict:
        history = "\n".join(f"{i + 1}. {s['tool']}({json.dumps(s['args'], ensure_ascii=False)[:300]}) → {s['result'][:1200]}"
                            for i, s in enumerate(steps))
        prompt = f"Richiesta: {request}\n\n" + (f"Passi già eseguiti:\n{history}\n\nProssima mossa?" if steps else "Prima mossa?")
        reply = await generate(prompt, as_json=True, max_tokens=900, temperature=0.1, kind="deep",
                               system=RULES.format(tools=await self.tools(request), files=FILES, share=archive.ROOT,
                                                  layout=layout(), team=board.digest()), timeout=240)
        return reply if isinstance(reply, dict) else {}

    async def _execute(self, name: str, args: dict, steps: list[dict]) -> None:
        try:
            result = await runner.run_as(name, args)
        except (AccessDenied, PermissionError) as exc:
            result = f"NEGATO: {exc}"
        except Exception as exc:
            result = f"ERRORE: {str(exc)[:300]}"
        if not result.startswith(("ERRORE", "NEGATO")):
            try:
                from features.team import roster
                from features.team.router import tool_router
                tool_router.learn_success(roster.owner(name), registry.REQUEST.get())
            except Exception as exc:
                store.event("WARN", f"Apprendimento instradamento non riuscito: {exc}", "agent")
        steps.append({"tool": name, "args": registry.clean_args(name, args), "result": result})
        store.event("INFO", f"Agente · {name}: {result[:140]}", "agent")

    async def run(self, request: str, steps: list[dict] | None = None, auto: str = "", trusted: bool = False,
                  routine: str = "", readonly: bool = False) -> str:
        token = act_as(SYSTEM) if auto else None
        try:
            return await self._run(request, steps, auto, trusted, routine, readonly)
        finally:
            if token is not None:
                current.reset(token)

    async def _run(self, request: str, steps: list[dict] | None, auto: str, trusted: bool, routine: str,
                   readonly: bool = False) -> str:
        steps = [] if steps is None else steps
        self.last_steps = steps
        registry.REQUEST.set(request)
        for _ in range(MAX_STEPS):
            allowed = {t["name"] for t in registry.available(level()) if gate.within_role(t["name"])}
            try:
                move = await self._decide(request, steps)
            except BrainUnavailable as exc:
                return f"Il mio cervello non è raggiungibile in questo momento: {exc}"
            if move.get("answer") or not move.get("tool"):
                return str(move.get("answer") or "Fatto, signore.")[:600]
            name, args = str(move["tool"]), move.get("args") or {}
            if name not in allowed:
                steps.append({"tool": name, "args": {}, "result": "ERRORE: strumento inesistente o non consentito"})
                continue
            decision = gate.tool(name)
            if not decision.allowed:
                return gate.refusal(decision)
            if registry.needs_confirm(name, args) and not (auto and trusted):
                problem = registry.precheck(name, args)
                if problem:
                    steps.append({"tool": name, "args": registry.clean_args(name, args), "result": f"ERRORE: {problem}"})
                    continue
                if auto:
                    verdict = await self._automatic(name, args, request, steps, auto, routine, readonly)
                    if verdict is None:
                        continue
                    return verdict
                self.pending[session_key()] = {"request": request, "steps": steps, "tool": name, "args": args, "at": time.time()}
                return f"Prima di procedere: {_summary(name, args)}. Confermi?"
            await self._execute(name, args, steps)
        done = [s for s in steps if not s["result"].startswith(("ERRORE", "NEGATO"))]
        return f"Ho eseguito {len(done)} passi ma non ho finito del tutto: ripetimi cosa manca."

    async def _automatic(self, name: str, args: dict, request: str, steps: list[dict], auto: str, routine: str,
                         readonly: bool) -> str | None:
        from features.autonomy import approvals
        from features.autonomy.trust import book
        if readonly:
            steps.append({"tool": name, "args": registry.clean_args(name, args),
                          "result": "NEGATO: in diagnosi si usano solo strumenti di sola lettura, senza modificare nulla"})
            return None
        if book.trusted(name, args):
            await self._execute(name, args, steps)
            return None
        if book.rejected(name, args):
            steps.append({"tool": name, "args": registry.clean_args(name, args),
                          "result": "NEGATO: azione rifiutata di recente dal proprietario, non la ripropongo"})
            return None
        item = approvals.add(auto, _summary(name, args), request, steps, name, args, routine)
        if not item.get("existing"):
            await self.on_approval(item)
        return f"In attesa della sua approvazione, signore: {_summary(name, args)}."

    async def on_approval(self, item: dict) -> None:
        pass

    async def resume(self, item: dict, yes: bool) -> str:
        if not yes:
            return "Annullato."
        steps = item["steps"]
        await self._execute(item["tool"], item["args"], steps)
        return await self.run(item["request"], steps, auto=item["title"], trusted=bool(item.get("trusted")),
                              routine=item.get("routine", ""))

    def _expire(self) -> None:
        now = time.time()
        for key in [k for k, v in self.pending.items() if now - v["at"] > PENDING_TTL]:
            del self.pending[key]

    def has_pending(self) -> bool:
        self._expire()
        return session_key() in self.pending

    def drop_pending(self) -> None:
        self.pending.pop(session_key(), None)

    async def confirm(self, yes: bool) -> str:
        self._expire()
        p = self.pending.pop(session_key(), None)
        if not p:
            return "Non avevo nulla in sospeso."
        if not yes:
            return "Annullato, signore."
        await self._execute(p["tool"], p["args"], p["steps"])
        return await self.run(p["request"], p["steps"])


agent = Agent()
__all__ = ["agent", "MODULES"]
