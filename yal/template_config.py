"""
Обработка .yal/template.toml — конфигурационного файла шаблона.
"""

from __future__ import annotations

import io
import json
import re
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any
from ruamel.yaml import YAML
import subprocess
import shlex
from ruamel.yaml import YAML

from yal import conditions
from yal.version import get_version
from yal.i18n import t, current_lang, yes_variants
from yal import generators, picker

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

_tomli_w = None
try:
    import tomli_w as _tomli_w
    _TOMLI_W_AVAILABLE = True
except ImportError:
    _tomli_w = None
    _TOMLI_W_AVAILABLE = False

YAL_YML = ".yal/template.yml"

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

# Известные типы полей. Неизвестный type трактуется как "text" с предупреждением —
# в духе остального кода (неизвестный формат target тоже не валит выполнение).
KNOWN_FIELD_TYPES: frozenset[str] = frozenset(
    {"text", "select", "multi-select", "boolean", "number", "list"}
)


@dataclass
class FieldDef:
    id: str
    type: str
    required: bool
    default: str
    options: list[str]
    is_folder_name: bool = False
    min: float | None = None       # только для type="number"
    max: float | None = None       # только для type="number"
    pattern: str | None = None     # только для type="text" — валидируется через re.fullmatch
    allow_custom: bool = False
    min_cols: int = 1
    show_if: str | None = None


@dataclass
class TargetFieldMapping:
    key: str
    field: str | None = None
    value: str | None = None
    fallback: str | None = None


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
    path = template_dir / YAL_YML
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml_parser.load(f)
    return _parse(raw)


def _parse(raw: dict[str, Any]) -> YalConfig:
    meta = raw.get("meta", {})
    fields: list[FieldDef] = []
    for fd in raw.get("fields", []):
        fields.append(FieldDef(
            id=fd["id"],
            type=fd.get("type", "text"),
            required=fd.get("required", False),
            default=generators.to_str(fd.get("default", "")),
            options=fd.get("options", []),
            is_folder_name=fd.get("is-folder-name", False),
            min=fd.get("min"),
            max=fd.get("max"),
            pattern=fd.get("pattern"),
            allow_custom=fd.get("allow-custom", False),
            min_cols=fd.get("min-cols", 1),
            show_if=fd.get("show-if"),
        ))

    targets = []
    for td in raw.get("targets", []):
        mappings = []
        for m in td.get("fields", []):
            mappings.append(TargetFieldMapping(
                key=m["key"],
                field=m.get("field"),
                value=m.get("value"),
                fallback=m.get("fallback"),
            ))
        targets.append(TargetDef(file=td["file"], format=td.get("format", "yaml"), mappings=mappings))

    raw_messages = raw.get("messages", {})
    field_ids = {fd.id for fd in fields}
    messages: dict[str, dict[str, dict[str, Any]]] = {"_base": {}}

    for key, value in raw_messages.items():
        if not isinstance(value, dict):
            # Короткая форма: messages.book-genre = "Enter book genre"
            messages["_base"][key] = {"prompt": str(value)}
            continue

        if key in field_ids:
            # messages.<field-id> — базовые (не локализованные) сообщения поля.
            # Сюда попадёт всё целиком: prompt, placeholder, option.*, и любые
            # другие произвольные ключи — без хардкода на конкретные имена.
            messages["_base"][key] = value
        else:
            # messages.<lang> — секция локализации; внутри — снова field-id → message-dict.
            messages[key] = {
                fid: (msg if isinstance(msg, dict) else {"prompt": str(msg)})
                for fid, msg in value.items()
            }

    return YalConfig(
        min_version=meta.get("yal-min-version", get_version()),
        fields=fields,
        targets=targets,
        messages=messages,
        post_commands=meta.get("post-commands", []),
        exclude=meta.get("exclude", [])
    )


def run_post_commands(commands: list[str], dest_dir: Path) -> None:
    """Исполняет команды в директории проекта."""
    import platform
    on_windows = platform.system() == "Windows"
    for cmd in commands:
        print(f"[YAL] {t('config.executing', name=cmd)}")
        try:
            if on_windows:
                # На Windows .cmd/.bat-обёртки (npm, npx, pip и т.п.) не найдёт
                # без shell=True — передаём строку напрямую
                subprocess.run(cmd, cwd=dest_dir, check=True, shell=True)
            else:
                subprocess.run(shlex.split(cmd), cwd=dest_dir, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[YAL] {t('config.executing-failed', name=cmd, error=e)}")


# ─── интерактивный сбор ───────────────────────────────────────────────────────

def collect(config: YalConfig) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for fd in config.fields:
        # Проверяем show-if
        if hasattr(fd, 'show_if') and fd.show_if:
            try:
                show = conditions.evaluate(fd.show_if, values)
                if not show:
                    # Поле скрыто — используем default с правильным типом
                    if fd.type == "boolean":
                        default = fd.default.strip().lower() in _TRUE_STRINGS
                    elif fd.type == "number":
                        try:
                            default = int(fd.default)
                        except ValueError:
                            try:
                                default = float(fd.default)
                            except ValueError:
                                default = None
                    elif fd.type == "multi-select":
                        default = [v.strip() for v in fd.default.split(",") if v.strip()] if fd.default else []
                    elif fd.type == "list":
                        default = [v.strip() for v in fd.default.split(",") if v.strip()] if fd.default else []
                    else:
                        default = fd.default
                        if default == "{placeholder}":
                            default = ""
                    values[fd.id] = default
                    continue
            except Exception:
                # При любой ошибке показываем поле (graceful degradation)
                pass

        prompt = _get_msg(config, fd.id, "prompt", fd.id)
        placeholder = _get_msg(config, fd.id, "placeholder", "")
        default = placeholder if fd.default == "{placeholder}" else fd.default
        values[fd.id] = _ask(fd, prompt, placeholder, default, config)
    return values


def _ask(fd: FieldDef, prompt_text: str, placeholder: str, default: str, config: YalConfig) -> Any:
    """Диспетчер по типу поля. Неизвестный/непригодный type — graceful fallback на text."""
    if fd.type in ("select", "multi-select") and not fd.options:
        print(f"[YAL] {t('config.field-no-options', id=fd.id, type=fd.type)}")
        return _ask_text(fd, prompt_text, placeholder, default)

    if fd.type == "boolean":
        return _ask_boolean(fd, prompt_text, default)
    if fd.type == "select":
        return _ask_select(fd, prompt_text, default, config)
    if fd.type == "multi-select":
        return _ask_multi_select(fd, prompt_text, default, config)
    if fd.type == "number":
        return _ask_number(fd, prompt_text, default)
    if fd.type == "list":
        return _ask_list(fd, prompt_text, default)

    if fd.type not in KNOWN_FIELD_TYPES:
        print(f"[YAL] {t('config.field-unknown-type', id=fd.id, type=fd.type)}")
    return _ask_text(fd, prompt_text, placeholder, default)


def _ask_text(fd: FieldDef, prompt_text: str, placeholder: str, default: str) -> str:
    compiled_pattern: re.Pattern[str] | None = None
    if fd.pattern:
        try:
            compiled_pattern = re.compile(fd.pattern)
        except re.error as e:
            print(f"[YAL] {t('config.field-pattern-invalid-regex', id=fd.id, error=e)}")

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
        if value and compiled_pattern is not None and not compiled_pattern.fullmatch(value):
            print(f"[YAL] {t('config.field-pattern-invalid', pattern=fd.pattern)}")
            continue
        return value


def _ask_boolean(fd: FieldDef, prompt_text: str, default: str) -> bool:
    default_value = default.strip().lower() in _TRUE_STRINGS if default else False
    if default_value:
        hint = t("common.confirm-prompt-true", default=" [Y/n]")
    else:
        hint = t("common.confirm-prompt-false", default=" [y/N]")
    print(f"[YAL] {prompt_text}{hint}: ", end="", flush=True)
    try:
        raw = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        raise RuntimeError(t("errors.cancelled", action=t("create.action")))
    if not raw:
        return default_value
    return raw in yes_variants()


# Сентинел "это пункт кастомного ввода", а не значение опции. Объект, а не
# строка — чтобы не было ложного совпадения, если реальная опция случайно
# совпадёт с локализованным текстом "Custom...".
_CUSTOM = object()


def _option_display(fd: FieldDef, config: YalConfig, opt: str) -> tuple[Any, str]:
    """
    value   — opt (оригинальное значение, которое попадет в values)
    display — локализованное отображение + описание
    """
    # Для хранения используем оригинальное значение opt
    value = opt
    # Для отображения берем локализованное
    display_value = _get_msg(config, fd.id, f"option.{opt}", opt)
    label = _get_msg(config, fd.id, f"option.label.{opt}", "")
    display = f"{display_value} — {label}" if label else display_value
    return value, display


def _ask_select(fd: FieldDef, prompt_text: str, default: str, config: YalConfig) -> str:
    custom_label = t("config.field-select-custom")

    resolved = [_option_display(fd, config, opt) for opt in fd.options]
    option_values: list[Any] = [v for v, _ in resolved]  # Оригинальные значения
    display_options: list[str] = [d for _, d in resolved]  # Локализованные для отображения

    # default из [[fields]] всегда оригинальное значение
    default_value = default if default in fd.options else default

    if fd.allow_custom:
        option_values.append(_CUSTOM)
        display_options.append(custom_label)

    if picker.is_interactive():
        initial_index = fd.options.index(default) if default in fd.options else 0
        chosen = picker.pick(prompt_text, display_options, multi=False, initial_index=initial_index, min_cols=fd.min_cols)
        value = option_values[chosen[0]]
    else:
        hint = t("config.field-select-hint", options=", ".join(display_options))
        while True:
            display_default = f" [{default_value}]" if default_value else ""
            print(f"[YAL] {prompt_text}{display_default}\n      {hint}: ", end="", flush=True)
            try:
                raw = input().strip()
            except (EOFError, KeyboardInterrupt):
                raise RuntimeError(t("errors.cancelled", action=t("create.action")))

            raw_value = raw if raw else default_value

            if not raw_value:
                if fd.required:
                    print(f"[YAL] {t('config.field-required')}")
                    continue
                return ""

            if fd.allow_custom and raw_value == custom_label:
                value = _CUSTOM
                break
            if raw_value in option_values:
                value = raw_value
                break

            print(f"[YAL] {t('config.field-invalid-option', options=', '.join(display_options))}")

    if value is _CUSTOM:
        return _ask_text(fd, prompt_text, "", "")
    return str(value)  # Возвращаем оригинальное значение


def _ask_multi_select(fd: FieldDef, prompt_text: str, default: str, config: YalConfig) -> list[str]:
    """
    Несколько вариантов из fd.options, с опциональной заменой значения и
    описанием (messages.<id>.option.<value> / option.label.<value>) и
    опциональным кастомным вводом (allow-custom) — кастомные пункты вводятся
    как в type="list" (свободный список строк), а не как одно текстовое
    значение, как в select. Возвращает list[str], без дублей.
    """
    options = fd.options
    resolved = [_option_display(fd, config, opt) for opt in options]
    option_values: list[Any] = [v for v, _ in resolved]  # Оригинальные значения
    display_options: list[str] = [d for _, d in resolved]  # Локализованные для отображения

    default_list = [v.strip() for v in default.split(",") if v.strip()] if default else []
    default_display = [
        option_values[options.index(v)] if v in options else v
        for v in default_list
    ]

    if picker.is_interactive():
        pick_display = list(display_options)
        pick_values: list[Any] = list(option_values)
        if fd.allow_custom:
            pick_display.append(t("config.field-select-custom"))
            pick_values.append(_CUSTOM)

        initial_checked = {options.index(v) for v in default_list if v in options}
        chosen = picker.pick(
            prompt_text, pick_display, multi=True,
            initial_checked=initial_checked, required=fd.required,
            min_cols=fd.min_cols
        )
        selected = [pick_values[i] for i in chosen]
        result = _dedupe([v for v in selected if v is not _CUSTOM])
        if _CUSTOM in selected:
            result = _dedupe(result + _collect_lines(t("config.field-multiselect-custom-prompt")))

        if fd.required and not result:
            print(f"[YAL] {t('config.field-required')}")
            return _ask_multi_select(fd, prompt_text, default, config)
        return result

    # Fallback для неинтерактивного stdin
    hint_key = "config.field-multiselect-hint-custom" if fd.allow_custom else "config.field-multiselect-hint"
    hint = t(hint_key, options=", ".join(display_options))
    while True:
        display_default = f" [{', '.join(default_display)}]" if default_display else ""
        print(f"[YAL] {prompt_text}{display_default}\n      {hint}: ", end="", flush=True)
        try:
            raw = input().strip()
        except (EOFError, KeyboardInterrupt):
            raise RuntimeError(t("errors.cancelled", action=t("create.action")))

        chosen = [v.strip() for v in raw.split(",") if v.strip()] if raw else default_display

        if not chosen:
            if fd.required:
                print(f"[YAL] {t('config.field-required')}")
                continue
            return []

        if not fd.allow_custom:
            invalid = [v for v in chosen if v not in option_values]
            if invalid:
                print(f"[YAL] {t('config.field-invalid-option', options=', '.join(display_options))}")
                continue

        return _dedupe(chosen)


def _dedupe(items: list[str]) -> list[str]:
    """Убирает дубли, сохраняя порядок первого появления."""
    seen: set[str] = set()
    result: list[str] = []
    for v in items:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


def _collect_lines(prompt_text: str) -> list[str]:
    """
    Сырой сбор строк до пустой строки — общий механизм для type="list" и для
    кастомного хвоста allow-custom в multi-select (тот же паттерн, что уже
    использует add._ask_excludes).
    """
    hint = t("config.field-list-hint")
    print(f"[YAL] {prompt_text}\n      {hint}")
    items: list[str] = []
    while True:
        print("  > ", end="", flush=True)
        try:
            line = input().strip()
        except (EOFError, KeyboardInterrupt):
            raise RuntimeError(t("errors.cancelled", action=t("create.action")))
        if not line:
            break
        items.append(line)
    return items


def _parse_number(raw: str) -> int | float | None:
    """int предпочтительнее float — "8080" должно остаться 8080, не 8080.0."""
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return None


def _number_range_text(fd: FieldDef) -> str | None:
    """Единая фраза диапазона — используется и как постоянная подсказка
    у строки ввода, и как сообщение об ошибке при выходе за границы."""
    if fd.min is None and fd.max is None:
        return None
    lo = fd.min if fd.min is not None else "-∞"
    hi = fd.max if fd.max is not None else "∞"
    return t("config.field-number-range", min=lo, max=hi)


def _ask_number(fd: FieldDef, prompt_text: str, default: str) -> int | float | None:
    """
    Числовой ввод с опциональной валидацией диапазона (fd.min/fd.max).
    Не required + пусто → None (а не 0 — отсутствие значения это не ноль).
    """
    range_text = _number_range_text(fd)
    while True:
        display_default = f" [{default}]" if default else ""
        suffix = f"  ({range_text})" if range_text else ""
        print(f"[YAL] {prompt_text}{display_default}{suffix}: ", end="", flush=True)
        try:
            raw = input().strip()
        except (EOFError, KeyboardInterrupt):
            raise RuntimeError(t("errors.cancelled", action=t("create.action")))

        raw_value = raw if raw else default
        if not raw_value:
            if fd.required:
                print(f"[YAL] {t('config.field-required')}")
                continue
            return None

        value = _parse_number(raw_value)
        if value is None:
            print(f"[YAL] {t('config.field-number-invalid')}")
            continue
        if (fd.min is not None and value < fd.min) or (fd.max is not None and value > fd.max):
            print(f"[YAL] {range_text}")
            continue
        return value


def _ask_list(fd: FieldDef, prompt_text: str, default: str) -> list[str]:
    """
    Произвольный список строк — в отличие от multi-select, варианты не
    ограничены фиксированным набором. Ввод по одной строке, пустая
    строка — конец (тот же паттерн, что уже использует add._ask_excludes;
    общий механизм — в _collect_lines, он же используется кастомным хвостом
    allow-custom у multi-select).
    """
    default_list = [v.strip() for v in default.split(",") if v.strip()] if default else []

    while True:
        display_default = f" [{', '.join(default_list)}]" if default_list else ""
        items = _collect_lines(f"{prompt_text}{display_default}")

        if not items:
            items = default_list

        if not items and fd.required:
            print(f"[YAL] {t('config.field-required')}")
            continue

        return items


# Канонические "истинные" строки для default булевых полей (не зависит от
# локали — это конфиг шаблона, а не пользовательский ввод).
_TRUE_STRINGS: frozenset[str] = frozenset({"true", "1", "yes", "on"})


def _get_msg(config: YalConfig, fid: str, key: str, fallback: str) -> str:
    """
    Достаёт сообщение по произвольному точечному пути key (например "prompt",
    "placeholder", "option.en-US", "anything.nested") из messages.<field-id>
    — сначала из текущей локали, потом из _base. Путь разбирается так же,
    как dotted-key в TOML разворачивает его в вложенные таблицы — никакой
    привязки к конкретным именам ключей здесь нет.
    """
    current_lang_code = current_lang()
    for lang in (current_lang_code, "_base"):
        node: Any = config.messages.get(lang, {}).get(fid)
        if not isinstance(node, dict):
            continue
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if isinstance(node, str) and node:
            return node
    return fallback


# ─── запись ───────────────────────────────────────────────────────────────────

def apply(config: YalConfig, values: dict[str, Any], dest_dir: Path) -> None:
    """
    Применяет собранные значения к целевым файлам.
    Ведущий слэш в target.file воспринимается как корень создаваемого проекта.
    Поддерживаемые форматы: yaml, json, toml, env.
    """
    for target in config.targets:
        relative_path = target.file.lstrip('\\/')
        file_path = dest_dir / relative_path

        if not file_path.exists():
            print(f"[YAL] {t('config.target-not-found', path=file_path)}")
            continue

        fmt = target.format.lower()
        if fmt == "yaml":
            _apply_yaml(target, values, file_path, config)
        elif fmt == "json":
            _apply_json(target, values, file_path, config)
        elif fmt == "toml":
            _apply_toml(target, values, file_path, config)
        elif fmt == "env":
            _apply_env(target, values, file_path, config)
        else:
            print(f"[YAL] {t('config.unknown-format', fmt=fmt, path=file_path)}")


# ─── yaml ─────────────────────────────────────────────────────────────────────

def _apply_yaml(target: "TargetDef", values: dict[str, Any], file_path: Path, config: YalConfig) -> None:
    raw_text = file_path.read_text(encoding='utf-8')
    protected = _protect_unicode_escapes(raw_text)
    data = yaml_parser.load(protected)

    for m in target.mappings:
        should_set, val = _resolve_mapping(m, values, config)
        if should_set:
            _set_nested_path(data, m.key, val)

    buf = io.StringIO()
    yaml_parser.dump(data, buf)
    file_path.write_text(
        _restore_unicode_escapes(buf.getvalue()),
        encoding='utf-8',
    )


# ─── json ─────────────────────────────────────────────────────────────────────

def _apply_json(target: "TargetDef", values: dict[str, Any], file_path: Path, config: YalConfig) -> None:
    raw_text = file_path.read_text(encoding='utf-8')
    data = json.loads(raw_text)

    for m in target.mappings:
        should_set, val = _resolve_mapping(m, values, config)
        if should_set:
            # JSON null: наш маркер уже разрешён в None через _resolve_mapping
            _set_nested_path(data, m.key, val)

    file_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding='utf-8',
    )


# ─── toml ─────────────────────────────────────────────────────────────────────

def _apply_toml(target: "TargetDef", values: dict[str, Any], file_path: Path, config: YalConfig) -> None:
    if not _TOMLI_W_AVAILABLE or _tomli_w is None:
        print(f"[YAL] {t('config.toml-write-unavailable', path=file_path)}")
        return

    with open(file_path, "rb") as f:
        data = tomllib.load(f)

    for m in target.mappings:
        should_set, val = _resolve_mapping(m, values, config)
        if should_set:
            if val is not None:
                _set_nested_path(data, m.key, val)

    file_path.write_bytes(_tomli_w.dumps(data).encode('utf-8'))


# ─── env ──────────────────────────────────────────────────────────────────────

def _apply_env(target: "TargetDef", values: dict[str, Any], file_path: Path, config: YalConfig) -> None:
    """
    Записывает/обновляет пары KEY=value в .env-файле.
    key в mappings — это имя переменной (напр. "APP_NAME" или "VITE_API_URL").
    Dot-нотация не поддерживается: .env плоский по определению.
    Существующие строки обновляются на месте, новые добавляются в конец.
    Комментарии и пустые строки сохраняются.
    """
    lines: list[str] = []
    if file_path.exists():
        lines = file_path.read_text(encoding='utf-8').splitlines()

    updates: dict[str, str | None] = {}
    for m in target.mappings:
        should_set, val = _resolve_mapping(m, values, config)
        if should_set:
            key = m.key.split(".")[-1]  # dot-нотацию игнорируем, берём последний сегмент
            updates[key] = None if val is None else generators.to_str(val)

    written: set[str] = set()
    result: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            result.append(line)
            continue
        if "=" in stripped:
            env_key = stripped.split("=", 1)[0].strip()
            if env_key in updates:
                val = updates[env_key]
                result.append(f'{env_key}={_env_quote(val)}' if val is not None else f'# {env_key}=')
                written.add(env_key)
                continue
        result.append(line)

    # Добавляем новые ключи, которых не было в файле
    for key, val in updates.items():
        if key not in written:
            result.append(f'{key}={_env_quote(val)}' if val is not None else f'# {key}=')

    file_path.write_text("\n".join(result) + "\n", encoding='utf-8')


def _env_quote(value: str) -> str:
    """Оборачивает значение в кавычки если содержит пробелы или спецсимволы."""
    if any(c in value for c in (' ', '\t', '"', "'", '#', '$', '`', '\\')):
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _resolve_mapping(m: TargetFieldMapping, values: dict[str, Any], config: YalConfig) -> tuple[bool, Any]:
    """
    Возвращает (should_set, value).
    should_set: True — нужно записать значение (даже если оно None/null)
    value: само значение для записи (локализованное)
    """
    raw_val = None
    # Сначала пытаемся получить значение
    if m.field is not None:
        raw_val = values.get(m.field)
    elif m.value is not None:
        raw_val = generators.resolve(m.value, values)

    # Fallback
    if _is_empty(raw_val) and m.fallback is not None:
        raw_val = generators.resolve(m.fallback, values)

    # Если ничего не нашли — пропускаем запись
    if _is_empty(raw_val):
        return False, None

    # Если нашли наш маркер — это значит "установить значение в None"
    if raw_val == "__YAL_NULL__":
        return True, None

    # Находим FieldDef для локализации
    fd = next((f for f in config.fields if f.id == m.field), None)
    if fd and fd.type in ("select", "multi-select"):
        raw_val = _localize_value(fd, config, raw_val)

    return True, raw_val


def _is_empty(value: Any) -> bool:
    """
    "Пусто": "" для text/number-как-строка, [] для multi-select/list, None
    для number без значения. boolean False и числовой 0 НЕ считаются
    пустыми — это полноценные, осознанно выбранные ответы, а не
    отсутствие ввода.
    """
    return value is None or value == "" or value == []


def _set_nested_path(data: dict, key_path: str, value: Any) -> None:
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


def get_folder_name(config: YalConfig, values: dict[str, Any]) -> str | None:
    for fd in config.fields:
        if fd.is_folder_name:
            val = values.get(fd.id)
            # is-folder-name имеет смысл только для текстовых значений —
            # bool/list (boolean, multi-select) сюда не годятся, откатываемся
            # на дефолтное имя папки, а не роняем Path(...) на не-str.
            return val if isinstance(val, str) and val else None
    return None


def _localize_value(fd: FieldDef, config: YalConfig, value: Any) -> Any:
    """
    Преобразует оригинальное значение в локализованное для записи в файл.
    Если value - список, преобразует каждый элемент.
    Если value - строка и для нее есть локализация, возвращает локализованную строку.
    """
    if value is None:
        return None

    # Если список - обрабатываем каждый элемент
    if isinstance(value, list):
        return [_localize_value(fd, config, item) for item in value]

    # Если строка - ищем локализацию
    if isinstance(value, str):
        # Ищем локализацию для этого значения
        localized = _get_msg(config, fd.id, f"option.{value}", value)
        return localized

    # Иначе возвращаем как есть
    return value
