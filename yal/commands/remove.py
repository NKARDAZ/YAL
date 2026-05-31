"""
Команда: yal remove <kind>[:<name>[@<version>]]

Удаляет скачанные шаблоны из локального хранилища.

Примеры:
  yal remove book               — удалить все версии всех шаблонов типа book
  yal remove book:default       — удалить все версии шаблона book:default
  yal remove book:default@1.7.1 — удалить конкретную версию
  yal remove book:cJSON         — удалить все версии пользовательского шаблона
  yal remove book:cJSON@2.1.0   — удалить конкретную версию

После удаления всех версий пользовательского шаблона запись о нём
удаляется и из ~/.yal/user-templates.toml.
"""

from __future__ import annotations

import argparse
import re
import sys

from yal import store, user_store
from yal.i18n import t, yes_variants
from yal.templates import user_registry
from yal.templates.registry import KIND_REGISTRIES, get_entry


def run(args: argparse.Namespace) -> None:
    kind, name, version = _parse_spec(args.what)

    # Собираем всё, что будет удалено, и показываем пользователю
    targets = _collect_targets(kind, name, version)

    if not targets:
        print(f"[YAL] {t('remove.nothing-found')}")
        sys.exit(0)

    _print_targets(targets)

    print(f"[YAL] {t('remove.confirm')}", end="")
    print(t("common.confirm-prompt"), end="", flush=True)
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)

    if answer not in yes_variants():
        print(f"[YAL] {t('errors.cancelled', action=t('remove.action'))}")
        sys.exit(0)

    _do_remove(targets)
    print(f"[YAL] {t('remove.done', count=len(targets))}")


# ─── сбор целей ───────────────────────────────────────────────────────────────

class RemoveTarget:
    """Одна версия шаблона, подлежащая удалению."""
    def __init__(self, kind: str, name: str, version: str, is_user: bool) -> None:
        self.kind = kind
        self.name = name
        self.version = version
        self.is_user = is_user

    def __str__(self) -> str:
        source = t("remove.source-user") if self.is_user else t("remove.source-builtin")
        return f"  {self.kind}:{self.name}@{self.version}  [{source}]"


def _collect_targets(
    kind: str,
    name: str | None,
    version: str | None,
) -> list[RemoveTarget]:
    """
    Собирает список версий для удаления по заданным фильтрам.
    Смотрит в оба хранилища (store и user_store).
    """
    targets: list[RemoveTarget] = []

    # Определяем имена для обхода
    if name is None:
        # yal remove book — все шаблоны этого kind
        builtin_names = list(KIND_REGISTRIES.get(kind, {}).keys())
        user_names = user_registry.list_names(kind)
        names_builtin = [(n, False) for n in builtin_names]
        names_user = [(n, True) for n in user_names]
        all_names = names_builtin + names_user
    else:
        # Определяем is_user по реестру
        is_user = _resolve_is_user(kind, name)
        all_names = [(name, is_user)]

    for n, is_user in all_names:
        if version is not None:
            # Конкретная версия
            if _version_exists(kind, n, version, is_user):
                targets.append(RemoveTarget(kind, n, version, is_user))
        else:
            # Все версии
            versions = _installed_versions(kind, n, is_user)
            for v in versions:
                targets.append(RemoveTarget(kind, n, v, is_user))

    return targets


def _resolve_is_user(kind: str, name: str) -> bool:
    """True если шаблон пользовательский, False если встроенный."""
    try:
        entry = get_entry(kind, name)
        return entry.is_user
    except ValueError:
        # Не найден ни там ни там — возможно уже частично удалён,
        # попробуем найти хоть где-нибудь на диске
        if user_store.user_installed_versions(kind, name):
            return True
        return False


def _version_exists(kind: str, name: str, version: str, is_user: bool) -> bool:
    if is_user:
        return user_store.user_is_installed(kind, name, version)
    return store.is_installed(kind, name, version)


def _installed_versions(kind: str, name: str, is_user: bool) -> list[str]:
    if is_user:
        return user_store.user_installed_versions(kind, name)
    return store.installed_versions(kind, name)


# ─── вывод и удаление ────────────────────────────────────────────────────────

def _print_targets(targets: list[RemoveTarget]) -> None:
    print(f"[YAL] {t('remove.will-remove')}:")
    for tgt in targets:
        print(str(tgt))


def _do_remove(targets: list[RemoveTarget]) -> None:
    removed_user: set[tuple[str, str]] = set()  # (kind, name) — для очистки реестра

    for tgt in targets:
        if tgt.is_user:
            user_store.user_remove(tgt.kind, tgt.name, tgt.version)
            removed_user.add((tgt.kind, tgt.name))
        else:
            store.remove(tgt.kind, tgt.name, tgt.version)

    # Если у пользовательского шаблона не осталось версий — убираем из реестра
    for kind, name in removed_user:
        if not user_store.user_installed_versions(kind, name):
            user_registry.remove_entry(kind, name)


# ─── парсинг спецификации ─────────────────────────────────────────────────────

def _parse_spec(spec: str) -> tuple[str, str | None, str | None]:
    """
    Разбирает:
      book               → (book, None, None)
      book:default       → (book, default, None)
      book:default@1.7.1 → (book, default, 1.7.1)
      book:cJSON@2.1.0   → (book, cJSON, 2.1.0)
    """
    pattern = r"^(?P<kind>[^:@]+)(?::(?P<name>[^@]+))?(?:@(?P<version>.+))?$"
    m = re.match(pattern, spec.strip())
    if not m:
        print(f"[YAL] {t('errors.parse-spec', spec=spec)}")
        print(f"      {t('errors.parse-spec-hint', fmt='<kind>[:<name>[@<version>]]')}")
        sys.exit(1)

    kind = m.group("kind").lower()
    name = m.group("name") or None       # регистр сохраняем
    version = m.group("version") or None

    if version is not None and name is None:
        # book@1.7.1 — синтаксис версии без имени не поддерживаем
        print(f"[YAL] {t('errors.parse-spec', spec=spec)}")
        print(f"      {t('errors.parse-spec-hint', fmt='<kind>[:<name>[@<version>]]')}")
        sys.exit(1)

    return kind, name, version
