import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.coffee import Coffee, init_db
from peewee import fn


def get_all_coffees_minified() -> str:
    """
    Load all available coffees and return as a pipe-delimited string for
    injection into the Claude system prompt as a cached block.
    Format: roaster|name|roast|process|origin|flavors|brew_methods|price_inr|url
    """
    init_db()
    coffees = list(
        Coffee.select()
        .where(Coffee.is_available == True)
        .order_by(Coffee.roaster, Coffee.name)
    )
    lines = ["roaster|name|roast|process|origin|flavors|brew_methods|price_inr|url"]
    for c in coffees:
        lines.append("|".join([
            (c.roaster      or "").replace("|", "/"),
            (c.name         or "").replace("|", "/"),
            c.roast_level   or "",
            c.process       or "",
            c.origin        or "",
            (c.flavor_notes or "").replace("|", "/"),
            (c.brew_methods or "").replace("|", "/"),
            str(int(c.price_min)) if c.price_min else "0",
            c.source_url    or "",
        ]))
    return "\n".join(lines)

def search_coffees(
    roast_level: str = None,
    brew_method: str = None,
    flavor_keywords: list = None,
    process: str = None,
    max_price: float = None,
    roaster: str = None,
    limit: int = 5
) -> list[dict]:
    """
    Query the database for coffees matching user preferences.
    Returns a list of coffee dicts ready to inject into the LLM prompt.
    """
    init_db()

    has_filters = any([
        roast_level and roast_level != "unknown",
        brew_method,
        flavor_keywords,
        process and process != "unknown",
        max_price,
        roaster,
    ])

    query = (Coffee.select()
             .where(Coffee.is_available == True)
             .where(Coffee.flavor_notes.is_null(False))
             .where(Coffee.flavor_notes != ""))

    if roaster:
        query = query.where(Coffee.roaster == roaster)

    if roast_level and roast_level != "unknown":
        query = query.where(Coffee.roast_level == roast_level)

    if brew_method:
        query = query.where(Coffee.brew_methods.contains(brew_method))

    if process and process != "unknown":
        query = query.where(Coffee.process == process)

    if max_price:
        query = query.where(Coffee.price_min <= max_price)

    if flavor_keywords:
        for keyword in flavor_keywords:
            query = query.where(
                Coffee.flavor_notes.contains(keyword) |
                Coffee.description.contains(keyword)
            )

    # Always randomise so results are diverse across roasters
    results = list(query.order_by(fn.RANDOM()).limit(limit))

    # If filters were too strict and returned nothing, fall back to random sample
    if not results and has_filters:
        results = list(
            Coffee.select()
            .where(Coffee.is_available == True)
            .where(Coffee.flavor_notes.is_null(False))
            .where(Coffee.flavor_notes != "")
            .order_by(fn.RANDOM())
            .limit(limit)
        )

    return [coffee_to_dict(c) for c in results]


def coffee_to_dict(c: Coffee) -> dict:
    return {
        "name":          c.name,
        "roaster":       c.roaster,
        "roast_level":   c.roast_level,
        "process":       c.process,
        "origin":        c.origin,
        "flavor_notes":  c.flavor_notes,
        "brew_methods":  c.brew_methods,
        "description":   c.description[:300],
        "price_min":     c.price_min,
        "source_url":    c.source_url,
        "affiliate_url": c.affiliate_url if c.affiliate_url else c.source_url,
    }