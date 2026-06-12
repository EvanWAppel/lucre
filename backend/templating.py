from pathlib import Path

from fastapi.templating import Jinja2Templates


def money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}"


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["money"] = money
