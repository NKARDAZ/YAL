"""
Команда: yal update <kind>[:<name>]

Примеры:
  yal update book
  yal update book:default
"""

from __future__ import annotations

import argparse
import re
import sys

from yal import github, store
from yal.i18n import t
from yal.templates.registry import get_entry, list_kinds
from yal.templates.book_handler import BookHandler, _confirm_download, _fetch_releases_safe

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
    except ValueError:
        print(f"[YAL] {t('errors.unknown-template', name=name, kind=kind, available=', '.join(list_kinds()))}")
        sys.exit(1)

    try:
        _update(kind, name, entry)
    except (ValueError, RuntimeError) as e:
        print(f"[YAL] {t('create.error', error=e)}")
        sys.exit(1)


def _update(kind: str, name: str, entry) -> None:
    releases = _fetch_releases_safe(entry.repo)
    if releases:
        _update_release(kind, name, entry, releases)
    else:
        _update_commit(kind, name, entry)


def _update_release(
    kind: str,
    name: str,
    entry,
    releases: list[github.ReleaseInfo],
) -> None:
    latest = releases[0]
    version = latest.tag.lstrip("vV")

    if store.is_installed(kind, version):
        print(f"[YAL] {t('update.already-latest', version=version)}")
        return

    local = store.latest_release_version(kind)
    if local:
        print(f"[YAL] {t('update.upgrading', kind=kind, name=name, old=local, new=version)}")
    else:
        print(f"[YAL] {t('update.installing', kind=kind, name=name, version=version)}")

    if not _confirm_download(kind, name, version, t("download.release"), entry.repo):
        raise RuntimeError(t("errors.cancelled", action=t("update.action")))

    dest = store.template_dir(kind, version)
    print(f"[YAL] {t('download.release-downloading', tag=latest.tag)}")
    github.download_release(latest, dest)
    store.save_meta(kind, version, "release", entry.repo)
    print(f"[YAL] {t('update.installed', path=dest)}")


def _update_commit(kind: str, name: str, entry) -> None:
    try:
        info = github.get_latest_commit(entry.repo)
    except Exception as e:
        raise RuntimeError(t("update.commit-fail", error=e)) from e

    version = info.sha7

    if store.is_installed(kind, version):
        print(f"[YAL] {t('update.already-latest-commit', version=version)}")
        return

    local_versions = store.installed_versions(kind)
    if local_versions:
        print(f"[YAL] {t('update.upgrading-commit', kind=kind, name=name, old=local_versions[-1], new=version)}")
    else:
        print(f"[YAL] {t('update.installing-commit', kind=kind, name=name, version=version)}")

    if not _confirm_download(kind, name, version, t("download.commit"), entry.repo):
        raise RuntimeError(t("errors.cancelled", action=t("update.action")))

    dest = store.template_dir(kind, version)
    print(f"[YAL] {t('download.commit-cloning', version=version)}")
    github.clone_repo(entry.repo, dest, ref=info.sha)
    store.save_meta(kind, version, "commit", entry.repo)
    print(f"[YAL] {t('update.installed', path=dest)}")


def _parse_spec(spec: str) -> tuple[str, str]:
    m = re.match(r"^(?P<kind>[^:@]+)(?::(?P<name>[^@]+))?$", spec.strip())
    if not m:
        print(f"[YAL] {t('errors.parse-spec', spec=spec)}")
        print(f"      {t('errors.parse-spec-hint', fmt='<kind>[:<name>]')}")
        sys.exit(1)

    kind = m.group("kind").lower()
    name = (m.group("name") or "default").lower()
    return kind, name
