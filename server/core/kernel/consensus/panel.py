import asyncio
import logging
import math
from typing import Sequence, Tuple

from server.core.kernel.consensus.ballot import Ballot, Voter
from server.core.kernel.domain.dag import ExecutionDag
from server.core.kernel.domain.outcome import ConsensusVerdict
from server.core.telemetry.journey import journey

logger = logging.getLogger("atena.kernel.consensus")


def byzantine_bounds(voters: int) -> Tuple[int, int]:
    faulty = (voters - 1) // 3
    return faulty, math.ceil((voters + faulty + 1) / 2)


class ConsensusPanel:
    def __init__(self, voters: Sequence[Voter], vote_timeout_seconds: float = 180.0, min_distinct_models: int = 1) -> None:
        if not voters:
            raise ValueError("a consensus panel needs at least one voter")
        self._voters = tuple(voters)
        self._timeout = vote_timeout_seconds
        self._min_models = max(1, min_distinct_models)
        self._faulty, self._quorum = byzantine_bounds(len(self._voters))

    @property
    def quorum(self) -> int:
        return self._quorum

    async def vote(self, dag: ExecutionDag) -> ConsensusVerdict:
        with journey.span("jury", "Giuria di Consenso", f"{len(self._voters)} votanti · quorum: {self._quorum}") as jury_span:
            ballots = await asyncio.gather(*(self._ballot(v, dag) for v in self._voters))
            approving = [b for b in ballots if b.approve]
            vetoes = [b for v, b in zip(self._voters, ballots) if v.can_veto and not b.approve]
            models = {b.model for b in approving if b.model}
            diverse = self._min_models <= 1 or len(models) >= self._min_models
            objections = tuple(f"{b.voter}: {b.reason}" for b in ballots if not b.approve)
            if not diverse:
                objections += (f"diversity: {len(models)} distinct models approved, {self._min_models} required",)
            approved = len(approving) >= self._quorum and not vetoes and diverse
            logger.info(
                "consensus on %s: %d/%d approve (quorum %d, f=%d), vetoes=%d, models=%d",
                dag.fingerprint()[:12], len(approving), len(ballots), self._quorum, self._faulty, len(vetoes), len(models),
            )
            detail = f"{'APPROVATO' if approved else 'RESPINTO'}: {len(approving)}/{len(ballots)} favorevoli, {len(vetoes)} veto"
            if objections:
                detail += f" | obiezioni: {'; '.join(objections[:2])}"
            jury_span.done("ok" if approved else "fail", detail)
            return ConsensusVerdict(approved=approved, objections=objections)

    async def _ballot(self, voter: Voter, dag: ExecutionDag) -> Ballot:
        with journey.span("voter", f"Votante: {voter.name}", f"Veto abilitato: {voter.can_veto}", parallel=True) as v_span:
            try:
                b = await asyncio.wait_for(voter.vote(dag), self._timeout)
                v_span.done("ok" if b.approve else "fail", f"{'FAVOREVOLE' if b.approve else 'CONTRARIO'}: {b.reason or ''}")
                return b
            except asyncio.TimeoutError:
                v_span.fail("timeout superato")
                return Ballot(voter.name, False, "no answer within the voting deadline")
            except Exception as exc:
                logger.warning("voter %s failed: %s", voter.name, exc.__class__.__name__)
                v_span.fail(f"errore {exc.__class__.__name__}")
                return Ballot(voter.name, False, f"voter unavailable ({exc.__class__.__name__})")
