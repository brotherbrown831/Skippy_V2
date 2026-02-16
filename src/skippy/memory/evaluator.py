import json
import logging

from openai import AsyncOpenAI
import psycopg

from skippy.agent.prompts import MEMORY_EVALUATION_PROMPT, PERSON_EXTRACTION_PROMPT
from skippy.config import settings
from skippy.utils.activity_logger import log_activity

logger = logging.getLogger("skippy")


async def evaluate_and_store(
    conversation_history: list[dict],
    user_message: str,
    assistant_message: str,
    conversation_id: str,
    user_id: str = "nolan",
) -> None:
    """Evaluate a conversation exchange for facts worth storing long-term.

    If storable facts are found:
    1. Extract and rewrite each discrete fact
    2. For each fact:
       a. Generate an embedding
       b. Check for duplicate memories (>0.8 cosine similarity)
       c. Either reinforce the existing memory or store a new one
       d. If category is person/family, also extract to people table
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Step 1: Ask LLM if this exchange contains storable information
    evaluation = await _evaluate_exchange(
        client, conversation_history, user_message, assistant_message
    )

    if not evaluation or not evaluation.get("should_store"):
        logger.debug("Memory evaluation: skipped — %s", evaluation.get("reason", "no reason"))
        return

    # NEW: Handle multiple facts
    extracted_facts = evaluation.get("extracted_facts", [])
    if not extracted_facts:
        logger.debug("Memory evaluation: no facts extracted despite should_store=true")
        return

    # Process each fact independently
    for fact_data in extracted_facts:
        extracted_fact = fact_data.get("content", "").strip()
        if not extracted_fact:
            continue

        category = fact_data.get("category", "fact")
        confidence = fact_data.get("confidence", 0.5)

        # Step 2: Generate embedding for this fact
        try:
            embedding_response = await client.embeddings.create(
                model=settings.embedding_model,
                input=extracted_fact,
            )
            embedding = embedding_response.data[0].embedding
        except Exception:
            logger.exception("Failed to generate memory embedding for fact: %s", extracted_fact[:50])
            continue  # Skip this fact, continue with others

        embedding_str = json.dumps(embedding)

        # Step 3: Check for similar existing memories
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Find the most similar existing memory
                await cur.execute(
                    """
                    SELECT * FROM (
                        SELECT
                            memory_id,
                            content,
                            confidence_score,
                            reinforcement_count,
                            1 - (embedding <=> (%s)::vector) AS similarity
                        FROM semantic_memories
                        WHERE user_id = %s
                            AND status = 'active'
                            AND embedding IS NOT NULL
                    ) sub
                    ORDER BY similarity DESC
                    LIMIT 1;
                    """,
                    (embedding_str, user_id),
                )
                row = await cur.fetchone()

                if row:
                    columns = [desc.name for desc in cur.description]
                    similarity = float(row[columns.index("similarity")])
                    existing_id = row[columns.index("memory_id")]

                    # Step 4a: If very similar, reinforce the existing memory
                    if similarity >= settings.memory_dedup_threshold:
                        await cur.execute(
                            """
                            UPDATE semantic_memories
                            SET reinforcement_count = reinforcement_count + 1,
                                confidence_score = LEAST(confidence_score + 0.05, 1.0),
                                updated_at = NOW()
                            WHERE memory_id = %s
                            RETURNING memory_id, content, reinforcement_count;
                            """,
                            (existing_id,),
                        )
                        result = await cur.fetchone()
                        logger.info(
                            "Memory reinforced: id=%s count=%s content='%s'",
                            result[0],
                            result[2],
                            result[1][:50],
                        )
                        await log_activity(
                            activity_type="memory_reinforced",
                            entity_type="memory",
                            entity_id=str(result[0]),
                            description=f"Reinforced memory: {result[1][:50]}...",
                            metadata={"reinforcement_count": result[2], "category": category},
                            user_id=user_id,
                        )
                        continue  # Move to next fact

                # Step 4b: Store as a new memory
                # Try to resolve person_id if this is a person/family memory
                person_id_for_memory = None
                if category in ("person", "family"):
                    try:
                        person_id_for_memory = await _extract_person_id_from_content(extracted_fact, user_id)
                    except Exception:
                        logger.debug("Could not link memory to person: %s", extracted_fact[:50])

                await cur.execute(
                    """
                    INSERT INTO semantic_memories
                        (user_id, content, embedding, confidence_score, status,
                         created_from_conversation_id, category, person_id)
                    VALUES (%s, %s, (%s)::vector, %s, 'active', %s, %s, %s)
                    RETURNING memory_id, content;
                    """,
                    (user_id, extracted_fact, embedding_str, confidence, conversation_id, category, person_id_for_memory),
                )
                result = await cur.fetchone()
                logger.info("New memory stored: id=%s content='%s'", result[0], result[1][:50])
                await log_activity(
                    activity_type="memory_created",
                    entity_type="memory",
                    entity_id=str(result[0]),
                    description=f"Added memory: {result[1][:50]}..." if len(result[1]) > 50 else f"Added memory: {result[1]}",
                    metadata={"category": category, "confidence": confidence},
                    user_id=user_id,
                )

        # Step 5: If person/family category, also upsert into structured people table
        if category in ("person", "family"):
            try:
                await _extract_and_store_person(client, extracted_fact, user_id)
            except Exception:
                logger.exception("Failed to auto-extract person data from fact: %s", extracted_fact[:50])


async def _extract_and_store_person(
    client: AsyncOpenAI,
    extracted_fact: str,
    user_id: str,
) -> None:
    """Extract structured person fields from a fact and upsert into the people table.

    Uses smart identity resolution:
    1. Extract name from LLM
    2. Use _resolve_person_identity() to check for existing person
    3. If match >=85 confidence → update existing, add extracted name as alias
    4. If match 70-84 → log suggestion but create new (conservative)
    5. Otherwise → create new person
    6. After upsert: increment importance_score
    """
    from skippy.tools.people import _resolve_person_identity, _update_person_importance

    try:
        response = await client.responses.create(
            model=settings.llm_model,
            instructions=PERSON_EXTRACTION_PROMPT,
            input=extracted_fact,
            temperature=0.1,
        )
        data = json.loads(response.output_text)
    except Exception:
        logger.exception("Failed to extract person fields from fact")
        return

    name = data.get("name", "").strip()
    if not name:
        logger.debug("Person extraction: no name found in fact")
        return

    # Build fields dict
    fields = {
        "relationship": data.get("relationship", ""),
        "birthday": data.get("birthday", ""),
        "address": data.get("address", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "notes": data.get("notes", ""),
    }

    try:
        # Step 1: Check for existing person
        person_id = None
        extracted_name_as_alias = False

        try:
            identity = await _resolve_person_identity(name, user_id)

            if identity["suggestion"]:
                # 70-84 confidence - log as suggestion but create new (conservative)
                logger.debug(
                    "Person extraction suggestion: '%s' (~= '%s' at %.0f%%)",
                    name, identity["canonical_name"], identity["confidence"]
                )
                # Fall through to create new
            else:
                # >=85 confidence or exact match - use existing
                person_id = identity["person_id"]
                extracted_name_as_alias = True
                logger.debug(
                    "Person extraction: matched '%s' to existing '%s' (%.0f%%)",
                    name, identity["canonical_name"], identity["confidence"]
                )

        except ValueError:
            # No match found - will create new
            pass

        # Step 2: Upsert person
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                if person_id:
                    # Update existing
                    updates = []
                    params = []

                    # Add extracted name as alias if it differs from canonical
                    if extracted_name_as_alias:
                        await cur.execute(
                            "SELECT canonical_name, aliases FROM people WHERE person_id = %s",
                            (person_id,)
                        )
                        row = await cur.fetchone()
                        if row:
                            canonical, aliases = row
                            if name != canonical and name not in (aliases or []):
                                aliases_list = list(aliases or [])
                                aliases_list.append(name)
                                updates.append("aliases = %s")
                                params.append(json.dumps(aliases_list))

                    # Add provided fields if non-empty
                    for field, val in fields.items():
                        if val:
                            updates.append(f"{field} = %s")
                            params.append(val)

                    if updates:
                        updates.append("updated_at = NOW()")
                        params.append(person_id)

                        await cur.execute(
                            f"""
                            UPDATE people
                            SET {", ".join(updates)}
                            WHERE person_id = %s
                            RETURNING person_id, canonical_name
                            """,
                            params,
                        )
                        row = await cur.fetchone()
                        if row:
                            logger.info(
                                "Auto-extracted: updated person id=%s name='%s'",
                                row[0], row[1]
                            )
                            await log_activity(
                                activity_type="person_updated",
                                entity_type="person",
                                entity_id=str(row[0]),
                                description=f"Updated person: {row[1]}",
                                metadata={"source": "auto_extraction"},
                                user_id=user_id,
                            )

                else:
                    # Create new person
                    await cur.execute(
                        """
                        INSERT INTO people (
                            user_id, name, canonical_name, relationship, birthday,
                            address, phone, email, notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING person_id, canonical_name;
                        """,
                        (
                            user_id, name, name,
                            fields["relationship"] or None,
                            fields["birthday"] or None,
                            fields["address"] or None,
                            fields["phone"] or None,
                            fields["email"] or None,
                            fields["notes"] or None,
                        ),
                    )
                    row = await cur.fetchone()
                    if row:
                        person_id = row[0]
                        logger.info(
                            "Auto-extracted: created person id=%s name='%s'",
                            row[0], row[1]
                        )
                        await log_activity(
                            activity_type="person_created",
                            entity_type="person",
                            entity_id=str(row[0]),
                            description=f"Added person: {row[1]}",
                            metadata={"source": "auto_extraction", "relationship": fields.get("relationship")},
                            user_id=user_id,
                        )

        # Step 4: Link any existing unlinked memories about this person
        if person_id:
            try:
                await _link_existing_memories_to_person(person_id, data.get("name", ""), user_id)
            except Exception:
                logger.exception("Failed to link existing memories to person %d", person_id)

    except Exception:
        logger.exception("Failed to upsert auto-extracted person")


async def _extract_person_id_from_content(content: str, user_id: str) -> int | None:
    """Extract person name from memory content and resolve to person_id.

    Uses regex patterns to extract name, then fuzzy matching to find person.
    Only returns person_id if high confidence (>=85%).

    Args:
        content: Memory content (e.g., "Summer enjoys crafting.")
        user_id: User ID

    Returns:
        person_id if high-confidence match found, None otherwise
    """
    import re
    from skippy.tools.people import _resolve_person_identity

    # Heuristic: Extract first capitalized name before common verbs/patterns
    # Matches: "Summer enjoys..." → "Summer"
    #          "Harper's birthday..." → "Harper"
    #          "Jenny Spaldin is..." → "Jenny Spaldin"
    patterns = [
        r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:is|has|lives|works|goes|likes|dislikes|enjoys|prefers)',
        r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\'s\s+',  # Possessive form
        r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:born|married|knows|met)',
    ]

    extracted_name = None
    for pattern in patterns:
        match = re.match(pattern, content)
        if match:
            extracted_name = match.group(1)
            break

    if not extracted_name:
        return None

    # Try to resolve to existing person
    try:
        identity = await _resolve_person_identity(extracted_name, user_id, threshold=85)
        if not identity["suggestion"]:  # Only use high-confidence matches
            logger.debug(
                "Linked memory to person: '%s' → %s (%.0f%%)",
                extracted_name, identity["canonical_name"], identity["confidence"]
            )
            return identity["person_id"]
    except ValueError:
        # No match found
        pass

    return None


async def _link_existing_memories_to_person(
    person_id: int,
    canonical_name: str,
    user_id: str,
) -> int:
    """Link existing unlinked person/family memories to this person.

    Searches for memories that mention this person's name (or aliases)
    and links them via person_id.

    Returns:
        Number of memories linked
    """
    async with await psycopg.AsyncConnection.connect(
        settings.database_url, autocommit=True
    ) as conn:
        async with conn.cursor() as cur:
            # Get person's aliases
            await cur.execute(
                "SELECT canonical_name, aliases FROM people WHERE person_id = %s",
                (person_id,)
            )
            row = await cur.fetchone()
            if not row:
                return 0

            canonical, aliases = row
            search_names = [canonical]
            if aliases:
                search_names.extend(aliases)

            # Find unlinked memories that mention this person
            # Build LIKE conditions for each name variant
            conditions = []
            params = [person_id, user_id]
            for name in search_names:
                conditions.append("(content ILIKE %s OR content ILIKE %s)")
                params.extend([f"{name} %", f"{name}'s %"])

            where_clause = " OR ".join(conditions)

            await cur.execute(
                f"""
                UPDATE semantic_memories
                SET person_id = %s
                WHERE user_id = %s
                  AND category IN ('person', 'family')
                  AND person_id IS NULL
                  AND status = 'active'
                  AND ({where_clause})
                RETURNING memory_id
                """,
                params
            )

            linked_ids = await cur.fetchall()
            count = len(linked_ids)

            if count > 0:
                logger.info("Linked %d existing memories to person %d (%s)", count, person_id, canonical)

            return count


async def _evaluate_exchange(
    client: AsyncOpenAI,
    conversation_history: list[dict],
    user_message: str,
    assistant_message: str,
) -> dict | None:
    """Ask the LLM to evaluate if an exchange contains storable facts."""
    # Build input as conversation array for Responses API
    input_messages = []

    # Add conversation history for context
    for msg in conversation_history:
        input_messages.append({"role": msg["role"], "content": msg["content"]})

    # Add the current exchange
    input_messages.append({
        "role": "user",
        "content": f"User: {user_message}\nAssistant: {assistant_message}",
    })

    try:
        response = await client.responses.create(
            model=settings.llm_model,
            instructions=MEMORY_EVALUATION_PROMPT,
            input=input_messages,
            temperature=0.1,
        )
        content = response.output_text
        return json.loads(content)
    except Exception:
        logger.exception("Failed to evaluate memory")
        return None
