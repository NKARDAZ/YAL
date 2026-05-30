"""GitHub-клиент: получение релизов и скачивание исходников."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import NamedTuple

import requests

GITHUB_API = "https://api.github.com"
TIMEOUT = 30


class ReleaseInfo(NamedTuple):
    tag: str
    zipball_url: str


class CommitInfo(NamedTuple):
    sha: str   # полный sha
    sha7: str  # первые 7 символов


# ─── публичный API ────────────────────────────────────────────────────────────

def get_releases(repo: str) -> list[ReleaseInfo]:
    """Возвращает список релизов (от новейшего к старейшему)."""
    url = f"{GITHUB_API}/repos/{_owner_repo(repo)}/releases"
    data = _gh_get(url)
    if isinstance(data, dict):
        return []
    return [ReleaseInfo(tag=r["tag_name"], zipball_url=r["zipball_url"]) for r in data]


def get_latest_commit(repo: str, branch: str = "HEAD") -> CommitInfo:
    url = f"{GITHUB_API}/repos/{_owner_repo(repo)}/commits/{branch}"
    data = _gh_get(url)
    if not isinstance(data, dict):
        raise RuntimeError(f"Неожиданный ответ от GitHub: {data!r}")
    sha: str = data["sha"]
    return CommitInfo(sha=sha, sha7=sha[:7])


def get_commit(repo: str, ref: str) -> CommitInfo:
    """Получить информацию о конкретном коммите по sha (полному или сокращённому)."""
    url = f"{GITHUB_API}/repos/{_owner_repo(repo)}/commits/{ref}"
    data = _gh_get(url)
    if not isinstance(data, dict):
        raise RuntimeError(f"Неожиданный ответ от GitHub: {data!r}")
    sha: str = data["sha"]
    return CommitInfo(sha=sha, sha7=sha[:7])


def download_release(release: ReleaseInfo, dest: Path) -> None:
    """
    Скачать zipball релиза и распаковать в dest/.
    GitHub оборачивает содержимое в папку «owner-repo-sha/» — мы её снимаем.
    """
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "release.zip"
        _download_file(release.zipball_url, zip_path)
        _extract_flat(zip_path, dest)


def clone_repo(repo: str, dest: Path, ref: str | None = None) -> None:
    """Клонирует репозиторий в dest, удаляет .git."""
    # Если папка уже существует (прерванная установка) — очищаем её
    if dest.exists():
        shutil.rmtree(dest, onexc=_force_remove_readonly)
    dest.mkdir(parents=True, exist_ok=True)
    clone_url = f"https://github.com/{_owner_repo(repo)}.git"

    if ref:
        # Полный клон чтобы можно было сделать checkout конкретного коммита
        _run(["git", "clone", clone_url, str(dest)])
        _run(["git", "-C", str(dest), "checkout", ref])
    else:
        _run(["git", "clone", "--depth", "1", clone_url, str(dest)])

    git_dir = dest / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir, onexc=_force_remove_readonly)


# ─── вспомогательные ──────────────────────────────────────────────────────────

def _owner_repo(repo: str) -> str:
    match = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git)?$", repo)
    if match:
        return match.group(1)
    if repo.count("/") == 1:
        return repo
    raise ValueError(f"Не удалось распознать репозиторий: {repo!r}")


def _gh_get(url: str) -> dict | list:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _download_file(url: str, dest: Path) -> None:
    headers: dict[str, str] = {}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with requests.get(url, stream=True, timeout=60, headers=headers) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def _extract_flat(zip_path: Path, dest: Path) -> None:
    """Распаковать zip, убирая верхний каталог-обёртку GitHub."""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        prefix = names[0].split("/")[0] + "/" if names else ""
        for member in names:
            rel = member[len(prefix):]
            if not rel:
                continue
            target = dest / rel
            if member.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as out:
                    out.write(src.read())


def _force_remove_readonly(func, path, _exc) -> None:
    """
    onexc-колбэк для shutil.rmtree.
    На Windows файлы в .git помечены read-only — снимаем атрибут и повторяем.
    """
    import stat
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Команда завершилась с ошибкой: {' '.join(cmd)}\n{result.stderr}"
        )
