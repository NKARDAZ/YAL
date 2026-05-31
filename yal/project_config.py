from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

from yal.i18n import t

YAL_PROJECT_TOML = "yal.toml"

# Встроенные команды — их нельзя перекрыть из yal.toml
BUILTIN_COMMANDS: frozenset[str] = frozenset({"create", "update"})


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


# ─── поиск yal.toml ───────────────────────────────────────────────────────────

def find_project_toml(start: Path | None = None) -> Path | None:
    """Ищет yal.toml в текущей директории. Возвращает Path или None."""
    base = (start or Path.cwd()).resolve()
    candidate = base / YAL_PROJECT_TOML
    return candidate if candidate.exists() else None


def project_root(toml_path: Path) -> Path:
    return toml_path.parent


# ─── загрузка ─────────────────────────────────────────────────────────────────

def load(toml_path: Path) -> ProjectConfig | None:
    if not toml_path.exists():
        return None
    with open(toml_path, "rb") as f:
        raw = tomllib.load(f)
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
