from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from random import Random
from threading import Event
from time import monotonic


LIMIT = 1_000_000_000
OPERATORS = ("+", "-", "×", "÷")
PRECEDENCE = {"+": 1, "-": 1, "×": 2, "÷": 2}
Progress = Callable[[int, int], None]


@dataclass(frozen=True)
class Config:
    count: int = 20
    min_numbers: int = 2
    max_numbers: int = 2
    minimum: int = 0
    maximum: int = 20
    mul_div: bool = False
    brackets: bool = False
    negative: bool = False
    remainder: bool = False
    fractions: bool = False

    def __post_init__(self) -> None:
        for name, value, low, high in (
            ("题目数量", self.count, 1, 10_000),
            ("每题最小数字个数", self.min_numbers, 2, 16),
            ("每题最大数字个数", self.max_numbers, 2, 16),
            ("最小数值", self.minimum, 0, 100),
            ("最大数值", self.maximum, 0, 100),
        ):
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name}必须是 {low}～{high} 的整数。")
        if self.max_numbers < self.min_numbers:
            raise ValueError("每题最大数字个数不能低于每题最小数字个数。")
        if self.minimum > self.maximum:
            raise ValueError("最小数值不能大于最大数值。")


@dataclass(frozen=True)
class Question:
    expression: str
    value: Fraction
    remainder: int = 0

    @property
    def answer(self) -> str:
        if self.remainder:
            return f"{self.value.numerator}...{self.remainder}"
        return str(self.value)


@dataclass(frozen=True)
class Worksheet:
    config: Config
    questions: tuple[Question, ...]


class CancelledError(Exception):
    pass


class GenerationError(Exception):
    pass


class _Rejected(Exception):
    pass


@dataclass(frozen=True)
class _Expression:
    text: str
    value: Fraction
    operator: str = ""


def check_cancelled(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise CancelledError()


def _calculate(
    left: Fraction, right: Fraction, op: str, config: Config, *, fractional_division: bool,
) -> Fraction:
    if (op in ("+", "-") and right == 0) or (op in ("×", "÷") and right == 1):
        raise _Rejected()
    if op == "+":
        value = left + right
    elif op == "-":
        value = left - right
    elif op == "×":
        value = left * right
    elif op == "÷":
        if right == 0:
            raise _Rejected()
        value = left / right
        if not fractional_division and value.denominator != 1:
            raise _Rejected()
    else:
        raise ValueError(f"未知运算符：{op}")
    if (not config.negative and value < 0) or (
        abs(value.numerator) > LIMIT or value.denominator > LIMIT
    ):
        raise _Rejected()
    return value


def _combine(left: _Expression, right: _Expression, op: str, config: Config) -> _Expression:
    value = _calculate(left.value, right.value, op, config, fractional_division=config.fractions)
    a, b = left.text, right.text
    if config.brackets:
        if left.operator:
            a = f"({a})"
        if right.operator:
            b = f"({b})"
    return _Expression(f"{a} {op} {b}", value, op)


def _leaf(rng: Random, config: Config) -> _Expression:
    value = rng.randint(config.minimum, config.maximum)
    return _Expression(str(value), Fraction(value))


def _tree(rng: Random, config: Config, numbers: int, operators: tuple[str, ...]) -> _Expression:
    if numbers == 1:
        return _leaf(rng, config)
    split = rng.randrange(1, numbers)
    left = _tree(rng, config, split, operators)
    right = _tree(rng, config, numbers - split, operators)
    return _combine(left, right, rng.choice(operators), config)


def _flat(rng: Random, config: Config, numbers: int, operators: tuple[str, ...]) -> _Expression:
    values = [_leaf(rng, config)]
    pending: list[str] = []

    def reduce() -> None:
        right, left = values.pop(), values.pop()
        values.append(_combine(left, right, pending.pop(), config))

    for _ in range(numbers - 1):
        op = rng.choice(operators)
        while pending and PRECEDENCE[pending[-1]] >= PRECEDENCE[op]:
            reduce()
        pending.append(op)
        values.append(_leaf(rng, config))
    while pending:
        reduce()
    return values[0]


def _binary(left: int, right: int, op: str, config: Config) -> Question:
    value = _calculate(Fraction(left), Fraction(right), op, config, fractional_division=config.remainder)
    remainder = 0
    if op == "÷" and config.remainder:
        quotient, remainder = divmod(left, right)
        value = Fraction(quotient)
    return Question(f"{left} {op} {right}", value, remainder)


def generate(config: Config, cancel: Event | None = None, progress: Progress | None = None) -> Worksheet:
    check_cancelled(cancel)
    rng = Random()
    operators = OPERATORS if config.mul_div else OPERATORS[:2]
    questions: list[Question]
    if progress:
        progress(0, config.count)

    # Enumerate small two-operand spaces to avoid random-search exhaustion near capacity.
    space = (config.maximum - config.minimum + 1) ** 2 * len(operators)
    if config.min_numbers == config.max_numbers == 2 and space <= 20_000:
        pool: list[Question] = []
        for left in range(config.minimum, config.maximum + 1):
            for right in range(config.minimum, config.maximum + 1):
                for op in operators:
                    check_cancelled(cancel)
                    try:
                        pool.append(_binary(left, right, op, config))
                    except _Rejected:
                        continue
        if len(pool) < config.count:
            raise GenerationError(
                f"当前条件下只有 {len(pool)} 道不重复的题目，无法生成 {config.count} 道。\n"
                "请减少题目数量、增大数值范围或放宽运算限制。"
            )
        questions = rng.sample(pool, config.count)
    else:
        questions = []
        seen: set[str] = set()
        budget = config.count * 2000 + 10_000
        last_report = monotonic()
        for _ in range(budget):
            check_cancelled(cancel)
            if progress and monotonic() - last_report >= 0.1:
                progress(len(questions), config.count)
                last_report = monotonic()
            try:
                numbers = rng.randint(config.min_numbers, config.max_numbers)
                if numbers == 2:
                    candidate = _binary(
                        rng.randint(config.minimum, config.maximum),
                        rng.randint(config.minimum, config.maximum),
                        rng.choice(operators), config,
                    )
                else:
                    expression = (
                        _tree(rng, config, numbers, operators)
                        if config.brackets else _flat(rng, config, numbers, operators)
                    )
                    candidate = Question(expression.text, expression.value)
            except _Rejected:
                continue
            if candidate.expression in seen:
                continue
            seen.add(candidate.expression)
            questions.append(candidate)
            if len(questions) == config.count:
                break
        if len(questions) != config.count:
            raise GenerationError(
                f"在尝试上限内只找到 {len(questions)} / {config.count} 道不重复的题目。\n"
                "这不代表数学上不存在足够题目。请减少数量、扩大范围或放宽限制。"
            )
    check_cancelled(cancel)
    if progress:
        progress(config.count, config.count)
    return Worksheet(config, tuple(questions))