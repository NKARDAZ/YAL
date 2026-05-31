"""
Обработчик типа 'book'.
Не содержит встроенного контента — всё берётся из репозитория,
указанного в реестре (registry.BOOK_REGISTRY).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from yal import github, store
from yal.i18n import t, yes_variants
from yal.templates.registry import TemplateEntry

KIND = "book"


class CreateResult:
    def __init__(self, dest: Path, version: str) -> None:
        self.dest = dest
        self.version = version


class BookHandler:
    def create(
        self,
        entry: TemplateEntry,
        name: str,
        output_dir: Path,
        ref: str | None,
        custom_folder_name: str | None = None,
    ) -> CreateResult:
        version = self._resolve_version(entry, name, ref)
        src = store.template_dir(KIND, version)

        # Если кастомное имя не задано, используем стандартное kind-version
        folder_name = custom_folder_name if custom_folder_name else f"{KIND}-{version}"
        dest = output_dir / folder_name

        if dest.exists():
            shutil.rmtree(dest)

        shutil.copytree(
            src,
            dest,
            ignore=shutil.ignore_patterns("yal-meta.json", *entry.exclude),
        )
        return CreateResult(dest=dest, version=version)

    def _resolve_version(
        self,
        entry: TemplateEntry,
        name: str,
        ref: str | None,
    ) -> str:
        if ref:
            if store.is_installed(KIND, ref):
                print(f"[YAL] {t('create.using-local', version=ref)}")
                return ref
            return self._download(entry, name, ref)

        recent = store.get_most_recent_local(KIND)
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

        if not _confirm_download(KIND, name, version, t("download.release"), entry.repo):
            raise RuntimeError(t("errors.cancelled", action=t("create.action")))

        dest = store.template_dir(KIND, version)
        print(f"[YAL] {t('download.release-downloading', tag=target.tag)}")
        github.download_release(target, dest)
        store.save_meta(KIND, version, "release", entry.repo)
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

        if not _confirm_download(KIND, name, version, t("download.commit"), entry.repo):
            raise RuntimeError(t("errors.cancelled", action=t("create.action")))

        dest = store.template_dir(KIND, version)
        print(f"[YAL] {t('download.commit-cloning', version=version)}")
        try:
            github.clone_repo(entry.repo, dest, ref=info.sha)
        except Exception:
            if dest.exists():
                import shutil as _shutil
                from yal.github import _force_remove_readonly
                _shutil.rmtree(dest, onexc=_force_remove_readonly)
            raise
        store.save_meta(KIND, version, "commit", entry.repo)
        print(f"[YAL] {t('download.done', path=dest)}")
        return version


# ── утилиты (используются также из update.py) ─────────────────────────────────

def _fetch_releases_safe(repo: str) -> list[github.ReleaseInfo]:
    try:
        return github.get_releases(repo)
    except Exception as e:
        print(f"[YAL] {t('errors.no-releases-warn', error=e)}")
        return []


def _confirm_download(
    kind: str,
    name: str,
    version: str,
    source_type: str,
    repo: str,
) -> bool:
    msg = t(
        "download.confirm",
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
