"""DSPy signatures for verifiable code generation."""

import dspy


class GenerateInitialBlock(dspy.Signature):
    """Generate a Python program that satisfies the task description.

    The program_template is a starting point with EVOLVE-BLOCK-START / END
    markers showing what needs to be implemented. Write the COMPLETE
    program — the markers are hints about what to change, but you can
    modify anything.
    """

    task_description = dspy.InputField(
        desc="What the program should accomplish"
    )
    task_context = dspy.InputField(
        desc="Rich task instructions, optimization hints, and performance targets"
    )
    program_template = dspy.InputField(
        desc="Starting Python code with EVOLVE-BLOCK markers showing editable region"
    )
    generated_code = dspy.OutputField(
        desc="Complete Python program with correct indentation and implementation"
    )


class ImproveBlockMutation(dspy.Signature):
    """Improve the Python program based on evaluation feedback and change history.

    You have access to:
    1. The task description (what the code should do)
    2. The task context (rich instructions, optimization targets, algorithm hints)
    3. The original program template (the starting point with EVOLVE-BLOCK markers)
    4. The CURRENT code (the best version so far)
    5. Evaluation feedback from the last run (score, errors, suggestions)
    6. What was changed in the previous iteration and what was learned

    Learn from past attempts. If the last change made things worse, revert
    the core approach and try a different strategy. Write the COMPLETE
    program — you can change anything.
    """

    task_description = dspy.InputField(
        desc="What the program should accomplish"
    )
    task_context = dspy.InputField(
        desc="Rich task instructions, optimization hints, and performance targets"
    )
    program_template = dspy.InputField(
        desc="The original starting code with EVOLVE-BLOCK markers"
    )
    current_code = dspy.InputField(
        desc="The current best version of the code"
    )
    evaluation_feedback = dspy.InputField(
        desc="Feedback from the last evaluation: pass/fail, score, errors, and suggestions for improvement"
    )
    change_history = dspy.InputField(
        desc="What was changed previously and whether it helped. Learn from past mistakes."
    )
    generated_code = dspy.OutputField(
        desc="The improved version of the program (the COMPLETE replacement). Keep code compact."
    )
    change_rationale = dspy.OutputField(
        desc="Brief explanation of what you changed and why. This will be shown to the next iteration as change_history."
    )


class FocusedBlockMutation(dspy.Signature):
    """Improve just the implementation inside the EVOLVE-BLOCK-START/END markers.

    You DON'T need to write the full program — only the inner implementation
    that goes BETWEEN the markers. The surrounding code (class, function
    signature, imports, helper methods) is preserved automatically.

    You have access to:
    1. The task description (what the code should do)
    2. The full surrounding code context (everything outside the EVOLVE-BLOCK)
    3. The current implementation inside the EVOLVE-BLOCK
    4. Evaluation feedback and change history

    Make targeted improvements to the inner implementation. Keep the same
    indentation level as the original block content.
    """

    task_description = dspy.InputField(
        desc="What the program should accomplish"
    )
    task_context = dspy.InputField(
        desc="Rich task instructions, optimization hints, and performance targets"
    )
    surrounding_context = dspy.InputField(
        desc="The full program code. Your new implementation replaces only the region between EVOLVE-BLOCK-START and EVOLVE-BLOCK-END"
    )
    current_block = dspy.InputField(
        desc="The current code inside the EVOLVE-BLOCK region that needs improvement"
    )
    evaluation_feedback = dspy.InputField(
        desc="Feedback from the last evaluation: pass/fail, score, errors, and suggestions"
    )
    change_history = dspy.InputField(
        desc="What was changed in the previous iteration and whether it helped"
    )
    new_block = dspy.OutputField(
        desc="The improved implementation for the EVOLVE-BLOCK region only. Keep the same indentation. Do NOT include the # EVOLVE-BLOCK markers or the function/class wrapper."
    )
    change_rationale = dspy.OutputField(
        desc="Brief explanation of what you changed and why. This will be shown to the next iteration as change_history."
    )
