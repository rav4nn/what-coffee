import httpx
import json
import time
import re
from datetime import datetime

# ── List of all your Shopify stores ──────────────────────────────────────────
STORES = [
    {"name": "Blue Tokai",          "url": "https://bluetokaicoffee.com"},
    {"name": "Corridor Seven",      "url": "https://corridorseven.coffee"},
    {"name": "Black Baza",          "url": "https://blackbazacoffee.com"},
    {"name": "Subko",               "url": "https://subko.coffee"},
    {"name": "Third Wave Coffee",   "url": "https://thirdwavecoffeeroasters.com"},
    {"name": "Toffee Coffee",       "url": "https://toffeecoffeeroasters.com"},
    {"name": "Maverick & Farmer",   "url": "https://maverickandfarmer.com"},
    {"name": "Grey Soul",           "url": "https://greysoul.coffee"},
    {"name": "Half Light",          "url": "https://halflightcoffee.com"},
    {"name": "Fraction 9",          "url": "https://fraction9coffee.com"},
    {"name": "Bili Hu",             "url": "https://bilihu.in"},
    {"name": "Araku",               "url": "https://arakucoffee.in"},
    {"name": "Kapi Kottai",         "url": "https://kapikottai.coffee"},
    {"name": "KC Roasters",         "url": "https://kcroasters.com"},
    {"name": "Savour Works",        "url": "https://savourworksroasters.com"},
    {"name": "Tulum",               "url": "https://tulum.coffee"},
    {"name": "Ground Zero",         "url": "https://groundzerocoffee.in"},
    {"name": "Hunkal Estate",       "url": "https://hunkalestatecoffee.com"},
]

# ── Keywords to filter only coffee products (excludes equipment, merch etc) ──
COFFEE_KEYWORDS = [
    "coffee", "espresso", "filter", "blend", "single origin",
    "natural", "washed", "honey", "roast", "estate", "arabica",
    "robusta", "pour over", "cold brew"
]

# ── Roast level detection ─────────────────────────────────────────────────────
ROAST_KEYWORDS = {
    "light":  ["light", "light roast", "filter roast"],
    "medium": ["medium", "medium roast", "omni roast"],
    "dark":   ["dark", "dark roast", "espresso roast", "french roast"]
}

def is_coffee_product(product: dict) -> bool:
    """Filter out non-coffee products like equipment, merch, subscriptions."""
    text = (
        product.get("title", "") + " " +
        product.get("product_type", "") + " " +
        " ".join(product.get("tags", []))
    ).lower()
    return any(keyword in text for keyword in COFFEE_KEYWORDS)

def extract_roast_level(text: str) -> str:
    """Detect roast level from product text."""
    text = text.lower()
    for level, keywords in ROAST_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return level
    return "unknown"

def extract_flavor_notes(tags: list, description: str) -> list:
    """Pull flavor notes from tags or description."""
    flavor_tags = [
        tag.replace("flavor:", "").replace("taste:", "").replace("notes:", "").strip()
        for tag in tags
        if any(prefix in tag.lower() for prefix in ["flavor", "taste", "notes", "tasting"])
    ]
    if flavor_tags:
        return flavor_tags

    # fallback: look for "tasting notes" or "tastes like" in description
    patterns = [
        r"tasting notes[:\s]+([^.|\n]+)",
        r"tastes like[:\s]+([^.|\n]+)",
        r"notes of[:\s]+([^.|\n]+)",
        r"flavou?rs?[:\s]+([^.|\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, description.lower())
        if match:
            raw = match.group(1)
            notes = [n.strip().title() for n in re.split(r",|and|&", raw) if n.strip()]
            return notes[:6]  # cap at 6 notes

    return []

def extract_brew_methods(tags: list, description: str) -> list:
    """Detect brew methods from tags or description."""
    brew_methods = [
        "espresso", "pour over", "french press", "aeropress",
        "moka pot", "cold brew", "drip", "filter", "chemex",
        "siphon", "v60", "clever dripper"
    ]
    text = (" ".join(tags) + " " + description).lower()
    return [method.title() for method in brew_methods if method in text]

def normalize_product(product: dict, store_name: str, store_url: str) -> dict:
    """Convert raw Shopify product JSON into our standard coffee schema."""
    title       = product.get("title", "")
    description = product.get("body_html", "") or ""
    tags        = product.get("tags", [])
    variants    = product.get("variants", [])
    images      = product.get("images", [])
    handle      = product.get("handle", "")

    # clean HTML from description
    clean_desc = re.sub(r"<[^>]+>", " ", description).strip()
    clean_desc = re.sub(r"\s+", " ", clean_desc)

    # get all price variants
    prices = [
        {
            "weight": v.get("title", ""),
            "price":  float(v.get("price", 0)),
            "available": v.get("available", True)
        }
        for v in variants if v.get("price")
    ]
    min_price = min((p["price"] for p in prices), default=0)

    full_text = f"{title} {' '.join(tags)} {clean_desc}"

    return {
        "name":          title,
        "roaster":       store_name,
        "source_url":    f"{store_url}/products/{handle}",
        "affiliate_url": "",           # you'll fill this in later
        "description":   clean_desc[:1000],
        "flavor_notes":  extract_flavor_notes(tags, clean_desc),
        "roast_level":   extract_roast_level(full_text),
        "brew_methods":  extract_brew_methods(tags, clean_desc),
        "tags":          tags,
        "price_min":     min_price,
        "price_variants": prices,
        "image_url":     images[0]["src"] if images else "",
        "handle":        handle,
        "scraped_at":    datetime.utcnow().isoformat(),
    }

def scrape_store(store: dict) -> list:
    """Scrape all coffee products from a single Shopify store."""
    base_url   = store["url"].rstrip("/")
    store_name = store["name"]
    all_products = []
    page = 1

    print(f"\n{'='*50}")
    print(f"Scraping: {store_name} ({base_url})")
    print(f"{'='*50}")

    while True:
        url = f"{base_url}/products.json?limit=250&page={page}"
        try:
            response = httpx.get(url, timeout=15, follow_redirects=True)
            if response.status_code != 200:
                print(f"  ✗ Got status {response.status_code}, stopping.")
                break

            data     = response.json()
            products = data.get("products", [])

            if not products:
                print(f"  ✓ No more products at page {page}.")
                break

            print(f"  → Page {page}: {len(products)} products found")

            for product in products:
                if is_coffee_product(product):
                    normalized = normalize_product(product, store_name, base_url)
                    all_products.append(normalized)
                    print(f"    ✓ {normalized['name']} — ₹{normalized['price_min']}")

            if len(products) < 250:
                break  # last page

            page += 1
            time.sleep(1)  # be polite, don't hammer the server

        except Exception as e:
            print(f"  ✗ Error scraping {store_name}: {e}")
            break

    print(f"  → Total coffee products: {len(all_products)}")
    return all_products


def scrape_all_stores() -> list:
    """Scrape all stores and return combined results."""
    all_coffees = []

    for store in STORES:
        coffees = scrape_store(store)
        all_coffees.extend(coffees)
        time.sleep(2)  # pause between stores

    return all_coffees


def save_to_json(coffees: list, filepath: str = "scraped_coffees.json"):
    """Save results to a JSON file."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(coffees, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Saved {len(coffees)} coffees to {filepath}")


if __name__ == "__main__":
    print("☕ Starting What Coffee scraper...")
    print(f"   Scraping {len(STORES)} stores\n")

    coffees = scrape_all_stores()
    save_to_json(coffees)

    print(f"\n📊 Summary:")
    print(f"   Total coffees scraped: {len(coffees)}")

    # breakdown by roaster
    from collections import Counter
    counts = Counter(c["roaster"] for c in coffees)
    for roaster, count in sorted(counts.items()):
        print(f"   {roaster}: {count} products")