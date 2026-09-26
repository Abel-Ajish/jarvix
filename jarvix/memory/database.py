"""SQLite database implementation for ConversationStore and MemoryStore.

Uses aiosqlite against SQLite at %APPDATA%/jarvix/memory.db
Implements the FROZEN interfaces from jarvix.core.store
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import aiosqlite

from jarvix.core.store import ConversationStore, MemoryStore, Message, Fact, SCHEMA_SQL


# Database path: %APPDATA%/jarvix/memory.db
_APP_DATA = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
_DB_DIR = _APP_DATA / "jarvix"
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DB_DIR / "memory.db"


def _safe_json_loads(s: Optional[str]) -> Any:
    """Parse JSON safely, returning None on decode errors."""
    if not s:
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None


def _row_to_message(row: aiosqlite.Row) -> Message:
    """Convert a database row to a Message object."""
    return Message(
        id=row["id"],
        conversation_id=row["conversation_id"],
        role=row["role"],
        content=row["content"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        metadata=_safe_json_loads(row["metadata"]),
    )


def _row_to_fact(row: aiosqlite.Row) -> Fact:
    """Convert a database row to a Fact object."""
    return Fact(
        id=row["id"],
        fact=row["fact"],
        source=row["source"],
        confidence=row["confidence"],
        created_at=datetime.fromisoformat(row["created_at"]),
        last_used=datetime.fromisoformat(row["last_used"]) if row["last_used"] else None,
        tags=_safe_json_loads(row["tags"]),
    )


class SQLiteConversationStore(ConversationStore):
    """SQLite implementation of ConversationStore."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or _DB_PATH
        self._initialized = False
        self._init_lock = asyncio.Lock()

    def close(self) -> None:
        """Close any open database connections."""
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Ensure database schema is created."""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:  # double-check after acquiring lock
                return
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                await db.executescript(SCHEMA_SQL)
                await db.commit()
            self._initialized = True

    async def create_conversation(self, title: Optional[str] = None) -> str:
        """Create a new conversation, return its ID."""
        await self._ensure_initialized()
        conv_id = f"conv_{datetime.now().isoformat().replace(':', '-').replace('.', '-')}"
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "INSERT INTO conversations (id, title) VALUES (?, ?)",
                (conv_id, title),
            )
            await db.commit()
        return conv_id

    async def add_message(
        self,
        conv_id: str,
        role: str,
        content: str,
        *,
        metadata: Optional[dict] = None,
    ) -> int:
        """Add a message, return its ID."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                INSERT INTO messages (conversation_id, role, content, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (conv_id, role, content, json.dumps(metadata) if metadata else None),
            )
            await db.execute(
                """
                UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """,
                (conv_id,),
            )
            # Update FTS
            await db.execute(
                """
                INSERT INTO messages_fts (rowid, content, conversation_id)
                VALUES (?, ?, ?)
                """,
                (cursor.lastrowid, content, conv_id),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_history(self, conv_id: str, limit: int = 50) -> List[Message]:
        """Get the last N messages for a conversation."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (conv_id, limit),
            )
            rows = await cursor.fetchall()
            return [_row_to_message(row) for row in reversed(rows)]

    async def search(self, query: str, limit: int = 50) -> List[Message]:
        """Full-text search across all conversations."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT m.* FROM messages m
                JOIN messages_fts f ON m.id = f.rowid
                WHERE messages_fts MATCH ?
                ORDER BY m.timestamp DESC
                LIMIT ?
                """,
                (query, limit),
            )
            rows = await cursor.fetchall()
            return [_row_to_message(row) for row in rows]

    async def delete_conversation(self, conv_id: str) -> None:
        """Delete a conversation and all its messages."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # Delete FTS entries first to prevent staleness
            await db.execute("DELETE FROM messages_fts WHERE conversation_id = ?", (conv_id,))
            # Messages are deleted via CASCADE
            await db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            await db.commit()

    async def list_conversations(self, limit: int = 50) -> List[dict]:
        """List recent conversations with their IDs and titles."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "title": row["title"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]


class SQLiteMemoryStore(MemoryStore):
    """SQLite implementation of MemoryStore."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or _DB_PATH
        self._initialized = False
        self._init_lock = asyncio.Lock()

    def close(self) -> None:
        """Close any open database connections."""
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Ensure database schema is created."""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:  # double-check after acquiring lock
                return
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                await db.executescript(SCHEMA_SQL)
                await db.commit()
            self._initialized = True

    async def add_fact(
        self,
        fact: str,
        *,
        source: str = "user",
        confidence: float = 1.0,
        tags: Optional[List[str]] = None,
    ) -> int:
        """Add a fact, return its ID."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                INSERT INTO memory_facts (fact, source, confidence, tags)
                VALUES (?, ?, ?, ?)
                """,
                (fact, source, confidence, json.dumps(tags) if tags else None),
            )
            # Update FTS
            await db.execute(
                """
                INSERT INTO facts_fts (rowid, fact, source, tags)
                VALUES (?, ?, ?, ?)
                """,
                (cursor.lastrowid, fact, source, json.dumps(tags) if tags else None),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_facts(self, query: Optional[str] = None, limit: int = 50) -> List[Fact]:
        """Get facts, optionally filtered by query."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if query:
                cursor = await db.execute(
                    """
                    SELECT m.* FROM memory_facts m
                    JOIN facts_fts f ON m.id = f.rowid
                    WHERE facts_fts MATCH ?
                    ORDER BY m.created_at DESC
                    LIMIT ?
                    """,
                    (query, limit),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT * FROM memory_facts
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            rows = await cursor.fetchall()
            return [_row_to_fact(row) for row in rows]

    async def update_fact(self, fact_id: int, **kwargs: Any) -> bool:
        """Update a fact's fields (fact, confidence, tags)."""
        await self._ensure_initialized()
        allowed_fields = {"fact", "source", "confidence", "tags"}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return False

        set_clauses = []
        params = []
        for key, value in updates.items():
            if key == "tags":
                set_clauses.append("tags = ?")
                params.append(json.dumps(value) if value else None)
            else:
                set_clauses.append(f"{key} = ?")
                params.append(value)

        params.append(fact_id)

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                UPDATE memory_facts SET {", ".join(set_clauses)}
                WHERE id = ?
                """,
                params,
            )
            # Update FTS if fact content changed
            if "fact" in updates or "source" in updates or "tags" in updates:
                # Get updated row
                row = await db.execute(
                    "SELECT id, fact, source, tags FROM memory_facts WHERE id = ?",
                    (fact_id,),
                )
                row_data = await row.fetchone()
                if row_data:
                    await db.execute(
                        """
                        UPDATE facts_fts SET fact = ?, source = ?, tags = ?
                        WHERE rowid = ?
                        """,
                        (row_data["fact"], row_data["source"], row_data["tags"], fact_id),
                    )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_fact(self, fact_id: int) -> bool:
        """Delete a fact by ID."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # Delete FTS entry first to prevent staleness
            await db.execute("DELETE FROM facts_fts WHERE rowid = ?", (fact_id,))
            cursor = await db.execute("DELETE FROM memory_facts WHERE id = ?", (fact_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def search_facts(self, query: str, limit: int = 50) -> List[Fact]:
        """Full-text search over facts."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT m.*, rank FROM memory_facts m
                JOIN facts_fts f ON m.id = f.rowid
                WHERE facts_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            )
            rows = await cursor.fetchall()
            return [_row_to_fact(row) for row in rows]


# Convenience function to get the default stores
async def get_conversation_store() -> SQLiteConversationStore:
    """Get the default ConversationStore instance."""
    return SQLiteConversationStore()


async def get_memory_store() -> SQLiteMemoryStore:
    """Get the default MemoryStore instance."""
    return SQLiteMemoryStore()