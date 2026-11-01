from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from counter import (
    Counts, EXTENSIONS, LANGUAGES, LanguageStats, ScanCancelled,
    count_source, format_report, scan_directory,
)


class SourceTests(unittest.TestCase):
    def check_counts(
        self, language: str, source: str | bytes, *,
        code: int, blank: int = 0, comment: int = 0, functions: int = 0,
    ) -> None:
        data = source.encode("utf-8") if isinstance(source, str) else source
        result = count_source(data, language)
        self.assertEqual(result, Counts(code, blank, comment, functions))

    def test_empty_files_and_physical_line_endings(self):
        for source, code, blank in (
            ("", 0, 0), ("\n", 0, 1), (" \t\n\nx", 1, 2),
            ("a\rb\r\nc\n", 3, 0), ("\v\f", 0, 1), ("x\n\n", 1, 1),
        ):
            with self.subTest(source=source):
                self.check_counts("C", source, code=code, blank=blank)

    def test_comments_and_mixed_lines(self):
        self.check_counts(
            "C", "// heading\n\nint x = 0; // mixed\n/* block\n\n*/\n"
            'char *s = "// not a comment";\n',
            code=2, blank=1, comment=4,
        )

    def test_comment_termination_and_code_after_block(self):
        self.check_counts("C", "/* a */ int f() {} // b\n/* unfinished\n\n",
                          code=1, comment=2, functions=1)

    def test_continued_c_comments(self):
        self.check_counts("C++", "// first \\\nsecond \\\nthird\nint x;\n",
                          code=1, comment=3)
        self.check_counts("JAVA", "// first \\\nint x;\n", code=1, comment=1)

    def test_escaped_and_continued_strings(self):
        self.check_counts("C", 'char *s = "\\" /*";\nchar *t = "line\\\n// string";\n',
                          code=3)
        self.check_counts("C", 'char *s = "unterminated\n// real comment\n',
                          code=1, comment=1)

    def test_cpp_raw_strings_and_digit_separators(self):
        self.check_counts(
            "C++", 'auto text = R"tag(// text\n\nint fake() {}\n)tag";\n'
            "auto n = 1'000;\nint real() { return 1; }\n",
            code=5, blank=1, functions=1,
        )

    def test_cpp_definitions_operators_and_initializers(self):
        source = (
            "int prototype(int);\n"
            "#define FAKE(x) { x; }\n"
            "#define OTHER(x) \\\n int macro_function() {}\n"
            "struct Thing {\n"
            "Thing(int x) : value{x}, other(1) {}\n"
            "~Thing() {}\n"
            "int operator()(int x) const noexcept { return x; }\n"
            "Thing operator+(const Thing& rhs) const { return rhs; }\n"
            "int method() const { if (test()) {} return 0; }\n"
            "int value; int other;\n"
            "};\n"
            "auto make() -> Thing { return Thing(1); }\n"
            "auto lambda = [](int x) { return x; };\n"
            "int ordinary() { auto local = [&]() {}; return 1; }\n"
        )
        self.assertEqual(count_source(source.encode(), "C++").functions, 7)

    def test_java_methods_constructors_annotations_and_text_blocks(self):
        source = (
            "record Data(int value) {}\n"
            "class Example {\n"
            "Example() {}\n"
            '@Name(value = "value") public int method() throws Exception { return 1; }\n'
            'String text = """\nint fake() {}\n""";\n'
            "abstract void declaration();\n"
            "Runnable action = () -> { run(); };\n"
            "Object obj = new Object() { public String toString() { return text; } };\n"
            "}\n"
        )
        self.assertEqual(count_source(source.encode(), "JAVA").functions, 3)

    def test_python_docstrings_methods_and_async_functions(self):
        self.check_counts(
            "Python",
            '"""module\n\nnot a comment\n"""\n'
            "# def fake(): pass\n"
            "class Example:\n"
            "    async def run(self):\n"
            "        def local(): return 1\n"
            "        return local()\n"
            "def stub(value: int) -> int: ...\n"
            "def generic[T](value: T) -> T: return value\n"
            "callback = lambda x: x\n",
            code=10, blank=1, comment=1, functions=4,
        )

    def test_python_strings_containing_fake_definitions(self):
        self.check_counts(
            "Python", "s = '''def fake():\n    pass # text\n'''\n"
            's = "# not a comment"\n# real comment\n',
            code=4, comment=1,
        )

    def test_python_nested_fstring_expressions_are_not_definitions(self):
        source = 's = f"{call("def fake(): pass")}"\n'
        self.check_counts("Python", source, code=1)

    def test_csharp_strings_and_interpolation(self):
        source = (
            'string regular = "// not a comment";\n'
            'string verbatim = @"a ""quote""\n\nvoid Fake() {}\n";\n'
            'string raw = """\nvoid Other() {} // text\n""";\n'
            'string interpolated = $"{Call("void FakeAgain() {}")}";\n'
            'string mixed = $@"{Call(@"// still a string")}";\n'
            "// actual comment\n"
        )
        self.check_counts("C#", source, code=9, blank=1, comment=1)

    def test_csharp_definitions_and_expression_bodies(self):
        source = (
            "record Person(string Name);\n"
            "class Example : Parent {\n"
            "public Example() : base(1) {}\n"
            "~Example() {}\n"
            '[Attr(Name = "foo")] public int Square(int x) => x * x;\n'
            "public T Identity<T>(T x) where T : class { return x; }\n"
            "public async Task Run() { int Local() => 1; await Work(); }\n"
            "public int Property { get { return 1; } set {} }\n"
            "public int Other => Square(2);\n"
            "Func<int, int> lambda = x => x + 1;\n"
            "Func<int, int> other = (x) => { return x; };\n"
            "Action anonymous = delegate() {};\n"
            "void declaration();\n"
            "public static Example operator +(Example a, Example b) { return a; }\n"
            "}\n"
        )
        self.assertEqual(count_source(source.encode(), "C#").functions, 7)

    def test_bom_encodings_and_legacy_bytes(self):
        source = "// 中文\nint f() { return 1; }\n"
        for encoding in ("utf-8-sig", "utf-16", "utf-32", "gbk"):
            with self.subTest(encoding=encoding):
                self.check_counts("C", source.encode(encoding), code=1, comment=1, functions=1)
        self.check_counts("C", b"\xfe\xff" + source.encode("utf-16-be"),
                          code=1, comment=1, functions=1)
        self.check_counts("C", b"// \xff\nint x;\n", code=1, comment=1)
        with self.assertRaises(UnicodeError):
            count_source(b"\xff\xfe\x00", "C")

    def test_statistics_use_code_lines_of_each_file_including_zero(self):
        stats = LanguageStats("C")
        for code in (0, 2, 4, 9):
            stats.add(Counts(code=code, functions=1))
        self.assertEqual(stats.files, 4)
        self.assertEqual((stats.code, stats.functions), (15, 4))
        self.assertEqual((stats.maximum, stats.minimum, stats.average, stats.median), (9, 0, 3.75, 3))
        stats.add(Counts(code=5))
        self.assertEqual(stats.median, 4)
        empty = LanguageStats("C")
        self.assertEqual((empty.maximum, empty.minimum, empty.average, empty.median), (0, 0, 0, 0))

    def test_cancellation_before_counting(self):
        cancel = Event()
        cancel.set()
        with self.assertRaises(ScanCancelled):
            count_source(b"int x;", "C", cancel)


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parent
        self.temporary = TemporaryDirectory(prefix="codecounter-test-", dir=parent)
        self.root = Path(self.temporary.name).resolve()
        self.assertEqual(self.root.parent, parent)
        self.addCleanup(self.temporary.cleanup)

    def write(self, name: str, data: str | bytes) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
        return path

    def test_nested_directories_languages_and_file_statistics(self):
        self.write("中文 空格/one.C", "int f() {}\n")
        self.write("中文 空格/empty.h", "")
        self.write("two.HPP", "// header\n")
        self.write("three.java", "class Three { void f() {} }\n")
        self.write("four.PYI", "def stub() -> None: ...\n")
        self.write("five.cs", "class Five { int f() => 1; }\n")
        self.write("ignored.txt", "not source\n")
        result = scan_directory(self.root)
        self.assertFalse(result.errors)
        self.assertEqual(tuple(result.languages), LANGUAGES)
        self.assertEqual(result.files, 6)
        c = result.languages["C"]
        self.assertEqual((c.files, c.code, c.minimum, c.maximum, c.average, c.median), (2, 1, 0, 1, 0.5, 0.5))
        for language in ("JAVA", "Python", "C#"):
            self.assertEqual(result.languages[language].functions, 1)

    def test_binary_files_with_source_extensions_are_skipped(self):
        self.write("photo.cpp", b"\xff\xd8\xff\xe0JPEG")
        self.write("binary.py", b"text\x00bytes")
        self.write("utf16.cs", "class C {}".encode("utf-16"))
        result = scan_directory(self.root)
        self.assertEqual(result.files, 1)
        self.assertEqual(len(result.skipped_binary), 2)
        self.assertNotIn("Skipped binary files", format_report(result))
        self.assertEqual(result.languages["C#"].code, 1)
        self.assertFalse(result.errors)

    def test_empty_directory(self):
        result = scan_directory(self.root)
        self.assertEqual(result.files, 0)
        self.assertFalse(result.errors)
        self.assertTrue(all(item.maximum == 0 for item in result.languages.values()))

    def test_bad_root(self):
        with self.assertRaises(FileNotFoundError):
            scan_directory(self.root / "missing")
        file = self.write("ordinary.txt", "content")
        with self.assertRaises(NotADirectoryError):
            scan_directory(file)

    def test_file_read_error_keeps_successful_results(self):
        self.write("good.c", "int good() {}\n")
        self.write("bad.c", "int bad() {}\n")
        read = Path.read_bytes

        def read_bytes(path: Path) -> bytes:
            if path.name == "bad.c":
                raise PermissionError("test read denied")
            return read(path)

        with patch("counter.Path.read_bytes", read_bytes):
            result = scan_directory(self.root)
        self.assertEqual(result.files, 1)
        self.assertEqual(result.languages["C"].functions, 1)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].path.name, "bad.c")

    def test_bad_encoding_is_reported_without_aborting(self):
        self.write("good.py", "pass\n")
        self.write("bad.c", b"\xff\xfe\x00")
        result = scan_directory(self.root)
        self.assertEqual(result.files, 1)
        self.assertEqual(len(result.errors), 1)

    def test_inaccessible_subdirectory_keeps_other_files(self):
        self.write("blocked/skip.c", "int x;")
        self.write("good.c", "int x;")
        import os
        scandir = os.scandir

        def open_directory(path: Path):
            if Path(path).name == "blocked":
                raise PermissionError("test directory denied")
            return scandir(path)

        with patch("counter.os.scandir", open_directory):
            result = scan_directory(self.root)
        self.assertEqual(result.files, 1)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].path.name, "blocked")

    def test_symlinks_are_not_followed(self):
        target = self.write("actual/source.c", "int x;")
        try:
            (self.root / "alias.c").symlink_to(target)
            (self.root / "loop").symlink_to(self.root, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Creating symlinks is unavailable: {error}")
        result = scan_directory(self.root)
        self.assertEqual(result.files, 1)
        self.assertFalse(result.errors)

    def test_cancel_during_scan_returns_partial_results(self):
        for index in range(5):
            self.write(f"file{index}.c", "int x;")
        cancel = Event()
        ticks = iter(index / 5 for index in range(100))
        with patch("counter.perf_counter", side_effect=lambda: next(ticks)):
            result = scan_directory(self.root, cancel, lambda _files, _path: cancel.set())
        self.assertTrue(result.cancelled)
        self.assertEqual(result.files, 1)

    def test_every_supported_extension(self):
        for index, extension in enumerate(EXTENSIONS):
            self.write(f"source{index}{extension.upper()}", "")
        result = scan_directory(self.root)
        self.assertEqual(result.files, len(EXTENSIONS))


if __name__ == "__main__":
    unittest.main()