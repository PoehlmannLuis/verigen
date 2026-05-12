def regex_match(pattern: str, string: str) -> bool:
    """Return True if the pattern matches the entire string.

    Supported operators:
        `.`  — any single character
        `*`  — zero or more of the preceding character/group
        `?`  — zero or one of the preceding character/group
    No escaping, no character classes, no anchors (^/$) — match is full-string.

    Examples:
        regex_match("ab", "ab")       -> True
        regex_match("a.b", "acb")     -> True
        regex_match("ab*", "abbb")    -> True
        regex_match("ab?", "a")       -> True
        regex_match("a.*b", "axxxb")  -> True
    """
    # EVOLVE-BLOCK-START
    raise NotImplementedError("Replace this code!")
    # EVOLVE-BLOCK-END
