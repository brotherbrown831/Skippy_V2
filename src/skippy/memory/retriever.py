import json
import logging

from openai import AsyncOpenAI
import psycopg

from skippy.config import settings

logger = logging.getLogger("skippy")


async def retrieve_memories(
    query: str,
    user_id: str = "nolan",
    limit: int = 5,
    threshold: float = 0.3,
) -> list[dict]:
    """Retrieve semantically similar memories from pgvector.

    Generates an embedding for the query, then performs cosine similarity
    search against stored memories.
    """
    # Generate embedding for the query
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        embedding_response = await client.embeddings.create(
            model=settings.embedding_model,
            input=query,
        )
        embedding = embedding_response.data[0].embedding
    except Exception:
        logger.exception("Failed to generate query embedding")
        return []

    embedding_str = json.dumps(embedding)

    # Search for similar memories
    sql = """
        SELECT * FROM (
            SELECT
                memory_id,
                content,
                category,
                confidence_score,
                1 - (embedding <=> ($1)::vector) AS similarity
            FROM semantic_memories
            WHERE user_id = $2
                AND status = 'active'
                AND embedding IS NOT NULL
        ) sub
        WHERE similarity > $3
        ORDER BY similarity DESC
        LIMIT $4;
    """

    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (embedding_str, user_id, threshold, limit))
                rows = await cur.fetchall()
                columns = [desc.name for desc in cur.description]

                return [
                    {
                        "memory_id": row[columns.index("memory_id")],
                        "content": row[columns.index("content")],
                        "category": row[columns.index("category")],
                        "confidence": row[columns.index("confidence_score")],
                        "similarity": float(row[columns.index("similarity")]),
                    }
                    for row in rows
                ]
    except Exception:
        logger.exception("Failed to search memories")
        return []
