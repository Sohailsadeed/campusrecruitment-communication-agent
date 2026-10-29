import { useState, useEffect, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  startTechnicalInterview,
  submitTechnicalAnswer,
  uploadResume,
  getResumeStatus,
  clearResume,
  getTechnicalSession,
  QuestionItem,
} from "../../api/technical";
import { useLiveEmotionStream } from "../../hooks/useLiveEmotionStream";
import LiveConfidenceNeedle from "../../components/Interview/LiveConfidenceNeedle";

const ROLE_PRESETS = [
  { label: "Full Stack Engineer", icon: "layers", desc: "React, Node.js, distributed caches, and system design" },
  { label: "Backend Systems Engineer", icon: "dns", desc: "High-throughput APIs, microservices, and databases" },
  { label: "Machine Learning Engineer", icon: "neurology", desc: "Model deployment, pipelines, and evaluation" },
  { label: "DevOps & Cloud Architect", icon: "cloud", desc: "Kubernetes, CI/CD, incident mitigation, and reliability" },
];

export const COMPANY_TIERS = [
  {
    id: "tier1_product",
    name: "FAANG / Tier-1 Product",
    bar: "Senior Scale & Systems Bar",
    icon: "hub",
    desc: "Millions of QPS, low latency, microservices resilience, CAP theorem, and deep fault tolerance.",
    presets: ["Google", "Meta", "Amazon", "Uber"],
  },
  {
    id: "growth_startup",
    name: "High-Growth Startup",
    bar: "Velocity & Practical Trade-offs",
    icon: "bolt",
    desc: "Rapid feature velocity vs tech debt, pragmatic API design, asynchronous workers, and traffic spikes.",
    presets: ["Stripe", "Airbnb", "Razorpay", "Postman"],
  },
  {
    id: "enterprise_service",
    name: "Enterprise & Service Giants",
    bar: "Core Fundamentals & SDLC",
    icon: "corporate_fare",
    desc: "SOLID OOP design, clean debugging, relational databases (ACID), and robust client contracts.",
    presets: ["TCS", "Infosys", "Accenture", "Wipro"],
  },
  {
    id: "early_seed",
    name: "Early-Stage Seed / 0-to-1",
    bar: "0-to-1 Builder & Ambiguity",
    icon: "construction",
    desc: "End-to-end fullstack ownership, building MVPs with speed, and navigating ambiguous requirements.",
    presets: ["Seed Startup", "Stealth AI", "YC Batch"],
  },
];

export default function TechnicalStudio() {
  const navigate = useNavigate();
  const { sessionId: paramSessionId } = useParams<{ sessionId?: string }>();
  const [searchParams] = useSearchParams();

  // Setup State
  const [role, setRole] = useState("Full Stack Engineer");
  const [customRole, setCustomRole] = useState("");
  const [targetCompany, setTargetCompany] = useState("");
  const [companyTier, setCompanyTier] = useState("tier1_product");
  const [maxQuestions, setMaxQuestions] = useState(5);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeUploadedName, setResumeUploadedName] = useState("");
  const [uploadingResume, setUploadingResume] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const [isCheckingResume, setIsCheckingResume] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Active Session State
  const [sessionId, setSessionId] = useState<number | null>(() => {
    if (paramSessionId) return Number(paramSessionId);
    const queryId = searchParams.get("session_id");
    if (queryId) return Number(queryId);
    const cached = localStorage.getItem("speakflow_active_technical_session");
    return cached ? Number(cached) : null;
  });
  const [currentQuestion, setCurrentQuestion] = useState<QuestionItem | null>(null);
  const [questionCount, setQuestionCount] = useState(0);
  const [answerText, setAnswerText] = useState("");
  const [isRestoringSession, setIsRestoringSession] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Voice Mode (Speech Recognition & MediaRecorder)
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [recordedAudioBlob, setRecordedAudioBlob] = useState<Blob | null>(null);
  const recognitionRef = useRef<any>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const { liveEmotion } = useLiveEmotionStream(sessionId, isRecording);

  // Check if candidate already has an indexed resume from a prior session
  useEffect(() => {
    let mounted = true;
    getResumeStatus()
      .then((status) => {
        if (!mounted) return;
        if (status.has_resume) {
          setResumeUploadedName(status.resume_name || "Active Resume on File");
          setUploadSuccess(true);
        }
      })
      .catch((err) => {
        console.warn("Could not check resume status:", err);
      })
      .finally(() => {
        if (mounted) setIsCheckingResume(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  // Restore ongoing active session if navigating back from dashboard/progress
  useEffect(() => {
    let mounted = true;
    if (sessionId && !currentQuestion) {
      setIsRestoringSession(true);
      getTechnicalSession(sessionId)
        .then((data) => {
          if (!mounted) return;
          if (data.is_complete) {
            // Already finished -> clean cache and redirect to report
            localStorage.removeItem("speakflow_active_technical_session");
            navigate(`/technical/report/${sessionId}`, { replace: true });
          } else if (data.current_question) {
            setCurrentQuestion(data.current_question);
            setQuestionCount(data.question_count || 0);
            if (data.role) setRole(data.role);
            if (data.target_company) setTargetCompany(data.target_company);
            if (data.company_tier) setCompanyTier(data.company_tier);
            localStorage.setItem("speakflow_active_technical_session", String(sessionId));
          }
        })
        .catch((err) => {
          console.warn("Could not restore technical interview session:", err);
          localStorage.removeItem("speakflow_active_technical_session");
          setSessionId(null);
        })
        .finally(() => {
          if (mounted) setIsRestoringSession(false);
        });
    }
    return () => {
      mounted = false;
    };
  }, [sessionId, currentQuestion, navigate]);

  // Timer effect
  useEffect(() => {
    let timer: any;
    if (sessionId) {
      timer = setInterval(() => setElapsedSeconds((s) => s + 1), 1000);
    }
    return () => clearInterval(timer);
  }, [sessionId]);

  // Speech Recognition setup
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

  const toggleRecording = async () => {
    if (isRecording) {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
      setIsRecording(false);
    } else {
      setRecordedAudioBlob(null);
      audioChunksRef.current = [];

      // Start MediaRecorder to capture audio stream for playback in report
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
          recorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) {
              audioChunksRef.current.push(e.data);
            }
          };
          recorder.onstop = () => {
            const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
            setRecordedAudioBlob(blob);
            stream.getTracks().forEach((track) => track.stop());
          };
          recorder.start();
          mediaRecorderRef.current = recorder;
        } catch (err) {
          console.warn("Could not start MediaRecorder for audio playback:", err);
        }
      }

      if (recognitionRef.current) {
        recognitionRef.current.start();
        setIsRecording(true);
      } else {
        alert("Voice recognition is not supported in this browser. Please use Chrome or Edge.");
      }
    }
  };

  const handleSpeakQuestion = (text: string) => {
    if (!("speechSynthesis" in window)) return;
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

  const handleResumeUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setResumeFile(file);
    setUploadingResume(true);
    setErrorMsg(null);

    try {
      const res = await uploadResume(file);
      setResumeUploadedName(res.resume_name);
      setUploadSuccess(true);
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to upload and index resume in ChromaDB.");
    } finally {
      setUploadingResume(false);
    }
  };

  const handleClearResume = async () => {
    try {
      await clearResume();
      setResumeFile(null);
      setResumeUploadedName("");
      setUploadSuccess(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (err: any) {
      setErrorMsg("Failed to detach resume.");
    }
  };

  const handleStartInterview = async () => {
    const activeRole = role === "Custom" ? customRole.trim() : role;
    if (!activeRole) {
      setErrorMsg("Please select or enter a target role.");
      return;
    }
    setIsStarting(true);
    setErrorMsg(null);

    try {
      const res = await startTechnicalInterview({
        role: activeRole,
        target_company: targetCompany.trim() || undefined,
        company_tier: companyTier,
        max_questions: maxQuestions,
      });

      setSessionId(res.session_id);
      setCurrentQuestion(res.current_question);
      setQuestionCount(0);
      setElapsedSeconds(0);
      setAnswerText("");
      localStorage.setItem("speakflow_active_technical_session", String(res.session_id));
      if (res.current_question?.text) {
        handleSpeakQuestion(res.current_question.text);
      }
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to initialize technical interview session.");
    } finally {
      setIsStarting(false);
    }
  };

  const handleSubmitAnswer = async () => {
    if (!sessionId || !answerText.trim()) {
      setErrorMsg("Please provide an answer before submitting.");
      return;
    }
    if (isRecording && recognitionRef.current) {
      recognitionRef.current.stop();
      setIsRecording(false);
    }
    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      const res = await submitTechnicalAnswer(sessionId, answerText.trim(), recordedAudioBlob);

      if (res.is_complete && res.report) {
        // Complete -> remove cached active session and go to report
        localStorage.removeItem("speakflow_active_technical_session");
        navigate(`/technical/report/${sessionId}`);
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
      setErrorMsg(err?.response?.data?.detail || "Failed to evaluate answer.");
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
  // RENDER: RESTORING OR SETUP VIEW
  // -------------------------------------------------------------------------
  if (isRestoringSession) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-[70vh] gap-4">
        <div className="w-12 h-12 rounded-full border-2 border-secondary border-t-transparent animate-spin" />
        <span className="font-headline-sm text-sm text-on-surface-variant font-medium">
          Restoring your active Technical Interview session...
        </span>
      </div>
    );
  }

  if (!sessionId || !currentQuestion) {
    return (
      <div className="relative w-full overflow-hidden px-4 sm:px-8 py-8 sm:py-10 max-w-7xl mx-auto flex flex-col gap-8">
        {/* Ambient Backdrop Aura */}
        <div className="pointer-events-none absolute -top-40 right-1/4 w-[700px] h-[400px] bg-primary/10 rounded-full blur-[140px]" />
        <div className="pointer-events-none absolute top-1/2 -left-20 w-[500px] h-[350px] bg-secondary-container/10 rounded-full blur-[120px]" />

        {/* Header Breadcrumb & Title */}
        <div className="relative z-10 flex flex-col gap-2">
          <div className="flex items-center gap-2 text-xs text-outline font-label-caps">
            <span className="hover:text-on-surface cursor-pointer" onClick={() => navigate("/")}>Practice Arena</span>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <span className="text-secondary font-semibold">Track 01: Technical Interview</span>
          </div>
          <div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-surface-container-high text-secondary font-label-numeric-sm text-[11px] font-medium mb-2">
              <span className="w-1.5 h-1.5 rounded-full bg-secondary animate-pulse" />
              RAG Semantic &amp; Logic Telemetry
            </div>
            <h1 className="font-display-hero text-3xl sm:text-4xl font-extrabold text-on-surface tracking-tight">
              Technical System Design &amp; Logic Articulation
            </h1>
            <p className="font-body-lg text-sm text-on-surface-variant max-w-3xl leading-relaxed mt-1">
              Practice conversational technical interviews grounded in your actual projects. Powered by
              RAG semantic resume indexing, LangGraph state orchestration, and real-time Nemotron evaluation.
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
          {/* Left Column: Role & Config (7 Cols) */}
          <div className="lg:col-span-7 flex flex-col gap-6">
            {/* Target Role Selector */}
            <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-4 shadow-lg">
              <div className="flex items-center justify-between">
                <span className="font-label-caps text-xs uppercase text-secondary font-bold tracking-wider">
                  Select Target Engineering Role
                </span>
                <span className="text-xs text-outline font-label-numeric-sm">Step 1 of 3</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {ROLE_PRESETS.map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    onClick={() => {
                      setRole(p.label);
                      setCustomRole("");
                    }}
                    className={`p-4 rounded-xl text-left border transition-all flex flex-col justify-between gap-2 ${
                      role === p.label
                        ? "bg-secondary-container/20 border-secondary text-on-surface shadow-md shadow-secondary/10"
                        : "bg-surface-container border-outline-variant/20 hover:border-outline-variant/60 text-on-surface-variant"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="material-symbols-outlined text-secondary text-[22px]">{p.icon}</span>
                      {role === p.label && (
                        <span className="material-symbols-outlined text-secondary text-[18px]">check_circle</span>
                      )}
                    </div>
                    <span className="font-headline-sm text-sm font-semibold text-on-surface">{p.label}</span>
                    <span className="text-[11px] text-outline leading-tight">{p.desc}</span>
                  </button>
                ))}
              </div>

              {/* Custom Role Input */}
              <div className="pt-2">
                <label className="text-xs text-outline font-label-caps uppercase block mb-1.5 font-semibold">
                  Or Specify Custom Specialization
                </label>
                <input
                  type="text"
                  placeholder="e.g. Distributed Database Engineer, Computer Vision Architect..."
                  value={customRole}
                  onChange={(e) => {
                    setCustomRole(e.target.value);
                    setRole("Custom");
                  }}
                  className="w-full px-3.5 py-2.5 rounded-lg bg-surface-container border border-outline-variant/40 text-on-surface text-xs focus:outline-none focus:border-secondary transition-colors"
                />
              </div>
            </div>

            {/* Target Company Calibration & Environment */}
            <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-5 shadow-lg">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                <span className="font-label-caps text-xs uppercase text-secondary font-bold tracking-wider flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-[18px]">tune</span>
                  Target Company Calibration &amp; Tier
                </span>
                <span className="text-xs text-outline font-label-numeric-sm">Step 2 of 3</span>
              </div>
              <p className="text-xs text-on-surface-variant leading-relaxed -mt-2">
                Pre-calibrates the interviewer's technical bar, scenario complexity, and architectural expectations.
              </p>

              {/* 4 Interactive Calibration Tiers */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {COMPANY_TIERS.map((tier) => {
                  const isSelected = companyTier === tier.id;
                  return (
                    <button
                      key={tier.id}
                      type="button"
                      onClick={() => {
                        setCompanyTier(tier.id);
                        if (!targetCompany || COMPANY_TIERS.some((t) => t.presets.includes(targetCompany))) {
                          setTargetCompany(tier.presets[0]);
                        }
                      }}
                      className={`p-3.5 rounded-xl text-left border transition-all flex flex-col justify-between gap-2.5 ${
                        isSelected
                          ? "bg-secondary-container/20 border-secondary text-on-surface shadow-md shadow-secondary/10"
                          : "bg-surface-container border-outline-variant/20 hover:border-outline-variant/60 text-on-surface-variant"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className={`material-symbols-outlined text-[20px] ${isSelected ? "text-secondary" : "text-outline"}`}>
                            {tier.icon}
                          </span>
                          <span className="font-headline-sm text-xs font-bold text-on-surface">
                            {tier.name}
                          </span>
                        </div>
                        {isSelected && (
                          <span className="material-symbols-outlined text-secondary text-[16px]">check_circle</span>
                        )}
                      </div>

                      <span className="text-[11px] text-outline leading-snug">
                        {tier.desc}
                      </span>

                      <div className="pt-1">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-label-numeric-sm font-semibold ${
                          isSelected ? "bg-secondary text-on-secondary" : "bg-surface-container-high text-outline"
                        }`}>
                          {tier.bar}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Company Quick-Select Chips */}
              <div className="flex flex-col gap-2 pt-1">
                <span className="text-xs text-outline font-label-caps uppercase font-semibold">
                  Quick-Fill Placement Presets ({COMPANY_TIERS.find((t) => t.id === companyTier)?.name})
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  {COMPANY_TIERS.find((t) => t.id === companyTier)?.presets.map((preset) => (
                    <button
                      key={preset}
                      type="button"
                      onClick={() => setTargetCompany(preset)}
                      className={`px-3 py-1 rounded-lg text-xs font-medium border transition-all ${
                        targetCompany.toLowerCase() === preset.toLowerCase()
                          ? "bg-secondary text-on-secondary border-secondary font-bold shadow-sm"
                          : "bg-surface-container text-on-surface-variant border-outline-variant/30 hover:bg-surface-container-high"
                      }`}
                    >
                      {preset}
                    </button>
                  ))}
                  {targetCompany && (
                    <button
                      type="button"
                      onClick={() => setTargetCompany("")}
                      className="px-2 py-1 rounded-lg text-[11px] text-outline hover:text-error transition-colors"
                      title="Clear custom company"
                    >
                      Clear
                    </button>
                  )}
                </div>
              </div>

              {/* Company Name Input & Question Depth */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1 border-t border-outline-variant/20">
                <div>
                  <label className="text-xs text-outline font-label-caps uppercase block mb-1.5 font-semibold">
                    Target Company Name
                  </label>
                  <input
                    type="text"
                    placeholder={`e.g. ${COMPANY_TIERS.find((t) => t.id === companyTier)?.presets.join(", ")}`}
                    value={targetCompany}
                    onChange={(e) => setTargetCompany(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-lg bg-surface-container border border-outline-variant/40 text-on-surface text-xs focus:outline-none focus:border-secondary transition-colors"
                  />
                </div>

                <div>
                  <label className="text-xs text-outline font-label-caps uppercase block mb-1.5 font-semibold">
                    Number of Interview Questions
                  </label>
                  <div className="flex items-center gap-2">
                    {[3, 5, 7].map((num) => (
                      <button
                        key={num}
                        type="button"
                        onClick={() => setMaxQuestions(num)}
                        className={`flex-1 py-2 rounded-lg text-xs font-semibold font-label-numeric border transition-all ${
                          maxQuestions === num
                            ? "bg-secondary text-on-secondary border-secondary font-bold shadow-sm"
                            : "bg-surface-container text-on-surface-variant border-outline-variant/30 hover:bg-surface-container-high"
                        }`}
                      >
                        {num} Questions
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: RAG Resume Ingestion (5 Cols) */}
          <div className="lg:col-span-5 flex flex-col gap-6">
            <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 flex flex-col gap-4 shadow-lg">
              <div className="flex items-center justify-between">
                <span className="font-label-caps text-xs uppercase text-primary font-bold tracking-wider flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-[18px]">description</span>
                  RAG Resume Grounding
                </span>
                <span className="font-label-numeric-sm text-[10px] px-2 py-0.5 rounded bg-surface-container text-outline">
                  ChromaDB
                </span>
              </div>
              <p className="text-xs text-on-surface-variant leading-relaxed">
                Upload your engineering resume (PDF). Our local vector pipeline chunks and indexes your background
                so the interviewer interrogates your actual past architectural choices.
              </p>

              {/* Hidden file input controlled by ref */}
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                onChange={handleResumeUpload}
                className="hidden"
                disabled={uploadingResume}
              />

              {/* Ingestion & Status Box */}
              {isCheckingResume ? (
                <div className="p-6 rounded-xl bg-surface-container/40 border border-outline-variant/30 flex items-center justify-center gap-3 text-outline text-xs">
                  <span className="material-symbols-outlined animate-spin text-[18px]">sync</span>
                  <span>Checking active resume grounding...</span>
                </div>
              ) : uploadingResume ? (
                <div className="p-6 rounded-xl bg-surface-container/60 border border-primary/40 flex flex-col items-center justify-center text-center gap-2">
                  <div className="w-10 h-10 rounded-full bg-primary/20 text-primary flex items-center justify-center animate-spin">
                    <span className="material-symbols-outlined text-[20px]">sync</span>
                  </div>
                  <span className="text-xs font-semibold text-on-surface">Chunking & Vector Indexing...</span>
                  <span className="text-[11px] text-outline">Generating embeddings with all-MiniLM-L6-v2</span>
                </div>
              ) : resumeUploadedName ? (
                /* Active Indexed Resume Card */
                <div className="p-4 rounded-xl bg-surface-container border border-primary/40 flex flex-col gap-3 shadow-md relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-primary/10 rounded-full blur-2xl pointer-events-none" />

                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-10 h-10 rounded-xl bg-primary/15 border border-primary/30 text-primary flex items-center justify-center flex-shrink-0">
                        <span className="material-symbols-outlined text-[22px]">picture_as_pdf</span>
                      </div>
                      <div className="flex flex-col min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-on-surface truncate max-w-[200px]" title={resumeUploadedName}>
                            {resumeUploadedName}
                          </span>
                        </div>
                        <span className="text-[11px] text-secondary flex items-center gap-1 font-medium mt-0.5">
                          <span className="material-symbols-outlined text-[14px]">verified</span>
                          Active in ChromaDB
                        </span>
                      </div>
                    </div>

                    <span className="font-label-caps text-[9px] px-2 py-0.5 rounded-full bg-primary-container text-on-primary-container font-bold tracking-wider flex-shrink-0">
                      GROUNDED
                    </span>
                  </div>

                  <p className="text-[11px] text-on-surface-variant leading-relaxed">
                    This active resume from your profile will be used to generate personalized architectural scenarios.
                  </p>

                  <div className="flex items-center gap-2 pt-2 border-t border-outline-variant/30">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="flex-1 py-1.5 px-3 rounded-lg bg-surface-container-high hover:bg-surface-container-highest border border-outline-variant/40 text-on-surface text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                    >
                      <span className="material-symbols-outlined text-[15px]">file_upload</span>
                      <span>Replace PDF</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleClearResume}
                      className="py-1.5 px-3 rounded-lg bg-error-container/20 hover:bg-error-container/30 border border-error/30 text-error text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                      title="Detach resume so drill uses general questions"
                    >
                      <span className="material-symbols-outlined text-[15px]">delete_outline</span>
                      <span>Detach</span>
                    </button>
                  </div>
                </div>
              ) : (
                /* Empty Upload Dropzone */
                <label className="relative border-2 border-dashed border-outline-variant/40 hover:border-primary/60 rounded-xl p-6 flex flex-col items-center justify-center text-center cursor-pointer transition-all bg-surface-container/50 hover:bg-surface-container">
                  <div className="w-12 h-12 rounded-full bg-primary/10 text-primary flex items-center justify-center mb-2">
                    <span className="material-symbols-outlined text-[24px]">cloud_upload</span>
                  </div>
                  <span className="text-xs font-semibold text-on-surface mb-0.5">
                    Click to upload engineering resume (PDF)
                  </span>
                  <span className="text-[10px] text-outline">
                    Supports standard PDF resumes (parsed into ChromaDB vector store)
                  </span>
                </label>
              )}
            </div>

            {/* Launch Action Card */}
            <div className="p-6 rounded-xl bg-gradient-to-br from-surface-container-low via-surface-container to-surface-container-high border border-outline-variant/30 flex flex-col gap-4 shadow-xl">
              <div className="flex items-center justify-between">
                <span className="font-label-caps text-xs uppercase text-outline font-semibold">Ready to begin</span>
                <span className="font-label-numeric-sm text-xs text-secondary font-bold">20-30 mins</span>
              </div>

              {/* Grounding Status Preview */}
              <div className="flex items-center justify-between text-xs py-2 px-3 rounded-lg bg-surface-container/60 border border-outline-variant/30">
                <span className="text-outline text-[11px] font-label-caps uppercase">Grounding Mode:</span>
                <span className={`font-semibold flex items-center gap-1.5 text-xs ${resumeUploadedName ? "text-tertiary" : "text-secondary"}`}>
                  <span className="material-symbols-outlined text-[15px]">
                    {resumeUploadedName ? "verified" : "auto_awesome"}
                  </span>
                  {resumeUploadedName ? "Resume-Grounded" : "General Role Scope"}
                </span>
              </div>

              <button
                type="button"
                onClick={handleStartInterview}
                disabled={isStarting}
                className="w-full py-3.5 px-6 rounded-xl bg-gradient-to-r from-secondary via-primary to-primary hover:opacity-90 transition-all text-white font-headline-sm text-sm font-bold flex items-center justify-center gap-2 shadow-lg shadow-secondary/20 cursor-pointer disabled:opacity-50"
              >
                {isStarting ? (
                  <>
                    <span className="material-symbols-outlined animate-spin text-[20px]">refresh</span>
                    <span>Synthesizing Interview Question 1...</span>
                  </>
                ) : (
                  <>
                    <span>Launch Technical Drill</span>
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
      <div className="pointer-events-none absolute top-1/2 -left-20 w-[500px] h-[350px] bg-secondary-container/10 rounded-full blur-[120px]" />

      {/* Studio Top Control Strip */}
      <div className="relative z-10 flex items-center justify-between p-4 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-md">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-secondary/10 text-secondary flex items-center justify-center">
            <span className="material-symbols-outlined text-[22px]">terminal</span>
          </div>
          <div className="flex flex-col">
            <span className="font-headline-sm text-sm font-bold text-on-surface">{role}</span>
            <div className="flex items-center gap-2 text-[11px] text-outline font-label-caps uppercase font-medium">
              <span>{targetCompany ? `Target: ${targetCompany}` : "Technical Evaluation Round"}</span>
              <span className="text-outline/40">•</span>
              <span className="text-secondary font-semibold">
                {COMPANY_TIERS.find((t) => t.id === companyTier)?.name || "FAANG Bar"}
              </span>
            </div>
          </div>
        </div>

        {/* Stepper & Timer */}
        <div className="flex items-center gap-3 sm:gap-4">
          {resumeUploadedName && (
            <div className="hidden sm:flex items-center gap-1 font-label-numeric-sm text-[11px] text-tertiary px-2.5 py-1 rounded-lg bg-tertiary-container/20 border border-tertiary/30">
              <span className="material-symbols-outlined text-[14px]">verified</span>
              <span>Grounded</span>
            </div>
          )}
          <div className="flex items-center gap-2 font-label-numeric-sm text-xs text-on-surface bg-surface-container px-3 py-1.5 rounded-lg border border-outline-variant/20">
            <span className="material-symbols-outlined text-[16px] text-tertiary">schedule</span>
            <span>{formatTimer(elapsedSeconds)}</span>
          </div>
          <div className="font-label-caps text-xs px-3 py-1.5 rounded-lg bg-secondary-container/20 text-secondary font-bold">
            Question {questionCount + 1} of {maxQuestions}
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-error-container/20 border border-error/30 text-error text-xs flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px]">error</span>
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Main Question Bento Box */}
      <div className="p-6 sm:p-8 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-xl flex flex-col gap-5 relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="font-label-caps text-xs uppercase tracking-wider text-secondary font-bold flex items-center gap-1.5">
            <span className="material-symbols-outlined text-[18px]">psychology</span>
            {currentQuestion?.type ? `${currentQuestion.type.toUpperCase()} CHALLENGE` : "TECHNICAL CHALLENGE"}
          </span>
          <button
            type="button"
            onClick={() => currentQuestion?.text && handleSpeakQuestion(currentQuestion.text)}
            className="flex items-center gap-1.5 px-3 py-1 rounded-md bg-surface-container hover:bg-surface-container-high text-xs text-secondary font-medium transition-colors"
          >
            <span className="material-symbols-outlined text-[16px]">
              {isSpeaking ? "volume_off" : "volume_up"}
            </span>
            <span>{isSpeaking ? "Stop Audio" : "Read Aloud"}</span>
          </button>
        </div>

        <p className="font-headline-md text-lg sm:text-xl text-on-surface font-semibold leading-relaxed">
          {currentQuestion?.text || "Synthesizing scenario question..."}
        </p>

        <div className="flex items-center gap-2 pt-1 border-t border-outline-variant/20 text-[11px] text-outline font-label-caps">
          <span className="material-symbols-outlined text-[14px] text-secondary">verified</span>
          <span>Grounding: ChromaDB Semantic Resume Chunks & Architecture Scenarios</span>
        </div>
      </div>

      {/* Answer Input Bento Box */}
      <div className="p-6 rounded-xl bg-surface-container-low border border-outline-variant/30 shadow-xl flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <span className="font-label-caps text-xs uppercase text-outline font-semibold tracking-wider">
            Your Spoken or Written Response
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={toggleRecording}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shadow-sm ${
                isRecording
                  ? "bg-error text-white animate-pulse"
                  : "bg-surface-container hover:bg-surface-container-high text-on-surface"
              }`}
            >
              <span className="material-symbols-outlined text-[16px]">
                {isRecording ? "mic" : "mic_none"}
              </span>
              <span>{isRecording ? "Recording Voice..." : "Voice Mode"}</span>
            </button>
          </div>
        </div>

        {isRecording && (
          <LiveConfidenceNeedle emotion={liveEmotion} isRecording={isRecording} />
        )}

        <textarea
          rows={6}
          value={answerText}
          onChange={(e) => setAnswerText(e.target.value)}
          placeholder="Articulate your thought process clearly. Structure your reasoning, state architectural trade-offs, and reference concrete engineering milestones..."
          className="w-full p-4 rounded-xl bg-surface-container border border-outline-variant/40 text-on-surface text-sm focus:outline-none focus:border-secondary transition-colors resize-y leading-relaxed font-body-md"
        />

        <div className="flex items-center justify-between pt-2">
          <span className="text-xs text-outline font-label-numeric-sm">
            {answerText.trim().split(/\s+/).filter(Boolean).length} words
          </span>

          <button
            type="button"
            onClick={handleSubmitAnswer}
            disabled={isSubmitting || !answerText.trim()}
            className="px-6 py-2.5 rounded-xl bg-secondary hover:bg-secondary/90 text-on-secondary font-headline-sm text-xs font-bold flex items-center gap-2 transition-all shadow-md shadow-secondary/20 cursor-pointer disabled:opacity-40"
          >
            {isSubmitting ? (
              <>
                <span className="material-symbols-outlined animate-spin text-[16px]">refresh</span>
                <span>Synthesizing Next Question...</span>
              </>
            ) : (
              <>
                <span>{questionCount + 1 >= maxQuestions ? "Complete & View Report" : "Next Question"}</span>
                <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
