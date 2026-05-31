"""
Команда: yal add <kind>:<name> from <repository URL>

Регистрирует внешний шаблон из GitHub и скачивает его в
~/.yal/user-templates/<kind>/<name>/<version>/.

Примеры:
  yal add book:mytheme from https://github.com/user/my-book-template
  yal add note:work from https://github.com/org/note-tpl
"""

from __future__ import annotations

import argparse
import sys

from yal import github, user_store
from yal.i18n import t, yes_variants
from yal.templates.registry import TemplateEntry
from yal.templates import user_registry


def run(args: argparse.Namespace) -> None:
    kind, name, repo = _parse_spec(args.what, args.repo)

    # Проверяем, не зарегистрирован ли уже
    existing = user_registry.get_entry(kind, name)
    if existing is not None and existing.repo == repo:
        print(f"[YAL] {t('add.already-registered', kind=kind, name=name)}")
        # Всё равно предлагаем скачать свежую версию
    elif existing is not None:
        print(f"[YAL] {t('add.name-conflict', kind=kind, name=name, old_repo=existing.repo)}")
        print(t("common.confirm-prompt"), end="", flush=True)
        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if answer not in yes_variants():
            print(f"[YAL] {t('errors.cancelled', action=t('add.action'))}")
            sys.exit(0)

    entry = TemplateEntry(repo=repo, exclude=[])

    try:
        version = _download(entry, kind, name)
    except (ValueError, RuntimeError) as e:
        print(f"[YAL] {t('create.error', error=e)}")
        sys.exit(1)

    # Предлагаем добавить исключения
    exclude = _ask_excludes()

    # Сохраняем в реестр
    user_registry.add_entry(kind, name, repo, exclude)

    dest = user_store.user_template_dir(kind, name, version)
    print(f"[YAL] {t('add.registered', kind=kind, name=name, path=dest)}")


# ─── скачивание ───────────────────────────────────────────────────────────────


def _fetch_releases_safe(repo: str) -> list[github.ReleaseInfo]:
    try:
        return github.get_releases(repo)
    except Exception as e:
        print(f"[YAL] {t('errors.no-releases-warn', error=e)}")
        return []


def _download(entry: TemplateEntry, kind: str, name: str) -> str:
    releases = _fetch_releases_safe(entry.repo)
    if releases:
        return _download_release(entry, kind, name, releases)
    else:
        return _download_commit(entry, kind, name)


def _download_release(
    entry: TemplateEntry,
    kind: str,
    name: str,
    releases: list[github.ReleaseInfo],
) -> str:
    latest = releases[0]
    version = latest.tag.lstrip("vV")

    if user_store.user_is_installed(kind, name, version):
        print(f"[YAL] {t('create.using-local', version=version)}")
        return version

    if not _confirm_download(kind, name, version, t("download.release"), entry.repo):
        raise RuntimeError(t("errors.cancelled", action=t("add.action")))

    dest = user_store.user_template_dir(kind, name, version)
    print(f"[YAL] {t('download.release-downloading', tag=latest.tag)}")
    github.download_release(latest, dest)
    user_store.user_save_meta(kind, name, version, "release", entry.repo)
    print(f"[YAL] {t('download.done', path=dest)}")
    return version


def _download_commit(entry: TemplateEntry, kind: str, name: str) -> str:
    print(f"[YAL] {t('update.no-releases')}")

    try:
        info = github.get_latest_commit(entry.repo)
    except Exception as e:
        raise RuntimeError(t("errors.commit-info-fail", error=e)) from e

    version = info.sha7

    if user_store.user_is_installed(kind, name, version):
        print(f"[YAL] {t('create.using-local', version=version)}")
        return version

    if not _confirm_download(kind, name, version, t("download.commit"), entry.repo):
        raise RuntimeError(t("errors.cancelled", action=t("add.action")))

    dest = user_store.user_template_dir(kind, name, version)
    print(f"[YAL] {t('download.commit-cloning', version=version)}")
    try:
        github.clone_repo(entry.repo, dest, ref=info.sha)
    except Exception:
        if dest.exists():
            import shutil as _shutil
            from yal.github import _force_remove_readonly
            _shutil.rmtree(dest, onexc=_force_remove_readonly)
        raise
    user_store.user_save_meta(kind, name, version, "commit", entry.repo)
    print(f"[YAL] {t('download.done', path=dest)}")
    return version


# ─── диалог исключений ────────────────────────────────────────────────────────

def _ask_excludes() -> list[str]:
    """
    Спрашивает пользователя, хочет ли он добавить exclude-паттерны.
    Возвращает список (без yal.template.toml — он глобальный).
    """
    print(f"\n[YAL] {t('add.ask-excludes')}", end="")
    print(t("common.confirm-prompt"), end="", flush=True)
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return []

    if answer not in yes_variants():
        return []

    print(f"[YAL] {t('add.exclude-hint')}")
    excludes: list[str] = []
    while True:
        print("  > ", end="", flush=True)
        try:
            line = input().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            break
        excludes.append(line)

    if excludes:
        print(f"[YAL] {t('add.excludes-saved', items=', '.join(excludes))}")
    return excludes


# ─── утилиты ──────────────────────────────────────────────────────────────────

def _confirm_download(
    kind: str,
    name: str,
    version: str,
    source_type: str,
    repo: str,
) -> bool:
    msg = t(
        "download.confirm-user",
        kind=kind,
        name=name,
        source_type=source_type,
        version=version,
        repo=repo,
    )
    print(f"[YAL]{msg}", end="")
    print(t("common.confirm-prompt"), end="", flush=True)
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in yes_variants()


def _parse_spec(what: str, repo: str) -> tuple[str, str, str]:
    """Разбирает '<kind>:<name>' и возвращает (kind, name, repo)."""
    if ":" not in what:
        print(f"[YAL] {t('errors.parse-spec', spec=what)}")
        print(f"      {t('errors.parse-spec-hint', fmt='<kind>:<name>')}")
        sys.exit(1)

    kind, _, name = what.partition(":")
    kind = kind.strip().lower()
    name = name.strip()   # регистр сохраняем как есть

    if not kind or not name:
        print(f"[YAL] {t('errors.parse-spec', spec=what)}")
        print(f"      {t('errors.parse-spec-hint', fmt='<kind>:<name>')}")
        sys.exit(1)

    if not repo.startswith("https://github.com/"):
        print(f"[YAL] {t('add.invalid-repo', repo=repo)}")
        sys.exit(1)

    return kind, name, repo
