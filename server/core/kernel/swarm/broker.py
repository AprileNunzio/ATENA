from typing import Mapping, Optional

from server.core.agent_registry.interfaces import AgentTaskRequest, BaseAgent
from server.core.agent_registry.pool_manager import AgentPoolManager
from server.core.kernel.domain.node import NodeSpec
from server.core.kernel.domain.outcome import ErrorPayload, NodeResult
from server.core.kernel.swarm.lanes import LaneGovernor, LaneSpec, lane_for
from server.core.orchestrator.brain_routing import preferred_brain_for


class SwarmBroker:
    def __init__(self, pool: AgentPoolManager, governor: LaneGovernor, user_id: str, device_id: str, goal: str) -> None:
        self._pool = pool
        self._governor = governor
        self._user_id = user_id
        self._device_id = device_id
        self._goal = goal

    async def execute(
        self,
        node: NodeSpec,
        upstream: Mapping[str, NodeResult],
        feedback: Optional[ErrorPayload],
    ) -> NodeResult:
        lane = lane_for(node.kind)
        spec = self._governor.spec(lane)
        request = self._request(node, upstream, feedback)
        from server.core.kernel.telemetry import NeuralTelemetry
        
        async with self._governor.slot(lane):
            agent = await self._select(request, spec)
            request.preferred_brain = preferred_brain_for(agent.agent_id)
            
            if agent.agent_id == "agent_self_healing_coder":
                architect_agent = await self._select_role(spec, "architect")
                reviewer_agent = await self._select_role(spec, "reviewer")
                executor_agent = await self._select_role(spec, "executor")
                
                from server.core.kernel.validators.code_validator import CodeValidator
                validator = CodeValidator()

                await NeuralTelemetry.emit("swarm_handoff", "system", {"to": "architect", "reason": "Planning Phase"})
                plan_req = self._build_req(node, upstream, feedback, "architect", "")
                plan_req.preferred_brain = request.preferred_brain
                plan_res = await architect_agent.execute(plan_req)

                max_retries = 3
                for attempt in range(max_retries):
                    await NeuralTelemetry.emit("swarm_handoff", "system", {"to": "self_healing_coder", "reason": "Code Generation"})
                    code_req = self._build_req(node, upstream, feedback, "coder", plan_res.result_data.get("code", ""))
                    code_req.preferred_brain = request.preferred_brain
                    code_res = await agent.execute(code_req)
                    generated_code = code_res.result_data.get("code", "")
                    
                    await NeuralTelemetry.emit("swarm_handoff", "system", {"to": "reviewer", "reason": "Code Validation"})
                    validation_errors = validator.validate(generated_code)
                    
                    if not validation_errors:
                        break
                    
                    # Se ci sono errori, aggiungili al feedback e riprova
                    feedback_str = " | ".join(validation_errors)
                    feedback = ErrorPayload(kind="validation_error", message=feedback_str)
                    await NeuralTelemetry.emit("swarm_reject", "reviewer", {"reason": feedback_str})
                
                await NeuralTelemetry.emit("swarm_handoff", "system", {"to": "executor", "reason": "Sandbox Validation"})
                exec_req = self._build_req(node, upstream, feedback, "executor", generated_code)
                exec_req.preferred_brain = request.preferred_brain
                response = await executor_agent.execute(exec_req)
                response.agent_id = "agent_self_healing_coder"
            else:
                response = await agent.execute(request)

        return NodeResult(
            node_id=node.node_id,
            output={**response.result_data, "status": response.status},
            speech=response.speech_output,
            agent_id=response.agent_id,
        )

    async def _select_role(self, spec: LaneSpec, role: str) -> BaseAgent:
        target_id = f"agent_{role}"
        if self._pool.registered([target_id]):
            return self._pool.select_among(None, [target_id])
        return await self._pool.select_best_agent(None)

    def _build_req(self, node: NodeSpec, upstream: Mapping[str, NodeResult], feedback: Optional[ErrorPayload], role: str, context: str) -> AgentTaskRequest:
        req = self._request(node, upstream, feedback)
        req.intent = f"{req.intent}_{role}"
        req.parameters["workflow_context"] = context
        return req

    async def _select(self, request: AgentTaskRequest, spec: LaneSpec) -> BaseAgent:
        if self._pool.registered(spec.agent_ids):
            return self._pool.select_among(request, spec.agent_ids)
        return await self._pool.select_best_agent(request)

    def _request(self, node: NodeSpec, upstream: Mapping[str, NodeResult], feedback: Optional[ErrorPayload]) -> AgentTaskRequest:
        return AgentTaskRequest(
            task_id=f"plan_{node.node_id}",
            user_id=self._user_id,
            intent=node.intent,
            raw_query=self._query(node, feedback),
            parameters={
                "device_id": self._device_id,
                "plan_context": self._goal,
                "node_kind": node.kind.value,
                "previous_results": {n: {**r.output, "speech": r.speech} for n, r in upstream.items()},
                "previous_error": feedback.to_prompt() if feedback else "",
            },
        )

    @staticmethod
    def _query(node: NodeSpec, feedback: Optional[ErrorPayload]) -> str:
        if feedback is None:
            return node.description
        if feedback.kind == "memory_warning":
            return f"{node.description}\n\nEsperienza passata da tenere presente:\n{feedback.message}"
        return f"{node.description}\n\nIl tentativo precedente è fallito: {feedback.to_prompt()}\nCorreggi e riprova."
