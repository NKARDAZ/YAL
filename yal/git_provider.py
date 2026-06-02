"""
Универсальный провайдер для git-репозиториев.

Поддерживает:
  — GitHub   (API релизов + zipball-скачивание + clone)
  — GitLab   (API релизов + архив-скачивание + clone)
  — Codeberg (API релизов Forgejo + clone)
  — Bitbucket (clone; нет публичного release-API для источников)
  — git.gay / gitverse / SourceForge (только clone)
  — Произвольный git-URL (только clone)

Сокращения для команды `yal add ... from <spec>`:
  user/repo              → https://github.com/user/repo
  github:user/repo       → https://github.com/user/repo
  gitlab:user/repo       → https://gitlab.com/user/repo
  codeberg:user/repo     → https://codeberg.org/user/repo
  bitbucket:user/repo    → https://bitbucket.org/user/repo
  git.gay:user/repo      → https://git.gay/user/repo
  gitverse:user/repo     → https://gitverse.ru/user/repo
  sourceforge:project/repo → ssh://user@git.code.sf.net/p/project/repo
    (для SourceForge без пользователя используется анонимный git-доступ:
     git://git.code.sf.net/p/project/repo)
"""

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

TIMEOUT = 30


# ─── типы данных ──────────────────────────────────────────────────────────────

class ReleaseInfo(NamedTuple):
    tag: str
    zipball_url: str
    released_at: str


class CommitInfo(NamedTuple):
    sha: str    # полный sha
    sha7: str   # первые 7 символов
    released_at: str


# ─── провайдеры ───────────────────────────────────────────────────────────────

class _Provider:
    """Базовый класс провайдера. Подклассы переопределяют нужные методы."""

    name: str = "generic"

    def supports_releases(self) -> bool:
        return False

    def get_releases(self, repo: str) -> list[ReleaseInfo]:
        return []

    def get_latest_commit(self, repo: str, branch: str = "HEAD") -> CommitInfo:
        raise NotImplementedError

    def get_commit(self, repo: str, ref: str) -> CommitInfo:
        raise NotImplementedError

    def download_release(self, release: ReleaseInfo, dest: Path) -> None:
        raise NotImplementedError(f"Provider '{self.name}' does not support release downloads")

    def clone_repo(self, repo: str, dest: Path, ref: str | None = None) -> None:
        _git_clone(repo, dest, ref)


class _GitHubProvider(_Provider):
    name = "github"
    _API = "https://api.github.com"

    def supports_releases(self) -> bool:
        return True

    def get_releases(self, repo: str) -> list[ReleaseInfo]:
        owner_repo = _github_owner_repo(repo)
        url = f"{self._API}/repos/{owner_repo}/releases"
        data = _gh_get(url)
        if isinstance(data, dict):
            return []
        return [
            ReleaseInfo(tag=r["tag_name"], zipball_url=r["zipball_url"], released_at=r["published_at"])
            for r in data
        ]

    def get_latest_commit(self, repo: str, branch: str = "HEAD") -> CommitInfo:
        owner_repo = _github_owner_repo(repo)
        url = f"{self._API}/repos/{owner_repo}/commits/{branch}"
        data = _gh_get(url)
        if not isinstance(data, dict):
            raise RuntimeError(f"Неожиданный ответ от GitHub: {data!r}")
        sha: str = data["sha"]
        date: str = data["commit"]["committer"]["date"]
        return CommitInfo(sha=sha, sha7=sha[:7], released_at=date)

    def get_commit(self, repo: str, ref: str) -> CommitInfo:
        owner_repo = _github_owner_repo(repo)
        url = f"{self._API}/repos/{owner_repo}/commits/{ref}"
        data = _gh_get(url)
        if not isinstance(data, dict):
            raise RuntimeError(f"Неожиданный ответ от GitHub: {data!r}")
        sha: str = data["sha"]
        date: str = data["commit"]["committer"]["date"]
        return CommitInfo(sha=sha, sha7=sha[:7], released_at=date)

    def download_release(self, release: ReleaseInfo, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        headers: dict[str, str] = {}
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "release.zip"
            _download_file(release.zipball_url, zip_path, headers)
            _extract_flat(zip_path, dest)


class _GitLabProvider(_Provider):
    """GitLab.com или self-hosted GitLab."""
    name = "gitlab"

    def __init__(self, base_url: str = "https://gitlab.com") -> None:
        self._base = base_url.rstrip("/")

    def supports_releases(self) -> bool:
        return True

    def _owner_repo(self, repo: str) -> str:
        """Извлекает 'owner/repo' (или 'group/sub/repo') из URL."""
        m = re.search(r"gitlab[^/]*/(.+?)(?:\.git)?$", repo)
        if m:
            return m.group(1).strip("/")
        if repo.count("/") >= 1 and not repo.startswith("http"):
            return repo.strip("/")
        raise ValueError(f"Не удалось распознать GitLab-репозиторий: {repo!r}")

    def get_releases(self, repo: str) -> list[ReleaseInfo]:
        encoded = self._owner_repo(repo).replace("/", "%2F")
        url = f"{self._base}/api/v4/projects/{encoded}/releases"
        token = os.environ.get("GITLAB_TOKEN") or os.environ.get("GL_TOKEN")
        headers = {"PRIVATE-TOKEN": token} if token else {}
        try:
            resp = requests.get(url, headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        result = []
        for r in data:
            tag = r.get("tag_name", "")
            released_at = r.get("released_at", "")
            # Ищем архив исходников
            src = r.get("assets", {}).get("sources", [])
            zip_url = next((s["url"] for s in src if s.get("format") == "zip"), "")
            if tag and zip_url:
                result.append(ReleaseInfo(tag=tag, zipball_url=zip_url, released_at=released_at))
        return result

    def get_latest_commit(self, repo: str, branch: str = "HEAD") -> CommitInfo:
        return _git_latest_commit(repo, branch)

    def get_commit(self, repo: str, ref: str) -> CommitInfo:
        return _git_get_commit(repo, ref)

    def download_release(self, release: ReleaseInfo, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        token = os.environ.get("GITLAB_TOKEN") or os.environ.get("GL_TOKEN")
        headers = {"PRIVATE-TOKEN": token} if token else {}
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "release.zip"
            _download_file(release.zipball_url, zip_path, headers)
            _extract_flat(zip_path, dest)


class _ForgejoProvider(_Provider):
    """Codeberg и другие экземпляры Forgejo/Gitea."""
    name = "forgejo"

    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")

    def supports_releases(self) -> bool:
        return True

    def _owner_repo(self, repo: str) -> str:
        # Убираем базовый URL и .git
        s = repo
        for prefix in (self._base + "/", "https://", "http://"):
            if s.startswith(prefix):
                s = s[len(prefix):]
        m = re.match(r"[^/]+/(.+?)(?:\.git)?$", s)
        if m:
            return m.group(1).strip("/")
        if s.count("/") == 1:
            return s.strip("/")
        raise ValueError(f"Не удалось распознать Forgejo-репозиторий: {repo!r}")

    def get_releases(self, repo: str) -> list[ReleaseInfo]:
        owner_repo = self._owner_repo(repo)
        url = f"{self._base}/api/v1/repos/{owner_repo}/releases"
        token = os.environ.get("FORGEJO_TOKEN") or os.environ.get("CODEBERG_TOKEN")
        headers = {"Authorization": f"token {token}"} if token else {}
        try:
            resp = requests.get(url, headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        result = []
        for r in data:
            tag = r.get("tag_name", "")
            published = r.get("published_at", r.get("created_at", ""))
            # Forgejo даёт zipball_url напрямую
            zipball = r.get("zipball_url", "")
            if not zipball:
                # Строим из тега
                zipball = f"{self._base}/{owner_repo}/archive/{tag}.zip"
            if tag:
                result.append(ReleaseInfo(tag=tag, zipball_url=zipball, released_at=published))
        return result

    def get_latest_commit(self, repo: str, branch: str = "HEAD") -> CommitInfo:
        return _git_latest_commit(repo, branch)

    def get_commit(self, repo: str, ref: str) -> CommitInfo:
        return _git_get_commit(repo, ref)

    def download_release(self, release: ReleaseInfo, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        token = os.environ.get("FORGEJO_TOKEN") or os.environ.get("CODEBERG_TOKEN")
        headers = {"Authorization": f"token {token}"} if token else {}
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "release.zip"
            _download_file(release.zipball_url, zip_path, headers)
            _extract_flat(zip_path, dest)


class _GenericGitProvider(_Provider):
    """Универсальный провайдер: только git clone, без API."""
    name = "git"

    def supports_releases(self) -> bool:
        return False

    def get_latest_commit(self, repo: str, branch: str = "HEAD") -> CommitInfo:
        return _git_latest_commit(repo, branch)

    def get_commit(self, repo: str, ref: str) -> CommitInfo:
        return _git_get_commit(repo, ref)


class _LsRemoteProvider(_GenericGitProvider):
    """Провайдер для git-хостов без release API: теги читаем через git ls-remote."""
    name = "git-ls-remote"

    def supports_releases(self) -> bool:
        return True

    def get_releases(self, repo: str) -> list[ReleaseInfo]:
        tags = _git_list_tags(repo)
        return [ReleaseInfo(tag=tag, zipball_url=repo, released_at="") for tag, _sha in tags]

    def download_release(self, release: ReleaseInfo, dest: Path) -> None:
        _git_clone(release.zipball_url, dest, release.tag)


# ─── определение провайдера по URL ───────────────────────────────────────────

_KNOWN_PROVIDERS: list[tuple[str, _Provider]] = [
    ("github.com", _GitHubProvider()),
    ("gitlab.com", _GitLabProvider("https://gitlab.com")),
    ("codeberg.org", _ForgejoProvider("https://codeberg.org")),
    ("git.gay", _ForgejoProvider("https://git.gay")),
    # Gitverse поддерживает теги и релизы через git ls-remote.
    ("gitverse.ru", _LsRemoteProvider()),
    # Остальные — только clone
    ("bitbucket.org", _GenericGitProvider()),
    ("git.code.sf.net", _GenericGitProvider()),  # SourceForge
]

_GENERIC = _GenericGitProvider()


def get_provider(repo: str) -> _Provider:
    """Выбирает провайдер по URL репозитория."""
    repo_lower = repo.lower()
    for domain, provider in _KNOWN_PROVIDERS:
        if domain in repo_lower:
            return provider
    return _GENERIC


# ─── сокращения (shortcuts) ──────────────────────────────────────────────────

# Карта: префикс → функция нормализации
def expand_repo_shortcut(spec: str) -> str:
    """
    Разворачивает сокращённую запись репозитория в полный URL.

    Правила:
      user/repo              → https://github.com/user/repo
      github:user/repo       → https://github.com/user/repo
      gitlab:user/repo       → https://gitlab.com/user/repo
      gitlab:host.com:user/repo → https://host.com/user/repo  (self-hosted)
      codeberg:user/repo     → https://codeberg.org/user/repo
      bitbucket:user/repo    → https://bitbucket.org/user/repo
      git.gay:user/repo      → https://git.gay/user/repo
      gitverse:user/repo     → https://gitverse.ru/user/repo
      sourceforge:project/repo → git://git.code.sf.net/p/project/repo
      sourceforge:user@project/repo → ssh://user@git.code.sf.net/p/project/repo
      Полный https?://... или git://... или ssh://... → без изменений
    """
    s = spec.strip()

    # Локальный путь на Windows или Unix
    if os.path.isabs(s) or s.startswith(("./", "../")):
        return s
    if os.path.exists(s):
        return s

    # Уже полный URL
    if re.match(r"^(https?|git|ssh)://", s):
        return s

    # Простое сокращение user/repo → GitHub
    if re.match(r"^[^:/\s]+/[^:/\s]+$", s):
        return f"https://github.com/{s}"

    # Префиксные сокращения
    prefix, _, rest = s.partition(":")
    prefix_lower = prefix.lower()

    if prefix_lower == "github":
        return f"https://github.com/{rest}"

    if prefix_lower == "gitlab":
        # gitlab:user/repo  или  gitlab:host.example.com:user/repo
        if ":" in rest:
            host, _, path = rest.partition(":")
            return f"https://{host}/{path}"
        return f"https://gitlab.com/{rest}"

    if prefix_lower == "codeberg":
        return f"https://codeberg.org/{rest}"

    if prefix_lower == "bitbucket":
        return f"https://bitbucket.org/{rest}"

    if prefix_lower in ("git.gay", "gitgay"):
        return f"https://git.gay/{rest}"

    if prefix_lower == "gitverse":
        return f"https://gitverse.ru/{rest}"

    if prefix_lower == "sourceforge":
        # sourceforge:project/repo  или  sourceforge:user@project/repo
        m = re.match(r"^(?P<user>[^@]+)@(?P<project>[^/]+)/(?P<repo>.+)$", rest)
        if m:
            user = m.group("user")
            project = m.group("project")
            repo_name = m.group("repo")
            return f"ssh://{user}@git.code.sf.net/p/{project}/{repo_name}"
        # Анонимный доступ
        m2 = re.match(r"^(?P<project>[^/]+)/(?P<repo>.+)$", rest)
        if m2:
            project = m2.group("project")
            repo_name = m2.group("repo")
            return f"git://git.code.sf.net/p/{project}/{repo_name}"
        raise ValueError(f"Не удалось разобрать SourceForge-сокращение: {spec!r}\n"
                         "  Формат: sourceforge:project/repo  или  sourceforge:user@project/repo")

    raise ValueError(f"Неизвестный префикс провайдера: {prefix!r} в {spec!r}")


def validate_repo_url(url: str) -> None:
    """Бросает ValueError если url не похож на git-адрес."""
    if os.path.exists(url):
        return
    if re.match(r"^(https?|git|ssh)://", url):
        return
    if re.match(r"^git@[^:]+:.+", url):
        return  # SCP-нотация: git@github.com:user/repo.git
    raise ValueError(f"Неподдерживаемый формат репозитория: {url!r}\n"
                     "  Ожидается https://, git://, ssh://, git@host:path или путь к локальному репозиторию")


# ─── публичный API (совместимый с прежним github.py) ─────────────────────────

def get_releases(repo: str) -> list[ReleaseInfo]:
    provider = get_provider(repo)
    if not provider.supports_releases():
        return []
    return provider.get_releases(repo)


def get_latest_commit(repo: str, branch: str = "HEAD") -> CommitInfo:
    return get_provider(repo).get_latest_commit(repo, branch)


def get_commit(repo: str, ref: str) -> CommitInfo:
    return get_provider(repo).get_commit(repo, ref)


def download_release(release: ReleaseInfo, dest: Path) -> None:
    # zipball_url содержит хост — определяем провайдер из него
    provider = get_provider(release.zipball_url)
    provider.download_release(release, dest)


def clone_repo(repo: str, dest: Path, ref: str | None = None) -> None:
    get_provider(repo).clone_repo(repo, dest, ref)


# ─── вспомогательные функции ─────────────────────────────────────────────────

def _github_owner_repo(repo: str) -> str:
    m = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git)?$", repo)
    if m:
        return m.group(1)
    if repo.count("/") == 1 and not repo.startswith("http"):
        return repo
    raise ValueError(f"Не удалось распознать GitHub-репозиторий: {repo!r}")


def _gh_get(url: str) -> dict | list:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _download_file(url: str, dest: Path, headers: dict[str, str] | None = None) -> None:
    h = headers or {}
    with requests.get(url, stream=True, timeout=60, headers=h) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def _extract_flat(zip_path: Path, dest: Path) -> None:
    """Распаковать zip, убирая верхний каталог-обёртку (GitHub/GitLab/Forgejo)."""
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


def _git_clone(repo: str, dest: Path, ref: str | None = None) -> None:
    """Клонирует репозиторий в dest, удаляет .git."""
    if dest.exists():
        shutil.rmtree(dest, onexc=_force_remove_readonly)
    dest.mkdir(parents=True, exist_ok=True)

    if ref:
        _run(["git", "clone", repo, str(dest)])
        _run(["git", "-C", str(dest), "checkout", ref])
    else:
        _run(["git", "clone", "--depth", "1", repo, str(dest)])

    git_dir = dest / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir, onexc=_force_remove_readonly)


def _git_latest_commit(repo: str, branch: str = "HEAD") -> CommitInfo:
    """Получает sha последнего коммита через git ls-remote (без полного клона)."""
    result = subprocess.run(
        ["git", "ls-remote", repo, branch],
        capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout.strip():
        # Fallback: пробуем HEAD
        result = subprocess.run(
            ["git", "ls-remote", repo, "HEAD"],
            capture_output=True, text=True
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"Не удалось получить коммит из {repo!r}: {result.stderr.strip()}"
        )
    line = result.stdout.strip().split("\n")[0]
    sha = line.split()[0] if line else ""
    if not sha:
        raise RuntimeError(f"Пустой ответ git ls-remote для {repo!r}")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return CommitInfo(sha=sha, sha7=sha[:7], released_at=now)


def _git_get_commit(repo: str, ref: str) -> CommitInfo:
    """Получает информацию о конкретном коммите/теге."""
    result = subprocess.run(
        ["git", "ls-remote", repo, ref, f"refs/tags/{ref}", f"refs/heads/{ref}"],
        capture_output=True, text=True
    )
    sha = ""
    if result.returncode == 0 and result.stdout.strip():
        sha = _pick_ref_sha_from_ls_remote(result.stdout.strip().splitlines(), ref)

    if not sha and re.fullmatch(r"[0-9a-fA-F]{7,40}", ref):
        result = subprocess.run(
            ["git", "ls-remote", "--heads", "--tags", repo],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                candidate = line.split()[0]
                if candidate.lower().startswith(ref.lower()):
                    sha = candidate
                    break

    if not sha and re.fullmatch(r"[0-9a-fA-F]{7,40}", ref):
        sha = ref

    if not sha:
        raise RuntimeError(
            f"Не удалось найти ref {ref!r} в {repo!r}. "
            "Ожидается ветка, тег или SHA-256/160 хеш."  # noqa: E501
        )
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return CommitInfo(sha=sha, sha7=sha[:7], released_at=now)


def _pick_ref_sha_from_ls_remote(lines: list[str], ref: str) -> str:
    exact_head = ""
    exact_tag = ""
    direct_sha = ""
    for line in lines:
        parts = line.split()
        if len(parts) < 2:
            continue
        sha, refname = parts[0], parts[1]
        if refname == f"refs/tags/{ref}^{{}}":
            return sha
        if refname == f"refs/heads/{ref}":
            exact_head = exact_head or sha
        if refname == f"refs/tags/{ref}":
            exact_tag = exact_tag or sha
        if refname == ref:
            direct_sha = direct_sha or sha
    return direct_sha or exact_head or exact_tag or ""


def _git_list_tags(repo: str) -> list[tuple[str, str]]:
    result = subprocess.run(
        ["git", "ls-remote", "--tags", repo],
        capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []

    tags: dict[str, dict[str, str]] = {}
    for line in result.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        sha, refname = parts[0], parts[1]
        if not refname.startswith("refs/tags/"):
            continue
        tag_name = refname[len("refs/tags/"):]
        if tag_name.endswith("^{}"):
            base_tag = tag_name[:-3]
            tags.setdefault(base_tag, {})["peeled"] = sha
        else:
            tags.setdefault(tag_name, {})["tag"] = sha

    result_tags: list[tuple[str, str]] = []
    for tag_name, data in tags.items():
        result_tags.append((tag_name, data.get("peeled") or data.get("tag")))
    return result_tags


def _force_remove_readonly(func, path, _exc) -> None:
    import stat
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Команда завершилась с ошибкой: {' '.join(cmd)}\n{result.stderr}"
        )
