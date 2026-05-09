"""LLM agent orchestration. Calls mcp-news-server over HTTP only (LangChain not wired yet)."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="BriefForge Agent Service",
    description="Agent + briefing API. Web and browsers talk only to this service.",
    version="0.1.0",
)

_mcp_base = os.getenv("MCP_NEWS_SERVER_URL", "http://localhost:8001").rstrip("/")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "agent-service",
        "mcp_news_server_url": _mcp_base,
    }


@app.post("/v1/chat")
def chat(body: ChatRequest) -> dict:
    return {
        "status": "placeholder",
        "reply": "Agent not implemented yet. Your message was received.",
        "message_echo": body.message,
        "mcp_news_server_url": _mcp_base,
    }
