from typing import Awaitable, Callable

from features.brain.roles import ROLES
from features.brain.scope import DEFAULT_SCOPE, DEFAULT_STRATEGY

MIXED = "mixed"
FLAGS = {
    "understanding.enabled": ("ATENA_UNDERSTANDING", "1"),
    "understanding.arbiter": ("ATENA_UNDERSTANDING_LLM", "1"),
    "skills.enabled": ("ATENA_SKILLS", "1"),
    "skills.generate": ("ATENA_SKILLS_GENERATE", "1"),
    "memory.enabled": ("ATENA_MIND", "1"),
    "agent.enabled": ("ATENA_AGENT", "1"),
    "agent.access": ("ATENA_AGENT_ACCESS", "completo"),
}
ROLE_KEYS = {"brain.strategy": ("strategy_key", DEFAULT_STRATEGY), "brain.scope": ("scope_key", DEFAULT_SCOPE)}


class EnvSettings:
    def __init__(self, read_env: Callable[[], dict], apply_config: Callable[[dict, str], Awaitable[list]]) -> None:
        self.read_env = read_env
        self.apply_config = apply_config

    def read(self) -> dict[str, str]:
        env = self.read_env()
        out = {name: env.get(key) or default for name, (key, default) in FLAGS.items()}
        for name, (attr, default) in ROLE_KEYS.items():
            values = {env.get(getattr(role, attr)) or default for role in ROLES}
            out[name] = values.pop() if len(values) == 1 else MIXED
        return out

    @staticmethod
    def env_updates(updates: dict[str, str]) -> dict[str, str]:
        env = {}
        for name, value in updates.items():
            if name in FLAGS:
                env[FLAGS[name][0]] = value
            elif name in ROLE_KEYS:
                env.update({getattr(role, ROLE_KEYS[name][0]): value for role in ROLES})
            else:
                raise ValueError(f"Impostazione del flusso sconosciuta: {name}")
        return env

    async def apply(self, updates: dict[str, str], user: str) -> list:
        return await self.apply_config(self.env_updates(updates), user)
