"""
Команда: yal update <kind>[:<name>]

Примеры:
  yal update book
  yal update book:default
  yal update book:mytheme
  yal update my-kind:default
  yal update book --commit
"""

from __future__ import annotations

import argparse
import re
import sys

from yal.i18n import t
from yal.templates.handler_def import get_handler, known_kinds
from yal.templates.registry import get_entry


def run(args: argparse.Namespace) -> None:
    kind, name = _parse_spec(args.what)

    try:
        entry = get_entry(kind, name)
    except ValueError as e:
        print(f"[YAL] {e}")
        sys.exit(1)

    handler = get_handler(kind, entry)
    if handler is None:
        print(f"[YAL] {t('errors.unknown-kind', kind=kind, available=', '.join(known_kinds()))}")
        sys.exit(1)

    try:
        handler.update_template(entry, name, force_commit=getattr(args, "commit", False))
    except (ValueError, RuntimeError) as e:
        print(f"[YAL] {t('create.error', error=e)}")
        sys.exit(1)


def _parse_spec(spec: str) -> tuple[str, str]:
    m = re.match(r"^(?P<kind>[^:@]+)(?::(?P<name>[^@]+))?$", spec.strip())
    if not m:
        print(f"[YAL] {t('errors.parse-spec', spec=spec)}")
        print(f"      {t('errors.parse-spec-hint', fmt='<kind>[:<name>]')}")
        sys.exit(1)

    kind = m.group("kind").lower()
    name = m.group("name") or "default"
    return kind, name
