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
  yal add book:mytheme from user/repo --commit
"""

from __future__ import annotations

import argparse
import sys
import re

from yal import user_store
from yal.git_provider import expand_repo_shortcut, validate_repo_url
from yal.i18n import t, yes_variants
from yal.templates.handler import GenericHandler
from yal.templates.registry import TemplateEntry, is_builtin
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
        except EOFError:
            print()
            sys.exit(0)
        except KeyboardInterrupt:
            raise
        if answer not in yes_variants():
            print(f"[YAL] {t('errors.cancelled', action=t('add.action'))}")
            sys.exit(0)
        exclude = None
    else:
        exclude = None

    # TemplateEntry создаётся здесь "с нуля" (а не через registry.get_entry),
    # поэтому is_user нужно выставить явно: иначе сработает дефолт is_user=False
    # из TemplateEntry, и GenericHandler начнёт писать в built-in store.* вместо
    # user_store.* — то есть в ~/.yal/templates/ вместо ~/.yal/user-templates/.
    entry = TemplateEntry(repo=repo, exclude=[], is_user=True)
    handler = GenericHandler(kind)

    try:
        version = handler._download(
            entry, name, ref,
            force_commit=getattr(args, "commit", False),
            action="add",
        )
    except (ValueError, RuntimeError) as e:
        print(f"[YAL] {t('create.error', error=e)}")
        sys.exit(1)

    if exclude is None:
        exclude = _ask_excludes()

    user_registry.add_entry(kind, name, repo, exclude)

    dest = user_store.user_template_dir(kind, name, version)
    print(f"[YAL] {t('add.registered', kind=kind, name=name, path=dest)}")


# ─── диалог исключений ────────────────────────────────────────────────────────

def _ask_excludes() -> list[str]:
    print(f"\n[YAL] {t('add.ask-excludes')}", end="")
    print(t("common.confirm-prompt"), end="", flush=True)
    try:
        answer = input().strip().lower()
    except EOFError:
        print()
        return []
    except KeyboardInterrupt:
        raise

    if answer not in yes_variants():
        return []

    print(f"[YAL] {t('add.exclude-hint')}")
    excludes: list[str] = []
    while True:
        print("  > ", end="", flush=True)
        try:
            line = input().strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            raise
        if not line:
            break
        excludes.append(line)

    if excludes:
        print(f"[YAL] {t('add.excludes-saved', items=', '.join(excludes))}")
    return excludes


# ─── парсинг спецификации ─────────────────────────────────────────────────────

def _parse_spec(what: str, from_kw: str | None, repo_spec: str | None) -> tuple[str, str, str | None, str]:
    """
    Разбирает <kind>:<name>[@<ref>] и необязательный <repo-spec>.

    repo-spec может быть:
      — Полным URL (https://, git://, ssh://)
      — Сокращением (user/repo, gitlab:user/repo, ...)
      — Путь к локальному git-репозиторию
    """
    pattern = r"^(?P<kind>[^:@]+):(?P<name>[^@]+)(?:@(?P<ref>.+))?$"
    m = re.match(pattern, what.strip())
    if not m:
        print(f"[YAL] {t('errors.parse-spec', spec=what)}")
        sys.exit(1)

    kind = m.group("kind").lower()
    name = m.group("name")
    ref = m.group("ref") or None

    if is_builtin(kind, name):
        print(f"[YAL] {t('add.builtin-conflict', kind=kind, name=name)}")
        sys.exit(1)

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
