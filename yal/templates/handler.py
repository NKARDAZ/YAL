"""
Универсальный обработчик шаблонов GenericHandler.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal, cast

from yal import github, store, user_store
from yal.i18n import t, yes_variants
from yal.templates.registry import TemplateEntry

# Определяем допустимые типы источников для строгой типизации
SourceType = Literal["release", "commit"]


class CreateResult:
    def __init__(self, dest: Path, version: str) -> None:
        self.dest = dest
        self.version = version


class GenericHandler:
    def __init__(self, kind: str) -> None:
        self.kind = kind

    def create(
        self,
        entry: TemplateEntry,
        name: str,
        output_dir: Path,
        ref: str | None,
        custom_folder_name: str | None = None,
    ) -> CreateResult:
        version = self._resolve_version(entry, name, ref)
        src = self._template_dir(entry, name, version)

        label = self.kind if name.lower() == "default" else name
        folder_name = custom_folder_name if custom_folder_name else f"{label}-{version}"
        dest = output_dir / folder_name

        if dest.exists():
            shutil.rmtree(dest)

        shutil.copytree(
            src,
            dest,
            ignore=shutil.ignore_patterns("yal-meta.json", "yal.template.toml", *entry.exclude),
        )
        return CreateResult(dest=dest, version=version)

    def _resolve_version(
        self,
        entry: TemplateEntry,
        name: str,
        ref: str | None,
    ) -> str:
        if ref:
            if self._is_installed(entry, name, ref):
                print(f"[YAL] {t('create.using-local', version=ref)}")
                return ref
            return self._download(entry, name, ref)

        recent = self._get_most_recent_local(entry, name)
        if recent:
            print(f"[YAL] {t('create.using-local', version=recent)}")
            return recent

        return self._download(entry, name, ref)

    def _download(
        self,
        entry: TemplateEntry,
        name: str,
        ref: str | None,
    ) -> str:
        releases = _fetch_releases_safe(entry.repo)
        if releases:
            return self._download_release(entry, name, ref, releases)
        else:
            return self._download_commit(entry, name, ref)

    def _download_release(
        self,
        entry: TemplateEntry,
        name: str,
        ref: str | None,
        releases: list[github.ReleaseInfo],
    ) -> str:
        if ref is None or ref == "latest":
            target = releases[0]
        else:
            target = next(
                (r for r in releases if r.tag in (ref, f"v{ref}")),
                None,
            )
            if target is None:
                available = ", ".join(r.tag for r in releases)
                raise ValueError(t("errors.release-missing", ref=ref, available=available))

        version = target.tag.lstrip("vV")

        if self._is_installed(entry, name, version):
            print(f"[YAL] {t('create.using-local', version=version)}")
            return version

        if not self.confirm_download(name, version, t("download.release"), entry.repo, entry.is_user):
            raise RuntimeError(t("errors.cancelled", action=t("create.action")))

        dest = self._template_dir(entry, name, version)
        print(f"[YAL] {t('download.release-downloading', tag=target.tag)}")
        github.download_release(target, dest)
        self._save_meta(entry, name, version, "release")
        print(f"[YAL] {t('download.done', path=dest)}")
        return version

    def _download_commit(
        self,
        entry: TemplateEntry,
        name: str,
        ref: str | None,
    ) -> str:
        print(f"[YAL] {t('update.no-releases')}")

        try:
            if ref is None or ref == "latest":
                info = github.get_latest_commit(entry.repo)
            else:
                info = github.get_commit(entry.repo, ref)
        except Exception as e:
            raise RuntimeError(t("errors.commit-info-fail", error=e)) from e

        version = info.sha7

        if self._is_installed(entry, name, version):
            print(f"[YAL] {t('create.using-local', version=version)}")
            return version

        if not self.confirm_download(name, version, t("download.commit"), entry.repo, entry.is_user):
            raise RuntimeError(t("errors.cancelled", action=t("create.action")))

        dest = self._template_dir(entry, name, version)
        print(f"[YAL] {t('download.commit-cloning', version=version)}")
        try:
            github.clone_repo(entry.repo, dest, ref=info.sha)
        except Exception:
            if dest.exists():
                import shutil as _shutil
                from yal.github import _force_remove_readonly
                _shutil.rmtree(dest, onexc=_force_remove_readonly)
            raise
        self._save_meta(entry, name, version, "commit")
        print(f"[YAL] {t('download.done', path=dest)}")
        return version

    # ── Адаптеры к хранилищам ─────────────────────────────────────────────────

    def _template_dir(self, entry: TemplateEntry, name: str, version: str) -> Path:
        if entry.is_user:
            return user_store.user_template_dir(self.kind, name, version)
        return store.template_dir(self.kind, name, version)

    def _is_installed(self, entry: TemplateEntry, name: str, version: str) -> bool:
        if entry.is_user:
            return user_store.user_is_installed(self.kind, name, version)
        return store.is_installed(self.kind, name, version)

    def _get_most_recent_local(self, entry: TemplateEntry, name: str) -> str | None:
        if entry.is_user:
            return user_store.user_get_most_recent_local(self.kind, name)
        return store.get_most_recent_local(self.kind, name)

    def _installed_versions(self, entry: TemplateEntry, name: str) -> list[str]:
        if entry.is_user:
            return user_store.user_installed_versions(self.kind, name)
        return store.installed_versions(self.kind, name)

    def _save_meta(self, entry: TemplateEntry, name: str, version: str, source: str) -> None:
        src_literal = cast(SourceType, source)
        if entry.is_user:
            user_store.user_save_meta(self.kind, name, version, src_literal, entry.repo)
        else:
            store.save_meta(self.kind, name, version, src_literal, entry.repo)

    def confirm_download(
        self, name: str, version: str, source_type: str, repo: str, is_user: bool = False
    ) -> bool:
        confirm_key = "download.confirm-user" if is_user else "download.confirm"
        msg = t(
            confirm_key,
            kind=self.kind,
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


# ── Утилиты ──────────────────────────────────────────────────────────────────

def _fetch_releases_safe(repo: str) -> list[github.ReleaseInfo]:
    try:
        return github.get_releases(repo)
    except Exception as e:
        print(f"[YAL] {t('errors.no-releases-warn', error=e)}")
        return []
