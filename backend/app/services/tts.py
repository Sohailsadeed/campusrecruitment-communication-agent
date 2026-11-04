"""Text-to-Speech (TTS) service: a local Kokoro voice with an Edge TTS fallback, disk cached.

One function hands the coach its voice, and its contract is what the rest of the app builds on: give
it the text of one line, get back a path to an audio file on disk, or ``None`` when nothing could be
spoken. The HR voice agent feeds that path to PyAV, which decodes it and resamples to the 48 kHz mono
PCM the LiveKit track publishes, so a change of engine never reaches the playback or interruption
code. ``cache_suffix`` exists because the agent speaks several different lines in one round; the
digest exists because the same line, in the same voice, is the same recording.

Kokoro (82M, Apache-licensed weights) is primary because it answers out loud on this machine: a
candidate's words do not cross a network to be spoken back. Edge TTS stays as the configured fallback
because Kokoro needs both a runtime in the venv and weights on disk, and a round should still be
able to speak when either is missing.

A generated file therefore arrives in one of two containers: 24 kHz mono 16-bit PCM WAV from Kokoro,
MP3 from Edge. Nothing converts either one here — the agent's resampler is the single place where the
sample rate changes, and the sentence the agent asked for is the sentence that gets spoken, so no
reply is ever buffered whole before it is heard.

Every attempt is logged by provider and failure classification, never by the text behind it: a
candidate's answer must not become a log line to reach a recording of it.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import logging
import os
import tempfile
import wave
from pathlib import Path
from typing import List, Optional, Tuple

from config import settings

logger = logging.getLogger(__name__)

_EDGE_TTS_AVAILABLE = False
try:
    import edge_tts
    _EDGE_TTS_AVAILABLE = True
except Exception:
    edge_tts = None


TTS_CACHE_DIR = settings.upload_dir / "tts"
TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_COACH_VOICE = settings.tts_edge_voice

# Kokoro emits 24 kHz mono float32; the agent republishes at 48 kHz. Recorded here so the WAV header
# and the cache identity name the same rate the audio was actually written at.
KOKORO_SAMPLE_RATE = 24000

_MIN_CACHED_BYTES = 1000
_MAX_SPOKEN_CHARS = 1500
_TRUNCATION_NOTE = "... Focus on these key adjustments."

# The only words that ever reach a log line beside a provider name.
FAILURE_CLASSIFICATIONS = ("unavailable", "init_failed", "generation_failed", "write_failed")


class TtsFailure(RuntimeError):
    """One provider's attempt to speak a line failed.

    The classification says what kind of failure it was, which is what an operator needs in order to
    fix a config; the detail is an exception name or a byte count, never the spoken text.
    """

    def __init__(self, classification: str, detail: str = "") -> None:
        if classification not in FAILURE_CLASSIFICATIONS:
            raise ValueError(f"unknown TTS failure classification {classification!r}")
        super().__init__(f"{classification}: {detail}" if detail else classification)
        self.classification = classification
        self.detail = detail


class TtsProvider:
    """One engine that can turn a line of text into one audio file."""

    name = ""
    extension = ""

    def available(self) -> bool:
        return False

    def voice_for(self, requested: str) -> str:
        """The voice this provider will actually speak.

        Kokoro and Edge share no voice vocabulary, so each provider translates the request; the
        cache key is built from the answer, not from what was asked for.
        """
        return requested

    def key_salt(self, voice: str) -> str:
        """Extra identity for the cache name: everything but the text and the voice that changes
        the audio. Empty keeps an existing cache entry's digest exactly as it was written."""
        return ""

    async def synthesize(self, clean_text: str, voice: str, target: Path) -> None:
        raise NotImplementedError(f"{self.name} speaks no audio")


class EdgeProvider(TtsProvider):
    """Microsoft neural voices over the network: the voice SpeakFlow has always used."""

    name = "edge"
    extension = ".mp3"

    def available(self) -> bool:
        return _EDGE_TTS_AVAILABLE

    async def synthesize(self, clean_text: str, voice: str, target: Path) -> None:
        if not self.available():
            raise TtsFailure("unavailable", "edge-tts is not installed")
        fd, tmp = _temp_target(target)
        os.close(fd)          # the writer opens by name; an open handle would block it on Windows
        try:
            try:
                await edge_tts.Communicate(clean_text, voice).save(str(tmp))
            except TtsFailure:
                raise
            except Exception as exc:
                raise TtsFailure("generation_failed", type(exc).__name__) from exc
            _publish(tmp, target)
            tmp = None
        finally:
            if tmp is not None:
                _unlink(tmp)


def _kokoro_runtime_installed() -> bool:
    """Is the Kokoro runtime importable? Asked without importing it: torch is heavy, and a service
    module that reached it at import would drag the whole backend down with it."""
    try:
        return importlib.util.find_spec("kokoro") is not None
    except (ImportError, ValueError):
        return False


class KokoroProvider(TtsProvider):
    """Kokoro-82M speaking locally through the ``kokoro`` runtime.

    The pipeline is heavy — torch weights, a G2P table, a voice pack — so it is built on the first
    line that needs it, in a worker thread, from the configured files. Nothing here downloads: if the
    weights are not on disk the provider reports itself unavailable and the fallback takes the line.
    """

    name = "kokoro"
    extension = ".wav"

    def __init__(self) -> None:
        self._pipeline = None
        self._build_lock = asyncio.Lock()
        # A failed build is remembered for the life of the process: re-trying it on every sentence
        # would make a candidate wait on a torch import between each barge-in check.
        self._init_failure: Optional[TtsFailure] = None

    def reset(self) -> None:
        """Forget the built pipeline and any remembered failure (tests, and reconfiguration)."""
        self._pipeline = None
        self._init_failure = None

    def available(self) -> bool:
        return (
            _kokoro_runtime_installed()
            and _is_readable_file(settings.tts_kokoro_model_path)
            and _is_readable_file(settings.tts_kokoro_config_path)
        )

    def voice_for(self, requested: str) -> str:
        if requested and requested != DEFAULT_COACH_VOICE:
            return requested          # a caller that named a voice meant it, for this provider too
        return settings.tts_kokoro_voice

    def key_salt(self, voice: str) -> str:
        return f"kokoro\n{voice}\n{settings.tts_kokoro_speed}\n{KOKORO_SAMPLE_RATE}"

    async def synthesize(self, clean_text: str, voice: str, target: Path) -> None:
        if not self.available():
            raise TtsFailure("unavailable", "the kokoro runtime or its model files are missing")
        if self._init_failure is not None:
            raise self._init_failure
        pipeline = await self._get_pipeline()
        try:
            # Generation, writing and publishing stay together in one worker thread: an interruption
            # cancels the wait, not the thread, and what the thread commits is a whole file.
            await asyncio.to_thread(self._speak_to_file, pipeline, clean_text, voice, target)
        except TtsFailure:
            raise
        except Exception as exc:
            raise TtsFailure("generation_failed", type(exc).__name__) from exc

    async def _get_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        async with self._build_lock:
            if self._pipeline is None:
                try:
                    self._pipeline = await asyncio.to_thread(_build_kokoro_pipeline)
                except TtsFailure as failure:
                    self._init_failure = failure
                    raise
            return self._pipeline

    def _speak_to_file(self, pipeline, text: str, voice: str, target: Path) -> None:
        fd, tmp = _temp_target(target)
        os.close(fd)
        try:
            samples = self._generate(pipeline, text, voice)
            _write_pcm_wav(samples, tmp, KOKORO_SAMPLE_RATE)
            _publish(tmp, target)
            tmp = None
        finally:
            if tmp is not None:
                _unlink(tmp)

    def _generate(self, pipeline, text: str, voice: str):
        """Speak exactly the line that was handed over.

        ``split_pattern=None`` is what keeps the agent in charge of sentence splitting: Kokoro would
        otherwise re-chunk the text on its own boundaries, and a reply would be synthesised in pieces
        nobody asked for. Kokoro may still return several prosody segments for one sentence, and they
        are concatenated in the order the model produced them.
        """
        try:
            results = list(pipeline(
                text,
                voice=self._voice_argument(voice),
                speed=settings.tts_kokoro_speed,
                split_pattern=None,
            ))
        except Exception as exc:
            raise TtsFailure("generation_failed", type(exc).__name__) from exc
        import numpy as np

        chunks = [_as_float32(result.audio) for result in results
                  if getattr(result, "audio", None) is not None]
        if not chunks:
            raise TtsFailure("generation_failed", "no audio segment was produced")
        return chunks[0] if len(chunks) == 1 else np.concatenate(chunks)

    def _voice_argument(self, voice: str) -> str:
        """Prefer a local voice pack, so speaking a line never depends on a hub lookup.

        The runtime resolves a bare voice name by repository id, which is how a pre-populated cache
        keeps working; a name with a pack in ``tts_kokoro_voices_dir`` is handed over as a file path
        instead, and the network is not consulted at all.
        """
        if voice.endswith(".pt"):
            return voice
        local = settings.tts_kokoro_voices_dir / f"{voice}.pt"
        return str(local) if _is_readable_file(local) else voice


def _build_kokoro_pipeline():
    """Construct the runtime from configured files. Blocking; always called off the event loop."""
    try:
        from kokoro import KModel, KPipeline
    except Exception as exc:
        raise TtsFailure("unavailable", f"kokoro import failed: {type(exc).__name__}") from exc
    try:
        model = KModel(
            repo_id=settings.tts_kokoro_repo_id,
            config=str(settings.tts_kokoro_config_path),
            model=str(settings.tts_kokoro_model_path),
        )
        return KPipeline(
            lang_code=settings.tts_kokoro_lang_code,
            repo_id=settings.tts_kokoro_repo_id,
            model=model,
            device=settings.tts_kokoro_device or None,
        )
    except Exception as exc:
        raise TtsFailure("init_failed", type(exc).__name__) from exc


def _as_float32(audio):
    """Kokoro hands back a tensor in some releases and an array in others; PCM needs float32."""
    detach = getattr(audio, "detach", None)
    if callable(detach):
        audio = detach().cpu()
    import numpy as np

    return np.asarray(audio, dtype=np.float32)


def _write_pcm_wav(samples, path: Path, sample_rate: int) -> None:
    """Mono 16-bit PCM WAV at the rate the model produced.

    The rate is written into the header rather than converted, because the agent's resampler is the
    one place audio rate changes in this pipeline. Clipping is deliberate: a float outside [-1, 1]
    wrapped into int16 becomes a loud click in a candidate's headphones.
    """
    import numpy as np

    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm.tobytes())


def _is_readable_file(path: Optional[Path]) -> bool:
    try:
        return path is not None and Path(path).is_file() and os.access(Path(path), os.R_OK)
    except OSError:
        return False


def _temp_target(target: Path) -> Tuple[int, Path]:
    """A unique name beside the cache entry, so a half-written line is never a readable file.

    Same directory because the publish is a rename, and a rename is only atomic within one volume.
    """
    fd, name = tempfile.mkstemp(dir=str(target.parent), prefix=f"{target.stem}.", suffix=".part")
    return fd, Path(name)


def _publish(tmp: Path, target: Path) -> None:
    """Commit a finished recording under its cache name — whole, or not at all."""
    try:
        size = tmp.stat().st_size
    except OSError as exc:
        raise TtsFailure("write_failed", type(exc).__name__) from exc
    if size < _MIN_CACHED_BYTES:
        raise TtsFailure("write_failed", f"generated file held {size} bytes")
    try:
        os.replace(tmp, target)
    except OSError as exc:
        raise TtsFailure("write_failed", type(exc).__name__) from exc


def _unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        # A temp file that outlived its attempt is worth one line: it is the only way a leaked
        # intermediate shows up at all, and it never carries audio anyone will be served.
        logger.warning("tts temporary file %s could not be removed: %s", path.name, type(exc).__name__)


_PROVIDERS = {"kokoro": KokoroProvider(), "edge": EdgeProvider()}


def _provider_chain() -> List[TtsProvider]:
    """The providers this configuration allows, in the order they get the line.

    Selection is configuration only: an installed runtime or a reachable service chooses nothing.
    """
    primary = _PROVIDERS[settings.tts_provider]
    chain = [primary]
    if settings.tts_fallback_enabled:
        fallback = _PROVIDERS[settings.tts_fallback_provider]
        if fallback is not primary:
            chain.append(fallback)
    return chain


def is_tts_available() -> bool:
    return any(provider.available() for provider in _provider_chain())


def _cache_digest(clean_text: str, voice: str, salt: str = "") -> str:
    """A short, stable identity for the audio a cache entry holds: that exact text, in that exact
    voice, in that exact engine. The session id and ``cache_suffix`` say *where* a line is spoken, not
    *what* is said, so without this digest a second round with a different answer would replay the
    first one's file.

    The salt is appended only when a provider has something to add. Edge's is empty, which leaves the
    preimage exactly what it was before Kokoro existed — every Edge recording already on disk stays
    addressable at the name it was written under, so a provider change cannot turn the whole cache
    into new network calls.
    """
    preimage = f"{voice}\n{clean_text}" + (f"\n{salt}" if salt else "")
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()[:12]


def _cache_file(provider: TtsProvider, session_id: int, clean_text: str, voice: str,
                safe_suffix: str) -> Path:
    return TTS_CACHE_DIR / (
        f"session_{session_id}_coach"
        f"{f'_{safe_suffix}' if safe_suffix else ''}"
        f"_{_cache_digest(clean_text, voice, provider.key_salt(voice))}{provider.extension}"
    )


async def synthesize_feedback_audio(
    session_id: int,
    text: str,
    voice: str = DEFAULT_COACH_VOICE,
    cache_suffix: str = "",
) -> Optional[Path]:
    """Synthesize one line of coach feedback to a file on disk, with caching and fallback.

    Returns the path, or ``None`` when no provider in the configured chain could speak the line — the
    caller's existing signal that this sentence has no audio, which is how the voice agent counts an
    unvoiced sentence and refuses to spend a question the candidate never heard.

    ``cache_suffix`` names a separate cache entry for the same session. The voice agent speaks several
    different texts in one round (a greeting, then each reply), and the cache key is the session —
    without a suffix every later line would return the first one's recording.

    Each provider gets its own attempt at the line, and a line is spoken by one provider from text to
    bytes: a failure partway through leaves no cache entry behind, so falling back for that sentence
    cannot mix two renderings of it. Because generation is per sentence, an engine that dies on the
    third sentence loses only the third sentence.
    """
    if not text or not text.strip():
        return None

    clean_text = text.strip()
    # Limit length to prevent giant generation if LLM produced huge text
    if len(clean_text) > _MAX_SPOKEN_CHARS:
        clean_text = clean_text[:_MAX_SPOKEN_CHARS] + _TRUNCATION_NOTE

    safe_suffix = "".join(c for c in cache_suffix if c.isalnum() or c in ("-", "_"))
    chain = _provider_chain()
    for index, provider in enumerate(chain):
        spoken_voice = provider.voice_for(voice)
        cache_file = _cache_file(provider, session_id, clean_text, spoken_voice, safe_suffix)
        if _is_readable_file(cache_file) and cache_file.stat().st_size > _MIN_CACHED_BYTES:
            return cache_file
        try:
            await provider.synthesize(clean_text, spoken_voice, cache_file)
            logger.info("tts session=%s provider=%s result=spoken", session_id, provider.name)
            return cache_file
        except TtsFailure as failure:
            nxt = chain[index + 1].name if index + 1 < len(chain) else "none"
            logger.warning(
                "tts session=%s provider=%s classification=%s detail=%s next_provider=%s "
                "fallback=%s",
                session_id, provider.name, failure.classification, failure.detail or "n/a", nxt,
                settings.tts_fallback_enabled)
    return None
