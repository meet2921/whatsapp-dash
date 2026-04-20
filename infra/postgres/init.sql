-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- fuzzy text search (keyword matching)
CREATE EXTENSION IF NOT EXISTS "btree_gin";  -- composite GIN indexes
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid(), encrypt()