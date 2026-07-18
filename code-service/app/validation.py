"""Tiered validation for Code Agent step execution (Build Plan Step 9).

Supports three graceful degradation tiers:
1. Repo-declared (Makefile lint/test, package.json scripts)
2. Generic per-language validator (Stylelint, html-validate, ruff, node --check)
3. Bare sanity check (UTF-8 parsing, search for git merge conflicts / corruption)
"""

import json
import logging
import os
from typing import List, Tuple
from app.sandbox.container import SandboxHandle, exec_in_sandbox

logger = logging.getLogger(__name__)


async def validate_step_changes(
    handle: SandboxHandle,
    host_repo_path: str,
    touched_files: List[str],
    expected_action_type: str = "",
) -> Tuple[bool, str, str | None]:
    """Runs tiered validation against touched files.

    Returns (success, check_tier, error_details).
    """
    # Filter out empty paths or non-existent files
    valid_touched = [
        f for f in touched_files 
        if os.path.isfile(os.path.join(host_repo_path, f))
    ]

    # If no files were modified in this step, pass validation using sanity check tier
    # UNLESS the plan step explicitly expected a file-changing action — in that
    # case zero touched files means the agent's tool call never actually
    # executed (e.g. a malformed/unparsed action), not that nothing needed to
    # change. Treat that as a failure so the correction loop gets another
    # attempt instead of silently completing a no-op step.
    if not valid_touched:
        if expected_action_type in ("modify", "create", "delete"):
            logger.warning(
                "Expected action_type '%s' but no files were touched on disk.",
                expected_action_type,
            )
            return (
                False,
                "sanity_only",
                f"Expected action type '{expected_action_type}' but no file "
                "changes were found on disk after the agent's turn. This "
                "usually means the requested edit was never actually "
                "executed — make sure to call file_editor (or terminal) to "
                "perform the change, not just describe it.",
            )
        logger.info("No modified files found. Skipping validation with generic success.")
        return True, "sanity_only", None

    # --- Tier 1: Repo-declared ---
    has_makefile = os.path.isfile(os.path.join(host_repo_path, "Makefile"))
    has_package_json = os.path.isfile(os.path.join(host_repo_path, "package.json"))

    if has_makefile:
        logger.info("Tier 1 validation: Makefile detected. Running 'make lint' and 'make test'.")
        exit_code_lint, out_lint = exec_in_sandbox(handle, ["make", "lint"])
        exit_code_test, out_test = exec_in_sandbox(handle, ["make", "test"])
        
        # If both fail with 'No rule to make target', we fall back to other tiers.
        no_rule_lint = "No rule to make target" in out_lint
        no_rule_test = "No rule to make target" in out_test
        
        if not (no_rule_lint and no_rule_test):
            success = (exit_code_lint == 0) and (exit_code_test == 0)
            errors = []
            if exit_code_lint != 0 and not no_rule_lint:
                errors.append(f"make lint failed:\n{out_lint}")
            if exit_code_test != 0 and not no_rule_test:
                errors.append(f"make test failed:\n{out_test}")
                
            if errors:
                return False, "repo_test_suite", "\n".join(errors)
            return True, "repo_test_suite", None

    if has_package_json:
        logger.info("Tier 1 validation: package.json detected. Checking npm scripts.")
        try:
            with open(os.path.join(host_repo_path, "package.json"), "r", encoding="utf-8") as f:
                pkg_data = json.load(f)
            scripts = pkg_data.get("scripts", {})
        except Exception as e:
            logger.warning("Could not parse package.json: %s", e)
            scripts = {}

        has_npm_lint = "lint" in scripts
        has_npm_test = "test" in scripts

        if has_npm_lint or has_npm_test:
            errors = []
            if has_npm_lint:
                code, out = exec_in_sandbox(handle, ["npm", "run", "lint"])
                if code != 0:
                    errors.append(f"npm run lint failed:\n{out}")
            if has_npm_test:
                code, out = exec_in_sandbox(handle, ["npm", "test"])
                if code != 0:
                    errors.append(f"npm test failed:\n{out}")
                    
            if errors:
                return False, "repo_test_suite", "\n".join(errors)
            return True, "repo_test_suite", None

    # --- Tier 2: Generic fallback ---
    logger.info("Tier 2 validation: Running generic per-language fallbacks.")
    generic_errors = []
    executed_generic_checks = False

    # Create temporary stylelint config inside sandbox if stylelint is required
    css_files = [f for f in valid_touched if f.endswith(".css")]
    has_stylelint_config = any(
        os.path.isfile(os.path.join(host_repo_path, cfg))
        for cfg in [".stylelintrc", ".stylelintrc.json", "stylelint.config.js"]
    )
    temp_config_created = False
    if css_files and not has_stylelint_config:
        try:
            with open(os.path.join(host_repo_path, ".stylelintrc.json"), "w", encoding="utf-8") as f:
                json.dump({"extends": ["stylelint-config-standard"]}, f)
            temp_config_created = True
        except Exception as e:
            logger.warning("Failed to write temporary stylelint config: %s", e)

    try:
        for file_path in valid_touched:
            ext = os.path.splitext(file_path)[1].lower()
            
            # HTML validation
            if ext in (".html", ".htm"):
                executed_generic_checks = True
                code, out = exec_in_sandbox(handle, ["html-validate", file_path])
                if code != 0:
                    generic_errors.append(f"HTML validation failed on {file_path}:\n{out}")
                    
            # CSS validation
            elif ext == ".css":
                executed_generic_checks = True
                code, out = exec_in_sandbox(handle, ["stylelint", file_path])
                if code != 0:
                    generic_errors.append(f"CSS validation failed on {file_path}:\n{out}")
                    
            # Python validation
            elif ext == ".py":
                executed_generic_checks = True
                code_chk, out_chk = exec_in_sandbox(handle, ["ruff", "check", file_path])
                code_fmt, out_fmt = exec_in_sandbox(handle, ["ruff", "format", "--check", file_path])
                if code_chk != 0 or code_fmt != 0:
                    generic_errors.append(
                        f"Python validation failed on {file_path}:\n"
                        f"Ruff Check exit {code_chk}:\n{out_chk}\n"
                        f"Ruff Format exit {code_fmt}:\n{out_fmt}"
                    )
                    
            # JS validation syntax-only check
            elif ext in (".js", ".mjs", ".cjs"):
                executed_generic_checks = True
                code, out = exec_in_sandbox(handle, ["node", "--check", file_path])
                if code != 0:
                    generic_errors.append(f"JS syntax check failed on {file_path}:\n{out}")

        if executed_generic_checks:
            if generic_errors:
                return False, "generic_validator", "\n".join(generic_errors)
            return True, "generic_validator", None

    finally:
        # Guarantee cleanup of temporary stylelint config
        if temp_config_created:
            try:
                os.remove(os.path.join(host_repo_path, ".stylelintrc.json"))
            except Exception:
                pass

    # --- Tier 3: Sanity last resort ---
    logger.info("Tier 3 validation: No validators matched. Running bare text sanity checks.")
    sanity_errors = []
    
    for file_path in valid_touched:
        full_path = os.path.join(host_repo_path, file_path)
        try:
            with open(full_path, "r", encoding="utf-8", errors="strict") as f:
                content = f.read()
                
            if "<<<<<<<" in content or "=======" in content or ">>>>>>>" in content:
                sanity_errors.append(f"File {file_path} contains unresolved git conflict markers.")
            elif "\x00" in content:
                sanity_errors.append(f"File {file_path} contains NULL bytes indicating corruption.")
        except UnicodeDecodeError as ude:
            sanity_errors.append(f"File {file_path} is not valid UTF-8 text: {ude}")
        except Exception as e:
            sanity_errors.append(f"Could not read file {file_path}: {e}")

    if sanity_errors:
        return False, "sanity_only", "\n".join(sanity_errors)
    return True, "sanity_only", None