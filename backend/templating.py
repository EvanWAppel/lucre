from pathlib import Path

from fastapi.templating import Jinja2Templates
from starlette.requests import Request


def money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}"


# Identity / links surfaced on the recruiter-facing intro and About pages.
SITE = {
    "owner_name": "Evan Appel",
    "tagline": (
        "A data and applied-AI professional whose distinguishing skill is using AI "
        "agents to make data reliably accessible — and bringing others along the way."
    ),
    "github_url": "https://github.com/EvanWAppel",
    "linkedin_url": "https://www.linkedin.com/in/evan-appel-8885569b/",
    "contact_email": "appelew@gmail.com",
    "resume_url": "/static/evan-appel-resume.pdf",
}


def _site_context(_request: Request) -> dict:
    """Make the identity/links block available to every template."""
    return {"site": SITE}


templates = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates"),
    context_processors=[_site_context],
)
templates.env.filters["money"] = money
