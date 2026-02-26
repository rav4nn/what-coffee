import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import uuid
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import anthropic
from dotenv import load_dotenv

from services.retrieval_service import get_all_coffees_minified

load_dotenv()

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="What Coffee API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-Id"],
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), max_retries=3)

# In-memory session store
sessions: dict = {}

# ── Load static content at startup ───────────────────────────────────────────

def _load_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "system_prompt.txt")
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

SYSTEM_PROMPT = _load_system_prompt()
COFFEE_DB     = get_all_coffees_minified()

# ── Request model ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message:    str = Field(..., max_length=500)
    session_id: str | None = None

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "What Coffee API is running"}


@app.post("/chat")
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    if session_id not in sessions:
        sessions[session_id] = []

    sessions[session_id].append({
        "role":    "user",
        "content": request.message,
    })

    def stream_response():
        full_response = ""
        with client.messages.stream(
            model      = "claude-sonnet-4-6",
            max_tokens = 1024,
            system     = [
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                },
                {
                    "type": "text",
                    "text": (
                        "COFFEE DATABASE "
                        "(columns: roaster|name|roast|process|origin|flavors|brew_methods|price_inr|url):\n"
                        + COFFEE_DB
                    ),
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages   = sessions[session_id],
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                yield text

        sessions[session_id].append({
            "role":    "assistant",
            "content": full_response,
        })

    return StreamingResponse(
        stream_response(),
        media_type = "text/plain",
        headers    = {"X-Session-Id": session_id},
    )


@app.delete("/chat/{session_id}")
def clear_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
    return {"status": "session cleared"}
