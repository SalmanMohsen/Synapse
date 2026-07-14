from unittest.mock import patch
import pytest
from app.prompt.assembly import assemble_prompt, batch_messages_for_summary

def simple_token_counter(text: str) -> int:
    # A simplified, predictable mock of the tokenizer for testing exact limits
    return len(text.split())

def test_assemble_prompt_fully_fits_within_budget():
    specialty = "Always structure Python modules cleanly."
    technology = "Write async methods using SQLAlchemy."
    title = "Implement user authentication endpoint"
    description = "Create a route that takes user details and issues a JWT."
    chunks = [
        ("app/auth/router.py", "def login(): pass"),
        ("app/auth/service.py", "class AuthService: pass")
    ]
    messages = [
        "First, we should establish the registration route.",
        "Yes, then we should implement registration and link it to JWT generation.",
        "Let's finalize on standard JWT auth flow."
    ]

    result = assemble_prompt(
        specialty_skill=specialty,
        technology_skill=technology,
        ticket_title=title,
        ticket_description=description,
        retrieved_chunks=chunks,
        thread_messages=messages,
        count_tokens_fn=simple_token_counter
    )

    assert result.needs_summarization is False
    assert len(result.messages_to_summarize) == 0
    assert len(result.messages_verbatim) == 3

    # Check correct order and XML tag structure
    assert specialty in result.prompt
    assert technology in result.prompt
    assert "<specialty_skill>" in result.prompt
    assert "<technology_skill>" in result.prompt
    assert "<ticket>" in result.prompt
    assert f'path="app/auth/router.py"' in result.prompt

    # Verify chronological ordering (oldest first, verbatim kept last)
    msg_1_idx = result.prompt.find("First, we should establish")
    msg_2_idx = result.prompt.find("Yes, then we should implement")
    msg_3_idx = result.prompt.find("Let's finalize on standard")

    assert msg_1_idx != -1
    assert msg_2_idx > msg_1_idx
    assert msg_3_idx > msg_2_idx


@patch("app.prompt.assembly.MAX_INPUT_LIMIT", 50)  # artificially low token limit
def test_assemble_prompt_overflow_splits_chronological_messages():
    specialty = "Standard standards."
    technology = "Standard tech."
    title = "Small ticket title"
    description = "Small ticket description"
    chunks = [("file.py", "print('hello')")]
    
    # 5 messages, each with an approximate token weight of 5
    messages = [
        "Oldest historical detail that we should ignore or compress.",
        "Middle message discussing design elements.",
        "Another discussion element.",
        "Recent critical details about files to change.",
        "Latest and most immediately relevant decision."
    ]

    result = assemble_prompt(
        specialty_skill=specialty,
        technology_skill=technology,
        ticket_title=title,
        ticket_description=description,
        retrieved_chunks=chunks,
        thread_messages=messages,
        count_tokens_fn=simple_token_counter
    )

    assert result.needs_summarization is True
    # Verify that oldest messages are earmarked for summarization, while latest remain verbatim
    assert "Oldest historical detail" in result.messages_to_summarize[0]
    assert "Latest and most immediately" in result.messages_verbatim[-1]


def test_batch_messages_for_summary():
    messages = [
        "One two three four five",
        "Six seven eight nine ten",
        "Eleven twelve thirteen fourteen fifteen",
        "Sixteen seventeen eighteen nineteen twenty"
    ]
    
    # Force batch limit to low size of 10 tokens per batch
    with patch("app.prompt.assembly.SUMMARIZATION_BATCH_LIMIT", 11):
        batches = batch_messages_for_summary(messages, simple_token_counter)
        
        assert len(batches) == 2
        # First batch should hold message 1 and 2 (5 + 5 tokens)
        assert len(batches[0]) == 2
        assert "One" in batches[0][0]
        assert "Six" in batches[0][1]
        
        # Second batch should hold message 3 and 4
        assert len(batches[1]) == 2
        assert "Eleven" in batches[1][0]