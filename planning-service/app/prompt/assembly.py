
import logging
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Constants matching locked decisions
MAX_INPUT_LIMIT = 28000  # 32K context window minus 4K reserved for output
SUMMARIZATION_BATCH_LIMIT = 4000  # Sane chunk size for a single summarization pass

CountTokensFn = Callable[[str], int]


@dataclass
class AssemblyResult:
    prompt: str
    needs_summarization: bool
    messages_to_summarize: List[str]
    messages_verbatim: List[str]


def _format_skills(specialty: str, technology: str) -> str:
    """Format skills in the strictly enforced XML layout."""
    return (
        f"<specialty_skill>\n{specialty.strip()}\n</specialty_skill>\n"
        f"<technology_skill>\n{technology.strip()}\n</technology_skill>\n"
    )


def _format_ticket(title: str, description: Optional[str]) -> str:
    """Format the ticket data in standard XML tags."""
    desc = description.strip() if description else "No description provided."
    return f"<ticket>\nTitle: {title.strip()}\nDescription: {desc}\n</ticket>\n"


def _format_chunks(chunks: List[Tuple[str, str]]) -> str:
    """Format retrieved Qdrant code chunks, tagging each with its file path."""
    lines = []
    for file_path, content in chunks:
        lines.append(f'<code_chunk path="{file_path}">\n{content.strip()}\n</code_chunk>')
    return "\n".join(lines) + "\n"


def _format_message(content: str) -> str:
    """Format single messages chronologically without author/timestamp attribution."""
    return f"<message>\n{content.strip()}\n</message>"


def assemble_prompt(
    specialty_skill: str,
    technology_skill: str,
    ticket_title: str,
    ticket_description: Optional[str],
    retrieved_chunks: List[Tuple[str, str]],  # List of (file_path, content)
    thread_messages: List[str],  # Chronological thread messages (oldest first)
    count_tokens_fn: CountTokensFn,
    thread_summary: Optional[str] = None
) -> AssemblyResult:
    """Build the full context prompt and calculate exact token limits.

    If the input budget is exceeded, it splits the message thread, preserving
    the newest messages verbatim while packaging the oldest for the summarization loop.

    count_tokens_fn must be bound to the Qwen tokenizer loaded at worker
    startup (transformers.AutoTokenizer) — the locked decision requires exact
    Qwen token counts for this budget check, not any other model's tokenizer.
    """
    # 1. Assemble static overhead blocks
    prefix_block = _format_skills(specialty_skill, technology_skill)
    ticket_block = _format_ticket(ticket_title, ticket_description)
    context_block = _format_chunks(retrieved_chunks)

    static_text = prefix_block + ticket_block + context_block
    if thread_summary:
        static_text += f"<thread_summary>\n{thread_summary.strip()}\n</thread_summary>\n"

    static_tokens = count_tokens_fn(static_text)

    # 2. Iterate backwards through messages to keep the most recent verbatim
    verbatim_messages: List[str] = []
    messages_to_summarize: List[str] = []
    
    current_message_tokens = 0
    available_message_budget = MAX_INPUT_LIMIT - static_tokens

    # Traverse chronological thread in reverse order (newest first)
    for msg in reversed(thread_messages):
        formatted_msg = _format_message(msg)
        msg_tokens = count_tokens_fn(formatted_msg) + 1  # Add separator safety margin

        if current_message_tokens + msg_tokens <= available_message_budget:
            verbatim_messages.insert(0, msg)  # Keep chronological order
            current_message_tokens += msg_tokens
        else:
            # This message and all older messages before it must be summarized
            messages_to_summarize.insert(0, msg)

    # If everything fits, compile cleanly
    if not messages_to_summarize:
        full_thread_text = "\n".join(_format_message(m) for m in verbatim_messages)
        final_prompt = static_text + full_thread_text
        return AssemblyResult(
            prompt=final_prompt,
            needs_summarization=False,
            messages_to_summarize=[],
            messages_verbatim=verbatim_messages
        )

    # If overflow occurred, notify caller that a summarization pass is required first
    return AssemblyResult(
        prompt="",
        needs_summarization=True,
        messages_to_summarize=messages_to_summarize,
        messages_verbatim=verbatim_messages
    )


# ------------------------------------------------------------------ #
# Refine-Style Sequentual Summarization Helper                         #
# ------------------------------------------------------------------ #

def batch_messages_for_summary(
    messages: List[str], count_tokens_fn: CountTokensFn
) -> List[List[str]]:
    """Group overflow messages into manageable chronological token batches."""
    batches: List[List[str]] = []
    current_batch: List[str] = []
    current_tokens = 0

    for msg in messages:
        msg_tokens = count_tokens_fn(msg)
        if current_tokens + msg_tokens > SUMMARIZATION_BATCH_LIMIT:
            if current_batch:
                batches.append(current_batch)
            current_batch = [msg]
            current_tokens = msg_tokens
        else:
            current_batch.append(msg)
            current_tokens += msg_tokens

    if current_batch:
        batches.append(current_batch)
    return batches
