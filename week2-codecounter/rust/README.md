# Rust codecounter

A standalone Rust rewrite using only the standard library. Existing C files are retained in the parent directory.

## Build and run

From this directory:

```powershell
.\compile.ps1 Debug
.\target\debug\codecounter.exe ..\testcase1

.\compile.ps1 Release
.\target\release\codecounter.exe ..\testcase1
```

The script defaults to Release. Without a directory argument, the program scans the current working directory. Use `--help` or `-h` for help. Elapsed wall time is printed in seconds, including handled error/help paths.

## Counting rules

- Recursively count C, C++, Java, and Python using the same extensions as the C version.
- Each physical line is classified once: blank, comment, or code. Mixed code/comment lines count as code.
- Empty lines inside block comments count as comments; empty lines inside multiline strings count as blank.
- Python docstrings and Java text blocks count as code. C++ raw strings and C/C++ continued line comments are recognized.
- Accept LF, CRLF, and CR line endings, UTF-8 BOM, and BOM-marked UTF-16 in either byte order. Other encodings are scanned as bytes for ASCII syntax.
- Skip symbolic links, Windows reparse points, and files with unsupported extensions.
- Preserve the C version's extension-based selection: binary files with source extensions are not filtered.
- Continue after individual file/directory errors and return 1; invalid argument counts return 2.

The scanner intentionally follows the original lightweight lexical rules rather than implementing complete language parsers.