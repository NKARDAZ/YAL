"""
Интерактивный выбор из списка стрелками — как checkbox/select в inquirer
(используется, например, в `npm create vue@latest`).

↑/↓ — навигация, Space — отметить/снять (только multi-select), Enter — подтвердить,
Esc/Ctrl+C/Ctrl+D — отмена (RuntimeError с тем же сообщением, что и остальные
confirm-диалоги приложения).

Если stdin/stdout не являются настоящим терминалом (пайп, редирект, тесты,
CI) — is_interactive() вернёт False, и вызывающий код должен использовать
текстовый fallback (см. template_config._ask_select/_ask_multi_select).

Реализовано на чистом stdlib: termios/tty на Unix, msvcrt на Windows —
без внешних зависимостей вроде curses/questionary/inquirer.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Iterator, NoReturn

from yal.i18n import t

_CURSOR_HIDE = "\x1b[?25l"
_CURSOR_SHOW = "\x1b[?25h"


def is_interactive() -> bool:
    """True, если можно безопасно запустить интерактивный picker в этом терминале."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    if sys.platform == "win32":
        try:
            import msvcrt  # noqa: F401
        except ImportError:
            return False
    else:
        try:
            import termios  # noqa: F401
            import tty  # noqa: F401
        except ImportError:
            return False
    return True


def _enable_windows_ansi() -> None:
    """Включает обработку ANSI escape-кодов в консоли Windows (10+)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


@contextmanager
def _raw_mode() -> Iterator[None]:
    """
    На Unix переводит stdin в raw-режим на время picker'а (посимвольный ввод
    без эха и построчной буферизации). На Windows — no-op: msvcrt.getch()
    уже читает по одному байту без буферизации сам по себе.
    """
    if sys.platform == "win32":
        yield
        return
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_key() -> str:
    """
    Читает одно "событие" клавиатуры. Возвращает: "up", "down", "space",
    "enter", "cancel" (одиночный Esc) или "other" (что угодно ещё).
    Ctrl+C/Ctrl+D пробрасывает как KeyboardInterrupt/EOFError.
    """
    if sys.platform == "win32":
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b"\r", b"\n"):
            return "enter"
        if ch == b" ":
            return "space"
        if ch == b"\x03":
            raise KeyboardInterrupt
        if ch == b"\x1b":
            return "cancel"
        if ch in (b"\xe0", b"\x00"):  # префикс расширенных клавиш (стрелки и т.п.)
            ch2 = msvcrt.getch()
            return {b"H": "up", b"P": "down"}.get(ch2, "other")
        return "other"

    import select
    fd = sys.stdin.fileno()
    ch = os.read(fd, 1).decode(errors="replace")
    if ch == "\x1b":
        # Различаем одиночный Esc (отмена) от начала последовательности
        # стрелки (Esc [ A/B) коротким неблокирующим ожиданием следующего
        # байта. os.read(fd, ...) — намеренно, а не sys.stdin.read(...):
        # буферизованный sys.stdin может затянуть в свой внутренний буфер
        # сразу все байты escape-последовательности за один системный
        # вызов, и тогда select() на самом fd честно скажет "данных нет",
        # хотя у Python они уже лежат в буфере — отсюда ложные срабатывания
        # "одиночный Esc", если читать через sys.stdin.read().
        if select.select([fd], [], [], 0.05)[0]:
            ch2 = os.read(fd, 1).decode(errors="replace")
            if ch2 == "[" and select.select([fd], [], [], 0.05)[0]:
                ch3 = os.read(fd, 1).decode(errors="replace")
                return {"A": "up", "B": "down"}.get(ch3, "other")
        return "cancel"
    if ch in ("\r", "\n"):
        return "enter"
    if ch == " ":
        return "space"
    if ch == "\x03":
        raise KeyboardInterrupt
    if ch == "\x04":
        raise EOFError
    return "other"


def _render(
    header: str,
    options: list[str],
    cursor: int,
    checked: set[int] | None,
    required_hint: str | None,
) -> list[str]:
    head = f"[YAL] {header}"
    if required_hint:
        head = f"{head}  {required_hint}"
    lines = [head]
    for i, opt in enumerate(options):
        if checked is None:
            marker = "●" if i == cursor else "○"
            lines.append(f"  {marker} {opt}")
        else:
            box = "■" if i in checked else "□"
            pointer = "›" if i == cursor else " "
            line = f" {pointer}{box} {opt}"
            if i == cursor:
                line = f"\x1b[1m{line}\x1b[0m"
            lines.append(line)
    return lines


def _abort(line_count: int) -> NoReturn:
    sys.stdout.write(f"\x1b[{line_count}A\x1b[0J{_CURSOR_SHOW}")
    sys.stdout.flush()
    raise RuntimeError(t("errors.cancelled", action=t("create.action")))


def pick(
    header: str,
    options: list[str],
    *,
    multi: bool = False,
    initial_index: int = 0,
    initial_checked: set[int] | None = None,
    required: bool = False,
) -> list[int]:
    """
    Запускает интерактивный picker. Возвращает список выбранных индексов
    (для multi=False — список из ровно одного элемента).

    Вызывающий код должен сам убедиться, что is_interactive() вернул True
    и что options непустой, прежде чем звать pick().
    """
    if not options:
        raise ValueError("pick() requires a non-empty options list")

    _enable_windows_ansi()

    cursor = max(0, min(initial_index, len(options) - 1))
    checked: set[int] = set(initial_checked or ())
    hint_key = "config.field-picker-hint-multi" if multi else "config.field-picker-hint-single"
    hint = t(hint_key)
    full_header = f"{header}  {hint}"

    def _required_hint() -> str | None:
        if multi and required and not checked:
            return t("config.field-required-hint")
        return None

    lines = _render(full_header, options, cursor, checked if multi else None, _required_hint())
    sys.stdout.write(_CURSOR_HIDE + "\n".join(lines) + "\n")
    sys.stdout.flush()

    with _raw_mode():
        while True:
            try:
                key = _read_key()
            except (KeyboardInterrupt, EOFError):
                _abort(len(lines))

            if key == "cancel":
                _abort(len(lines))

            changed = False
            if key == "up":
                cursor = (cursor - 1) % len(options)
                changed = True
            elif key == "down":
                cursor = (cursor + 1) % len(options)
                changed = True
            elif key == "space" and multi:
                checked ^= {cursor}
                changed = True
            elif key == "enter":
                if multi and required and not checked:
                    pass  # игнорируем — хинт уже виден на экране
                else:
                    break

            if changed:
                new_lines = _render(full_header, options, cursor, checked if multi else None, _required_hint())
                sys.stdout.write(f"\x1b[{len(lines)}A")
                for line in new_lines:
                    sys.stdout.write("\r\x1b[2K" + line + "\n")
                lines = new_lines
                sys.stdout.flush()

    chosen = sorted(checked) if multi else [cursor]
    sys.stdout.write(f"\x1b[{len(lines)}A\x1b[0J")
    summary = ", ".join(options[i] for i in chosen) if chosen else "—"
    sys.stdout.write(f"[YAL] {header}: {summary}\n{_CURSOR_SHOW}")
    sys.stdout.flush()
    return chosen
