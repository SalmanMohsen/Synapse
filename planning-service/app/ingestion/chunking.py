"""Chunking dispatch by file type.

- Code files: tree-sitter function/class-level chunking (Python, TS/JS minimum).
- Markdown: header-based splitting.
- Config files (.json/.yaml/.yml/.toml, docker-compose.yml, .env.example, ...):
  whole-file chunking — small enough that the "chunk" is the whole file.
  Lockfiles are excluded even though they share extensions with legitimate config.
- Excluded entirely: node_modules, .git, build/dist output, binary/image assets,
  lockfiles.
- Any chunk (any dispatch path) exceeding nomic-embed-text's token limit gets a
  simple line-based fallback split.
"""

import os
from dataclasses import dataclass

from tree_sitter_language_pack import get_parser

from app.ingestion.embeddings import MAX_EMBED_TOKENS, count_tokens

_EXCLUDED_DIR_PARTS = {"node_modules", ".git", "dist", "build", "__pycache__"}

_BINARY_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".bmp",
    ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".zip", ".tar", ".gz",
}

_LOCKFILE_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "composer.lock",
}

_CODE_LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}

_CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml"}
_CONFIG_BASENAMES = {"docker-compose.yml", "docker-compose.yaml", ".env.example"}

# Node types treated as chunk-worthy units, per tree-sitter grammar. Covers the
# common definition shapes for Python/JS/TS. arrow_function is handled
# separately below (only counted when it's the RHS of a variable declaration,
# e.g. `const foo = () => {...}` — not every inline callback argument).
_CHUNK_NODE_TYPES = {
    "function_definition",       # Python
    "class_definition",          # Python
    "function_declaration",      # JS/TS
    "class_declaration",         # JS/TS
    "method_definition",         # JS/TS
}


@dataclass
class Chunk:
    file_path: str
    content: str
    start_line: int | None = None
    end_line: int | None = None


def is_excluded(file_path: str) -> bool:
    parts = file_path.split("/")
    if any(part in _EXCLUDED_DIR_PARTS for part in parts):
        return True
    basename = os.path.basename(file_path)
    if basename in _LOCKFILE_NAMES:
        return True
    _, ext = os.path.splitext(basename)
    if ext.lower() in _BINARY_IMAGE_EXTENSIONS:
        return True
    return False


def _fallback_split(text: str, file_path: str) -> list[Chunk]:
    """Line-based split for any chunk exceeding the embedding model's token limit."""
    lines = text.splitlines(keepends=True)
    chunks: list[Chunk] = []
    current: list[str] = []
    for line in lines:
        current.append(line)
        if count_tokens("".join(current)) >= MAX_EMBED_TOKENS:
            # Pull the last line back out before it tips over the limit.
            overflow_line = current.pop()
            if current:
                chunks.append(Chunk(file_path=file_path, content="".join(current)))
            current = [overflow_line]
    if current:
        chunks.append(Chunk(file_path=file_path, content="".join(current)))
    return chunks


def _enforce_token_limit(chunks: list[Chunk]) -> list[Chunk]:
    result: list[Chunk] = []
    for chunk in chunks:
        if count_tokens(chunk.content) <= MAX_EMBED_TOKENS:
            result.append(chunk)
        else:
            result.extend(_fallback_split(chunk.content, chunk.file_path))
    return result


def _chunk_code(file_path: str, content: str, language: str) -> list[Chunk]:
    parser = get_parser(language)
    tree = parser.parse(content.encode("utf-8"))
    chunks: list[Chunk] = []

    def _capture(node) -> None:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        text = content.encode("utf-8")[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )
        chunks.append(
            Chunk(
                file_path=file_path,
                content=text,
                start_line=start_line,
                end_line=end_line,
            )
        )

    def walk(node) -> None:
        if node.type == "arrow_function":
            parent = node.parent
            if parent is not None and parent.type == "variable_declarator":
                # const foo = () => {...} — a named, standalone unit.
                _capture(node)
                return
            # Inline callback (e.g. arr.map(x => x + 1)) — not a standalone
            # unit; keep walking in case it contains something chunk-worthy
            # nested inside (rare, but cheap to allow).
            for child in node.children:
                walk(child)
            return
        if node.type in _CHUNK_NODE_TYPES:
            _capture(node)
            return  # don't descend into a captured node's children
        for child in node.children:
            walk(child)

    walk(tree.root_node)

    if not chunks:
        # No function/class definitions found (e.g. a small script or a
        # constants-only file) — the whole file is the only unit available.
        chunks.append(Chunk(file_path=file_path, content=content))

    return chunks


def _chunk_markdown(file_path: str, content: str) -> list[Chunk]:
    lines = content.splitlines(keepends=True)
    chunks: list[Chunk] = []
    current: list[str] = []
    start_line = 1

    for i, line in enumerate(lines, start=1):
        if line.startswith("#") and current:
            chunks.append(
                Chunk(
                    file_path=file_path,
                    content="".join(current),
                    start_line=start_line,
                    end_line=i - 1,
                )
            )
            current = [line]
            start_line = i
        else:
            current.append(line)

    if current:
        chunks.append(
            Chunk(
                file_path=file_path,
                content="".join(current),
                start_line=start_line,
                end_line=len(lines),
            )
        )

    if not chunks:
        chunks.append(Chunk(file_path=file_path, content=content))

    return chunks


def _is_config_file(file_path: str) -> bool:
    basename = os.path.basename(file_path)
    if basename in _CONFIG_BASENAMES:
        return True
    _, ext = os.path.splitext(basename)
    return ext.lower() in _CONFIG_EXTENSIONS


def dispatch_chunk(file_path: str, content: str) -> list[Chunk]:
    """Routes a file to the right chunking strategy, then enforces the token limit."""
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext in _CODE_LANGUAGE_BY_EXTENSION:
        chunks = _chunk_code(file_path, content, _CODE_LANGUAGE_BY_EXTENSION[ext])
    elif ext == ".md":
        chunks = _chunk_markdown(file_path, content)
    elif _is_config_file(file_path):
        chunks = [Chunk(file_path=file_path, content=content)]
    else:
        # Not in any recognized dispatch category — deliberately skipped rather
        # than guessing at a chunking strategy for file types outside the stack.
        return []

    return _enforce_token_limit(chunks)