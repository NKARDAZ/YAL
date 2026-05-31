from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from yal.version import get_version

YAL_PROJECT_TOML = "yal.toml"


def fill_yal_toml_origin(
    project_dir: Path,
    template: str,
    template_version: str,
) -> None:
    """
    Подставляет значения в [origin] внутри project_dir/yal.toml.

    project_dir      — корень созданного проекта
    template         — вид шаблона, например "book"
    template_version — версия шаблона, например "1.2.0" или "c651f7d"
    """
    toml_path = project_dir / YAL_PROJECT_TOML
    if not toml_path.exists():
        with open(toml_path, "w", encoding="utf-8") as f:
            f.write("[origin]\n")
            f.write('template = ""\n')
            f.write('template-version = ""\n')
            f.write('created-at = ""\n')
            f.write('yal-version = ""\n')

    text = toml_path.read_text(encoding="utf-8")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    replacements = {
        "template": template,
        "template-version": template_version,
        "created-at": now,
        "yal-version": get_version(),
    }

    for key, value in replacements.items():
        pattern = rf'(?m)^(\s*{re.escape(key)}\s*=\s*)"".*?(\r?\n|$)'
        replacement = rf'\g<1>"{value}"\2'
        text = re.sub(pattern, replacement, text)

    toml_path.write_text(text, encoding="utf-8")
