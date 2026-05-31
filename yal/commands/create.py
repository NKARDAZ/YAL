"""
Команда: yal create <kind>[:<name>][@<ref>]

Примеры:
  yal create book
  yal create book@latest
  yal create book@1.7.1
  yal create book@c651f7d
  yal create book:default@1.7.1
  yal create book:mytheme
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from yal import store, template_config, user_store
from yal.i18n import t
from yal.templates.book_handler import BookHandler
from yal.templates.registry import TemplateEntry, get_entry, list_kinds
from yal.yal_toml_writer import fill_yal_toml_origin

_HANDLERS = {
    "book": BookHandler(),
}


def run(args: argparse.Namespace) -> None:
    kind, name, ref = _parse_spec(args.what)

    handler = _HANDLERS.get(kind)
    if handler is None:
        print(f"[YAL] {t('errors.unknown-kind', kind=kind, available=', '.join(list_kinds()))}")
        sys.exit(1)

    try:
        entry = get_entry(kind, name)
    except ValueError as e:
        print(f"[YAL] {e}")
        sys.exit(1)

    output_dir = Path(args.output).resolve()

    # 1. Получаем версию и загружаем конфигурацию до создания папок
    version = handler._resolve_version(entry, name, ref)
    src_dir = _src_dir(entry, kind, name, version)
    config = template_config.load(src_dir)

    values = {}
    folder_name = None

    # 2. Собираем значения и определяем имя папки
    if config is not None:
        values = template_config.collect(config)
        folder_name = template_config.get_folder_name(config, values)

    try:
        # 3. Создаём структуру проекта
        result = handler.create(
            entry=entry,
            name=name,
            output_dir=output_dir,
            ref=ref,
            custom_folder_name=folder_name,
        )

        if config is not None:
            template_config.apply(config, values, result.dest)
            fill_yal_toml_origin(result.dest, template=kind, template_version=result.version)
        else:
            print(f"[YAL] {t('config.no-config')}")

        print(f"[YAL] {t('create.created', path=result.dest)}")

    except (ValueError, RuntimeError) as e:
        print(f"[YAL] {t('create.error', error=e)}")
        sys.exit(1)


def _src_dir(entry: TemplateEntry, kind: str, name: str, version: str) -> Path:
    """Путь к исходникам шаблона в зависимости от типа реестра."""
    if entry.is_user:
        return user_store.user_template_dir(kind, name, version)
    return store.template_dir(kind, name, version)


def _parse_spec(spec: str) -> tuple[str, str, str | None]:
    pattern = r"^(?P<kind>[^:@]+)(?::(?P<name>[^@]+))?(?:@(?P<ref>.+))?$"
    m = re.match(pattern, spec.strip())
    if not m:
        print(f"[YAL] {t('errors.parse-spec', spec=spec)}")
        print(f"      {t('errors.parse-spec-hint', fmt='<kind>[:<name>][@<ref>]')}")
        sys.exit(1)

    kind = m.group("kind").lower()
    name = m.group("name") or "default"   # регистр сохраняем как есть
    ref = m.group("ref") or None
    return kind, name, ref
