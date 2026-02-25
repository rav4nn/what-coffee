"""
enricher.py

Uses the Claude API to fill in missing fields for coffee products
that the normalizer couldn't extract via regex alone.

Fields it enriches:
  - flavor_notes   (e.g. ["Chocolate", "Citrus", "Caramel"])
  - roast_level    (light / medium-light / medium / medium-dark / dark)
  - process        (natural / washed / honey / anaerobic / carbonic maceration / monsooned)
  - origin         (e.g. "Chikmagalur", "Coorg", "Araku Valley")
  - brew_methods   (e.g. ["Espresso", "Pour Over"])
  - acidity        (low / medium / high)
  - body           (light / medium / full)

Run:
    python scraper/enricher.py

Requires:
    ANTHROPIC_API_KEY in your .env file
"""

import json
import time
import os
import re
from dotenv import load_dotenv
import anthropic

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

INPUT_FILE  = "normalized_coffees.json"
OUTPUT_FILE = "enriched_coffees.json"
PROGRESS_FILE = "enrichment_progress.json"  # saves progress so you can resume

MODEL       = "claude-haiku-4-5-20251001"   # fast + cheap — perfect for structured extraction
DELAY       = 0.3                            # seconds between API calls (avoid rate limits)
MAX_RETRIES = 3

VALID_ROAST_LEVELS = {
    "light", "medium-light", "medium", "medium-dark", "dark", "unknown"
}
VALID_PROCESSES = {
    "natural", "washed", "honey", "anaerobic",
    "carbonic maceration", "monsooned", "experimental", "unknown"
}
VALID_ACIDITY = {"low", "medium", "high", "unknown"}
VALID_BODY    = {"light", "medium", "full", "unknown"}

KNOWN_BREW_METHODS = {
    "Espresso", "Pour Over", "AeroPress", "French Press",
    "Moka Pot", "Cold Brew", "South Indian Filter", "Drip", "Siphon"
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def needs_enrichment(product: dict) -> bool:
    """Returns True if any key field is missing."""
    return (
        not product.get("flavor_notes") or
        product.get("roast_level") == "unknown" or
        product.get("process") == "unknown" or
        not product.get("brew_methods") or
        product.get("origin") in ("India", "", None) or
        product.get("acidity") == "unknown" or
        product.get("body") == "unknown"
    )


def build_prompt(product: dict) -> str:
    """Build a focused extraction prompt for a single coffee product."""
    missing = []
    if not product.get("flavor_notes"):
        missing.append("flavor_notes")
    if product.get("roast_level") == "unknown":
        missing.append("roast_level")
    if product.get("process") == "unknown":
        missing.append("process")
    if not product.get("brew_methods"):
        missing.append("brew_methods")
    if product.get("origin") in ("India", "", None):
        missing.append("origin")
    if product.get("acidity") == "unknown":
        missing.append("acidity")
    if product.get("body") == "unknown":
        missing.append("body")

    already_known = {
        "roast_level": product.get("roast_level"),
        "process":     product.get("process"),
        "origin":      product.get("origin"),
        "flavor_notes": product.get("flavor_notes"),
        "brew_methods": product.get("brew_methods"),
        "acidity":     product.get("acidity"),
        "body":        product.get("body"),
    }

    return f"""You are extracting structured data from an Indian specialty coffee product listing.

PRODUCT NAME: {product.get("name", "")}
ROASTER: {product.get("roaster", "")}
DESCRIPTION: {product.get("description", "")}
TAGS: {", ".join(product.get("tags", []))}

ALREADY KNOWN (do not change these):
{json.dumps({k: v for k, v in already_known.items() if v and v != "unknown"}, indent=2)}

FIELDS TO EXTRACT: {", ".join(missing)}

Return ONLY a valid JSON object with these exact fields (no explanation, no markdown):

{{
  "flavor_notes": ["Note1", "Note2", "Note3"],
  "roast_level": "light|medium-light|medium|medium-dark|dark|unknown",
  "process": "natural|washed|honey|anaerobic|carbonic maceration|monsooned|experimental|unknown",
  "brew_methods": ["Espresso", "Pour Over", "AeroPress", "French Press", "Moka Pot", "Cold Brew", "South Indian Filter"],
  "origin": "specific Indian region or estate name, e.g. Chikmagalur, Coorg, Araku Valley",
  "acidity": "low|medium|high|unknown",
  "body": "light|medium|full|unknown"
}}

Rules:
- flavor_notes: Extract actual flavor descriptors only (e.g. "Chocolate", "Citrus", "Caramel"). 
  Max 6 notes. Empty array [] if truly none mentioned.
- roast_level: Infer from context if not explicit. Espresso = medium-dark/dark. Filter = light/medium.
- process: Only what is explicitly stated or strongly implied. "unknown" if not mentioned.
- brew_methods: Only methods explicitly recommended. Empty array [] if none mentioned.
- origin: Be as specific as possible. Estate name > region > state. "India" only as last resort.
- If a field cannot be determined, use "unknown" for strings or [] for arrays."""


def parse_llm_response(text: str) -> dict | None:
    """Extract and validate JSON from LLM response."""
    # strip markdown fences if present
    text = re.sub(r"```json\s*|\s*```", "", text).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # try to find JSON object within the text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return None
        else:
            return None

    # validate and clean
    result = {}

    # flavor_notes — must be list of non-empty strings > 2 chars
    raw_notes = data.get("flavor_notes", [])
    if isinstance(raw_notes, list):
        result["flavor_notes"] = [
            str(n).strip().title()
            for n in raw_notes
            if isinstance(n, str) and len(n.strip()) > 2
        ][:6]
    else:
        result["flavor_notes"] = []

    # roast_level
    roast = str(data.get("roast_level", "unknown")).lower().strip()
    result["roast_level"] = roast if roast in VALID_ROAST_LEVELS else "unknown"

    # process
    process = str(data.get("process", "unknown")).lower().strip()
    result["process"] = process if process in VALID_PROCESSES else "unknown"

    # brew_methods — filter to known methods only
    raw_brew = data.get("brew_methods", [])
    if isinstance(raw_brew, list):
        result["brew_methods"] = [
            m for m in raw_brew
            if isinstance(m, str) and m.strip() in KNOWN_BREW_METHODS
        ]
    else:
        result["brew_methods"] = []

    # origin
    origin = str(data.get("origin", "India")).strip()
    result["origin"] = origin if origin else "India"

    # acidity
    acidity = str(data.get("acidity", "unknown")).lower().strip()
    result["acidity"] = acidity if acidity in VALID_ACIDITY else "unknown"

    # body
    body = str(data.get("body", "unknown")).lower().strip()
    result["body"] = body if body in VALID_BODY else "unknown"

    return result


def merge(original: dict, enriched: dict) -> dict:
    """Merge enriched fields into original, only filling in missing values."""
    updated = original.copy()

    if not original.get("flavor_notes") and enriched.get("flavor_notes"):
        updated["flavor_notes"] = enriched["flavor_notes"]

    if original.get("roast_level") == "unknown" and enriched.get("roast_level") != "unknown":
        updated["roast_level"] = enriched["roast_level"]

    if original.get("process") == "unknown" and enriched.get("process") != "unknown":
        updated["process"] = enriched["process"]

    if not original.get("brew_methods") and enriched.get("brew_methods"):
        updated["brew_methods"] = enriched["brew_methods"]

    if original.get("origin") in ("India", "", None) and enriched.get("origin") not in ("India", "", None):
        updated["origin"] = enriched["origin"]

    if original.get("acidity") == "unknown" and enriched.get("acidity") != "unknown":
        updated["acidity"] = enriched["acidity"]

    if original.get("body") == "unknown" and enriched.get("body") != "unknown":
        updated["body"] = enriched["body"]

    return updated


def load_progress() -> dict:
    """Load previously enriched results so we can resume if interrupted."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


# ── Main enrichment loop ──────────────────────────────────────────────────────

def enrich_all():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not found. "
            "Create a .env file in the backend folder with:\n"
            "ANTHROPIC_API_KEY=your_key_here"
        )

    client = anthropic.Anthropic(api_key=api_key)

    print(f"📂 Loading {INPUT_FILE}...")
    with open(INPUT_FILE, encoding="utf-8") as f:
        products = json.load(f)

    print(f"   {len(products)} products loaded")

    # load progress from previous run (if any)
    progress = load_progress()
    if progress:
        print(f"   Resuming — {len(progress)} products already enriched from previous run")

    to_enrich   = [p for p in products if needs_enrichment(p)]
    already_done = [p for p in products if not needs_enrichment(p)]

    print(f"   {len(to_enrich)} products need enrichment")
    print(f"   {len(already_done)} products already complete — skipping")
    print()

    enriched_results = []
    api_calls  = 0
    errors     = 0
    skipped    = 0

    for i, product in enumerate(to_enrich):
        key = product.get("source_url") or product.get("handle")

        # resume: skip if already done in a previous run
        if key in progress:
            enriched_results.append(progress[key])
            skipped += 1
            continue

        print(f"[{i+1}/{len(to_enrich)}] {product['roaster']} — {product['name'][:50]}")

        prompt = build_prompt(product)

        for attempt in range(MAX_RETRIES):
            try:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=500,
                    messages=[{"role": "user", "content": prompt}]
                )
                raw_text = response.content[0].text
                parsed   = parse_llm_response(raw_text)

                if parsed:
                    merged = merge(product, parsed)
                    enriched_results.append(merged)
                    progress[key] = merged
                    api_calls += 1

                    # show what was filled in
                    filled = []
                    if parsed.get("flavor_notes") and not product.get("flavor_notes"):
                        filled.append(f"flavor: {parsed['flavor_notes'][:3]}")
                    if parsed.get("roast_level") != "unknown" and product.get("roast_level") == "unknown":
                        filled.append(f"roast: {parsed['roast_level']}")
                    if parsed.get("process") != "unknown" and product.get("process") == "unknown":
                        filled.append(f"process: {parsed['process']}")
                    if filled:
                        print(f"   ✓ Filled: {' | '.join(filled)}")
                    else:
                        print(f"   ✓ No new data extracted")

                    break
                else:
                    print(f"   ✗ Could not parse response (attempt {attempt+1})")
                    if attempt == MAX_RETRIES - 1:
                        enriched_results.append(product)  # keep original
                        errors += 1

            except Exception as e:
                print(f"   ✗ API error: {e} (attempt {attempt+1})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)  # exponential backoff
                else:
                    enriched_results.append(product)
                    errors += 1

        # save progress every 10 products
        if (i + 1) % 10 == 0:
            save_progress(progress)
            print(f"   💾 Progress saved ({i+1}/{len(to_enrich)})")

        time.sleep(DELAY)

    # combine enriched + already-complete products
    final = enriched_results + already_done

    # save final output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    # clean up progress file on successful completion
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

    # ── Final quality report ──────────────────────────────────────────────────
    total = len(final)
    print(f"\n{'='*50}")
    print(f"✅ Enrichment complete — {OUTPUT_FILE}")
    print(f"{'='*50}")
    print(f"   API calls made:  {api_calls}")
    print(f"   Skipped (done):  {skipped}")
    print(f"   Errors:          {errors}")
    print()
    print(f"📊 Field coverage after enrichment:")

    def pct(n): return f"{n}/{total} ({100*n//total}%)"

    print(f"   Flavor notes:    {pct(sum(1 for p in final if p.get('flavor_notes')))}")
    print(f"   Roast level:     {pct(sum(1 for p in final if p.get('roast_level') != 'unknown'))}")
    print(f"   Process:         {pct(sum(1 for p in final if p.get('process') != 'unknown'))}")
    print(f"   Brew methods:    {pct(sum(1 for p in final if p.get('brew_methods')))}")
    print(f"   Specific origin: {pct(sum(1 for p in final if p.get('origin') not in ('India', '', None)))}")
    print(f"   Acidity:         {pct(sum(1 for p in final if p.get('acidity') != 'unknown'))}")
    print(f"   Body:            {pct(sum(1 for p in final if p.get('body') != 'unknown'))}")


if __name__ == "__main__":
    enrich_all()