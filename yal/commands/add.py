"""
Команда: yal add <kind>:<name>[@<ref>] from <repo-spec>

Регистрирует внешний шаблон и скачивает его.

Поддерживаемые форматы <repo-spec>:
  user/repo                           → GitHub (как раньше)
  github:user/repo                    → GitHub явно
  gitlab:user/repo                    → GitLab.com
  gitlab:host.example.com:user/repo   → self-hosted GitLab
  codeberg:user/repo                  → Codeberg
  bitbucket:user/repo                 → Bitbucket
  git.gay:user/repo                   → git.gay
  gitverse:user/repo                  → gitverse.ru
  sourceforge:project/repo            → SourceForge (анонимный git://)
  sourceforge:user@project/repo       → SourceForge (ssh://)
  https://...                         → произвольный URL
  git://...  /  ssh://...             → произвольный URL

Примеры:
  yal add book:mytheme@0.4.1 from https://github.com/user/my-book-template
  yal add note:work from gitlab:mygroup/note-tpl
  yal add doc:corp from gitlab:git.corp.example.com:team/doc-template
  yal add book:sf from sourceforge:nkardaz@myproject/book
"""

from __future__ import annotations

import argparse
import sys
import re

from yal import user_store
from yal.git_provider import (
    expand_repo_shortcut,
    validate_repo_url,
    get_releases,
    get_latest_commit,
    get_commit,
    download_release,
    clone_repo,
    ReleaseInfo,
    _force_remove_readonly,
)
from yal.i18n import t, yes_variants
from yal.templates.registry import TemplateEntry
from yal.templates import user_registry


def run(args: argparse.Namespace) -> None:
    kind, name, ref, repo = _parse_spec(args.what, args.from_kw, args.repo)

    # Проверяем, не зарегистрирован ли уже
    existing = user_registry.get_entry(kind, name)
    if existing is not None and existing.repo == repo:
        if ref is None:
            print(f"[YAL] {t('add.already-registered', kind=kind, name=name)}")
            sys.exit(0)
        exclude = existing.exclude
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
        exclude = None
    else:
        exclude = None

    entry = TemplateEntry(repo=repo, exclude=[])

    try:
        version = _download(entry, kind, name, ref)
    except (ValueError, RuntimeError) as e:
        print(f"[YAL] {t('create.error', error=e)}")
        sys.exit(1)

    if exclude is None:
        exclude = _ask_excludes()

    user_registry.add_entry(kind, name, repo, exclude)

    dest = user_store.user_template_dir(kind, name, version)
    print(f"[YAL] {t('add.registered', kind=kind, name=name, path=dest)}")


# ─── скачивание ───────────────────────────────────────────────────────────────

def _fetch_releases_safe(repo: str) -> list[ReleaseInfo]:
    try:
        return get_releases(repo)
    except Exception as e:
        print(f"[YAL] {t('errors.no-releases-warn', error=e)}")
        return []


def _download(entry: TemplateEntry, kind: str, name: str, ref: str | None) -> str:
    releases = _fetch_releases_safe(entry.repo)
    if releases:
        return _download_release(entry, kind, name, ref, releases)
    else:
        return _download_commit(entry, kind, name, ref)


def _download_release(
    entry: TemplateEntry, kind: str, name: str, ref: str | None, releases: list[ReleaseInfo]
) -> str:
    if ref is None or ref == "latest":
        target = releases[0]
        version = target.tag.lstrip("vV")
    else:
        target = next((r for r in releases if r.tag in (ref, f"v{ref}")), None)
        if target is None:
            return _download_commit(entry, kind, name, ref)
        version = target.tag.lstrip("vV")

    if user_store.user_is_installed(kind, name, version):
        print(f"[YAL] {t('create.using-local', version=version)}")
        return version

    if not _confirm_download(kind, name, version, t("download.release"), entry.repo):
        raise RuntimeError(t("errors.cancelled", action=t("add.action")))

    dest = user_store.user_template_dir(kind, name, version)
    print(f"[YAL] {t('download.release-downloading', tag=target.tag)}")
    download_release(target, dest)
    user_store.user_save_meta(kind, name, version, "release", entry.repo, target.released_at)
    print(f"[YAL] {t('download.done', path=dest)}")
    return version


def _download_commit(entry: TemplateEntry, kind: str, name: str, ref: str | None) -> str:
    print(f"[YAL] {t('update.no-releases')}")
    try:
        info = (
            get_latest_commit(entry.repo)
            if (ref is None or ref == "latest")
            else get_commit(entry.repo, ref)
        )
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
        clone_repo(entry.repo, dest, ref=info.sha)
    except Exception:
        if dest.exists():
            import shutil as _shutil
            _shutil.rmtree(dest, onexc=_force_remove_readonly)
        raise
    user_store.user_save_meta(kind, name, version, "commit", entry.repo, info.released_at)
    print(f"[YAL] {t('download.done', path=dest)}")
    return version


# ─── диалог исключений ────────────────────────────────────────────────────────

def _ask_excludes() -> list[str]:
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

def _confirm_download(kind, name, version, source_type, repo) -> bool:
    msg = t("download.confirm-user", kind=kind, name=name, source_type=source_type, version=version, repo=repo)
    print(f"[YAL]{msg}", end="")
    print(t("common.confirm-prompt"), end="", flush=True)
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in yes_variants()


def _parse_spec(what: str, from_kw: str | None, repo_spec: str | None) -> tuple[str, str, str | None, str]:
    """
    Разбирает <kind>:<name>[@<ref>] и необязательный <repo-spec>.

    repo-spec может быть:
      — Полным URL (https://, git://, ssh://)
      — Сокращением (user/repo, gitlab:user/repo, ...)
      — Путь к локальному git-репозиторию
    """
    # Парсим what
    pattern = r"^(?P<kind>[^:@]+):(?P<name>[^@]+)(?:@(?P<ref>.+))?$"
    m = re.match(pattern, what.strip())
    if not m:
        print(f"[YAL] {t('errors.parse-spec', spec=what)}")
        sys.exit(1)

    kind = m.group("kind").lower()
    name = m.group("name")
    ref = m.group("ref") or None

    if from_kw is None and repo_spec is None:
        existing = user_registry.get_entry(kind, name)
        if existing is None:
            print(f"[YAL] {t('add.repo-required', kind=kind, name=name)}")
            sys.exit(1)
        return kind, name, ref, existing.repo

    if from_kw is None or repo_spec is None:
        print(f"[YAL] {t('add.invalid-from')}")
        sys.exit(1)

    if from_kw.lower() != "from":
        print(f"[YAL] {t('add.invalid-from-keyword', keyword=from_kw)}")
        sys.exit(1)

    try:
        repo = expand_repo_shortcut(repo_spec.strip())
        validate_repo_url(repo)
    except ValueError as e:
        print(f"[YAL] {t('add.invalid-repo', repo=repo_spec)}\n      {e}")
        sys.exit(1)

    return kind, name, ref, repo
