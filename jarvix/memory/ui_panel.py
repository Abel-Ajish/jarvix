"""Memory UI Panel - PySide6 widget for managing memories.

Shows memory list with columns: Category, Created, Last Used, Importance, Source
Actions: Search, Add, Edit, Delete, Forget, Clear Category, Clear All
Registers as Panel via PanelRegistry
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from jarvix.core.logger import get_logger
from jarvix.core.store import Fact
from jarvix.memory.manager import get_memory_manager, MemoryManager
from jarvix.ui.extensions import Panel, get_panel_registry

_LOG = get_logger("jarvix.memory.panel")


class MemoryPanel(QWidget):
    """Main widget for the Memory panel."""

    def __init__(self, memory_manager: Optional[MemoryManager] = None) -> None:
        super().__init__()
        self._manager = memory_manager
        self._facts: List[Fact] = []
        self._setup_ui()
        self._load_memories()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Toolbar
        toolbar = QToolBar()
        toolbar.setMovable(False)

        # Search
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search memories...")
        self._search_input.setMinimumWidth(200)
        self._search_input.returnPressed.connect(self._on_search)
        toolbar.addWidget(QLabel("Search:"))
        toolbar.addWidget(self._search_input)

        toolbar.addSeparator()

        # Add button
        add_action = QAction("Add", self)
        add_action.triggered.connect(self._on_add)
        toolbar.addAction(add_action)

        # Edit button
        edit_action = QAction("Edit", self)
        edit_action.triggered.connect(self._on_edit)
        toolbar.addAction(edit_action)

        # Delete/Forget button
        delete_action = QAction("Forget", self)
        delete_action.triggered.connect(self._on_delete)
        toolbar.addAction(delete_action)

        toolbar.addSeparator()

        # Clear Category
        clear_cat_action = QAction("Clear Category", self)
        clear_cat_action.triggered.connect(self._on_clear_category)
        toolbar.addAction(clear_cat_action)

        # Clear All
        clear_all_action = QAction("Clear All", self)
        clear_all_action.triggered.connect(self._on_clear_all)
        toolbar.addAction(clear_all_action)

        toolbar.addSeparator()

        # Refresh
        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self._load_memories)
        toolbar.addAction(refresh_action)

        layout.addWidget(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Category", "Created", "Last Used", "Importance", "Source"])
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.itemDoubleClicked.connect(self._on_edit)

        # Configure columns
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Category
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Created
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Last Used
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Importance
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Source

        layout.addWidget(self._table)

        # Status label
        self._status_label = QLabel("Loading...")
        layout.addWidget(self._status_label)

    def _load_memories(self) -> None:
        """Load all memories asynchronously."""
        self._status_label.setText("Loading memories...")
        QTimer.singleShot(0, self._do_load_memories)

    async def _do_load_memories(self) -> None:
        try:
            mgr = await get_memory_manager() if self._manager is None else self._manager
            self._facts = await mgr.list_memories(limit=500)
            self._populate_table(self._facts)
            self._status_label.setText(f"Showing {len(self._facts)} memories")
        except Exception as e:
            _LOG.error("Failed to load memories: %s", e)
            self._status_label.setText(f"Error: {e}")

    def _populate_table(self, facts: List[Fact]) -> None:
        """Populate the table with facts."""
        self._table.setRowCount(0)
        self._table.setRowCount(len(facts))

        for row, fact in enumerate(facts):
            # Category (from tags)
            category = ""
            if fact.tags:
                category = ", ".join(fact.tags[:2])  # Show first 2 tags
            self._table.setItem(row, 0, QTableWidgetItem(category))

            # Created
            created_str = fact.created_at.strftime("%Y-%m-%d %H:%M")
            self._table.setItem(row, 1, QTableWidgetItem(created_str))

            # Last Used
            last_used_str = fact.last_used.strftime("%Y-%m-%d %H:%M") if fact.last_used else "Never"
            self._table.setItem(row, 2, QTableWidgetItem(last_used_str))

            # Importance (confidence as percentage)
            importance_str = f"{fact.confidence * 100:.0f}%"
            importance_item = QTableWidgetItem(importance_str)
            importance_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 3, importance_item)

            # Source
            self._table.setItem(row, 4, QTableWidgetItem(fact.source))

            # Store fact ID in the first item for reference
            self._table.item(row, 0).setData(Qt.UserRole, fact.id)

    def _get_selected_fact(self) -> Optional[Fact]:
        """Get the currently selected fact."""
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        fact_id = self._table.item(row, 0).data(Qt.UserRole)
        for fact in self._facts:
            if fact.id == fact_id:
                return fact
        return None

    @Slot()
    def _on_search(self) -> None:
        """Handle search."""
        query = self._search_input.text().strip()
        if not query:
            self._populate_table(self._facts)
            return

        QTimer.singleShot(0, lambda: self._do_search(query))

    async def _do_search(self, query: str) -> None:
        try:
            mgr = await get_memory_manager() if self._manager is None else self._manager
            results = await mgr.search_memory(query, limit=100)
            self._populate_table(results)
            self._status_label.setText(f"Found {len(results)} matches for '{query}'")
        except Exception as e:
            _LOG.error("Search failed: %s", e)
            self._status_label.setText(f"Search error: {e}")

    @Slot()
    def _on_add(self) -> None:
        """Add a new fact."""
        dialog = FactDialog(self)
        if dialog.exec() == QDialog.Accepted:
            fact_text = dialog.fact_text
            source = dialog.source
            confidence = dialog.confidence
            tags = dialog.tags

            QTimer.singleShot(0, lambda: self._do_add(fact_text, source, confidence, tags))

    async def _do_add(self, fact: str, source: str, confidence: float, tags: Optional[List[str]]) -> None:
        try:
            mgr = await get_memory_manager() if self._manager is None else self._manager
            fact_id = await mgr.remember(fact, source, confidence, tags)
            _LOG.info("Added memory with ID %d", fact_id)
            self._load_memories()
        except Exception as e:
            _LOG.error("Failed to add memory: %s", e)
            QMessageBox.critical(self, "Error", f"Failed to add memory: {e}")

    @Slot()
    def _on_edit(self) -> None:
        """Edit the selected fact."""
        fact = self._get_selected_fact()
        if not fact:
            return

        dialog = FactDialog(self, fact)
        if dialog.exec() == QDialog.Accepted:
            QTimer.singleShot(0, lambda: self._do_edit(fact.id, dialog.fact_text, dialog.source, dialog.confidence, dialog.tags))

    async def _do_edit(self, fact_id: int, fact: str, source: str, confidence: float, tags: Optional[List[str]]) -> None:
        try:
            mgr = await get_memory_manager() if self._manager is None else self._manager
            success = await mgr.update_memory(
                fact_id,
                fact=fact,
                source=source,
                confidence=confidence,
                tags=tags,
            )
            if success:
                _LOG.info("Updated memory %d", fact_id)
                self._load_memories()
            else:
                QMessageBox.warning(self, "Not Found", "Memory not found")
        except Exception as e:
            _LOG.error("Failed to update memory: %s", e)
            QMessageBox.critical(self, "Error", f"Failed to update memory: {e}")

    @Slot()
    def _on_delete(self) -> None:
        """Delete the selected fact."""
        fact = self._get_selected_fact()
        if not fact:
            return

        reply = QMessageBox.question(
            self,
            "Forget Memory",
            f"Forget this memory?\n\n\"{fact.fact[:100]}{'...' if len(fact.fact) > 100 else ''}\"",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            QTimer.singleShot(0, lambda: self._do_delete(fact.id))

    async def _do_delete(self, fact_id: int) -> None:
        try:
            mgr = await get_memory_manager() if self._manager is None else self._manager
            success = await mgr.forget_memory(fact_id)
            if success:
                _LOG.info("Deleted memory %d", fact_id)
                self._load_memories()
            else:
                QMessageBox.warning(self, "Not Found", "Memory not found")
        except Exception as e:
            _LOG.error("Failed to delete memory: %s", e)
            QMessageBox.critical(self, "Error", f"Failed to delete memory: {e}")

    @Slot()
    def _on_clear_category(self) -> None:
        """Clear all memories with a specific tag/category."""
        # Get unique categories from current facts
        categories = set()
        for fact in self._facts:
            if fact.tags:
                categories.update(fact.tags)

        if not categories:
            QMessageBox.information(self, "No Categories", "No categories found")
            return

        # Show category selection dialog
        dialog = CategorySelectDialog(sorted(categories), self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_category:
            category = dialog.selected_category
            reply = QMessageBox.question(
                self,
                "Clear Category",
                f"Forget all memories with category '{category}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                QTimer.singleShot(0, lambda: self._do_clear_category(category))

    async def _do_clear_category(self, category: str) -> None:
        try:
            mgr = await get_memory_manager() if self._manager is None else self._manager
            # Find all facts with this tag
            all_facts = await mgr.list_memories(limit=1000)
            deleted = 0
            for fact in all_facts:
                if fact.tags and category in fact.tags:
                    if await mgr.forget_memory(fact.id):
                        deleted += 1
            _LOG.info("Cleared category '%s': deleted %d memories", category, deleted)
            self._load_memories()
            QMessageBox.information(self, "Done", f"Cleared category '{category}': {deleted} memories forgotten")
        except Exception as e:
            _LOG.error("Failed to clear category: %s", e)
            QMessageBox.critical(self, "Error", f"Failed to clear category: {e}")

    @Slot()
    def _on_clear_all(self) -> None:
        """Clear all memories."""
        reply = QMessageBox.question(
            self,
            "Clear All Memories",
            "FORGET ALL MEMORIES? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            # Double confirmation
            reply2 = QMessageBox.question(
                self,
                "Confirm",
                "Are you absolutely sure? All memories will be permanently deleted.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply2 == QMessageBox.Yes:
                QTimer.singleShot(0, self._do_clear_all)

    async def _do_clear_all(self) -> None:
        try:
            mgr = await get_memory_manager() if self._manager is None else self._manager
            all_facts = await mgr.list_memories(limit=10000)
            deleted = 0
            for fact in all_facts:
                if await mgr.forget_memory(fact.id):
                    deleted += 1
            _LOG.info("Cleared all memories: deleted %d", deleted)
            self._load_memories()
            QMessageBox.information(self, "Done", f"Cleared all memories: {deleted} forgotten")
        except Exception as e:
            _LOG.error("Failed to clear all: %s", e)
            QMessageBox.critical(self, "Error", f"Failed to clear all: {e}")

    def _show_context_menu(self, pos) -> None:
        """Show context menu on right-click."""
        item = self._table.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)

        edit_action = menu.addAction("Edit")
        edit_action.triggered.connect(self._on_edit)

        delete_action = menu.addAction("Forget")
        delete_action.triggered.connect(self._on_delete)

        menu.addSeparator()

        copy_action = menu.addAction("Copy Fact")
        copy_action.triggered.connect(lambda: self._copy_fact(item.row()))

        menu.exec(self._table.mapToGlobal(pos))

    def _copy_fact(self, row: int) -> None:
        """Copy fact text to clipboard."""
        fact_id = self._table.item(row, 0).data(Qt.UserRole)
        for fact in self._facts:
            if fact.id == fact_id:
                from PySide6.QtWidgets import QApplication
                QApplication.clipboard().setText(fact.fact)
                self._status_label.setText("Copied to clipboard")
                break


class FactDialog(QDialog):
    """Dialog for adding/editing a fact."""

    def __init__(self, parent: QWidget, fact: Optional[Fact] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Memory" if fact is None else "Edit Memory")
        self.resize(500, 400)

        self.fact_text = ""
        self.source = "user"
        self.confidence = 1.0
        self.tags: List[str] = []

        layout = QVBoxLayout(self)

        # Fact text
        layout.addWidget(QLabel("Fact:"))
        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText("Enter the fact to remember...")
        if fact:
            self._text_edit.setPlainText(fact.fact)
        layout.addWidget(self._text_edit)

        # Source
        layout.addWidget(QLabel("Source:"))
        self._source_input = QLineEdit()
        self._source_input.setPlaceholderText("user, ai, or system")
        self._source_input.setText(fact.source if fact else "user")
        layout.addWidget(self._source_input)

        # Confidence
        layout.addWidget(QLabel("Confidence (0.0 - 1.0):"))
        self._confidence_input = QLineEdit()
        self._confidence_input.setPlaceholderText("1.0")
        self._confidence_input.setText(str(fact.confidence) if fact else "1.0")
        layout.addWidget(self._confidence_input)

        # Tags
        layout.addWidget(QLabel("Tags (comma-separated):"))
        self._tags_input = QLineEdit()
        self._tags_input.setPlaceholderText("work, personal, project")
        if fact and fact.tags:
            self._tags_input.setText(", ".join(fact.tags))
        layout.addWidget(self._tags_input)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        fact_text = self._text_edit.toPlainText().strip()
        if not fact_text:
            QMessageBox.warning(self, "Empty Fact", "Please enter a fact")
            return

        source = self._source_input.text().strip() or "user"
        if source not in ("user", "ai", "system"):
            source = "user"

        try:
            confidence = float(self._confidence_input.text().strip() or "1.0")
            confidence = max(0.0, min(1.0, confidence))
        except ValueError:
            confidence = 1.0

        tags_text = self._tags_input.text().strip()
        tags = [t.strip() for t in tags_text.split(",") if t.strip()] if tags_text else None

        self.fact_text = fact_text
        self.source = source
        self.confidence = confidence
        self.tags = tags or []
        self.accept()


class CategorySelectDialog(QDialog):
    """Dialog for selecting a category."""

    def __init__(self, categories: List[str], parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Category")
        self.resize(300, 400)

        self.selected_category: Optional[str] = None

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Select a category to clear:"))

        self._list = QListWidget()
        self._list.addItems(categories)
        self._list.setCurrentRow(0)
        layout.addWidget(self._list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        item = self._list.currentItem()
        if item:
            self.selected_category = item.text()
            self.accept()


class MemoryPanelWrapper(Panel):
    """Panel wrapper for the Memory UI."""

    name = "Memory"
    icon = "🧠"

    def __init__(self) -> None:
        self._panel: Optional[MemoryPanel] = None

    def widget(self) -> QWidget:
        if self._panel is None:
            self._panel = MemoryPanel()
        return self._panel

    def on_show(self) -> None:
        if self._panel:
            self._panel._load_memories()

    def on_hide(self) -> None:
        pass


# Register the panel on import
def register_memory_panel() -> None:
    """Register the memory panel and settings tab."""
    registry = get_panel_registry()
    registry.register(MemoryPanelWrapper())


# Auto-register when imported
register_memory_panel()