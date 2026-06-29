from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from ruamel.yaml import YAML
from yal.version import get_version

YAL_PROJECT_YML = ".yal/project.yml"

# Настройка YAML парсера
yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.allow_unicode = True

def fill_yal_project_origin(
    project_dir: Path,
    template: str,
    template_version: str,
) -> None:
    """
    Подставляет значения в [origin] внутри project_dir/.yal/project.yml.

    project_dir      — корень созданного проекта
    template         — вид шаблона, например "book"
    template_version — версия шаблона, например "1.2.0" или "c651f7d"
    """
    yml_path = project_dir / YAL_PROJECT_YML
    yml_path.parent.mkdir(parents=True, exist_ok=True)

    # Загружаем существующий файл или создаём новый
    if yml_path.exists():
        with open(yml_path, "r", encoding="utf-8") as f:
            data = yaml.load(f) or {}
    else:
        data = {}

    # Убеждаемся, что есть секция origin
    if "origin" not in data:
        data["origin"] = {}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    data["origin"]["template"] = template
    data["origin"]["template-version"] = template_version
    data["origin"]["created-at"] = now
    data["origin"]["yal-version"] = get_version()

    # Записываем обратно
    with open(yml_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
