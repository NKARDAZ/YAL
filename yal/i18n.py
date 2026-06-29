"""
Локализация утилиты yal.

Определяет язык из системной локали и загружает соответствующий
TOML-файл из yal/locales/.

Использование:
    from yal.i18n import t
    print(t("errors.unknown-kind", kind="book", available="book, note"))
"""

from __future__ import annotations

import locale
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

_LOCALES_DIR = Path(__file__).parent / "locales"
_FALLBACK_LANG = "en"

# Кэш загруженных данных
_data: dict[str, Any] = {}
_lang: str = ""


def _detect_lang() -> str:
    """Определяет язык из системной локали."""
    try:
        # Windows: getlocale() возвращает ('Russian_Russia', '1251') и подобное
        loc = locale.getlocale()[0] or ""
        if loc:
            # берём первые два символа: 'ru_RU' → 'ru', 'Russian_Russia' → 'ru'
            tag = loc.lower()
            if tag.startswith("ru"):
                return "ru"
            # добавлять другие языки здесь по мере появления локалей
        return _FALLBACK_LANG
    except Exception:
        return _FALLBACK_LANG


def _load(lang: str) -> dict[str, Any]:
    path = _LOCALES_DIR / f"{lang}.toml"
    if not path.exists():
        if lang != _FALLBACK_LANG:
            return _load(_FALLBACK_LANG)
        raise FileNotFoundError(f"Locale file not found: {path}")
    with open(path, "rb") as f:
        return tomllib.load(f)


def _ensure_loaded() -> None:
    global _data, _lang
    if not _data:
        _lang = _detect_lang()
        _data = _load(_lang)


def t(key: str, **kwargs: Any) -> str:
    """
    Получить локализованную строку по точечному ключу и подставить параметры.

    t("errors.unknown-kind", kind="book", available="book, note")
    → "Неизвестный тип: 'book'. Доступные: book, note"
    """
    _ensure_loaded()
    parts = key.split(".")
    node: Any = _data
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return key  # возвращаем ключ как fallback
        node = node[part]

    if not isinstance(node, str):
        return key

    try:
        return node.format(**kwargs)
    except KeyError:
        return node


def current_lang() -> str:
    _ensure_loaded()
    return _lang


def yes_variants() -> list[str]:
    _ensure_loaded()
    v = _data.get("common", {}).get("yes-variants", ["y", "yes", "j", "ja", "д", "да", "d", "da", "はい", "是", "是的"])
    return [s.lower() for s in v]
