"""Configuration dataclasses for the swarm."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path


class AgentStatus(enum.Enum):
    IDLE = "idle"
    PLANNING = "planning"
    WORKING = "working"
    WAITING = "waiting"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """Defines a single specialist agent."""

    name: str
    role: str
    task: str
    depends_on: tuple[str, ...] = ()
    max_turns: int = 50
    allowed_tools: tuple[str, ...] = (
        "Read", "Write", "Edit", "Bash",
    )


@dataclass(slots=True)
class SwarmPlan:
    """The Boss's blueprint for the entire build."""

    project_name: str
    project_dir: Path
    description: str
    agents: list[AgentConfig] = field(default_factory=list)

    def agent_names(self) -> list[str]:
        return [a.name for a in self.agents]

    def get_agent(self, name: str) -> AgentConfig | None:
        return next((a for a in self.agents if a.name == name), None)
