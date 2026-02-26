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

from services.retrieval_service import search_coffees

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

MAX_TURNS = 8  # hard cap per session — no API call beyond this

# ── Tool definition ───────────────────────────────────────────────────────────

SEARCH_TOOL = {
    "name": "search_coffees",
    "description": (
        "Search the coffee database for coffees that match the user's preferences. "
        "Call this as soon as you have the user's brew method AND flavor preferences. "
        "Do not keep asking questions — call the tool and present the results."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "brew_method": {
                "type": "string",
                "description": "Brewing equipment, e.g. 'Pour Over', 'Espresso', 'French Press', 'AeroPress', 'Moka Pot', 'South Indian Filter', 'Cold Brew'",
            },
            "roast_level": {
                "type": "string",
                "enum": ["light", "medium-light", "medium", "medium-dark", "dark"],
                "description": "Preferred roast level",
            },
            "flavor_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Flavor descriptors the user mentioned, e.g. ['fruity', 'citrus', 'chocolate', 'caramel', 'floral']",
            },
            "max_price": {
                "type": "number",
                "description": "Maximum budget in INR per 250g",
            },
        },
        "required": [],
    },
}


def _format_search_results(coffees: list[dict]) -> str:
    if not coffees:
        return "No coffees found matching those preferences."
    lines = []
    for c in coffees:
        price = f"Rs.{int(c['price_min'])}/250g" if c.get("price_min") else ""
        lines.append(
            f"- {c['roaster']} | {c['name']} | roast:{c.get('roast_level','')} | "
            f"process:{c.get('process','')} | origin:{c.get('origin','')} | "
            f"flavors:{c.get('flavor_notes','')} | {price} | {c.get('source_url','')}"
        )
    return "\n".join(lines)

# ── Load static content at startup ───────────────────────────────────────────

def _load_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "system_prompt.txt")
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

SYSTEM_PROMPT = _load_system_prompt()

_log("INFO", "startup", system_prompt_chars=len(SYSTEM_PROMPT))

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

    # Count only real user turns (not tool_result messages)
    turn = sum(
        1 for m in sessions[session_id]
        if m["role"] == "user" and isinstance(m.get("content"), str)
    ) + 1

    _log("INFO", "chat_request",
         session_id=session_id,
         is_new_session=is_new,
         turn=turn,
         message_length=len(request.message))

    # Hard turn cap — return canned message without calling Claude
    if turn > MAX_TURNS:
        _log("INFO", "turn_limit_reached", session_id=session_id)
        canned = "You've reached the end of this session! Refresh the page to start fresh and discover more coffees."
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
        usage = None
        try:
            # ── First call: conversation or tool invocation ───────────────────
            with client.messages.stream(
                model      = "claude-haiku-4-5-20251001",
                max_tokens = 600,
                system     = SYSTEM_PROMPT,
                tools      = [SEARCH_TOOL],
                messages   = sessions[session_id],
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield text
                first_msg = stream.get_final_message()
                usage = first_msg.usage

            # ── If Claude called the search tool ─────────────────────────────
            if first_msg.stop_reason == "tool_use":
                tool_block = next(b for b in first_msg.content if b.type == "tool_use")
                tool_input = tool_block.input

                _log("INFO", "tool_call",
                     session_id=session_id,
                     turn=turn,
                     brew_method=tool_input.get("brew_method"),
                     roast_level=tool_input.get("roast_level"),
                     flavor_keywords=tool_input.get("flavor_keywords"))

                results = search_coffees(
                    brew_method     = tool_input.get("brew_method"),
                    roast_level     = tool_input.get("roast_level"),
                    flavor_keywords = tool_input.get("flavor_keywords"),
                    max_price       = tool_input.get("max_price"),
                    limit           = 3,
                )
                tool_result = _format_search_results(results)

                followup_messages = sessions[session_id] + [
                    {"role": "assistant", "content": first_msg.content},
                    {"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": tool_block.id, "content": tool_result}
                    ]},
                ]

                # ── Second call: Claude writes recommendation from results ────
                rec_response = ""
                with client.messages.stream(
                    model      = "claude-haiku-4-5-20251001",
                    max_tokens = 600,
                    system     = SYSTEM_PROMPT,
                    tools      = [SEARCH_TOOL],
                    messages   = followup_messages,
                ) as stream2:
                    for text in stream2.text_stream:
                        rec_response += text
                        yield text
                    usage = stream2.get_final_message().usage

                # Store full tool exchange in session history
                sessions[session_id].append({"role": "assistant", "content": first_msg.content})
                sessions[session_id].append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": tool_block.id, "content": tool_result}
                ]})
                sessions[session_id].append({"role": "assistant", "content": rec_response})

            else:
                # Plain conversational response
                sessions[session_id].append({"role": "assistant", "content": full_response})

            _log("INFO", "chat_response",
                 session_id=session_id,
                 turn=turn,
                 duration_ms=round((time.perf_counter() - t0) * 1000),
                 response_length=len(full_response),
                 input_tokens=usage.input_tokens if usage else 0,
                 output_tokens=usage.output_tokens if usage else 0,
                 used_tool=(first_msg.stop_reason == "tool_use"))

        except Exception as exc:
            _log("ERROR", "chat_error",
                 session_id=session_id,
                 turn=turn,
                 duration_ms=round((time.perf_counter() - t0) * 1000),
                 error=str(exc))
            raise

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
