from ...models.myserver import (
    Tool1Input,
    OutputPhrase
)
async def tool1(word:Tool1Input)->OutputPhrase:
    tool_logic : str = f"Votre choix : {word}"
    return OutputPhrase(returned_phrase=tool_logic)