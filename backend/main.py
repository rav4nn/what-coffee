import sys
import os
import json
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import anthropic
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.retrieval_service import search_coffees

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="What Coffee API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this when you deploy
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# In-memory session store (fine for development)
sessions: dict = {}

# ── Load system prompt ────────────────────────────────────────────────────────

def load_system_prompt(coffee_context: str) -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "system_prompt.txt")
    with open(prompt_path, encoding="utf-8") as f:
        template = f.read()
    return template.replace("{COFFEE_CONTEXT}", coffee_context)

# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message:    str
    session_id: str | None = None

class ChatResponse(BaseModel):
    session_id: str
    response:   str

# ── Preference extraction ─────────────────────────────────────────────────────

def extract_preferences(messages: list) -> dict:
    """
    Quick pass to pull structured preferences from conversation history.
    Used to query the database before generating a response.
    """
    conversation_text = " ".join(
        m["content"] for m in messages if m["role"] == "user"
    ).lower()

    prefs = {
        "roast_level":      None,
        "brew_method":      None,
        "flavor_keywords":  [],
        "process":          None,
        "max_price":        None,
    }

    # roast level
    if any(w in conversation_text for w in ["light", "fruity", "bright", "acidic", "floral"]):
        prefs["roast_level"] = "light"
    elif any(w in conversation_text for w in ["dark", "bold", "strong", "bitter", "intense"]):
        prefs["roast_level"] = "dark"
    elif any(w in conversation_text for w in ["medium", "balanced", "smooth"]):
        prefs["roast_level"] = "medium"

    # brew method
    brew_map = {
        "espresso":             "Espresso",
        "pour over":            "Pour Over",
        "v60":                  "Pour Over",
        "french press":         "French Press",
        "aeropress":            "AeroPress",
        "moka pot":             "Moka Pot",
        "cold brew":            "Cold Brew",
        "south indian filter":  "South Indian Filter",
        "filter coffee":        "South Indian Filter",
        "drip":                 "Drip",
    }
    for keyword, method in brew_map.items():
        if keyword in conversation_text:
            prefs["brew_method"] = method
            break

    # flavor keywords
    flavor_words = [
        "chocolate", "caramel", "fruity", "citrus", "berry",
        "floral", "nutty", "spicy", "honey", "vanilla",
        "tropical", "winey", "earthy", "smoky"
    ]
    prefs["flavor_keywords"] = [f for f in flavor_words if f in conversation_text]

    # process
    if "natural" in conversation_text:
        prefs["process"] = "natural"
    elif "washed" in conversation_text:
        prefs["process"] = "washed"
    elif "honey" in conversation_text:
        prefs["process"] = "honey"

    # budget
    import re
    price_match = re.search(r"(?:under|below|less than|budget|₹|rs\.?)\s*(\d+)", conversation_text)
    if price_match:
        prefs["max_price"] = float(price_match.group(1))

    return prefs

# ── Format coffees for LLM context ───────────────────────────────────────────

def format_coffee_context(coffees: list) -> str:
    if not coffees:
        return "No specific coffees found for this query."

    lines = []
    for i, c in enumerate(coffees, 1):
        lines.append(f"""
COFFEE {i}: {c['name']} by {c['roaster']}
  Roast: {c['roast_level']} | Process: {c['process']} | Origin: {c['origin']}
  Flavor Notes: {c['flavor_notes']}
  Brew Methods: {c['brew_methods']}
  Price: ₹{c['price_min']}
  Description: {c['description']}
  Buy here: {c['affiliate_url']}
""")
    return "\n".join(lines)

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "What Coffee API is running"}


@app.post("/chat")
async def chat(request: ChatRequest):
    # get or create session
    session_id = request.session_id or str(uuid.uuid4())
    if session_id not in sessions:
        sessions[session_id] = []

    # add user message to history
    sessions[session_id].append({
        "role":    "user",
        "content": request.message
    })

    # extract preferences and query database
    prefs   = extract_preferences(sessions[session_id])
    coffees = search_coffees(
        roast_level     = prefs["roast_level"],
        brew_method     = prefs["brew_method"],
        flavor_keywords = prefs["flavor_keywords"],
        process         = prefs["process"],
        max_price       = prefs["max_price"],
        limit           = 5
    )

    # build system prompt with relevant coffees injected
    coffee_context = format_coffee_context(coffees)
    system_prompt  = load_system_prompt(coffee_context)

    # stream response from Claude
    def stream_response():
        full_response = ""
        with client.messages.stream(
            model      = "claude-sonnet-4-6",
            max_tokens = 1024,
            system     = system_prompt,
            messages   = sessions[session_id],
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                yield text

        # save assistant response to session history
        sessions[session_id].append({
            "role":    "assistant",
            "content": full_response
        })

    return StreamingResponse(stream_response(), media_type="text/plain")


@app.delete("/chat/{session_id}")
def clear_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
    return {"status": "session cleared"}