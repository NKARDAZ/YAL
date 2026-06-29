"""
Интерактивный выбор из списка стрелками — как checkbox/select в inquirer
с поддержкой многострочного отображения и колонок при необходимости.
"""

from __future__ import annotations

import os
import sys
import shutil
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
    Читает одно "событие" клавиатуры. Возвращает: "up", "down", "left", "right",
    "space", "enter", "cancel" (одиночный Esc) или "other" (что угодно ещё).
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
            return {b"H": "up", b"P": "down", b"K": "left", b"M": "right"}.get(ch2, "other")
        return "other"

    import select
    fd = sys.stdin.fileno()
    ch = os.read(fd, 1).decode(errors="replace")
    if ch == "\x1b":
        if select.select([fd], [], [], 0.05)[0]:
            ch2 = os.read(fd, 1).decode(errors="replace")
            if ch2 == "[" and select.select([fd], [], [], 0.05)[0]:
                ch3 = os.read(fd, 1).decode(errors="replace")
                return {"A": "up", "B": "down", "D": "left", "C": "right"}.get(ch3, "other")
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


def _get_terminal_size() -> tuple[int, int]:
    """Возвращает (width, height) терминала."""
    try:
        size = shutil.get_terminal_size()
        return size.columns, size.lines
    except Exception:
        return 80, 24


def _calculate_layout(
    options: list[str],
    term_width: int,
    term_height: int,
    header_lines: int,
    min_cols: int = 1,  # <-- НОВЫЙ ПАРАМЕТР
) -> tuple[int, int, int]:
    """
    Рассчитывает оптимальную раскладку для списка опций.
    Возвращает (cols, rows, max_item_width) где:
    - cols: количество колонок
    - rows: количество строк
    - max_item_width: максимальная ширина одного пункта
    """
    # Минимальная ширина для пункта (плюс маркер и отступы)
    min_item_width = 4  # "  ● " или " ›■ "

    # Сначала считаем максимальную длину текста
    max_text_len = max((len(opt) for opt in options), default=0)
    max_item_width = max(min_item_width, max_text_len + 4)  # + отступы

    # Вычисляем максимальное количество строк, доступное для списка
    max_rows = term_height - header_lines - 2  # -2 для запаса

    # Определяем, сколько колонок помещается по ширине
    max_cols_by_width = max(1, (term_width - 2) // max_item_width)

    # Если список помещается в одну колонку без прокрутки - так и оставляем
    # НО только если min_cols = 1
    if min_cols <= 1 and len(options) <= max_rows:
        return 1, len(options), max_item_width

    # Начинаем с min_cols, если он больше 1
    start_cols = max(2, min_cols)

    # Пытаемся распределить по колонкам, начиная с min_cols
    for cols in range(start_cols, max_cols_by_width + 1):
        rows = (len(options) + cols - 1) // cols
        if rows <= max_rows:
            return cols, rows, max_item_width

    # Если не влезает даже в максимальное количество колонок,
    # используем максимальное количество колонок, но с прокруткой
    cols = max_cols_by_width
    rows = (len(options) + cols - 1) // cols
    return cols, rows, max_item_width


def _format_item(
    idx: int,
    opt: str,
    cursor: int,
    checked: set[int] | None,
    width: int,
) -> str:
    """Форматирует один пункт с фиксированной шириной."""
    if checked is None:
        marker = "●" if idx == cursor else "○"
        prefix = "  "
        item = f"{prefix}{marker} {opt}"
    else:
        box = "■" if idx in checked else "□"
        pointer = "›" if idx == cursor else " "
        item = f" {pointer}{box} {opt}"
        if idx == cursor:
            # ANSI-коды не должны влиять на ширину
            item = f"\x1b[1m{item}\x1b[0m"

    # Выравниваем с учетом того, что ANSI-коды не влияют на видимую ширину
    visible_len = len(item.replace("\x1b[1m", "").replace("\x1b[0m", ""))
    if visible_len < width:
        item = item + " " * (width - visible_len)
    return item


def _render_grid(
    header: str,
    options: list[str],
    cursor: int,
    checked: set[int] | None,
    required_hint: str | None,
    cols: int,
    rows: int,
    max_item_width: int,
) -> tuple[list[str], int]:
    """
    Рендерит сетку опций с колонками.
    Возвращает (строки для вывода, количество строк для прокрутки).
    """
    head = f"[YAL] {header}"
    if required_hint:
        head = f"{head}  {required_hint}"
    lines = [head]

    for row in range(rows):
        line_parts = []
        for col in range(cols):
            idx = col * rows + row
            if idx < len(options):
                item = _format_item(idx, options[idx], cursor, checked, max_item_width)
                line_parts.append(item)
            else:
                line_parts.append(" " * max_item_width)
        lines.append("".join(line_parts))

    return lines, len(lines) - 1  # возвращаем только строки с пунктами


def _render_list(
    header: str,
    options: list[str],
    cursor: int,
    checked: set[int] | None,
    required_hint: str | None,
    start_line: int,
    visible_rows: int,
) -> tuple[list[str], int, int]:
    """
    Рендерит список с прокруткой.
    Возвращает (строки, новый курсор, видимые строки).
    """
    head = f"[YAL] {header}"
    if required_hint:
        head = f"{head}  {required_hint}"
    lines = [head]

    end = min(start_line + visible_rows, len(options))

    for i in range(start_line, end):
        opt = options[i]
        if checked is None:
            marker = "●" if i == cursor else "○"
            line = f"  {marker} {opt}"
            if i == cursor:
                line = f"\x1b[1m{line}\x1b[0m"
        else:
            box = "■" if i in checked else "□"
            pointer = "›" if i == cursor else " "
            line = f" {pointer}{box} {opt}"
            if i == cursor:
                line = f"\x1b[1m{line}\x1b[0m"
        lines.append(line)

    return lines, start_line, len(lines) - 1


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
    min_cols: int = 1,
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

    term_width, term_height = _get_terminal_size()

    hint_key = "config.field-picker-hint-multi" if multi else "config.field-picker-hint-single"
    hint = t(hint_key)
    full_header = f"{header}  {hint}"
    header_lines = 1

    cols, rows, max_item_width = _calculate_layout(
        options, term_width, term_height, header_lines, min_cols
    )

    start_line = 0
    total_visible = min(len(options), term_height - header_lines - 2)

    def _required_hint() -> str | None:
        if multi and required and not checked:
            return t("config.field-required-hint")
        return None

    # Первоначальный рендер
    if cols == 1 and len(options) > rows:
        lines, start_line, visible_rows = _render_list(
            full_header, options, cursor, checked if multi else None,
            _required_hint(), start_line, total_visible
        )
    else:
        lines, visible_rows = _render_grid(
            full_header, options, cursor, checked if multi else None,
            _required_hint(), cols, rows, max_item_width
        )

    sys.stdout.write(_CURSOR_HIDE + "\n".join(lines) + "\n")
    sys.stdout.flush()
    line_count = len(lines)

    with _raw_mode():
        while True:
            try:
                key = _read_key()
            except (KeyboardInterrupt, EOFError):
                _abort(line_count)

            if key == "cancel":
                _abort(line_count)

            changed = False
            old_cursor = cursor

            if key == "up":
                # Вверх/вниз - навигация по строкам (вертикально)
                if cols == 1:
                    # В одну колонку - просто предыдущий/следующий
                    cursor = (cursor - 1) % len(options)
                else:
                    # В сетке - переходим на ту же колонку, но строкой выше
                    col = cursor // rows
                    row = cursor % rows
                    row = (row - 1) % rows
                    cursor = col * rows + row
                changed = True
            elif key == "down":
                if cols == 1:
                    cursor = (cursor + 1) % len(options)
                else:
                    col = cursor // rows
                    row = cursor % rows
                    row = (row + 1) % rows
                    cursor = col * rows + row
                changed = True
            elif key == "left":
                # Влево/вправо - навигация по колонкам (горизонтально)
                if cols > 1:
                    col = cursor // rows
                    row = cursor % rows
                    col = (col - 1) % cols
                    new_idx = col * rows + row
                    if new_idx < len(options):
                        cursor = new_idx
                    else:
                        # Если в этой колонке нет элемента на этой строке,
                        # переходим на предыдущую строку
                        row = (row - 1) % rows
                        cursor = col * rows + row
                    changed = True
            elif key == "right":
                if cols > 1:
                    col = cursor // rows
                    row = cursor % rows
                    col = (col + 1) % cols
                    new_idx = col * rows + row
                    if new_idx < len(options):
                        cursor = new_idx
                    else:
                        # Если в этой колонке нет элемента на этой строке,
                        # переходим на следующую строку (если есть)
                        row = (row + 1) % rows
                        cursor = col * rows + row
                    changed = True
            elif key == "space" and multi:
                checked ^= {cursor}
                changed = True
            elif key == "enter":
                if multi and required and not checked:
                    pass
                else:
                    break

            if changed:
                term_width, term_height = _get_terminal_size()
                total_visible = min(len(options), term_height - header_lines - 2)

                cols, rows, max_item_width = _calculate_layout(
                    options, term_width, term_height, header_lines, min_cols
                )

                if cols == 1 and len(options) > rows:
                    if cursor < start_line:
                        start_line = cursor
                    elif cursor >= start_line + total_visible:
                        start_line = cursor - total_visible + 1

                    new_lines, start_line, visible_rows = _render_list(
                        full_header, options, cursor, checked if multi else None,
                        _required_hint(), start_line, total_visible
                    )
                else:
                    new_lines, visible_rows = _render_grid(
                        full_header, options, cursor, checked if multi else None,
                        _required_hint(), cols, rows, max_item_width
                    )

                sys.stdout.write(f"\x1b[{line_count}A")
                for line in new_lines:
                    sys.stdout.write("\r\x1b[2K" + line + "\n")
                for _ in range(line_count - len(new_lines)):
                    sys.stdout.write("\r\x1b[2K\n")
                lines = new_lines
                line_count = len(lines)
                sys.stdout.flush()

    chosen = sorted(checked) if multi else [cursor]
    sys.stdout.write(f"\x1b[{line_count}A\x1b[0J")
    summary = ", ".join(options[i] for i in chosen) if chosen else "—"
    sys.stdout.write(f"[YAL] {header}: {summary}\n{_CURSOR_SHOW}")
    sys.stdout.flush()
    return chosen
