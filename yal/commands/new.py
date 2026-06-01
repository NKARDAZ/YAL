"""
Команда: yal create <kind>[:<name>][@<ref>]

Примеры:
  yal create book
  yal create book@latest
  yal create book@1.7.1
  yal create book@c651f7d
  yal create book:default@1.7.1
  yal create book:mytheme
  yal create my-kind:default
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from yal import store, template_config, user_store
from yal.i18n import t
from yal.templates.handler_def import get_handler, known_kinds
from yal.templates.registry import TemplateEntry, get_entry
from yal.yal_toml_writer import fill_yal_toml_origin


def run(args: argparse.Namespace) -> None:
    kind, name, ref = _parse_spec(args.what)

    try:
        entry = get_entry(kind, name)
    except ValueError as e:
        print(f"[YAL] {e}")
        sys.exit(1)

    handler = get_handler(kind, entry)
    if handler is None:
        print(f"[YAL] {t('errors.unknown-kind', kind=kind, available=', '.join(known_kinds()))}")
        sys.exit(1)

    output_dir = Path(args.output).resolve()

    # 1. Определяем версию один раз (может потребовать загрузки и подтверждения)
    version = handler._resolve_version(entry, name, ref)

    # 2. Загружаем конфигурацию шаблона
    src_dir = _src_dir(entry, kind, name, version)
    config = template_config.load(src_dir)

    values = {}
    folder_name = None

    # 3. Собираем значения полей и имя папки (диалог с пользователем)
    if config is not None:
        values = template_config.collect(config)
        folder_name = template_config.get_folder_name(config, values)

    try:
        # 4. Копируем шаблон в dest, передавая уже определённую версию
        #    чтобы handler.create не вызывал _resolve_version повторно
        result = handler.create(
            entry=entry,
            name=name,
            output_dir=output_dir,
            ref=ref,
            custom_folder_name=folder_name,
            resolved_version=version,
        )

        if config is not None:
            template_config.apply(config, values, result.dest)
            fill_yal_toml_origin(result.dest, template=kind, template_version=result.version)
            if config.post_commands:
                template_config.run_post_commands(config.post_commands, result.dest)
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
    name = m.group("name") or "default"
    ref = m.group("ref") or None
    return kind, name, ref
