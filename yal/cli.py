"""yal — точка входа CLI."""

from __future__ import annotations

import argparse
import sys

from yal.commands import create as cmd_create
from yal.commands import update as cmd_update


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yal",
        description="Yalla Nkardaz’s personal CLI toolkit",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # ── create ───────────────────────────────────────────────────────────────
    p_create = sub.add_parser("create", help="Create project from template")
    p_create.add_argument(
        "what",
        help=(
            "What to create. Format: <kind>[:<name>][@<ref>]\n"
            "Example: book  |  book@1.7.1  |  book@c651f7d  |  book:default@latest"
        ),
    )
    p_create.add_argument(
        "-o", "--output",
        default=".",
        metavar="DIR",
        help="Where to save the result (default: current directory)",
    )

    # ── update ───────────────────────────────────────────────────────────────
    p_update = sub.add_parser("update", help="Update template")
    p_update.add_argument(
        "what",
        help=(
            "What to update. Format: <kind>[:<name>]\n"
            "Example: book  |  book:default"
        ),
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "create":
        cmd_create.run(args)

    if args.command == "update":
        cmd_update.run(args)
