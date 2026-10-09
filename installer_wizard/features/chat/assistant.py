import importlib
import time

import httpx
from state import store

from features.actions import router as actions
from features.authz import gate
from features.brain import stages
from features.brain.llm import BrainUnavailable
from features.chat import code
from features.chat import context as request_context
from features.chat.compose import compose_generic
from features.chat.intents import detect_intent
from features.chat.skill_dispatch import run_skill
from features.chat.skills.people import person_info_skill
from features.locale.pivot import pivot
from features.chat.templates import remember_template
from features.understanding import router as understanding

CONNECTORS = {"places": "features.places.commands", "vault": "features.vault.commands", "selftest": "features.selftest.commands", "sounds": "features.sounds.commands", "whiteboard": "features.whiteboard.commands", "screens": "features.desktop.commands", "models3d": "features.models3d.commands", "documents": "features.documents.commands", "music": "features.music.commands", "livecam": "features.cameras.commands", "vision": "features.vision.sight", "gservices": "features.google.commands", "maps": "features.maps.maps"}

EARLY = ("whiteboard", "livecam")
PERSONAL = {"gservices", "vault", "documents", "maps", "vision", "livecam"}


def _refused(name: str, started: float) -> dict | None:
    decision = gate.connector(name)
    if decision.allowed:
        return None
    return {"reply": gate.refusal(decision), "ui": {"mode": "face"}, "intent": "authz", "agent": f"autorizzazioni · {name}",
            "elapsed_ms": int((time.time() - started) * 1000)}


async def _agent(text: str, started: float) -> dict:
    from features.agent import commands as agent_cmd
    async with stages.stage("agent", "Agente con strumenti"):
        speech, ui = await agent_cmd.answer(text)
    return {"reply": speech, "ui": ui, "intent": "agent", "agent": "agente · strumenti",
            "elapsed_ms": int((time.time() - started) * 1000)}


async def _connect(text: str, started: float, only: tuple | None = None, skip: tuple = ()) -> dict | None:
    for connector, module in CONNECTORS.items():
        if (only and connector not in only) or connector in skip:
            continue
        if not gate.connector_allowed(connector):
            continue
        try:
            async with stages.attempt("tool", f"Connettore · {connector}", misses=(LookupError,)):
                speech, ui = await importlib.import_module(module).answer(text)
        except LookupError:
            continue
        except Exception as exc:
            if type(exc).__name__ == "NotLinked":
                speech, ui = str(exc), {"mode": "face"}
            else:
                store.event("WARN", f"Connettore {connector}: {exc}", connector)
                speech, ui = f"Non riesco a raggiungere il servizio in questo momento: {exc}", {"mode": "face"}
        elapsed = int((time.time() - started) * 1000)
        if ui.get("mode") != "face":
            remember_template(connector, ui, elapsed)
        if connector in PERSONAL and ui.get("mode") == "focus":
            ui["personal"] = True
        return {"reply": speech, "ui": ui, "intent": connector, "agent": connector, "elapsed_ms": elapsed}
    return None


async def _home(text: str, started: float) -> dict | None:
    try:
        from features.home_assistant.home import brain as home_brain
        async with stages.attempt("agent", "Domotica") as probe:
            home_out = await home_brain.handle(text)
            if not home_out:
                probe.skip()
    except Exception as exc:
        store.event("WARN", f"Casa non disponibile: {exc}", "home")
        return None
    if not home_out:
        return None
    speech, ui, agent = home_out
    elapsed = int((time.time() - started) * 1000)
    if ui.get("mode") != "face":
        remember_template("home", ui, elapsed)
    return {"reply": speech, "ui": ui, "intent": "home", "agent": agent, "elapsed_ms": elapsed}


async def handle(text: str, core_call, speech_lang: dict | None = None) -> dict:
    lang = (speech_lang or {}).get("lang", "it")
    switched = bool((speech_lang or {}).get("switched"))
    routing = text if switched else await pivot.to_pivot(text, lang)

    generated = {"by_model": False}

    async def ask(_query: str) -> dict:
        generated["by_model"] = True
        return await core_call(text)

    result = await _route(routing, ask, speech_lang)
    if lang != pivot.PIVOT and result.get("reply"):
        result["reply"] = await pivot.from_pivot(result["reply"], lang, force=not generated["by_model"])
    return result


async def _route(text: str, core_call, speech_lang: dict | None = None) -> dict:
    started = time.time()
    from features.automations.bus import emit
    emit("voice_command", {"text": text})
    try:
        from features.automations import commands as automation_cmd
        async with stages.attempt("skill", "Automazioni", misses=(LookupError,)):
            speech, ui = await automation_cmd.answer(text)
        return {"reply": speech, "ui": ui, "intent": "automations", "agent": "automazioni",
                "elapsed_ms": int((time.time() - started) * 1000)}
    except LookupError:
        pass
    try:
        from features.scene import voice as scene_voice
        from features.scene.service import scene
        spatial = scene_voice.answer(text, scene.graph, pivot.PIVOT)
    except Exception:
        spatial = None
    if spatial:
        return {"reply": spatial, "ui": {"mode": "face"}, "intent": "scene", "agent": "scena",
                "elapsed_ms": int((time.time() - started) * 1000)}
    located = await _connect(text, started, ("places",))
    if located:
        return located
    from features.agent import commands as agent_cmd
    if agent_cmd.strong(text):
        return await _agent(text, started)
    tried: set[str] = set()
    async with stages.stage("classifier", "Classificatore Intenti", "Analisi semantica e instradamento") as probe:
        decision = await understanding.route(text, request_context.device.get())
        probe.note(understanding.describe(decision))
    domains = decision.domains if understanding.enabled() else list(EARLY)
    if understanding.enabled() and domains and (refused := _refused(domains[0], started)):
        return refused
    for domain in domains:
        tried.add(domain)
        if domain == "people":
            if not gate.connector_allowed("people"):
                continue
            speech, ui = await person_info_skill(text)
            ui["personal"] = True
            return {"reply": speech, "ui": ui, "intent": "people", "agent": "persone", "elapsed_ms": int((time.time() - started) * 1000)}
        out = await (_home(text, started) if domain == "home" else _connect(text, started, (domain,)))
        if out:
            return out
    if "home" not in tried:
        out = await _home(text, started)
        if out:
            return out
    async with stages.attempt("tool", "Azioni") as probe:
        act = await actions.handle(text)
        if not act:
            probe.skip()
    if act:
        speech, ui, agent = act
        elapsed = int((time.time() - started) * 1000)
        return {"reply": speech, "ui": ui, "intent": "action", "agent": agent, "elapsed_ms": elapsed}
    found = await _connect(text, started, None, tuple(tried))
    if found:
        return found
    intent = detect_intent(text)
    if (speech_lang or {}).get("switched") and intent not in ("voices",):
        intent = "conversation"
    agent = "atena_ui"
    refused = _refused(intent, started)
    if refused:
        return refused
    try:
        async with stages.attempt("skill", f"Abilità · {intent}", misses=(LookupError,)):
            speech, ui = await run_skill(intent, text)
    except LookupError:
        from features.skills.library import library
        async with stages.attempt("skill", "Libreria di algoritmi") as probe:
            solved = await library.try_answer(text)
            if not solved:
                probe.skip()
        if solved:
            agent = f"algoritmo · {solved['name']} ({solved['total_ms']} ms)"
            speech, ui = solved["speech"], {"mode": "face"}
        elif actions.CALC.search(text) and (calc := await actions.try_calc(text)):
            agent = "calcolo verificato"
            speech, ui = calc
        else:
            agent, speech, ui = await _converse(text, core_call)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        store.event("WARN", f"Abilità '{intent}' non disponibile: {exc}", "assistant")
        async with stages.stage("system2", "Generazione della risposta", f"Abilità «{intent}» non disponibile"):
            data = await core_call(text)
        agent = data.get("agent_id") or "core"
        speech, ui = code.answer(data.get("speech_output") or "", text) or compose_generic(data.get("speech_output") or "…", text)
    if ui.get("code"):
        intent = ui.pop("intent", "code_view")

    elapsed = int((time.time() - started) * 1000)
    if ui.get("mode") != "face":
        remember_template(intent, ui, elapsed)
    return {"reply": speech, "ui": ui, "intent": intent, "agent": agent, "elapsed_ms": elapsed}


async def _diagnose(text: str) -> tuple[str, dict] | None:
    try:
        return await actions.diagnose_action(text)
    except BrainUnavailable as exc:
        store.event("WARN", f"Diagnostica senza cervello disponibile: {exc}", "assistant")
        return None


async def _converse(text: str, core_call) -> tuple[str, str, dict]:
    from features.agent import commands as agent_cmd
    if agent_cmd.weak(text) and not code.wanted(text):
        async with stages.stage("agent", "Agente con strumenti"):
            speech, ui = await agent_cmd.answer(text)
        return "agente · strumenti", speech, ui
    if actions.ACTIONISH.search(text):
        found = await _diagnose(text)
        if found:
            return "diagnostica · comando di sistema", *found
    async with stages.stage("system2", "Generazione della risposta") as probe:
        data = await core_call(text)
        probe.note(f"Modello: {data.get('agent_id') or 'core'}")
    reply = data.get("speech_output") or "…"
    refused = bool(actions.REFUSAL.search(reply))
    if refused and not actions.ACTIONISH.search(text):
        found = await _diagnose(text)
        if found:
            return "diagnostica · comando di sistema", *found
    if refused and agent_cmd.enabled():
        async with stages.stage("agent", "Agente con strumenti", "Il modello ha rifiutato: provo con gli strumenti"):
            speech, ui = await agent_cmd.answer(text)
        return "agente · strumenti", speech, ui
    if refused:
        actions.note_gap(text, "il modello ha rifiutato e nessuno strumento è adatto")
    return data.get("agent_id") or "core", *(code.answer(reply, text) or await _presented(reply, text) or compose_generic(reply, text))


async def _presented(reply: str, text: str):
    from features.presentation.composition import compose
    async with stages.attempt("tool", "Impaginazione della risposta") as probe:
        laid_out = await compose(text, reply)
        if not laid_out:
            probe.skip()
    return laid_out
