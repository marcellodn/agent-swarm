"""Textual TUI — the main interactive chat interface.

Layout:
  ┌──────────┬───────────────────────────────────┐
  │ AGENTS   │  Agent Name (role)                │
  │          │  ────────────────                  │
  │ ● Boss   │                                    │
  │ ● backend│  Boss: Welcome! Tell me what ...   │
  │ ● security│                                   │
  │          │  You: Build a secure REST API ...  │
  │          │                                    │
  │          │  Boss: I'll create these agents... │
  ├──────────┴───────────────────────────────────┤
  │ > Type a message...                           │
  └───────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message as TMessage
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Footer, Header, Input, RichLog, Static

from .boss import Boss
from .bus import MessageBus, MessageType
from .config import AgentStatus, SwarmPlan
from .swarm import Swarm


# ── Custom messages ──────────────────────────────────────────

class AgentSelected(TMessage):
    """User clicked an agent in the sidebar."""

    def __init__(self, agent_name: str) -> None:
        super().__init__()
        self.agent_name = agent_name


class BusMessage(TMessage):
    """Forwarded from the MessageBus for safe UI update."""

    def __init__(self, sender: str, content: str, msg_type: MessageType) -> None:
        super().__init__()
        self.sender = sender
        self.content = content
        self.msg_type = msg_type


# ── Sidebar agent button ────────────────────────────────────

STATUS_ICON = {
    "idle": "○",
    "planning": "◌",
    "working": "●",
    "waiting": "◑",
    "done": "✓",
    "failed": "✗",
}
STATUS_STYLE = {
    "idle": "dim",
    "planning": "yellow",
    "working": "bold cyan",
    "waiting": "yellow",
    "done": "bold green",
    "failed": "bold red",
}


class AgentButton(Static):
    """Clickable agent entry in the sidebar."""

    is_selected = reactive(False)
    status = reactive("idle")

    def __init__(self, agent_name: str, role: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.agent_name = agent_name
        self.role = role

    def render(self) -> Text:
        icon = STATUS_ICON.get(self.status, "○")
        style = STATUS_STYLE.get(self.status, "dim")
        marker = " ◂" if self.is_selected else ""
        t = Text()
        t.append(f" {icon} ", style=style)
        t.append(self.agent_name, style="bold" if self.is_selected else "")
        t.append(marker, style="#a855f7")
        t.append(f"\n   {self.role}", style="dim")
        return t

    def on_click(self) -> None:
        self.post_message(AgentSelected(self.agent_name))


# ── Main application ────────────────────────────────────────

class SwarmApp(App[None]):
    """Multi-agent swarm with chat-style interface."""

    TITLE = "Agent Swarm"

    CSS = """
    Screen {
        background: #0d1117;
        color: #c9d1d9;
    }

    #sidebar {
        width: 24;
        background: #161b22;
        border-right: solid #30363d;
        padding: 1 0;
    }

    #sidebar-title {
        text-align: center;
        text-style: bold;
        color: #a855f7;
        padding: 0 1;
        margin-bottom: 1;
    }

    AgentButton {
        width: 100%;
        height: 3;
        padding: 0 0;
        margin: 0 0;
    }

    AgentButton:hover {
        background: #21262d;
    }

    #chat-area {
        background: #0d1117;
    }

    #chat-header {
        height: 3;
        background: #161b22;
        border-bottom: solid #30363d;
        padding: 1 2;
        text-style: bold;
        color: #a855f7;
    }

    .chat-log {
        background: #0d1117;
        padding: 1 2;
        scrollbar-background: #161b22;
        scrollbar-color: #484f58;
        scrollbar-color-hover: #a855f7;
    }

    .chat-log-hidden {
        display: none;
    }

    #chat-input {
        dock: bottom;
        margin: 1 2;
        background: #161b22;
        border: round #30363d;
        color: #c9d1d9;
        padding: 0 1;
    }

    #chat-input:focus {
        border: round #a855f7;
    }

    Header {
        background: #a855f7;
        color: #ffffff;
    }

    Footer {
        background: #161b22;
        color: #484f58;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+n", "next_agent", "Next"),
        Binding("ctrl+p", "prev_agent", "Prev"),
    ]

    selected_agent: reactive[str] = reactive("boss")

    def __init__(self, project_dir: Path, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.project_dir = project_dir
        self.boss = Boss(project_dir)
        self.swarm: Swarm | None = None
        self.bus = MessageBus()
        self._current_plan: SwarmPlan | None = None
        self._phase = "planning"  # planning | confirming | building | done
        self._agent_buttons: dict[str, AgentButton] = {}
        self._chat_logs: dict[str, RichLog] = {}
        self._agent_order: list[str] = ["boss"]

    # ── compose ──────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Static("AGENTS", id="sidebar-title")
                btn = AgentButton("boss", "Boss")
                btn.is_selected = True
                self._agent_buttons["boss"] = btn
                yield btn
            with Vertical(id="chat-area"):
                yield Static("Boss", id="chat-header")
                log = RichLog(
                    id="chat-boss",
                    markup=True,
                    wrap=True,
                    classes="chat-log",
                )
                self._chat_logs["boss"] = log
                yield log
                yield Input(
                    placeholder="Describe what you want to build...",
                    id="chat-input",
                )
        yield Footer()

    def on_mount(self) -> None:
        log = self._chat_logs["boss"]
        log.write(Text("Boss", style="bold #a855f7"))
        log.write("")
        log.write("Welcome! Tell me what you want to build and")
        log.write("I'll assemble a team of specialist agents.")
        log.write("")
        self.query_one("#chat-input", Input).focus()

    # ── agent selection ──────────────────────────────────────

    def watch_selected_agent(self, old: str, new: str) -> None:
        # Toggle sidebar highlight
        if old in self._agent_buttons:
            self._agent_buttons[old].is_selected = False
        if new in self._agent_buttons:
            self._agent_buttons[new].is_selected = True

        # Toggle chat log visibility
        for name, log in self._chat_logs.items():
            if name == new:
                log.remove_class("chat-log-hidden")
                log.add_class("chat-log")
            else:
                log.remove_class("chat-log")
                log.add_class("chat-log-hidden")

        # Update header
        role = ""
        if new in self._agent_buttons:
            role = self._agent_buttons[new].role
        header_text = f"{new}" + (f"  ({role})" if role and role != "Boss" else "")
        self.query_one("#chat-header", Static).update(header_text)

    def on_agent_selected(self, event: AgentSelected) -> None:
        self.selected_agent = event.agent_name

    def action_next_agent(self) -> None:
        idx = self._agent_order.index(self.selected_agent)
        self.selected_agent = self._agent_order[(idx + 1) % len(self._agent_order)]

    def action_prev_agent(self) -> None:
        idx = self._agent_order.index(self.selected_agent)
        self.selected_agent = self._agent_order[(idx - 1) % len(self._agent_order)]

    # ── input handling ───────────────────────────────────────

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.clear()

        agent = self.selected_agent
        log = self._chat_logs.get(agent)
        if log:
            log.write(Text.assemble(
                ("\n You ", "bold #58a6ff on #161b22"),
                ("  ", ""),
                (text, ""),
            ))
            log.write("")

        if agent == "boss":
            self._handle_boss_input(text)
        else:
            self._handle_agent_input(agent, text)

    # ── boss interaction ─────────────────────────────────────

    @work(exclusive=True, group="boss")
    async def _handle_boss_input(self, text: str) -> None:
        log = self._chat_logs["boss"]

        if self._phase == "planning":
            log.write(Text("Planning...", style="yellow"))
            log.write("")
            try:
                plan = await self.boss.create_plan(text)
                self._current_plan = plan
                self._show_plan(plan, log)
                self._phase = "confirming"
            except Exception as exc:
                log.write(Text(f"Error: {exc}", style="bold red"))

        elif self._phase == "confirming":
            if text.lower() in ("y", "yes"):
                await self._launch_swarm()
            elif text.lower() in ("q", "quit"):
                self.exit()
            else:
                log.write(Text("Refining plan...", style="yellow"))
                log.write("")
                try:
                    plan = await self.boss.refine_plan(self._current_plan, text)  # type: ignore[arg-type]
                    self._current_plan = plan
                    self._show_plan(plan, log)
                except Exception as exc:
                    log.write(Text(f"Error: {exc}", style="bold red"))

        elif self._phase in ("building", "done"):
            log.write(Text(
                "Agents are working. Select one in the sidebar (Ctrl+N/P) "
                "to watch or interact.",
                style="dim",
            ))

    def _show_plan(self, plan: SwarmPlan, log: RichLog) -> None:
        log.write(Text(f"Project: {plan.project_name}", style="bold #a855f7"))
        log.write(Text(plan.description, style=""))
        log.write("")
        for i, a in enumerate(plan.agents, 1):
            deps = f" → waits for {', '.join(a.depends_on)}" if a.depends_on else ""
            log.write(Text.assemble(
                (f"  {i}. ", "bold cyan"),
                (a.name, "bold"),
                (f"  ({a.role}){deps}", "dim"),
            ))
            log.write(Text(f"     {a.task[:120]}", style=""))
        log.write("")
        log.write(Text(
            "Approve? [y]es / type feedback to refine / [q]uit",
            style="yellow",
        ))

    async def _launch_swarm(self) -> None:
        plan = self._current_plan
        if plan is None:
            return

        log = self._chat_logs["boss"]
        log.write("")
        log.write(Text("Launching the swarm!", style="bold green"))
        log.write("")

        # Create chat panes and sidebar buttons for each agent
        sidebar = self.query_one("#sidebar", Vertical)
        chat_area = self.query_one("#chat-area", Vertical)
        input_widget = self.query_one("#chat-input", Input)

        for cfg in plan.agents:
            # Sidebar button
            btn = AgentButton(cfg.name, cfg.role)
            btn.status = "working"
            self._agent_buttons[cfg.name] = btn
            await sidebar.mount(btn)
            self._agent_order.append(cfg.name)

            # Chat log (hidden by default — only selected agent is visible)
            agent_log = RichLog(
                id=f"chat-{cfg.name}",
                markup=True,
                wrap=True,
                classes="chat-log-hidden",
            )
            self._chat_logs[cfg.name] = agent_log
            await chat_area.mount(agent_log, before=input_widget)

            agent_log.write(Text(f"{cfg.name}  ({cfg.role})", style="bold #a855f7"))
            agent_log.write("")
            agent_log.write(Text(f"Task: {cfg.task[:200]}", style="dim"))
            agent_log.write("")

        # Build and start the swarm
        self.swarm = Swarm(plan, self.bus)
        self.swarm.build_agents()
        self._phase = "building"

        input_widget.placeholder = "Talk to any agent — switch with Ctrl+N / Ctrl+P"

        log.write(Text(
            f"{len(plan.agents)} agents working. Switch tabs to watch them.",
            style="dim",
        ))

        # Start monitoring the bus
        self._monitor_bus()

        # Start agents
        await self.swarm.start()

        # Wait for completion in background
        self._wait_for_completion()

    @work(exclusive=True, group="monitor")
    async def _monitor_bus(self) -> None:
        """Read from the MessageBus and post to UI safely."""
        q = self.bus.subscribe()
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=1.0)
                    self.post_message(BusMessage(msg.sender, msg.content, msg.msg_type))
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            self.bus.unsubscribe(q)

    def on_bus_message(self, event: BusMessage) -> None:
        """Handle bus messages on the Textual thread."""
        log = self._chat_logs.get(event.sender)
        if not log:
            return

        if event.msg_type == MessageType.DONE:
            log.write("")
            log.write(Text("✓ Task complete.", style="bold green"))
            btn = self._agent_buttons.get(event.sender)
            if btn:
                btn.status = "done"
        elif event.msg_type == MessageType.STATUS:
            if "FAILED" in event.content:
                log.write(Text(event.content, style="red"))
                btn = self._agent_buttons.get(event.sender)
                if btn:
                    btn.status = "failed"
            else:
                log.write(Text(event.content, style="dim"))

    @work(exclusive=True, group="wait")
    async def _wait_for_completion(self) -> None:
        """Wait for all agents to finish, then show summary."""
        if not self.swarm:
            return

        statuses = await self.swarm.wait()
        self._phase = "done"

        # Update sidebar
        for name, status in statuses.items():
            btn = self._agent_buttons.get(name)
            if btn:
                btn.status = status.value

        # Boss summary
        status_map = {n: s.value for n, s in statuses.items()}
        boss_log = self._chat_logs["boss"]
        boss_log.write("")

        done = sum(1 for s in statuses.values() if s == AgentStatus.DONE)
        total = len(statuses)
        style = "bold green" if done == total else "bold yellow"
        boss_log.write(Text(f"Swarm complete — {done}/{total} agents finished.", style=style))

        try:
            summary = await self.boss.summarise(status_map)
            boss_log.write("")
            for line in summary.strip().splitlines():
                boss_log.write(line)
        except Exception:
            pass

        boss_log.write("")
        boss_log.write(Text(
            "You can still talk to any agent for follow-ups.",
            style="dim",
        ))

        self.query_one("#chat-input", Input).placeholder = "Ask a follow-up..."

    # ── specialist interaction ───────────────────────────────

    @work(group="agent-chat")
    async def _handle_agent_input(self, agent_name: str, text: str) -> None:
        """Send a follow-up message to a specialist agent."""
        if not self.swarm:
            return

        agent = self.swarm.agents.get(agent_name)
        log = self._chat_logs.get(agent_name)
        if not agent or not log:
            return

        if agent.status == AgentStatus.WORKING:
            log.write(Text("Agent is busy — message queued.", style="dim yellow"))
            return

        btn = self._agent_buttons.get(agent_name)
        if btn:
            btn.status = "working"

        log.write(Text("Working...", style="dim"))
        log.write("")

        try:
            await agent.execute_followup(text)
            log.write("")
            log.write(Text("✓ Done.", style="bold green"))
        except Exception as exc:
            log.write(Text(f"Error: {exc}", style="bold red"))
        finally:
            if btn:
                btn.status = "done"
