# EVOLVE-BLOCK: a marker-based approach for defining editable regions in generated code.
#
# A template file contains:
#   # EVOLVE-BLOCK-START
#   ... code to be replaced by LLM ...
#   # EVOLVE-BLOCK-END
#
# Everything outside these markers is immutable context.
# Everything inside is the editable block.

import re
from typing import Optional

EVOLVE_BLOCK_START = "# EVOLVE-BLOCK-START"
EVOLVE_BLOCK_END = "# EVOLVE-BLOCK-END"

# Also support Python-block syntax (triple-quoted regions in comments)
ALT_START = r"EVOLVE-BLOCK-START"
ALT_END = r"EVOLVE-BLOCK-END"


def extract_block(code: str) -> Optional[str]:
    """Extract the content between EVOLVE-BLOCK-START and EVOLVE-BLOCK-END markers.

    Returns None if markers are not found.
    """
    lines = code.splitlines()
    start_idx = None
    end_idx = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if EVOLVE_BLOCK_START in stripped or stripped == ALT_START:
            start_idx = i
        if EVOLVE_BLOCK_END in stripped or stripped == ALT_END:
            end_idx = i

    if start_idx is None or end_idx is None:
        return None

    # Content is between the two marker lines
    content_lines = lines[start_idx + 1 : end_idx]
    return "\n".join(content_lines)


def replace_block(code: str, new_block: str) -> str:
    """Replace the content between EVOLVE-BLOCK-START and EVOLVE-BLOCK-END with new_block.

    Preserves the marker lines and the code outside the block.
    """
    lines = code.splitlines()
    start_idx = None
    end_idx = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if EVOLVE_BLOCK_START in stripped or stripped == ALT_START:
            start_idx = i
        if EVOLVE_BLOCK_END in stripped or stripped == ALT_END:
            end_idx = i

    if start_idx is None or end_idx is None:
        raise ValueError("EVOLVE-BLOCK markers not found in code template")

    # Reconstruct: before start marker + start marker + new block + end marker + after end marker
    before = lines[: start_idx + 1]
    after = lines[end_idx:]
    indent = _detect_indent(lines, start_idx + 1)
    indented_block = _indent_block(new_block.strip(), indent)

    return "\n".join(before) + "\n" + indented_block + "\n" + "\n".join(after)


def _detect_indent(lines: list[str], idx: int) -> str:
    """Detect the indentation of the line at idx (first line inside block)."""
    if idx < len(lines):
        stripped = lines[idx].lstrip()
        indent = lines[idx][: len(lines[idx]) - len(stripped)]
        return indent
    return ""


def _indent_block(block: str, indent: str) -> str:
    """Normalise then add indentation to each line of a block.

    Strips ALL leading whitespace from each line, then adds the target
    indentation. This prevents the LLM's own indentation from compounding.
    For simple function bodies (all statements at one level) this is correct;
    nested blocks may need a more nuanced approach in future.
    """
    if not indent:
        return block
    lines = block.splitlines()
    # Remove ALL leading whitespace from every non-empty line
    stripped = [ln.lstrip() if ln.strip() else "" for ln in lines]
    # Add our target indentation
    indented = [indent + ln if ln.strip() else "" for ln in stripped]
    return "\n".join(indented)
