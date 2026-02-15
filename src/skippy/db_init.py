"""Helpers for ensuring the database schema is in place."""
from __future__ import annotations

import logging
from importlib import resources
from pathlib import Path

import psycopg

from skippy.config import settings


logger = logging.getLogger("skippy.db_init")

_SCHEMA_FILE = Path(__file__).resolve().parents[2] / "db" / "init.sql"
_SCHEMA_RESOURCE = resources.files("skippy").joinpath("resources/init.sql")
_schema_sql: str | None = None
_schema_source: str | None = None
_schema_applied = False


async def initialize_schema() -> None:
    """Run the bundled schema file so tables (including ha_entities) exist."""
    global _schema_sql, _schema_source, _schema_applied

    if _schema_applied:
        return

    if _schema_sql is None:
        try:
            _schema_sql = _SCHEMA_FILE.read_text()
            _schema_source = str(_SCHEMA_FILE)
        except FileNotFoundError:  # pragma: no cover - file comes from the repo
            try:
                _schema_sql = _SCHEMA_RESOURCE.read_text()
                _schema_source = str(_SCHEMA_RESOURCE)
            except Exception:  # pragma: no cover - packaged schema missing
                logger.warning(
                    "Schema file not found in %s or packaged resources; skipping initialization",
                    _SCHEMA_FILE.parent,
                )
                _schema_applied = True
                return

    if not _schema_sql.strip():
        logger.warning(
            "Schema file %s is empty; skipping initialization",
            _schema_source or _SCHEMA_FILE,
        )
        _schema_applied = True
        return

    try:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url,
            autocommit=True,
        ) as conn:
            async with conn.cursor() as cur:
                schema_origin = _schema_source or _SCHEMA_FILE
                logger.info("Applying database schema from %s", schema_origin)
                await cur.execute(_schema_sql)
        _schema_applied = True
    except Exception:  # pragma: no cover - relies on postgres availability
        schema_origin = _schema_source or _SCHEMA_FILE
        logger.exception("Failed to initialize database schema from %s", schema_origin)
        raise
