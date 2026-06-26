"""
Команда: yal update <kind>[:<name>]

Примеры:
  yal update book
  yal update book:default
  yal update book:mytheme
  yal update my-kind:default
"""

from __future__ import annotations

import argparse
import re
import sys

from yal import git_provider
from yal.i18n import t
from yal.templates.handler import _fetch_releases_safe
from yal.templates.handler_def import get_handler, known_kinds
from yal.templates.registry import get_entry


def run(args: argparse.Namespace) -> None:
    kind, name = _parse_spec(args.what)

    try:
        entry = get_entry(kind, name)
    except ValueError as e:
        print(f"[YAL] {e}")
        sys.exit(1)

    handler = get_handler(kind, entry)
    if handler is None:
        print(f"[YAL] {t('errors.unknown-kind', kind=kind, available=', '.join(known_kinds()))}")
        sys.exit(1)

    try:
        _update(kind, name, entry, handler, force_commit=getattr(args, "commit", False))
    except (ValueError, RuntimeError) as e:
        print(f"[YAL] {t('create.error', error=e)}")
        sys.exit(1)


def _update(kind, name, entry, handler, force_commit: bool = False) -> None:
    if force_commit:
        _update_commit(kind, name, entry, handler)
        return
    releases = _fetch_releases_safe(entry.repo)
    if releases:
        _update_release(kind, name, entry, handler, releases)
    else:
        _update_commit(kind, name, entry, handler)


def _update_release(kind, name, entry, handler, releases) -> None:
    latest = releases[0]
    version = latest.tag.lstrip("vV")

    if handler._is_installed(entry, name, version):
        print(f"[YAL] {t('update.already-latest', version=version)}")
        return

    local = handler._get_most_recent_local(entry, name)
    if local:
        print(f"[YAL] {t('update.upgrading', kind=kind, name=name, old=local, new=version)}")
    else:
        print(f"[YAL] {t('update.installing', kind=kind, name=name, version=version)}")

    if not handler.confirm_download(name, version, t("download.release"), entry.repo, entry.is_user):
        raise RuntimeError(t("errors.cancelled", action=t("update.action")))

    dest = handler._template_dir(entry, name, version)
    print(f"[YAL] {t('download.release-downloading', tag=latest.tag)}")
    git_provider.download_release(latest, dest)
    handler._save_meta(entry, name, version, "release", latest.released_at)
    print(f"[YAL] {t('update.installed', path=dest)}")


def _update_commit(kind, name, entry, handler) -> None:
    try:
        info = git_provider.get_latest_commit(entry.repo)
    except Exception as e:
        raise RuntimeError(t("update.commit-fail", error=e)) from e

    version = info.sha7

    if handler._is_installed(entry, name, version):
        print(f"[YAL] {t('update.already-latest-commit', version=version)}")
        return

    local_versions = handler._installed_versions(entry, name)
    if local_versions:
        print(f"[YAL] {t('update.upgrading-commit', kind=kind, name=name, old=local_versions[-1], new=version)}")
    else:
        print(f"[YAL] {t('update.installing-commit', kind=kind, name=name, version=version)}")

    if not handler.confirm_download(name, version, t("download.commit"), entry.repo, entry.is_user):
        raise RuntimeError(t("errors.cancelled", action=t("update.action")))

    dest = handler._template_dir(entry, name, version)
    print(f"[YAL] {t('download.commit-cloning', version=version)}")
    git_provider.clone_repo(entry.repo, dest, ref=info.sha)
    handler._save_meta(entry, name, version, "commit", info.released_at)
    print(f"[YAL] {t('update.installed', path=dest)}")


def _parse_spec(spec: str) -> tuple[str, str]:
    m = re.match(r"^(?P<kind>[^:@]+)(?::(?P<name>[^@]+))?$", spec.strip())
    if not m:
        print(f"[YAL] {t('errors.parse-spec', spec=spec)}")
        print(f"      {t('errors.parse-spec-hint', fmt='<kind>[:<name>]')}")
        sys.exit(1)

    kind = m.group("kind").lower()
    name = m.group("name") or "default"
    return kind, name
