"""SpeakFlow / LiveKit HR voice agent (V1).

A single-purpose worker that joins one HR round's room, greets the candidate with the existing
coach TTS, listens to the candidate's microphone, transcribes with the existing Whisper service,
answers with the existing Ollama integration point and speaks the answer back into the room.

V1 is deliberately not Laya's state machine. The audio round-trip is the deliverable, and it is a
live conversation: the microphone is read continuously, including while the coach is speaking, so a
candidate can interrupt and the agent stops talking and answers the interruption instead of the
answer it was building. The reply itself is streamed: Ollama sentences are synthesised and played as
they arrive, so the coach starts speaking before the model has finished, and a barge-in closes the
HTTP stream rather than merely ignoring it.

Nothing here talks to the browser's token endpoint: the agent mints its own token from the
environment key pair, and it refuses to start unless the session it was pointed at exists, is an
HR round, and belongs to the user whose room it is.

It is also an interviewer with a memory. One ``HrConversation`` per HR session holds what has been
asked and answered, judges each answer (the local Ollama model, with a plain heuristic when it is
not reachable), asks one probe for an answer that is vague, incomplete, contradictory or off topic,
and otherwise advances with the app's existing ``pick_next_hr_question`` — which is what stops the
round from repeating itself. What the candidate said is scored by the app's existing
``evaluate_hr_answer`` and stored on the session's own ``HRInterview`` record in the shape
``POST /api/hr/answer`` stores it, so the behavioral scorecard is the same dossier for a voice round
as for a typed one; the report is written only once every planned question has an answer. The agent
adds no table, no scorer and no second persistence path, and every write re-applies the routes'
session-ownership rule to the user whose room it is in. The memory belongs to the session the agent
was pointed at; two candidates never share one.

Start it locally (the LiveKit server from docker-compose.livekit.yml must already be up, and the
candidate's browser must already be in the room or join right after)::

    export HR_SESSION_ID=1 HR_USER_ID=1
    export LIVEKIT_API_KEY=... LIVEKIT_API_SECRET=...        # same pair as .env.livekit
    export LIVEKIT_URL=ws://localhost:7880
    export DATABASE_URL=... UPLOAD_DIR=... LOGS_DIR=...      # whatever the backend uses
    export WHISPER_MODEL_NAME=small HF_HUB_OFFLINE=1         # the cached ASR snapshot
    python backend/app/agents/hr_voice_agent.py

The agent needs livekit-agents (for the RTC bindings) and av (to decode the TTS file); both stay
out of backend/speakvenv and are supplied on PYTHONPATH from an isolated target directory.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
import time
import wave
from datetime import timedelta
from pathlib import Path
from typing import List, Optional

BACKEND_DIR = Path(__file__).resolve().parents[2]   # backend/, where config.py lives
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import settings  # noqa: E402
from app.services import livekit_access  # noqa: E402
from app.services.hr.evaluator import evaluate_hr_answer, generate_hr_report  # noqa: E402
from app.services.hr.hr_service import (  # noqa: E402
    pick_next_hr_question,
    question_ref,
    resolve_answer_slot,
)
from app.services.speech_analytics import analyze_answer, round_report_block  # noqa: E402
from app.services.transcription import transcribe_audio  # noqa: E402
from app.services.tts import synthesize_feedback_audio  # noqa: E402

AGENT_IDENTITY = "hr-voice-agent"
SILENCE_AFTER_MS = 900          # end of a candidate turn
MAX_UTTERANCE_SECONDS = 25.0
SPEAK_SAMPLE_RATE = 48000       # what LiveKit publishes
LISTEN_FRAME_MS = 20
STATE_PATTERN = re.compile(r"^[a-z_]{3,24}$")

# Speech detection. The level gate is the same value the turn-taking listener always used: barge-in
# is earned by how *long* speech lasts, not by making the gate louder.
VOICE_RMS = 500
MIN_UTTERANCE_VOICED_MS = 200   # under this it is a click or a breath, not an answer
BARGE_IN_VOICED_MS = 400        # uninterrupted speech required before the coach is cut off
AEC_GRACE_MS = 250              # the echo canceller needs this to learn the speaker->mic path


# ---------------------------------------------------------------------------
# Room selection: the agent is restricted to one HR room, and only after the
# session behind that room name is verified in the database.
# ---------------------------------------------------------------------------
def resolve_room() -> tuple[int, int, str]:
    session_id = int(os.environ["HR_SESSION_ID"])
    user_id = int(os.environ["HR_USER_ID"])

    from app.database.engine import SessionLocal
    from app.models.session import Session as SessionModel

    with SessionLocal() as db:
        row = db.get(SessionModel, session_id)
        if row is None or row.round_type != "hr" or row.user_id != user_id:
            raise SystemExit(
                f"refusing to join: session {session_id} is not an HR round owned by user {user_id}"
            )
    return session_id, user_id, livekit_access.hr_room_name(session_id, user_id)


def agent_token(room: str) -> str:
    """A token for the agent itself — same room, its own identity, never the candidate's."""
    from livekit.api import AccessToken, VideoGrants

    if not settings.livekit_api_key or not settings.livekit_api_secret:
        raise SystemExit("LIVEKIT_API_KEY / LIVEKIT_API_SECRET are not set")

    grants = VideoGrants(
        room=room,
        room_join=True,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,   # state messages only, see publish_state()
        can_publish_sources=["microphone"],
        can_update_own_metadata=True,
    )
    return (
        AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(AGENT_IDENTITY)
        .with_ttl(timedelta(minutes=30))
        .with_grants(grants)
        .to_jwt()
    )


# ---------------------------------------------------------------------------
# Audio: existing TTS file -> 48 kHz mono PCM frames for the published track
# ---------------------------------------------------------------------------
def speech_frames(mp3_path: Path) -> List["object"]:
    import av
    from livekit import rtc

    frames: List[object] = []
    container = av.open(str(mp3_path))
    stream = container.streams.audio[0]
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SPEAK_SAMPLE_RATE)
    for packet in container.demux(stream):
        for decoded in packet.decode():
            for converted in resampler.resample(decoded):
                data = converted.to_ndarray().tobytes()   # resampler output is mono s16
                per_frame = SPEAK_SAMPLE_RATE // 100          # 20 ms
                samples = len(data) // 2
                for offset in range(0, samples, per_frame):
                    chunk = data[offset * 2 : min(offset + per_frame, samples) * 2]
                    frames.append(
                        rtc.AudioFrame(chunk, SPEAK_SAMPLE_RATE, 1, len(chunk) // 2)
                    )
    container.close()
    return frames


async def speak(source, mp3_path: Path) -> None:
    """Play a TTS file into the room at real time.

    Barge-in cancels this task and calls ``source.clear_queue()``, which discards the audio already
    buffered for the browser and resolves any pending ``wait_for_playout()``; the loop is sitting on
    a 20 ms ``capture_frame`` await when the cancel lands, so the voice stops within one frame.
    """
    for frame in speech_frames(mp3_path):
        # capture_frame applies its own backpressure: it waits while the source queue is full,
        # so this loop can run flat out and still play at real time.
        await source.capture_frame(frame)
    await source.wait_for_playout()      # don't cut the last word off in the browser's jitter buffer


# ---------------------------------------------------------------------------
# Response text: the existing Ollama chat integration point, with no fabricated answer
# ---------------------------------------------------------------------------
# What the candidate hears when Ollama is not answering. One complete sentence, so a fallback can
# never reach the TTS cache half-generated.
_FALLBACK_REPLY = ("Thanks — I heard you. Tell me the specific action you took yourself, and what "
                   "changed because of it.")

_INTERVIEWER_INSTRUCTIONS = (
    "You are the HR interviewer running a behavioural round out loud. Speak plainly and warmly in "
    "two short sentences at most: acknowledge what the candidate actually said, then do exactly one "
    "thing — ask the question you are given, or ask the single follow-up you are given. Never ask "
    "two questions at once, never repeat something you already asked, never mention scores, and "
    "never invent a detail the candidate did not give you."
)

# A sentence is speakable once its terminator has been followed by whitespace: a bare "Mr." or a
# trailing "." at the end of a partial stream is not, and the trailing space is what stops a
# decimal or an ellipsis mid-stream from being cut in half.
_SENTENCE_BREAK = re.compile(r"([.!?…]+[\"')\]]?)\s+")


def split_sentences(buffer: str, flush: bool = False) -> tuple[List[str], str]:
    """Take the sentences a streaming model has finished out of ``buffer``, returning the rest.

    Only text ending at a whitespace-followed terminator is released. Everything handed to TTS is
    therefore a complete utterance: a half sentence synthesised mid-generation would be cached and
    replayed as though it were the answer. ``flush`` releases what is left once generation has
    actually ended, so a model that omits terminal punctuation is still spoken.
    """
    done: List[str] = []
    while True:
        match = _SENTENCE_BREAK.search(buffer)
        if match is None:
            break
        sentence, buffer = buffer[:match.end()], buffer[match.end():]
        if sentence.strip():
            done.append(sentence.strip())
    if flush:
        if buffer.strip():
            done.append(buffer.strip())
        buffer = ""
    return done, buffer


def _chat_request(messages: List[dict], num_predict: int = 150, *, stream: bool = False) -> dict:
    return {
        "model": settings.ollama_model,
        # Ollama's /api/chat streams unless told otherwise, and a streamed body is NDJSON: a caller
        # that wants one JSON answer has to ask for it explicitly or response.json() fails.
        "stream": stream,
        # Thinking models spend the whole num_predict budget on "thinking" and answer with empty
        # content, which looks identical to an unreachable server.
        "think": False,
        "messages": messages,
        "options": {"temperature": 0.3, "num_predict": num_predict},
    }


def _chat_url() -> str:
    return f"{settings.ollama_base_url.rstrip('/')}/api/chat"


async def reply_stream(messages: List[dict]):
    """Yield ``(sentence, origin)`` while Ollama is still generating, origin is ollama|fallback.

    The stream is closed by the caller's ``aclose()``, which is what makes a barge-in stop the
    model rather than merely stop its playback: nothing after the interruption keeps producing
    speech. A failure before the first sentence yields the scripted reply; a failure *after* one
    leaves the already-spoken sentences alone instead of contradicting them with a new answer.
    """
    import httpx

    request = _chat_request(messages, stream=True)
    client = httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=5.0))
    spoken_chars = 0
    buffer = ""
    try:
        async with client.stream("POST", _chat_url(), json=request) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                payload = json.loads(line)
                buffer += ((payload.get("message") or {}).get("content") or "")
                sentences, buffer = split_sentences(buffer)
                for sentence in sentences:
                    spoken_chars += len(sentence)
                    yield sentence, "ollama"
                if payload.get("done"):
                    break
        sentences, buffer = split_sentences(buffer, flush=True)
        for sentence in sentences:
            spoken_chars += len(sentence)
            yield sentence, "ollama"
        if spoken_chars == 0:
            print("[agent] ollama answered with empty content; using the scripted reply")
            yield _FALLBACK_REPLY, "fallback"
    except Exception as exc:                      # unreachable Ollama is a normal local state
        if spoken_chars:
            print(f"[agent] ollama stream stopped early ({type(exc).__name__}) after "
                  f"{spoken_chars} characters already spoken")
        else:
            print(f"[agent] ollama unavailable ({type(exc).__name__}); using the scripted reply")
            yield _FALLBACK_REPLY, "fallback"
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Answer understanding: is this answer good enough to move on, or does it earn one probe?
# ---------------------------------------------------------------------------
VERDICTS = ("sufficient", "vague", "incomplete_star", "contradictory", "off_topic")

_CLASSIFY_INSTRUCTIONS = (
    "You assess one answer in an HR behavioural interview. Judge the answer only against the "
    "question it answered and the round's history. Reply in JSON only, no prose: "
    '{"assessment": one of "sufficient" | "vague" | "incomplete_star" | "contradictory" | '
    '"off_topic", "missing": a short phrase naming what the answer still lacks, empty when '
    'sufficient}. "sufficient" means the candidate described their own action and something real '
    "came of it, even if briefly."
)


def heuristic_verdict(answer: str) -> dict:
    """The fallback read on an answer when no model is reachable, so the round still progresses.

    Deliberately narrow and always logged as a heuristic: a first-person actor and some outcome are
    the two things about a behavioural answer that can be checked without a model. A brief answer
    that names both is not probed for length — over-probing an evidenced answer is its own defect.
    """
    if not re.search(r"\b(i|my|me|we|our)\b", answer, re.IGNORECASE):
        return {"assessment": "vague", "missing": "the specific action you took yourself"}
    if not re.search(
            r"\d|percent|%|\b(result|resulted|led to|so that|which meant|ended up|reduced|"
            r"increased)\b", answer, re.IGNORECASE):
        return {"assessment": "incomplete_star",
                "missing": ("the situation, what you did yourself and what came of it"
                            if len(answer.split()) < 15 else "the outcome of that action")}
    return {"assessment": "sufficient", "missing": ""}


def parse_verdict(raw: str) -> Optional[dict]:
    """Read the classifier's JSON even when a small model wraps it in prose or code fences."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    assessment = str(data.get("assessment", "")).strip().lower()
    if assessment not in VERDICTS:
        return None
    return {"assessment": assessment, "missing": str(data.get("missing", "")).strip()[:160]}


async def classify_answer(question: str, answer: str, history: str) -> dict:
    """Return ``{"assessment", "missing", "origin"}`` for one candidate answer."""
    import httpx

    request = _chat_request(
        [
            {"role": "system", "content": _CLASSIFY_INSTRUCTIONS},
            {"role": "user", "content": f"{history}\n\nQuestion: {question}\n"
                                        f"Candidate's answer: {answer}"},
        ],
        num_predict=90,
    )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=5.0)) as client:
            response = await client.post(_chat_url(), json=request)
            response.raise_for_status()
            raw = ((response.json().get("message") or {}).get("content") or "")
        verdict = parse_verdict(raw)
        if verdict is not None:
            return {**verdict, "origin": "ollama"}
        print(f"[agent] classifier returned unreadable verdict {raw[:80]!r}; using the heuristic")
    except Exception as exc:
        print(f"[agent] classifier unavailable ({type(exc).__name__}); using the heuristic")
    return {**heuristic_verdict(answer), "origin": "heuristic"}


# ---------------------------------------------------------------------------
# The round's memory: one instance per HR session, never shared
# ---------------------------------------------------------------------------
class HrConversation:
    """What has been asked and answered in this round, and what to do about the next answer.

    Question *selection* is not re-invented here: progression goes through the existing
    ``pick_next_hr_question``, which already excludes everything its ``asked_texts`` contains, and
    this class owns that list plus the probe limit. Selecting the next question and consuming it are
    also two steps (``propose`` then ``commit``): only a coach line the candidate heard to the end
    moves the round on, so an interruption cannot spend a question they were never told. It is the
    memory of who was asked what; the scoring, persistence and ownership rules stay with the app's
    existing HR evaluator and routes, which is where every write goes through.
    """

    def __init__(self, role: Optional[str] = None, company: Optional[str] = None,
                 track: str = "standard_hr", planned: Optional[dict] = None,
                 asked: Optional[List[dict]] = None, exchanges: Optional[List[dict]] = None,
                 max_questions: int = 4) -> None:
        self.role = role
        self.company = company
        self.track = track
        self.max_questions = max_questions
        self.asked: List[dict] = list(asked or [])
        self.exchanges: List[dict] = list(exchanges or [])
        self.current: Optional[dict] = planned
        self.probed_for: Optional[str] = None
        # The question the coach is about to ask, held here until the candidate has demonstrably
        # heard it. Selecting it and consuming it are two steps: a line cut by a barge-in must not
        # burn a question the candidate never listened to.
        self.proposed: Optional[dict] = None

    @property
    def question_text(self) -> str:
        return (self.current or {}).get("text", "")

    @property
    def asked_texts(self) -> List[str]:
        return [q.get("text", "") for q in self.asked if q.get("text")]

    def ask(self, question: dict) -> dict:
        """Mark a question as now asked, so neither the model nor progression can repeat it."""
        self.current = question
        if not self.already_asked(question.get("text", "")):
            self.asked = self.asked + [question]
        self.probed_for = None
        return question

    def propose(self, question: dict) -> dict:
        """Put a question in front of the candidate without consuming it yet."""
        self.current = question
        self.proposed = question
        return question

    def commit(self, reason: str) -> None:
        """Consume the proposed question now that the candidate has demonstrably heard it.

        Called only when a coach line carrying that question has played all the way through. A line
        cut by a barge-in, or one whose audio never reached the room, leaves ``proposed`` in place, so
        the same question is offered again next turn instead of being skipped — an interruption costs
        the round nothing it did not actually get.
        """
        if self.proposed is None:
            return
        question, self.proposed = self.proposed, None
        self.ask(question)
        print(f"[agent] question {len(self.asked)} committed ({reason})")

    def already_asked(self, text: str) -> bool:
        return text.strip().lower() in {t.strip().lower() for t in self.asked_texts}

    @property
    def answered_question(self) -> Optional[dict]:
        """The question the candidate is answering right now, but only if they were told it.

        ``current`` also holds a proposal the coach was cut off before finishing, and words spoken
        over an unheard proposal are not an answer to it. Returning nothing for that case is what
        keeps an interrupted question off the record instead of marking it completed.
        """
        if self.current is None or self.proposed is self.current:
            return None
        return self.current if self.already_asked(self.question_text) else None

    def record_answer(self, answer: str) -> None:
        self.exchanges = self.exchanges + [{"question": self.question_text, "answer": answer}]

    def answers_to(self, text: str) -> List[str]:
        """Every answer this candidate has given to this question, oldest first.

        A probe follow-up answers the question it probes, so the two belong to one record: joining
        them is what lets the app's evaluator see everything said about that question without the
        round writing a second entry for it.
        """
        wanted = text.strip().lower()
        return [e["answer"] for e in self.exchanges if e["question"].strip().lower() == wanted]

    def next_question(self) -> dict:
        """Progress the round with the round's own selector, which already excludes what was asked."""
        from app.database.engine import SessionLocal

        # db=None inside this helper would skip the seeded questions, so hand it a short-lived
        # session: the question bank belongs to the app, and the JSON list is only its fallback.
        with SessionLocal() as db:
            return pick_next_hr_question(self.track, self.company, self.asked, db)

    @property
    def round_complete(self) -> bool:
        return len(self.asked) >= self.max_questions

    def history(self, *, pending_answer: str = "") -> str:
        """What the round already knows, newest last.

        ``pending_answer`` is the exchange being spoken about right now; it is handed to the model as
        its own line, so listing it again inside the history would present one answer twice.
        """
        exchanges = self.exchanges
        if pending_answer and exchanges and exchanges[-1]["answer"] == pending_answer:
            exchanges = exchanges[:-1]
        if not exchanges:
            return "Nothing has been answered yet in this round."
        recent = exchanges[-4:]
        return "Already asked and answered in this round:\n" + "\n".join(
            f"- Asked: {e['question'][:110]}\n  Candidate: {e['answer'][:220]}" for e in recent)

    def open(self) -> dict:
        """The first thing the interviewer says: greet, then ask where the round actually stands."""
        if self.current and not self.already_asked(self.current.get("text", "")):
            return self.propose(self.current)
        return self.propose(self.next_question())

    def instruction(self, verdict: dict) -> str:
        """One probe for a weak answer, otherwise move on — and never probe the same point twice."""
        question = self.question_text
        if (verdict["assessment"] != "sufficient" and self.probed_for != question
                and not self.round_complete):
            self.probed_for = question
            focus = verdict["missing"] or "a concrete example"
            print(f"[agent] answer judged {verdict['assessment']} "
                  f"({verdict['origin']}): probing once")
            return (
                f"The candidate answered the question '{question}'. Their answer was "
                f"{verdict['assessment']} — it still needs {focus}. Acknowledge what they did say, "
                f"then ask ONE short spoken follow-up for exactly that. Do not change the subject "
                f"and do not ask a second question."
            )
        if self.round_complete:
            print(f"[agent] {len(self.asked)} questions covered: closing the round")
            return (
                "The round has covered the planned number of questions. Thank the candidate for "
                "their answers and close the interview in one short spoken sentence. Ask nothing "
                "further."
            )
        # A question that is still uncommitted is the one the candidate has not heard yet, so it
        # outranks anything the selector might pick: the round repeats it instead of skipping it.
        nxt = self.proposed if self.proposed is not None else self.next_question()
        self.propose(nxt)
        print(f"[agent] proposing question {len(self.asked) + 1}, counted as asked only once heard")
        return (
            f"The candidate's answer was sufficient. Acknowledge it in a clause, then ask this next "
            f"behavioural question exactly once, in your own words: '{nxt['text']}'. "
            f"Do not ask a second question."
        )

    def messages(self, transcript: str, instruction: str) -> List[dict]:
        """The prompt for the line the candidate is about to hear, with this round's memory."""
        context = [
            f"Role being interviewed for: {self.role or 'the role'}.",
            f"Company: {self.company or 'not specified'}.",
            f"Interview track: {self.track}.",
            self.history(pending_answer=transcript),
            f"The candidate just said: {transcript}",
        ]
        return [
            {"role": "system", "content": _INTERVIEWER_INSTRUCTIONS},
            {"role": "user", "content": "\n".join(context) + "\n\n" + instruction
                             + " Answer with the words to speak, nothing else."},
        ]


def load_hr_context(session_id: int) -> HrConversation:
    """Seed the round from the HR record the web flow owns; never invent an interview."""
    from app.database.engine import SessionLocal
    from app.models.hr import HRInterview

    with SessionLocal() as db:
        row = db.query(HRInterview).filter(HRInterview.session_id == session_id).first()
        if row is None:
            print(f"[agent] session {session_id} has no HR record: starting a plain behavioural "
                  f"round from the existing question bank")
            return HrConversation()
        done = list(row.questions or [])
        return HrConversation(
            role=row.role,
            company=row.target_company,
            track=row.interview_mode or "standard_hr",
            max_questions=row.max_questions or 4,
            asked=[{**q, "answer": None} for q in done],
            exchanges=[{"question": q.get("text", ""), "answer": q.get("answer", "")}
                       for q in done if q.get("answer")],
            planned=row.current_question,
        )


# ---------------------------------------------------------------------------
# Writing what the voice round heard into the record the text flow owns
# ---------------------------------------------------------------------------
# The bar evaluate_hr_answer itself uses to call an answer too brief to score. Fragments of a
# barge-in ("wait, can you say that again?") sit under it, and a question whose only record is
# eight characters is not a question that was answered.
MIN_PERSISTED_ANSWER_CHARS = 15


def _owned_hr(db, session_id: int, user_id: int):
    """This candidate's HR round, or nothing at all.

    The agent has no request to authenticate, so it re-applies the routes' own rule to the user id
    ``resolve_room`` already checked against the room name: the session must exist, be an HR round,
    and belong to that user. A write that fails it is refused rather than guessed at, so a mis-set
    ``HR_SESSION_ID`` can only ever touch the session the agent was authorised to join.
    """
    from fastapi import HTTPException

    from app.models.user import User
    from app.services.session_ownership import owned_round_session

    user = db.get(User, user_id)
    if user is None:
        return None, None
    try:
        session = owned_round_session(db, session_id, user, round_type="hr")
    except HTTPException:                 # the same refusal the HR routes return
        return None, None
    return session, session.hr_detail


def _record_asked_question(session_id: int, user_id: int, question: dict) -> None:
    """Mirror the question the candidate has demonstrably been told.

    ``current_question`` is how the web flow records what a round is on, so a voice round that left
    it alone would show the candidate a question they had already heard and answered.
    """
    from app.database.engine import SessionLocal

    with SessionLocal() as db:
        session, hr = _owned_hr(db, session_id, user_id)
        if hr is None or session.status == "completed":
            print(f"[agent] session {session_id} is not open for this candidate: "
                  f"question not mirrored")
            return
        hr.current_question = question
        db.commit()


def _write_voice_answer(session_id: int, user_id: int, question: dict,
                        answer: str, evaluation: dict,
                        speech: Optional[dict] = None) -> Optional[dict]:
    """Store one heard answer in the shape POST /api/hr/answer stores one.

    The session's own live question is the authority, resolved by the same helper the route uses: a
    probe follow-up and a typed submit for the question still on screen both amend that one entry, so
    a repeated, retried or re-heard answer cannot double-count. A question the round has moved past is
    refused rather than rewritten -- the recorded answer stands, and the candidate's typed answer is
    never replaced by a late spoken one. The returned dict says whether a write made the round
    complete, which is the only condition under which a report may be written.
    """
    from app.database.engine import SessionLocal

    with SessionLocal() as db:
        session, hr = _owned_hr(db, session_id, user_id)
        if hr is None:
            print(f"[agent] refused to write session {session_id}: no HR record owned by user "
                  f"{user_id}")
            return None
        if session.status == "completed":
            print(f"[agent] session {session_id} is already complete on record: answer not stored")
            return None

        stored = list(hr.questions or [])
        slot, index = resolve_answer_slot(hr.current_question, stored, question_ref(question))
        if slot != "live":
            reason = ("already answered and is no longer the live question" if slot == "history"
                      else "not a question this round is holding")
            print(f"[agent] answer not written to session {session_id}: that question is {reason} "
                  f"(the live question is {question_ref(hr.current_question) or 'none'}; the "
                  f"answer on the record is kept)")
            return None

        entry = {
            **(stored[index] if index is not None else question),
            "answer": answer,
            "audio_url": None,             # this round transcribes in memory and keeps no recording
            "vocal_delivery": {},          # no per-answer emotion pass in the voice lane
            "speech": speech or {},        # measured from the utterance the candidate just spoke
            "answered_by": "voice_agent",
            "evaluation": evaluation,
        }
        if index is None:
            stored.append(entry)
        else:
            stored[index] = entry
        hr.questions = stored
        hr.question_count = len(stored)
        db.commit()
        return {
            "questions": stored,
            "count": len(stored),
            "max_questions": hr.max_questions,
            "complete": len(stored) >= hr.max_questions,
            "role": hr.role,
            "company": hr.target_company,
        }


def _finalize_voice_report(session_id: int, user_id: int, report: dict) -> bool:
    """Close the session exactly the way the text flow closes one."""
    from app.database.engine import SessionLocal

    with SessionLocal() as db:
        session, hr = _owned_hr(db, session_id, user_id)
        if hr is None or session.status == "completed":
            return False
        hr.current_question = None
        session.status = "completed"
        session.overall_score = float(report.get("total_score", 75))
        session.report = report
        db.commit()
        return True


# ---------------------------------------------------------------------------
# State signalling for the frontend
# ---------------------------------------------------------------------------
async def publish_state(room, state: str) -> None:
    if not STATE_PATTERN.match(state):
        return
    payload = json.dumps({"agent": "hr-voice", "state": state}).encode()
    await room.local_participant.publish_data(payload, reliable=True, topic="agent_state")


def _rms(pcm: bytes) -> float:
    import array

    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5


# ---------------------------------------------------------------------------
# The candidate's microphone: one consumer for the whole round, never paused for playback
# ---------------------------------------------------------------------------
class CandidateMic:
    """Reads the candidate's audio continuously and hands finished utterances to a queue.

    This is what makes barge-in possible: the microphone is still being read while the coach's own
    voice is in the room, so speech detection and TTS playback are not mutually exclusive. Frames
    are buffered from the first voiced sample, so interrupting the coach loses none of the
    interruption.

    The coach's voice is kept out of the candidate's lane by the browser's echo canceller plus two
    timing rules, not by a louder gate or by switching listening off:

    * ``BARGE_IN_VOICED_MS`` of *unbroken* speech is needed to cut the coach off, so a cough, a
      desk knock or a half-second of AEC bleed-through stops nothing;
    * ``AEC_GRACE_MS`` must have elapsed since this line of audio started, because the canceller
      needs a moment to learn the speaker-to-microphone path before its output can be trusted.

    A pause shorter than ``SILENCE_AFTER_MS`` stays inside the same utterance, and an utterance with
    less than ``MIN_UTTERANCE_VOICED_MS`` of speech in it is dropped rather than queued — so neither
    a false start nor a breath can corrupt the turn order.

    The residual is known and not hidden: browser echo cancellation is imperfect, so a turn of the
    coach's own voice can still reach the transcript. Listening is deliberately *not* switched off
    during playback to make that invisible.
    """

    def __init__(self, sink: "asyncio.Queue[Path]", on_barge_in, playback_active) -> None:
        self._sink = sink
        self._on_barge_in = on_barge_in
        self._playback_active = playback_active
        self._task: Optional[asyncio.Task] = None
        self._stream = None
        self._seq = 0
        self._reset()

    def attach(self, track) -> None:
        """Start (or restart) consuming a published microphone track."""
        from livekit import rtc

        if self._task is not None:
            self._task.cancel()
        self._reset()
        self._stream = rtc.AudioStream(track, sample_rate=SPEAK_SAMPLE_RATE, num_channels=1,
                                       frame_size_ms=LISTEN_FRAME_MS)
        self._task = asyncio.ensure_future(self._pump())
        print("[agent] microphone consumer started (live during playback)")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                print(f"[agent] microphone consumer ended during close: {type(exc).__name__}")
            self._task = None

    async def _pump(self) -> None:
        try:
            async for event in self._stream:      # AudioStream yields AudioFrameEvent(frame=...)
                self._on_frame(event.frame)
        except asyncio.CancelledError:
            raise
        except Exception as exc:                  # the candidate unpublishing is a normal event
            print(f"[agent] microphone stream ended: {type(exc).__name__}")
        finally:
            # One cancel is delivered once, so the consumer can still close its own stream on the
            # way out — the native handle is never left to the garbage collector.
            try:
                await self._stream.aclose()
            except asyncio.CancelledError:
                print("[agent] microphone stream close interrupted; handle not confirmed freed")
            except Exception as exc:
                print(f"[agent] microphone stream close failed: {type(exc).__name__}")

    def _reset(self) -> None:
        self._active = False
        self._chunks: List[bytes] = []
        self._voiced_ms = 0
        self._voiced_run = 0
        self._quiet_ms = 0
        self._barge_in_done = False
        self._started_at = 0.0
        self._sample_rate = SPEAK_SAMPLE_RATE

    def _on_frame(self, frame) -> None:
        data = bytes(frame.data)
        self._sample_rate = frame.sample_rate or self._sample_rate
        voiced = _rms(data) > VOICE_RMS

        if not self._active:
            if not voiced:
                return
            self._active = True                   # a turn begins at the first voiced frame
            self._started_at = time.monotonic()
            self._chunks = [data]
            self._voiced_ms = self._voiced_run = LISTEN_FRAME_MS
            self._quiet_ms = 0
            self._barge_in_done = False
            return

        self._chunks.append(data)
        if voiced:
            self._voiced_ms += LISTEN_FRAME_MS
            self._voiced_run += LISTEN_FRAME_MS
            self._quiet_ms = 0
            if not self._barge_in_done and self._playback_active():
                if self._voiced_run >= BARGE_IN_VOICED_MS:
                    self._barge_in_done = True
                    self._on_barge_in(self._voiced_ms)
        else:
            self._voiced_run = 0                  # a break in the speech restarts the barge-in run
            self._quiet_ms += LISTEN_FRAME_MS

        if self._quiet_ms >= SILENCE_AFTER_MS:
            self._finish()
        elif time.monotonic() - self._started_at >= MAX_UTTERANCE_SECONDS:
            self._finish()                        # a long answer is handed over, not discarded

    def _finish(self) -> None:
        voiced_ms, chunks = self._voiced_ms, self._chunks
        self._reset()
        if voiced_ms < MIN_UTTERANCE_VOICED_MS:
            print(f"[agent] {voiced_ms} ms of noise ignored (not enough speech for a turn)")
            return

        self._seq += 1
        path = (Path(tempfile.gettempdir())
                / f"speakflow_agent_utterance_{os.getpid()}_{self._seq}.wav")
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(self._sample_rate)
            handle.writeframes(b"".join(chunks))
        self._sink.put_nowait(path)


# ---------------------------------------------------------------------------
# The round: the microphone never stops, and only one coach line is in flight
# ---------------------------------------------------------------------------
class HrVoiceRound:
    """Runs one HR round: greet, listen, answer, and be interruptible the whole time.

    Every coach line — the greeting and each answer — runs as one task that the microphone consumer
    can cancel. An interruption therefore does two things at once: the audio already on its way to
    the browser is dropped, and the answer that was still being built (transcription, Ollama, TTS)
    dies with it, so the agent replies to the interruption instead of to the words it had stopped
    saying. Nothing is ever spoken from a superseded turn.
    """

    def __init__(self, room, source, session_id: int, user_id: int) -> None:
        self.room = room
        self.source = source
        self._session_id = session_id
        # The id resolve_room verified against this room's name. Every write re-checks it, so the
        # round can only ever touch the HR record of the candidate whose room it is in.
        self._user_id = user_id
        # One memory per HR session, built from that session's own record and never shared: two
        # agents in two rooms cannot see each other's questions or answers.
        self.conversation = load_hr_context(session_id)
        self.utterances: asyncio.Queue = asyncio.Queue()
        self.mic = CandidateMic(self.utterances, on_barge_in=self._interrupt,
                                playback_active=self._coach_is_audible)
        self._line_task: Optional[asyncio.Task] = None
        self._player_task: Optional[asyncio.Task] = None
        # The answer currently being scored and written. It outlives the coach line it followed, so
        # it is waited for on the way out rather than dropped.
        self._persist_task: Optional[asyncio.Task] = None
        # (question, answer) pairs a failed attempt could not put on the record, one per question.
        self._unfiled: List[tuple] = []
        self._speaking = False
        self._playback_started_at = 0.0
        self._turn = 0
        self._stopping = False
        self._halted = False
        self._pending_mic = None

    # ---- the coach's own audio ------------------------------------------
    def _coach_is_audible(self) -> bool:
        """True while our voice is in the room and past the echo canceller's convergence window."""
        return (self._speaking
                and (time.monotonic() - self._playback_started_at) * 1000.0 >= AEC_GRACE_MS)

    async def _say(self, mp3_path: Path) -> None:
        await publish_state(self.room, "speaking")
        self._playback_started_at = time.monotonic()
        self._speaking = True
        print("[agent] speaking")
        try:
            await speak(self.source, mp3_path)
        finally:
            self._speaking = False                # also true when a barge-in cancelled the play

    def _interrupt(self, voiced_ms: int) -> None:
        """Called by the microphone consumer the moment the candidate is genuinely talking."""
        if self._line_task is not None and not self._line_task.done():
            self._line_task.cancel()              # stops new frames and the unfinished answer
        self.source.clear_queue()                # and discards what was already buffered to play
        print(f"[agent] candidate spoke for {voiced_ms} ms over the coach: line cut, "
              f"pending answer discarded")

    async def _run_line(self, line, label: str) -> bool:
        """Await one coach line, and survive the interruption that cancels it.

        Returns whether the candidate heard it to the end, which is what decides whether the round
        may count the question that line carried as asked.
        """
        self._line_task = asyncio.ensure_future(line)
        heard = True
        try:
            await self._line_task
        except asyncio.CancelledError:
            if self._stopping:
                raise
            print(f"[agent] {label} was interrupted; the candidate has the floor")
            heard = False
        finally:
            self._line_task = None
        if not (self._halted or self._stopping):
            await publish_state(self.room, "listening")
        return heard

    # ---- one turn --------------------------------------------------------
    async def _respond(self, utterance: Path) -> None:
        await publish_state(self.room, "processing")
        try:
            # Whisper is a blocking CPU call. In a thread it cannot starve the microphone consumer,
            # so an interruption raised while the agent is thinking is still heard.
            result = await asyncio.to_thread(
                transcribe_audio, utterance, model_name=settings.whisper_model_name,
                allow_mock=False,
            )
        finally:
            utterance.unlink(missing_ok=True)     # candidate audio never outlives the turn

        transcript = (result.get("text") or "").strip()
        if not transcript:
            if not result.get("segments") and not float(result.get("confidence") or 0.0):
                # An empty result with no segments and confidence 0.0 is what _empty_transcription()
                # returns when no ASR engine could run at all. Treating that as "the candidate said
                # nothing" would let a broken pipeline pass as a quiet round.
                await publish_state(self.room, "asr_error")
                self._halted = True
                print(
                    "[agent] ASR produced no engine output (empty text, confidence 0.0): a failed "
                    "transcription, not a silent candidate. Check the PyAV / faster-whisper "
                    "pairing, then start the round again."
                )
            else:
                print("[agent] no speech recognised in that turn")
            return

        print(f"[agent] candidate said {len(transcript)} characters")
        self._turn += 1
        # Judge the answer against the question it answered and what the round already knows, then
        # let the round decide — one probe, or move on. Both happen before a word is synthesised, so
        # a barge-in during classification kills a turn that had not spoken yet, not half an answer.
        verdict = await classify_answer(self.conversation.question_text, transcript,
                                        self.conversation.history())
        # Snapshot the question this answers before the round moves on: instruction() reuses
        # ``current`` for the next proposal, and this answer belongs to the question before it.
        answered = self.conversation.answered_question
        self.conversation.record_answer(transcript)
        combined = " ".join(self.conversation.answers_to(self.conversation.question_text))
        # Measured from this utterance together with the word timings the ASR engine returned for it.
        # Where a re-heard question is filed as one longer reply, these figures describe only what
        # the candidate just said, and the entry says so instead of implying otherwise.
        speech = analyze_answer(transcript, result.get("words"), result.get("segments"),
                                question=self.conversation.question_text)
        if combined.strip() != transcript.strip():
            speech["measured_from"] = "this utterance only"
        if answered is None:
            print("[agent] nothing committed behind that answer: nothing to score")
        else:
            # Scored and filed from its own task, before the coach has said a word about it: a
            # barge-in cancels the reply mid-coroutine, and an answer the candidate actually gave
            # must not go missing because the coach was talked over.
            self._score_and_file(answered, combined, speech)
        instruction = self.conversation.instruction(verdict)
        heard = await self._speak_stream(
            reply_stream(self.conversation.messages(transcript, instruction)))
        if heard:
            self.conversation.commit("the candidate heard the whole line")
            await self._record_asked()
        else:
            # Cut short, never voiced, or the scripted fallback — in all three cases the candidate
            # has not been told the new question, so it is still owed to them next turn.
            print("[agent] that line did not reach the candidate whole: nothing was consumed")

    # ---- the round on the record -----------------------------------------
    def _score_and_file(self, question: dict, answer: str,
                        speech: Optional[dict] = None) -> None:
        """Queue one answer for scoring and storage, without holding up the coach's reply.

        The tasks chain: each new one waits for the answer before it to be on the record, so two
        turns can never read, merge and write the same question list at the same time. Cancelling a
        reply is not the same as discarding what the candidate said, which is why this runs off the
        line task rather than inside it — and anything a failed attempt could not file is retried
        here before the next answer is written.
        """
        previous = self._persist_task

        async def worker() -> None:
            await self._await_previous(previous)
            await self._file_pending()
            if await self._evaluate_and_store(question, answer, speech):
                # The report is on the record: say so, because the candidate's last spoken answer is
                # already behind them and the room has no other way to learn the round is finished.
                try:
                    await publish_state(self.room, "completed")
                except Exception as exc:
                    print(f"[agent] round finished but the room did not take the completion "
                          f"signal ({type(exc).__name__}); the report is still on the record")

        self._persist_task = asyncio.ensure_future(worker())

    async def _await_previous(self, previous: Optional[asyncio.Task]) -> None:
        if previous is not None and not previous.done():
            try:
                await previous
            except (asyncio.CancelledError, Exception):   # not this answer's fault
                pass

    async def _file_pending(self) -> None:
        """Retry whatever an earlier turn could not file, oldest question first."""
        pending, self._unfiled = self._unfiled, []
        for question, answer, speech in pending:
            await self._evaluate_and_store(question, answer, speech)

    def _keep_for_retry(self, question: dict, answer: str,
                        speech: Optional[dict] = None) -> None:
        """Hold an unfiled answer, one per question, until a turn can write it."""
        key = str(question.get("text", "")).strip().lower()
        kept = [(q, a, s) for q, a, s in self._unfiled
                if str(q.get("text", "")).strip().lower() != key]
        self._unfiled = kept + [(question, answer, speech)]

    async def _record_asked(self) -> None:
        """Put the question the candidate has now demonstrably heard into the session's own record."""
        question = self.conversation.current
        if question is None:
            return
        try:
            await asyncio.to_thread(_record_asked_question, self._session_id, self._user_id,
                                    dict(question))
        except Exception as exc:
            # The candidate heard the question either way; the memory of the round is unaffected.
            print(f"[agent] could not mirror the asked question into session "
                  f"{self._session_id} ({type(exc).__name__}); continuing")

    async def _evaluate_and_store(self, question: Optional[dict], answer: str,
                                  speech: Optional[dict] = None) -> bool:
        """Score a heard answer with the app's evaluator and write it to the app's HR record.

        Returns whether that answer completed the round, which is also the only condition under
        which a report is generated. A failure here costs the attempt, never the candidate's words:
        the answer stays in the round's memory *and* in ``_unfiled``, which the next turn files
        before anything else.
        """
        if question is None or len(answer) < MIN_PERSISTED_ANSWER_CHARS:
            return False

        try:
            evaluation = await evaluate_hr_answer(
                role=self.conversation.role or "Software Engineer",
                company=self.conversation.company,
                track=question.get("track", self.conversation.track),
                question=question.get("text", "Behavioral question"),
                candidate_answer=answer,
            )
        except Exception as exc:
            # The real evaluator answers its own failures with a scored fallback; anything that
            # escapes it is this task's problem, and an unscored answer is not filed as a fact.
            print(f"[agent] evaluation failed ({type(exc).__name__}); the transcript is kept "
                  f"in the round and tried again next turn")
            self._keep_for_retry(question, answer, speech)
            return False
        try:
            outcome = await asyncio.to_thread(_write_voice_answer, self._session_id,
                                              self._user_id, dict(question), answer, evaluation,
                                              speech)
        except Exception as exc:
            print(f"[agent] could not write that answer to session {self._session_id} "
                  f"({type(exc).__name__}); the transcript is kept for the next turn")
            self._keep_for_retry(question, answer, speech)
            return False
        if outcome is None:
            print("[agent] that answer was not written: the session will not accept it "
                  "(not this candidate's HR round, or already complete)")
            return False
        print(f"[agent] answer stored: {outcome['count']}/{outcome['max_questions']} questions "
              f"answered, overall={evaluation.get('overall_score')}/100 "
              f"STAR={evaluation.get('star_structure', {}).get('completeness_score')}/100")
        if not outcome["complete"]:
            return False

        try:
            report = await generate_hr_report(role=outcome["role"], company=outcome["company"],
                                              questions_asked=outcome["questions"])
            try:
                from app.services.emotion import get_session_emotion_summary

                # The same key the text report carries, so the frontend reads one shape of report.
                report["vocal_delivery"] = get_session_emotion_summary(self._session_id,
                                                                       fallback={})
                # The same delivery section the text flow attaches, so both reports read alike.
                report["speech"] = round_report_block(outcome["questions"])
            except Exception as exc:
                print(f"[agent] no vocal delivery summary for session {self._session_id} "
                      f"({type(exc).__name__})")
            written = await asyncio.to_thread(_finalize_voice_report, self._session_id,
                                              self._user_id, report)
        except Exception as exc:
            # Every answer is on the record; only the dossier is missing, and the text flow's own
            # report path can produce it for a session that is complete but unreported.
            print(f"[agent] session {self._session_id} answered but not reported "
                  f"({type(exc).__name__})")
            return False
        if written:
            print(f"[agent] round complete: report written, total="
                  f"{report.get('total_score')}/100")
            return True
        return False

    # ---- one streamed reply ------------------------------------------------
    async def _speak_stream(self, stream) -> bool:
        """Speak each sentence as soon as its audio exists, and stop the model when cancelled.

        Generation, synthesis and playback are deliberately three concurrent steps: the candidate
        hears the coach's first sentence while the model is still writing the second. The ``finally``
        is what keeps that honest under a barge-in — the HTTP stream is closed, the player is
        cancelled and the source queue is emptied, so no sentence of a superseded answer is spoken
        after the candidate takes the floor.

        Returns whether the candidate heard the *model's own* line from start to finish. That is the
        only answer the round may treat as evidence a question was put: a cancelled line, a line with
        a sentence TTS could not voice, or the scripted fallback, all say nothing about it.
        """
        spoken: asyncio.Queue = asyncio.Queue()
        player = asyncio.ensure_future(self._play_chunks(spoken))
        self._player_task = player
        origins: List[str] = []
        sentences = 0
        unvoiced = 0
        played = 0
        cancelled = False
        try:
            async for text, origin in stream:
                origins.append(origin)
                mp3 = await synthesize_feedback_audio(
                    self._session_id, text, cache_suffix=f"reply_{self._turn}_{sentences}")
                sentences += 1
                if sentences == 1:
                    # Logged as the first sentence lands, not when the turn ends: an interrupted
                    # reply never reaches its end, and "where did that voice come from?" is exactly
                    # the question the interrupted turns need answered.
                    print(f"[agent] reply origin={origin} first_sentence_after_transcript")
                if mp3 is not None:
                    spoken.put_nowait(mp3)         # plays while the next sentence is generated
                else:
                    unvoiced += 1
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            await stream.aclose()                  # stops the model, not merely our reading of it
            if cancelled:
                player.cancel()
                self.source.clear_queue()          # drop whatever was already buffered to play
            else:
                spoken.put_nowait(None)
            await asyncio.wait({player}, timeout=5.0)
            self._player_task = None
            if not cancelled and player.done() and not player.cancelled():
                played = player.result()             # a decode failure is still a failure
        if not origins:
            print("[agent] TTS produced no audio for that reply")
        elif sentences > 1:
            print(f"[agent] reply sentences={sentences} played={played} "
                  f"origins={','.join(dict.fromkeys(origins))}")
        # Heard whole means: the model finished, every sentence got audio, every chunk was spoken to
        # the end, and none of it was the scripted fallback. Anything less leaves the round where it
        # was, so a question the candidate only half-heard is never counted as asked.
        return (not cancelled) and sentences > 0 and unvoiced == 0 and played == sentences \
            and "fallback" not in origins

    async def _play_chunks(self, queue: asyncio.Queue) -> None:
        """Play synthesised sentences in the order the model produced them.

        Every chunk goes through the same source and the same 20 ms frame capture as a whole line
        did, so ``clear_queue()`` plus a cancel is still an immediate stop: at most the frame
        already handed to the SDK can outlive the interruption. Returns how many chunks were spoken
        to the end, which is what tells the turn whether the room heard the whole line.
        """
        first = True
        played = 0
        try:
            while True:
                mp3_path = await queue.get()
                if mp3_path is None:
                    return played
                if first:
                    first = False
                    self._playback_started_at = time.monotonic()
                    self._speaking = True
                    await publish_state(self.room, "speaking")
                    print("[agent] speaking")
                await speak(self.source, mp3_path)
                played += 1
        finally:
            self._speaking = False

    async def shutdown(self) -> None:
        """Leave no half-played line and no half-read microphone behind."""
        self._stopping = True
        if self._line_task is not None and not self._line_task.done():
            self._line_task.cancel()
            try:
                await self._line_task
            except asyncio.CancelledError:
                pass
            self._line_task = None
        if self._player_task is not None and not self._player_task.done():
            self._player_task.cancel()             # a line cancelled at shutdown still had a player
        # The candidate has left, but what they said may still be on its way to the record. Let it
        # land, then try once more whatever a failed attempt could not file: an answer lost to a
        # shutdown is a real loss, not a tidy one.
        await self._await_previous(self._persist_task)
        if self._unfiled:
            try:
                await asyncio.wait_for(self._file_pending(), timeout=60.0)
            except (asyncio.CancelledError, Exception) as exc:
                print(f"[agent] {len(self._unfiled)} answer(s) did not reach the record "
                      f"({type(exc).__name__})")
        await self.mic.close()

    async def _attach_pending_mic(self, wait_seconds: float = 0.0) -> None:
        """Attach a remembered microphone from a safe point, not from the room's event callback."""
        deadline = time.monotonic() + wait_seconds
        while self._pending_mic is None and time.monotonic() < deadline:
            await asyncio.sleep(0.2)              # the candidate has not opened a microphone yet
        if self._pending_mic is None:
            return
        track, self._pending_mic = self._pending_mic, None
        self.mic.attach(track)

    # ---- the round -------------------------------------------------------
    async def run(self, url: str, room_name: str) -> None:
        from livekit import rtc

        @self.room.on("participant_connected")
        def on_participant(participant) -> None:
            print(f"[agent] participant connected: {participant.identity}")

        @self.room.on("track_subscribed")
        def on_track(track, publication, participant) -> None:
            if isinstance(track, rtc.RemoteAudioTrack):
                # Only remembered here. Building an AudioStream is a synchronous FFI call, and doing
                # it inside this callback re-enters the same channel the room's own in-flight request
                # is waiting on — the agent deadlocks before it publishes anything. The round loop
                # attaches it at an await boundary instead.
                print(f"[agent] {participant.identity} published a microphone")
                self._pending_mic = track

        @self.room.on("participant_disconnected")
        def on_left(participant) -> None:
            print(f"[agent] participant left: {participant.identity}")
            if not self.room.remote_participants:
                self.utterances.put_nowait(None)   # the round ends with nobody in the room

        @self.room.on("disconnected")
        def on_closed(*_args) -> None:
            print("[agent] room closed")

        print(f"[agent] joining {room_name} as {AGENT_IDENTITY}")
        await self.room.connect(url, agent_token(room_name))
        voice_track = rtc.LocalAudioTrack.create_audio_track("coach-voice", self.source)
        await self.room.local_participant.publish_track(
            voice_track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        )
        await publish_state(self.room, "connected")
        print("[agent] in the room; coach voice published")

        # Listening starts before the first word is spoken, so the greeting itself is heard through
        # the microphone: that is what shows the agent cannot mistake its own voice for a candidate.
        await self._attach_pending_mic(wait_seconds=30.0)

        # The round opens on the question the session's own record says it is on — or, for a fresh
        # record, the first one the existing selector picks. Nothing is invented here.
        opening = self.conversation.open()
        print(f"[agent] opening question: {opening['text'][:80]}")
        greeting = (
            "Hello! I am your SpeakFlow HR coach. This is a practice behavioural round, so take "
            f"your time. {opening['text']}"
        )
        mp3 = await synthesize_feedback_audio(self._session_id, greeting, cache_suffix="greeting")
        if mp3 is None:
            print("[agent] TTS produced no audio; continuing silently")
        elif await self._run_line(self._say(mp3), "greeting"):
            # Only now has the round's first question actually been put to the candidate.
            self.conversation.commit("the greeting played to the end")
            await self._record_asked()

        while True:
            await self._attach_pending_mic()      # a re-published microphone is picked up here
            try:
                utterance = await asyncio.wait_for(self.utterances.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            if utterance is None:
                print("[agent] the candidate left the room; ending the round")
                return
            while not self.utterances.empty():
                # The candidate's latest words outrank their earlier ones, and they outrank an
                # answer the agent is slow to build: keep the newest, delete what it replaced.
                replaced = utterance
                utterance = self.utterances.get_nowait()
                if utterance is None:
                    replaced.unlink(missing_ok=True)
                    return
                replaced.unlink(missing_ok=True)
            await self._run_line(self._respond(utterance), f"reply {self._turn + 1}")
            if self._halted:
                return


async def run() -> None:
    from livekit import rtc

    session_id, user_id, room_name = resolve_room()
    url = settings.livekit_url
    if not url:
        raise SystemExit("LIVEKIT_URL is not set")

    round_ = HrVoiceRound(rtc.Room(), rtc.AudioSource(SPEAK_SAMPLE_RATE, 1), session_id, user_id)
    try:
        await round_.run(url, room_name)
    finally:
        await round_.shutdown()
        await publish_state(round_.room, "closed")
        await round_.room.disconnect()
        print("[agent] disconnected cleanly")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("[agent] stopped")
