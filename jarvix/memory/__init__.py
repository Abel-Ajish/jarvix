"""Memory package for jarvix.

Provides persistent memory (facts) with:
- SQLite-backed storage via aiosqlite
- FTS5 full-text search
- High-level MemoryManager API
- PySide6 UI panel for managing memories
"""

from __future__ import annotations

from typing import List, Optional

from jarvix.core.store import Fact
from jarvix.memory.database import (
    SQLiteConversationStore,
    SQLiteMemoryStore,
    get_conversation_store,
    get_memory_store,
)
from jarvix.memory.manager import (
    MemoryManager,
    get_memory_manager,
    remember,
    retrieve_memory,
    search_memory,
    update_memory,
    forget_memory,
    list_memories,
)
from jarvix.memory.search import (
    SearchEngine,
    SearchResult,
    get_search_engine,
    search_messages,
    search_facts,
    search_all,
)

# ---------------------------------------------------------------------------
# Panel registration
# ---------------------------------------------------------------------------

from jarvix.ui.extensions import get_panel_registry, get_settings_tab_registry, SettingsTab
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QCheckBox


class MemorySettingsTab(SettingsTab):
    """Settings tab for memory configuration."""

    group = "core"
    title = "Memory"

    def __init__(self) -> None:
        self._widget: Optional[QWidget] = None

    def widget(self) -> QWidget:
        if self._widget is None:
            self._widget = self._build_widget()
        return self._widget

    def _build_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel("<h3>Memory Settings</h3>"))

        # Max memories setting
        layout.addWidget(QLabel("Maximum memories stored:"))
        max_btn = QPushButton("500 (default)")
        max_btn.setCheckable(True)
        layout.addWidget(max_btn)

        # Auto-remember toggle
        auto_check = QCheckBox("Automatically remember important facts from conversations")
        auto_check.setChecked(True)
        layout.addWidget(auto_check)

        # Clear all button
        clear_btn = QPushButton("Clear All Memories...")
        clear_btn.clicked.connect(self._on_clear_all)
        layout.addWidget(clear_btn)

        layout.addStretch()

        # Info label
        info = QLabel("Memories are stored in %APPDATA%/jarvix/memory.db")
        info.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(info)

        return widget

    def _on_clear_all(self) -> None:
        """Handle clear all from settings."""
        from PySide6.QtWidgets import QMessageBox
        parent = self._widget.parent() if self._widget else None
        if parent:
            reply = QMessageBox.question(
                parent,
                "Clear All Memories",
                "FORGET ALL MEMORIES? This cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                # Run async clear
                async def _clear():
                    mgr = await get_memory_manager()
                    facts = await mgr.list_memories(limit=10000)
                    for fact in facts:
                        await mgr.forget_memory(fact.id)
                try:
                    loop.run_until_complete(_clear())
                except Exception as e:
                    if parent:
                        QMessageBox.critical(parent, "Error", str(e))


# Register panel and settings tab on import
def _register_memory_ui() -> None:
    """Register the memory panel and settings tab."""
    from jarvix.memory.ui_panel import MemoryPanelWrapper

    panel_registry = get_panel_registry()
    panel_registry.register(MemoryPanelWrapper())

    settings_registry = get_settings_tab_registry()
    settings_registry.register(MemorySettingsTab())


_register_memory_ui()


__all__ = [
    "Fact",
    "MemoryManager",
    "SQLiteConversationStore",
    "SQLiteMemoryStore",
    "SearchEngine",
    "SearchResult",
    "get_memory_manager",
    "get_memory_store",
    "get_conversation_store",
    "get_search_engine",
    "remember",
    "retrieve_memory",
    "search_memory",
    "update_memory",
    "forget_memory",
    "list_memories",
    "search_messages",
    "search_facts",
    "search_all",
]