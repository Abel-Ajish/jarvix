"""Full-text search implementation using SQLite FTS5.

Provides ranked search across conversations and facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from jarvix.core.store import Message, Fact, SCHEMA_SQL
from jarvix.memory.database import (
    SQLiteConversationStore,
    SQLiteMemoryStore,
    _DB_PATH,
    _row_to_message,
    _row_to_fact,
)

import aiosqlite
import json


@dataclass
class SearchResult:
    """A search result with relevance score."""
    item: Any  # Message or Fact
    score: float
    type: str  # "message" or "fact"


class SearchEngine:
    """FTS5 full-text search engine with ranking."""

    def __init__(
        self,
        conv_store: Optional[SQLiteConversationStore] = None,
        mem_store: Optional[SQLiteMemoryStore] = None,
    ):
        self._conv_store = conv_store
        self._mem_store = mem_store

    async def search_messages(
        self,
        query: str,
        limit: int = 50,
        min_score: float = 0.0,
    ) -> List[SearchResult]:
        """Search messages using FTS5 with ranking.

        Args:
            query: Search query (supports FTS5 syntax)
            limit: Maximum results
            min_score: Minimum rank score

        Returns:
            List of SearchResult with Message objects ranked by relevance
        """
        # Ensure stores are initialized
        if self._conv_store:
            await self._conv_store._ensure_initialized()

        async with aiosqlite.connect(_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT m.*, bm25(messages_fts) as rank
                FROM messages m
                JOIN messages_fts f ON m.id = f.rowid
                WHERE messages_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            )
            rows = await cursor.fetchall()

            results = []
            for row in rows:
                msg = _row_to_message(row)
                # BM25 returns lower scores for better matches, invert for score
                rank = row["rank"]
                score = 1.0 / (1.0 + rank) if rank is not None else 0.0
                if score >= min_score:
                    results.append(SearchResult(item=msg, score=score, type="message"))
            return results

    async def search_facts(
        self,
        query: str,
        limit: int = 50,
        min_score: float = 0.0,
    ) -> List[SearchResult]:
        """Search facts using FTS5 with ranking.

        Args:
            query: Search query (supports FTS5 syntax)
            limit: Maximum results
            min_score: Minimum rank score

        Returns:
            List of SearchResult with Fact objects ranked by relevance
        """
        if self._mem_store:
            await self._mem_store._ensure_initialized()

        async with aiosqlite.connect(_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT m.*, bm25(facts_fts) as rank
                FROM memory_facts m
                JOIN facts_fts f ON m.id = f.rowid
                WHERE facts_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            )
            rows = await cursor.fetchall()

            results = []
            for row in rows:
                fact = _row_to_fact(row)
                rank = row["rank"]
                score = 1.0 / (1.0 + rank) if rank is not None else 0.0
                if score >= min_score:
                    results.append(SearchResult(item=fact, score=score, type="fact"))
            return results

    async def search_all(
        self,
        query: str,
        limit: int = 50,
        min_score: float = 0.0,
    ) -> List[SearchResult]:
        """Search both messages and facts, merged and ranked.

        Args:
            query: Search query
            limit: Maximum total results
            min_score: Minimum rank score

        Returns:
            Combined list of SearchResult objects sorted by score descending
        """
        # Search both with double limit to allow merging
        msg_results = await self.search_messages(query, limit * 2, min_score)
        fact_results = await self.search_facts(query, limit * 2, min_score)

        # Merge and sort by score
        all_results = msg_results + fact_results
        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results[:limit]


async def get_search_engine() -> SearchEngine:
    """Get a SearchEngine instance with default stores."""
    return SearchEngine()


# Convenience functions
async def search_messages(query: str, limit: int = 50) -> List[SearchResult]:
    """Search messages (convenience function)."""
    engine = await get_search_engine()
    return await engine.search_messages(query, limit)


async def search_facts(query: str, limit: int = 50) -> List[SearchResult]:
    """Search facts (convenience function)."""
    engine = await get_search_engine()
    return await engine.search_facts(query, limit)


async def search_all(query: str, limit: int = 50) -> List[SearchResult]:
    """Search everything (convenience function)."""
    engine = await get_search_engine()
    return await engine.search_all(query, limit)


# ---------------------------------------------------------------------------
# Synchronous convenience functions used by tests
# ---------------------------------------------------------------------------

def search_conversations(
    conversation_store: Any,
    query: str,
    limit: int = 50,
) -> List[SearchResult]:
    """Synchronous search helper for ConversationStore fixtures.

    This is a thin wrapper around the store's own search method,
    returning SearchResult objects for compatibility with the test suite.
    """
    results = conversation_store.search(query, limit=limit)
    output: List[SearchResult] = []
    for msg in results:
        output.append(SearchResult(item=msg, score=1.0, type="message"))
    return output


def search_facts(
    memory_store: Any,
    query: str,
    limit: int = 50,
) -> List[SearchResult]:
    """Synchronous search helper for MemoryStore fixtures.

    This is a thin wrapper around the store's own search method,
    returning SearchResult objects for compatibility with the test suite.
    """
    facts = memory_store.get_facts(query=query, limit=limit)
    output: List[SearchResult] = []
    for fact in facts:
        output.append(SearchResult(item=fact, score=1.0, type="fact"))
    return output