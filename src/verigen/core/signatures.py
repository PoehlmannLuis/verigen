"""DSPy signatures for verifiable code generation."""

import dspy


class GenerateInitialBlock(dspy.Signature):
    """Implement the code inside an EVOLVE-BLOCK region of a Python program.

    The EVOLVE-BLOCK-START / EVOLVE-BLOCK-END markers delimit the region
    you need to fill in. Everything outside those markers is fixed context.
    Write valid Python code at the correct indentation level for the block.
    """

    task_description = dspy.InputField(
        desc="What the program should accomplish"
    )
    program_template = dspy.InputField(
        desc="Python program with EVOLVE-BLOCK-START and EVOLVE-BLOCK-END markers showing the region to implement"
    )
    block_implementation = dspy.OutputField(
        desc="Python code for the EVOLVE-BLOCK region. ALL lines must start at the SAME indentation level. Do NOT add any indentation at the beginning of lines — the system handles indentation. Write each statement on its own line without leading spaces."
    )


class ImproveBlockMutation(dspy.Signature):
    """Improve the code inside an EVOLVE-BLOCK region based on evaluation feedback.

    You have access to:
    1. The task description (what the function should do)
    2. The full program template (showing where the EVOLVE-BLOCK is)
    3. The CURRENT code inside the EVOLVE-BLOCK
    4. Evaluation feedback from the last run (score, errors, suggestions)

    Make targeted improvements that fix errors or improve the score.
    Write valid Python code. All lines must use the SAME indentation level.
    """

    task_description = dspy.InputField(
        desc="What the program should accomplish"
    )
    program_context = dspy.InputField(
        desc="The full program template with EVOLVE-BLOCK-START/END markers showing where the editable region is"
    )
    current_block_code = dspy.InputField(
        desc="The code currently inside the EVOLVE-BLOCK region"
    )
    evaluation_feedback = dspy.InputField(
        desc="Feedback from the last evaluation: pass/fail, score, errors, and suggestions for improvement"
    )
    improved_block_code = dspy.OutputField(
        desc="The improved Python code for the EVOLVE-BLOCK region. ALL lines must start at the SAME indentation level. Do NOT add any leading spaces or tabs — the system handles indentation automatically."
    )
    change_rationale = dspy.OutputField(
        desc="Brief explanation of what was changed and why it should improve the result"
    )
