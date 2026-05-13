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


def extract_expected_name(template: str) -> Optional[str]:
    """Extract the function or class name from the template (before EVOLVE-BLOCK).

    Used by the static analysis pre-filter to verify the generated code
    defines the expected symbol.
    """
    for line in template.splitlines():
        m = re.match(r'^\s*(?:def|class|async def)\s+(\w+)', line)
        if m:
            return m.group(1)
    return None


def replace_block_content(full_code: str, new_block: str) -> str:
    """Replace the content between EVOLVE-BLOCK-START and EVOLVE-BLOCK-END markers.

    Used by focused mutation mode. Preserves the surrounding code and normalizes
    the indentation of the new block to match the template's block indentation.

    Args:
        full_code: The complete program with EVOLVE-BLOCK markers.
        new_block: The new implementation content (without the markers).

    Returns:
        The full program with the block region replaced.
    """
    import textwrap

    lines = full_code.splitlines()
    start_idx = None
    end_idx = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if EVOLVE_BLOCK_START in stripped or stripped == ALT_START:
            start_idx = i
        if EVOLVE_BLOCK_END in stripped or stripped == ALT_END:
            end_idx = i

    if start_idx is None or end_idx is None or start_idx >= end_idx:
        return full_code

    # Detect indentation from the first non-empty line in the old block
    indent = ""
    for i in range(start_idx + 1, end_idx):
        if lines[i].strip():
            leading = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
            if leading:
                indent = leading
            break

    # Normalize indentation:
    # 1. Dedent the raw block using textwrap.dedent (removes common leading
    #    whitespace while preserving relative indentation)
    # 2. Strip leading/trailing blank lines
    # 3. Apply the template's block indentation
    clean_block = new_block
    if clean_block.strip():
        try:
            clean_block = textwrap.dedent(clean_block).strip()
        except Exception:
            clean_block = clean_block.strip()
        indented = textwrap.indent(clean_block, indent)
        new_lines = lines[:start_idx + 1] + [indented] + lines[end_idx:]
    else:
        new_lines = lines[:start_idx + 1] + lines[end_idx:]

    return "\n".join(new_lines)


def replace_block(code: str, new_code: str) -> str:
    """DEPRECATED: LLM now generates the complete program. This function returns
    new_code as-is. Kept for backwards compatibility with any external callers.
    """
    import warnings
    warnings.warn(
        "replace_block is deprecated — LLM generates full programs. "
        "This function returns new_code as-is and will be removed in v0.3.",
        DeprecationWarning,
        stacklevel=2,
    )
    return new_code
