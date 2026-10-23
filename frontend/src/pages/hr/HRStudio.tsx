import { useState, useEffect, useRef } from "react";
import { useNavigate, useParams, useSearchParams, Link } from "react-router-dom";
import {
  getHRTracks,
  startHRInterview,
  submitHRAnswer,
  getHRSession,
  HRQuestionItem,
  HRTrackInfo,
} from "../../api/hr";

const ROLE_PRESETS = [
  "Software Development Engineer",
  "Full Stack Developer",
  "Frontend Engineer",
  "Backend Systems Engineer",
  "Product Analyst / Associate PM",
];

export default function HRStudio() {
  const navigate = useNavigate();
  const { sessionId: paramSessionId } = useParams<{ sessionId?: string }>();
  const [searchParams] = useSearchParams();

  // Setup state
  const [role, setRole] = useState("Software Development Engineer");
  const [customRole, setCustomRole] = useState("");
  const [targetCompany, setTargetCompany] = useState("");
  const [interviewMode, setInterviewMode] = useState("standard_hr");
  const [maxQuestions, setMaxQuestions] = useState(4);
  const [tracks, setTracks] = useState<HRTrackInfo[]>([]);

  // Active Session state
  const [sessionId, setSessionId] = useState<number | null>(() => {
    if (paramSessionId) return Number(paramSessionId);
    const qId = searchParams.get("session_id");
    if (qId) return Number(qId);
    const cached = localStorage.getItem("speakflow_active_hr_session");
    return cached ? Number(cached) : null;
  });

  const [currentQuestion, setCurrentQuestion] = useState<HRQuestionItem | null>(null);
  const [questionCount, setQuestionCount] = useState(0);
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

  // 1. Fetch tracks on mount
  useEffect(() => {
    getHRTracks()
      .then((data) => setTracks(data.tracks))
      .catch((err) => console.warn("Could not load HR tracks:", err));
  }, []);

  // 2. Restore active session if sessionId exists
  useEffect(() => {
    let mounted = true;
    if (sessionId && !currentQuestion) {
      setIsRestoring(true);
      getHRSession(sessionId)
        .then((data) => {
          if (!mounted) return;
          if (data.is_complete) {
            localStorage.removeItem("speakflow_active_hr_session");
            navigate(`/hr/report/${sessionId}`, { replace: true });
          } else if (data.current_question) {
            setCurrentQuestion(data.current_question);
            setQuestionCount(data.question_count || 0);
            setMaxQuestions(data.max_questions || 4);
            if (data.role) setRole(data.role);
            if (data.target_company) setTargetCompany(data.target_company);
            if (data.interview_mode) setInterviewMode(data.interview_mode);
            localStorage.setItem("speakflow_active_hr_session", String(sessionId));
          }
        })
        .catch((err) => {
          console.warn("Could not restore HR session:", err);
          localStorage.removeItem("speakflow_active_hr_session");
          setSessionId(null);
        })
        .finally(() => {
          if (mounted) setIsRestoring(false);
        });
    }
    return () => {
      mounted = false;
    };
  }, [sessionId, currentQuestion, navigate]);

  // 3. Timer effect
  useEffect(() => {
    let timer: any;
    if (sessionId && !isRestoring) {
      timer = setInterval(() => setElapsedSeconds((s) => s + 1), 1000);
    }
    return () => clearInterval(timer);
  }, [sessionId, isRestoring]);

  // 4. Speech Recognition setup
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
        setErrorMsg("Microphone permission denied. You can continue by typing your answer in the scratchpad.");
      }
    }
  };

  const handleStartInterview = async () => {
    const activeRole = role === "Custom" ? customRole.trim() : role;
    if (!activeRole) {
      setErrorMsg("Please select or enter your target role.");
      return;
    }

    setIsStarting(true);
    setErrorMsg(null);

    try {
      const res = await startHRInterview({
        role: activeRole,
        target_company: targetCompany.trim() || undefined,
        interview_mode: interviewMode,
        max_questions: maxQuestions,
      });

      setSessionId(res.session_id);
      setCurrentQuestion(res.current_question);
      setQuestionCount(0);
      setElapsedSeconds(0);
      setAnswerText("");
      setRecordedAudioBlob(null);
      localStorage.setItem("speakflow_active_hr_session", String(res.session_id));
      if (res.current_question?.text) {
        handleSpeakQuestion(res.current_question.text);
      }
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to initialize HR interview session.");
    } finally {
      setIsStarting(false);
    }
  };

  const handleSubmitAnswer = async () => {
    if (!sessionId || !answerText.trim()) {
      setErrorMsg("Please provide an answer before submitting.");
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
      const res = await submitHRAnswer(sessionId, answerText.trim(), recordedAudioBlob);

      if (res.is_complete && res.report) {
        localStorage.removeItem("speakflow_active_hr_session");
        navigate(`/hr/report/${sessionId}`);
      } else if (res.next_question) {
        setCurrentQuestion(res.next_question);
        setQuestionCount(res.question_count);
        setAnswerText("");
        setRecordedAudioBlob(null);
        if (res.next_question.text) {
          handleSpeakQuestion(res.next_question.text);
        }
      }
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to evaluate behavioral response.");
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
        <div className="w-12 h-12 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        <span className="font-headline-sm text-sm text-on-surface-variant font-medium">
          Restoring active HR &amp; Behavioral session...
        </span>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // RENDER: SETUP VIEW
  // -------------------------------------------------------------------------
  if (!sessionId || !currentQuestion) {
    return (
      <div className="relative w-full overflow-hidden px-4 sm:px-8 py-8 sm:py-10 max-w-7xl mx-auto flex flex-col gap-8">
        {/* Ambient Backdrop Aura */}
        <div className="pointer-events-none absolute -top-40 right-1/4 w-[700px] h-[400px] bg-primary/10 rounded-full blur-[140px]" />
        <div className="pointer-events-none absolute top-1/2 -left-20 w-[500px] h-[350px] bg-secondary-container/10 rounded-full blur-[120px]" />

        {/* Header Breadcrumbs & Title */}
        <div className="relative z-10 flex flex-col gap-2">
          <div className="flex items-center gap-2 text-xs text-outline font-label-caps">
            <Link to="/" className="hover:text-on-surface transition-colors">Practice Arena</Link>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <span className="text-primary font-semibold">Track 02: HR &amp; Behavioral Round</span>
          </div>

          <div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-surface-container-high text-primary font-label-numeric-sm text-[11px] font-medium mb-2">
              <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
              STAR Method &amp; Personal Ownership Diagnostics
            </div>
            <h1 className="font-display-hero text-3xl sm:text-4xl font-extrabold text-on-surface tracking-tight">
              HR &amp; Behavioral Interview Studio
            </h1>
            <p className="font-body-lg text-sm text-on-surface-variant max-w-3xl leading-relaxed mt-1">
              Master behavioral storytelling for campus placements. Practice Situation-Task-Action-Result structure,
              personal "I" vs. "We" ownership conviction, conflict resolution, and authentic culture fit.
            </p>
          </div>
        </div>

        {errorMsg && (
          <div className="p-4 rounded-xl bg-error-container/20 border border-error/30 text-error text-xs flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px]">error</span>
            <span>{errorMsg}</span>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Column: Role & Track (7 Cols) */}
          <div className="lg:col-span-7 flex flex-col gap-6">
            {/* Step 1: Target Role & Company */}
            <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-4 shadow-lg">
              <span className="font-label-caps text-xs uppercase text-primary font-bold tracking-wider">
                Step 1: Target Role &amp; Organization
              </span>

              <div className="flex flex-col gap-3">
                <label className="text-xs text-outline font-label-caps uppercase font-semibold">
                  Engineering / Placement Role
                </label>
                <div className="flex flex-wrap gap-2">
                  {ROLE_PRESETS.map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => {
                        setRole(p);
                        setCustomRole("");
                      }}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                        role === p
                          ? "bg-primary text-on-primary border-primary shadow-sm"
                          : "bg-surface-container text-on-surface-variant border-outline-variant/30 hover:bg-surface-container-high"
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => setRole("Custom")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                      role === "Custom"
                        ? "bg-primary text-on-primary border-primary shadow-sm"
                        : "bg-surface-container text-on-surface-variant border-outline-variant/30 hover:bg-surface-container-high"
                    }`}
                  >
                    Custom
                  </button>
                </div>

                {role === "Custom" && (
                  <input
                    type="text"
                    placeholder="e.g. Solutions Architect, Data Platform Engineer..."
                    value={customRole}
                    onChange={(e) => setCustomRole(e.target.value)}
                    className="w-full mt-2 px-3.5 py-2.5 rounded-lg bg-surface-container border border-outline-variant/40 text-on-surface text-xs focus:outline-none focus:border-primary transition-colors"
                  />
                )}

                {/* Target Company */}
                <div className="pt-2 border-t border-outline-variant/20">
                  <label className="text-xs text-outline font-label-caps uppercase block mb-1.5 font-semibold">
                    Target Company (Optional)
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Google, Amazon, Microsoft, McKinsey, Early-stage Seed..."
                    value={targetCompany}
                    onChange={(e) => setTargetCompany(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-lg bg-surface-container border border-outline-variant/40 text-on-surface text-xs focus:outline-none focus:border-primary transition-colors"
                  />
                </div>
              </div>
            </div>

            {/* Step 2: Behavioral Focus Track */}
            <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-4 shadow-lg">
              <span className="font-label-caps text-xs uppercase text-primary font-bold tracking-wider">
                Step 2: Behavioral Focus Track
              </span>

              <div className="flex flex-col gap-2.5">
                {/* Standard Comprehensive Card */}
                <button
                  type="button"
                  onClick={() => setInterviewMode("standard_hr")}
                  className={`p-4 rounded-xl text-left border transition-all flex items-start justify-between gap-3 ${
                    interviewMode === "standard_hr"
                      ? "bg-primary-container/20 border-primary text-on-surface shadow-md shadow-primary/10"
                      : "bg-surface-container border-outline-variant/20 hover:border-outline-variant/60 text-on-surface-variant"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <span className="material-symbols-outlined text-primary text-[22px] mt-0.5">star</span>
                    <div>
                      <span className="font-headline-sm text-sm font-bold text-on-surface block">
                        Comprehensive Campus Placement Drill (Recommended)
                      </span>
                      <span className="text-xs text-outline leading-snug mt-0.5 block">
                        Rotates across Leadership, Conflict Resolution, Past Failures, and Company Culture Fit.
                      </span>
                    </div>
                  </div>
                  {interviewMode === "standard_hr" && (
                    <span className="material-symbols-outlined text-primary text-[18px]">check_circle</span>
                  )}
                </button>

                {/* Individual Behavioral Tracks */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {tracks.map((t) => {
                    const isSelected = interviewMode === t.id;
                    return (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => setInterviewMode(t.id)}
                        className={`p-3.5 rounded-xl text-left border transition-all flex flex-col justify-between gap-2 ${
                          isSelected
                            ? "bg-primary-container/20 border-primary text-on-surface shadow-sm shadow-primary/10"
                            : "bg-surface-container border-outline-variant/20 hover:border-outline-variant/50 text-on-surface-variant"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="material-symbols-outlined text-primary text-[20px]">{t.icon}</span>
                          {isSelected && (
                            <span className="material-symbols-outlined text-primary text-[16px]">check_circle</span>
                          )}
                        </div>
                        <div>
                          <span className="font-headline-sm text-xs font-bold text-on-surface block">
                            {t.title}
                          </span>
                          <span className="text-[11px] text-outline leading-tight mt-0.5 block">
                            {t.desc}
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: Question Depth & Launch (5 Cols) */}
          <div className="lg:col-span-5 flex flex-col gap-6">
            <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-5 shadow-lg relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 rounded-full blur-3xl pointer-events-none" />

              <div className="flex items-center justify-between">
                <span className="font-label-caps text-xs uppercase text-primary font-bold tracking-wider">
                  Session Depth
                </span>
                <span className="text-xs text-outline font-label-numeric-sm">4 Questions Bar</span>
              </div>

              {/* Question Count Pills */}
              <div>
                <label className="text-xs text-outline font-label-caps uppercase block mb-2 font-semibold">
                  Number of Behavioral Scenarios
                </label>
                <div className="flex items-center gap-2">
                  {[3, 4, 5].map((num) => (
                    <button
                      key={num}
                      type="button"
                      onClick={() => setMaxQuestions(num)}
                      className={`flex-1 py-2.5 rounded-lg text-xs font-semibold border transition-all ${
                        maxQuestions === num
                          ? "bg-primary text-on-primary border-primary font-bold shadow-sm"
                          : "bg-surface-container text-on-surface-variant border-outline-variant/30 hover:bg-surface-container-high"
                      }`}
                    >
                      {num} Questions
                    </button>
                  ))}
                </div>
              </div>

              {/* Behavioral Rubric Preview */}
              <div className="p-4 rounded-xl bg-surface-container/60 border border-outline-variant/20 flex flex-col gap-2.5">
                <span className="text-xs text-outline font-label-caps uppercase font-semibold">
                  What Interviewers Evaluate:
                </span>
                <div className="flex flex-col gap-2 text-[11px] text-on-surface-variant">
                  <div className="flex items-start gap-2">
                    <span className="material-symbols-outlined text-primary text-[15px] mt-0.5">verified_user</span>
                    <span><strong>Personal Ownership:</strong> High "I" agency vs. vague "we" deflection</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="material-symbols-outlined text-primary text-[15px] mt-0.5">view_timeline</span>
                    <span><strong>STAR Rigor:</strong> Situation, Task, Action, and Measurable Result</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="material-symbols-outlined text-primary text-[15px] mt-0.5">psychology</span>
                    <span><strong>Emotional Maturity:</strong> Conflict de-escalation &amp; self-awareness</span>
                  </div>
                </div>
              </div>

              {/* Launch CTA */}
              <button
                type="button"
                onClick={handleStartInterview}
                disabled={isStarting}
                className="w-full py-3.5 px-6 rounded-xl bg-gradient-to-r from-primary via-indigo-500 to-purple-600 hover:opacity-95 transition-all text-on-primary font-headline-sm text-sm font-bold flex items-center justify-center gap-2 shadow-lg shadow-primary/20 cursor-pointer disabled:opacity-50"
              >
                {isStarting ? (
                  <>
                    <span className="material-symbols-outlined animate-spin text-[20px]">refresh</span>
                    <span>Synthesizing Question 1...</span>
                  </>
                ) : (
                  <>
                    <span>Launch Behavioral Interview</span>
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
  // RENDER: LIVE INTERVIEW STUDIO
  // -------------------------------------------------------------------------
  return (
    <div className="relative w-full overflow-hidden px-4 sm:px-8 py-8 sm:py-10 max-w-6xl mx-auto flex flex-col gap-6">
      {/* Ambient Backdrop Aura */}
      <div className="pointer-events-none absolute -top-40 right-1/4 w-[700px] h-[400px] bg-primary/10 rounded-full blur-[140px]" />
      <div className="pointer-events-none absolute top-1/2 -left-20 w-[500px] h-[350px] bg-secondary/10 rounded-full blur-[120px]" />

      {/* Studio Header Strip */}
      <div className="relative z-10 flex items-center justify-between p-4 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-md">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
            <span className="material-symbols-outlined text-[22px]">record_voice_over</span>
          </div>
          <div className="flex flex-col">
            <span className="font-headline-sm text-sm font-bold text-on-surface">{role}</span>
            <div className="flex items-center gap-2 text-[11px] text-outline font-label-caps uppercase font-medium">
              <span>{targetCompany ? `Target: ${targetCompany}` : "HR Behavioral Round"}</span>
              <span className="text-outline/40">•</span>
              <span className="text-primary font-semibold">
                Question {questionCount + 1} of {maxQuestions}
              </span>
            </div>
          </div>
        </div>

        {/* Stepper & Timer */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 font-label-numeric-sm text-xs text-on-surface bg-surface-container px-3 py-1.5 rounded-lg border border-outline-variant/20">
            <span className="material-symbols-outlined text-[16px] text-primary">schedule</span>
            <span>{formatTimer(elapsedSeconds)}</span>
          </div>

          <button
            type="button"
            onClick={() => handleSpeakQuestion(currentQuestion.text)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold font-label-caps flex items-center gap-1.5 transition-colors border ${
              isSpeaking
                ? "bg-secondary text-on-secondary border-secondary"
                : "bg-surface-container text-outline hover:text-on-surface border-outline-variant/30"
            }`}
          >
            <span className="material-symbols-outlined text-[16px]">
              {isSpeaking ? "volume_off" : "volume_up"}
            </span>
            <span className="hidden sm:inline">{isSpeaking ? "Mute" : "Listen"}</span>
          </button>
        </div>
      </div>

      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-error-container/20 border border-error/30 text-error text-xs flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px]">error</span>
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Main Question Card Deck */}
      <div className="p-6 sm:p-8 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-xl flex flex-col gap-4 relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="font-label-caps text-xs uppercase tracking-wider text-primary font-bold flex items-center gap-1.5">
            <span className="material-symbols-outlined text-[18px]">psychology</span>
            BEHAVIORAL CHALLENGE #{questionCount + 1}
          </span>
          <span className="font-label-numeric-sm text-[11px] px-2.5 py-0.5 rounded-full bg-primary-container/30 text-primary font-semibold">
            STAR Method Grounding
          </span>
        </div>

        <h2 className="font-headline-md text-xl sm:text-2xl font-bold text-on-surface leading-relaxed">
          "{currentQuestion.text}"
        </h2>

        {/* STAR Guidance Hints */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-outline-variant/20">
          <div className="p-2.5 rounded-lg bg-surface-container/60 border border-outline-variant/20 flex flex-col gap-0.5">
            <span className="font-label-caps text-[10px] text-primary font-bold">1. Situation</span>
            <span className="text-[11px] text-outline leading-tight">Context, team, project constraints</span>
          </div>
          <div className="p-2.5 rounded-lg bg-surface-container/60 border border-outline-variant/20 flex flex-col gap-0.5">
            <span className="font-label-caps text-[10px] text-primary font-bold">2. Task</span>
            <span className="text-[11px] text-outline leading-tight">Your specific assignment or hurdle</span>
          </div>
          <div className="p-2.5 rounded-lg bg-surface-container/60 border border-outline-variant/20 flex flex-col gap-0.5">
            <span className="font-label-caps text-[10px] text-primary font-bold">3. Action ("I")</span>
            <span className="text-[11px] text-outline leading-tight">What YOU specifically decided/coded</span>
          </div>
          <div className="p-2.5 rounded-lg bg-surface-container/60 border border-outline-variant/20 flex flex-col gap-0.5">
            <span className="font-label-caps text-[10px] text-primary font-bold">4. Result</span>
            <span className="text-[11px] text-outline leading-tight">Measurable outcome &amp; lasting lesson</span>
          </div>
        </div>
      </div>

      {/* Articulation & Scratchpad Deck */}
      <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-lg flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-label-caps text-xs uppercase text-primary font-bold tracking-wider">
              Candidate Spoken Narrative &amp; Notes
            </span>
            {isRecording && (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-error/20 text-error text-[10px] font-semibold animate-pulse">
                <span className="w-1.5 h-1.5 rounded-full bg-error" />
                Live Recording
              </span>
            )}
          </div>

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

        <textarea
          rows={9}
          value={answerText}
          onChange={(e) => setAnswerText(e.target.value)}
          placeholder="Speak into your microphone or write your behavioral answer here:
- Situation: (Set the context, project, or team challenge...)
- Task: (What was your personal objective or obstacle?)
- Action: (Focus on 'I decided...', 'I researched...', 'I mediated...')
- Result: (What was the measurable outcome or learning?)"
          className="w-full p-4 rounded-xl bg-surface-container border border-outline-variant/40 text-on-surface text-sm font-sans leading-relaxed focus:outline-none focus:border-primary transition-colors resize-y min-h-[200px]"
        />

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-2">
          <div className="flex items-center gap-3 text-xs text-outline">
            <span className="font-label-numeric-sm">{answerText.trim().split(/\s+/).filter(Boolean).length} words</span>
            <span>•</span>
            <span>Targeting: <strong className="text-on-surface font-semibold">Personal Ownership &amp; Evidence</strong></span>
          </div>

          <button
            type="button"
            onClick={handleSubmitAnswer}
            disabled={isSubmitting || !answerText.trim()}
            className="py-3 px-6 rounded-xl bg-gradient-to-r from-primary via-indigo-500 to-purple-600 hover:opacity-95 text-on-primary font-headline-sm text-sm font-bold flex items-center justify-center gap-2 shadow-lg shadow-primary/20 cursor-pointer disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <span className="material-symbols-outlined animate-spin text-[18px]">sync</span>
                <span>Evaluating Behavioral Response...</span>
              </>
            ) : (
              <>
                <span>Submit Behavioral Answer</span>
                <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
