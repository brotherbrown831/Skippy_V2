import json
import logging

from openai import AsyncOpenAI
import psycopg

from skippy.agent.prompts import MEMORY_EVALUATION_PROMPT, PERSON_EXTRACTION_PROMPT
from skippy.config import settings

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
                        continue  # Move to next fact

                # Step 4b: Store as a new memory
                await cur.execute(
                    """
                    INSERT INTO semantic_memories
                        (user_id, content, embedding, confidence_score, status,
                         created_from_conversation_id, category)
                    VALUES (%s, %s, (%s)::vector, %s, 'active', %s, %s)
                    RETURNING memory_id, content;
                    """,
                    (user_id, extracted_fact, embedding_str, confidence, conversation_id, category),
                )
                result = await cur.fetchone()
                logger.info("New memory stored: id=%s content='%s'", result[0], result[1][:50])

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
    """Extract structured person fields from a fact and upsert into the people table."""
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

    # Build upsert — only update non-empty fields
    fields = {
        "relationship": data.get("relationship", ""),
        "birthday": data.get("birthday", ""),
        "address": data.get("address", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "notes": data.get("notes", ""),
    }

    updates = []
    for field, val in fields.items():
        if val:
            updates.append(f"{field} = EXCLUDED.{field}")
    updates.append("updated_at = NOW()")
    set_clause = ", ".join(updates)

    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    INSERT INTO people (user_id, name, relationship, birthday, address, phone, email, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, LOWER(name))
                    DO UPDATE SET {set_clause}
                    RETURNING person_id, name;
                    """,
                    (
                        user_id, name,
                        fields["relationship"] or None,
                        fields["birthday"] or None,
                        fields["address"] or None,
                        fields["phone"] or None,
                        fields["email"] or None,
                        fields["notes"] or None,
                    ),
                )
                row = await cur.fetchone()
                logger.info("Auto-extracted person: id=%s name='%s'", row[0], row[1])
    except Exception:
        logger.exception("Failed to upsert auto-extracted person")


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
