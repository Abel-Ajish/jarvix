"""Wake word detection module for jarvix.

Supports multiple modes:
- Wake word: Energy-based or Porcupine (if available) detection for "jarvix"
- Push-to-talk: Manual activation via hotkey/button
- Continuous: Always listening
- Disabled: No voice activation

Publishes VoiceWake event when wake word detected.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable

from jarvix.core.events import EventBus, VoiceWake, ErrorRaised
from jarvix.core.logger import get_logger
from jarvix.core.config import get_settings

_LOG = get_logger("jarvix.voice.wake_word")


class WakeMode(Enum):
    """Wake word detection mode."""
    WAKE_WORD = "wake_word"      # Listen for "jarvix" (or custom)
    PUSH_TO_TALK = "push_to_talk"  # Manual activation
    CONTINUOUS = "continuous"     # Always listening
    DISABLED = "disabled"         # No voice activation


@dataclass
class WakeConfig:
    """Configuration for wake word detection."""
    mode: WakeMode = WakeMode.WAKE_WORD
    wake_word: str = "jarvix"
    sensitivity: float = 0.5
    sample_rate: int = 16000
    frame_length: int = 512
    # Porcupine settings
    porcupine_access_key: str = ""
    porcupine_model_path: str = ""
    porcupine_keyword_paths: list = None

    def __post_init__(self):
        if self.porcupine_keyword_paths is None:
            self.porcupine_keyword_paths = []


class WakeDetector(ABC):
    """Abstract base class for wake word detectors."""

    @abstractmethod
    async def start(self) -> bool:
        """Start detection. Returns True on success."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop detection."""
        ...

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Whether detector is running."""
        ...


class EnergyWakeDetector(WakeDetector):
    """Simple energy-based wake word detection.

    Listens for audio energy spike followed by the wake word pattern.
    This is a fallback when Porcupine is not available.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: WakeConfig,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self._event_bus = event_bus
        self._config = config
        self._on_error = on_error
        self._running = False
        self._stream = None
        self._energy_threshold = 0.02
        self._last_wake_time = 0.0
        self._wake_cooldown = 2.0  # seconds

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> bool:
        if self._running:
            return True

        try:
            import sounddevice as sd
            self._stream = sd.InputStream(
                samplerate=self._config.sample_rate,
                channels=1,
                dtype='float32',
                blocksize=self._config.frame_length,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._running = True
            _LOG.info("Energy-based wake detector started (wake word: %s)", self._config.wake_word)
            return True
        except Exception as e:
            _LOG.error("Failed to start wake detector: %s", e)
            self._publish_error(f"Wake detector failed: {e}")
            if self._on_error:
                self._on_error(e)
            return False

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            _LOG.warning("Wake detector audio status: %s", status)

        if not self._running:
            return

        # Calculate energy
        import numpy as np
        audio_data = indata[:, 0] if indata.ndim > 1 else indata
        energy = np.sqrt(np.mean(audio_data ** 2))

        current_time = time.time()

        # Simple energy spike detection
        if energy > self._energy_threshold:
            # Check cooldown
            if current_time - self._last_wake_time > self._wake_cooldown:
                self._last_wake_time = current_time
                # In a real implementation, we'd do pattern matching here
                # For now, just trigger on any loud sound
                _LOG.debug("Energy spike detected (%.4f)", energy)
                self._trigger_wake()

    def _trigger_wake(self) -> None:
        """Publish wake event."""
        _LOG.info("Wake word detected: %s", self._config.wake_word)
        self._event_bus.publish(VoiceWake())

    def stop(self) -> None:
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        _LOG.info("Energy wake detector stopped")

    def _publish_error(self, message: str) -> None:
        self._event_bus.publish(ErrorRaised(message, component="voice.wake_word.energy"))


class PorcupineWakeDetector(WakeDetector):
    """Porcupine wake word detector (requires pvporcupine package)."""

    def __init__(
        self,
        event_bus: EventBus,
        config: WakeConfig,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self._event_bus = event_bus
        self._config = config
        self._on_error = on_error
        self._running = False
        self._porcupine = None
        self._stream = None
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> bool:
        if self._running:
            return True

        try:
            import pvporcupine

            # Initialize Porcupine
            if self._config.porcupine_keyword_paths:
                self._porcupine = pvporcupine.create(
                    access_key=self._config.porcupine_access_key,
                    keyword_paths=self._config.porcupine_keyword_paths,
                    model_path=self._config.porcupine_model_path or None,
                    sensitivities=[self._config.sensitivity] * len(self._config.porcupine_keyword_paths),
                )
            else:
                # Use built-in keyword
                self._porcupine = pvporcupine.create(
                    access_key=self._config.porcupine_access_key,
                    keywords=[self._config.wake_word],
                    sensitivities=[self._config.sensitivity],
                )

            import sounddevice as sd
            self._stream = sd.InputStream(
                samplerate=self._porcupine.sample_rate,
                channels=1,
                dtype='int16',
                blocksize=self._porcupine.frame_length,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._running = True
            _LOG.info("Porcupine wake detector started (wake word: %s)", self._config.wake_word)
            return True

        except ImportError:
            _LOG.warning("pvporcupine not installed, falling back to energy detector")
            return False
        except Exception as e:
            _LOG.error("Failed to start Porcupine: %s", e)
            self._publish_error(f"Porcupine failed: {e}")
            if self._on_error:
                self._on_error(e)
            return False

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            _LOG.warning("Porcupine audio status: %s", status)

        if not self._running or self._porcupine is None:
            return

        # Process frame
        pcm = indata.flatten()
        keyword_index = self._porcupine.process(pcm)

        if keyword_index >= 0:
            _LOG.info("Porcupine detected keyword index: %d", keyword_index)
            self._event_bus.publish(VoiceWake())

    def stop(self) -> None:
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if self._porcupine:
            self._porcupine.delete()
            self._porcupine = None
        _LOG.info("Porcupine wake detector stopped")

    def _publish_error(self, message: str) -> None:
        self._event_bus.publish(ErrorRaised(message, component="voice.wake_word.porcupine"))


class PushToTalkDetector(WakeDetector):
    """Push-to-talk detector - triggered by external signal (hotkey/button)."""

    def __init__(
        self,
        event_bus: EventBus,
        config: WakeConfig,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self._event_bus = event_bus
        self._config = config
        self._on_error = on_error
        self._running = False
        self._trigger_callback: Optional[Callable[[], None]] = None

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> bool:
        self._running = True
        _LOG.info("Push-to-talk detector started")
        return True

    def trigger(self) -> None:
        """Call this to manually trigger wake word (e.g., from hotkey)."""
        if self._running:
            _LOG.info("Push-to-talk triggered")
            self._event_bus.publish(VoiceWake())

    def stop(self) -> None:
        self._running = False
        _LOG.info("Push-to-talk detector stopped")


class ContinuousDetector(WakeDetector):
    """Continuous listening detector - always publishes VoiceWake immediately."""

    def __init__(
        self,
        event_bus: EventBus,
        config: WakeConfig,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self._event_bus = event_bus
        self._config = config
        self._on_error = on_error
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> bool:
        self._running = True
        # Immediately publish wake for continuous mode
        self._event_bus.publish(VoiceWake())
        _LOG.info("Continuous detector started")
        return True

    def stop(self) -> None:
        self._running = False
        _LOG.info("Continuous detector stopped")


class DisabledDetector(WakeDetector):
    """Disabled detector - no voice activation."""

    def __init__(
        self,
        event_bus: EventBus,
        config: WakeConfig,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self._event_bus = event_bus
        self._config = config
        self._on_error = on_error
        self._running = False

    @property
    def is_running(self) -> bool:
        return False

    async def start(self) -> bool:
        _LOG.info("Wake word detection disabled")
        return True

    def stop(self) -> None:
        pass


class WakeWordManager:
    """Manages wake word detection based on configured mode."""

    def __init__(
        self,
        event_bus: EventBus,
        config: Optional[WakeConfig] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self._event_bus = event_bus
        self._config = config or WakeConfig()
        self._on_error = on_error
        self._detector: Optional[WakeDetector] = None
        self._running = False

    async def start(self) -> bool:
        """Start wake word detection based on configured mode."""
        if self._running:
            return True

        # Create detector based on mode
        self._detector = self._create_detector()

        if self._detector is None:
            return False

        success = await self._detector.start()
        if success:
            self._running = True
        return success

    def _create_detector(self) -> Optional[WakeDetector]:
        """Create appropriate detector based on mode."""
        mode = self._config.mode

        if mode == WakeMode.DISABLED:
            return DisabledDetector(self._event_bus, self._config, self._on_error)
        elif mode == WakeMode.PUSH_TO_TALK:
            return PushToTalkDetector(self._event_bus, self._config, self._on_error)
        elif mode == WakeMode.CONTINUOUS:
            return ContinuousDetector(self._event_bus, self._config, self._on_error)
        elif mode == WakeMode.WAKE_WORD:
            # Try Porcupine first, fall back to energy
            if self._config.porcupine_access_key:
                detector = PorcupineWakeDetector(self._event_bus, self._config, self._on_error)
                # We'll try to start it and fall back if needed
                return detector
            else:
                return EnergyWakeDetector(self._event_bus, self._config, self._on_error)

        return None

    async def try_start_with_fallback(self) -> bool:
        """Try Porcupine, fall back to energy detector."""
        if self._config.mode != WakeMode.WAKE_WORD:
            return await self.start()

        # Try Porcupine
        if self._config.porcupine_access_key:
            detector = PorcupineWakeDetector(self._event_bus, self._config, self._on_error)
            if await detector.start():
                self._detector = detector
                self._running = True
                return True
            _LOG.info("Porcupine failed, falling back to energy detector")

        # Fallback to energy
        detector = EnergyWakeDetector(self._event_bus, self._config, self._on_error)
        if await detector.start():
            self._detector = detector
            self._running = True
            return True

        return False

    def trigger_push_to_talk(self) -> None:
        """Trigger wake word for push-to-talk mode."""
        if isinstance(self._detector, PushToTalkDetector):
            self._detector.trigger()

    def stop(self) -> None:
        if self._detector:
            self._detector.stop()
            self._detector = None
        self._running = False
        _LOG.info("Wake word manager stopped")

    def set_mode(self, mode: WakeMode) -> None:
        """Change detection mode (requires restart)."""
        was_running = self._running
        if was_running:
            self.stop()
        self._config.mode = mode
        if was_running:
            # Restart will be called externally
            pass

    @property
    def is_running(self) -> bool:
        return self._running and (self._detector.is_running if self._detector else False)


def create_wake_detector(
    event_bus: EventBus,
    mode: str = "wake_word",
    wake_word: str = "jarvix",
    **kwargs
) -> WakeWordManager:
    """Factory function to create wake word manager from settings."""
    wake_mode = WakeMode(mode) if isinstance(mode, str) else mode
    config = WakeConfig(
        mode=wake_mode,
        wake_word=wake_word,
        **kwargs
    )
    return WakeWordManager(event_bus, config)