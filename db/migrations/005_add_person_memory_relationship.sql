-- Migration: Add Foreign Key Relationship Between People and Memories
-- Date: 2026-02-16
-- Purpose: Link semantic_memories to people table for structured relationship queries

-- Step 1: Add person_id column to semantic_memories (nullable - not all memories relate to people)
ALTER TABLE semantic_memories
ADD COLUMN IF NOT EXISTS person_id INT;

-- Step 2: Add foreign key constraint with SET NULL on delete (if person deleted, memory remains but person_id = NULL)
ALTER TABLE semantic_memories
ADD CONSTRAINT fk_memory_person
FOREIGN KEY (person_id) REFERENCES people(person_id)
ON DELETE SET NULL;

-- Step 3: Create index for query performance (filtering memories by person)
CREATE INDEX IF NOT EXISTS idx_memories_person_id
ON semantic_memories (person_id)
WHERE person_id IS NOT NULL;

-- Step 4: Create composite index for common query patterns (user + person + category)
CREATE INDEX IF NOT EXISTS idx_memories_user_person_category
ON semantic_memories (user_id, person_id, category)
WHERE person_id IS NOT NULL AND status = 'active';

-- Step 5: Link existing memories to people using conservative exact-match approach
-- Only link if memory content starts with person's canonical name or known aliases
DO $$
DECLARE
    person_record RECORD;
    canonical_name TEXT;
    aliases TEXT[];
    name_pattern TEXT;
    alias_name TEXT;
    count_linked INT := 0;
BEGIN
    -- Loop through all people and link matching memories
    FOR person_record IN
        SELECT person_id, canonical_name, aliases
        FROM people
        WHERE user_id = 'nolan'
    LOOP
        canonical_name := person_record.canonical_name;
        aliases := COALESCE(person_record.aliases, ARRAY[]::TEXT[]);

        -- Link memories starting with canonical name
        UPDATE semantic_memories
        SET person_id = person_record.person_id
        WHERE person_id IS NULL
          AND category IN ('person', 'family')
          AND status = 'active'
          AND (
            content ILIKE canonical_name || ' %' OR
            content ILIKE canonical_name || '''s %'
          );

        count_linked := count_linked + FOUND::INT * (FOUND::INT);  -- Rough count

        -- Link memories starting with each alias
        FOREACH alias_name IN ARRAY aliases
        LOOP
            UPDATE semantic_memories
            SET person_id = person_record.person_id
            WHERE person_id IS NULL
              AND category IN ('person', 'family')
              AND status = 'active'
              AND (
                content ILIKE alias_name || ' %' OR
                content ILIKE alias_name || '''s %'
              );
        END LOOP;
    END LOOP;

    RAISE NOTICE 'Migration complete: Linked person/family memories to people table';
END $$;

-- Step 6: Add helpful comment
COMMENT ON COLUMN semantic_memories.person_id IS 'Foreign key to people table - links memory to a specific person. Nullable - not all memories are about people.';
