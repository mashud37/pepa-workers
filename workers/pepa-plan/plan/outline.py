from backends import llm
from backends import prompt


def generate(idea, literature, skeleton, structure=None, blueprint=None):
    return llm.complete(
        prompt.outline_system(),
        prompt.outline_prompt(idea, literature, skeleton, structure, blueprint),
        max_tokens=4000,
        quality=True,
    )
