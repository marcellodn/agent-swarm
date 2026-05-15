"""Single specialist agent — wraps a Claude Code session."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from claude_code_sdk import ClaudeCodeOptions, query

from .bus import Message, MessageBus, MessageType
from .config import AgentConfig, AgentStatus
from .roles import build_system_prompt

log = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 30


class Agent:
    """Lifecycle wrapper around one Claude Code agent session."""

    def __init__(
        self,
        cfg: AgentConfig,
        bus: MessageBus,
        project_dir: Path,
        project_name: str,
        project_description: str,
        all_agent_names: list[str],
    ) -> None:
        self.cfg = cfg
        self.bus = bus
        self.project_dir = project_dir
        self.status = AgentStatus.IDLE
        self.output_lines: list[str] = []
        self._task: asyncio.Task[None] | None = None

        self._system_prompt = build_system_prompt(
            role_key=cfg.role,
            project_name=project_name,
            project_description=project_description,
            task=cfg.task,
            agent_names=[n for n in all_agent_names if n != cfg.name],
        )

    @property
    def name(self) -> str:
        return self.cfg.name

    @property
    def last_output(self) -> str:
        return self.output_lines[-1] if self.output_lines else ""

    async def start(self) -> None:
        """Launch the agent as a background asyncio task."""
        self.status = AgentStatus.WORKING
        self._task = asyncio.create_task(self._run(), name=f"agent-{self.name}")

    async def wait(self) -> None:
        if self._task:
            await self._task

    async def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            self.status = AgentStatus.FAILED

    async def execute_followup(self, prompt: str) -> None:
        """Run a follow-up query (user talking to the agent directly)."""
        self.status = AgentStatus.WORKING
        await self._execute(prompt)
        self.status = AgentStatus.DONE
        await self.bus.send(Message(
            sender=self.name,
            recipient="*",
            content="Follow-up complete.",
            msg_type=MessageType.DONE,
        ))

    # ── internal ────────────────────────────────────────────

    async def _run(self) -> None:
        """Execute the initial task."""
        swarm_dir = self.project_dir / "_swarm" / "done"
        swarm_dir.mkdir(parents=True, exist_ok=True)

        await self.bus.send(Message(
            sender=self.name,
            recipient="*",
            content=f"Starting: {self.cfg.task[:120]}",
            msg_type=MessageType.STATUS,
        ))

        try:
            await self._execute(self.cfg.task)
            self.status = AgentStatus.DONE
            await self.bus.send(Message(
                sender=self.name,
                recipient="*",
                content="Task complete.",
                msg_type=MessageType.DONE,
            ))

        except asyncio.CancelledError:
            self.status = AgentStatus.FAILED
            raise
        except Exception as exc:
            self.status = AgentStatus.FAILED
            log.exception("Agent %s failed", self.name)
            await self.bus.send(Message(
                sender=self.name,
                recipient="*",
                content=f"FAILED: {exc}",
                msg_type=MessageType.STATUS,
            ))

    async def _execute(self, prompt: str) -> None:
        """Run a Claude Code query with retry on rate limits."""
        options = ClaudeCodeOptions(
            system_prompt=self._system_prompt,
            cwd=str(self.project_dir),
            allowed_tools=list(self.cfg.allowed_tools),
            max_turns=self.cfg.max_turns,
        )

        for attempt in range(MAX_RETRIES):
            try:
                async for msg in query(prompt=prompt, options=options):
                    await self._handle_sdk_message(msg)
                return  # success
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                msg_str = str(exc).lower()
                is_rate_limit = any(
                    kw in msg_str
                    for kw in ("rate_limit", "rate limit", "429", "overloaded")
                )
                if is_rate_limit and attempt < MAX_RETRIES - 1:
                    wait = RETRY_DELAY * (attempt + 1)
                    await self.bus.send(Message(
                        sender=self.name,
                        recipient="*",
                        content=f"Rate limited — retrying in {wait}s...",
                        msg_type=MessageType.STATUS,
                    ))
                    await asyncio.sleep(wait)
                    continue
                raise

    async def _handle_sdk_message(self, msg: object) -> None:
        """Extract text and stream it to the bus."""
        try:
            if hasattr(msg, "content"):
                content = msg.content
                if isinstance(content, str):
                    await self._emit(content)
                elif isinstance(content, list):
                    for block in content:
                        if hasattr(block, "text"):
                            await self._emit(block.text)

            if hasattr(msg, "result") and msg.result:
                await self._emit(str(msg.result))
        except Exception:
            pass

    async def _emit(self, text: str) -> None:
        """Store output and send to bus for real-time UI updates."""
        for line in text.strip().splitlines():
            stripped = line.strip()
            if stripped:
                self.output_lines.append(stripped)
                if len(self.output_lines) > 500:
                    self.output_lines = self.output_lines[-250:]
                await self.bus.send(Message(
                    sender=self.name,
                    recipient="*",
                    content=stripped,
                    msg_type=MessageType.STATUS,
                ))
