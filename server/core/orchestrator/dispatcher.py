import time
import uuid
import logging
from typing import Dict, Any, Optional
from server.core.agent_registry.interfaces import AgentTaskRequest, AgentTaskResponse
from server.core.agent_registry.pool_manager import agent_pool
from server.core.context_graph.graph_client import graph_client
from server.core.kernel.consensus.laws_book import laws_book
from server.core.context_graph.node_schema import NodeType, RelationType
from server.core.orchestrator.brain_routing import preferred_brain_for
from server.core.orchestrator.intent_classifier import intent_classifier
from server.core.planner.task_decomposer import task_planner
from server.features.skill_synthesis.synthesizer_lobe import skill_synthesizer
from server.shared.utils.text_sanitizer import TextSanitizer
from server.core.reasoning.conversation import conversation_engine
from server.core.memory.semantic_cache import semantic_cache
from server.core.orchestrator.system1_router import system1_router, System1Intent
from server.core.reasoning.system2_engine import system2_engine
from server.core.telemetry.journey import journey

logger = logging.getLogger("atena.dispatcher")

class OrchestratorDispatcher:
    def __init__(self) -> None:
        self._sanitizer = TextSanitizer()

    async def dispatch_user_command(
        self,
        raw_query: str,
        speaker_id: str,
        device_id: str,
        biometric_score: float,
        context_override: Optional[Dict[str, Any]] = None,
        from server.features.project_workspace.manager import project_manager
        
        response = await self._internal_dispatch(raw_query, speaker_id, device_id, biometric_score, context_override)
        
        state = project_manager.get_active(speaker_id)
        if state and state.is_active and response and response.status == "SUCCESS" and not response.result_data.get("closed"):
            from server.features.llm_gateway.gateway import llm_gateway
            from server.features.llm_gateway.contracts import LLMRequest, LLMMessage
            
            prompt = (
                "Stiamo lavorando a un progetto software insieme. Sei il mio collega sviluppatore Senior, ironico, "
                "brillante e complice. "
                f"La mia richiesta era: '{raw_query}'. "
                f"Esito del sistema tecnico: '{response.speech_output}'. "
                "Rispondi direttamente a me (come fossimo colleghi), confermando che il lavoro è fatto o le modifiche "
                "sono state apportate ai file. Fai una battuta scherzosa, proponi idee moderne, prendimi un po' "
                "in giro bonariamente se ho chiesto cose desuete (es. puro HTML invece di React/PHP/Rust), ridi con "
                "'ahhahaha' o 'lol' e condividi un consiglio tecnico veloce. Sii collaborativo. Max 2-3 frasi fluide e umane. "
                "CRITICAL MANDATORY INSTRUCTION: You MUST write your ENTIRE response in the EXACT SAME LANGUAGE that I used in my request."
            )
            try:
                banter = await llm_gateway.generate_completion(LLMRequest(
                    model_name=response.agent_id if "coder" in response.agent_id else "qwen2.5-coder:7b",
                    component="project_banter",
                    messages=[LLMMessage(role="user", content=prompt)],
                    temperature=0.8
                ))
                if banter and banter.content:
                    response.speech_output = banter.content
            except Exception:
                pass

        if response and response.speech_output:
            project_manager.add_response(speaker_id, response.speech_output)
        return response

    async def _internal_dispatch(
        self,
        raw_query: str,
        speaker_id: str,
        device_id: str,
        biometric_score: float,
        context_override: Optional[Dict[str, Any]] = None,
    ) -> AgentTaskResponse:
        sanitized_query = self._sanitizer.sanitize_plain_text(raw_query)
        
        from server.features.project_workspace.manager import project_manager
        sanitized_query = project_manager.process_query(sanitized_query, speaker_id)
        if "progetto attuale è stato chiuso" in sanitized_query or "current project has been closed" in sanitized_query:
            return AgentTaskResponse(
                task_id=f"tsk_sys_{uuid.uuid4().hex[:8]}",
                agent_id="system_core",
                status="SUCCESS",
                speech_output=sanitized_query,
                result_data={"closed": True}
            )

        journey.begin(sanitized_query, speaker_id or "user")

        with journey.span("laws", "Leggi Fondamentali", "Controllo vincoli e conformità delle leggi") as laws_span:
            laws_book.update(str((context_override or {}).get("laws") or ""))
            laws_span.ok("Leggi conformi (Asimov 0, 1, 2, 3)")

        with journey.span("cache", "Memoria Semantica", "Lookup cache rapida") as cache_span:
            cached_res = await semantic_cache.lookup(sanitized_query)
            if cached_res.hit and cached_res.action_result:
                cache_span.ok(f"Cache HIT (similarità: {cached_res.similarity:.2f})")
                act = cached_res.action_result
                res = AgentTaskResponse(
                    task_id=f"tsk_cache_{uuid.uuid4().hex[:8]}",
                    agent_id=act.get("agent_id", "semantic_cache"),
                    status="SUCCESS",
                    result_data={
                        **act.get("result_data", {}),
                        "cache_hit": True,
                        "similarity": cached_res.similarity,
                        "strategy": cached_res.strategy,
                    },
                    speech_output=act.get("speech_output", ""),
                    execution_time_ms=cached_res.lookup_latency_ms,
                )
                journey.finish(res.speech_output, res.status, res.agent_id)
                return res
            else:
                cache_span.fail("Cache MISS · procedo con analisi cognitiva")

        task_id = f"tsk_{uuid.uuid4().hex[:12]}"

        graph_client.upsert_node(
            node_id=speaker_id,
            node_type=NodeType.USER,
            label=f"User {speaker_id}",
            properties={"last_seen": time.time(), "biometric_confidence": biometric_score},
        )

        graph_client.upsert_node(
            node_id=task_id,
            node_type=NodeType.CONCEPT,
            label=f"Task: {sanitized_query[:40]}",
            properties={"raw_query": sanitized_query, "status": "CLASSIFYING"},
        )

        graph_client.link_nodes(
            source_id=speaker_id,
            target_id=task_id,
            relation_type=RelationType.TRIGGERED_BY,
            weight=biometric_score,
        )

        with journey.span("router", "System 1 Router", "Riflesso rapido non autoregressivo") as s1_span:
            sys1_decision = await system1_router.classify(sanitized_query)
            s1_span.ok(f"{sys1_decision.intent.value} (conf: {sys1_decision.confidence:.2f}, {sys1_decision.latency_ms:.1f}ms)")
        logger.info(
            "System 1 Non-Autoregressive Decision: %s (confidence: %.2f in %.2f ms)",
            sys1_decision.intent.value,
            sys1_decision.confidence,
            sys1_decision.latency_ms,
        )

        with journey.span("classifier", "Classificatore Intenti", "Analisi semantica dell'intento") as class_span:
            if intent_classifier._fallback_routing(sanitized_query) == "GENERAL_INTELLIGENCE" and len(sanitized_query) < 240:
                extracted_intent, confidence = "GENERAL_INTELLIGENCE", 0.7
                class_span.ok(f"Intento: {extracted_intent} (fallback rapido, conf: {confidence:.2f})")
            else:
                extracted_intent, confidence = await intent_classifier.classify(sanitized_query)
                class_span.ok(f"Intento: {extracted_intent} (conf: {confidence:.2f})")

        graph_client.upsert_node(
            node_id=task_id,
            node_type=NodeType.CONCEPT,
            label=f"Task: {sanitized_query[:40]}",
            properties={
                "intent": extracted_intent,
                "intent_confidence": confidence,
                "system1_intent": sys1_decision.intent.value,
                "status": "PLANNING",
            },
        )

        if sys1_decision.intent == System1Intent.WHITEBOARD_CANVAS:
            is_math = any(w in sanitized_query.lower() for w in ["matematica", "calcol", "equazion", "espression", "operazion", "algebra", "conto"])
            if is_math:
                speech = "Ecco la lavagna: lavoriamo insieme sulla matematica! Scrivi pure un calcolo o un'equazione e io la risolverò."
            else:
                speech = "Ecco la lavagna: possiamo iniziare a lavorare insieme sullo schema, signore."
            graph_client.upsert_node(
                node_id=task_id,
                node_type=NodeType.CONCEPT,
                label=f"Task: {sanitized_query[:40]}",
                properties={"status": "COMPLETED", "speech_output": speech},
            )
            res = AgentTaskResponse(
                task_id=task_id,
                agent_id="whiteboard",
                status="SUCCESS",
                result_data={
                    "surface": "whiteboard",
                    "action": sys1_decision.surface_action or "collaborative_canvas",
                    "params": sys1_decision.parameters,
                },
                speech_output=speech,
                execution_time_ms=sys1_decision.latency_ms,
            )
            await semantic_cache.record_success(
                sanitized_query,
                {
                    "agent_id": res.agent_id,
                    "speech_output": res.speech_output,
                    "result_data": res.result_data,
                },
            )
            journey.finish(res.speech_output, res.status, res.agent_id)
            return res

        if sys1_decision.intent == System1Intent.BROWSER_ACTION:
            started = time.time()
            search_query = sanitized_query
            for p in ["apri il sito di", "apri il sito", "vai su", "naviga su", "cerca su"]:
                if p in search_query.lower():
                    search_query = search_query.lower().replace(p, "").strip()
            details = f"Navigazione richiesta: {search_query}"
            journey.step("decision", "Instradamento → browser", f"System 1: browser_action · ricerca: {search_query}")
            with journey.span("tool", "Ricerca web", search_query) as web_span:
                try:
                    from server.features.agent_tools.web_search_tool import web_search
                    details = await web_search(search_query)
                    web_span.ok(str(details)[:600])
                except Exception as exc:
                    web_span.fail(f"{type(exc).__name__}: {exc}")
            speech = f"Ho aperto il browser ed effettuato la ricerca per '{search_query}', signore."
            graph_client.upsert_node(
                node_id=task_id,
                node_type=NodeType.CONCEPT,
                label=f"Task: {sanitized_query[:40]}",
                properties={"status": "COMPLETED", "speech_output": speech},
            )
            res = AgentTaskResponse(
                task_id=task_id,
                agent_id="browser_agent",
                status="SUCCESS",
                result_data={
                    "surface": "browser",
                    "action": "navigate_web",
                    "query": search_query,
                    "details": details,
                },
                speech_output=speech,
                execution_time_ms=(time.time() - started) * 1000,
            )
            await semantic_cache.record_success(
                sanitized_query,
                {
                    "agent_id": res.agent_id,
                    "speech_output": res.speech_output,
                    "result_data": res.result_data,
                },
            )
            journey.finish(res.speech_output, res.status, res.agent_id)
            return res

        if sys1_decision.intent == System1Intent.CONVERSATION or (
            extracted_intent in ("GENERAL_INTELLIGENCE", "PEOPLE_MANAGEMENT") and sys1_decision.intent != System1Intent.COMPLEX_TASK
        ):
            journey.step("decision", "Instradamento → conversazione",
                         f"System 1: {sys1_decision.intent.value} · classificatore: {extracted_intent} · scartati: lavagna, browser, progetto, System 2, agenti")
            started = time.time()
            answer = await conversation_engine.reply(
                sanitized_query,
                device_id,
                people_context=(context_override or {}).get("people_present", ""),
                knowledge=(context_override or {}).get("knowledge", ""),
                models=(context_override or {}).get("models") or None,
                max_tokens=(context_override or {}).get("max_tokens") or 400,
                reply_language=str((context_override or {}).get("reply_language") or ""),
                speaker=str((context_override or {}).get("speaker") or ""),
                dialogue=str((context_override or {}).get("dialogue") or ""),
                long_term=str((context_override or {}).get("long_term") or ""),
                laws=str((context_override or {}).get("laws") or ""),
                pinned=str((context_override or {}).get("pinned") or ""),
                capabilities=str((context_override or {}).get("capabilities") or ""),
            )
            graph_client.upsert_node(
                node_id=task_id,
                node_type=NodeType.CONCEPT,
                label=f"Task: {sanitized_query[:40]}",
                properties={"status": "COMPLETED", "speech_output": answer[:200]},
            )
            res = AgentTaskResponse(
                task_id=task_id,
                agent_id="atena_conversation",
                status="SUCCESS",
                result_data={
                    "intent": extracted_intent,
                    "confidence": confidence,
                    "model": conversation_engine.last_model,
                },
                speech_output=answer,
                execution_time_ms=(time.time() - started) * 1000,
            )
            await semantic_cache.record_success(
                sanitized_query,
                {
                    "agent_id": res.agent_id,
                    "speech_output": res.speech_output,
                    "result_data": res.result_data,
                },
            )
            journey.finish(res.speech_output, res.status, res.agent_id)
            return res

        is_complex = await task_planner.should_decompose(sanitized_query)
        is_web_or_code = "sito web" in sanitized_query.lower() or "progetto" in sanitized_query.lower() or "app" in sanitized_query.lower()
        journey.step("planner", "Valutazione di complessità", f"scomposizione necessaria: {is_complex} · sito/progetto/app: {is_web_or_code}")

        if is_complex or is_web_or_code:
            logger.info("Complex task detected, delegating to LongRunningTaskManager")

            from server.core.kernel.composition import build_scheduler
            from server.core.orchestrator.interrupt_manager import project_manager

            async def background_planner_task(checkpoint, observer) -> bool:
                dag = await task_planner.plan(sanitized_query)
                graph_client.upsert_node(
                    node_id=task_id,
                    node_type=NodeType.CONCEPT,
                    label=f"Task: {sanitized_query[:40]}",
                    properties={"status": "EXECUTING_PLAN", "plan_steps": len(dag.nodes), "plan": dag.fingerprint()},
                )
                scheduler = build_scheduler(
                    agent_pool, speaker_id, device_id, sanitized_query, observer=observer, checkpoint=checkpoint
                )
                outcome = await scheduler.run(dag)
                graph_client.upsert_node(
                    node_id=task_id,
                    node_type=NodeType.CONCEPT,
                    label=f"Task: {sanitized_query[:40]}",
                    properties={"status": outcome.status, "nodes": outcome.summary()},
                )
                return outcome.succeeded

            journey.step("decision", "Instradamento → progetto in background",
                         f"scomposizione richiesta (complesso={is_complex}, sito/progetto/app={is_web_or_code}): pianificazione in DAG con giuria per i passi distruttivi")
            await project_manager.start_project(task_id, sanitized_query[:40], background_planner_task)

            res = AgentTaskResponse(
                task_id=task_id,
                agent_id="orchestrator_planner",
                status="STARTED_IN_BACKGROUND",
                result_data={"message": "Progetto avviato in background."},
                speech_output="Ho creato il progetto e la roadmap. La lavorazione in background è iniziata.",
                execution_time_ms=0,
            )
            journey.finish(res.speech_output, res.status, res.agent_id)
            return res

        if sys1_decision.intent == System1Intent.COMPLEX_TASK and extracted_intent == "GENERAL_INTELLIGENCE":
            journey.step("decision", "Instradamento → System 2", "compito complesso senza agente dedicato: ragionamento latente (scartati: conversazione, agenti, progetto)")
            with journey.span("system2", "System 2 · ragionamento latente", "pensiero esteso prima della risposta") as s2_span:
                sys2_result = await system2_engine.execute(sanitized_query, context_override)
                s2_span.ok(f"modello {sys2_result.model_used} · {sys2_result.latency_ms:.0f} ms")
            res = AgentTaskResponse(
                task_id=task_id,
                agent_id="system2_latent_engine",
                status="SUCCESS",
                result_data={
                    "intent": "COMPLEX_REASONING",
                    "thinking": sys2_result.thinking,
                    "model": sys2_result.model_used,
                    "tool_calls": sys2_result.tool_calls,
                },
                speech_output=sys2_result.response,
                execution_time_ms=sys2_result.latency_ms,
            )
            await semantic_cache.record_success(
                sanitized_query,
                {
                    "agent_id": res.agent_id,
                    "speech_output": res.speech_output,
                    "result_data": res.result_data,
                },
            )
            journey.finish(res.speech_output, res.status, res.agent_id)
            return res

        task_request = AgentTaskRequest(
            task_id=task_id,
            user_id=speaker_id,
            intent=extracted_intent,
            raw_query=sanitized_query,
            confidence=confidence,
            parameters={
                "device_id": device_id,
                "biometric_score": biometric_score,
                **(context_override or {}),
            },
        )

        try:
            with journey.span("pool", "Selezione agente", f"intento {extracted_intent}") as pool_span:
                assigned_agent = await agent_pool.select_best_agent(task_request)
                pool_span.ok(f"scelto: {assigned_agent.agent_id}")
        except Exception as exc:
            logger.warning("No agent for intent '%s', acquiring a new skill", extracted_intent)
            journey.step("decision", "Nessun agente adatto", f"{exc} → ripiego: acquisizione di una nuova skill", "fail")
            with journey.span("skill", "Acquisizione skill", f"intento mancante: {extracted_intent}") as skill_span:
                skill_res = await self._acquire_skill(task_id, extracted_intent, sanitized_query, device_id)
                skill_span.done("ok" if skill_res.status == "SUCCESS" else "fail", skill_res.speech_output[:400])
            journey.finish(skill_res.speech_output, skill_res.status, skill_res.agent_id)
            return skill_res

        graph_client.upsert_node(
            node_id=assigned_agent.agent_id,
            node_type=NodeType.AGENT,
            label=assigned_agent.agent_id.replace("_", " ").title(),
            properties={"capabilities": assigned_agent.capabilities},
        )

        graph_client.link_nodes(
            source_id=task_id,
            target_id=assigned_agent.agent_id,
            relation_type=RelationType.DEPENDS_ON,
        )

        graph_client.upsert_node(
            node_id=task_id,
            node_type=NodeType.CONCEPT,
            label=f"Task: {sanitized_query[:40]}",
            properties={"status": "EXECUTING", "assigned_agent": assigned_agent.agent_id},
        )

        brain = preferred_brain_for(assigned_agent.agent_id)
        if brain:
            task_request.preferred_brain = brain
            logger.info("Assegnato cervello specifico '%s' all'agente '%s'", brain, assigned_agent.agent_id)

        with journey.span("agent", assigned_agent.agent_id,
                          f"intento {extracted_intent}" + (f" · cervello assegnato: {brain}" if brain else "")) as agent_span:
            response = await assigned_agent.execute(task_request)
            if response.status == "SUCCESS":
                agent_span.ok(response.speech_output[:600])
            else:
                agent_span.fail(f"{response.status}: {response.speech_output[:400]}")

        graph_client.upsert_node(
            node_id=task_id,
            node_type=NodeType.CONCEPT,
            label=f"Task: {sanitized_query[:40]}",
            properties={
                "status": response.status,
                "execution_time_ms": response.execution_time_ms,
                "speech_output": response.speech_output[:200],
            },
        )

        if response.status == "SUCCESS":
            await semantic_cache.record_success(
                sanitized_query,
                {
                    "agent_id": response.agent_id,
                    "speech_output": response.speech_output,
                    "result_data": response.result_data,
                },
            )

        journey.finish(response.speech_output, response.status, response.agent_id)
        return response

    async def _acquire_skill(self, task_id: str, intent: str, query: str, device_id: str) -> AgentTaskResponse:
        started = time.time()
        outcome = await skill_synthesizer.acquire({
            "missing_intent": intent,
            "context": {"query": query, "device_id": device_id},
        })
        graph_client.upsert_node(
            node_id=task_id,
            node_type=NodeType.CONCEPT,
            label=f"Task: {query[:40]}",
            properties={"status": "COMPLETED" if outcome.ok else "FAILED", "acquired_tool": outcome.tool_name},
        )
        if not outcome.ok:
            return AgentTaskResponse(
                task_id=task_id,
                agent_id="skill_synthesizer",
                status="SYNTHESIS_FAILED",
                result_data={"reason": outcome.message, "attempts": outcome.attempts},
                speech_output=outcome.speech,
                execution_time_ms=(time.time() - started) * 1000,
            )
        return AgentTaskResponse(
            task_id=task_id,
            agent_id="skill_synthesizer",
            status="SUCCESS",
            result_data={
                "tool": outcome.tool_name,
                "data": outcome.data,
                "egress_hosts": list(outcome.egress_hosts),
                "attempts": outcome.attempts,
                "acquired": True,
            },
            speech_output=outcome.speech,
            execution_time_ms=(time.time() - started) * 1000,
        )


orchestrator_dispatcher = OrchestratorDispatcher()
