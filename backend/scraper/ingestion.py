"""
ingestion.py

Loads enriched_coffees.json into the SQLite database.

Run:
    python scraper/ingestion.py
"""

import json
import sys
import os

# make sure Python can find the models folder
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.coffee import Coffee, init_db

INPUT_FILE = "enriched_coffees.json"

def load():
    print(f"📂 Loading {INPUT_FILE}...")
    with open(INPUT_FILE, encoding="utf-8") as f:
        products = json.load(f)
    print(f"   {len(products)} products found")

    # Set up the database
    init_db()

    inserted = 0
    updated  = 0
    skipped  = 0

    for p in products:
        # Convert lists to comma-separated strings for SQLite storage
        flavor_notes = ", ".join(p.get("flavor_notes") or [])
        brew_methods = ", ".join(p.get("brew_methods") or [])
        tags         = ", ".join(p.get("tags") or [])

        data = {
            "name":          p.get("name", ""),
            "roaster":       p.get("roaster", ""),
            "handle":        p.get("handle", ""),
            "source_url":    p.get("source_url", ""),
            "affiliate_url": p.get("affiliate_url", ""),
            "image_url":     p.get("image_url", ""),
            "description":   p.get("description", ""),
            "roast_level":   p.get("roast_level", "unknown"),
            "process":       p.get("process", "unknown"),
            "origin":        p.get("origin", "India"),
            "acidity":       p.get("acidity", "unknown"),
            "body":          p.get("body", "unknown"),
            "flavor_notes":  flavor_notes,
            "brew_methods":  brew_methods,
            "tags":          tags,
            "price_min":     p.get("price_min", 0),
            "is_available":  p.get("is_available", True),
            "scraped_at":    p.get("scraped_at", ""),
        }

        # Upsert — insert new, update existing (matched by source_url)
        try:
            coffee = Coffee.get(Coffee.source_url == data["source_url"])
            # update existing record
            for key, value in data.items():
                setattr(coffee, key, value)
            coffee.save()
            updated += 1
        except Coffee.DoesNotExist:
            Coffee.create(**data)
            inserted += 1
        except Exception as e:
            print(f"   ✗ Error on {p.get('name')}: {e}")
            skipped += 1

    print(f"\n✅ Ingestion complete")
    print(f"   Inserted: {inserted}")
    print(f"   Updated:  {updated}")
    print(f"   Errors:   {skipped}")
    print(f"   Total in DB: {Coffee.select().count()}")

    # Quick breakdown
    print(f"\n📊 Database summary:")
    from collections import Counter
    all_coffees = list(Coffee.select())
    roasters = Counter(c.roaster for c in all_coffees)
    for roaster, count in sorted(roasters.items()):
        print(f"   {roaster}: {count}")

if __name__ == "__main__":
    load()