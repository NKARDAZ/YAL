"""
Запись ответов пользователя в .yal/answers.yml.

Сохраняет все значения полей из template.toml после интерактивного опроса.
Формат:
    fields:
      - id: "field-name"
        value: field's final value
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from ruamel.yaml import YAML


def write_answers(project_dir: Path, values: dict[str, Any]) -> None:
    """
    Записывает ответы пользователя в .yal/answers.yml.

    Args:
        project_dir: Корень созданного проекта
        values: Словарь с ответами пользователя {field_id: value}
    """
    answers_path = project_dir / ".yal" / "answers.yml"
    answers_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, list[dict[str, Any]]] = {"fields": []}

    for field_id, value in values.items():
        entry: dict[str, Any] = {"id": field_id}

        if isinstance(value, list):
            entry["value"] = [str(v) for v in value]
        elif isinstance(value, bool):
            entry["value"] = value
        elif isinstance(value, (int, float)):
            entry["value"] = value
        elif value is None:
            entry["value"] = ""
        else:
            entry["value"] = str(value)

        data["fields"].append(entry)

    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.preserve_quotes = True

    with open(answers_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
