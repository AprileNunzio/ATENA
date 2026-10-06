from typing import Any, Dict

from server.features.skill_synthesis.application.acquisition import Acquisition
from server.features.skill_synthesis.composition import SynthesisModelUnavailable, skill_acquisition, tool_synthesizer

__all__ = ["SkillSynthesizerLobe", "SynthesisModelUnavailable", "skill_synthesizer", "tool_synthesizer"]


class SkillSynthesizerLobe:
    async def acquire(self, request: Dict[str, Any]) -> Acquisition:
        intent = request.get("missing_intent", "unknown")
        context = request.get("context", {})
        goal = str(context.get("query") or intent)
        return await skill_acquisition.acquire(goal, {"intent": intent})

    async def synthesize_new_skill(self, request: Dict[str, Any]) -> str:
        outcome = await self.acquire(request)
        if not outcome.ok:
            return f"Sintesi non riuscita: {outcome.message}"
        return f"Nuovo strumento «{outcome.tool_name}» creato e verificato in sandbox in {outcome.attempts} tentativi."


skill_synthesizer = SkillSynthesizerLobe()
