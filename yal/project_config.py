from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any
from ruamel.yaml import YAML

from yal.i18n import t

YAL_PROJECT_YML = ".yal/project.yml"

BUILTIN_COMMANDS: frozenset[str] = frozenset({"new", "update", "add", "remove"})

yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.allow_unicode = True

# ─── модели ───────────────────────────────────────────────────────────────────

@dataclass
class ArgumentDef:
    flag: str           # например "--mode"
    choices: list[str]  # допустимые значения; пусто → любое


@dataclass
class CommandDef:
    name: str
    script: str | None = None
    exec: str | None = None
    arguments: list[ArgumentDef] = dc_field(default_factory=list)
    macros: str | None = None

    @property
    def is_macro(self) -> bool:
        return self.macros is not None

    @property
    def is_inline_script(self) -> bool:
        if self.script is None:
            return False
        return "\n" in self.script.strip()


@dataclass
class OriginInfo:
    template: str
    template_version: str
    created_at: str
    yal_version: str


@dataclass
class ProjectConfig:
    origin: OriginInfo
    commands: list[CommandDef]

    def find_command(self, name: str) -> CommandDef | None:
        name_lower = name.lower()
        for cmd in self.commands:
            if cmd.name.lower() == name_lower:
                return cmd
        return None


# ─── поиск .yal/project.toml ───────────────────────────────────────────────────────────

def find_project_yaml(start: Path | None = None) -> Path | None:
    """Ищет .yal/project.yml в текущей директории. Возвращает Path или None."""
    base = (start or Path.cwd()).resolve()
    candidate = base / YAL_PROJECT_YML
    return candidate if candidate.exists() else None


def project_root(toml_path: Path) -> Path:
    """
    Возвращает корневую директорию проекта.
    Если project.toml лежит в папке .yal, корень - это родительская папка.
    """
    if toml_path.parent.name == ".yal":
        return toml_path.parent.parent
    return toml_path.parent


# ─── загрузка ─────────────────────────────────────────────────────────────────

def load(toml_path: Path) -> ProjectConfig | None:
    if not toml_path.exists():
        return None
    with open(toml_path, "r", encoding="utf-8") as f:
        raw = yaml.load(f)
    return _parse(raw)


def _parse(raw: dict[str, Any]) -> ProjectConfig:
    origin_raw = raw.get("origin", {})
    origin = OriginInfo(
        template=origin_raw.get("template", ""),
        template_version=origin_raw.get("template-version", ""),
        created_at=origin_raw.get("created-at", ""),
        yal_version=origin_raw.get("yal-version", ""),
    )

    commands: list[CommandDef] = []
    for cmd_raw in raw.get("command", []):
        name = cmd_raw.get("name", "").strip()
        if not name:
            continue
        args: list[ArgumentDef] = []
        for flag, choices in cmd_raw.get("arguments", {}).items():
            args.append(ArgumentDef(flag=flag, choices=list(choices)))
        commands.append(CommandDef(
            name=name,
            script=cmd_raw.get("script"),
            exec=cmd_raw.get("exec"),
            arguments=args,
            macros=cmd_raw.get("macros"),
        ))

    return ProjectConfig(origin=origin, commands=commands)


# ─── резолвинг путей и интерпретаторов ───────────────────────────────────────

def resolve_script_path(script: str, root: Path) -> Path:
    """
    Ведущий «/» означает корень проекта (root), а не корень ФС.
    """
    if script.startswith("/") or script.startswith("\\"):
        return (root / script.lstrip("/\\")).resolve()
    return (root / script).resolve()


_EXT_EXEC: dict[str, str] = {
    ".py": "python3",
    ".js": "node",
    ".ts": "ts-node",
    ".rb": "ruby",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".fish": "fish",
    ".pl": "perl",
    ".lua": "lua",
    ".php": "php",
}


def resolve_exec(exec_str: str | None, script_path: Path | None) -> list[str]:
    """
    Возвращает [interpreter, ...] для subprocess.

    «os-bash» → ["cmd", "/c"] на Windows, ["bash", "-c"] на Unix.
    Если exec не задан — определяем по расширению скрипта.
    """
    if exec_str is not None:
        if exec_str.lower() == "os-bash":
            if platform.system() == "Windows":
                return ["cmd", "/c"]
            return ["bash", "-c"]
        return exec_str.split()

    if script_path is not None:
        ext = script_path.suffix.lower()
        if ext in _EXT_EXEC:
            return [_EXT_EXEC[ext]]

    return []


# Флаг "выполнить код напрямую" для каждого интерпретатора — позволяет
# передать инлайн-скрипт как один CLI-аргумент, без записи на диск.
_INLINE_FLAGS: dict[str, str] = {
    "python3": "-c", "python": "-c",
    "node": "-e", "ts-node": "-e",
    "ruby": "-e",
    "bash": "-c", "zsh": "-c", "fish": "-c", "sh": "-c",
    "perl": "-e",
    "lua": "-e",
    "php": "-r",
}


def resolve_inline_exec(exec_str: str | None) -> list[str]:
    """
    Возвращает [interpreter, ..., flag] для запуска инлайн-скрипта
    (cmd.script — многострочная строка) без создания временного файла:
    весь код передаётся интерпретатору как один аргумент через его
    собственный флаг "выполнить код" (-c/-e/-r).

    «os-bash» → ["cmd", "/c"] на Windows, ["bash", "-c"] на Unix — флаг
    уже включён в результат resolve_exec, отдельно его добавлять не нужно.

    В отличие от resolve_exec, exec для инлайн-скрипта обязателен:
    расширения файла, по которому можно было бы угадать интерпретатор,
    здесь просто нет.
    """
    if exec_str is None:
        raise ArgumentError(t("project.inline-exec-required"))

    if exec_str.lower() == "os-bash":
        if platform.system() == "Windows":
            return ["cmd", "/c"]
        return ["bash", "-c"]

    parts = exec_str.split()
    interpreter = parts[0]
    flag = _INLINE_FLAGS.get(interpreter)
    if flag is None:
        raise ArgumentError(t("project.inline-exec-unsupported", exec=exec_str))

    return parts + [flag]


# Интерпретаторы, которые пытаются распарсить "--flag=value" как СВОЙ
# собственный CLI-флаг, если не поставить разделитель "--" перед аргументами
# скрипта. python3/python — протестированное исключение: ему "--" не нужен,
# и он не вычищает его сам, так что лишний "--" просочился бы в sys.argv.
_INLINE_NEEDS_SEPARATOR: set[str] = {
    "bash", "zsh", "fish", "sh",
    "node", "ts-node",
    "ruby", "perl", "php",
}

# lua трактует первый позиционный аргумент после кода как путь к файлу-скрипту
# для запуска — даже вместе с -e. Передать туда "--flag=value" и получить его
# в `arg`, не наткнувшись на "cannot open <flag>", средствами самого lua CLI
# невозможно — поэтому при наличии аргументов явно отказываем, а не теряем их.
_INLINE_NO_EXTRA_ARGS: set[str] = {"lua"}


def inline_extra_args(interpreter: str, flags: dict[str, str]) -> list[str]:
    """
    Формирует CLI-хвост с пользовательскими флагами для инлайн-запуска,
    учитывая то, как конкретный интерпретатор разбирает свои аргументы.
    """
    if not flags:
        return []

    if interpreter in _INLINE_NO_EXTRA_ARGS:
        raise ArgumentError(t("project.inline-args-unsupported", exec=interpreter))

    extra: list[str] = ["--"] if interpreter in _INLINE_NEEDS_SEPARATOR else []
    for flag, value in flags.items():
        extra.append(f"{flag}={value}" if value else flag)
    return extra


# ─── валидация аргументов ─────────────────────────────────────────────────────

class ArgumentError(ValueError):
    pass


def validate_args(cmd: CommandDef, user_args: dict[str, str]) -> dict[str, str]:
    """
    Проверяет переданные аргументы. Бросает ArgumentError при нарушении.
    - Неизвестный флаг → ошибка
    - choices непустой → значение должно быть в нём
    - choices пустой  → любое значение
    """
    known_flags = {a.flag: a for a in cmd.arguments}
    result: dict[str, str] = {}

    for flag, value in user_args.items():
        if flag not in known_flags:
            raise ArgumentError(t(
                "project.arg-unknown",
                name=cmd.name,
                flag=flag,
                available=", ".join(known_flags) or t("project.arg-none"),
            ))
        arg_def = known_flags[flag]
        if arg_def.choices and value not in arg_def.choices:
            raise ArgumentError(t(
                "project.arg-invalid-value",
                flag=flag,
                value=value,
                choices=", ".join(arg_def.choices),
            ))
        result[flag] = value

    return result


def parse_user_args(argv: list[str]) -> dict[str, str]:
    """
    Разбирает ["--mode=print", "--as=pdf"] → {"--mode": "print", "--as": "pdf"}.
    Поддерживает: --key=value, --key value, --flag (без значения → "").
    """
    result: dict[str, str] = {}
    i = 0
    while i < len(argv):
        token = argv[i]
        if "=" in token and token.startswith("--"):
            key, _, val = token.partition("=")
            result[key] = val
        elif token.startswith("--"):
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                result[token] = argv[i + 1]
                i += 1
            else:
                result[token] = ""
        i += 1
    return result
