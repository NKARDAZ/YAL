"""
Обработка yal.toml — конфигурационного файла шаблона.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any
from ruamel.yaml import YAML

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

from yal.i18n import t, current_lang

YAL_TOML = "yal.toml"

# Настройка парсера для "Round-trip" (сохранение структуры)
yaml_parser = YAML()
yaml_parser.preserve_quotes = True
yaml_parser.indent(mapping=2, sequence=4, offset=2)
yaml_parser.allow_unicode = True
yaml_parser.encoding = 'utf-8'
yaml_parser.representer.ignore_aliases = lambda *args: True


# Утилита для отображения None как ~
def _represent_none(self, data):
    return self.represent_scalar('tag:yaml.org,2002:null', '~')


yaml_parser.representer.add_representer(type(None), _represent_none)


# ─── модели ───────────────────────────────────────────────────────────────────

@dataclass
class FieldDef:
    id: str
    type: str
    required: bool
    default: str
    options: list[str]
    is_folder_name: bool = False


@dataclass
class TargetFieldMapping:
    field: str
    key: str


@dataclass
class TargetDef:
    file: str
    format: str
    mappings: list[TargetFieldMapping] = dc_field(default_factory=list)


@dataclass
class YalConfig:
    min_version: str
    fields: list[FieldDef]
    targets: list[TargetDef]
    messages: dict[str, dict[str, dict[str, str]]]


# ─── загрузка ─────────────────────────────────────────────────────────────────

def load(template_dir: Path) -> YalConfig | None:
    path = template_dir / YAL_TOML
    if not path.exists():
        return None
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    return _parse(raw)


def _parse(raw: dict[str, Any]) -> YalConfig:
    meta = raw.get("meta", {})
    fields = [FieldDef(id=fd["id"], type=fd.get("type", "text"), required=fd.get("required", False),
                       default=fd.get("default", ""), options=fd.get("options", []),
                       is_folder_name=fd.get("is-folder-name", False)) for fd in raw.get("fields", [])]

    targets = []
    for td in raw.get("targets", []):
        mappings = [TargetFieldMapping(field=m["field"], key=m["key"]) for m in td.get("fields", [])]
        targets.append(TargetDef(file=td["file"], format=td.get("format", "yaml"), mappings=mappings))

    messages = {}
    for lang, lang_data in raw.get("messages", {}).items():
        messages[lang] = {fid: (msg if isinstance(msg, dict) else {"prompt": str(msg)})
                          for fid, msg in lang_data.items()}

    return YalConfig(min_version=meta.get("yal-min-version", "0.0.0"), fields=fields, targets=targets, messages=messages)


# ─── интерактивный сбор ───────────────────────────────────────────────────────

def collect(config: YalConfig) -> dict[str, str]:
    values = {}
    for fd in config.fields:
        prompt = _get_msg(config, fd.id, "prompt", fd.id)
        placeholder = _get_msg(config, fd.id, "placeholder", "")
        default = placeholder if fd.default == "{placeholder}" else fd.default
        values[fd.id] = _ask(fd, prompt, placeholder, default)
    return values


def _ask(fd: FieldDef, prompt_text: str, placeholder: str, default: str) -> str:
    while True:
        display_default = f" [{default}]" if default else ""
        print(f"[yal] {prompt_text}{display_default}: ", end="", flush=True)
        try:
            raw = input().strip()
        except (EOFError, KeyboardInterrupt):
            raise RuntimeError(t("errors.cancelled", action=t("create.action")))
        value = raw if raw else default
        if fd.required and not value:
            continue
        return value


def _get_msg(config: YalConfig, fid: str, key: str, fallback: str) -> str:
    current_lang_code = current_lang()
    for lang_code in [current_lang_code, "en", next(iter(config.messages), "")]:
        if (msg := config.messages.get(lang_code, {}).get(fid, {}).get(key)):
            return msg
    return fallback


# ─── запись ───────────────────────────────────────────────────────────────────

def apply(config: YalConfig, values: dict[str, Any], dest_dir: Path) -> None:
    """
    Применяет собранные значения к целевым файлам.
    Ведущий слэш в target.file воспринимается как корень создаваемого проекта.
    """
    for target in config.targets:
        if target.format == "yaml":
            relative_path = target.file.lstrip('\\/')
            file_path = dest_dir / relative_path

            if not file_path.exists():
                print(f"[yal] Ошибка: целевой файл {file_path} не найден.")
                continue

            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml_parser.load(f)

            for m in target.mappings:
                val = values.get(m.field)
                if val is not None:
                    _set_yaml_path(data, m.key, val)

            with open(file_path, 'w', encoding='utf-8') as f:
                yaml_parser.dump(data, f)


def _set_yaml_path(data: dict, key_path: str, value: str) -> None:
    segments = _parse_key_path(key_path)
    node = data
    for i, seg in enumerate(segments[:-1]):
        if isinstance(seg, int):
            node = node[seg]
        else:
            if seg not in node:
                next_seg = segments[i + 1]
                node[seg] = [] if isinstance(next_seg, int) else {}
            node = node[seg]
    node[segments[-1]] = value


def _parse_key_path(key_path: str) -> list[str | int]:
    result = []
    for part in key_path.split("."):
        m = re.match(r"^(.+?)\[(\d+)\]$", part)
        if m:
            result.append(m.group(1))
            result.append(int(m.group(2)))
        else:
            result.append(part)
    return result


def get_folder_name(config: YalConfig, values: dict[str, str]) -> str | None:
    for fd in config.fields:
        if fd.is_folder_name:
            return values.get(fd.id)
    return None
