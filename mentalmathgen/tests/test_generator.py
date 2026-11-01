import ast
from dataclasses import replace
from fractions import Fraction
from itertools import product
from threading import Event
import unittest

from generator import CancelledError, Config, GenerationError, LIMIT, Question, generate


class GeneratorTests(unittest.TestCase):
    def evaluate(self, node: ast.expr, config: Config, numbers: int) -> tuple[Fraction, int]:
        if isinstance(node, ast.Constant):
            assert type(node.value) is int
            self.assertGreaterEqual(node.value, config.minimum)
            self.assertLessEqual(node.value, config.maximum)
            return Fraction(node.value), 1
        assert isinstance(node, ast.BinOp)
        left, a = self.evaluate(node.left, config, numbers)
        right, b = self.evaluate(node.right, config, numbers)
        if isinstance(node.op, ast.Add):
            self.assertNotEqual(right, 0)
            value = left + right
        elif isinstance(node.op, ast.Sub):
            self.assertNotEqual(right, 0)
            value = left - right
        elif isinstance(node.op, ast.Mult):
            self.assertTrue(config.mul_div)
            self.assertNotEqual(right, 1)
            value = left * right
        else:
            self.assertIsInstance(node.op, ast.Div)
            self.assertTrue(config.mul_div)
            self.assertNotEqual(right, 0)
            self.assertNotEqual(right, 1)
            value = left / right
            if not (config.remainder if numbers == 2 else config.fractions):
                self.assertEqual(value.denominator, 1)
        if not config.negative:
            self.assertGreaterEqual(value, 0)
        self.assertLessEqual(abs(value.numerator), LIMIT)
        self.assertLessEqual(value.denominator, LIMIT)
        return value, a + b

    def check_question(self, question: Question, config: Config) -> int:
        tree = ast.parse(question.expression.replace("×", "*").replace("÷", "/"), mode="eval").body
        assert isinstance(tree, ast.BinOp)
        numbers = sum(isinstance(node, ast.Constant) for node in ast.walk(tree))
        self.assertGreaterEqual(numbers, config.min_numbers)
        self.assertLessEqual(numbers, config.max_numbers)
        value, count = self.evaluate(tree, config, numbers)
        self.assertEqual(count, numbers)
        if numbers == 2 and isinstance(tree.op, ast.Div) and config.remainder:
            assert isinstance(tree.left, ast.Constant) and isinstance(tree.right, ast.Constant)
            assert type(tree.left.value) is int and type(tree.right.value) is int
            quotient, remainder = divmod(tree.left.value, tree.right.value)
            self.assertEqual(question.value, quotient)
            self.assertEqual(question.remainder, remainder)
            self.assertEqual(question.answer, f"{quotient}...{remainder}" if remainder else str(quotient))
        else:
            self.assertEqual(question.value, value)
            self.assertEqual(question.answer, str(value))
            self.assertEqual(question.remainder, 0)
        self.assertEqual("(" in question.expression, config.brackets and numbers > 2)
        return numbers

    def test_generated_expressions_obey_rules_and_exact_answers(self):
        cases = product((2, 3, 5), (False, True), (False, True), (False, True), (False, True))
        for numbers, mul_div, brackets, negative, fractions in cases:
            config = Config(
                count=15, min_numbers=numbers, max_numbers=numbers, maximum=10, mul_div=mul_div,
                brackets=brackets, negative=negative, fractions=fractions,
                remainder=fractions, seed=42,
            )
            with self.subTest(config=config):
                sheet = generate(config)
                self.assertEqual(len(sheet.questions), config.count)
                self.assertEqual(len({q.expression for q in sheet.questions}), config.count)
                for question in sheet.questions:
                    self.assertEqual(self.check_question(question, config), numbers)

    def test_mixed_operand_counts_apply_rules_per_question(self):
        for brackets, negative, remainder, fractions in product((False, True), repeat=4):
            config = Config(
                count=100, min_numbers=2, max_numbers=5, maximum=10, mul_div=True,
                brackets=brackets, negative=negative, remainder=remainder, fractions=fractions, seed=42,
            )
            with self.subTest(config=config):
                sheet = generate(config)
                self.assertEqual(len(sheet.questions), 100)
                self.assertEqual(len({q.expression for q in sheet.questions}), 100)
                self.assertEqual({self.check_question(q, config) for q in sheet.questions}, {2, 3, 4, 5})
                self.assertEqual(any(q.remainder for q in sheet.questions), remainder)
                self.assertEqual(any(q.value.denominator != 1 for q in sheet.questions), fractions)

    def test_seed_reproduces_entire_worksheet(self):
        config = Config(count=30, min_numbers=2, max_numbers=5, mul_div=True, brackets=True, fractions=True, negative=True, seed=314)
        self.assertEqual(generate(config), generate(config))
        random_sheet = generate(replace(config, seed=None))
        self.assertEqual(random_sheet.questions, generate(replace(config, seed=random_sheet.seed)).questions)

    def test_two_operand_capacity_and_textual_deduplication(self):
        config = Config(count=9, maximum=2, seed=7)
        sheet = generate(config)
        self.assertEqual(len(sheet.questions), 9)
        self.assertEqual(
            {q.expression for q in sheet.questions},
            {"0 + 1", "0 + 2", "1 + 1", "1 + 2", "2 + 1", "2 + 2", "1 - 1", "2 - 1", "2 - 2"},
        )
        for question in sheet.questions:
            self.check_question(question, config)
        with self.assertRaisesRegex(GenerationError, "只有 9"):
            generate(replace(config, count=10))

    def test_random_two_operand_generation_obeys_operation_rules(self):
        # This range exceeds the enumeration limit, exercising random candidates.
        config = Config(count=1000, maximum=100, mul_div=True, negative=True, remainder=True, seed=42)
        for question in generate(config).questions:
            self.assertEqual(self.check_question(question, config), 2)

    def test_no_zero_divisors_and_zero_range_is_supported(self):
        config = Config(count=1, maximum=0, mul_div=True)
        sheet = generate(config)
        self.assertEqual(sheet.questions, (Question("0 × 0", Fraction(0)),))
        with self.assertRaisesRegex(GenerationError, "只有 1"):
            generate(replace(config, count=2))
        with self.assertRaisesRegex(GenerationError, "只有 0"):
            generate(replace(config, mul_div=False))

    def test_sixteen_operands(self):
        config = Config(count=5, min_numbers=16, max_numbers=16, minimum=1, maximum=3, brackets=True, seed=19)
        for question in generate(config).questions:
            value, count = self.evaluate(ast.parse(question.expression, mode="eval").body, config, 16)
            self.assertEqual(count, 16)
            self.assertEqual(question.value, value)

    def test_random_attempt_limit_reports_incomplete_without_returning_a_sheet(self):
        with self.assertRaisesRegex(GenerationError, "尝试上限"):
            generate(Config(count=5, min_numbers=3, max_numbers=3, maximum=0, seed=1))

    def test_cancellation_before_and_during_generation(self):
        cancel = Event()
        cancel.set()
        with self.assertRaises(CancelledError):
            generate(Config(), cancel)
        cancel.clear()
        with self.assertRaises(CancelledError):
            generate(Config(count=10_000, maximum=100_000), cancel, lambda _completed, _total: cancel.set())

    def test_invalid_configuration(self):
        for kwargs in (
            {"count": 0}, {"count": 10001}, {"count": 1.5},
            {"min_numbers": 1}, {"min_numbers": 17}, {"min_numbers": 2.5},
            {"max_numbers": 1}, {"max_numbers": 17}, {"max_numbers": 2.5},
            {"min_numbers": 4, "max_numbers": 3}, {"minimum": -1}, {"maximum": 1000001},
            {"minimum": 10, "maximum": 9}, {"seed": 0}, {"seed": 2147483648},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                replace(Config(), **kwargs)


if __name__ == "__main__":
    unittest.main()