from peewee import *
import os

# Database file will be created at backend/coffees.db
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db = SqliteDatabase(os.path.join(BASE_DIR, "coffees.db"))

class BaseModel(Model):
    class Meta:
        database = db

class Coffee(BaseModel):
    # Identity
    name          = CharField()
    roaster       = CharField()
    handle        = CharField()
    source_url    = CharField(unique=True)
    affiliate_url = CharField(default="")
    image_url     = CharField(default="")

    # Coffee attributes
    description   = TextField(default="")
    roast_level   = CharField(default="unknown")
    process       = CharField(default="unknown")
    origin        = CharField(default="India")
    acidity       = CharField(default="unknown")
    body          = CharField(default="unknown")

    # Stored as comma-separated strings (easy for SQLite)
    flavor_notes  = CharField(default="")   # "Chocolate, Caramel, Citrus"
    brew_methods  = CharField(default="")   # "Espresso, Pour Over"
    tags          = CharField(default="")

    # Pricing
    price_min     = FloatField(default=0)
    is_available  = BooleanField(default=True)

    # Metadata
    scraped_at    = CharField(default="")

    class Meta:
        table_name = "coffees"

def init_db():
    """Create the database and tables if they don't exist."""
    db.connect(reuse_if_open=True)
    db.create_tables([Coffee], safe=True)
    print("✅ Database ready")