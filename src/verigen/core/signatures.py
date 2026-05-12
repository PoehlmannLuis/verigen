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
    program_template = dspy.InputField(
        desc="Starting Python code with EVOLVE-BLOCK markers showing editable region"
    )
    generated_code = dspy.OutputField(
        desc="Complete Python program with correct indentation and implementation"
    )


class ImproveBlockMutation(dspy.Signature):
    """Improve the Python program based on evaluation feedback.

    You have access to:
    1. The task description (what the code should do)
    2. The original program template (the starting point)
    3. The CURRENT code (the best version so far)
    4. Evaluation feedback from the last run (score, errors, suggestions)

    Make targeted improvements that fix errors or improve the score.
    Write the COMPLETE program — you can change anything.
    """

    task_description = dspy.InputField(
        desc="What the program should accomplish"
    )
    program_context = dspy.InputField(
        desc="The original program template with EVOLVE-BLOCK markers"
    )
    current_code = dspy.InputField(
        desc="The current best version of the code"
    )
    evaluation_feedback = dspy.InputField(
        desc="Feedback from the last evaluation: pass/fail, score, errors, and suggestions for improvement"
    )
    generated_code = dspy.OutputField(
        desc="The improved version of the program (the COMPLETE replacement). Keep code compact."
    )
