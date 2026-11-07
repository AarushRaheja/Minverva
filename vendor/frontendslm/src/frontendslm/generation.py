"""Version 2: generate one component; assemble the trusted stylesheet outside the model."""
import re

from frontendslm.schemas import SourceManifest

FIXED_CSS = """@tailwind base;
@tailwind components;
@tailwind utilities;
html { font-family: ui-sans-serif, system-ui, sans-serif; }
body { margin: 0; }
*, *::before, *::after { box-sizing: border-box; }
:focus-visible { outline: 2px solid currentColor; outline-offset: 3px; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
"""


def split_thinking_tokens(token_ids: list[int], end_thinking_id: int) -> tuple[list[int], list[int]]:
    """Use the model's actual delimiter token, never a substring guessed from TSX."""
    if token_ids.count(end_thinking_id) != 1:
        raise ValueError('Expected exactly one thinking/final-answer delimiter token')
    index = token_ids.index(end_thinking_id)
    if index == len(token_ids) - 1:
        raise ValueError('Thinking completed without a final answer')
    return token_ids[:index], token_ids[index + 1:]


def component_manifest(raw: str, *, truncated: bool = False) -> SourceManifest:
    if truncated:
        raise ValueError("Generation exhausted its token budget; incomplete source is not accepted")
    source = raw.strip()
    if source.startswith("```"):
        match = re.fullmatch(r"```(?:tsx|typescript|jsx)?\n(.*?)\n```", source, re.DOTALL)
        if not match:
            raise ValueError("Expected exactly one TSX file, optionally enclosed in one fence")
        source = match.group(1).strip()
    if not re.match(r"(?:import\s|export\s|(?:const|function|type|interface)\s|/\*)", source):
        raise ValueError("Expected TSX source, not a JSON bundle or explanation")
    if "```" in source or "export default" not in source:
        raise ValueError("Expected one complete default-exported component")
    # Syntax/import/type correctness is measured by the unchanged isolated build.
    return SourceManifest(design_tokens={}, component_tree=["App"],
                          files={"src/App.tsx": source + "\n", "src/index.css": FIXED_CSS})
