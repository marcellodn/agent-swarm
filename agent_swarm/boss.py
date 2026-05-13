"""Boss agent — the user's point of contact.

Responsibilities:
  1. Talk to the user, understand the project
  2. Break it into specialist tasks (the plan)
  3. Launch & monitor the swarm
  4. Report results
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from claude_code_sdk import ClaudeCodeOptions, query

from .config import AgentConfig, SwarmPlan
from .roles import ROLES

log = logging.getLogger(__name__)

PLAN_SYSTEM_PROMPT = """\
You are the Boss of a multi-agent coding swarm. Your job:
1. Understand what the user wants to build.
2. Break it into INDEPENDENT specialist tasks.
3. Return a JSON plan — nothing else.

Available specialist roles: {roles}

Reply with ONLY valid JSON matching this schema:
{{
  "project_name": "string",
  "description": "one-paragraph project summary",
  "agents": [
    {{
      "name": "short-kebab-name",
      "role": "one of the role keys above",
      "task": "detailed paragraph describing exactly what this agent must build",
      "depends_on": ["other-agent-name"]  // optional, usually empty
    }}
  ]
}}

Rules:
- 2-6 agents is ideal. Don't over-split.
- Each task must be concrete and actionable.
- Minimise dependencies — agents should be able to work in parallel.
- Include a cybersecurity agent if the project handles user data.
- Include a testing agent for any non-trivial project.
- Use clear, specific task descriptions — the agent only sees its own task.
"""

SUMMARY_SYSTEM_PROMPT = """\
You are the Boss summarising the results of a multi-agent coding swarm.
Given the status of each agent and the files they created, write a
clear summary for the user: what was built, what succeeded, what failed,
and any next steps. Be concise and direct.
"""


class Boss:
    """Plans work and orchestrates the swarm on behalf of the user."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir

    async def create_plan(self, user_request: str) -> SwarmPlan:
        """Ask Claude to break the user's request into agent tasks."""
        role_list = ", ".join(ROLES.keys())
        system = PLAN_SYSTEM_PROMPT.format(roles=role_list)

        prompt = (
            f"The user wants to build the following:\n\n"
            f"{user_request}\n\n"
            f"The project directory is: {self.project_dir}\n\n"
            f"Create the agent plan."
        )

        raw_text = await self._ask_claude(prompt, system)
        return self._parse_plan(raw_text)

    async def refine_plan(self, plan: SwarmPlan, feedback: str) -> SwarmPlan:
        """Let the user tweak the plan before execution."""
        role_list = ", ".join(ROLES.keys())
        system = PLAN_SYSTEM_PROMPT.format(roles=role_list)

        current = json.dumps({
            "project_name": plan.project_name,
            "description": plan.description,
            "agents": [
                {"name": a.name, "role": a.role, "task": a.task,
                 "depends_on": list(a.depends_on)}
                for a in plan.agents
            ],
        }, indent=2)

        prompt = (
            f"Current plan:\n{current}\n\n"
            f"User feedback:\n{feedback}\n\n"
            f"Return the updated JSON plan."
        )

        raw_text = await self._ask_claude(prompt, system)
        return self._parse_plan(raw_text)

    async def summarise(self, statuses: dict[str, str]) -> str:
        """Generate a human-readable summary after the swarm finishes."""
        # Collect done-files written by agents
        done_dir = self.project_dir / "_swarm" / "done"
        summaries: dict[str, str] = {}
        if done_dir.exists():
            for f in done_dir.glob("*.md"):
                summaries[f.stem] = f.read_text(errors="replace")[:500]

        prompt = (
            f"Agent statuses: {json.dumps(statuses)}\n\n"
            f"Agent summaries:\n{json.dumps(summaries, indent=2)}\n\n"
            f"Write a clear summary for the user."
        )

        return await self._ask_claude(prompt, SUMMARY_SYSTEM_PROMPT)

    # ── helpers ─────────────────────────────────────────────────

    async def _ask_claude(self, prompt: str, system: str) -> str:
        """Run a one-shot Claude Code query and return the text."""
        options = ClaudeCodeOptions(
            system_prompt=system,
            cwd=str(self.project_dir),
            max_turns=3,
        )

        chunks: list[str] = []
        async for msg in query(prompt=prompt, options=options):
            text = self._extract_text(msg)
            if text:
                chunks.append(text)

        return "\n".join(chunks)

    @staticmethod
    def _extract_text(msg: object) -> str:
        """Pull plain text out of an SDK message.

        Handles AssistantMessage (.content → list[TextBlock]),
        ResultMessage (.result), and raw strings.
        """
        parts: list[str] = []

        if hasattr(msg, "content"):
            content = msg.content
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if hasattr(block, "text"):
                        parts.append(block.text)

        if hasattr(msg, "result") and msg.result:
            parts.append(str(msg.result))

        return "\n".join(parts)

    def _parse_plan(self, raw: str) -> SwarmPlan:
        """Extract JSON from Claude's response and build a SwarmPlan."""
        # Claude sometimes wraps JSON in markdown code fences
        text = raw.strip()
        if "```" in text:
            blocks = text.split("```")
            for block in blocks:
                block = block.strip()
                if block.startswith("json"):
                    block = block[4:].strip()
                if block.startswith("{"):
                    text = block
                    break

        data = json.loads(text)

        agents = []
        for a in data["agents"]:
            agents.append(AgentConfig(
                name=a["name"],
                role=a["role"],
                task=a["task"],
                depends_on=tuple(a.get("depends_on", [])),
            ))

        return SwarmPlan(
            project_name=data.get("project_name", "project"),
            project_dir=self.project_dir,
            description=data.get("description", ""),
            agents=agents,
        )
