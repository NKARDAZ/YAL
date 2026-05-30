"""
Команда: yal create <kind>[:<name>][@<ref>]

Примеры:
  yal create book
  yal create book@latest
  yal create book@1.7.1
  yal create book@c651f7d
  yal create book:default@1.7.1
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from yal.i18n import t
from yal.templates.registry import get_entry, list_kinds
from yal.templates.book_handler import BookHandler
from yal import store, template_config

_HANDLERS = {
    "book": BookHandler(),
}


def run(args: argparse.Namespace) -> None:
    kind, name, ref = _parse_spec(args.what)

    handler = _HANDLERS.get(kind)
    if handler is None:
        print(f"[yal] {t('errors.unknown-kind', kind=kind, available=', '.join(list_kinds()))}")
        sys.exit(1)

    try:
        entry = get_entry(kind, name)
    except ValueError as e:
        print(f"[yal] {e}")
        sys.exit(1)

    output_dir = Path(args.output).resolve()

    # 1. Получаем версию и загружаем конфигурацию до создания папок
    version = handler._resolve_version(entry, name, ref)
    src_dir = store.template_dir(kind, version)
    config = template_config.load(src_dir)

    values = {}
    folder_name = None

    # 2. Собираем значения и определяем имя папки
    if config is not None:
        values = template_config.collect(config)
        folder_name = template_config.get_folder_name(config, values)

    try:
        # 3. Создаем структуру проекта с учетом имени
        result = handler.create(
            entry=entry,
            name=name,
            output_dir=output_dir,
            ref=ref,
            custom_folder_name=folder_name
        )

        # 4. Применяем настройки (запись значений в файлы)
        if config is not None:
            template_config.apply(config, values, result.dest)
        else:
            print(f"[yal] {t('config.no-config')}")

        print(f"[yal] {t('create.created', path=result.dest)}")

    except (ValueError, RuntimeError) as e:
        print(f"[yal] {t('create.error', error=e)}")
        sys.exit(1)


def _parse_spec(spec: str) -> tuple[str, str, str | None]:
    pattern = r"^(?P<kind>[^:@]+)(?::(?P<name>[^@]+))?(?:@(?P<ref>.+))?$"
    m = re.match(pattern, spec.strip())
    if not m:
        print(f"[yal] {t('errors.parse-spec', spec=spec)}")
        print(f"      {t('errors.parse-spec-hint', fmt='<kind>[:<name>][@<ref>]')}")
        sys.exit(1)

    kind = m.group("kind").lower()
    name = (m.group("name") or "default").lower()
    ref = m.group("ref") or None
    return kind, name, ref
