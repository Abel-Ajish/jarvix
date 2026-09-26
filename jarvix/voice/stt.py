"""Speech-to-Text module for jarvix using faster-whisper.

Wraps faster-whisper (tiny.en model, ~75MB) with silence detection.
Runs in thread pool (CPU-only, no CUDA).
Handles "model not downloaded" gracefully.
Publishes VoiceResult event with transcribed text.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

from jarvix.core.events import EventBus, VoiceResult, ErrorRaised
from jarvix.core.logger import get_logger
from jarvix.core.config import get_settings

_LOG = get_logger("jarvix.voice.stt")

# Suppress faster-whisper model download warnings in console
warnings.filterwarnings("ignore", category=UserWarning, module="faster_whisper")


@dataclass
class STTConfig:
    """Configuration for STT module."""
    model_size: str = "tiny.en"
    device: str = "cpu"
    compute_type: str = "int8"
    silence_timeout_ms: int = 800
    sample_rate: int = 16000
    language: str = "en"


class STTError(Exception):
    """Raised when STT encounters a fatal error."""
    pass


class STT:
    """Speech-to-Text using faster-whisper.

    Runs model inference in a thread pool to avoid blocking the event loop.
    Uses CPU-only inference (no CUDA) for portability.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: Optional[STTConfig] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self._event_bus = event_bus
        self._config = config or STTConfig()
        self._on_error = on_error

        self._model = None
        self._model_lock = threading.Lock()
        max_workers = min(4, (threading.active_count() + 1))
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="stt-")
        self._running = False
        self._listen_task: Optional[asyncio.Task] = None

        # Audio buffer for continuous recording
        self._audio_buffer = bytearray()
        self._last_speech_time = 0.0
        self._silence_frames = 0

    async def initialize(self) -> bool:
        """Load the Whisper model. Returns True on success."""
        try:
            _LOG.info("Loading faster-whisper model: %s", self._config.model_size)

            # Import here to catch import errors
            from faster_whisper import WhisperModel

            # Load model in thread pool to avoid blocking
            loop = asyncio.get_running_loop()
            self._model = await loop.run_in_executor(
                self._executor,
                self._load_model,
            )

            _LOG.info("STT model loaded successfully")
            return True

        except Exception as e:
            _LOG.error("Failed to load STT model: %s", e)
            self._publish_error(f"STT model load failed: {e}")
            if self._on_error:
                self._on_error(e)
            return False

    def _load_model(self):
        """Load the Whisper model (runs in thread pool)."""
        from faster_whisper import WhisperModel

        # Try to load model, handle missing model gracefully
        try:
            model = WhisperModel(
                self._config.model_size,
                device=self._config.device,
                compute_type=self._config.compute_type,
                download_root=str(Path.home() / ".cache" / "faster-whisper"),
            )
            return model
        except Exception as e:
            # Check if it's a model download error
            if "not found" in str(e).lower() or "download" in str(e).lower():
                raise STTError(
                    f"Model '{self._config.model_size}' not found. "
                    f"Run: python -c \"from faster_whisper import WhisperModel; WhisperModel('{self._config.model_size}')\" "
                    f"to download it first."
                ) from e
            raise

    async def transcribe_audio(self, audio_data: bytes) -> Optional[str]:
        """Transcribe audio bytes to text. Returns None if no speech detected."""
        if self._model is None:
            _LOG.warning("STT model not loaded")
            return None

        try:
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(
                self._executor,
                self._transcribe_sync,
                audio_data,
            )
            return text
        except Exception as e:
            _LOG.exception("Transcription failed")
            self._publish_error(f"Transcription failed: {e}")
            return None

    def _transcribe_sync(self, audio_data: bytes) -> Optional[str]:
        """Synchronous transcription (runs in thread pool)."""
        import numpy as np

        # Convert bytes to numpy array
        # Assuming 16-bit PCM at 16kHz
        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        # Check if audio has enough energy (simple VAD)
        if len(audio_np) == 0:
            return None

        rms = np.sqrt(np.mean(audio_np ** 2))
        if rms < 0.01:  # Very low energy threshold
            return None

        # Transcribe
        segments, info = self._model.transcribe(
            audio_np,
            language=self._config.language,
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=self._config.silence_timeout_ms),
        )

        # Combine segments
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        full_text = " ".join(text_parts).strip()
        return full_text if full_text else None

    def _publish_error(self, message: str) -> None:
        """Publish error to event bus."""
        self._event_bus.publish(ErrorRaised(message, component="voice.stt"))

    def shutdown(self) -> None:
        """Clean up resources."""
        self._running = False
        self._model = None
        self._executor.shutdown(wait=True, cancel_futures=True)
        _LOG.info("STT shut down")


class StreamingSTT:
    """Streaming STT with silence detection for continuous listening.

    Buffers audio and detects end-of-speech via silence timeout.
    Publishes VoiceResult when speech ends.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: Optional[STTConfig] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self._event_bus = event_bus
        self._config = config or STTConfig()
        self._on_error = on_error

        self._stt = STT(event_bus, config, on_error)
        self._running = False
        self._stream = None
        # Max ~30s of audio at 16kHz mono int16 (960KB) to prevent unbounded growth
        self._max_buffer_size = self._config.sample_rate * 30 * 2
        self._buffer = bytearray()
        self._last_voice_time = 0.0
        self._callback: Optional[Callable[[str], None]] = None

    async def start(self, callback: Optional[Callable[[str], None]] = None) -> bool:
        """Start streaming STT. Returns True on success."""
        if self._running:
            return True

        self._callback = callback

        # Initialize STT model
        if not await self._stt.initialize():
            return False

        self._running = True

        # Start audio stream
        try:
            import sounddevice as sd
            self._stream = sd.InputStream(
                samplerate=self._config.sample_rate,
                channels=1,
                dtype='int16',
                blocksize=512,
                callback=self._audio_callback,
            )
            self._stream.start()
            _LOG.info("Streaming STT started")
            return True
        except Exception as e:
            _LOG.error("Failed to start audio stream: %s", e)
            self._publish_error(f"Audio stream failed: {e}")
            if self._on_error:
                self._on_error(e)
            return False

    def _audio_callback(self, indata, frames, time_info, status):
        """Audio input callback (runs in sounddevice thread)."""
        if status:
            _LOG.warning("Audio callback status: %s", status)

        if not self._running:
            return

        # Add to buffer, dropping oldest data if it would exceed max size
        if len(self._buffer) + len(indata.tobytes()) > self._max_buffer_size:
            excess = len(self._buffer) + len(indata.tobytes()) - self._max_buffer_size
            self._buffer = bytearray(self._buffer[excess:])
        self._buffer.extend(indata.tobytes())

        # Simple energy-based voice activity detection
        import numpy as np
        audio_data = np.frombuffer(indata.tobytes(), dtype=np.int16).astype(np.float32) / 32768.0
        rms = np.sqrt(np.mean(audio_data ** 2)) if len(audio_data) > 0 else 0

        current_time = time.time()
        if rms > 0.015:  # Voice activity threshold
            self._last_voice_time = current_time

        # Check for silence timeout
        if self._last_voice_time > 0:
            silence_duration = (current_time - self._last_voice_time) * 1000
            if silence_duration >= self._config.silence_timeout_ms:
                # End of speech detected
                self._process_buffer()

    def _process_buffer(self) -> None:
        """Process accumulated audio buffer."""
        if len(self._buffer) < self._config.sample_rate * 0.5:  # Less than 0.5s
            self._buffer.clear()
            self._last_voice_time = 0.0
            return

        audio_data = bytes(self._buffer)
        self._buffer.clear()
        self._last_voice_time = 0.0

        # Transcribe in background, keeping a reference to capture exceptions
        self._pending_task = asyncio.create_task(self._transcribe_and_publish(audio_data))
        self._pending_task.add_done_callback(lambda t: self._handle_transcription_error(t))

    async def _transcribe_and_publish(self, audio_data: bytes) -> None:
        """Transcribe audio and publish result."""
        text = await self._stt.transcribe_audio(audio_data)
        if text:
            _LOG.info("STT result: %s", text)
            self._event_bus.publish(VoiceResult(text))
            if self._callback:
                try:
                    self._callback(text)
                except Exception:
                    _LOG.exception("STT callback failed")

    def stop(self) -> None:
        """Stop streaming STT."""
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._stt.shutdown()
        _LOG.info("Streaming STT stopped")

    def _publish_error(self, message: str) -> None:
        """Publish error to event bus."""
        self._event_bus.publish(ErrorRaised(message, component="voice.streaming_stt"))


# Convenience function for one-shot transcription
async def transcribe_once(event_bus: EventBus, audio_data: bytes, config: Optional[STTConfig] = None) -> Optional[str]:
    """One-shot transcription without streaming."""
    stt = STT(event_bus, config)
    try:
        if await stt.initialize():
            return await stt.transcribe_audio(audio_data)
    finally:
        stt.shutdown()
    return None