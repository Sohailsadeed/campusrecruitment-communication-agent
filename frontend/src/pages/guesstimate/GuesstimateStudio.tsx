import { useState, useEffect, useRef } from "react";
import { useNavigate, useParams, useSearchParams, Link } from "react-router-dom";
import {
  getGuesstimateMetadata,
  getRandomGuesstimate,
  startGuesstimateSession,
  submitGuesstimateAnswer,
  getGuesstimateSession,
  GuesstimateMetadataResponse,
} from "../../api/guesstimate";
import { useLiveEmotionStream } from "../../hooks/useLiveEmotionStream";
import LiveConfidenceNeedle from "../../components/Interview/LiveConfidenceNeedle";
import LiveCoachNudge from "../../components/Interview/LiveCoachNudge";

const CATEGORY_CARDS = [
  {
    id: "Market Sizing",
    title: "Market Sizing",
    icon: "query_stats",
    desc: "Estimate total addressable market (TAM), annual customer volume, or unit demand.",
    tag: "Demand-Side Focus",
  },
  {
    id: "Revenue Estimation",
    title: "Revenue Estimation",
    icon: "payments",
    desc: "Calculate revenue, average ticket sizes, footfall throughput, and pricing models.",
    tag: "Store & Unit Economics",
  },
  {
    id: "Operational & Capacity Sizing",
    title: "Operational & Capacity",
    icon: "factory",
    desc: "Model fulfillment queues, fleet dispatch, hospital beds, and logistics bottlenecks.",
    tag: "Supply & Throughput",
  },
  {
    id: "Abstract / Fermi Problems",
    title: "Abstract & Fermi",
    icon: "calculate",
    desc: "Tackle unconventional dimensional, volumetric, and order-of-magnitude estimations.",
    tag: "First Principles & Physics",
  },
];

const FRAMEWORK_MODES = [
  {
    id: "top_down",
    title: "Top-Down Demand Framework",
    desc: "Start from macro population, segment by demographic & income, apply penetration & frequency.",
  },
  {
    id: "bottom_up",
    title: "Bottom-Up Supply Framework",
    desc: "Start with unit capacity, operational hours, customer turnover, and multiply by average spend.",
  },
  {
    id: "fermi",
    title: "Volumetric / Dimensional Fermi",
    desc: "Calculate dimensional volume or physical constraints, apply packing efficiency factor.",
  },
];

export default function GuesstimateStudio() {
  const navigate = useNavigate();
  const { sessionId: paramSessionId } = useParams<{ sessionId?: string }>();
  const [searchParams] = useSearchParams();

  // Setup state
  const [category, setCategory] = useState("Market Sizing");
  const [difficulty, setDifficulty] = useState("Intermediate");
  const [previewQuestion, setPreviewQuestion] = useState("");
  const [customQuestion, setCustomQuestion] = useState("");
  const [isCustomMode, setIsCustomMode] = useState(false);
  const [approachType, setApproachType] = useState("top_down");
  const [metadata, setMetadata] = useState<GuesstimateMetadataResponse | null>(null);
  const [isShuffling, setIsShuffling] = useState(false);

  // Active Session state
  const [sessionId, setSessionId] = useState<number | null>(() => {
    if (paramSessionId) return Number(paramSessionId);
    const qId = searchParams.get("session_id");
    if (qId) return Number(qId);
    const cached = localStorage.getItem("speakflow_active_guesstimate_session");
    return cached ? Number(cached) : null;
  });

  const [activeQuestion, setActiveQuestion] = useState("");
  const [answerText, setAnswerText] = useState("");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [isStarting, setIsStarting] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isSpeaking, setIsSpeaking] = useState(false);

  // Voice recording state
  const [isRecording, setIsRecording] = useState(false);
  const [recordedAudioBlob, setRecordedAudioBlob] = useState<Blob | null>(null);
  const recognitionRef = useRef<any>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const { liveEmotion, nudge } = useLiveEmotionStream(sessionId, isRecording, {
    category,
    question: activeQuestion,
    partialTranscript: answerText,
  });

  // 1. Fetch metadata on mount
  useEffect(() => {
    getGuesstimateMetadata()
      .then((data) => setMetadata(data))
      .catch((err) => console.warn("Could not load guesstimate metadata:", err));
  }, []);

  // 2. Fetch initial sample question on category/difficulty change
  useEffect(() => {
    if (!sessionId && !isCustomMode) {
      setIsShuffling(true);
      getRandomGuesstimate(category, difficulty)
        .then((data) => {
          setPreviewQuestion(data.question);
        })
        .catch((err) => console.warn("Failed to sample guesstimate:", err))
        .finally(() => setIsShuffling(false));
    }
  }, [category, difficulty, sessionId, isCustomMode]);

  // 3. Restore session if sessionId exists
  useEffect(() => {
    let mounted = true;
    if (sessionId) {
      setIsRestoring(true);
      getGuesstimateSession(sessionId)
        .then((data) => {
          if (!mounted) return;
          if (data.is_complete) {
            localStorage.removeItem("speakflow_active_guesstimate_session");
            navigate(`/guesstimate/report/${sessionId}`, { replace: true });
          } else {
            setActiveQuestion(data.question);
            setCategory(data.category);
            setDifficulty(data.difficulty);
            setApproachType(data.approach_type || "top_down");
            if (data.candidate_answer) setAnswerText(data.candidate_answer);
            localStorage.setItem("speakflow_active_guesstimate_session", String(sessionId));
          }
        })
        .catch((err) => {
          console.warn("Could not restore guesstimate session:", err);
          localStorage.removeItem("speakflow_active_guesstimate_session");
          setSessionId(null);
        })
        .finally(() => {
          if (mounted) setIsRestoring(false);
        });
    }
    return () => {
      mounted = false;
    };
  }, [sessionId, navigate]);

  // 4. Timer effect
  useEffect(() => {
    let timer: any;
    if (sessionId && !isRestoring) {
      timer = setInterval(() => setElapsedSeconds((s) => s + 1), 1000);
    }
    return () => clearInterval(timer);
  }, [sessionId, isRestoring]);

  // 5. Speech Recognition setup
  useEffect(() => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onresult = (event: any) => {
        let transcript = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript;
        }
        setAnswerText((prev) => (prev ? `${prev} ${transcript}` : transcript));
      };

      recognition.onerror = () => setIsRecording(false);
      recognition.onend = () => setIsRecording(false);
      recognitionRef.current = recognition;
    }
  }, []);

  const handleShuffle = async () => {
    setIsShuffling(true);
    try {
      const data = await getRandomGuesstimate(category, difficulty);
      setPreviewQuestion(data.question);
    } catch (err) {
      console.warn("Failed to shuffle question:", err);
    } finally {
      setIsShuffling(false);
    }
  };

  const handleSpeakQuestion = (text: string) => {
    if (!window.speechSynthesis) return;
    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    setIsSpeaking(true);
    window.speechSynthesis.speak(utterance);
  };

  const toggleRecording = async () => {
    if (isRecording) {
      if (recognitionRef.current) recognitionRef.current.stop();
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
      setIsRecording(false);
    } else {
      setErrorMsg(null);
      audioChunksRef.current = [];
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const recorder = new MediaRecorder(stream);
        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) audioChunksRef.current.push(e.data);
        };
        recorder.onstop = () => {
          const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
          setRecordedAudioBlob(blob);
          stream.getTracks().forEach((track) => track.stop());
        };
        recorder.start(250);
        mediaRecorderRef.current = recorder;

        if (recognitionRef.current) recognitionRef.current.start();
        setIsRecording(true);
      } catch (err) {
        console.warn("Microphone access failed:", err);
        setErrorMsg("Microphone permission denied. You can continue by typing in the scratchpad.");
      }
    }
  };

  const handleStartDrill = async () => {
    const chosenQ = isCustomMode ? customQuestion.trim() : previewQuestion.trim();
    if (!chosenQ) {
      setErrorMsg("Please select or enter a guesstimate problem statement.");
      return;
    }

    setIsStarting(true);
    setErrorMsg(null);

    try {
      const res = await startGuesstimateSession({
        category,
        difficulty,
        question: chosenQ,
        approach_type: approachType,
      });

      setSessionId(res.session_id);
      setActiveQuestion(res.question);
      setElapsedSeconds(0);
      setAnswerText("");
      setRecordedAudioBlob(null);
      localStorage.setItem("speakflow_active_guesstimate_session", String(res.session_id));
      handleSpeakQuestion(res.question);
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to initialize guesstimate session.");
    } finally {
      setIsStarting(false);
    }
  };

  const handleSubmit = async () => {
    if (!sessionId || !answerText.trim()) {
      setErrorMsg("Please provide your calculation and breakdown before submitting.");
      return;
    }

    if (isRecording) {
      if (recognitionRef.current) recognitionRef.current.stop();
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
      setIsRecording(false);
    }
    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      const res = await submitGuesstimateAnswer(
        sessionId,
        answerText.trim(),
        approachType,
        recordedAudioBlob
      );
      localStorage.removeItem("speakflow_active_guesstimate_session");
      navigate(`/guesstimate/report/${res.session_id}`);
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to evaluate guesstimate response.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const formatTimer = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  };

  // -------------------------------------------------------------------------
  // RENDER: RESTORING SESSION
  // -------------------------------------------------------------------------
  if (isRestoring) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-[70vh] gap-4">
        <div className="w-12 h-12 rounded-full border-2 border-tertiary border-t-transparent animate-spin" />
        <span className="font-headline-sm text-sm text-on-surface-variant font-medium">
          Restoring your active Guesstimate Drill session...
        </span>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // RENDER: SETUP VIEW (CARD SELECTION & LAUNCH)
  // -------------------------------------------------------------------------
  if (!sessionId) {
    return (
      <div className="relative w-full overflow-hidden px-4 sm:px-8 py-8 sm:py-10 max-w-7xl mx-auto flex flex-col gap-8">
        {/* Ambient Backdrop Aura */}
        <div className="pointer-events-none absolute -top-40 right-1/4 w-[700px] h-[400px] bg-tertiary/10 rounded-full blur-[140px]" />
        <div className="pointer-events-none absolute top-1/2 -left-20 w-[500px] h-[350px] bg-primary/10 rounded-full blur-[120px]" />

        {/* Header Breadcrumbs & Title */}
        <div className="relative z-10 flex flex-col gap-2">
          <div className="flex items-center gap-2 text-xs text-outline font-label-caps">
            <Link to="/" className="hover:text-on-surface transition-colors">Practice Arena</Link>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <span className="text-tertiary font-semibold">Track 03: Guesstimate &amp; Market Sizing</span>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-surface-container-high text-tertiary font-label-numeric-sm text-[11px] font-medium mb-2">
                <span className="w-1.5 h-1.5 rounded-full bg-tertiary animate-pulse" />
                990 Curated Placement Guesstimates Indexed
              </div>
              <h1 className="font-display-hero text-3xl sm:text-4xl font-extrabold text-on-surface tracking-tight">
                Guesstimate &amp; Market Sizing Studio
              </h1>
              <p className="font-body-lg text-sm text-on-surface-variant max-w-3xl leading-relaxed mt-1">
                Master consulting case estimations and product management sizing drills. Practice structured
                MECE segmentation, realistic proxy benchmarking, mental math out loud, and sanity checks.
              </p>
            </div>

            {/* Total Library Badge */}
            <div className="flex items-center gap-3 p-3 rounded-xl bg-surface-container-low border border-outline-variant/30">
              <span className="material-symbols-outlined text-tertiary text-[26px]">analytics</span>
              <div className="flex flex-col">
                <span className="font-label-numeric text-base font-bold text-on-surface">
                  {metadata?.total_questions || 990}
                </span>
                <span className="text-[10px] text-outline font-label-caps uppercase">Curated Problems</span>
              </div>
            </div>
          </div>
        </div>

        {errorMsg && (
          <div className="p-4 rounded-xl bg-error-container/20 border border-error/30 text-error text-xs flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px]">error</span>
            <span>{errorMsg}</span>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Column: Category & Difficulty (7 Cols) */}
          <div className="lg:col-span-7 flex flex-col gap-6">
            {/* Step 1: Select Category */}
            <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-4 shadow-lg">
              <div className="flex items-center justify-between">
                <span className="font-label-caps text-xs uppercase text-tertiary font-bold tracking-wider flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-[18px]">category</span>
                  Step 1: Select Estimation Category
                </span>
                <span className="text-xs text-outline font-label-numeric-sm">4 Archetypes</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {CATEGORY_CARDS.map((cat) => {
                  const isSelected = category === cat.id;
                  const count = metadata?.categories.find((c) => c.id === cat.id)?.count;
                  return (
                    <button
                      key={cat.id}
                      type="button"
                      onClick={() => setCategory(cat.id)}
                      className={`p-4 rounded-xl text-left border transition-all flex flex-col justify-between gap-3 ${
                        isSelected
                          ? "bg-tertiary-container/20 border-tertiary text-on-surface shadow-md shadow-tertiary/10"
                          : "bg-surface-container border-outline-variant/20 hover:border-outline-variant/60 text-on-surface-variant"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="w-9 h-9 rounded-lg bg-surface-container-high flex items-center justify-center text-tertiary">
                          <span className="material-symbols-outlined text-[20px]">{cat.icon}</span>
                        </div>
                        {isSelected ? (
                          <span className="material-symbols-outlined text-tertiary text-[18px]">check_circle</span>
                        ) : count ? (
                          <span className="font-label-numeric-sm text-[11px] px-2 py-0.5 rounded bg-surface-container-high text-outline">
                            {count}
                          </span>
                        ) : null}
                      </div>

                      <div>
                        <span className="font-headline-sm text-sm font-semibold text-on-surface block">
                          {cat.title}
                        </span>
                        <span className="text-[11px] text-outline leading-tight mt-1 block">
                          {cat.desc}
                        </span>
                      </div>

                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-label-caps uppercase font-semibold w-fit ${
                        isSelected ? "bg-tertiary text-on-tertiary" : "bg-surface-container-high text-outline"
                      }`}>
                        {cat.tag}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Step 2: Difficulty & Framework */}
            <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-4 shadow-lg">
              <span className="font-label-caps text-xs uppercase text-tertiary font-bold tracking-wider flex items-center gap-1.5">
                <span className="material-symbols-outlined text-[18px]">speed</span>
                Step 2: Difficulty Level &amp; Approach Strategy
              </span>

              <div className="flex flex-col gap-4">
                {/* Difficulty Pills */}
                <div>
                  <label className="text-xs text-outline font-label-caps uppercase block mb-2 font-semibold">
                    Placement Difficulty Tier
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {["Beginner", "Intermediate", "Advanced"].map((lvl) => {
                      const isSel = difficulty === lvl;
                      const count = metadata?.difficulties.find((d) => d.id === lvl)?.count;
                      return (
                        <button
                          key={lvl}
                          type="button"
                          onClick={() => setDifficulty(lvl)}
                          className={`py-2.5 px-3 rounded-lg text-xs font-semibold border transition-all flex flex-col items-center gap-0.5 ${
                            isSel
                              ? "bg-tertiary text-on-tertiary border-tertiary shadow-sm"
                              : "bg-surface-container text-on-surface-variant border-outline-variant/30 hover:bg-surface-container-high"
                          }`}
                        >
                          <span>{lvl}</span>
                          {count && (
                            <span className={`text-[10px] ${isSel ? "text-on-tertiary/80" : "text-outline"}`}>
                              {count} questions
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Strategy Framework */}
                <div className="pt-2 border-t border-outline-variant/20">
                  <label className="text-xs text-outline font-label-caps uppercase block mb-2 font-semibold">
                    Target Decomposition Strategy
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    {FRAMEWORK_MODES.map((fw) => (
                      <button
                        key={fw.id}
                        type="button"
                        onClick={() => setApproachType(fw.id)}
                        className={`p-3 rounded-lg text-left border transition-all flex flex-col justify-between gap-1.5 ${
                          approachType === fw.id
                            ? "bg-tertiary-container/20 border-tertiary text-on-surface"
                            : "bg-surface-container border-outline-variant/20 hover:border-outline-variant/50 text-on-surface-variant"
                        }`}
                      >
                        <span className="font-headline-sm text-xs font-semibold text-on-surface">
                          {fw.title}
                        </span>
                        <span className="text-[10px] text-outline leading-tight">
                          {fw.desc}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: Problem Preview & Launch (5 Cols) */}
          <div className="lg:col-span-5 flex flex-col gap-6">
            {/* Question Card Deck */}
            <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-4 shadow-lg relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-tertiary/10 rounded-full blur-3xl pointer-events-none" />

              <div className="flex items-center justify-between">
                <span className="font-label-caps text-xs uppercase text-tertiary font-bold tracking-wider flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-[18px]">lightbulb</span>
                  Problem Statement Preview
                </span>
                <button
                  type="button"
                  onClick={() => setIsCustomMode(!isCustomMode)}
                  className="text-xs text-outline hover:text-tertiary font-label-numeric-sm transition-colors"
                >
                  {isCustomMode ? "Use Curated Bank" : "Enter Custom"}
                </button>
              </div>

              {!isCustomMode ? (
                /* Curated Problem Preview Box */
                <div className="p-4 rounded-xl bg-surface-container border border-outline-variant/30 flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-label-caps uppercase text-outline">
                      {category} • {difficulty}
                    </span>
                    <button
                      type="button"
                      onClick={handleShuffle}
                      disabled={isShuffling}
                      className="inline-flex items-center gap-1 text-xs text-tertiary font-semibold hover:underline cursor-pointer disabled:opacity-50"
                    >
                      <span className={`material-symbols-outlined text-[16px] ${isShuffling ? "animate-spin" : ""}`}>
                        shuffle
                      </span>
                      <span>Next Problem</span>
                    </button>
                  </div>

                  <p className="font-headline-sm text-sm sm:text-base font-semibold text-on-surface leading-relaxed min-h-[4rem]">
                    "{previewQuestion || "Loading question from bank..."}"
                  </p>
                </div>
              ) : (
                /* Custom Question Input */
                <div className="flex flex-col gap-2">
                  <label className="text-xs text-outline font-label-caps uppercase font-semibold">
                    Custom Guesstimate Topic
                  </label>
                  <textarea
                    rows={4}
                    placeholder="e.g. Estimate the number of commercial EV charging stations needed in Bangalore by 2028."
                    value={customQuestion}
                    onChange={(e) => setCustomQuestion(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-lg bg-surface-container border border-outline-variant/40 text-on-surface text-xs focus:outline-none focus:border-tertiary transition-colors resize-none"
                  />
                </div>
              )}

              {/* MBB Evaluation Criteria Checklist */}
              <div className="flex flex-col gap-2 pt-2 border-t border-outline-variant/20">
                <span className="text-xs text-outline font-label-caps uppercase font-semibold">
                  What Interviewers Will Evaluate:
                </span>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="flex items-center gap-1.5 text-on-surface-variant">
                    <span className="material-symbols-outlined text-tertiary text-[15px]">account_tree</span>
                    <span>MECE Structuring</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-on-surface-variant">
                    <span className="material-symbols-outlined text-tertiary text-[15px]">verified</span>
                    <span>Proxy Plausibility</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-on-surface-variant">
                    <span className="material-symbols-outlined text-tertiary text-[15px]">calculate</span>
                    <span>Mental Math Flow</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-on-surface-variant">
                    <span className="material-symbols-outlined text-tertiary text-[15px]">balance</span>
                    <span>Sanity &amp; Sensitivity</span>
                  </div>
                </div>
              </div>

              {/* Launch CTA */}
              <button
                type="button"
                onClick={handleStartDrill}
                disabled={isStarting || (!previewQuestion && !customQuestion)}
                className="w-full mt-2 py-3.5 px-6 rounded-xl bg-gradient-to-r from-tertiary via-emerald-500 to-teal-500 hover:opacity-95 transition-all text-on-tertiary font-headline-sm text-sm font-bold flex items-center justify-center gap-2 shadow-lg shadow-tertiary/20 cursor-pointer disabled:opacity-50"
              >
                {isStarting ? (
                  <>
                    <span className="material-symbols-outlined animate-spin text-[20px]">refresh</span>
                    <span>Initializing Estimation Sandbox...</span>
                  </>
                ) : (
                  <>
                    <span>Launch Guesstimate Drill</span>
                    <span className="material-symbols-outlined text-[20px]">arrow_forward</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // RENDER: LIVE ESTIMATION DRILL STUDIO
  // -------------------------------------------------------------------------
  return (
    <div className="relative w-full overflow-hidden px-4 sm:px-8 py-8 sm:py-10 max-w-6xl mx-auto flex flex-col gap-6">
      {/* Ambient Backdrop Aura */}
      <div className="pointer-events-none absolute -top-40 right-1/4 w-[700px] h-[400px] bg-tertiary/10 rounded-full blur-[140px]" />
      <div className="pointer-events-none absolute top-1/2 -left-20 w-[500px] h-[350px] bg-primary/10 rounded-full blur-[120px]" />

      {/* Studio Header Strip */}
      <div className="relative z-10 flex items-center justify-between p-4 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-md">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-tertiary/10 text-tertiary flex items-center justify-center">
            <span className="material-symbols-outlined text-[22px]">query_stats</span>
          </div>
          <div className="flex flex-col">
            <span className="font-headline-sm text-sm font-bold text-on-surface">{category}</span>
            <div className="flex items-center gap-2 text-[11px] text-outline font-label-caps uppercase font-medium">
              <span>{difficulty}</span>
              <span className="text-outline/40">•</span>
              <span className="text-tertiary font-semibold">
                {FRAMEWORK_MODES.find((f) => f.id === approachType)?.title || "Top-Down"}
              </span>
            </div>
          </div>
        </div>

        {/* Timer & Speech Status */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 font-label-numeric-sm text-xs text-on-surface bg-surface-container px-3 py-1.5 rounded-lg border border-outline-variant/20">
            <span className="material-symbols-outlined text-[16px] text-tertiary">schedule</span>
            <span>{formatTimer(elapsedSeconds)}</span>
          </div>

          <button
            type="button"
            onClick={() => handleSpeakQuestion(activeQuestion)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold font-label-caps flex items-center gap-1.5 transition-colors border ${
              isSpeaking
                ? "bg-secondary text-on-secondary border-secondary"
                : "bg-surface-container text-outline hover:text-on-surface border-outline-variant/30"
            }`}
          >
            <span className="material-symbols-outlined text-[16px]">
              {isSpeaking ? "volume_off" : "volume_up"}
            </span>
            <span className="hidden sm:inline">{isSpeaking ? "Mute" : "Listen Problem"}</span>
          </button>
        </div>
      </div>

      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-error-container/20 border border-error/30 text-error text-xs flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px]">error</span>
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Problem Statement Hero Deck */}
      <div className="p-6 sm:p-8 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-xl flex flex-col gap-4 relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="font-label-caps text-xs uppercase tracking-wider text-tertiary font-bold flex items-center gap-1.5">
            <span className="material-symbols-outlined text-[18px]">psychology</span>
            CASE GUESSTIMATE PROBLEM
          </span>
          <span className="font-label-numeric-sm text-[11px] px-2.5 py-0.5 rounded-full bg-tertiary-container/30 text-tertiary font-semibold">
            {difficulty}
          </span>
        </div>

        <h2 className="font-headline-md text-xl sm:text-2xl font-bold text-on-surface leading-relaxed">
          "{activeQuestion}"
        </h2>

        {/* 4-Step Golden Consulting Roadmap */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-outline-variant/20">
          <div className="p-2.5 rounded-lg bg-surface-container/60 border border-outline-variant/20 flex flex-col gap-1">
            <span className="font-label-caps text-[10px] text-tertiary font-bold">1. Clarify Bounds</span>
            <span className="text-[11px] text-outline leading-tight">Geography, timeframe, product scope</span>
          </div>
          <div className="p-2.5 rounded-lg bg-surface-container/60 border border-outline-variant/20 flex flex-col gap-1">
            <span className="font-label-caps text-[10px] text-tertiary font-bold">2. State Equation</span>
            <span className="text-[11px] text-outline leading-tight">State MECE formula before math</span>
          </div>
          <div className="p-2.5 rounded-lg bg-surface-container/60 border border-outline-variant/20 flex flex-col gap-1">
            <span className="font-label-caps text-[10px] text-tertiary font-bold">3. Proxies &amp; Math</span>
            <span className="text-[11px] text-outline leading-tight">Justify numbers &amp; calculate out loud</span>
          </div>
          <div className="p-2.5 rounded-lg bg-surface-container/60 border border-outline-variant/20 flex flex-col gap-1">
            <span className="font-label-caps text-[10px] text-tertiary font-bold">4. Reality Check</span>
            <span className="text-[11px] text-outline leading-tight">Check sanity against macro anchors</span>
          </div>
        </div>
      </div>

      {/* Articulation & Scratchpad Deck */}
      <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-lg flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-label-caps text-xs uppercase text-tertiary font-bold tracking-wider">
              Candidate Verbal Breakdown &amp; Scratchpad
            </span>
            {isRecording && (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-error/20 text-error text-[10px] font-semibold animate-pulse">
                <span className="w-1.5 h-1.5 rounded-full bg-error" />
                Live Audio Stream
              </span>
            )}
          </div>

          {/* Voice Mode Toggle Button */}
          <button
            type="button"
            onClick={toggleRecording}
            className={`px-4 py-2 rounded-xl font-headline-sm text-xs font-bold flex items-center gap-2 transition-all cursor-pointer ${
              isRecording
                ? "bg-error text-white shadow-lg shadow-error/25 animate-pulse"
                : "bg-surface-container-high hover:bg-surface-container-highest text-on-surface border border-outline-variant/30"
            }`}
          >
            <span className="material-symbols-outlined text-[18px]">
              {isRecording ? "stop" : "mic"}
            </span>
            <span>{isRecording ? "Finish Speaking" : "Answer Verbally (Microphone)"}</span>
          </button>
        </div>

        {isRecording && (
          <LiveConfidenceNeedle emotion={liveEmotion} isRecording={isRecording} />
        )}

        <LiveCoachNudge nudge={nudge} />

        {/* Articulation Text Area */}
        <textarea
          rows={10}
          value={answerText}
          onChange={(e) => setAnswerText(e.target.value)}
          placeholder="Speak into your microphone or structure your breakdown here:
1. Clarifications & Scope: (e.g., Focus on India, retail consumer sales, annual volume)
2. Formula / MECE Tree: Total = Population × Target Demographic % × Penetration % × Frequency
3. Assumptions & Calculations: (Walk through the numbers step-by-step...)
4. Sanity Check: (Why does this final figure make sense?)"
          className="w-full p-4 rounded-xl bg-surface-container border border-outline-variant/40 text-on-surface text-sm font-mono leading-relaxed focus:outline-none focus:border-tertiary transition-colors resize-y min-h-[220px]"
        />

        {/* Action Bottom Strip */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-2">
          <div className="flex items-center gap-3 text-xs text-outline">
            <span className="font-label-numeric-sm">{answerText.trim().split(/\s+/).filter(Boolean).length} words</span>
            <span>•</span>
            <span>Approach: <strong className="text-on-surface">{FRAMEWORK_MODES.find((f) => f.id === approachType)?.title}</strong></span>
          </div>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={isSubmitting || !answerText.trim()}
            className="py-3 px-6 rounded-xl bg-gradient-to-r from-tertiary via-emerald-500 to-teal-500 hover:opacity-95 text-on-tertiary font-headline-sm text-sm font-bold flex items-center justify-center gap-2 shadow-lg shadow-tertiary/20 cursor-pointer disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <span className="material-symbols-outlined animate-spin text-[18px]">sync</span>
                <span>Evaluating Breakdown &amp; Math...</span>
              </>
            ) : (
              <>
                <span>Submit Solution for MBB Review</span>
                <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
