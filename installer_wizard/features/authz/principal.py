from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import IntEnum


class Strength(IntEnum):
    NONE = 0
    WEAK = 1
    SINGLE = 2
    STRONG = 3


@dataclass(frozen=True)
class Principal:
    slug: str = ""
    role: str = "anonymous"
    strength: Strength = Strength.NONE
    factors: tuple[str, ...] = field(default_factory=tuple)
    override: str = ""

    @property
    def known(self) -> bool:
        return bool(self.slug)

    def describe(self) -> dict:
        return {"slug": self.slug, "role": self.role, "strength": self.strength.name.lower(),
                "factors": list(self.factors), "override": self.override}


ANONYMOUS = Principal()
SYSTEM = Principal(slug="atena", role="system", strength=Strength.STRONG, factors=("system",))

current: ContextVar[Principal] = ContextVar("atena_principal", default=ANONYMOUS)


def acting() -> Principal:
    return current.get()


def act_as(principal: Principal):
    return current.set(principal)
