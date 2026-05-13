"""Swarm orchestrator — spawns agents and manages their lifecycle."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .agent import Agent
from .bus import MessageBus
from .config import AgentConfig, AgentStatus, SwarmPlan

log = logging.getLogger(__name__)


class Swarm:
    """Manages the full lifecycle of a multi-agent build."""

    def __init__(self, plan: SwarmPlan, bus: MessageBus) -> None:
        self.plan = plan
        self.bus = bus
        self.agents: dict[str, Agent] = {}

        Path(plan.project_dir / "_swarm" / "done").mkdir(parents=True, exist_ok=True)

    def build_agents(self) -> None:
        """Instantiate Agent objects from the plan."""
        names = self.plan.agent_names()
        for cfg in self.plan.agents:
            self.bus.register(cfg.name)
            self.agents[cfg.name] = Agent(
                cfg=cfg,
                bus=self.bus,
                project_dir=self.plan.project_dir,
                project_name=self.plan.project_name,
                project_description=self.plan.description,
                all_agent_names=names,
            )

    async def start(self) -> None:
        """Launch all agents respecting dependency order."""
        started: set[str] = set()
        pending = list(self.agents.values())

        while pending:
            ready = [
                a for a in pending
                if all(dep in started for dep in a.cfg.depends_on)
            ]
            if not ready:
                log.warning("Breaking dependency cycle, starting remaining agents")
                ready = pending

            for agent in ready:
                await agent.start()
                started.add(agent.name)

            pending = [a for a in pending if a.name not in started]
            if pending:
                await asyncio.sleep(0.5)

    async def wait(self) -> dict[str, AgentStatus]:
        """Block until all agents finish."""
        await asyncio.gather(
            *(agent.wait() for agent in self.agents.values()),
            return_exceptions=True,
        )
        return self.get_status()

    async def cancel_all(self) -> None:
        for agent in self.agents.values():
            await agent.cancel()

    def get_status(self) -> dict[str, AgentStatus]:
        return {name: agent.status for name, agent in self.agents.items()}

    def add_agent(self, cfg: AgentConfig) -> Agent:
        """Hot-add an agent to a running swarm."""
        self.plan.agents.append(cfg)
        self.bus.register(cfg.name)
        agent = Agent(
            cfg=cfg,
            bus=self.bus,
            project_dir=self.plan.project_dir,
            project_name=self.plan.project_name,
            project_description=self.plan.description,
            all_agent_names=self.plan.agent_names(),
        )
        self.agents[cfg.name] = agent
        return agent
