-- Core coffee table
CREATE TABLE coffees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    roaster TEXT,
    origin TEXT,              -- Ethiopia, Colombia, etc.
    process TEXT,             -- Washed, Natural, Honey
    roast_level TEXT,         -- Light, Medium, Dark
    flavor_notes TEXT[],      -- ["chocolate", "berry", "citrus"]
    brew_methods TEXT[],      -- ["espresso", "pour over", "french press"]
    description TEXT,
    price DECIMAL,
    affiliate_url TEXT,       -- your monetization link
    source_url TEXT,          -- where scraped from
    is_curated BOOLEAN DEFAULT false,   -- your own picks
    embedding VECTOR(1536),   -- for semantic search (pgvector)
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

-- Conversation sessions
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT UNIQUE NOT NULL,
    messages JSONB DEFAULT '[]',  -- full chat history
    user_profile JSONB DEFAULT '{}',  -- extracted preferences
    created_at TIMESTAMP DEFAULT now()
);