import pytest
from unittest.mock import patch
from app.ingestion.chunking import is_excluded, dispatch_chunk


def test_chunking_is_excluded_rules():
    assert is_excluded("node_modules/lodash/index.js") is True
    assert is_excluded(".git/config") is True
    assert is_excluded("package-lock.json") is True
    assert is_excluded("assets/logo.png") is True
    # Valid source code
    assert is_excluded("src/utils/calculator.py") is False


def test_chunking_python_ast_parsing():
    content = (
        "class UserService:\n"
        "    def create_user(self):\n"
        "        pass\n\n"
        "def health_check():\n"
        "    return 'OK'\n"
    )

    chunks = dispatch_chunk("src/services.py", content)

    # Identifies the class (containing the method) and the standalone function as 2 discrete units
    assert len(chunks) == 2
    assert "class UserService" in chunks[0].content
    assert "def health_check" in chunks[1].content


def test_chunking_markdown_headers():
    content = (
        "# Installation\n"
        "Follow these steps.\n"
        "## Configuration\n"
        "Adjust environment variables.\n"
    )

    chunks = dispatch_chunk("README.md", content)

    assert len(chunks) == 2
    assert "Installation" in chunks[0].content
    assert "Configuration" in chunks[1].content


def test_chunking_fallback_token_limit_splitting():
    # Input has multiple lines to allow splitting
    long_content = "word\n" * 100
    
    # Return 9000 (exceeding 8192) for full content, and 1 for smaller line pieces
    def mock_count_tokens(text):
        return 9000 if len(text.split()) > 10 else 1

    with patch("app.ingestion.chunking.count_tokens", side_effect=mock_count_tokens):
        chunks = dispatch_chunk("config.json", long_content)

        assert len(chunks) > 1