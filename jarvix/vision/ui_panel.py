"""Vision UI Panel for jarvix settings (Phase 7).

Provides a settings tab for vision configuration:
- Capture mode (mss/PIL)
- Default monitor/region
- Vision model selection
- Confidence threshold
- Backend testing
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from jarvix.core.config import get_settings
from jarvix.core.logger import get_logger
from jarvix.ui.extensions import SettingsTab, get_settings_tab_registry
from jarvix.vision.capture import get_capture_backend, get_monitors, get_primary_monitor, HAS_MSS, HAS_PIL

_LOG = get_logger("jarvix.vision.ui_panel")


class VisionSettingsTab(SettingsTab):
    """Settings tab for vision configuration."""

    group = "vision"
    title = "Vision"

    def __init__(self) -> None:
        self._widget: Optional[QWidget] = None
        self._settings = get_settings()
        self._monitors: List[Any] = []

    def widget(self) -> QWidget:
        if self._widget is None:
            self._widget = self._build_widget()
        return self._widget

    def _build_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # --- Capture Backend ---
        backend_group = QGroupBox("Screen Capture")
        backend_layout = QFormLayout(backend_group)

        self._backend_label = QLabel(self._get_backend_status())
        self._backend_label.setWordWrap(True)
        backend_layout.addRow("Active backend:", self._backend_label)

        if HAS_MSS:
            self._capture_mode = QComboBox()
            self._capture_mode.addItems(["auto", "mss", "PIL"])
            current = self._settings.get("vision.capture_mode", "auto")
            self._capture_mode.setCurrentText(current)
            self._capture_mode.currentTextChanged.connect(self._on_capture_mode_changed)
            backend_layout.addRow("Preferred mode:", self._capture_mode)
        else:
            mode_label = QLabel("PIL (mss not installed - run: pip install mss)")
            mode_label.setStyleSheet("color: #888;")
            backend_layout.addRow("Mode:", mode_label)

        # Monitor selection
        self._refresh_monitors()
        self._monitor_combo = QComboBox()
        self._populate_monitor_combo()
        current_monitor = self._settings.get("vision.default_monitor", 0)
        self._monitor_combo.setCurrentIndex(current_monitor)
        self._monitor_combo.currentIndexChanged.connect(self._on_monitor_changed)
        backend_layout.addRow("Default monitor:", self._monitor_combo)

        # Region capture option
        self._use_custom_region = QCheckBox("Use custom capture region")
        self._use_custom_region.setChecked(self._settings.get("vision.use_custom_region", False))
        self._use_custom_region.toggled.connect(self._on_custom_region_toggled)
        backend_layout.addRow("", self._use_custom_region)

        # Region inputs
        region_layout = QHBoxLayout()
        self._region_left = QSpinBox()
        self._region_left.setRange(-10000, 10000)
        self._region_left.setValue(self._settings.get("vision.region_left", 0))
        self._region_left.setSuffix(" px")
        self._region_left.setEnabled(self._use_custom_region.isChecked())
        self._region_left.valueChanged.connect(self._on_region_changed)

        self._region_top = QSpinBox()
        self._region_top.setRange(-10000, 10000)
        self._region_top.setValue(self._settings.get("vision.region_top", 0))
        self._region_top.setSuffix(" px")
        self._region_top.setEnabled(self._use_custom_region.isChecked())
        self._region_top.valueChanged.connect(self._on_region_changed)

        self._region_width = QSpinBox()
        self._region_width.setRange(1, 10000)
        self._region_width.setValue(self._settings.get("vision.region_width", 1920))
        self._region_width.setSuffix(" px")
        self._region_width.setEnabled(self._use_custom_region.isChecked())
        self._region_width.valueChanged.connect(self._on_region_changed)

        self._region_height = QSpinBox()
        self._region_height.setRange(1, 10000)
        self._region_height.setValue(self._settings.get("vision.region_height", 1080))
        self._region_height.setSuffix(" px")
        self._region_height.setEnabled(self._use_custom_region.isChecked())
        self._region_height.valueChanged.connect(self._on_region_changed)

        region_layout.addWidget(QLabel("Left:"))
        region_layout.addWidget(self._region_left)
        region_layout.addWidget(QLabel("Top:"))
        region_layout.addWidget(self._region_top)
        region_layout.addWidget(QLabel("Width:"))
        region_layout.addWidget(self._region_width)
        region_layout.addWidget(QLabel("Height:"))
        region_layout.addWidget(self._region_height)
        region_layout.addStretch()

        backend_layout.addRow("Region:", region_layout)

        # Test capture button
        test_capture_btn = QPushButton("Test Screen Capture")
        test_capture_btn.clicked.connect(self._on_test_capture)
        backend_layout.addRow("", test_capture_btn)

        layout.addWidget(backend_group)

        # --- Vision Model ---
        model_group = QGroupBox("Vision Model")
        model_layout = QFormLayout(model_group)

        self._vision_provider = QComboBox()
        self._vision_provider.addItems(["auto", "openrouter", "openai", "anthropic", "gemini"])
        self._vision_provider.setCurrentText(self._settings.get("vision.provider", "auto"))
        self._vision_provider.currentTextChanged.connect(self._on_provider_changed)
        model_layout.addRow("Provider:", self._vision_provider)

        self._vision_model = QLineEdit(self._settings.get("vision.model", ""))
        self._vision_model.setPlaceholderText("Leave empty for provider default (e.g., anthropic/claude-3.5-sonnet)")
        self._vision_model.editingFinished.connect(self._on_model_changed)
        model_layout.addRow("Model:", self._vision_model)

        # Confidence threshold
        self._confidence_threshold = QSpinBox()
        self._confidence_threshold.setRange(0, 100)
        self._confidence_threshold.setValue(int(self._settings.get("vision.confidence_threshold", 0.3) * 100))
        self._confidence_threshold.setSuffix("%")
        self._confidence_threshold.valueChanged.connect(self._on_confidence_changed)
        model_layout.addRow("Detection confidence:", self._confidence_threshold)

        # Test vision button
        test_vision_btn = QPushButton("Test Vision Model")
        test_vision_btn.clicked.connect(self._on_test_vision)
        model_layout.addRow("", test_vision_btn)

        layout.addWidget(model_group)

        # --- UI Detection ---
        ui_group = QGroupBox("UI Element Detection")
        ui_layout = QFormLayout(ui_group)

        self._enable_ui_detection = QCheckBox("Enable UI element detection")
        self._enable_ui_detection.setChecked(self._settings.get("vision.enable_ui_detection", True))
        self._enable_ui_detection.toggled.connect(self._on_ui_detection_changed)
        ui_layout.addRow("", self._enable_ui_detection)

        self._max_elements = QSpinBox()
        self._max_elements.setRange(10, 500)
        self._max_elements.setValue(self._settings.get("vision.max_elements", 100))
        self._max_elements.setSuffix(" elements")
        self._max_elements.valueChanged.connect(self._on_max_elements_changed)
        ui_layout.addRow("Max elements per analysis:", self._max_elements)

        layout.addWidget(ui_group)

        # --- Performance ---
        perf_group = QGroupBox("Performance")
        perf_layout = QFormLayout(perf_group)

        self._capture_timeout = QSpinBox()
        self._capture_timeout.setRange(100, 10000)
        self._capture_timeout.setValue(self._settings.get("vision.capture_timeout_ms", 5000))
        self._capture_timeout.setSuffix(" ms")
        self._capture_timeout.valueChanged.connect(self._on_capture_timeout_changed)
        perf_layout.addRow("Capture timeout:", self._capture_timeout)

        self._cache_screenshots = QCheckBox("Cache last screenshot (for rapid repeated analysis)")
        self._cache_screenshots.setChecked(self._settings.get("vision.cache_screenshots", False))
        self._cache_screenshots.toggled.connect(self._on_cache_changed)
        perf_layout.addRow("", self._cache_screenshots)

        layout.addWidget(perf_group)

        layout.addStretch()

        # Info
        info = QLabel(
            "Vision subsystem uses screen capture (mss/PIL) + online AI vision models. "
            "Requires a configured AI provider with vision support (OpenRouter, OpenAI, Anthropic, Gemini). "
            "mss is recommended for multi-monitor support and speed."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(info)

        return widget

    def _get_backend_status(self) -> str:
        backend = get_capture_backend()
        if backend == "mss":
            return "mss (fast, multi-monitor) ✓"
        elif backend == "PIL":
            return "PIL ImageGrab (single monitor fallback)"
        return "No capture backend available"

    def _refresh_monitors(self) -> None:
        self._monitors = get_monitors()

    def _populate_monitor_combo(self) -> None:
        self._monitor_combo.clear()
        self._monitor_combo.addItem("All monitors combined", 0)
        for m in self._monitors:
            label = f"Monitor {m.index}: {m.width}×{m.height} @ ({m.left},{m.top})"
            if m.is_primary:
                label += " (Primary)"
            self._monitor_combo.addItem(label, m.index)

    # --- Handlers ---

    def _on_capture_mode_changed(self, value: str) -> None:
        self._settings.set("vision.capture_mode", value)
        self._backend_label.setText(self._get_backend_status())

    def _on_monitor_changed(self, index: int) -> None:
        monitor_id = self._monitor_combo.currentData()
        self._settings.set("vision.default_monitor", monitor_id)

    def _on_custom_region_toggled(self, checked: bool) -> None:
        self._settings.set("vision.use_custom_region", checked)
        for widget in [self._region_left, self._region_top, self._region_width, self._region_height]:
            widget.setEnabled(checked)

    def _on_region_changed(self) -> None:
        self._settings.set("vision.region_left", self._region_left.value())
        self._settings.set("vision.region_top", self._region_top.value())
        self._settings.set("vision.region_width", self._region_width.value())
        self._settings.set("vision.region_height", self._region_height.value())

    def _on_provider_changed(self, value: str) -> None:
        self._settings.set("vision.provider", value)

    def _on_model_changed(self) -> None:
        self._settings.set("vision.model", self._vision_model.text().strip())

    def _on_confidence_changed(self, value: int) -> None:
        self._settings.set("vision.confidence_threshold", value / 100.0)

    def _on_ui_detection_changed(self, checked: bool) -> None:
        self._settings.set("vision.enable_ui_detection", checked)

    def _on_max_elements_changed(self, value: int) -> None:
        self._settings.set("vision.max_elements", value)

    def _on_capture_timeout_changed(self, value: int) -> None:
        self._settings.set("vision.capture_timeout_ms", value)

    def _on_cache_changed(self, checked: bool) -> None:
        self._settings.set("vision.cache_screenshots", checked)

    def _on_test_capture(self) -> None:
        """Test screen capture in background."""
        from jarvix.vision.capture import capture_to_temp_async, get_capture_backend

        btn = self._widget.findChild(QPushButton)
        if btn:
            btn.setEnabled(False)
            btn.setText("Capturing...")

        async def _test():
            try:
                # Use current settings
                monitor_index = self._monitor_combo.currentData()
                use_custom = self._use_custom_region.isChecked()

                region = None
                if use_custom:
                    region = (
                        self._region_left.value(),
                        self._region_top.value(),
                        self._region_left.value() + self._region_width.value(),
                        self._region_top.value() + self._region_height.value(),
                    )

                path = await capture_to_temp_async(
                    monitor_index=monitor_index,
                    region=region,
                )
                return True, f"Capture successful!\nSaved to: {path}\nBackend: {get_capture_backend()}"
            except Exception as e:
                return False, f"Capture failed: {e}"

        def _done(fut):
            try:
                ok, msg = fut.result()
                if self._widget:
                    if btn:
                        btn.setEnabled(True)
                        btn.setText("Test Screen Capture")
                    if ok:
                        QMessageBox.information(self._widget, "Capture Test", msg)
                    else:
                        QMessageBox.warning(self._widget, "Capture Test Failed", msg)
            except Exception as e:
                if self._widget and btn:
                    btn.setEnabled(True)
                    btn.setText("Test Screen Capture")
                _LOG.exception("Test capture callback failed")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        fut = asyncio.run_coroutine_threadsafe(_test(), loop)
        fut.add_done_callback(_done)

    def _on_test_vision(self) -> None:
        """Test vision model with a sample capture."""
        from jarvix.vision.online_vision import vision_analyze, vision_is_available
        from jarvix.vision.capture import capture_screen_bytes

        btn = self._widget.findChild(QPushButton)
        # Find the test vision button specifically
        for b in self._widget.findChildren(QPushButton):
            if b.text() == "Test Vision Model":
                btn = b
                break

        if btn:
            btn.setEnabled(False)
            btn.setText("Testing...")

        async def _test():
            try:
                if not vision_is_available():
                    return False, "No vision model configured. Set up an AI provider with vision support."

                # Capture screen
                image_bytes = await capture_screen_bytes()

                # Test with simple prompt
                result = await vision_analyze(
                    image_bytes,
                    "Describe what you see in one sentence.",
                )

                if result.ok:
                    return True, f"Vision working!\nProvider: {result.model}\nResponse: {result.text[:200]}..."
                else:
                    return False, f"Vision failed: {result.error}"

            except Exception as e:
                return False, f"Vision test failed: {e}"

        def _done(fut):
            try:
                ok, msg = fut.result()
                if self._widget:
                    if btn:
                        btn.setEnabled(True)
                        btn.setText("Test Vision Model")
                    if ok:
                        QMessageBox.information(self._widget, "Vision Test", msg)
                    else:
                        QMessageBox.warning(self._widget, "Vision Test Failed", msg)
            except Exception as e:
                if self._widget and btn:
                    btn.setEnabled(True)
                    btn.setText("Test Vision Model")
                _LOG.exception("Test vision callback failed")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        fut = asyncio.run_coroutine_threadsafe(_test(), loop)
        fut.add_done_callback(_done)


def register_vision_settings_tab() -> None:
    """Register the vision settings tab."""
    settings_registry = get_settings_tab_registry()
    settings_registry.register(VisionSettingsTab())