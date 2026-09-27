"""Memory manager - high-level interface for remembering and retrieving facts.

This module provides the main public API for the Memory system:
- remember(fact, source, confidence, tags) -> fact_id
- retrieve_memory(query, limit) -> List[Fact]
- search_memory(query, limit) -> List[Fact]
- update_memory(fact_id, **kwargs) -> bool
- forget_memory(fact_id) -> bool
- list_memories(limit) -> List[Fact]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from jarvix.core.store import Fact
from jarvix.memory.database import SQLiteConversationStore, SQLiteMemoryStore, get_conversation_store, get_memory_store


class MemoryManager:
    """High-level memory management interface."""

    def __init__(self, db_path: Optional[Path] = None):
        self._conversation_store: Optional[SQLiteConversationStore] = None
        self._memory_store: Optional[SQLiteMemoryStore] = None
        if db_path is not None:
            self._conversation_store = SQLiteConversationStore(db_path)
            self._memory_store = SQLiteMemoryStore(db_path)

    def close(self) -> None:
        """Close the underlying stores."""
        if self._conversation_store:
            self._conversation_store.close()
        if self._memory_store:
            self._memory_store.close()

    async def _get_conv_store(self) -> SQLiteConversationStore:
        if self._conversation_store is None:
            self._conversation_store = await get_conversation_store()
        return self._conversation_store

    async def _get_mem_store(self) -> SQLiteMemoryStore:
        if self._memory_store is None:
            self._memory_store = await get_memory_store()
        return self._memory_store

    async def remember(
        self,
        fact: str,
        source: str = "user",
        confidence: float = 1.0,
        tags: Optional[List[str]] = None,
    ) -> int:
        """Remember a new fact, return its ID.

        Args:
            fact: The fact to remember
            source: Source of the fact ("user", "ai", "system")
            confidence: Confidence level 0.0-1.0
            tags: Optional list of tags for categorization

        Returns:
            The ID of the newly created fact
        """
        store = await self._get_mem_store()
        return await store.add_fact(fact, source=source, confidence=confidence, tags=tags)

    async def retrieve_memory(
        self,
        query: Optional[str] = None,
        limit: int = 50,
    ) -> List[Fact]:
        """Retrieve memories, optionally filtered by query.

        Args:
            query: Optional search query
            limit: Maximum number of results

        Returns:
            List of Fact objects
        """
        store = await self._get_mem_store()
        return await store.get_facts(query, limit)

    async def search_memory(
        self,
        query: str,
        limit: int = 50,
    ) -> List[Fact]:
        """Full-text search over memories.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of matching Fact objects ranked by relevance
        """
        store = await self._get_mem_store()
        return await store.search_facts(query, limit)

    async def update_memory(
        self,
        fact_id: int,
        **kwargs: Any,
    ) -> bool:
        """Update a fact's fields.

        Args:
            fact_id: ID of the fact to update
            **kwargs: Fields to update (fact, source, confidence, tags)

        Returns:
            True if the fact was updated, False if not found
        """
        store = await self._get_mem_store()
        return await store.update_fact(fact_id, **kwargs)

    async def forget_memory(self, fact_id: int) -> bool:
        """Forget (delete) a fact by ID.

        Args:
            fact_id: ID of the fact to forget

        Returns:
            True if the fact was deleted, False if not found
        """
        store = await self._get_mem_store()
        return await store.delete_fact(fact_id)

    async def list_memories(self, limit: int = 50) -> List[Fact]:
        """List all memories, most recent first.

        Args:
            limit: Maximum number of results

        Returns:
            List of Fact objects
        """
        store = await self._get_mem_store()
        return await store.get_facts(None, limit)

    async def start_conversation(self, title: Optional[str] = None) -> str:
        """Start a new conversation.

        Args:
            title: Optional title for the conversation

        Returns:
            Conversation ID
        """
        store = await self._get_conv_store()
        return await store.create_conversation(title)

    async def add_user_message(self, conv_id: str, content: str) -> int:
        """Add a user message to a conversation.

        Args:
            conv_id: Conversation ID
            content: Message content

        Returns:
            Message ID
        """
        store = await self._get_conv_store()
        return await store.add_message(conv_id, "user", content)

    async def add_assistant_message(self, conv_id: str, content: str) -> int:
        """Add an assistant message to a conversation.

        Args:
            conv_id: Conversation ID
            content: Message content

        Returns:
            Message ID
        """
        store = await self._get_conv_store()
        return await store.add_message(conv_id, "assistant", content)

    async def get_conversation_history(self, conv_id: str) -> List[dict]:
        """Get conversation history.

        Args:
            conv_id: Conversation ID

        Returns:
            List of message dicts
        """
        store = await self._get_conv_store()
        history = await store.get_history(conv_id)
        return [{"role": m.role, "content": m.content} for m in history]

    async def recall(self, query: Optional[str] = None, limit: int = 50) -> List[dict]:
        """Recall facts.

        Args:
            query: Optional search query
            limit: Maximum results

        Returns:
            List of fact dicts
        """
        facts = await self.retrieve_memory(query, limit)
        return [{"fact": f.fact, "source": f.source, "confidence": f.confidence} for f in facts]

    async def forget(self, fact_id: int) -> bool:
        """Forget a fact.

        Args:
            fact_id: Fact ID

        Returns:
            True if deleted
        """
        return await self.forget_memory(fact_id)

    async def search_all(self, query: str, limit: int = 50) -> dict:
        """Search both conversations and facts.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            Dict with 'conversations' and 'facts' keys
        """
        conversations = []
        facts = await self.recall(query=query, limit=limit)
        return {"conversations": conversations, "facts": facts}


# Global singleton instance
_manager: Optional[MemoryManager] = None


async def get_memory_manager() -> MemoryManager:
    """Get the global MemoryManager instance."""
    global _manager
    if _manager is None:
        _manager = MemoryManager()
    return _manager


# Convenience functions for direct use
async def remember(
    fact: str,
    source: str = "user",
    confidence: float = 1.0,
    tags: Optional[List[str]] = None,
) -> int:
    """Remember a fact (convenience function)."""
    mgr = await get_memory_manager()
    return await mgr.remember(fact, source, confidence, tags)


async def retrieve_memory(
    query: Optional[str] = None,
    limit: int = 50,
) -> List[Fact]:
    """Retrieve memories (convenience function)."""
    mgr = await get_memory_manager()
    return await mgr.retrieve_memory(query, limit)


async def search_memory(
    query: str,
    limit: int = 50,
) -> List[Fact]:
    """Search memories (convenience function)."""
    mgr = await get_memory_manager()
    return await mgr.search_memory(query, limit)


async def update_memory(
    fact_id: int,
    **kwargs: Any,
) -> bool:
    """Update a memory (convenience function)."""
    mgr = await get_memory_manager()
    return await mgr.update_memory(fact_id, **kwargs)


async def forget_memory(fact_id: int) -> bool:
    """Forget a memory (convenience function)."""
    mgr = await get_memory_manager()
    return await mgr.forget_memory(fact_id)


async def list_memories(limit: int = 50) -> List[Fact]:
    """List all memories (convenience function)."""
    mgr = await get_memory_manager()
    return await mgr.list_memories(limit)