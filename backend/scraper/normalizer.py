import json
import re
from collections import Counter

# ── Product type filters ──────────────────────────────────────────────────────

# Tags or name keywords that indicate a NON-coffee product
EXCLUDE_TAGS = {
    "event", "equipment", "merchandise", "course", "gift card",
    "gift-card", "brewing equipment", "grinder", "kettle", "scale",
    "courses", "events"
}

EXCLUDE_NAME_KEYWORDS = [
    "filter paper", "drip bag", "workshop", "event", "course",
    "mug", "tumbler", "merchandise", "gift card", "grinder",
    "kettle", "scale", "equipment", "t-shirt", "tote",
    "concentrate",  # Blue Tokai "Drop" concentrates are not roasted beans
]

# Keywords that confirm this IS a coffee product
COFFEE_CONFIRM_KEYWORDS = [
    "estate", "single origin", "blend", "roast", "arabica", "robusta",
    "gesha", "geisha", "natural", "washed", "honey", "anaerobic",
    "carbonic", "peaberry", "monsooned", "monsoon", "filter coffee",
    "espresso blend", "cold brew", "capsule"
]

# ── Roast level ───────────────────────────────────────────────────────────────

ROAST_MAP = {
    "light": [
        "light roast", "light-roast", "filter roast", "filter-roast",
        "light filter", "omni-roast light", "light omni"
    ],
    "medium-light": [
        "medium light", "medium-light", "omni roast", "omni-roast",
        "omni roast"
    ],
    "medium": [
        "medium roast", "medium-roast", "med roast"
    ],
    "medium-dark": [
        "medium dark", "medium-dark", "medium dark roast",
        "medium-dark-roast"
    ],
    "dark": [
        "dark roast", "dark-roast", "espresso roast", "french roast",
        "italian roast"
    ],
}

# ── Process method ────────────────────────────────────────────────────────────

PROCESS_KEYWORDS = {
    "natural": ["natural", "dry process", "dry processed", "sun dried"],
    "washed": ["washed", "wet process", "fully washed", "wet processed"],
    "honey": ["honey", "pulped natural", "semi-washed"],
    "anaerobic": ["anaerobic", "anaerobic natural", "anaerobic washed"],
    "carbonic maceration": ["carbonic maceration", "carbonic"],
    "experimental": ["experimental", "bioreactor", "fermented", "culture natural"],
    "monsooned": ["monsooned", "monsoon malabar"],
}

# ── Origin / Region ───────────────────────────────────────────────────────────

INDIAN_REGIONS = {
    "Chikmagalur": ["chikmagalur", "chikkamagalur"],
    "Coorg": ["coorg", "kodagu"],
    "Nilgiris": ["nilgiri", "nilgiris", "ooty"],
    "Yercaud": ["yercaud"],
    "Wayanad": ["wayanad"],
    "Araku Valley": ["araku", "paderu", "andhra"],
    "Bababudangiri": ["bababudangiri", "baba budangiri"],
    "Sakleshpur": ["sakleshpur", "sakleshpura"],
    "Anamalai": ["anamalai", "valparai"],
    "Munnar": ["munnar"],
    "Shevaroy Hills": ["shevaroy", "yercaud"],
    "Karnataka": ["karnataka"],
    "Kerala": ["kerala"],
    "Tamil Nadu": ["tamil nadu", "tamilnadu"],
}

# ── Brew methods ──────────────────────────────────────────────────────────────

BREW_METHOD_ALIASES = {
    "Espresso":             ["espresso", "commercial espresso", "home espresso"],
    "Pour Over":            ["pour over", "pourover", "v60", "chemex", "kalita"],
    "AeroPress":            ["aeropress", "inverted aeropress", "aerobie"],
    "French Press":         ["french press", "cafetiere"],
    "Moka Pot":             ["moka pot", "stovetop"],
    "Cold Brew":            ["cold brew", "cold water"],
    "South Indian Filter":  ["south indian filter", "coffee filter", "filter coffee", "channi"],
    "Drip":                 ["drip", "batch brew", "clever dripper"],
    "Siphon":               ["siphon", "vacuum pot"],
}

# ── Acidity / Body ────────────────────────────────────────────────────────────

ACIDITY_MAP = {
    "low":    ["acidity-low", "low acidity", "low-acidity"],
    "medium": ["acidity-medium", "medium acidity", "medium-acidity"],
    "high":   ["acidity-high", "acidity-medium-high", "high acidity", "bright"],
}

BODY_MAP = {
    "light":  ["light body", "light-body", "tea-like"],
    "medium": ["medium body", "medium-body"],
    "full":   ["full body", "full-body", "heavy body", "syrupy"],
}

# ── Weight normalization ──────────────────────────────────────────────────────

def normalize_weight(weight_str: str) -> str:
    """Standardize weight strings like '250 gm', '250g', '250 g' → '250g'"""
    w = weight_str.lower().strip()
    # extract the numeric part + unit
    match = re.search(r"(\d+)\s*(g|gm|gms|gram|grams|kg|kgs|kilogram)", w)
    if match:
        num, unit = match.group(1), match.group(2)
        if unit in ("kg", "kgs", "kilogram"):
            return f"{num}kg"
        return f"{num}g"
    return weight_str  # return original if we can't parse it


def extract_weight_variants(variants: list) -> list:
    """Deduplicate and normalize weight variants, keeping unique weights only."""
    seen_weights = set()
    clean_variants = []
    for v in variants:
        raw_weight = v.get("weight", "").split("/")[0].strip()  # "250g / Aeropress" → "250g"
        normalized = normalize_weight(raw_weight)
        if normalized not in seen_weights:
            seen_weights.add(normalized)
            clean_variants.append({
                "weight":    normalized,
                "price":     v.get("price", 0),
                "available": v.get("available", False),
            })
    return sorted(clean_variants, key=lambda x: x["price"])


# ── Core extraction helpers ───────────────────────────────────────────────────

def extract_roast_level(text: str, tags: list) -> str:
    tag_text = " ".join(t.lower() for t in tags)
    combined = f"{text.lower()} {tag_text}"
    for level, keywords in ROAST_MAP.items():
        if any(kw in combined for kw in keywords):
            return level
    return "unknown"


def extract_process(text: str, tags: list) -> str:
    tag_text = " ".join(t.lower() for t in tags)
    combined = f"{text.lower()} {tag_text}"
    for process, keywords in PROCESS_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return process
    return "unknown"


def extract_origin(text: str, tags: list) -> str:
    tag_text = " ".join(t.lower() for t in tags)
    combined = f"{text.lower()} {tag_text}"
    for region, keywords in INDIAN_REGIONS.items():
        if any(kw in combined for kw in keywords):
            return region
    return "India"  # default — all these roasters are Indian


def extract_brew_methods(text: str, tags: list, variants: list) -> list:
    # also check variant titles — Blue Tokai puts grind type in variants
    variant_text = " ".join(v.get("weight", "").lower() for v in variants)
    tag_text     = " ".join(t.lower() for t in tags)
    combined     = f"{text.lower()} {tag_text} {variant_text}"

    found = []
    for method, aliases in BREW_METHOD_ALIASES.items():
        if any(alias in combined for alias in aliases):
            found.append(method)
    return found


def extract_flavor_notes(tags: list, description: str) -> list:
    # First try tags with flavor prefixes
    flavor_tags = [
        re.sub(r"^(flavor:|taste:|notes:|tasting notes:|flavour:)", "", tag, flags=re.IGNORECASE).strip()
        for tag in tags
        if re.match(r"(flavor|taste|notes|tasting|flavour)", tag, re.IGNORECASE)
    ]
    if flavor_tags:
        return [n.title() for n in flavor_tags if len(n) > 2]

    # Try multiple regex patterns against the description
    patterns = [
        r"tasting notes[:\-\s]+([^\.\n\|]{5,100})",
        r"tastes? like[:\-\s]+([^\.\n\|]{5,100})",
        r"notes? of[:\-\s]+([^\.\n\|]{5,100})",
        r"flavou?rs?[:\-\s]+([^\.\n\|]{5,100})",
        r"cup profile[:\-\s]+([^\.\n\|]{5,100})",
        r"you'?ll? (?:taste|notice|find)[:\-\s]+([^\.\n\|]{5,80})",
        r"bright notes? of[:\-\s]+([^\.\n\|]{5,80})",
        r"notes? include[:\-\s]+([^\.\n\|]{5,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            raw = match.group(1)
            # split on comma, 'and', '&', '+'
            notes = re.split(r",\s*|\s+and\s+|\s*&\s*|\s*\+\s*", raw)
            # clean each note
            clean = []
            for note in notes:
                note = re.sub(r"\s+", " ", note).strip().title()
                # reject if too short, too long, or looks like a sentence fragment
                if 3 <= len(note) <= 30 and not re.search(r"\b(with|the|this|that|for|its|our)\b", note, re.IGNORECASE):
                    clean.append(note)
            if clean:
                return clean[:6]  # cap at 6 flavor notes

    return []


def extract_acidity(text: str, tags: list) -> str:
    tag_text = " ".join(t.lower() for t in tags)
    combined = f"{text.lower()} {tag_text}"
    for level, keywords in ACIDITY_MAP.items():
        if any(kw in combined for kw in keywords):
            return level
    return "unknown"


def extract_body(text: str) -> str:
    text_lower = text.lower()
    for level, keywords in BODY_MAP.items():
        if any(kw in text_lower for kw in keywords):
            return level
    return "unknown"


def is_coffee_product(product: dict) -> bool:
    """
    Two-stage filter:
    1. Hard exclude — tags or name contains known non-coffee keywords
    2. Soft confirm — at least one coffee keyword must be present
    """
    name     = product.get("name", "").lower()
    tags     = [t.lower() for t in product.get("tags", [])]
    desc     = product.get("description", "").lower()
    combined = f"{name} {' '.join(tags)} {desc}"

    # Stage 1: hard excludes
    if any(kw in name for kw in EXCLUDE_NAME_KEYWORDS):
        return False
    if any(tag in EXCLUDE_TAGS for tag in tags):
        return False

    # Stage 2: must have at least one coffee signal
    return any(kw in combined for kw in COFFEE_CONFIRM_KEYWORDS)


# ── Main normalizer ───────────────────────────────────────────────────────────

def normalize(product: dict) -> dict:
    name        = product.get("name", "").strip()
    description = product.get("description", "").strip()
    tags        = product.get("tags", [])
    variants    = product.get("price_variants", [])
    full_text   = f"{name} {description}"

    flavor_notes  = extract_flavor_notes(tags, description)
    roast_level   = extract_roast_level(full_text, tags)
    process       = extract_process(full_text, tags)
    origin        = extract_origin(full_text, tags)
    brew_methods  = extract_brew_methods(full_text, tags, variants)
    acidity       = extract_acidity(full_text, tags)
    body          = extract_body(full_text)
    clean_variants = extract_weight_variants(variants)

    # availability — True if at least one variant is available
    is_available = any(v.get("available", False) for v in variants)

    return {
        # identity
        "name":           name,
        "roaster":        product.get("roaster", ""),
        "handle":         product.get("handle", ""),
        "source_url":     product.get("source_url", ""),
        "affiliate_url":  product.get("affiliate_url", ""),
        "image_url":      product.get("image_url", ""),

        # coffee attributes
        "description":    description,
        "flavor_notes":   flavor_notes,
        "roast_level":    roast_level,
        "process":        process,
        "origin":         origin,
        "brew_methods":   brew_methods,
        "acidity":        acidity,
        "body":           body,

        # pricing
        "price_min":      product.get("price_min", 0),
        "price_variants": clean_variants,
        "is_available":   is_available,

        # metadata
        "tags":           tags,
        "scraped_at":     product.get("scraped_at", ""),
    }


# ── Run normalizer ────────────────────────────────────────────────────────────

def run(input_path: str, output_path: str):
    print(f"📂 Loading {input_path}...")
    with open(input_path, encoding="utf-8") as f:
        raw_data = json.load(f)

    print(f"   {len(raw_data)} raw products loaded")

    # Step 1: filter non-coffee products
    coffee_only = [p for p in raw_data if is_coffee_product(p)]
    excluded    = len(raw_data) - len(coffee_only)
    print(f"   {excluded} non-coffee products removed")
    print(f"   {len(coffee_only)} coffee products remaining")

    # Step 2: normalize each product
    normalized = [normalize(p) for p in coffee_only]

    # Step 3: deduplicate by source_url
    seen_urls = set()
    deduped   = []
    for p in normalized:
        if p["source_url"] not in seen_urls:
            seen_urls.add(p["source_url"])
            deduped.append(p)
    dupes = len(normalized) - len(deduped)
    if dupes:
        print(f"   {dupes} duplicates removed")

    # Step 4: save
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    # ── Quality report ────────────────────────────────────────────────────────
    total = len(deduped)
    print(f"\n✅ Saved {total} products to {output_path}")
    print(f"\n📊 Quality Report:")
    print(f"{'─'*45}")

    def pct(n): return f"{n}/{total} ({100*n//total}%)"

    has_flavor   = sum(1 for p in deduped if p["flavor_notes"])
    has_roast    = sum(1 for p in deduped if p["roast_level"] != "unknown")
    has_process  = sum(1 for p in deduped if p["process"] != "unknown")
    has_origin   = sum(1 for p in deduped if p["origin"] != "India")
    has_brew     = sum(1 for p in deduped if p["brew_methods"])
    has_acidity  = sum(1 for p in deduped if p["acidity"] != "unknown")
    available    = sum(1 for p in deduped if p["is_available"])

    print(f"  Flavor notes:      {pct(has_flavor)}")
    print(f"  Roast level known: {pct(has_roast)}")
    print(f"  Process known:     {pct(has_process)}")
    print(f"  Specific origin:   {pct(has_origin)}")
    print(f"  Brew methods:      {pct(has_brew)}")
    print(f"  Acidity known:     {pct(has_acidity)}")
    print(f"  Currently in stock:{pct(available)}")

    print(f"\n  By roaster:")
    roaster_counts = Counter(p["roaster"] for p in deduped)
    for roaster, count in sorted(roaster_counts.items()):
        print(f"    {roaster}: {count}")

    print(f"\n  Roast level breakdown:")
    roast_counts = Counter(p["roast_level"] for p in deduped)
    for roast, count in sorted(roast_counts.items()):
        print(f"    {roast}: {count}")

    print(f"\n  Process breakdown:")
    process_counts = Counter(p["process"] for p in deduped)
    for process, count in sorted(process_counts.items()):
        print(f"    {process}: {count}")


if __name__ == "__main__":
    run(
        input_path="scraped_coffees.json",
        output_path="normalized_coffees.json"
    )