"""
Мини-язык логических выражений для show-if в .yal/template.toml.
Безопасный парсер без eval(), работает только с уже собранными значениями полей.
"""

from __future__ import annotations

import re
from typing import Any


class ParseError(Exception):
    """Ошибка парсинга выражения show-if."""
    pass


class EvalError(Exception):
    """Ошибка вычисления выражения show-if."""
    pass


# ─── токенайзер ──────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r'''
    \s*(?:
        (?:and|or|not|in)\b     # ключевые слова
        |\(|\)                  # скобки
        |==|!=|<=|>=|<|>        # операторы сравнения
        |'[^']*'                # строки в одинарных кавычках
        |"[^"]*"                # строки в двойных кавычках
        |[a-zA-Z_][a-zA-Z0-9_\-]*  # идентификаторы
        |\d+(?:\.\d+)?          # числа
        |\[                     # начало списка
        |\]                     # конец списка
        |,                      # разделитель в списке
    )
''', re.VERBOSE)


def tokenize(expr: str) -> list[str]:
    """Разбивает выражение на токены."""
    tokens = []
    pos = 0
    while pos < len(expr):
        # Пропускаем пробелы
        if expr[pos].isspace():
            pos += 1
            continue

        # Ищем токен
        match = _TOKEN_RE.match(expr, pos)
        if not match:
            raise ParseError(f"Unexpected character at position {pos}: '{expr[pos]}'")

        token = match.group(0).strip()
        if token:  # игнорируем пустые
            tokens.append(token)
        pos = match.end()

    return tokens


# ─── парсер ──────────────────────────────────────────────────────────────────

class Parser:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def next(self) -> str:
        tok = self.peek()
        if tok is None:
            raise ParseError("Unexpected end of expression")
        self.pos += 1
        return tok

    def expect(self, expected: str) -> None:
        tok = self.next()
        if tok != expected:
            raise ParseError(f"Expected '{expected}', got '{tok}'")

    def parse_expr(self) -> Any:
        """expr := or_expr"""
        return self.parse_or()

    def parse_or(self) -> Any:
        """or_expr := and_expr (('or') and_expr)*"""
        left = self.parse_and()
        while self.peek() == "or":
            self.next()
            right = self.parse_and()
            left = ("or", left, right)
        return left

    def parse_and(self) -> Any:
        """and_expr := unary (('and') unary)*"""
        left = self.parse_unary()
        while self.peek() == "and":
            self.next()
            right = self.parse_unary()
            left = ("and", left, right)
        return left

    def parse_unary(self) -> Any:
        """unary := ['not'] primary"""
        if self.peek() == "not":
            self.next()
            return ("not", self.parse_primary())
        return self.parse_primary()

    def parse_primary(self) -> Any:
        """primary := '(' expr ')' | comparison"""
        if self.peek() == "(":
            self.next()
            node = self.parse_expr()
            self.expect(")")
            return node
        return self.parse_comparison()

    def parse_comparison(self) -> Any:
        """
        comparison := operand [op operand]
        op := '==' | '!=' | '<' | '<=' | '>' | '>=' | 'in' | 'not in'
        """
        left = self.parse_operand()

        op = self.peek()
        if op in ("==", "!=", "<", "<=", ">", ">="):
            self.next()
            right = self.parse_operand()
            return (op, left, right)
        elif op == "not":
            # not in — специальный случай
            self.next()
            if self.peek() != "in":
                raise ParseError("Expected 'in' after 'not'")
            self.next()
            right = self.parse_operand()
            return ("not in", left, right)
        elif op == "in":
            self.next()
            right = self.parse_operand()
            return ("in", left, right)
        else:
            # Нет оператора — это просто проверка на truthiness
            return ("truthy", left)

    def parse_operand(self) -> Any:
        """operand := identifier | string | number | bool-literal | '[' list ']'"""
        tok = self.peek()
        if tok is None:
            raise ParseError("Expected operand")

        # Идентификатор
        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_\-]*$', tok):
            self.next()
            return ("id", tok)

        # Строка
        if (tok.startswith("'") and tok.endswith("'")) or (tok.startswith('"') and tok.endswith('"')):
            self.next()
            return ("str", tok[1:-1])

        # Число
        if re.match(r'^\d+(?:\.\d+)?$', tok):
            self.next()
            return ("num", float(tok) if '.' in tok else int(tok))

        # Список
        if tok == "[":
            self.next()
            items = []
            while self.peek() != "]":
                if self.peek() == ",":
                    self.next()
                    continue
                items.append(self.parse_operand())
            self.expect("]")
            return ("list", items)

        raise ParseError(f"Unexpected token: '{tok}'")


# ─── AST → значение ─────────────────────────────────────────────────────────

def eval_node(node: Any, values: dict[str, Any]) -> bool:
    """Вычисляет AST-узел."""
    if not isinstance(node, tuple):
        raise EvalError(f"Expected tuple node, got {type(node)}")

    op = node[0]

    if op == "truthy":
        _, identifier = node
        # Извлекаем имя идентификатора из разных форматов
        if isinstance(identifier, tuple) and len(identifier) == 2 and identifier[0] == "id":
            identifier = identifier[1]
        # Если все еще кортеж (например, ("id", "name")), берем второй элемент
        elif isinstance(identifier, tuple) and len(identifier) == 2:
            identifier = identifier[1]
        # Если это строка - оставляем как есть
        elif not isinstance(identifier, str):
            raise EvalError(f"Expected string identifier, got {type(identifier)}")

        val = _resolve_id(identifier, values)
        return bool(val)

    if op == "not":
        _, inner = node
        return not eval_node(inner, values)

    if op in ("and", "or"):
        _, left, right = node
        if op == "and":
            return eval_node(left, values) and eval_node(right, values)
        else:  # or
            return eval_node(left, values) or eval_node(right, values)

    if op in ("==", "!=", "<", "<=", ">", ">=", "in", "not in"):
        _, left, right = node
        left_val = _eval_operand(left, values)
        right_val = _eval_operand(right, values)
        return _compare(op, left_val, right_val)

    raise EvalError(f"Unknown operator: {op}")


def _resolve_id(identifier: str, values: dict[str, Any]) -> Any:
    """Достаёт значение поля из values."""
    if identifier not in values:
        raise EvalError(f"Unknown field: '{identifier}'")
    return values[identifier]


def _eval_operand(operand: Any, values: dict[str, Any]) -> Any:
    """Вычисляет операнд: идентификатор, строку, число или список."""
    if not isinstance(operand, tuple):
        raise EvalError(f"Expected tuple operand, got {type(operand)}")

    op = operand[0]
    val = operand[1]

    if op == "id":
        return _resolve_id(val, values)
    elif op == "str":
        return val
    elif op == "num":
        return val
    elif op == "list":
        return [_eval_operand(item, values) for item in val]
    else:
        raise EvalError(f"Unknown operand type: {op}")


def _compare(op: str, left: Any, right: Any) -> bool:
    """Выполняет сравнение двух значений."""
    # Для 'in' и 'not in' работаем с последовательностями
    if op == "in":
        return left in right if hasattr(right, "__contains__") else False
    if op == "not in":
        return left not in right if hasattr(right, "__contains__") else True

    # Для остальных сравнений — только числа
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        raise EvalError(f"Comparison {op} requires numbers, got {type(left)} and {type(right)}")

    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right

    raise EvalError(f"Unknown comparison operator: {op}")


# ─── публичный API ──────────────────────────────────────────────────────────

def evaluate(expr: str, values: dict[str, Any]) -> bool:
    """
    Парсит и вычисляет выражение show-if.
    Возвращает True, если поле должно быть показано.
    """
    try:
        tokens = tokenize(expr)
        parser = Parser(tokens)
        ast = parser.parse_expr()
        return eval_node(ast, values)
    except (ParseError, EvalError) as e:
        # Безопасное падение: при любой ошибке показываем поле
        return True


# ─── тесты ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Небольшой self-test
    values = {
        "use-ci": True,
        "ci-provider": "github-actions",
        "features": ["auth", "api", "admin"],
        "port": 8080,
        "license": "GPL-3.0",
        "empty": "",
        "zero": 0,
    }

    tests = [
        ("use-ci", True),
        ("not use-ci", False),
        ("ci-provider == 'github-actions'", True),
        ("ci-provider == 'gitlab-ci'", False),
        ("port > 1024", True),
        ("port > 9000", False),
        ("'auth' in features", True),
        ("'db' in features", False),
        ("use-ci and ci-provider == 'github-actions'", True),
        ("use-ci and ci-provider == 'gitlab-ci'", False),
        ("(ci-provider == 'github-actions' or ci-provider == 'gitlab-ci') and use-ci", True),
        ("empty", False),
        ("zero", False),
        ("license in ['GPL-3.0', 'AGPL-3.0']", True),
        ("license in ['MIT', 'Apache-2.0']", False),
    ]

    for expr, expected in tests:
        result = evaluate(expr, values)
        status = "✓" if result == expected else "✗"
        print(f"{status} {expr} → {result} (expected {expected})")
