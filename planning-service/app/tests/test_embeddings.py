import pytest
from unittest.mock import patch, MagicMock
import numpy as np
from app.ingestion.embeddings import count_tokens, embed_documents, embed_query


class FakeTokenizer:
    def encode(self, text, add_special_tokens=False):
        return [1] * len(text.split())


class FakeModel:
    def __init__(self):
        self.tokenizer = FakeTokenizer()

    def encode(self, texts, normalize_embeddings=True):
        import numpy as np
        # Return a NumPy array so .tolist() can be called on it by embeddings.py
        if isinstance(texts, list):
            return np.ones((len(texts), 256))
        else:
            return np.ones(256)


@pytest.fixture(autouse=True)
def mock_sentence_transformer():
    """Bypass loading heavy HuggingFace weights on local disk."""
    fake_model = FakeModel()
    with patch("app.ingestion.embeddings._get_model", return_value=fake_model):
        yield fake_model


def test_token_counter_using_tokenizer():
    text = "nomic embedding test token"
    assert count_tokens(text) == 4


def test_embed_documents_attaches_document_prefix(mock_sentence_transformer):
    with patch.object(mock_sentence_transformer, "encode", return_value=np.array([[0.1]*256])) as mock_encode:
        embed_documents(["content lines"])
        
        mock_encode.assert_called_once_with(
            ["search_document: content lines"],
            normalize_embeddings=True
        )


def test_embed_query_attaches_query_prefix(mock_sentence_transformer):
    with patch.object(mock_sentence_transformer, "encode", return_value=np.array([0.1]*256)) as mock_encode:
        embed_query("search query")
        
        mock_encode.assert_called_once_with(
            "search_query: search query",
            normalize_embeddings=True
        )