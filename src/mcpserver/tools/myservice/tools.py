"""Example service: one tool, one input model, one output model.

Copy this directory (`tools/<yourservice>/`) for each group of tools. Keep the tool a plain
function: registration happens in `tools/__init__.py`, never through a decorator here.
"""

from ...models.myserver import OutputPhrase, Tool1Input


async def tool1(word: Tool1Input) -> OutputPhrase:
    """Echo the chosen word back in a sentence.

    This docstring is the tool description the model reads, so it must say what the tool does,
    when to call it, and what it returns.
    """
    tool_logic: str = f"Votre choix : {word}"
    return OutputPhrase(returned_phrase=tool_logic)
