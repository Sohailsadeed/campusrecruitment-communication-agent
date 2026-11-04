# Coach voice: Kokoro (local) with an Edge TTS fallback

Everything the coach says out loud comes from one function, `synthesize_feedback_audio` in
[backend/app/services/tts.py](../backend/app/services/tts.py): it takes the text of one line and
returns a path to an audio file, or `None` when nothing could be spoken. The HR voice agent hands that
path to PyAV and publishes it; the typed-report endpoint `/api/sessions/{id}/tts` streams it. Neither
of them knows which engine produced the file.

Two engines are configured by name, never by what happens to be installed:

| `TTS_PROVIDER` / `TTS_FALLBACK_PROVIDER` | What it is | Output |
| --- | --- | --- |
| `kokoro` | Kokoro-82M through the reference `kokoro` runtime, on this machine | 24 kHz mono 16-bit PCM WAV |
| `edge` | Microsoft neural voices over the network (what SpeakFlow used before) | MP3 |

The default is `TTS_PROVIDER=kokoro` with `TTS_FALLBACK_ENABLED=true` and
`TTS_FALLBACK_PROVIDER=edge`. A provider that cannot speak a line yields it to the next one in the
chain; if the chain is exhausted the function returns `None`, which is the same signal the voice agent
already treats as "this sentence had no audio" — see `unvoiced` in `_speak_stream`, in
[backend/app/agents/hr_voice_agent.py](../backend/app/agents/hr_voice_agent.py).

## 1. Runtime

`kokoro` supports Python `>=3.10,<3.13`, so it runs on the project's 3.12 venv
(`backend/speakvenv`). Its own dependencies arrive with it — `torch`, `transformers`,
`huggingface_hub`, `loguru` and `misaki[en]`. Three of those are already in the venv (verified by
`importlib.util.find_spec`: `torch`, `transformers`, `huggingface_hub`); `loguru` and `misaki` are not,
so installing `kokoro` adds them, along with `numpy` staying at 1.26.2. Leaving `numpy` unpinned is why
`kokoro` was chosen over `kokoro-onnx`: every release of `kokoro-onnx` requires `numpy>=2.0.2`, and the
`numpy<2.0.0` ceiling in [backend/requirements.txt](../backend/requirements.txt) is load-bearing for
MediaPipe and OpenCV.

Install it into the venv the project already uses. **Do not run this from a checkout you are not
prepared to change; it is a dependency install, and nothing in the test path needs it.**

```
backend/speakvenv/Scripts/pip.exe install "kokoro>=0.9.4"
```

Or, as a declaration the next person installing the backend gets:

```
backend/speakvenv/Scripts/pip.exe install -r backend/requirements.txt
```

### Phonemization

Kokoro turns text into phonemes through `misaki`, which `pip install kokoro` pulls in as
`misaki[en]`. That extra carries `espeakng-loader` and `phonemizer-fork`, and `espeakng-loader` ships
the espeak-ng data and shared library inside its own wheel — so on Windows **there is no system
espeak-ng package to install**. Upstream's README shows `apt-get install espeak-ng` because Colab has
no such wheel; on a Linux deployment, install it the same way or rely on the loader wheel. If neither
is present, `KPipeline` logs that the out-of-distribution fallback is disabled and keeps going,
skipping words its own table cannot pronounce.

## 2. Model files (acquired by hand, never at startup)

The app reads weights from disk and fetches nothing. Place them where the configuration points:

```
backend/models/kokoro/
├── kokoro-v1_0.pth        # TTS_KOKORO_MODEL_PATH
├── config.json            # TTS_KOKORO_CONFIG_PATH
└── voices/
    └── af_heart.pt        # one pack per voice, under TTS_KOKORO_VOICES_DIR
```

Fetch them from the Apache-licensed upstream repository (this is a several-hundred-megabyte download
and is deliberately not part of any startup path):

```
backend/speakvenv/Scripts/pip.exe install "huggingface_hub[cli]"
backend/speakvenv/Scripts/hf.exe download hexgrad/Kokoro-82M --local-dir backend/models/kokoro
```

or only the files you need:

```
backend/speakvenv/Scripts/hf.exe download hexgrad/Kokoro-82M --local-dir backend/models/kokoro ^
  --include "kokoro-v1_0.pth" "config.json" "voices/af_heart.pt"
```

On a machine that must not reach the network at all, set `HF_HUB_OFFLINE=1` — the same convention the
Whisper snapshot already uses — and keep the voice packs in `TTS_KOKORO_VOICES_DIR`: a voice with a
local pack is passed to the runtime as a file path, so no hub lookup happens.

Never commit these files; they are weights, not source. `backend/models/` is ignored by git for
exactly that reason.

## 3. Configuration

Every value below is an environment variable read by
[backend/config.py](../backend/config.py) — none of them is hardcoded in the service. Defaults are in
parentheses. There are no credentials anywhere in this feature.

| Variable | Default | Meaning |
| --- | --- | --- |
| `TTS_PROVIDER` | `kokoro` | Which engine gets each line first. |
| `TTS_FALLBACK_ENABLED` | `true` | Whether the second provider may take a failed line. |
| `TTS_FALLBACK_PROVIDER` | `edge` | That second provider. Must differ from `TTS_PROVIDER`. |
| `TTS_EDGE_VOICE` | `en-US-ChristopherNeural` | The Edge voice, and the default `voice` argument. |
| `TTS_KOKORO_MODEL_PATH` | `backend/models/kokoro/kokoro-v1_0.pth` | Weights file. |
| `TTS_KOKORO_CONFIG_PATH` | `backend/models/kokoro/config.json` | Model config (vocab, ISTFTNet dims). |
| `TTS_KOKORO_VOICES_DIR` | `backend/models/kokoro/voices` | Local voice packs, `<voice>.pt`. |
| `TTS_KOKORO_REPO_ID` | `hexgrad/Kokoro-82M` | Repository id the runtime quotes when a voice has no local pack. |
| `TTS_KOKORO_LANG_CODE` | `a` | `a` American English, `b` British. Must match the voice's prefix. |
| `TTS_KOKORO_VOICE` | `af_heart` | Voice pack. Any `hexgrad/Kokoro-82M` name from `VOICES.md`. |
| `TTS_KOKORO_SPEED` | `1.0` | Speech rate multiplier, validated in `[0.5, 2.0]`. |
| `TTS_KOKORO_DEVICE` | *(empty)* | Empty lets the runtime choose; `cpu` is the deterministic answer. |

Invalid values are refused when settings load, not when a candidate is on the line: an unknown
provider name, a device outside `""|cpu|cuda`, a language code outside `a|b`, a speed outside the
range, and `TTS_FALLBACK_PROVIDER` equal to `TTS_PROVIDER` with the fallback enabled all raise
`ValidationError`.

A voice pack is looked up under `TTS_KOKORO_VOICES_DIR/<voice>.pt` first and only then treated as a
repository name, so the two acquisition routes above are interchangeable.

## 4. What the audio sounds like to the pipeline

Kokoro emits 24 kHz mono float32. `tts.py` clips it to `[-1, 1]`, writes it as 16-bit PCM into a WAV
with the rate in the header, and renames the finished file onto its cache name — so a half-written
line can never be served, and a temporary file is removed on every failure path. No rate conversion
happens here: the voice agent's `speech_frames()` resamples once, `24 kHz → 48 kHz`, on its way into
the LiveKit track, exactly as it already did for MP3. `get_session_tts` declares the media type from
the file it is serving, so the browser is told `audio/wav` or `audio/mpeg` whichever arrived.

Cache names still key on session, `cache_suffix`, voice and text. The engine's identity is folded into
the digest only where it changes the audio: Edge passes an empty salt, so every Edge recording
already on disk is still addressable at the name it was written under, and a provider change does not
turn the whole cache into new network calls.

## 5. Switching engines, and what a failure looks like

To keep the round on the voice it has always used:

```
TTS_PROVIDER=edge
```

To refuse a remote voice entirely — a deployment that must answer locally or say nothing:

```
TTS_PROVIDER=kokoro
TTS_FALLBACK_ENABLED=false
```

With the fallback off, a failed line is logged and `None` is returned; no other provider is tried and
nothing is switched silently. Every attempt logs `provider`, `classification` (`unavailable`,
`init_failed`, `generation_failed`, `write_failed`), `detail` (an exception name or a byte count),
`next_provider` and `fallback`, and never the text behind it. The cache filename is a digest of the
spoken text, so it is not logged either.

`unavailable` means the runtime or the weight files are missing — the round keeps working as soon as
§2 is done, with no code change. `init_failed` is remembered for the life of the process, so a broken
model directory does not make every sentence wait on another torch import.

## 6. Verified and not yet verified

Covered by [backend/tests/test_tts_providers.py](../backend/tests/test_tts_providers.py), with mocked
Kokoro and Edge adapters and no network, no weights and no LiveKit server: provider selection, both
fallback paths, fallback-off behaviour, the WAV sample-rate and header contract, per-sentence cache
keys, cancellation during generation, the absence of a stale commit after cancellation, temp-file
cleanup, and Edge's unchanged cache digests.

Not covered there, and still to be done at runtime: real Kokoro inference (needs §1 and §2 on the
target machine), an actual 24 kHz → 48 kHz decode inside a live room, and the one behaviour a mock
cannot show — when Kokoro dies mid-reply the surviving sentences are spoken in the Edge voice, so a
single reply can change voice partway through.

The phonemization notes in §1 are read from the runtime's own source and packaging metadata, not
exercised here: no install was run, so "`espeakng-loader` brings its own espeak-ng data on Windows" and
"a missing out-of-distribution fallback only warns" are both unverified by execution.
