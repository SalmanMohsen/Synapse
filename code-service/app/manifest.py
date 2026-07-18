"""Incremental updates for the Codebase Manifest index (Build Plan Step 15).

Parses structural symbols using AST (Python) and tree-sitter libraries, fetches lightweight
purpose summaries from vLLM, and upserts file metadata in the Postgres codebase_manifest table.
"""

import ast
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List
from openai import AsyncOpenAI

from app.config import LLM_BASE_URL, LLM_MODEL_NAME
from app.db import codebase_manifest, get_connection

logger = logging.getLogger(__name__)


def parse_python_exports(content: str) -> dict:
    """Standard Python AST parser to extract structural details.

    Extremely fast, zero dependencies, and acts as a bulletproof fallback.
    """
    try:
        tree = ast.parse(content)
        exports = {"classes": [], "functions": [], "imports": []}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                exports["classes"].append(node.name)
            elif isinstance(node, ast.FunctionDef):
                exports["functions"].append(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    exports["imports"].append(alias.name)
        return exports
    except Exception as e:
        logger.debug("Python AST parser failed: %s", e)
        return {}


def parse_tree_sitter_exports(content: str, ext: str) -> dict:
    """Defensively walks a tree-sitter AST to extract landmarks for HTML, CSS, JS/TS, and Python.

    Fails gracefully if the tree-sitter parser is missing or fails compilation.
    """
    lang_map = {
        ".html": "html",
        ".htm": "html",
        ".css": "css",
        ".js": "javascript",
        ".ts": "typescript",
        ".py": "python"
    }
    lang_name = lang_map.get(ext)
    if not lang_name:
        return {}
        
    try:
        from tree_sitter_language_pack import get_parser
        parser = get_parser(lang_name)
        tree = parser.parse(content.encode("utf-8"))
        
        exports = {"landmarks": []}
        cursor = tree.walk()
        reached_root = False
        
        # Depth-First Search traversal to extract landmarks (selectors, classes, tags)
        while not reached_root:
            node = cursor.node
            node_type = node.type
            
            # Extract elements of interest
            if node_type in (
                "class_selector", "id_selector", "tag_name", 
                "function_definition", "class_definition", "method_definition"
            ):
                text = content[node.start_byte:node.end_byte].strip()
                if text and text not in [lm["name"] for lm in exports["landmarks"]]:
                    exports["landmarks"].append({"type": node_type, "name": text})
                    
            if cursor.goto_first_child():
                continue
            if cursor.goto_next_sibling():
                continue
            
            while True:
                if not cursor.goto_parent():
                    reached_root = True
                    break
                if cursor.goto_next_sibling():
                    break
                    
        return exports
    except Exception as e:
        logger.debug("Tree-sitter parse failed for extension %s: %s", ext, e)
        return {}


async def generate_file_purpose(file_path: str, content: str) -> str:
    """Invokes vLLM for a concise, cheap, 1-to-2 sentence summary of a file's purpose."""
    client = AsyncOpenAI(base_url=LLM_BASE_URL, api_key="not-needed")
    
    # Defensive truncation to avoid blowing the context window or token limits
    truncated_content = content[:3000]
    if len(content) > 3000:
        truncated_content += "\n... [truncated for token budget] ..."
        
    try:
        response = await client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Senior Software Engineer compiling a codebase manifest.\n"
                        "Provide a concise, 1-to-2 sentence summary of this file's purpose in the codebase."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"File path: {file_path}\n"
                        f"File Content:\n```\n{truncated_content}\n```\n\n"
                        "Provide the 1-2 sentence purpose summary now:"
                    )
                }
            ],
            temperature=0.1,
            max_tokens=100,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("vLLM purpose summary generation failed for %s: %s", file_path, e)
        return "Purpose summary generation failed."


async def upsert_codebase_manifest(
    project_id: str,
    file_path: str,
    exports_json: dict,
    purpose_summary: str,
    ticket_id: str
) -> None:
    """Inserts or updates a file's codebase manifest record in Postgres."""
    from sqlalchemy import select

    async with get_connection() as conn:
        stmt = select(codebase_manifest.c.id).where(
            codebase_manifest.c.project_id == project_id,
            codebase_manifest.c.file_path == file_path
        )
        result = await conn.execute(stmt)
        row = result.first()
        
        now = datetime.now(timezone.utc)
        
        if row:
            record_id = row[0]
            await conn.execute(
                codebase_manifest.update()
                .where(codebase_manifest.c.id == record_id)
                .values(
                    exports_json=exports_json,
                    purpose_summary=purpose_summary,
                    last_ticket_id=ticket_id,
                    updated_at=now
                )
            )
            logger.info("Updated codebase manifest record for file: %s", file_path)
        else:
            new_id = str(uuid.uuid4())
            await conn.execute(
                codebase_manifest.insert().values(
                    id=new_id,
                    project_id=project_id,
                    file_path=file_path,
                    exports_json=exports_json,
                    purpose_summary=purpose_summary,
                    last_ticket_id=ticket_id,
                    created_at=now,
                    updated_at=now
                )
            )
            logger.info("Created codebase manifest record for file: %s", file_path)


async def update_codebase_manifest_incremental(
    project_id: str,
    ticket_id: str,
    host_repo_path: str,
    file_paths: List[str]
) -> None:
    """Incrementally updates codebase manifest records for all given modified files."""
    for fp in file_paths:
        full_path = os.path.join(host_repo_path, fp)
        if not os.path.isfile(full_path):
            # File was deleted as part of the plan step; remove it from the index
            async with get_connection() as conn:
                await conn.execute(
                    codebase_manifest.delete()
                    .where(
                        codebase_manifest.c.project_id == project_id,
                        codebase_manifest.c.file_path == fp
                    )
                )
            logger.info("Deleted manifest record for removed file: %s", fp)
            continue
            
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            logger.warning("Failed to read file content for manifest update: %s", e)
            continue
            
        ext = os.path.splitext(fp)[1].lower()
        
        # Symmetrical parser selection
        exports = {}
        if ext == ".py":
            exports = parse_python_exports(content)
        if not exports:
            # Fall back to generic tree-sitter analysis
            exports = parse_tree_sitter_exports(content, ext)
            
        purpose = await generate_file_purpose(fp, content)
        
        await upsert_codebase_manifest(
            project_id=project_id,
            file_path=fp,
            exports_json=exports,
            purpose_summary=purpose,
            ticket_id=ticket_id
        )