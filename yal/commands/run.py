"""
Команда: yal <custom-name> [--arg=value ...]

Выполняет команды, описанные в yal.toml текущего проекта.
Встроенные команды (new, update) всегда имеют приоритет — этот
модуль вызывается только если команда не опознана как встроенная.

Поддерживаемые варианты:
  1. Скрипт-файл  — script = "/build/build.py", exec = "python3"
  2. Inline-скрипт — script = multiline string, exec = "os-bash"
  3. Макрос        — macros = "make --mode=print"
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from yal.project_config import (
    BUILTIN_COMMANDS,
)

from yal.i18n import t
from yal.project_config import (
    ArgumentError,
    CommandDef,
    ProjectConfig,
    find_project_toml,
    load,
    parse_user_args,
    project_root,
    resolve_exec,
    resolve_script_path,
    validate_args,
)

_MAX_MACRO_DEPTH = 10


# ─── точка входа из cli.py ────────────────────────────────────────────────────

def run_from_argv(argv: list[str]) -> None:
    toml_path = find_project_toml()
    config = None
    root = None
    messages = []

    if toml_path is not None:
        config = load(toml_path)
        if config is None:
            messages.append(f"[YAL] {t('project.toml-invalid')}")
            sys.exit(1)
        root = project_root(toml_path)
    else:
        messages.append(f"[YAL] {t('project.no-toml')}")

    if config is not None:
        best_name: str | None = None
        best_len: int = 0

        for cmd in config.commands:
            name_tokens = cmd.name.strip().split()
            n = len(name_tokens)
            if argv[:n] == name_tokens and n > best_len:
                best_name = cmd.name
                best_len = n

        if best_name is not None:
            raw_args = argv[best_len:]
            _execute(best_name, raw_args, config, root, depth=0)
            return

    candidate = argv[0] if argv else ""
    print(f"[YAL] {t('project.command-not-found', name=candidate)}")
    _print_available(config)
    for msg in messages:
        print(msg)
    sys.exit(1)


# ─── выполнение ───────────────────────────────────────────────────────────────

def _execute(
    command_name: str,
    raw_argv: list[str],
    config: ProjectConfig | None,
    root: Path | None,
    depth: int,
) -> None:
    if config is None or root is None:
        print(f"[YAL] {t('project.no-toml')}")
        sys.exit(1)

    if depth > _MAX_MACRO_DEPTH:
        print(f"[YAL] {t('project.macro-loop', name=command_name)}")
        sys.exit(1)

    cmd = config.find_command(command_name)
    if cmd is None:
        print(f"[YAL] {t('project.command-not-found', name=command_name)}")
        _print_available(config)
        sys.exit(1)

    if cmd.is_macro:
        _run_macro(cmd, config, root, depth)
    else:
        _run_script(cmd, raw_argv, root)


def _run_macro(cmd: CommandDef, config: ProjectConfig, root: Path, depth: int) -> None:
    assert cmd.macros is not None
    tokens = cmd.macros.strip().split()
    if not tokens:
        print(f"[YAL] {t('project.macro-empty', name=cmd.name)}")
        sys.exit(1)

    target_name = tokens[0]
    macro_args = tokens[1:]
    print(f"[YAL] {t('project.macro-expanding', from_=cmd.name, to=target_name)}")
    _execute(target_name, macro_args, config, root, depth + 1)


def _run_script(cmd: CommandDef, raw_argv: list[str], root: Path) -> None:
    assert cmd.script is not None

    user_args = parse_user_args(raw_argv)
    try:
        validated = validate_args(cmd, user_args)
    except ArgumentError as e:
        print(f"[YAL] {e}")
        sys.exit(1)

    _run_file(cmd, validated, root)


def _run_file(cmd: CommandDef, validated: dict[str, str], root: Path) -> None:
    assert cmd.script is not None
    script_path = resolve_script_path(cmd.script, root)

    if not script_path.exists():
        print(f"[YAL] {t('project.script-not-found', path=script_path)}")
        sys.exit(1)

    exec_parts = resolve_exec(cmd.exec, script_path)
    cli = (exec_parts + [str(script_path)]) if exec_parts else [str(script_path)]

    for flag, value in validated.items():
        cli.append(f"{flag}={value}" if value else flag)

    print(f"[YAL] {t('project.running', cmd=' '.join(cli))}")
    _subprocess_run(cli, cwd=root)


def _subprocess_run(
    cli: list[str],
    cwd: Path,
    extra_env: dict[str, str] | None = None,
) -> None:
    env = {**os.environ, **(extra_env or {})}
    result = subprocess.run(cli, cwd=cwd, env=env)
    if result.returncode != 0:
        print(f"[YAL] {t('project.script-failed', code=result.returncode)}")
        sys.exit(result.returncode)


def _build_env(args: dict[str, str]) -> dict[str, str]:
    """{"--mode": "print"} → {"YAL_MODE": "print"}"""
    return {
        "YAL_" + flag.lstrip("-").upper().replace("-", "_"): value
        for flag, value in args.items()
    }


def _ext_for_exec(interpreter: str) -> str:
    return {
        "python3": ".py", "python": ".py",
        "node": ".js", "ts-node": ".ts",
        "ruby": ".rb", "perl": ".pl",
        "lua": ".lua", "php": ".php",
    }.get(interpreter, ".tmp")


def _print_available(config: ProjectConfig | None) -> None:
    builtin_names = list(BUILTIN_COMMANDS)
    print(f"[YAL] {t('project.available-commands', names=', '.join(builtin_names))}")

    if config is None:
        return
    if not config.commands:
        print(f"[YAL] {t('project.no-commands')}")
        return

    project_names = [cmd.name for cmd in config.commands]
    print(f"[YAL] {t('project.available-project-commands', names=', '.join(project_names))}")
