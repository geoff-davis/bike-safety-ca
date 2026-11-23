"""Where the reports point readers: the project, and the pages that explain its methods."""

from __future__ import annotations

REPO = "https://github.com/geoff-davis/bike-safety-ca"


def doc(name: str) -> str:
    """The address of a page in the project's ``docs/`` on GitHub."""
    return f"{REPO}/blob/main/docs/{name}"


MODEL_DOC = doc("forecasting_model.md")
SHOWN = REPO.removeprefix("https://")  # how the address reads on paper
MADE_WITH = f"*Made with bike-safety-ca, free and open source: [{SHOWN}]({REPO}).*"
