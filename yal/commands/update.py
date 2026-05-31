"""
Команда: yal update <kind>[:<name>]

Примеры:
  yal update book
  yal update book:default
  yal update book:mytheme
"""

from __future__ import annotations

import argparse
import re
import sys

from yal import github, store, user_store
from yal.i18n import t
from yal.templates.book_handler import BookHandler, _confirm_download, _fetch_releases_safe
from yal.templates.registry import TemplateEntry, get_entry, list_kinds

_HANDLERS = {
    "book": BookHandler(),
}


def run(args: argparse.Namespace) -> None:
    kind, name = _parse_spec(args.what)

    if kind not in _HANDLERS:
        print(f"[YAL] {t('errors.unknown-kind', kind=kind, available=', '.join(list_kinds()))}")
        sys.exit(1)

    try:
        entry = get_entry(kind, name)
    except ValueError as e:
        print(f"[YAL] {e}")
        sys.exit(1)

    try:
        _update(kind, name, entry)
    except (ValueError, RuntimeError) as e:
        print(f"[YAL] {t('create.error', error=e)}")
        sys.exit(1)


def _update(kind: str, name: str, entry: TemplateEntry) -> None:
    releases = _fetch_releases_safe(entry.repo)
    if releases:
        _update_release(kind, name, entry, releases)
    else:
        _update_commit(kind, name, entry)


def _update_release(
    kind: str,
    name: str,
    entry: TemplateEntry,
    releases: list[github.ReleaseInfo],
) -> None:
    latest = releases[0]
    version = latest.tag.lstrip("vV")

    if _is_installed(entry, kind, name, version):
        print(f"[YAL] {t('update.already-latest', version=version)}")
        return

    local = _latest_release_version(entry, kind, name)
    if local:
        print(f"[YAL] {t('update.upgrading', kind=kind, name=name, old=local, new=version)}")
    else:
        print(f"[YAL] {t('update.installing', kind=kind, name=name, version=version)}")

    if not _confirm_download(kind, name, version, t("download.release"), entry.repo, entry.is_user):
        raise RuntimeError(t("errors.cancelled", action=t("update.action")))

    dest = _template_dir(entry, kind, name, version)
    print(f"[YAL] {t('download.release-downloading', tag=latest.tag)}")
    github.download_release(latest, dest)
    _save_meta(entry, kind, name, version, "release")
    print(f"[YAL] {t('update.installed', path=dest)}")


def _update_commit(kind: str, name: str, entry: TemplateEntry) -> None:
    try:
        info = github.get_latest_commit(entry.repo)
    except Exception as e:
        raise RuntimeError(t("update.commit-fail", error=e)) from e

    version = info.sha7

    if _is_installed(entry, kind, name, version):
        print(f"[YAL] {t('update.already-latest-commit', version=version)}")
        return

    local_versions = _installed_versions(entry, kind, name)
    if local_versions:
        print(f"[YAL] {t('update.upgrading-commit', kind=kind, name=name, old=local_versions[-1], new=version)}")
    else:
        print(f"[YAL] {t('update.installing-commit', kind=kind, name=name, version=version)}")

    if not _confirm_download(kind, name, version, t("download.commit"), entry.repo, entry.is_user):
        raise RuntimeError(t("errors.cancelled", action=t("update.action")))

    dest = _template_dir(entry, kind, name, version)
    print(f"[YAL] {t('download.commit-cloning', version=version)}")
    github.clone_repo(entry.repo, dest, ref=info.sha)
    _save_meta(entry, kind, name, version, "commit")
    print(f"[YAL] {t('update.installed', path=dest)}")


# ── диспетчеры хранилища ──────────────────────────────────────────────────────

def _template_dir(entry: TemplateEntry, kind: str, name: str, version: str):
    if entry.is_user:
        return user_store.user_template_dir(kind, name, version)
    return store.template_dir(kind, name, version)


def _is_installed(entry: TemplateEntry, kind: str, name: str, version: str) -> bool:
    if entry.is_user:
        return user_store.user_is_installed(kind, name, version)
    return store.is_installed(kind, name, version)


def _latest_release_version(entry: TemplateEntry, kind: str, name: str) -> str | None:
    if entry.is_user:
        return user_store.user_latest_release_version(kind, name)
    return store.latest_release_version(kind, name)


def _installed_versions(entry: TemplateEntry, kind: str, name: str) -> list[str]:
    if entry.is_user:
        return user_store.user_installed_versions(kind, name)
    return store.installed_versions(kind, name)


def _save_meta(
    entry: TemplateEntry,
    kind: str,
    name: str,
    version: str,
    source: str,
) -> None:
    if entry.is_user:
        user_store.user_save_meta(kind, name, version, source, entry.repo)  # type: ignore[arg-type]
    else:
        store.save_meta(kind, name, version, source, entry.repo)  # type: ignore[arg-type]


def _parse_spec(spec: str) -> tuple[str, str]:
    m = re.match(r"^(?P<kind>[^:@]+)(?::(?P<name>[^@]+))?$", spec.strip())
    if not m:
        print(f"[YAL] {t('errors.parse-spec', spec=spec)}")
        print(f"      {t('errors.parse-spec-hint', fmt='<kind>[:<name>]')}")
        sys.exit(1)

    kind = m.group("kind").lower()
    name = m.group("name") or "default"   # регистр сохраняем как есть
    return kind, name
