#define _CRT_SECURE_NO_WARNINGS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <wctype.h>
#include <ctype.h>

/* Windows: cl /nologo /W4 /utf-8 /TC codecounter.c
 * Physical lines are exclusive: blank, comment-only, or code (including mixed).
 * Blank lines inside comments count as comments; inside strings as blank. Python docstrings
 * are code. Headers .h belong to C; .hpp/.hh/.hxx belong to C++.
 * Non-source files and reparse points are skipped.
 */
enum { SLASH=1, BLOCK=2, HASH=4, PYTHON=8, CPP=16, JAVA=32 };
typedef struct {
    const char *name;
    const wchar_t *extensions;
    unsigned syntax;
    unsigned long long files, blank, comment, code;
} Language;
static Language languages[] = {
    {"C", L".c.h.", SLASH|BLOCK, 0,0,0,0},
    {"C++", L".cpp.cc.cxx.hpp.hh.hxx.ipp.inl.", SLASH|BLOCK|CPP, 0,0,0,0},
    {"Java", L".java.", SLASH|BLOCK|JAVA, 0,0,0,0},
    {"Python", L".py.pyi.pyw.", HASH|PYTHON, 0,0,0,0}
};
#define LANGUAGE_COUNT (sizeof languages / sizeof languages[0])
static int errors;
static LARGE_INTEGER start_time, timer_frequency;

static void print_elapsed(void)
{
    LARGE_INTEGER end_time;
    QueryPerformanceCounter(&end_time);
    printf("Elapsed time: %.6f seconds.\n",
           (double)(end_time.QuadPart - start_time.QuadPart) / timer_frequency.QuadPart);
}

static void *allocate(size_t size)
{
    void *p = malloc(size ? size : 1);
    if (!p) { fputs("Out of memory.\n", stderr); exit(1); }
    return p;
}

static void report(const wchar_t *path, const char *message)
{
    int size = WideCharToMultiByte(CP_UTF8, 0, path, -1, NULL, 0, NULL, NULL);
    char *name = (char *)allocate((size_t)size);
    WideCharToMultiByte(CP_UTF8, 0, path, -1, name, size, NULL, NULL);
    fprintf(stderr, "%s: %s\n", message, name);
    free(name);
    errors = 1;
}

static int language_of(const wchar_t *name)
{
    const wchar_t *extension = wcsrchr(name, L'.');
    wchar_t key[32];
    size_t i, n;
    if (!extension || (n = wcslen(extension)) + 2 > sizeof key / sizeof key[0]) return -1;
    for (i = 0; i < n; ++i) key[i] = (wchar_t)towlower(extension[i]);
    key[n] = L'.'; key[n + 1] = 0;
    for (i = 0; i < LANGUAGE_COUNT; ++i)
        if (wcsstr(languages[i].extensions, key)) return (int)i;
    return -1;
}

/* ASCII syntax also works with the legacy encodings in the supplied samples.
 * Strip UTF-8 BOM; reduce BOM-marked UTF-16 to ASCII syntax/non-ASCII markers. */
static char *read_source(const wchar_t *path, size_t *length)
{
    FILE *file = _wfopen(path, L"rb");
    char *data;
    __int64 size;
    size_t n, i, j;
    if (!file) { report(path, "Cannot open file"); return NULL; }
    if (_fseeki64(file, 0, SEEK_END) || (size = _ftelli64(file)) < 0 ||
        (unsigned long long)size > (size_t)-1 - 8 || _fseeki64(file, 0, SEEK_SET)) {
        report(path, "Cannot determine file size"); fclose(file); return NULL;
    }
    data = (char *)allocate((size_t)size + 8);
    n = fread(data, 1, (size_t)size, file);
    if (n != (size_t)size || ferror(file)) {
        report(path, "Cannot read file"); free(data); fclose(file); return NULL;
    }
    fclose(file);
    if (n >= 2 && (((unsigned char)data[0] == 255 && (unsigned char)data[1] == 254) ||
                   ((unsigned char)data[0] == 254 && (unsigned char)data[1] == 255))) {
        int little = (unsigned char)data[0] == 255;
        if (n % 2) { report(path, "Invalid UTF-16 file"); free(data); return NULL; }
        for (i = 2, j = 0; i + 1 < n; i += 2) {
            unsigned a = (unsigned char)data[i], b = (unsigned char)data[i + 1];
            unsigned value = little ? a + 256 * b : b + 256 * a;
            data[j++] = value < 128 ? (char)value : '\x80';
        }
        n = j;
    } else if (n >= 3 && !memcmp(data, "\xef\xbb\xbf", 3)) {
        memmove(data, data + 3, n - 3); n -= 3;
    }
    memset(data + n, 0, 8);
    *length = n;
    return data;
}

static int begins(const char *data, size_t i, size_t end, const char *word)
{
    size_t n = strlen(word);
    return n <= end - i && !memcmp(data + i, word, n);
}

static void count_source(Language *language, const char *data, size_t length)
{
    size_t pos = 0;
    unsigned syntax = language->syntax;
    int block = 0, quote = 0, triple = 0, raw = 0, continued_comment = 0;
    char raw_end[20] = {0};
    ++language->files;
    while (pos < length) {
        size_t start = pos, end, i;
        int has_code = 0, has_comment = block || continued_comment, nonblank = 0;
        while (pos < length && data[pos] != '\r' && data[pos] != '\n') ++pos;
        end = pos;
        if (pos < length && data[pos++] == '\r' && pos < length && data[pos] == '\n') ++pos;
        for (i = start; i < end; ++i)
            if (!isspace((unsigned char)data[i])) { nonblank = 1; break; }
        if (continued_comment) {
            has_comment = 1;
            continued_comment = end > start && data[end - 1] == '\\';
            i = end;
        } else i = start;
        while (i < end) {
            char c = data[i];
            if (block) {
                has_comment = 1;
                if (begins(data, i, end, "*/")) { block = 0; i += 2; }
                else ++i;
            } else if (raw) {
                has_code = 1;
                if (begins(data, i, end, raw_end)) { raw = 0; i += strlen(raw_end); }
                else ++i;
            } else if (quote) {
                has_code = 1;
                if (c == '\\') i += i + 1 < end ? 2 : 1;
                else if (c == quote && (!triple ||
                         (i + 2 < end && data[i + 1] == quote && data[i + 2] == quote))) {
                    i += triple ? 3 : 1; quote = triple = 0;
                } else ++i;
            } else if (isspace((unsigned char)c)) ++i;
            else if (((syntax & SLASH) && begins(data, i, end, "//")) ||
                     ((syntax & HASH) && c == '#')) {
                has_comment = 1;
                if ((!strcmp(language->name, "C") || (syntax & CPP)) &&
                    end > start && data[end - 1] == '\\') continued_comment = 1;
                break;
            } else if ((syntax & BLOCK) && begins(data, i, end, "/*")) {
                has_comment = 1; block = 1; i += 2;

            } else if ((syntax & CPP) && begins(data, i, end, "R\"")) {
                size_t j = i + 2;
                while (j < end && j - (i + 2) <= 16 && data[j] != '(' &&
                       !isspace((unsigned char)data[j]) && data[j] != '\\' && data[j] != ')') ++j;
                has_code = 1;
                if (j < end && data[j] == '(' && j - (i + 2) <= 16) {
                    size_t delimiter = j - (i + 2);
                    raw_end[0] = ')'; memcpy(raw_end + 1, data + i + 2, delimiter);
                    raw_end[delimiter + 1] = '"'; raw_end[delimiter + 2] = 0;
                    raw = 1; i = j + 1;
                } else ++i;
            } else if (c == '\'' || c == '"') {
                if (c == '\'' && (syntax & CPP) && i > start && i + 1 < end &&
                    isalnum((unsigned char)data[i - 1]) && isalnum((unsigned char)data[i + 1])) {
                    has_code = 1; ++i; continue;
                }
                has_code = 1; quote = c;
                triple = (syntax & (PYTHON|JAVA)) && i + 2 < end && data[i + 1] == c && data[i + 2] == c;
                i += triple ? 3 : 1;
            } else { has_code = 1; ++i; }
        }
        if (!nonblank && has_comment) ++language->comment;
        else if (!nonblank) ++language->blank;
        else if (has_code) ++language->code;
        else if (has_comment) ++language->comment;
        else ++language->code;
        if (quote && !triple &&
            !(end > start && data[end - 1] == '\\')) quote = 0;
    }
}

static wchar_t *join_path(const wchar_t *directory, const wchar_t *name)
{
    size_t a = wcslen(directory), b = wcslen(name);
    wchar_t *result = (wchar_t *)allocate((a + b + 2) * sizeof(wchar_t));
    memcpy(result, directory, a * sizeof(wchar_t));
    if (a && directory[a - 1] != L'\\' && directory[a - 1] != L'/') result[a++] = L'\\';
    memcpy(result + a, name, (b + 1) * sizeof(wchar_t));
    return result;
}

static void scan_directory(const wchar_t *directory)
{
    WIN32_FIND_DATAW entry;
    wchar_t *pattern = join_path(directory, L"*");
    HANDLE search = FindFirstFileW(pattern, &entry);
    DWORD error;
    free(pattern);
    if (search == INVALID_HANDLE_VALUE) {
        if (GetLastError() != ERROR_FILE_NOT_FOUND) report(directory, "Cannot enumerate directory");
        return;
    }
    do {
        wchar_t *path;
        int index;
        if (!wcscmp(entry.cFileName, L".") || !wcscmp(entry.cFileName, L"..") ||
            (entry.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) continue;
        path = join_path(directory, entry.cFileName);
        if (entry.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) scan_directory(path);
        else if ((index = language_of(entry.cFileName)) >= 0) {
            size_t length;
            char *data = read_source(path, &length);
            if (data) { count_source(&languages[index], data, length); free(data); }
        }
        free(path);
    } while (FindNextFileW(search, &entry));
    error = GetLastError();
    FindClose(search);
    if (error != ERROR_NO_MORE_FILES) report(directory, "Directory enumeration failed");
}

static void print_result(void)
{
    size_t i;
    unsigned long long files = 0, blank = 0, comment = 0, code = 0;
    const char *rule = "----------------------------------------------------------------------------";
    puts(rule);
    printf("%-16s %12s %14s %14s %14s\n", "Language", "files", "blank", "comment", "code");
    puts(rule);
    for (i = 0; i < LANGUAGE_COUNT; ++i) {
        Language *p = &languages[i];
        printf("%-16s %12llu %14llu %14llu %14llu\n", p->name, p->files, p->blank, p->comment, p->code);
        files += p->files; blank += p->blank; comment += p->comment; code += p->code;
    }
    puts(rule);
    printf("%-16s %12llu %14llu %14llu %14llu\n", "SUM", files, blank, comment, code);
    puts(rule);
}

int wmain(int argc, wchar_t **argv)
{
    const wchar_t *directory = argc == 2 ? argv[1] : L".";
    DWORD attributes;
    QueryPerformanceCounter(&start_time);
    QueryPerformanceFrequency(&timer_frequency);
    atexit(print_elapsed);
    SetConsoleOutputCP(CP_UTF8);
    if (argc > 2) { fputs("Usage: codecounter.exe [directory]\n", stderr); return 2; }
    if (argc == 2 && (!wcscmp(argv[1], L"--help") || !wcscmp(argv[1], L"-h"))) {
        puts("Usage: codecounter.exe [directory]\nRecursively count source lines; default directory is .");
        return 0;
    }
    attributes = GetFileAttributesW(directory);
    if (attributes == INVALID_FILE_ATTRIBUTES || !(attributes & FILE_ATTRIBUTE_DIRECTORY)) {
        report(directory, "Not an accessible directory"); return 1;
    }
    scan_directory(directory);
    print_result();
    return errors ? 1 : 0;
}