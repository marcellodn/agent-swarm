"""CLI entry point — parses args and launches the Textual app."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="agent-swarm",
        description="Multi-agent swarm orchestrator — chat with your build team.",
    )
    parser.add_argument(
        "-d", "--dir",
        type=Path,
        default=Path.cwd(),
        help="Project directory (default: current directory)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(name)s %(levelname)s: %(message)s",
    )

    project_dir = args.dir.resolve()
    project_dir.mkdir(parents=True, exist_ok=True)

    try:
        from .app import SwarmApp

        app = SwarmApp(project_dir)
        app.run()
    except KeyboardInterrupt:
        sys.exit(130)
