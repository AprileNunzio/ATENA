import logging
from typing import Callable, Optional, Sequence

from server.core.kernel.consensus.ballot import Voter
from server.core.kernel.consensus.critical import CriticalAction, IntentConsistencyVoter
from server.core.kernel.consensus.ledger import VerdictLedger
from server.core.kernel.consensus.panel import ConsensusPanel
from server.core.kernel.consensus.policy_voter import PolicyGuardVoter
from server.core.kernel.domain.outcome import ConsensusVerdict

logger = logging.getLogger("atena.kernel.consensus.jury")


class CriticalActionJury:
    def __init__(
        self,
        llm_voters: Callable[[], Sequence[Voter]],
        ledger: Optional[VerdictLedger] = None,
        min_distinct_models: int = 2,
        vote_timeout_seconds: float = 45.0,
    ) -> None:
        self._llm_voters = llm_voters
        self._ledger = ledger
        self._min_models = min_distinct_models
        self._timeout = vote_timeout_seconds

    async def judge(self, action: CriticalAction) -> ConsensusVerdict:
        voters = [PolicyGuardVoter(), IntentConsistencyVoter(action), *self._llm_voters()]
        panel = ConsensusPanel(voters, vote_timeout_seconds=self._timeout, min_distinct_models=self._min_models)
        verdict = await panel.vote(action.to_dag())
        if self._ledger is not None:
            try:
                self._ledger.append({
                    "action": action.target,
                    "origin": action.origin,
                    "utterance": action.utterance[:300],
                    "approved": verdict.approved,
                    "objections": list(verdict.objections),
                })
            except OSError as exc:
                logger.error("cannot record critical verdict, denying: %s", exc)
                return ConsensusVerdict(False, verdict.objections + (f"ledger: audit unavailable ({exc.__class__.__name__})",))
        logger.warning("critical action %s from %s: %s", action.target, action.origin, "APPROVED" if verdict.approved else "DENIED")
        return verdict
