"""yal — точка входа CLI."""

from __future__ import annotations

import argparse
import sys

from yal.commands import create as cmd_create
from yal.commands import update as cmd_update


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yal",
        description="Your personal CLI toolkit",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # ── create ───────────────────────────────────────────────────────────────
    p_create = sub.add_parser("create", help="Создать проект по шаблону")
    p_create.add_argument(
        "what",
        help=(
            "Что создать. Формат: <kind>[:<name>][@<ref>]\n"
            "Примеры: book  |  book@1.7.1  |  book@c651f7d  |  book:default@latest"
        ),
    )
    p_create.add_argument(
        "-o", "--output",
        default=".",
        metavar="DIR",
        help="Куда сохранить результат (по умолчанию: текущая папка)",
    )

    # ── update ───────────────────────────────────────────────────────────────
    p_update = sub.add_parser("update", help="Обновить шаблон до последней версии")
    p_update.add_argument(
        "what",
        help="Что обновить. Формат: <kind>[:<name>]  Пример: book  |  book:default",
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
