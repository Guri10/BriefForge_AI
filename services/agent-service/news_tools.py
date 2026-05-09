"""LangChain tool schemas for MCP news endpoints (execution is manual in agent_runner)."""

from __future__ import annotations

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field


class SearchNewsInput(BaseModel):
    """Search news articles via mcp-news-server (NewsAPI everything-style)."""

    model_config = ConfigDict(populate_by_name=True)

    query: str = Field(..., description="Keywords or question to search for in news articles.")
    language: str | None = Field(None, description="Optional ISO 639-1 language code, e.g. en")
    from_: str | None = Field(
        None,
        alias="from",
        description="Optional start date YYYY-MM-DD",
    )
    to: str | None = Field(None, description="Optional end date YYYY-MM-DD")
    page_size: int | None = Field(
        None,
        ge=1,
        le=100,
        description="Max articles to return (capped at 20 server-side)",
    )


class TopHeadlinesInput(BaseModel):
    """Top headlines via mcp-news-server."""

    country: str | None = Field(None, description="Optional ISO country code, e.g. us")
    category: str | None = Field(
        None,
        description="Optional category: business, entertainment, general, health, science, sports, technology",
    )
    q: str | None = Field(None, description="Optional keywords to filter headlines")
    page_size: int | None = Field(
        None,
        ge=1,
        le=100,
        description="Max articles (capped at 20 server-side)",
    )


def _stub(**_kwargs: object) -> str:
    """LangChain may bind this; real execution is in agent_runner manual loop."""
    return ""


def make_news_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            func=_stub,
            name="search_news",
            description=(
                "Search news articles across sources. Call this before stating facts about "
                "recent events not covered by headlines. Arguments are passed to the news service only."
            ),
            args_schema=SearchNewsInput,
        ),
        StructuredTool.from_function(
            func=_stub,
            name="top_headlines",
            description=(
                "Get current top headlines, optionally by country or category. Prefer for "
                "'today', 'headlines', or broad breaking-style questions."
            ),
            args_schema=TopHeadlinesInput,
        ),
    ]
