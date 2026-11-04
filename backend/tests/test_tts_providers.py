"""Phase 07 — the coach's voice: Kokoro primary, Edge TTS fallback, and the contract around both.

Everything here drives `app/services/tts.py` with stand-ins for the two runtimes: no weights, no
network, no LiveKit server, no candidate data. What is under test is the seam the rest of the app
depends on — `synthesize_feedback_audio(session_id, text, voice, cache_suffix) -> Optional[Path]` —
because that one function decides whether a barge-in, a half-written file or a dead engine reaches a
candidate's headphones.

Two properties are worth naming before the tests that prove them:

* A line is committed whole or not at all. Generation writes beside the cache name and renames, so
  there is no moment in which a reader can find a truncated recording, and every failure path leaves
  no intermediate behind.
* Nothing about the spoken text reaches a log. The cache filename is a digest of that text, so it is
  not logged either.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
import wave
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

np = pytest.importorskip("numpy")

from app.services import tts  # noqa: E402  (the module under test; conftest put backend/ on sys.path)

LINE = "Tell me about a time you disagreed with a teammate."
EDGE_VOICE = "en-US-ChristopherNeural"
KOKORO_VOICE = "af_heart"

FAKE_WAV_SAMPLES = 1200        # frames of audio in each generated segment
# Anything a reader can call a recording: the publish gate is a size, and both engines clear it.
FAKE_MP3 = b"\xff\xfb\x90\x00" + b"edge-tts-payload" * 200


# ---------------------------------------------------------------------------
# Fixture plumbing: the cache moves to temporary space, and the chain is pinned per test.
# ---------------------------------------------------------------------------
@pytest.fixture
def cache_dir(monkeypatch, tmp_path) -> Path:
    root = tmp_path / "tts-cache"
    root.mkdir()
    monkeypatch.setattr(tts, "TTS_CACHE_DIR", root)
    return root


@pytest.fixture
def chain(cache_dir, monkeypatch) -> List["FakeEngine"]:
    """An ordered pair of stand-in providers, installed in place of the real ones."""
    primary = FakeEngine("kokoro", ".wav", voice_map={EDGE_VOICE: KOKORO_VOICE}, salt="kokoro")
    fallback = FakeEngine("edge", ".mp3")
    monkeypatch.setattr(tts.settings, "tts_provider", "kokoro")
    monkeypatch.setattr(tts.settings, "tts_fallback_provider", "edge")
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", True)
    monkeypatch.setitem(tts._PROVIDERS, "kokoro", primary)
    monkeypatch.setitem(tts._PROVIDERS, "edge", fallback)
    return [primary, fallback]


def synthesize(session_id: int = 7, text: str = LINE, voice: str = EDGE_VOICE,
               cache_suffix: str = "") -> Optional[Path]:
    return asyncio.run(tts.synthesize_feedback_audio(session_id, text, voice, cache_suffix))


async def _wait_until(condition, complaint: str, timeout: float = 5.0) -> None:
    """Poll from the event loop: a worker thread's progress is the only clock a cancellation test has."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        await asyncio.sleep(0.02)
    pytest.fail(complaint)


def seeded(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


class FakeEngine:
    """A provider that records its calls and either writes a file or fails in a named way."""

    def __init__(self, name: str, extension: str, *, voice_map=None, salt: str = "",
                 error: Optional[Exception] = None, speaks: bool = True) -> None:
        self.name = name
        self.extension = extension
        self.voice_map = dict(voice_map or {})
        self.salt = salt
        self.error = error
        self.speaks = speaks
        self.calls: List[Tuple[str, str, Path]] = []

    def available(self) -> bool:
        return self.error is None and self.speaks

    def voice_for(self, requested: str) -> str:
        return self.voice_map.get(requested, requested)

    def key_salt(self, voice: str) -> str:
        return f"{self.salt}\n{voice}" if self.salt else ""

    async def synthesize(self, clean_text: str, voice: str, target: Path) -> None:
        self.calls.append((clean_text, voice, target))
        if self.error is not None:
            raise self.error
        if not self.speaks:
            raise tts.TtsFailure("generation_failed", "the fake declined to speak")
        target.write_bytes(FAKE_MP3)


class FakeEdgeTts:
    """Stand-in for the `edge_tts` package, with hooks to drive the real temp-file code.

    `gate` blocks `save` (an attempt interrupted mid-stream), `error` makes it raise, and
    `partial_on_error` reproduces the hazard the previous implementation had: bytes on disk left by an
    attempt that never finished.
    """

    def __init__(self, *, payload: bytes = FAKE_MP3, error: Optional[Exception] = None,
                 gate: Optional[asyncio.Event] = None, partial_on_error: bool = False) -> None:
        self.payload = payload
        self.error = error
        self.gate = gate
        self.partial_on_error = partial_on_error
        self.saved: List[Tuple[str, str, Path]] = []

    def Communicate(self, text: str, voice: str) -> "_FakeCommunicate":
        return _FakeCommunicate(self, text, voice)


class _FakeCommunicate:
    def __init__(self, module: FakeEdgeTts, text: str, voice: str) -> None:
        self.module, self.text, self.voice = module, text, voice

    async def save(self, path: str) -> None:
        target = Path(path)
        self.module.saved.append((self.text, self.voice, target))
        if self.module.gate is not None:
            await asyncio.wait_for(self.module.gate.wait(), timeout=5)
        if self.module.error is not None:
            if self.module.partial_on_error:
                target.write_bytes(b"\xff" * 5)
            raise self.module.error
        target.write_bytes(self.module.payload)


class FakeTensor:
    """The shape Kokoro's own releases hand back: a tensor with detach()/cpu() on it."""

    def __init__(self, values) -> None:
        self.values = values

    def detach(self) -> "FakeTensor":
        return self

    def cpu(self) -> "FakeArray":
        return FakeArray(self.values)


class FakeArray:
    def __init__(self, values) -> None:
        self.values = np.asarray(values, dtype=np.float32)

    def __array__(self, dtype=None):
        return self.values if dtype is None else self.values.astype(dtype)


class FakeResult:
    """One `KPipeline` segment. Only `audio` matters to this service; None means "no audio"."""

    def __init__(self, audio) -> None:
        self.graphemes = "some words"
        self.phonemes = "sAm w3:dz"
        self.audio = audio


class RecordingKokoroPipeline:
    """Stand-in for `KPipeline`: records how it was asked to speak, then yields fake segments.

    Each segment is louder than the one before it, so a test can tell whether the pieces were put back
    in the order the model produced them.
    """

    def __init__(self, *, segments: int = 1, amplitude: float = 0.4,
                 error: Optional[Exception] = None) -> None:
        self.segments = segments
        self.amplitude = amplitude
        self.error = error
        self.calls: List[dict] = []

    def __call__(self, text: str, **kwargs):
        self.calls.append(dict(text=text, **kwargs))
        if self.error is not None:
            raise self.error
        for index in range(self.segments):
            level = self.amplitude * (index + 1) / self.segments
            yield FakeResult(FakeTensor(np.full(FAKE_WAV_SAMPLES, level, np.float32)))


class BlockedKokoroPipeline:
    """A pipeline that stays inside generation until the test releases it, as real inference does.

    Once released it stays released, so the same object can also speak the sentences that come after
    the interruption — which is what a barge-in actually needs.
    """

    def __init__(self, *, gate: threading.Event, samples: int = FAKE_WAV_SAMPLES) -> None:
        self.gate = gate
        self.samples = samples
        self.calls: List[dict] = []

    def __call__(self, text: str, **kwargs):
        self.gate.wait(5)
        self.calls.append(dict(text=text, **kwargs))
        yield FakeResult(FakeTensor(
            np.full(self.samples, self.amplitude(len(self.calls)), np.float32)))

    def amplitude(self, index: int) -> float:
        return 0.3 + 0.1 * index


def kokoro_provider(monkeypatch, files: Path, pipeline, *, runtime_installed: bool = True,
                    voice_pack: bool = True) -> tts.KokoroProvider:
    """A real KokoroProvider with a configured-but-fake runtime, weights and voice pack.

    Only the import of `kokoro` and the construction of the pipeline are replaced. Availability,
    generation, WAV writing, publishing and cleanup run exactly as they do in production.
    """
    weights = seeded(files / "kokoro-v1_0.pth", b"fake-checkpoint-bytes" * 200)
    config = seeded(files / "config.json", b'{"vocab": {"a": 1}}' + b" " * 2000)
    voices = files / "voices"
    voices.mkdir(parents=True, exist_ok=True)
    if voice_pack:
        seeded(voices / f"{KOKORO_VOICE}.pt", b"fake-voice-pack" * 200)
    monkeypatch.setattr(tts, "_kokoro_runtime_installed", lambda: runtime_installed)
    monkeypatch.setattr(tts.settings, "tts_kokoro_model_path", weights)
    monkeypatch.setattr(tts.settings, "tts_kokoro_config_path", config)
    monkeypatch.setattr(tts.settings, "tts_kokoro_voices_dir", voices)
    monkeypatch.setattr(tts.settings, "tts_kokoro_lang_code", "a")
    monkeypatch.setattr(tts.settings, "tts_kokoro_voice", KOKORO_VOICE)
    monkeypatch.setattr(tts.settings, "tts_kokoro_speed", 1.0)
    monkeypatch.setattr(tts.settings, "tts_provider", "kokoro")
    monkeypatch.setattr(tts.settings, "tts_fallback_provider", "edge")

    provider = tts.KokoroProvider()

    async def _already_built():
        return pipeline

    monkeypatch.setattr(provider, "_get_pipeline", _already_built)
    monkeypatch.setitem(tts._PROVIDERS, "kokoro", provider)
    return provider


def use_edge(monkeypatch, fake: FakeEdgeTts) -> FakeEdgeTts:
    """Install a fake `edge_tts` and make Edge the only provider the chain will try."""
    monkeypatch.setattr(tts, "edge_tts", fake)
    monkeypatch.setattr(tts, "_EDGE_TTS_AVAILABLE", True)
    monkeypatch.setattr(tts.settings, "tts_provider", "edge")
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)
    monkeypatch.setattr(tts.settings, "tts_edge_voice", EDGE_VOICE)
    return fake


# ---------------------------------------------------------------------------
# §6.1 provider selection: configuration chooses the engine, and nothing else does.
# ---------------------------------------------------------------------------
def test_configured_provider_gets_the_line_and_the_fallback_stays_idle(chain, cache_dir):
    primary, fallback = chain

    path = synthesize()

    assert path is not None and path.parent == cache_dir
    assert path.suffix == ".wav", "Kokoro's audio, not the fallback's"
    assert primary.calls and primary.calls[0][1] == KOKORO_VOICE
    assert fallback.calls == [], "a working primary never hands the line to Edge"


def test_the_other_provider_is_chosen_when_configuration_says_so(chain, cache_dir, monkeypatch):
    primary, fallback = chain
    monkeypatch.setattr(tts.settings, "tts_provider", "edge")
    monkeypatch.setattr(tts.settings, "tts_fallback_provider", "kokoro")

    path = synthesize()

    assert path.suffix == ".mp3"
    assert fallback.calls and primary.calls == []


def test_provider_names_are_the_only_selectors_and_bad_ones_are_refused():
    from pydantic import ValidationError

    from config import Settings

    defaults = Settings(_env_file=None)
    assert (defaults.tts_provider, defaults.tts_fallback_provider) == ("kokoro", "edge")
    assert defaults.tts_fallback_enabled is True

    for invalid in (
        {"tts_provider": "openai"},
        {"tts_fallback_provider": "s3"},
        {"tts_kokoro_speed": 4.0},
        {"tts_kokoro_lang_code": "xx"},
        {"tts_kokoro_device": "mps"},
        {"tts_provider": "edge", "tts_fallback_provider": "edge"},
    ):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **invalid)


# ---------------------------------------------------------------------------
# §6.2 & §6.3 fallback: unavailable, init failure and mid-generation failure all reach Edge.
# ---------------------------------------------------------------------------
def test_missing_kokoro_runtime_is_reported_and_edge_speaks(chain, cache_dir, caplog):
    primary, fallback = chain
    primary.error = tts.TtsFailure("unavailable", "the kokoro runtime or model files are missing")

    with caplog.at_level(logging.WARNING, logger="app.services.tts"):
        path = synthesize()

    assert path is not None and path.suffix == ".mp3"
    assert len(primary.calls) == 1, "the configured provider is attempted before anything else"
    assert len(fallback.calls) == 1
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "provider=kokoro" in logged and "classification=unavailable" in logged
    assert "next_provider=edge" in logged


def test_initialisation_failure_is_remembered_instead_of_retried_every_line(cache_dir, monkeypatch):
    """A broken model directory must not make a candidate wait on another torch import per sentence."""
    builds: List[int] = []

    def _explode():
        builds.append(1)
        raise tts.TtsFailure("init_failed", "RuntimeError")

    monkeypatch.setattr(tts, "_build_kokoro_pipeline", _explode)
    fake_edge = use_edge(monkeypatch, FakeEdgeTts())
    monkeypatch.setattr(tts.settings, "tts_kokoro_model_path",
                        seeded(cache_dir / "weights.pth", b"x" * 2000))
    monkeypatch.setattr(tts.settings, "tts_kokoro_config_path",
                        seeded(cache_dir / "config.json", b"x" * 2000))
    monkeypatch.setattr(tts, "_kokoro_runtime_installed", lambda: True)
    monkeypatch.setattr(tts.settings, "tts_provider", "kokoro")
    monkeypatch.setattr(tts.settings, "tts_fallback_provider", "edge")
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", True)
    monkeypatch.setitem(tts._PROVIDERS, "kokoro", tts.KokoroProvider())

    first = synthesize(cache_suffix="reply_1_0")
    second = synthesize(cache_suffix="reply_1_1", text="And what did you do next?")

    assert first is not None and second is not None
    assert first.suffix == ".mp3"
    assert builds == [1], "the remembered init failure short-circuits the retry"
    assert len(fake_edge.saved) == 2


def test_kokoro_failing_on_the_second_sentence_loses_only_that_sentence(cache_dir, monkeypatch):
    """§3.3: an engine failure in the middle of a reply must not corrupt playback state.

    Sentences arrive one at a time, exactly as the agent's stream hands them over, so the first keeps
    its Kokoro recording and only the failing one is re-spoken by Edge. Both are complete, readable
    files the moment they are returned — which is the guarantee the agent's queue depends on.
    """
    pipeline = RecordingKokoroPipeline()
    kokoro_provider(monkeypatch, cache_dir.parent / "kokoro-files", pipeline)
    fake_edge = FakeEdgeTts()
    monkeypatch.setattr(tts, "edge_tts", fake_edge)
    monkeypatch.setattr(tts, "_EDGE_TTS_AVAILABLE", True)
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", True)

    spoken: List[Path] = []
    for index, text in enumerate(["What did you do yourself?", "What changed after that?"]):
        if index == 1:
            pipeline.error = RuntimeError("the fake runtime died mid-sentence")
        spoken.append(synthesize(cache_suffix=f"reply_1_{index}", text=text))

    kokoro_line, edge_line = spoken
    assert kokoro_line is not None and kokoro_line.suffix == ".wav"
    assert edge_line is not None and edge_line.suffix == ".mp3"
    assert kokoro_line != edge_line
    assert kokoro_line.read_bytes()[:4] == b"RIFF"
    assert edge_line.read_bytes() == FAKE_MP3
    assert len(fake_edge.saved) == 1, "Edge was asked for the failed sentence only"


def test_both_providers_failing_returns_none_without_inventing_audio(chain, cache_dir):
    primary, fallback = chain
    primary.error = tts.TtsFailure("generation_failed", "RuntimeError")
    fallback.error = tts.TtsFailure("unavailable", "edge-tts is not installed")

    assert synthesize() is None
    assert list(cache_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# §6.4 fallback disabled: report the failure, do not silently switch engines.
# ---------------------------------------------------------------------------
def test_fallback_disabled_refuses_the_line_and_names_no_other_provider(chain, cache_dir, caplog,
                                                                       monkeypatch):
    primary, fallback = chain
    primary.error = tts.TtsFailure("unavailable", "the kokoro runtime or model files are missing")
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)

    with caplog.at_level(logging.WARNING, logger="app.services.tts"):
        assert synthesize() is None

    assert fallback.calls == [], "the disabled fallback was used anyway"
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "next_provider=none" in logged and "fallback=False" in logged
    assert "classification=unavailable" in logged


def test_a_provider_that_is_not_the_configured_fallback_is_never_tried(cache_dir, monkeypatch):
    """The only silent switch allowed is to the provider the configuration names."""
    monkeypatch.setattr(tts.settings, "tts_provider", "kokoro")
    monkeypatch.setattr(tts.settings, "tts_fallback_provider", "edge")
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", True)
    monkeypatch.setitem(tts._PROVIDERS, "kokoro", FakeEngine(
        "kokoro", ".wav", error=tts.TtsFailure("unavailable", "no runtime")))
    monkeypatch.setitem(tts._PROVIDERS, "edge", FakeEngine(
        "edge", ".mp3", error=tts.TtsFailure("unavailable", "edge-tts is not installed")))
    monkeypatch.setitem(tts._PROVIDERS, "openai", FakeEngine("openai", ".mp3"))

    assert synthesize() is None
    assert tts._PROVIDERS["openai"].calls == []


# ---------------------------------------------------------------------------
# §6.5 format and sample rate: 24 kHz mono 16-bit PCM, converted nowhere but the agent.
# ---------------------------------------------------------------------------
def test_kokoro_audio_is_mono_16_bit_pcm_at_the_rate_the_model_produced(cache_dir, monkeypatch):
    pipeline = RecordingKokoroPipeline()
    provider = kokoro_provider(monkeypatch, cache_dir.parent / "files", pipeline)
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)

    path = synthesize(cache_suffix="reply_1_0")

    assert provider.available() is True
    assert path is not None and path.suffix == ".wav"
    with wave.open(str(path)) as clip:
        assert clip.getnchannels() == 1
        assert clip.getsampwidth() == 2
        assert clip.getframerate() == tts.KOKORO_SAMPLE_RATE == 24000
        assert clip.getnframes() == FAKE_WAV_SAMPLES, \
            "no resampling happened here — the agent's AudioResampler is the only conversion"
    assert pipeline.calls[0]["split_pattern"] is None, \
        "the agent splits sentences; Kokoro must not re-chunk them on its own boundaries"
    assert pipeline.calls[0]["speed"] == 1.0


def test_two_segments_of_one_sentence_keep_the_order_they_were_generated_in(cache_dir, monkeypatch):
    pipeline = RecordingKokoroPipeline(segments=2, amplitude=0.8)
    kokoro_provider(monkeypatch, cache_dir.parent / "files", pipeline)
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)

    path = synthesize(cache_suffix="greeting")

    with wave.open(str(path)) as clip:
        assert clip.getnframes() == 2 * FAKE_WAV_SAMPLES
        frames = np.frombuffer(clip.readframes(clip.getnframes()), dtype="<i2")
    half = len(frames) // 2
    assert frames[:half].mean() < frames[half:].mean(), \
        "the louder second segment arrived first: concatenation is out of order"


def test_a_value_outside_the_float_range_is_clipped_not_wrapped(cache_dir, monkeypatch):
    """An int16 wrap is a loud click in a candidate's headphones, so peaks are clipped first."""
    pipeline = RecordingKokoroPipeline(amplitude=4.0)
    kokoro_provider(monkeypatch, cache_dir.parent / "files", pipeline)
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)

    path = synthesize(cache_suffix="reply_1_0")

    with wave.open(str(path)) as clip:
        frames = np.frombuffer(clip.readframes(clip.getnframes()), dtype="<i2")
    assert frames.max() <= 32767 and frames.min() >= -32768
    assert frames.max() > 30000, "clipping never turned the signal into silence"


def test_a_segment_with_no_audio_is_a_generation_failure_not_silence(cache_dir, monkeypatch):
    class SilentPipeline:
        def __init__(self):
            self.calls: List[dict] = []

        def __call__(self, text, **kwargs):
            self.calls.append(dict(text=text, **kwargs))
            yield FakeResult(None)

    kokoro_provider(monkeypatch, cache_dir.parent / "files", SilentPipeline())
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)

    assert synthesize() is None
    assert list(cache_dir.iterdir()) == []


def test_kokoro_is_unavailable_without_its_weights_or_its_runtime(cache_dir, monkeypatch):
    monkeypatch.setattr(tts.settings, "tts_kokoro_model_path", cache_dir / "absent.pth")
    monkeypatch.setattr(tts.settings, "tts_kokoro_config_path", cache_dir / "absent.json")
    monkeypatch.setattr(tts, "_kokoro_runtime_installed", lambda: True)
    assert tts.KokoroProvider().available() is False

    weights = seeded(cache_dir / "weights.pth", b"x" * 2000)
    config = seeded(cache_dir / "config.json", b"x" * 2000)
    monkeypatch.setattr(tts.settings, "tts_kokoro_model_path", weights)
    monkeypatch.setattr(tts.settings, "tts_kokoro_config_path", config)
    assert tts.KokoroProvider().available() is True

    monkeypatch.setattr(tts, "_kokoro_runtime_installed", lambda: False)
    assert tts.KokoroProvider().available() is False


# ---------------------------------------------------------------------------
# §6.6 sentence-level generation: one cache entry per sentence, in order, reusable.
# ---------------------------------------------------------------------------
def test_each_sentence_of_a_reply_gets_its_own_entry_in_order(chain, cache_dir):
    primary, _ = chain
    sentences = ["Thanks for that.", "What did you do yourself?", "And what came of it?"]
    suffixes = [f"reply_{turn}_{index}" for turn in (1, 2) for index in range(3)]

    paths = [synthesize(cache_suffix=suffix, text=text)
             for suffix, text in zip(suffixes, sentences * 2)]

    assert all(path is not None for path in paths)
    assert len(set(paths)) == len(paths), "six sentences, six recordings"
    assert [path.name.split("session_7_coach_")[1].rsplit("_", 1)[0] for path in paths] == suffixes
    assert [text for text, _, _ in primary.calls] == sentences * 2


def test_the_same_line_in_the_same_voice_is_synthesised_once(chain, cache_dir):
    primary, _ = chain

    first = synthesize(cache_suffix="greeting")
    second = synthesize(cache_suffix="greeting")

    assert first == second
    assert len(primary.calls) == 1, "a cached line is not re-spoken"


def test_a_different_engine_gets_a_different_entry_for_the_same_text(chain, cache_dir, monkeypatch):
    primary, fallback = chain

    kokoro_path = synthesize()
    monkeypatch.setattr(tts.settings, "tts_provider", "edge")
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)
    edge_path = synthesize()

    assert kokoro_path != edge_path
    assert kokoro_path.suffix == ".wav" and edge_path.suffix == ".mp3"


def test_speech_speed_is_part_of_the_identity_of_a_kokoro_recording(monkeypatch):
    """The same sentence at two speeds is two recordings; a cache must not replay the slower one."""
    provider = tts.KokoroProvider()

    def name_at(speed: float) -> str:
        monkeypatch.setattr(tts.settings, "tts_kokoro_speed", speed)
        return tts._cache_file(provider, 7, LINE, KOKORO_VOICE, "reply_1_0").name

    assert name_at(0.9) != name_at(1.4)
    assert name_at(1.4).endswith(".wav")


def test_a_poisoned_cache_entry_is_not_returned_as_audio(cache_dir, monkeypatch):
    """A 400-byte file at the cache name is a failed write, not a recording."""
    provider = FakeEngine("kokoro", ".wav", voice_map={EDGE_VOICE: KOKORO_VOICE}, salt="kokoro")
    monkeypatch.setattr(tts.settings, "tts_provider", "kokoro")
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)
    monkeypatch.setitem(tts._PROVIDERS, "kokoro", provider)
    expected = tts._cache_file(provider, 7, LINE, KOKORO_VOICE, "reply_1_0")
    seeded(expected, b"\xff" * 400)

    path = synthesize(cache_suffix="reply_1_0")

    assert path == expected
    assert len(provider.calls) == 1, "a truncated entry was served as though it were the answer"


# ---------------------------------------------------------------------------
# §6.7 & §6.8 cancellation: an interrupted line is never half-playable, and never stale.
# ---------------------------------------------------------------------------
def test_cancelling_kokoro_mid_generation_returns_no_path_and_commits_no_recording(
        cache_dir, monkeypatch):
    """The agent cancels this await on a barge-in, and a cancelled await must yield nothing to play."""
    gate = threading.Event()
    pipeline = BlockedKokoroPipeline(gate=gate)
    kokoro_provider(monkeypatch, cache_dir.parent / "files", pipeline)
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)

    async def scenario():
        task = asyncio.create_task(
            tts.synthesize_feedback_audio(7, LINE, EDGE_VOICE, "reply_1_0"))
        # The temp file exists as soon as the attempt starts; generation has not begun, so nothing
        # has been published and the worker thread is still parked inside the model.
        await _wait_until(lambda: list(cache_dir.glob("*.part")),
                          "the attempt never created its temp file")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            pytest.fail("a cancelled synthesis returned a path")
        listing = sorted(p.name for p in cache_dir.iterdir())
        gate.set()
        await _wait_until(lambda: list(cache_dir.glob("*.wav")),
                          "the released thread never published")
        return listing

    at_cancellation = asyncio.run(scenario())

    assert not [name for name in at_cancellation if name.endswith(".wav")], \
        "a cancelled line was committed as a recording"
    assert len([name for name in at_cancellation if name.endswith(".part")]) == 1


def test_an_interrupted_line_finishes_whole_or_not_at_all(cache_dir, monkeypatch):
    """The generation thread cannot be interrupted, so what it commits has to be safe.

    It publishes one complete recording under a content-addressed name. Nothing plays it — the agent's
    queue only ever receives what an uncancelled await returned — no intermediate is left behind, and
    the sentences after the interruption are spoken normally, because a cancelled line leaves no
    provider state behind.
    """
    gate = threading.Event()
    pipeline = BlockedKokoroPipeline(gate=gate)
    kokoro_provider(monkeypatch, cache_dir.parent / "files", pipeline)
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)

    async def scenario():
        task = asyncio.create_task(
            tts.synthesize_feedback_audio(7, LINE, EDGE_VOICE, "reply_1_0"))
        await _wait_until(lambda: list(cache_dir.glob("*.part")),
                          "the attempt never created its temp file")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert list(cache_dir.glob("*.wav")) == [], "committed while the caller was being cancelled"
        gate.set()
        await _wait_until(lambda: list(cache_dir.glob("*.wav")),
                          "the released thread never published")
        return sorted(p.name for p in cache_dir.iterdir())

    names = asyncio.run(scenario())

    committed = [name for name in names if name.endswith(".wav")]
    assert len(committed) == 1, names
    assert not [name for name in names if name.endswith(".part")], \
        "an intermediate outlived the attempt that made it"
    with wave.open(str(cache_dir / committed[0])) as clip:
        assert clip.getnframes() == FAKE_WAV_SAMPLES

    following = synthesize(cache_suffix="reply_1_1", text="What happened after that?")
    assert following is not None and following.suffix == ".wav"
    assert following.name != committed[0]
    assert len(pipeline.calls) == 2


def test_an_interruption_mid_edge_write_leaves_no_recording_at_all(cache_dir, monkeypatch):
    gate = asyncio.Event()
    fake = FakeEdgeTts(gate=gate)
    use_edge(monkeypatch, fake)

    async def scenario():
        task = asyncio.create_task(
            tts.synthesize_feedback_audio(7, LINE, EDGE_VOICE, "reply_1_0"))
        await _wait_until(lambda: fake.saved, "Edge never started writing")
        await _wait_until(lambda: list(cache_dir.glob("*.part")),
                          "the attempt never created its temp file")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        gate.set()
        await asyncio.sleep(0.05)
        return sorted(p.name for p in cache_dir.iterdir())

    assert asyncio.run(scenario()) == [], "a cancelled remote write left bytes behind"


# ---------------------------------------------------------------------------
# §6.9 temporary resources: every failure path cleans up, and nothing partial is ever published.
# ---------------------------------------------------------------------------
def test_a_failed_edge_write_is_cleaned_up(cache_dir, monkeypatch):
    fake = FakeEdgeTts(error=ConnectionError("the network went away"), partial_on_error=True)
    use_edge(monkeypatch, fake)

    assert synthesize() is None
    assert list(cache_dir.iterdir()) == [], "a partial file survived the failure"


def test_an_empty_recording_is_never_published(cache_dir, monkeypatch):
    """A provider that produces a file with no real audio in it must not become a cache hit."""
    fake = FakeEdgeTts(payload=b"\xff" * 8)
    use_edge(monkeypatch, fake)

    assert synthesize() is None
    assert list(cache_dir.iterdir()) == []


def test_a_failing_kokoro_generation_cleans_up_its_temporary(cache_dir, monkeypatch):
    pipeline = RecordingKokoroPipeline(error=RuntimeError("phonemization failed"))
    kokoro_provider(monkeypatch, cache_dir.parent / "files", pipeline)
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)

    assert synthesize() is None
    assert list(cache_dir.iterdir()) == []


def test_a_temporary_that_cannot_be_removed_is_reported_not_swallowed(cache_dir, caplog):
    """A leftover intermediate is the only way a leak shows up, so it gets a line rather than a pass.

    A directory is the cheapest unreadable-by-permission target on every platform: `unlink` on one is
    an OSError, exactly like a file another process still holds open.
    """
    with caplog.at_level(logging.WARNING, logger="app.services.tts"):
        tts._unlink(cache_dir)

    assert any(cache_dir.name in record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------------------
# §6.10 Edge compatibility: the pre-migration contract, unchanged.
# ---------------------------------------------------------------------------
def test_edge_cache_names_are_exactly_what_they_were_before_kokoro(cache_dir, monkeypatch):
    """An engine switch must not invalidate one existing recording, or the upgrade re-fetches the
    whole cache from a remote service."""
    digest = hashlib.sha256(f"{EDGE_VOICE}\n{LINE}".encode("utf-8")).hexdigest()[:12]
    seeded(cache_dir / f"session_12_coach_greeting_{digest}.mp3", FAKE_MP3)
    fake = use_edge(monkeypatch, FakeEdgeTts())

    path = synthesize(session_id=12, cache_suffix="greeting")

    assert path.name == f"session_12_coach_greeting_{digest}.mp3"
    assert path.read_bytes() == FAKE_MP3
    assert fake.saved == [], "a pre-existing Edge recording was regenerated and re-fetched"


def test_a_fresh_edge_line_still_uses_the_old_digest_formula(cache_dir, monkeypatch):
    use_edge(monkeypatch, FakeEdgeTts())

    path = synthesize(session_id=12, cache_suffix="greeting")

    digest = hashlib.sha256(f"{EDGE_VOICE}\n{LINE}".encode("utf-8")).hexdigest()[:12]
    assert path.name == f"session_12_coach_greeting_{digest}.mp3"
    assert path.suffix == ".mp3"


def test_edge_tts_absent_and_no_fallback_means_no_voice(cache_dir, monkeypatch):
    monkeypatch.setattr(tts, "edge_tts", None)
    monkeypatch.setattr(tts, "_EDGE_TTS_AVAILABLE", False)
    monkeypatch.setattr(tts.settings, "tts_provider", "edge")
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)

    assert synthesize() is None
    assert tts.is_tts_available() is False


def test_unvoiced_and_oversized_lines_keep_their_existing_behaviour(chain, cache_dir):
    primary, _ = chain

    assert synthesize(text="   ") is None
    assert synthesize(text="") is None
    assert primary.calls == []

    long_line = "word " * 400                      # 2000 characters, over the spoken limit
    assert synthesize(text=long_line) is not None
    spoken = primary.calls[-1][0]
    assert len(spoken) == tts._MAX_SPOKEN_CHARS + len(tts._TRUNCATION_NOTE)
    assert spoken.endswith(tts._TRUNCATION_NOTE)


# ---------------------------------------------------------------------------
# Voice resolution, availability and logging hygiene.
# ---------------------------------------------------------------------------
def test_the_default_edge_voice_becomes_the_configured_kokoro_voice(cache_dir, monkeypatch):
    pipeline = RecordingKokoroPipeline()
    provider = kokoro_provider(monkeypatch, cache_dir.parent / "files", pipeline)
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)

    synthesize()

    assert pipeline.calls[0]["voice"] == str(
        tts.settings.tts_kokoro_voices_dir / f"{KOKORO_VOICE}.pt"), \
        "a configured local pack must be used as a file, never looked up in a repository"
    assert provider.voice_for("bf_emma") == "bf_emma", "a caller that named a voice meant it"
    assert provider.voice_for(tts.DEFAULT_COACH_VOICE) == KOKORO_VOICE


def test_a_voice_without_a_local_pack_is_left_for_the_hf_cache(cache_dir, monkeypatch):
    pipeline = RecordingKokoroPipeline()
    provider = kokoro_provider(monkeypatch, cache_dir.parent / "files", pipeline,
                               voice_pack=False)
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)

    synthesize()

    assert pipeline.calls[0]["voice"] == KOKORO_VOICE
    assert provider._voice_argument("some/where/af_heart.pt") == "some/where/af_heart.pt"


def test_availability_reports_the_chain_not_one_engine(monkeypatch):
    monkeypatch.setattr(tts.settings, "tts_provider", "kokoro")
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", True)
    monkeypatch.setattr(tts, "_kokoro_runtime_installed", lambda: False)
    monkeypatch.setattr(tts, "edge_tts", None)
    monkeypatch.setattr(tts, "_EDGE_TTS_AVAILABLE", False)
    assert tts.is_tts_available() is False

    monkeypatch.setattr(tts, "_EDGE_TTS_AVAILABLE", True)
    assert tts.is_tts_available() is True


def test_the_spoken_text_and_its_cache_name_never_reach_the_logs(chain, cache_dir, caplog,
                                                                 monkeypatch):
    """§3.4: a log line must not turn into a transcript of a candidate's answer."""
    primary, _ = chain
    primary.error = tts.TtsFailure("generation_failed", "RuntimeError")
    monkeypatch.setattr(tts.settings, "tts_fallback_enabled", False)
    spoken_text = "I disagreed with my VP about the migration deadline."
    digest = tts._cache_digest(spoken_text, KOKORO_VOICE, f"kokoro\n{KOKORO_VOICE}")

    with caplog.at_level(logging.DEBUG, logger="app.services.tts"):
        assert synthesize(text=spoken_text) is None

    logged = " ".join(record.getMessage() for record in caplog.records)
    assert spoken_text not in logged
    assert digest not in logged
    assert ".wav" not in logged
    assert "classification=generation_failed" in logged and "provider=kokoro" in logged


def test_an_unknown_failure_classification_is_refused():
    with pytest.raises(ValueError):
        tts.TtsFailure("network_blamed")


def test_the_provider_base_class_speaks_nothing():
    base = tts.TtsProvider()
    assert base.available() is False
    assert base.voice_for(EDGE_VOICE) == EDGE_VOICE
    assert base.key_salt(EDGE_VOICE) == ""
    with pytest.raises(NotImplementedError):
        asyncio.run(base.synthesize("text", EDGE_VOICE, Path("nowhere.wav")))
