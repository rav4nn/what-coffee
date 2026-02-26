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
from openai import OpenAI
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

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

# In-memory session store — list of message dicts per session
sessions: dict = {}

MAX_TURNS = 8  # hard cap per session

# ── Tool definition ───────────────────────────────────────────────────────────

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_coffees",
        "description": (
            "Search the coffee database for coffees that match the user's preferences. "
            "Call this as soon as you have the user's brew method AND flavor preferences. "
            "Do not keep asking questions — call the tool and present the results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "brew_method": {
                    "type": "string",
                    "description": "Brewing equipment, e.g. Pour Over, Espresso, French Press, AeroPress, Moka Pot, South Indian Filter, Cold Brew",
                },
                "roast_level": {
                    "type": "string",
                    "description": "Preferred roast level: light, medium-light, medium, medium-dark, dark",
                },
                "flavor_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Flavor descriptors the user mentioned, e.g. fruity, citrus, chocolate, caramel, floral",
                },
                "max_price": {
                    "type": "number",
                    "description": "Maximum budget in INR per 250g",
                },
            },
        },
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

# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_real_user_turn(msg: dict) -> bool:
    """True for user text messages, False for tool result messages."""
    return msg.get("role") == "user" and isinstance(msg.get("content"), str)

def _build_messages(session_id: str) -> list[dict]:
    """Prepend system prompt to session history for each API call."""
    return [{"role": "system", "content": SYSTEM_PROMPT}] + sessions[session_id]

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

    turn = sum(1 for m in sessions[session_id] if _is_real_user_turn(m)) + 1

    _log("INFO", "chat_request",
         session_id=session_id,
         is_new_session=is_new,
         turn=turn,
         message_length=len(request.message))

    if turn > MAX_TURNS:
        _log("INFO", "turn_limit_reached", session_id=session_id)
        canned = "You've reached the end of this session! Refresh the page to start fresh and discover more coffees."
        return StreamingResponse(
            iter([canned]),
            media_type = "text/plain",
            headers    = {"X-Session-Id": session_id},
        )

    sessions[session_id].append({"role": "user", "content": request.message})

    def stream_response():
        full_text         = ""
        rec_text          = ""
        tool_call_id      = None
        tool_call_name    = None
        tool_call_args    = ""
        t0                = time.perf_counter()

        try:
            # ── First call ────────────────────────────────────────────────────
            with client.chat.completions.create(
                model    = "deepseek-chat",
                messages = _build_messages(session_id),
                tools    = [SEARCH_TOOL],
                stream   = True,
                max_tokens = 600,
            ) as stream:
                for chunk in stream:
                    choice = chunk.choices[0]
                    delta  = choice.delta

                    if delta.content:
                        full_text += delta.content
                        yield delta.content

                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            if tc.id:
                                tool_call_id = tc.id
                            if tc.function and tc.function.name:
                                tool_call_name = tc.function.name
                            if tc.function and tc.function.arguments:
                                tool_call_args += tc.function.arguments

            # ── Tool call branch ──────────────────────────────────────────────
            if tool_call_name:
                fc_args = json.loads(tool_call_args)

                _log("INFO", "tool_call",
                     session_id=session_id,
                     turn=turn,
                     brew_method=fc_args.get("brew_method"),
                     roast_level=fc_args.get("roast_level"),
                     flavor_keywords=fc_args.get("flavor_keywords"))

                raw_flavors     = fc_args.get("flavor_keywords") or []
                flavor_keywords = list(raw_flavors) if isinstance(raw_flavors, list) else [k.strip() for k in str(raw_flavors).split(",") if k.strip()]

                max_price_raw = fc_args.get("max_price")
                max_price     = float(max_price_raw) if max_price_raw is not None else None

                results     = search_coffees(
                    brew_method     = fc_args.get("brew_method"),
                    roast_level     = fc_args.get("roast_level"),
                    flavor_keywords = flavor_keywords,
                    max_price       = max_price,
                    limit           = 3,
                )
                tool_result = _format_search_results(results)

                # Store assistant tool call + tool result in history
                sessions[session_id].append({
                    "role":       "assistant",
                    "content":    None,
                    "tool_calls": [{
                        "id":       tool_call_id,
                        "type":     "function",
                        "function": {
                            "name":      tool_call_name,
                            "arguments": tool_call_args,
                        },
                    }],
                })
                sessions[session_id].append({
                    "role":         "tool",
                    "content":      tool_result,
                    "tool_call_id": tool_call_id,
                })

                # ── Second call: stream the recommendation ────────────────────
                with client.chat.completions.create(
                    model      = "deepseek-chat",
                    messages   = _build_messages(session_id),
                    stream     = True,
                    max_tokens = 600,
                ) as stream2:
                    for chunk in stream2:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            rec_text += delta.content
                            yield delta.content

                sessions[session_id].append({"role": "assistant", "content": rec_text})

            else:
                # Plain conversational response
                sessions[session_id].append({"role": "assistant", "content": full_text})

            _log("INFO", "chat_response",
                 session_id=session_id,
                 turn=turn,
                 duration_ms=round((time.perf_counter() - t0) * 1000),
                 response_length=len(rec_text if tool_call_name else full_text),
                 used_tool=(tool_call_name is not None))

        except Exception as exc:
            _log("ERROR", "chat_error",
                 session_id=session_id,
                 turn=turn,
                 duration_ms=round((time.perf_counter() - t0) * 1000),
                 error=str(exc))
            err = str(exc)
            if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                yield "I'm getting a lot of requests right now — please try again in a minute!"
            else:
                yield "Something went wrong on my end. Please try again!"

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
