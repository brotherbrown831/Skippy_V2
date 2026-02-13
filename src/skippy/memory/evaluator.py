import json
import logging

from openai import AsyncOpenAI
import psycopg

from skippy.agent.prompts import MEMORY_EVALUATION_PROMPT
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

    If a storable fact is found:
    1. Extract and rewrite the fact
    2. Generate an embedding
    3. Check for duplicate memories (>0.8 cosine similarity)
    4. Either reinforce the existing memory or store a new one
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Step 1: Ask LLM if this exchange contains storable information
    evaluation = await _evaluate_exchange(
        client, conversation_history, user_message, assistant_message
    )

    if not evaluation or not evaluation.get("should_store"):
        logger.debug("Memory evaluation: skipped — %s", evaluation.get("reason", "no reason"))
        return

    extracted_fact = evaluation.get("extracted_fact")
    if not extracted_fact:
        return

    category = evaluation.get("category", "fact")
    confidence = evaluation.get("confidence", 0.5)

    # Step 2: Generate embedding for the extracted fact
    try:
        embedding_response = await client.embeddings.create(
            model=settings.embedding_model,
            input=extracted_fact,
        )
        embedding = embedding_response.data[0].embedding
    except Exception:
        logger.exception("Failed to generate memory embedding")
        return

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
                        1 - (embedding <=> ($1)::vector) AS similarity
                    FROM semantic_memories
                    WHERE user_id = $2
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
                        WHERE memory_id = $1
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
                    return

            # Step 4b: Store as a new memory
            await cur.execute(
                """
                INSERT INTO semantic_memories
                    (user_id, content, embedding, confidence_score, status,
                     created_from_conversation_id, category)
                VALUES ($1, $2, ($3)::vector, $4, 'active', $5, $6)
                RETURNING memory_id, content;
                """,
                (user_id, extracted_fact, embedding_str, confidence, conversation_id, category),
            )
            result = await cur.fetchone()
            logger.info("New memory stored: id=%s content='%s'", result[0], result[1][:50])


async def _evaluate_exchange(
    client: AsyncOpenAI,
    conversation_history: list[dict],
    user_message: str,
    assistant_message: str,
) -> dict | None:
    """Ask the LLM to evaluate if an exchange contains storable facts."""
    messages = [
        {"role": "system", "content": MEMORY_EVALUATION_PROMPT},
    ]

    # Add conversation history for context
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add the current exchange
    messages.append({
        "role": "user",
        "content": f"User: {user_message}\nAssistant: {assistant_message}",
    })

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception:
        logger.exception("Failed to evaluate memory")
        return None
