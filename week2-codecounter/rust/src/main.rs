use std::env;
use std::fs::{self, Metadata};
use std::io;
use std::path::Path;
use std::process::ExitCode;
use std::time::Instant;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Language {
    C,
    Cpp,
    Java,
    Python,
}

const LANGUAGES: [Language; 4] = [
    Language::C,
    Language::Cpp,
    Language::Java,
    Language::Python,
];

impl Language {
    fn name(self) -> &'static str {
        match self {
            Self::C => "C",
            Self::Cpp => "C++",
            Self::Java => "Java",
            Self::Python => "Python",
        }
    }

    fn index(self) -> usize {
        self as usize
    }

    fn continues_comments(self) -> bool {
        matches!(self, Self::C | Self::Cpp)
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Counts {
    files: u64,
    blank: u64,
    comment: u64,
    code: u64,
}

impl Counts {
    fn add(&mut self, other: Self) {
        self.files += other.files;
        self.blank += other.blank;
        self.comment += other.comment;
        self.code += other.code;
    }
}

fn language_of(path: &Path) -> Option<Language> {
    match path.extension()?.to_str()?.to_ascii_lowercase().as_str() {
        "c" | "h" => Some(Language::C),
        "cpp" | "cc" | "cxx" | "hpp" | "hh" | "hxx" | "ipp" | "inl" => {
            Some(Language::Cpp)
        }
        "java" => Some(Language::Java),
        "py" | "pyi" | "pyw" => Some(Language::Python),
        _ => None,
    }
}

// Preserve ASCII syntax in legacy byte encodings and BOM-marked UTF-16.
fn normalize_source(mut data: Vec<u8>) -> io::Result<Vec<u8>> {
    if data.starts_with(&[0xff, 0xfe]) || data.starts_with(&[0xfe, 0xff]) {
        if data.len() % 2 != 0 {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "Invalid UTF-16 file"));
        }
        let little = data[0] == 0xff;
        let mut output = 0;
        for input in (2..data.len()).step_by(2) {
            let pair = [data[input], data[input + 1]];
            let value = if little {
                u16::from_le_bytes(pair)
            } else {
                u16::from_be_bytes(pair)
            };
            data[output] = if value < 128 { value as u8 } else { 0x80 };
            output += 1;
        }
        data.truncate(output);
    } else if data.starts_with(&[0xef, 0xbb, 0xbf]) {
        data.drain(..3);
    }
    Ok(data)
}

fn is_space(byte: u8) -> bool {
    matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c)
}

fn count_source(language: Language, data: &[u8]) -> Counts {
    let mut counts = Counts { files: 1, ..Counts::default() };
    let mut pos = 0;
    let mut block = false;
    let mut quote = None;
    let mut triple = false;
    let mut raw_end = Vec::new();
    let mut continued_comment = false;

    while pos < data.len() {
        let start = pos;
        while pos < data.len() && !matches!(data[pos], b'\r' | b'\n') {
            pos += 1;
        }
        let line = &data[start..pos];
        if pos < data.len() {
            let ending = data[pos];
            pos += 1;
            if ending == b'\r' && data.get(pos) == Some(&b'\n') {
                pos += 1;
            }
        }

        let nonblank = line.iter().any(|&byte| !is_space(byte));
        let mut has_code = false;
        let mut has_comment = block || continued_comment;
        let mut i = 0;
        if continued_comment {
            continued_comment = line.last() == Some(&b'\\');
            i = line.len();
        }

        while i < line.len() {
            let byte = line[i];
            let rest = &line[i..];
            if block {
                has_comment = true;
                if rest.starts_with(b"*/") {
                    block = false;
                    i += 2;
                } else {
                    i += 1;
                }
            } else if !raw_end.is_empty() {
                has_code = true;
                if rest.starts_with(&raw_end) {
                    i += raw_end.len();
                    raw_end.clear();
                } else {
                    i += 1;
                }
            } else if let Some(delimiter) = quote {
                has_code = true;
                if byte == b'\\' {
                    i += (line.len() - i).min(2);
                } else if byte == delimiter
                    && (!triple || rest.starts_with(&[delimiter; 3]))
                {
                    i += if triple { 3 } else { 1 };
                    quote = None;
                    triple = false;
                } else {
                    i += 1;
                }
            } else if is_space(byte) {
                i += 1;
            } else if (language != Language::Python && rest.starts_with(b"//"))
                || (language == Language::Python && byte == b'#')
            {
                has_comment = true;
                continued_comment = language.continues_comments()
                    && line.last() == Some(&b'\\');
                break;
            } else if language != Language::Python && rest.starts_with(b"/*") {
                has_comment = true;
                block = true;
                i += 2;
            } else if language == Language::Cpp && rest.starts_with(b"R\"") {
                has_code = true;
                let mut j = i + 2;
                while j < line.len()
                    && j - (i + 2) <= 16
                    && line[j] != b'('
                    && !is_space(line[j])
                    && !matches!(line[j], b'\\' | b')')
                {
                    j += 1;
                }
                if j < line.len() && line[j] == b'(' && j - (i + 2) <= 16 {
                    raw_end.push(b')');
                    raw_end.extend_from_slice(&line[i + 2..j]);
                    raw_end.push(b'"');
                    i = j + 1;
                } else {
                    i += 1;
                }
            } else if matches!(byte, b'\'' | b'"') {
                has_code = true;
                if byte == b'\''
                    && language == Language::Cpp
                    && i > 0
                    && i + 1 < line.len()
                    && line[i - 1].is_ascii_alphanumeric()
                    && line[i + 1].is_ascii_alphanumeric()
                {
                    i += 1;
                    continue;
                }
                quote = Some(byte);
                triple = matches!(language, Language::Python | Language::Java)
                    && rest.starts_with(&[byte; 3]);
                i += if triple { 3 } else { 1 };
            } else {
                has_code = true;
                i += 1;
            }
        }

        if !nonblank && has_comment {
            counts.comment += 1;
        } else if !nonblank {
            counts.blank += 1;
        } else if has_code {
            counts.code += 1;
        } else if has_comment {
            counts.comment += 1;
        } else {
            counts.code += 1;
        }
        if quote.is_some() && !triple && line.last() != Some(&b'\\') {
            quote = None;
        }
    }
    counts
}

fn skip_entry(metadata: &Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
        metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
    }
    #[cfg(not(windows))]
    {
        metadata.file_type().is_symlink()
    }
}

fn report(path: &Path, error: impl std::fmt::Display, errors: &mut bool) {
    eprintln!("{}: {error}", path.display());
    *errors = true;
}

fn scan_directory(directory: &Path) -> ([Counts; 4], bool) {
    let mut totals = [Counts::default(); 4];
    let mut errors = false;
    let mut pending = vec![directory.to_path_buf()];
    while let Some(directory) = pending.pop() {
        let entries = match fs::read_dir(&directory) {
            Ok(entries) => entries,
            Err(error) => {
                report(&directory, error, &mut errors);
                continue;
            }
        };
        for entry in entries {
            let entry = match entry {
                Ok(entry) => entry,
                Err(error) => {
                    report(&directory, error, &mut errors);
                    continue;
                }
            };
            let path = entry.path();
            let metadata = match fs::symlink_metadata(&path) {
                Ok(metadata) => metadata,
                Err(error) => {
                    report(&path, error, &mut errors);
                    continue;
                }
            };
            if skip_entry(&metadata) {
                continue;
            }
            if metadata.is_dir() {
                pending.push(path);
            } else if metadata.is_file() {
                if let Some(language) = language_of(&path) {
                    match fs::read(&path).and_then(normalize_source) {
                        Ok(data) => totals[language.index()].add(count_source(language, &data)),
                        Err(error) => report(&path, error, &mut errors),
                    }
                }
            }
        }
    }
    (totals, errors)
}

fn print_result(totals: &[Counts; 4]) {
    const RULE: &str = "----------------------------------------------------------------------------";
    fn row(name: &str, counts: Counts) {
        println!(
            "{:<16} {:>12} {:>14} {:>14} {:>14}",
            name, counts.files, counts.blank, counts.comment, counts.code
        );
    }
    println!("{RULE}");
    println!(
        "{:<16} {:>12} {:>14} {:>14} {:>14}",
        "Language", "files", "blank", "comment", "code"
    );
    println!("{RULE}");
    let mut sum = Counts::default();
    for language in LANGUAGES {
        let counts = totals[language.index()];
        row(language.name(), counts);
        sum.add(counts);
    }
    println!("{RULE}");
    row("SUM", sum);
    println!("{RULE}");
}

fn run() -> u8 {
    let mut args = env::args_os().skip(1);
    let directory = args.next().unwrap_or_else(|| ".".into());
    if args.next().is_some() {
        eprintln!("Usage: codecounter.exe [directory]");
        return 2;
    }
    if directory == "--help" || directory == "-h" {
        println!("Usage: codecounter.exe [directory]\nRecursively count source lines; default directory is .");
        return 0;
    }
    let directory = Path::new(&directory);
    if !directory.is_dir() {
        eprintln!("Not an accessible directory: {}", directory.display());
        return 1;
    }
    let (totals, errors) = scan_directory(directory);
    print_result(&totals);
    u8::from(errors)
}

fn main() -> ExitCode {
    let start = Instant::now();
    let status = run();
    println!("Elapsed time: {:.6} seconds.", start.elapsed().as_secs_f64());
    ExitCode::from(status)
}