from backends import llm, prompt


def refine(outline, feedback, skeleton):
    return llm.complete(
        prompt.refine_system(),
        prompt.refine_prompt(outline, feedback),
        max_tokens=4000,
        quality=True,
    )
