from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median
from threading import Event
from time import perf_counter
import os
import re
import stat


LANGUAGES = ("C", "C++", "JAVA", "Python", "C#")
COLUMNS = (
    ("language", "语言"),
    ("files", "源文件数"),
    ("code", "代码行数"),
    ("blank", "空行数"),
    ("comment", "注释行数"),
    ("functions", "函数个数"),
    ("maximum", "最大值"),
    ("minimum", "最小值"),
    ("average", "均值"),
    ("median", "中位数"),
)
EXTENSIONS = {
    **dict.fromkeys((".c", ".h"), "C"),
    **dict.fromkeys((".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".ipp", ".inl"), "C++"),
    ".java": "JAVA",
    **dict.fromkeys((".py", ".pyi", ".pyw"), "Python"),
    **dict.fromkeys((".cs", ".csx"), "C#"),
}
SPACE = " \t\f\v"
STARTS = {
    "C": re.compile(r"//|/\*|[\"']"),
    "C++": re.compile(r'//|/\*|R"(?P<raw>[^ ()\\\t\n\f\v]{0,16})\(|["\']'),
    "JAVA": re.compile(r'//|/\*|"""|["\']'),
    "Python": re.compile("#|(?i:(?<!\\w)(?:fr|rf|br|rb|f|r|b|u))?(?:'''|\"\"\"|['\"])"),
    "C#": re.compile(r"""//|/\*|(?:\$+@?|@\$?)?"{3,}|(?:\$@|@\$|@|\$)?"|'"""),
}
TOKENS = re.compile(r"[^\W\d]\w*|\d+\w*|::|=>|->|&&|\.\.\.|[^\s]", re.UNICODE)
PYTHON_FUNCTION = re.compile(
    r"(?:async(?:\s|\\\n)+)?"
    r"def(?:\s|\\\n)+[^\W\d]\w*(?:\s|\\\n)*"
    r"(?:\[[^\]]*\](?:\s|\\\n)*)?\("
)
NON_FUNCTIONS = {
    "if", "for", "foreach", "while", "switch", "catch", "using", "lock",
    "fixed", "sizeof", "alignof", "decltype", "noexcept", "throw", "throws",
    "return", "new", "delete", "typeof", "nameof", "checked", "unchecked",
    "synchronized", "assert", "delegate", "requires", "static_assert",
    "__attribute__", "__declspec",
}


@dataclass
class Counts:
    code: int = 0
    blank: int = 0
    comment: int = 0
    function_lines: list[int] = field(default_factory=list[int])

    @property
    def functions(self) -> int:
        return len(self.function_lines)


@dataclass
class LanguageStats:
    language: str
    files: int = 0
    code: int = 0
    blank: int = 0
    comment: int = 0
    function_lines: list[int] = field(default_factory=list[int], repr=False)

    @property
    def functions(self) -> int:
        return len(self.function_lines)

    def add(self, counts: Counts) -> None:
        self.files += 1
        self.code += counts.code
        self.blank += counts.blank
        self.comment += counts.comment
        self.function_lines.extend(counts.function_lines)

    @property
    def maximum(self) -> int:
        return max(self.function_lines, default=0)

    @property
    def minimum(self) -> int:
        return min(self.function_lines, default=0)

    @property
    def average(self) -> float:
        return mean(self.function_lines) if self.function_lines else 0.0

    @property
    def median(self) -> float:
        return median(self.function_lines) if self.function_lines else 0.0

    def row(self) -> tuple[str, int, int, int, int, int, int, int, str, str]:
        return (
            self.language, self.files, self.code, self.blank, self.comment,
            self.functions, self.maximum, self.minimum,
            f"{self.average:.2f}", f"{self.median:.2f}",
        )


@dataclass(frozen=True)
class ScanError:
    path: Path
    message: str


@dataclass
class ScanResult:
    languages: dict[str, LanguageStats] = field(
        default_factory=lambda: {name: LanguageStats(name) for name in LANGUAGES}
    )
    errors: list[ScanError] = field(default_factory=list[ScanError])
    skipped_binary: list[Path] = field(default_factory=list[Path])
    elapsed: float = 0.0
    cancelled: bool = False

    @property
    def files(self) -> int:
        return sum(item.files for item in self.languages.values())


class ScanCancelled(Exception):
    pass


class BinarySourceError(ValueError):
    pass


def _check_cancel(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ScanCancelled


def decode_source(data: bytes) -> str:
    # Preserve ASCII syntax in legacy encodings instead of dropping unreadable bytes.
    for bom, encoding in (
        (b"\xff\xfe\x00\x00", "utf-32"),
        (b"\x00\x00\xfe\xff", "utf-32"),
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
    ):
        if data.startswith(bom):
            return data.decode(encoding)
    if b"\x00" in data or data.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")):
        raise BinarySourceError("文件内容是二进制，已跳过。")
    return data.decode("utf-8-sig", errors="surrogateescape")


def _line_comment_end(text: str, start: int, continued: bool) -> int:
    end = text.find("\n", start)
    while end != -1 and continued and end > start and text[end - 1] == "\\":
        end = text.find("\n", end + 1)
    return len(text) if end == -1 else end


def _string_end(
    text: str,
    pos: int,
    delimiter: str,
    cancel: Event | None,
    *,
    verbatim: bool = False,
    interpolated: bool = False,
    language: str = "C#",
) -> int:
    while pos < len(text):
        if pos % 4096 == 0:
            _check_cancel(cancel)
        if text.startswith(delimiter, pos):
            if verbatim and text.startswith('""', pos):
                pos += 2
                continue
            return pos + len(delimiter)
        char = text[pos]
        if interpolated and char == "{":
            if text.startswith("{{", pos):
                pos += 2
            else:
                pos = _interpolation_end(text, pos + 1, cancel, language)
        elif char == "\\" and not verbatim:
            pos += 2
        elif char == "\n" and len(delimiter) == 1 and not verbatim:
            return pos
        else:
            pos += 1
    return len(text)


def _interpolation_end(text: str, pos: int, cancel: Event | None, language: str) -> int:
    depth = 1
    while pos < len(text):
        if pos % 4096 == 0:
            _check_cancel(cancel)
        match = STARTS[language].match(text, pos)
        if match is not None:
            pos = _token_end(text, match, language, cancel)
        elif text[pos] == "{":
            depth += 1
            pos += 1
        elif text[pos] == "}":
            depth -= 1
            pos += 1
            if depth == 0:
                return pos
        else:
            pos += 1
    return len(text)


def _token_end(text: str, match: re.Match[str], language: str, cancel: Event | None) -> int:
    opener = match.group()
    if opener in ("//", "#"):
        return _line_comment_end(text, match.end(), language in ("C", "C++"))
    if opener == "/*":
        end = text.find("*/", match.end())
        return len(text) if end == -1 else end + 2
    if language == "C++" and opener.startswith('R"'):
        delimiter = ")" + match.group("raw") + '"'
        end = text.find(delimiter, match.end())
        return len(text) if end == -1 else end + len(delimiter)
    quotes = opener.lstrip("$@") if language != "Python" else opener.lstrip("fFrRbBuU")
    if language == "C#" and len(quotes) >= 3:
        end = text.find(quotes, match.end())
        return len(text) if end == -1 else end + len(quotes)
    return _string_end(
        text, match.end(), quotes, cancel,
        verbatim=language == "C#" and "@" in opener,
        interpolated=(language == "C#" and "$" in opener) or (language == "Python" and "f" in opener.lower()),
        language=language,
    )


def _lex(text: str, language: str, cancel: Event | None) -> tuple[Counts, str, list[int]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    line_count = text.count("\n") + int(bool(text) and not text.endswith("\n"))
    flags = bytearray(line_count)
    cleaned: list[str] = []
    current_line = 0

    def emit(segment: str, kind: str) -> None:
        nonlocal current_line
        parts = segment.split("\n")
        for index, part in enumerate(parts):
            if current_line < line_count:
                if kind == "comment" and (part or index < len(parts) - 1):
                    flags[current_line] |= 1
                elif kind != "comment" and part.strip(SPACE):
                    flags[current_line] |= 2
            if index < len(parts) - 1:
                current_line += 1
        if kind == "code":
            cleaned.append(segment)
        elif language == "Python" and kind == "string":
            # One expression with the same line span, even for a docstring ending at column zero.
            closing = ")" if parts[-1] else ""
            cleaned.append("(" + "\n" * (len(parts) - 1) + closing)
        else:
            cleaned.append("\n".join(" " * len(p) for p in parts))

    pos = 0
    while (match := STARTS[language].search(text, pos)) is not None:
        _check_cancel(cancel)
        start = match.start()
        # C++ digit separators are not character literals.
        if (
            language == "C++" and match.group() == "'" and 0 < start < len(text) - 1
            and text[start - 1].isascii() and text[start - 1].isalnum()
            and text[start + 1].isascii() and text[start + 1].isalnum()
        ):
            emit(text[pos:match.end()], "code")
            pos = match.end()
            continue
        emit(text[pos:start], "code")
        end = min(_token_end(text, match, language, cancel), len(text))
        kind = "comment" if match.group() in ("//", "/*", "#") else "string"
        emit(text[start:end], kind)
        pos = end
    emit(text[pos:], "code")
    # prefix[i] is the number of code lines before physical line i (zero-based).
    prefix = [0]
    for flag in flags:
        prefix.append(prefix[-1] + bool(flag & 2))
    counts = Counts(
        code=prefix[-1],
        blank=flags.count(0),
        comment=sum(flag == 1 for flag in flags),
    )
    return counts, "".join(cleaned), prefix


def _pairs(tokens: list[str]) -> dict[int, int]:
    pairs: dict[int, int] = {}
    stack: list[int] = []
    closing = {")": "(", "]": "[", "}": "{"}
    for index, token in enumerate(tokens):
        if token in ("(", "[", "{"):
            stack.append(index)
        elif token in closing and stack and tokens[stack[-1]] == closing[token]:
            start = stack.pop()
            pairs[start] = index
            pairs[index] = start
    return pairs


def _function_name(tokens: list[str], opening: int, pairs: dict[int, int]) -> int | None:
    index = opening - 1
    if index < 0:
        return None
    if tokens[index] in (")", "]") and index in pairs:
        before = pairs[index] - 1
        if before >= 0 and tokens[before] == "operator":
            return before
        return None
    if tokens[index] == ">":
        depth = 1
        index -= 1
        while index >= 0 and depth:
            if tokens[index] == ">":
                depth += 1
            elif tokens[index] == "<":
                depth -= 1
            index -= 1
    if index >= 0 and tokens[index].isidentifier():
        return index
    for candidate in range(index, max(-1, index - 4), -1):
        if tokens[candidate] == "operator":
            return candidate
        if tokens[candidate] in (";", "{", "}", "(", ")"):
            break
    return None


def _body_after(tokens: list[str], closing: int, pairs: dict[int, int], language: str) -> int | None:
    pos = closing + 1
    while pos < len(tokens):
        token = tokens[pos]
        if token == "{":
            return pos
        if token == "=>" and language == "C#":
            return pos
        if token in ("const", "volatile", "override", "final", "mutable", "&", "&&"):
            pos += 1
        elif token in ("noexcept", "throw", "__attribute__", "__declspec"):
            pos += 1
            if pos < len(tokens) and tokens[pos] == "(":
                if pos not in pairs:
                    return None
                pos = pairs[pos] + 1
        elif token == "[" and pos in pairs:
            pos = pairs[pos] + 1
        elif token in ("throws", "where", "->", "requires"):
            pos += 1
            while pos < len(tokens) and tokens[pos] not in ("{", ";", "=", "=>"):
                if tokens[pos] in ("(", "[") and pos in pairs:
                    pos = pairs[pos] + 1
                else:
                    pos += 1
        elif token == ":" and language in ("C++", "C#"):
            # Constructor initializers may use either parentheses or braces.
            pos += 1
            while pos < len(tokens):
                while pos < len(tokens) and tokens[pos] not in ("(", "{", ";", "}"):
                    pos += 1
                if pos >= len(tokens) or tokens[pos] not in ("(", "{") or pos not in pairs:
                    return None
                pos = pairs[pos] + 1
                if pos < len(tokens) and tokens[pos] == ",":
                    pos += 1
                    continue
                break
        else:
            return None
    return None


def _python_function_ranges(cleaned: str) -> Iterator[tuple[int, int]]:
    """Yield half-open physical line ranges, closing suites at the next logical dedent."""
    active: list[tuple[int, int]] = []  # indentation, first line
    offset = 0
    depth = 0
    continued = False
    lines = cleaned.split("\n")
    if lines[-1] == "":
        lines.pop()
    for number, line in enumerate(lines):
        content = line.lstrip(" \t\f")
        if content and not continued:
            leading = len(line) - len(content)
            indent = len(line[:leading].rsplit("\f", 1)[-1].expandtabs())
            while active and indent <= active[-1][0]:
                yield active.pop()[1], number
            if PYTHON_FUNCTION.match(cleaned, offset + leading):
                active.append((indent, number))
        depth += line.count("(") + line.count("[") + line.count("{")
        depth -= line.count(")") + line.count("]") + line.count("}")
        continued = depth > 0 or line.endswith("\\")
        offset += len(line) + 1
    while active:
        yield active.pop()[1], len(lines)


def _expression_end(tokens: list[str], body: int, pairs: dict[int, int]) -> int:
    """C# expression bodies end at the semicolon outside any nested expression."""
    index = body + 1
    while index < len(tokens):
        token = tokens[index]
        if token == ";":
            return index
        if token == "}":
            return index - 1
        if token in ("(", "[", "{") and index in pairs:
            index = pairs[index]
        index += 1
    return len(tokens) - 1


def _function_ranges(cleaned: str, language: str) -> Iterator[tuple[int, int]]:
    if language == "Python":
        yield from _python_function_ranges(cleaned)
        return
    if language in ("C", "C++"):
        cleaned = re.sub(
            r"(?m)^[ \t]*#(?:[^\n]*\\\n)*[^\n]*",
            lambda match: "\n" * match.group().count("\n"), cleaned,
        )
    tokens: list[str] = []
    lines: list[int] = []
    for number, line in enumerate(cleaned.split("\n")):
        line_tokens: list[str] = TOKENS.findall(line)
        tokens.extend(line_tokens)
        lines.extend([number] * len(line_tokens))
    pairs = _pairs(tokens)
    bodies: set[int] = set()
    boundary = 0
    for opening, token in enumerate(tokens):
        if token in (";", "{", "}"):
            boundary = opening + 1
        elif (
            language == "C++" and token == ":" and opening > 0
            and tokens[opening - 1] in ("public", "protected", "private")
        ):
            boundary = opening + 1
        if token != "(" or opening not in pairs:
            continue
        name = _function_name(tokens, opening, pairs)
        if name is None or tokens[name] in NON_FUNCTIONS:
            continue
        if name > 0 and tokens[name - 1] in (".", "->", "@", "new"):
            continue
        # Ignore attributes, arguments, and constraints when examining the prefix.
        prefix: list[str] = []
        pos = boundary
        while pos < name:
            if tokens[pos] in ("(", "[") and pos in pairs and pairs[pos] < name:
                pos = pairs[pos] + 1
            else:
                prefix.append(tokens[pos])
                pos += 1
        if any(word in prefix for word in ("=", "return", "new", "class", "struct", "record", "interface", "enum", "union")):
            continue
        body = _body_after(tokens, pairs[opening], pairs, language)
        if body is None or body in bodies:
            continue
        bodies.add(body)
        if tokens[body] == "{":
            end = pairs.get(body, len(tokens) - 1)
        else:
            end = _expression_end(tokens, body, pairs)
        yield lines[boundary], lines[end] + 1


def count_functions(cleaned: str, language: str) -> int:
    return sum(1 for _ in _function_ranges(cleaned, language))


def count_source(data: bytes, language: str, cancel: Event | None = None) -> Counts:
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    _check_cancel(cancel)
    counts, cleaned, prefix = _lex(decode_source(data), language, cancel)
    _check_cancel(cancel)
    for start, stop in _function_ranges(cleaned, language):
        _check_cancel(cancel)
        counts.function_lines.append(prefix[stop] - prefix[start])
    return counts


def scan_directory(
    directory: Path,
    cancel: Event | None = None,
    progress: Callable[[int, Path], None] | None = None,
) -> ScanResult:
    directory = Path(directory).expanduser()
    metadata = directory.stat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise NotADirectoryError(f"不是目录：{directory}")
    result = ScanResult()
    started = perf_counter()
    pending = [directory]
    last_progress = started

    def report(path: Path, error: Exception) -> None:
        result.errors.append(ScanError(path, str(error)))

    try:
        while pending:
            _check_cancel(cancel)
            current = pending.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        _check_cancel(cancel)
                        path = Path(entry.path)
                        try:
                            metadata = entry.stat(follow_symlinks=False)
                            if (
                                stat.S_ISLNK(metadata.st_mode)
                                or getattr(metadata, "st_file_attributes", 0)
                                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                            ):
                                continue
                            if stat.S_ISDIR(metadata.st_mode):
                                pending.append(path)
                            elif stat.S_ISREG(metadata.st_mode):
                                language = EXTENSIONS.get(path.suffix.lower())
                                if language is not None:
                                    counts = count_source(path.read_bytes(), language, cancel)
                                    result.languages[language].add(counts)
                        except BinarySourceError:
                            result.skipped_binary.append(path)
                        except (OSError, UnicodeError, ValueError) as error:
                            report(path, error)
                        now = perf_counter()
                        if progress is not None and now - last_progress >= 0.1:
                            progress(result.files, path)
                            last_progress = now
            except OSError as error:
                report(current, error)
    except ScanCancelled:
        result.cancelled = True
    result.elapsed = perf_counter() - started
    return result


def format_report(result: ScanResult) -> str:
    headings = ("Language", "files", "code", "blank", "comment", "functions", "max", "min", "mean", "median")
    rows = [headings, *(tuple(str(value) for value in item.row()) for item in result.languages.values())]
    widths = [max(len(row[index]) for row in rows) for index in range(len(headings))]
    lines = [
        "  ".join(value.ljust(widths[index]) if index == 0 else value.rjust(widths[index]) for index, value in enumerate(row))
        for row in rows
    ]
    lines.append(f"Elapsed time: {result.elapsed:.6f} seconds.")
    return "\n".join(lines)