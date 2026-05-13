# Agent Swarm

A terminal-based multi-agent orchestrator with a chat-style TUI. A **Boss** agent talks to you, plans the work, then spawns specialist agents that build your software in parallel — each in their own chat window you can switch between.

## How it works

```
┌──────────┬──────────────────────────────────────┐
│ AGENTS   │  backend-api (backend)               │
│          │  ─────────────────────                │
│ ● Boss   │                                       │
│ ● backend│  Starting: Build REST endpoints...    │
│ ● auth   │  Creating src/routes.py               │
│ ● tests  │  Setting up Express middleware...     │
│          │                                       │
├──────────┴──────────────────────────────────────┤
│ > Talk to any agent...                   Ctrl+N │
└─────────────────────────────────────────────────┘
```

1. **Describe** your project to the Boss
2. **Review** the plan — the Boss breaks it into specialist tasks
3. **Approve** (or tweak) the plan
4. **Watch** agents work in real-time chat windows (Ctrl+N / Ctrl+P to switch)
5. **Talk** to any agent directly for follow-ups
6. **Get** a summary when the swarm finishes

## Quick start

```bash
# Clone and install
git clone https://github.com/marcellodng/agent-swarm.git
cd agent-swarm
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e .

# Run (in any project directory)
agent-swarm --dir ~/my-project
```

### Prerequisites

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated

## Built-in specialist roles

| Role | Focus |
|------|-------|
| `backend` | Server-side code, APIs, business logic |
| `frontend` | UI components, responsive design, accessibility |
| `cybersecurity` | OWASP Top 10, auth, input validation, secrets |
| `designer` | Design systems, CSS, colour palettes, typography |
| `devops` | Docker, CI/CD, deployment, monitoring |
| `database` | Schemas, migrations, query optimisation |
| `testing` | Unit, integration, and e2e tests |
| `architect` | System design, API contracts, ADRs |
| `docs` | README, API docs, onboarding guides |

The Boss picks the right combination based on your project.

## Architecture

```
agent_swarm/
  app.py      # Textual TUI — chat windows, sidebar, input
  cli.py      # CLI entry point
  boss.py     # Plans work, talks to user, summarises results
  swarm.py    # Orchestrator — agent lifecycle and dependencies
  agent.py    # Single agent wrapper around claude-code-sdk
  bus.py      # Async message bus for inter-agent communication
  config.py   # Dataclasses (AgentConfig, SwarmPlan, AgentStatus)
  roles.py    # Specialist role definitions and prompt builder
```

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+N` | Switch to next agent |
| `Ctrl+P` | Switch to previous agent |
| `Ctrl+Q` | Quit |

## How agents coordinate

- **Hub-and-spoke**: all messages route through the Boss
- **File-based contracts**: agents write clean, documented code so others can read it
- **Done signals**: each agent writes a summary to `_swarm/done/<name>.md`
- **Dependency ordering**: agents can declare dependencies; the swarm respects launch order
- **Follow-ups**: talk to any agent after their task for refinements

## Contributing

1. Fork the repo
2. Create a feature branch
3. Install dev dependencies: `pip install -e ".[dev]"`
4. Run linting: `ruff check .`
5. Submit a PR

## License

MIT — free to use, modify, and distribute.
