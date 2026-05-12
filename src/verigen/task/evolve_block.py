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


def replace_block(code: str, new_code: str) -> str:
    """Replace the content with new generated code.

    The LLM generates the full program (EVOLVE-BLOCK markers are
    informational). Returns the new code as-is.
    """
    return new_code
