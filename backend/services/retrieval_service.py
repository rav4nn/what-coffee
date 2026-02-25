import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.coffee import Coffee, init_db

def search_coffees(
    roast_level: str = None,
    brew_method: str = None,
    flavor_keywords: list = None,
    process: str = None,
    max_price: float = None,
    limit: int = 5
) -> list[dict]:
    """
    Query the database for coffees matching user preferences.
    Returns a list of coffee dicts ready to inject into the LLM prompt.
    """
    init_db()
    query = Coffee.select().where(Coffee.is_available == True)

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

    results = list(query.limit(limit))

    # if filters are too strict and return nothing, fall back to no filters
    if not results:
        query = Coffee.select().where(Coffee.is_available == True).limit(limit)
        results = list(query)

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