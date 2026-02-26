import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import anthropic
from dotenv import load_dotenv

from services.retrieval_service import get_all_coffees_minified

load_dotenv()

# ── Logging setup ─────────────────────────────────────────────────────────────

class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts":    datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "msg":   record.getMessage(),
        }
        if hasattr(record, "data"):
            payload.update(record.data)
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload)

_handler = logging.StreamHandler()
_handler.setFormatter(_JSONFormatter())

log = logging.getLogger("what_coffee")
log.addHandler(_handler)
log.setLevel(logging.INFO)
log.propagate = False


def _log(level: str, msg: str, **data):
    record = logging.LogRecord(
        name="what_coffee", level=getattr(logging, level),
        pathname="", lineno=0, msg=msg, args=(), exc_info=None,
    )
    record.data = data
    log.handle(record)

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

MAX_TURNS      = 8   # hard cap per session — no API call beyond this
HISTORY_WINDOW = 6   # messages sent as context (3 turn pairs)

# ── Load static content at startup ───────────────────────────────────────────

def _load_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "system_prompt.txt")
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

SYSTEM_PROMPT = _load_system_prompt()
COFFEE_DB     = get_all_coffees_minified()

_log("INFO", "startup",
     coffee_db_lines=COFFEE_DB.count("\n"),
     system_prompt_chars=len(SYSTEM_PROMPT))

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
    is_new     = session_id not in sessions
    if is_new:
        sessions[session_id] = []

    turn = len(sessions[session_id]) // 2 + 1

    _log("INFO", "chat_request",
         session_id=session_id,
         is_new_session=is_new,
         turn=turn,
         message_length=len(request.message))

    # Hard turn cap — return canned message without calling Claude
    if turn > MAX_TURNS:
        _log("INFO", "turn_limit_reached", session_id=session_id)
        canned = "You've reached the end of this session! Refresh the page to start fresh and discover more coffees. ☕"
        return StreamingResponse(
            iter([canned]),
            media_type = "text/plain",
            headers    = {"X-Session-Id": session_id},
        )

    sessions[session_id].append({
        "role":    "user",
        "content": request.message,
    })

    def stream_response():
        full_response = ""
        t0 = time.perf_counter()
        # Sliding window — cap how much history is sent to Claude
        context = sessions[session_id][-HISTORY_WINDOW:]
        try:
            with client.messages.stream(
                model      = "claude-haiku-4-5-20251001",
                max_tokens = 600,
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
                messages   = context,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield text

                usage = stream.get_final_message().usage

            _log("INFO", "chat_response",
                 session_id=session_id,
                 turn=turn,
                 duration_ms=round((time.perf_counter() - t0) * 1000),
                 response_length=len(full_response),
                 input_tokens=usage.input_tokens,
                 output_tokens=usage.output_tokens,
                 cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0),
                 cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0))

        except Exception as exc:
            _log("ERROR", "chat_error",
                 session_id=session_id,
                 turn=turn,
                 duration_ms=round((time.perf_counter() - t0) * 1000),
                 error=str(exc))
            raise

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
        _log("INFO", "session_cleared", session_id=session_id)
    return {"status": "session cleared"}
