"""
Обработка yal.template.toml — конфигурационного файла шаблона.
"""

from __future__ import annotations

import io
import re
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any
from ruamel.yaml import YAML
import subprocess
import shlex

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

from yal.i18n import t, current_lang
from yal import generators

YAL_TOML = "yal.template.toml"

# ─── защита \uXXXX при round-trip чтении/записи YAML ─────────────────────────
# ruamel.yaml раскрывает \uXXXX → символ ещё на этапе load().
# Чтобы сохранить исходные escape-последовательности, временно заменяем их
# на заглушки из Unicode Private Use Area (U+E000–U+E001), которые ruamel
# пропускает как есть, а после dump() восстанавливаем обратно.

_YAML_UESC_RE = re.compile(r'\\u([0-9a-fA-F]{4})')
_YAML_PLACEHOLDER_RE = re.compile(r'\uE000UESC([0-9a-fA-F]{4})\uE001')


def _protect_unicode_escapes(text: str) -> str:
    """Заменяет \\uXXXX → <PUA>UESCXXXX<PUA> чтобы ruamel не раскрывал их."""
    return _YAML_UESC_RE.sub(lambda m: f'\uE000UESC{m.group(1)}\uE001', text)


def _restore_unicode_escapes(text: str) -> str:
    """Обратная замена: <PUA>UESCXXXX<PUA> → \\uXXXX."""
    return _YAML_PLACEHOLDER_RE.sub(lambda m: f'\\u{m.group(1)}', text)


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
    key: str
    field: str | None = None   # ссылка на поле из [[fields]] (приоритет)
    value: str | None = None   # литерал или ${GENERATOR} (запасной вариант)


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
    post_commands: list[str] = dc_field(default_factory=list)
    exclude: list[str] = dc_field(default_factory=list)


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
        mappings = []
        for m in td.get("fields", []):
            mappings.append(TargetFieldMapping(
                key=m["key"],
                field=m.get("field"),
                value=m.get("value"),
            ))
        targets.append(TargetDef(file=td["file"], format=td.get("format", "yaml"), mappings=mappings))

    raw_messages = raw.get("messages", {})
    messages = {}

    base_msgs = {}
    for fid, msg in raw_messages.items():
        if not isinstance(msg, dict) or any(k in msg for k in ["prompt", "placeholder"]):
            base_msgs[fid] = (msg if isinstance(msg, dict) else {"prompt": str(msg)})

    messages["_base"] = base_msgs

    # 2. Извлекаем языковые секции
    for lang, data in raw_messages.items():
        if isinstance(data, dict) and not any(k in data for k in ["prompt", "placeholder"]):
            messages[lang] = {
                fid: (msg if isinstance(msg, dict) else {"prompt": str(msg)})
                for fid, msg in data.items()
            }

    return YalConfig(
        min_version=meta.get("yal-min-version", "0.0.0"),
        fields=fields,
        targets=targets,
        messages=messages,
        post_commands=meta.get("post-commands", []),
        exclude=meta.get("exclude", [])
    )


def run_post_commands(commands: list[str], dest_dir: Path) -> None:
    """Исполняет команды в директории проекта."""
    for cmd in commands:
        print(f"[YAL] {t('config.executing', name=cmd)}")
        try:
            args = shlex.split(cmd)
            subprocess.run(args, cwd=dest_dir, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[YAL] {t('config.executing-failed', name=cmd, error=e)}")


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
        print(f"[YAL] {prompt_text}{display_default}: ", end="", flush=True)
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

    if (msg := config.messages.get(current_lang_code, {}).get(fid, {}).get(key)):
        return msg

    if (msg := config.messages.get("_base", {}).get(fid, {}).get(key)):
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
                print(f"[YAL] {t('config.target-not-found', path=file_path)}")
                continue

            raw_text = file_path.read_text(encoding='utf-8')
            protected = _protect_unicode_escapes(raw_text)
            data = yaml_parser.load(protected)

            for m in target.mappings:
                val = _resolve_mapping(m, values)
                if val is not None:
                    _set_yaml_path(data, m.key, val)

            buf = io.StringIO()
            yaml_parser.dump(data, buf)
            file_path.write_text(
                _restore_unicode_escapes(buf.getvalue()),
                encoding='utf-8',
            )


def _resolve_mapping(m: TargetFieldMapping, values: dict[str, Any]) -> str | None:
    """
    Определяет итоговое значение для маппинга по приоритету:
      1. field — ссылка на значение из пользовательского ввода (collect).
      2. value — литерал или выражение ${GENERATOR}.

    Если ни field, ни value не дали результата — возвращает None,
    и запись в YAML-файл пропускается.
    """
    # Приоритет 1: field → берём из пользовательского ввода
    if m.field is not None:
        user_val = values.get(m.field)
        if user_val is not None:
            return user_val

    # Приоритет 2: value → литерал или ${...}
    if m.value is not None:
        return generators.resolve(m.value)

    return None


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
