"""
Универсальный обработчик шаблонов GenericHandler.

Единая точка для всей логики "release vs commit": и `yal new`/`yal add`
(через _resolve_version/_download), и `yal update` (через update_template)
используют одни и те же низкоуровневые методы _fetch_release/_fetch_commit
для собственно скачивания и сохранения метаданных. Раньше эта механика была
продублирована ещё и в commands/add.py и commands/update.py — теперь она
живёт только здесь.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal, cast

from yal import git_provider, store, user_store
from yal.i18n import t, yes_variants
from yal.templates.registry import TemplateEntry

SourceType = Literal["release", "commit"]


class CreateResult:
    def __init__(self, dest: Path, version: str) -> None:
        self.dest = dest
        self.version = version


class GenericHandler:
    def __init__(self, kind: str) -> None:
        self.kind = kind

    # ── создание проекта (yal new) ────────────────────────────────────────────

    def create(
        self,
        entry: TemplateEntry,
        name: str,
        output_dir: Path,
        ref: str | None,
        custom_folder_name: str | None = None,
        resolved_version: str | None = None,
        force_commit: bool = False,
    ) -> CreateResult:
        version = resolved_version if resolved_version is not None else self._resolve_version(entry, name, ref, force_commit)
        src = self._template_dir(entry, name, version)

        label = self.kind if name.lower() == "default" else name
        folder_name = custom_folder_name if custom_folder_name else f"{label}-{version}"
        dest = output_dir / folder_name

        from yal import template_config
        config = template_config.load(src)

        combined_exclude = set(entry.exclude)
        if config and config.exclude:
            combined_exclude.update(config.exclude)

        combined_exclude.add("yal-meta.json")

        if dest.exists():
            shutil.rmtree(dest)

        # Копируем всё
        shutil.copytree(
            src,
            dest,
            ignore=shutil.ignore_patterns(*combined_exclude),
        )

        template_yaml = dest / ".yal" / "template.yml"
        if template_yaml.exists():
            template_yaml.unlink()
            print(f"[YAL] Удалён {template_yaml}")

        yal_dir = dest / ".yal"
        if yal_dir.exists() and yal_dir.is_dir():
            contents = list(yal_dir.iterdir())
            if not contents:
                shutil.rmtree(yal_dir)
                print(f"[YAL] Удалена пустая папка {yal_dir}")

        return CreateResult(dest=dest, version=version)


    def _resolve_version(
        self,
        entry: TemplateEntry,
        name: str,
        ref: str | None,
        force_commit: bool = False,
    ) -> str:
        if ref:
            if self._is_installed(entry, name, ref):
                print(f"[YAL] {t('create.using-local', version=ref)}")
                return ref
            return self._download(entry, name, ref, force_commit)

        if not force_commit:
            recent = self._get_most_recent_local(entry, name)
            if recent:
                print(f"[YAL] {t('create.using-local', version=recent)}")
                return recent

        return self._download(entry, name, ref, force_commit)

    def _download(
        self,
        entry: TemplateEntry,
        name: str,
        ref: str | None,
        force_commit: bool = False,
        action: str = "create",
    ) -> str:
        """
        Используется и из new.py (через _resolve_version), и напрямую
        из commands/add.py при первой регистрации шаблона.

        `action` — какой i18n-ключ `<action>.action` подставлять в сообщение
        об отмене (`errors.cancelled`): "create" для yal new, "add" для yal add.
        """
        if force_commit:
            return self._download_commit(entry, name, ref, action=action)
        releases = _fetch_releases_safe(entry.repo)
        if releases:
            return self._download_release(entry, name, ref, releases, action=action)
        else:
            return self._download_commit(entry, name, ref, action=action)

    def _download_release(
        self,
        entry: TemplateEntry,
        name: str,
        ref: str | None,
        releases: list[git_provider.ReleaseInfo],
        action: str = "create",
    ) -> str:
        if ref is None or ref == "latest":
            target = releases[0]
        else:
            target = next(
                (r for r in releases if r.tag in (ref, f"v{ref}")),
                None,
            )
            if target is None:
                return self._download_commit(entry, name, ref, action=action)

        version = target.tag.lstrip("vV")

        if self._is_installed(entry, name, version):
            print(f"[YAL] {t('create.using-local', version=version)}")
            return version

        dest = self._fetch_release(entry, name, version, target, action=action)
        print(f"[YAL] {t('download.done', path=dest)}")
        return version

    def _download_commit(
        self,
        entry: TemplateEntry,
        name: str,
        ref: str | None,
        action: str = "create",
    ) -> str:
        print(f"[YAL] {t('update.no-releases')}")

        try:
            if ref is None or ref == "latest":
                info = git_provider.get_latest_commit(entry.repo)
            else:
                info = git_provider.get_commit(entry.repo, ref)
        except Exception as e:
            raise RuntimeError(t("errors.commit-info-fail", error=e)) from e

        version = info.sha7

        if self._is_installed(entry, name, version):
            print(f"[YAL] {t('create.using-local', version=version)}")
            return version

        dest = self._fetch_commit(entry, name, version, info, action=action)
        print(f"[YAL] {t('download.done', path=dest)}")
        return version

    # ── обновление шаблона (yal update) ───────────────────────────────────────

    def update_template(
        self,
        entry: TemplateEntry,
        name: str,
        force_commit: bool = False,
    ) -> None:
        """Полная логика команды `yal update` для одного шаблона."""
        if force_commit:
            self._update_commit(entry, name)
            return
        releases = _fetch_releases_safe(entry.repo)
        if releases:
            self._update_release(entry, name, releases)
        else:
            self._update_commit(entry, name)

    def _update_release(self, entry: TemplateEntry, name: str, releases: list[git_provider.ReleaseInfo]) -> None:
        latest = releases[0]
        version = latest.tag.lstrip("vV")

        if self._is_installed(entry, name, version):
            print(f"[YAL] {t('update.already-latest', version=version)}")
            return

        local = self._get_most_recent_local(entry, name)
        if local:
            print(f"[YAL] {t('update.upgrading', kind=self.kind, name=name, old=local, new=version)}")
        else:
            print(f"[YAL] {t('update.installing', kind=self.kind, name=name, version=version)}")

        dest = self._fetch_release(entry, name, version, latest, action="update")
        print(f"[YAL] {t('update.installed', path=dest)}")

    def _update_commit(self, entry: TemplateEntry, name: str) -> None:
        try:
            info = git_provider.get_latest_commit(entry.repo)
        except Exception as e:
            raise RuntimeError(t("update.commit-fail", error=e)) from e

        version = info.sha7

        if self._is_installed(entry, name, version):
            print(f"[YAL] {t('update.already-latest-commit', version=version)}")
            return

        local_versions = self._installed_versions(entry, name)
        if local_versions:
            print(f"[YAL] {t('update.upgrading-commit', kind=self.kind, name=name, old=local_versions[-1], new=version)}")
        else:
            print(f"[YAL] {t('update.installing-commit', kind=self.kind, name=name, version=version)}")

        dest = self._fetch_commit(entry, name, version, info, action="update")
        print(f"[YAL] {t('update.installed', path=dest)}")

    # ── единственное место, где мы реально что-то скачиваем и сохраняем ──────

    def _fetch_release(
        self,
        entry: TemplateEntry,
        name: str,
        version: str,
        target: git_provider.ReleaseInfo,
        action: str = "create",
    ) -> Path:
        if not self.confirm_download(name, version, t("download.release"), entry.repo, entry.is_user):
            raise RuntimeError(t("errors.cancelled", action=t(f"{action}.action")))

        dest = self._template_dir(entry, name, version)
        print(f"[YAL] {t('download.release-downloading', tag=target.tag)}")
        git_provider.download_release(target, dest)
        self._save_meta(entry, name, version, "release", target.released_at)
        return dest

    def _fetch_commit(
        self,
        entry: TemplateEntry,
        name: str,
        version: str,
        info,  # CommitInfo-подобный объект из git_provider (.sha, .released_at)
        action: str = "create",
    ) -> Path:
        if not self.confirm_download(name, version, t("download.commit"), entry.repo, entry.is_user):
            raise RuntimeError(t("errors.cancelled", action=t(f"{action}.action")))

        dest = self._template_dir(entry, name, version)
        print(f"[YAL] {t('download.commit-cloning', version=version)}")
        try:
            git_provider.clone_repo(entry.repo, dest, ref=info.sha)
        except Exception:
            if dest.exists():
                import shutil as _shutil
                _shutil.rmtree(dest, onexc=git_provider._force_remove_readonly)
            raise
        self._save_meta(entry, name, version, "commit", info.released_at)
        return dest

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

    def _save_meta(
        self, entry: TemplateEntry, name: str, version: str,
        source: str, released_at: str
    ) -> None:
        src_literal = cast(SourceType, source)
        if entry.is_user:
            user_store.user_save_meta(self.kind, name, version, src_literal, entry.repo, released_at)
        else:
            store.save_meta(self.kind, name, version, src_literal, entry.repo, released_at)

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
        except EOFError:
            print()
            return False
        except KeyboardInterrupt:
            raise
        return answer in yes_variants()


# ── Утилиты ──────────────────────────────────────────────────────────────────

def _fetch_releases_safe(repo: str) -> list[git_provider.ReleaseInfo]:
    try:
        return git_provider.get_releases(repo)
    except Exception as e:
        print(f"[YAL] {t('errors.no-releases-warn', error=e)}")
        return []
