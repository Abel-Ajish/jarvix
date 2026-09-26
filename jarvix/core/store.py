"""SQLite store interfaces for jarvix.

These are the FROZEN contracts that Phase 3 (Memory) will implement.
Phase 1 only defines the interfaces and the schema.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional


@dataclass
class Message:
    """A conversation message."""
    id: int
    conversation_id: str
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    timestamp: datetime
    metadata: Optional[dict] = None


@dataclass
class Fact:
    """A remembered fact."""
    id: int
    fact: str
    source: str  # "user" | "ai" | "system"
    confidence: float
    created_at: datetime
    last_used: Optional[datetime] = None
    tags: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Interfaces (frozen after Phase 1)
# ---------------------------------------------------------------------------

class ConversationStore(ABC):
    """Interface for conversation persistence."""

    @abstractmethod
    def create_conversation(self, title: Optional[str] = None) -> str:
        """Create a new conversation, return its ID."""
        ...

    @abstractmethod
    def add_message(
        self,
        conv_id: str,
        role: str,
        content: str,
        *,
        metadata: Optional[dict] = None,
    ) -> int:
        """Add a message, return its ID."""
        ...

    @abstractmethod
    def get_history(self, conv_id: str, limit: int = 50) -> List[Message]:
        """Get the last N messages for a conversation."""
        ...

    @abstractmethod
    def search(self, query: str, limit: int = 50) -> List[Message]:
        """Full-text search across all conversations."""
        ...

    @abstractmethod
    def delete_conversation(self, conv_id: str) -> None:
        """Delete a conversation and all its messages."""
        ...

    @abstractmethod
    def list_conversations(self, limit: int = 50) -> List[dict]:
        """List recent conversations with their IDs and titles."""
        ...


class MemoryStore(ABC):
    """Interface for persistent memory (facts)."""

    @abstractmethod
    def add_fact(
        self,
        fact: str,
        *,
        source: str = "user",
        confidence: float = 1.0,
        tags: Optional[List[str]] = None,
    ) -> int:
        """Add a fact, return its ID."""
        ...

    @abstractmethod
    def get_facts(self, query: Optional[str] = None, limit: int = 50) -> List[Fact]:
        """Get facts, optionally filtered by query."""
        ...

    @abstractmethod
    def update_fact(self, fact_id: int, **kwargs: Any) -> bool:
        """Update a fact's fields (fact, confidence, tags)."""
        ...

    @abstractmethod
    def delete_fact(self, fact_id: int) -> bool:
        """Delete a fact by ID."""
        ...

    @abstractmethod
    def search_facts(self, query: str, limit: int = 50) -> List[Fact]:
        """Full-text search over facts."""
        ...


# ---------------------------------------------------------------------------
# Schema (also frozen)
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- Enable WAL mode for concurrent read/write
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
-- Conversations
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Messages
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT,  -- JSON
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(timestamp);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content, conversation_id, content='messages', content_rowid='id'
);

-- Memory facts
CREATE TABLE IF NOT EXISTS memory_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    tags TEXT  -- JSON array
);

CREATE INDEX IF NOT EXISTS idx_facts_created ON memory_facts(created_at);
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    fact, source, tags, content='memory_facts', content_rowid='id'
);

-- Tool call log (for debugging / replay)
CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT,
    tool_name TEXT NOT NULL,
    args TEXT,  -- JSON
    result TEXT,  -- JSON
    ok INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Permission log (audit trail)
CREATE TABLE IF NOT EXISTS permissions_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    args TEXT,  -- JSON
    decision TEXT NOT NULL,  -- "allowed" | "confirmed" | "denied"
    reason TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""