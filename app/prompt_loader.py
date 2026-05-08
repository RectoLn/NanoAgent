from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).parent
PROMPTS_DIR = APP_DIR / "prompts"


def load_prompt(path: str) -> str:
    """Load a prompt file relative to app/ or app/prompts/."""
    prompt_path = Path(path)
    if prompt_path.is_absolute():
        full_path = prompt_path
    elif prompt_path.parts and prompt_path.parts[0] == "prompts":
        full_path = APP_DIR / prompt_path
    else:
        full_path = PROMPTS_DIR / prompt_path

    with open(full_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def render_prompt(path: str, **values: Any) -> str:
    """Render a prompt by replacing {name} placeholders with string values."""
    text = load_prompt(path)
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text
