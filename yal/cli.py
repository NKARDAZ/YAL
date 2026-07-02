"""yal — точка входа CLI."""

from __future__ import annotations

import argparse
import sys

from yal.commands import new as cmd_create
from yal.commands import update as cmd_update
from yal.commands import run as cmd_run
from yal.commands import add as cmd_add
from yal.commands import remove as cmd_remove
from yal.project_config import BUILTIN_COMMANDS
from yal.version import get_version
from yal.i18n import t


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yal",
        description="Yalla Nkardaz's personal CLI toolkit",
    )

    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"YAL {get_version()}",
        help="Show utility’s version number and exit"
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # ── new ───────────────────────────────────────────────────────────────
    p_create = sub.add_parser("new", help="Create project from template")
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
    p_create.add_argument(
        "--commit",
        action="store_true",
        help="Skip release lookup and use the latest matching commit instead",
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
    p_update.add_argument(
        "--commit",
        action="store_true",
        help="Skip release lookup and update to the latest commit instead",
    )

    # ── add ──────────────────────────────────────────────────────────────────
    p_add = sub.add_parser("add", help="Register an external template from a git repository")
    p_add.add_argument(
        "what",
        help="Template to register. Format: <kind>:<name>[@<ref>], e.g. gitlab:test@c651f7db",
    )
    p_add.add_argument(
        "from_kw",
        nargs="?",
        metavar="from",
        help="Optional keyword 'from'",
    )
    p_add.add_argument(
        "repo",
        nargs="?",
        metavar="URL",
        help="Git repository URL",
    )
    p_add.add_argument(
        "--commit",
        action="store_true",
        help="Skip release lookup and download the latest matching commit instead",
    )

    # ── remove ────────────────────────────────────────────────────────────────
    p_remove = sub.add_parser("remove", help="Remove downloaded template(s)")
    p_remove.add_argument(
        "what",
        help=(
            "What to remove. Format: <kind>[:<name>[@<version>]]\n"
            "Example: book  |  book:default  |  book:default@1.7.1"
        ),
    )

    return parser


def main() -> None:
    args_list = sys.argv[1:]
    flags = [arg for arg in args_list if arg.startswith("-")]
    command_args = [arg for arg in args_list if not arg.startswith("-")]

    parser = build_parser()
    parser.parse_known_args(flags)

    if command_args:
        command = command_args[0]

        # Встроенные команды
        if command in BUILTIN_COMMANDS:
            args = parser.parse_args(args_list)

            # Обёртка для перехвата KeyboardInterrupt
            try:
                if args.command == "new":
                    cmd_create.run(args)
                elif args.command == "update":
                    cmd_update.run(args)
                elif args.command == "add":
                    cmd_add.run(args)
                elif args.command == "remove":
                    cmd_remove.run(args)
            except KeyboardInterrupt:
                print(f"\n[YAL] {t('errors.interrupted')}")
                sys.exit(130)
            return

    if args_list:
        # Для run команды тоже нужен перехват
        try:
            cmd_run.run_from_argv(args_list)
        except KeyboardInterrupt:
            print(f"\n[YAL] {t('errors.interrupted')}")
            sys.exit(130)
    else:
        parser.print_help()
