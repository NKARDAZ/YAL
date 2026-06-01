"""
Обёртка для обратной совместимости.

Весь функционал перенесён в yal/git_provider.py.
Этот модуль реэкспортирует публичный API чтобы не ломать
существующие импорты вида `from yal import github`.
"""

from yal.git_provider import (  # noqa: F401
    ReleaseInfo,
    CommitInfo,
    get_releases,
    get_latest_commit,
    get_commit,
    download_release,
    clone_repo,
    _force_remove_readonly,
)
