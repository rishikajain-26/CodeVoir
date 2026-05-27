import { useEffect, useMemo, useRef, useState } from "react"
import Editor from "@monaco-editor/react"
import { AlertTriangle, ArrowLeft, BarChart3, Bot, Brain, Briefcase, Calendar, Camera, Code2, FileText, LogIn, LogOut, Mic, Play, Send, Shield, Sparkles, Square, Target, TrendingUp, Upload } from "lucide-react"

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"
// Use the Vite proxy (/api → 127.0.0.1:8000) as primary, direct URL as fallback.
// Dead ports (8010) removed — they caused "session not found" errors to be swallowed.
const API_BASES = [...new Set(["", API])]

// ElevenLabs TTS — set VITE_ELEVENLABS_API_KEY in .env.local to enable.
// Falls back to browser Web Speech API when key is absent.
const EL_API_KEY = import.meta.env.VITE_ELEVENLABS_API_KEY || ""
const EL_VOICE_ID = import.meta.env.VITE_ELEVENLABS_VOICE_ID || "21m00Tcm4TlvDq8ikWAM"
const EL_MODEL = "eleven_turbo_v2_5"   // lowest latency model

// onAudioReady(audio) is called with the Audio element as soon as it exists,
// allowing the caller to store it for interrupt support before playback starts.
async function _elevenLabsTTS(text, onAudioReady) {
  const res = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${EL_VOICE_ID}/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "xi-api-key": EL_API_KEY },
    body: JSON.stringify({
      text,
      model_id: EL_MODEL,
      voice_settings: { stability: 0.48, similarity_boost: 0.78, style: 0.0, use_speaker_boost: true },
    }),
  })
  if (!res.ok) throw new Error(`ElevenLabs ${res.status}`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const audio = new Audio(url)
  if (onAudioReady) onAudioReady(audio)
  return new Promise((resolve, reject) => {
    audio.onended = () => { URL.revokeObjectURL(url); resolve(null) }
    audio.onerror = () => { URL.revokeObjectURL(url); reject(new Error("audio error")) }
    audio.play().catch(reject)
  })
}

const languageLabels = {
  python: "Python",
  cpp: "C++",
  c: "C",
  java: "Java",
}

const defaultCode = `# Select a language and start solving.
`

const defaultDashboard = {
  stats: { total_interviews: 0, completed_interviews: 0, companies_practiced: 0, average_score: 0, best_score: 0, xp: 0, level: 1, completed_company_sets: 0 },
  xp: { total_xp: 0, level: 1, title: "Interview Rookie", level_progress: 0, xp_to_next_level: 450, completed_company_sets: 0, company_cards: [], next_goals: [], rules: [] },
  companies: [],
  interviews: [],
}

function getStoredProfile() {
  if (typeof window === "undefined") return { authenticated: false, user_id: "local-user", name: "Candidate", email: "" }
  if (!window.localStorage.getItem("codevoir_auth_token")) return { authenticated: false, user_id: "local-user", name: "Candidate", email: "" }
  const stored = window.localStorage.getItem("codevoir_user_profile")
  if (stored) {
    try {
      const parsed = JSON.parse(stored)
      if (parsed?.authenticated && parsed?.user_id) return { name: parsed.name || "Candidate", user_id: parsed.user_id, email: parsed.email || "", authenticated: true }
    } catch {}
  }
  return { authenticated: false, user_id: "local-user", name: "Candidate", email: "" }
}

function authToken() {
  if (typeof window === "undefined") return ""
  return window.localStorage.getItem("codevoir_auth_token") || ""
}

function testValue(value) {
  if (value === undefined || value === null || value === "") return "—"
  if (typeof value === "string") return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

export default function App() {
  const [userProfile, setUserProfile] = useState(getStoredProfile)
  const [screen, setScreen] = useState(() => getStoredProfile().authenticated ? "dashboard" : "welcome")
  const [dashboard, setDashboard] = useState(defaultDashboard)
  const [dashboardLoading, setDashboardLoading] = useState(false)
  const [selectedReport, setSelectedReport] = useState(null)
  const [session, setSession] = useState(null)
  const [form, setForm] = useState({ job_role: "Software Engineer", experience_level: "fresher", target_company: "", job_description: "", round_type: "dsa", difficulty: "medium", timer_minutes: 35 })
  const [resume, setResume] = useState(null)
  const [resumeReviewFile, setResumeReviewFile] = useState(null)
  const [resumeReview, setResumeReview] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [scratchpadMode, setScratchpadMode] = useState("text")
  const [scratchpad, setScratchpad] = useState("")
  const [language, setLanguage] = useState("python")
  const [code, setCode] = useState(defaultCode)
  const [codeResult, setCodeResult] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [warning, setWarning] = useState("")
  const [error, setError] = useState("")
  const [transcriptOpen, setTranscriptOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [cameraPos, setCameraPos] = useState({ x: 24, y: 88 })
  const [voiceState, setVoiceState] = useState("idle")
  const [autoVoice, setAutoVoice] = useState(false)
  const [liveTranscript, setLiveTranscript] = useState("")
  const [companies, setCompanies] = useState([])
  const [companyDirectory, setCompanyDirectory] = useState([])
  const [companyRounds, setCompanyRounds] = useState({ company: "", resolved: false, rounds: [] })
  const [companyLoading, setCompanyLoading] = useState(false)
  const [roundOptions, setRoundOptions] = useState([])
  const [isBusy, setIsBusy] = useState(false)
  const [dsaProgress, setDsaProgress] = useState(null)
  const videoRef = useRef(null)
  const recognitionRef = useRef(null)
  const autoVoiceRef = useRef(false)
  const liveTranscriptRef = useRef("")
  const speakingRef = useRef(false)
  const ttsTimeoutRef = useRef(null)
  const voiceRestartTimerRef = useRef(null)
  const intentionalStopRef = useRef(false)
  const voiceRetryRef = useRef(0)
  const lastListenEndedAtRef = useRef(0)
  const lastAiSpokenRef = useRef("")
  const ttsEndedAtRef = useRef(0)       // timestamp when TTS audio finished playing
  const dragRef = useRef(null)
  const editorTelemetryRef = useRef({ lastChangeAt: Date.now(), edits: 0, pasteEvents: 0, largePastes: 0, deletions: 0, idleGaps: 0, maxLines: 0 })
  const codeRef = useRef(defaultCode)
  const languageRef = useRef("python")
  const currentAudioRef = useRef(null)   // tracks active ElevenLabs Audio element

  const currentProblem = session?.problem
  const activeRound = session?.round_type || form.round_type
  const isDsaRound = activeRound === "dsa"
  const isCsRound = activeRound === "cs_fundamentals"
  const isProjectRound = !isDsaRound && !isCsRound
  const roundTitle = isDsaRound ? "DSA + Code Interview" : isCsRound ? "CS Fundamentals Interview" : "Project + Behavioural Interview"
  const selectedRoundOption = roundOptions.find((round) => round.id === activeRound || round.legacy_ids?.includes(activeRound))
  const availableSetupRounds = companyRounds.resolved ? companyRounds.rounds || [] : []
  const selectedSetupRound = availableSetupRounds.find((round) => round.id === form.round_type)
  const canStartConfiguredInterview = Boolean(companyRounds.resolved && selectedSetupRound && !companyLoading && form.target_company.trim())
  const lastAiMessage = useMemo(() => [...messages].reverse().find((m) => m.role === "interviewer")?.content ?? "", [messages])

  useEffect(() => {
    apiFetch("/api/interview/round-options")
      .then((res) => res.ok ? res.json() : null)
      .then((meta) => setRoundOptions(meta?.rounds || []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    apiFetch("/api/interview/company-directory")
      .then((res) => res.ok ? res.json() : null)
      .then((meta) => {
        const entries = meta?.companies || []
        setCompanyDirectory(entries)
        setCompanies(entries.map((item) => item.company))
      })
      .catch(() => {
        apiFetch("/api/problems/companies")
          .then((res) => res.ok ? res.json() : null)
          .then((meta) => setCompanies(meta?.companies || []))
          .catch(() => {})
      })
  }, [])

  useEffect(() => {
    const company = form.target_company.trim()
    if (!company) {
      setCompanyRounds({ company: "", resolved: false, rounds: [] })
      return
    }
    let cancelled = false
    setCompanyLoading(true)
    apiFetch(`/api/interview/company-rounds?company=${encodeURIComponent(company)}`)
      .then((res) => res.ok ? res.json() : null)
      .then((meta) => {
        if (cancelled || !meta) return
        const rounds = meta.rounds || []
        setCompanyRounds(meta)
        if (meta.resolved && rounds.length) {
          setForm((prev) => {
            if (rounds.some((round) => round.id === prev.round_type)) return prev
            return { ...prev, round_type: rounds[0].id, difficulty: rounds[0].id === "dsa" ? prev.difficulty : "medium" }
          })
        }
      })
      .catch(() => {
        if (!cancelled) setCompanyRounds({ company, resolved: false, rounds: [] })
      })
      .finally(() => {
        if (!cancelled) setCompanyLoading(false)
      })
    return () => { cancelled = true }
  }, [form.target_company])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const token = params.get("auth_token")
    if (token) {
      window.localStorage.setItem("codevoir_auth_token", token)
      window.history.replaceState({}, "", window.location.pathname)
      loadAuthenticatedProfile(token)
      return
    }
    if (authToken()) loadAuthenticatedProfile()
  }, [])

  useEffect(() => {
    if (!currentProblem) return
    const nextCode = getStarterCode(currentProblem, language)
    setCode(nextCode)
    codeRef.current = nextCode
    setCodeResult(null)
  }, [language, currentProblem?.id])

  useEffect(() => {
    codeRef.current = code
  }, [code])

  useEffect(() => {
    languageRef.current = language
  }, [language])

  useEffect(() => {
    if (!session?.session_id || !isDsaRound) return undefined
    let stopped = false
    const tick = () => {
      apiFetch(`/api/interview/progress?session_id=${encodeURIComponent(session.session_id)}`)
        .then((res) => {
          if (res.status === 404) { stopped = true; clearInterval(timer); return null }
          return res.ok ? res.json() : null
        })
        .then((payload) => {
          if (payload?.dsa_progress) setDsaProgress(payload.dsa_progress)
        })
        .catch(() => {})
    }
    tick()
    const timer = window.setInterval(() => { if (!stopped) tick() }, 1000)
    return () => window.clearInterval(timer)
  }, [session?.session_id, isDsaRound])

  useEffect(() => {
    if (screen !== "dashboard" || !userProfile.authenticated) return
    loadDashboard()
  }, [screen, userProfile.authenticated, userProfile.user_id])

  useEffect(() => {
    if (screen !== "interview" || !session) return
    const onVisibility = () => document.hidden && reportViolation("tab_hidden", { title: document.title })
    const onBlur = () => window.setTimeout(() => !document.hasFocus() && reportViolation("window_blur", {}), 1800)
    document.addEventListener("visibilitychange", onVisibility)
    window.addEventListener("blur", onBlur)
    return () => {
      document.removeEventListener("visibilitychange", onVisibility)
      window.removeEventListener("blur", onBlur)
    }
  }, [screen, session])

  useEffect(() => {
    if (screen !== "interview") return
    let active = true
    navigator.mediaDevices?.getUserMedia({ video: true, audio: false })
      .then((stream) => {
        if (active && videoRef.current) videoRef.current.srcObject = stream
      })
      .catch(() => setWarning("Camera permission is blocked. Voice and manual text mode still work."))
    return () => {
      active = false
      if (voiceRestartTimerRef.current) window.clearTimeout(voiceRestartTimerRef.current)
      videoRef.current?.srcObject?.getTracks?.().forEach((track) => track.stop())
    }
  }, [screen])

  useEffect(() => {
    autoVoiceRef.current = autoVoice
  }, [autoVoice])

  useEffect(() => {
    liveTranscriptRef.current = liveTranscript
  }, [liveTranscript])

  async function startSession() {
    if (!canStartConfiguredInterview) {
      setError("Select a company from the available data and choose one of its supported rounds.")
      return
    }
    setIsBusy(true)
    setError("")
    try {
      const created = await postJson("/api/session/start", { ...form, user_id: userProfile.user_id })
      if (resume) {
        const fd = new FormData()
        fd.append("session_id", created.session_id)
        fd.append("file", resume)
        await apiFetch("/api/resume/upload", { method: "POST", body: fd })
      }
      setSession(created)
      setDsaProgress(created.dsa_progress || null)
      setMessages([{ role: "interviewer", content: created.ai_text }])
      setCode(getStarterCode(created.problem, language))
      setScreen("interview")
      speak(created.ai_text)
    } catch (err) {
      setError(err.message || "Could not start interview. Check that the backend is running.")
    } finally {
      setIsBusy(false)
    }
  }

  async function reviewResume() {
    if (!resumeReviewFile) return
    setIsBusy(true)
    try {
      const fd = new FormData()
      fd.append("file", resumeReviewFile)
      const res = await apiFetch("/api/resume/review", { method: "POST", body: fd })
      setResumeReview(await res.json())
    } finally {
      setIsBusy(false)
    }
  }

  async function sendMessage(text = input, behavioralMetrics = {}) {
    const clean = text.trim()
    if (!clean || !session) return
    if (isBusy) return
    // Only apply echo filter within 500ms of TTS ending or while TTS is playing.
    // After that window, candidate speech is always genuine — no false positives.
    const inEchoWindow = speakingRef.current || (Date.now() - ttsEndedAtRef.current < 500)
    if (inEchoWindow && isLikelyEcho(clean, lastAiSpokenRef.current)) {
      setLiveTranscript("")
      if (autoVoiceRef.current && !speakingRef.current) scheduleListen(800)
      return
    }
    setInput("")
    setLiveTranscript("")
    setMessages((prev) => [...prev, { role: "candidate", content: clean }])
    setIsBusy(true)
    // Show "thinking" indicator while backend retries LLM
    setMessages((prev) => [...prev, { role: "thinking", content: "" }])
    try {
      const payload = { session_id: session.session_id, user_text: clean, behavioral_metrics: behavioralMetrics, code_context: currentCodeContext("message") }
      if (isCsRound && scratchpad.trim()) payload.scratchpad = { mode: scratchpadMode, content: scratchpad }
      const reply = await postJson("/api/interview/message", payload)
      // Remove thinking indicator
      setMessages((prev) => prev.filter((m) => m.role !== "thinking"))
      if (reply.dsa_progress) setDsaProgress(reply.dsa_progress)
      setSession((prev) => {
        if (!prev) return prev
        const updates = {
          phase: reply.phase,
          question_count: reply.question_count,
          exchange_count: reply.exchange_count,
          behavioral_signals: reply.behavioral_signals,
          weak_areas: reply.weak_areas,
        }
        if (reply.cs_fundamentals) updates.cs_fundamentals = reply.cs_fundamentals
        if (reply.project_behavioral) updates.project_behavioral = reply.project_behavioral
        if (reply.problem_changed && reply.problem) updates.problem = reply.problem
        return { ...prev, ...updates }
      })
      if (reply.problem_changed && reply.problem) {
        const nextCode = getStarterCode(reply.problem, language)
        setCode(nextCode)
        codeRef.current = nextCode
        setCodeResult(null)
        setMessages((prev) => [
          ...prev,
          { role: "interviewer", content: reply.ai_text },
          { role: "system", content: `Next problem loaded: ${reply.problem.title}` },
        ])
        speak(reply.ai_text)
        return
      }
      const msgObj = { role: "interviewer", content: reply.ai_text }
      if (reply.degraded) msgObj.degraded = true
      setMessages((prev) => [...prev, msgObj])
      speak(reply.ai_text)
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.role !== "thinking"))
      const detail = friendlyError(err)
      setError(detail)
      setMessages((prev) => [...prev, { role: "interviewer", content: `I hit a connection issue while replying: ${detail}. Please try again or use manual text for this turn.` }])
      window.setTimeout(() => setError(""), 6000)
    } finally {
      setIsBusy(false)
    }
  }

  async function submitCode() {
    if (!session) return
    setIsBusy(true)
    try {
      const reply = await postJson("/api/interview/submit-code", { session_id: session.session_id, code, language, problem_id: currentProblem?.id })
      if (reply.dsa_progress) setDsaProgress(reply.dsa_progress)
      if (reply.problem_changed && reply.problem) setSession((prev) => ({ ...prev, problem: reply.problem }))
      setCodeResult(reply.result)
      setMessages((prev) => [...prev, { role: "candidate", content: `Submitted ${languageLabels[language]} code.` }, { role: "interviewer", content: reply.ai_text }])
      speak(reply.ai_text)
    } catch (err) {
      if (err.status === 404) {
        setError("Session expired — the server was restarted. Please go back and start a new interview.")
        return
      }
      const staleProblem = parseErrorDetail(err)?.current_problem
      if (err.status === 409 && staleProblem) {
        setSession((prev) => ({ ...prev, problem: staleProblem }))
        const nextCode = getStarterCode(staleProblem, language)
        setCode(nextCode)
        codeRef.current = nextCode
        setCodeResult(null)
      }
      const detail = friendlyError(err)
      setError(detail)
      setMessages((prev) => [...prev, { role: "interviewer", content: `Code submission could not be evaluated: ${detail}` }])
      window.setTimeout(() => setError(""), 8000)
    } finally {
      setIsBusy(false)
    }
  }

  async function runTests() {
    if (!session || !currentProblem) return
    setIsBusy(true)
    try {
      const reply = await postJson("/api/interview/run-tests", { session_id: session.session_id, code, language, problem_id: currentProblem?.id })
      setCodeResult(reply.result)
    } catch (err) {
      if (err.status === 404) {
        setError("Session expired — the server was restarted. Please go back and start a new interview.")
        return
      }
      const staleProblem = parseErrorDetail(err)?.current_problem
      if (err.status === 409 && staleProblem) {
        setSession((prev) => ({ ...prev, problem: staleProblem }))
        const nextCode = getStarterCode(staleProblem, language)
        setCode(nextCode)
        codeRef.current = nextCode
        setCodeResult(null)
      }
      const detail = friendlyError(err)
      setError(detail)
      window.setTimeout(() => setError(""), 8000)
    } finally {
      setIsBusy(false)
    }
  }

  async function finishInterview() {
    if (!session) return
    const report = await apiFetch(`/api/feedback/${session.session_id}`).then((r) => r.json())
    setFeedback(report)
    setSelectedReport(report)
    loadDashboard()
    setScreen("feedback")
  }

  async function loadDashboard() {
    setDashboardLoading(true)
    try {
      const payload = await apiFetch(`/api/dashboard?user_id=${encodeURIComponent(userProfile.user_id)}`).then((r) => r.json())
      setDashboard({ ...defaultDashboard, ...payload })
    } catch (err) {
      setError(friendlyError(err))
      window.setTimeout(() => setError(""), 6000)
    } finally {
      setDashboardLoading(false)
    }
  }

  async function openReport(sessionId) {
    setIsBusy(true)
    setError("")
    try {
      const report = await apiFetch(`/api/feedback/${sessionId}`).then((r) => r.json())
      setSelectedReport(report)
      setFeedback(report)
      setScreen("feedback")
    } catch (err) {
      setError(friendlyError(err))
      window.setTimeout(() => setError(""), 6000)
    } finally {
      setIsBusy(false)
    }
  }

  async function loadAuthenticatedProfile(token = authToken()) {
    try {
      const profile = await apiFetch("/api/auth/me", {
        headers: { Authorization: `Bearer ${token}` },
      }).then((r) => r.json())
      window.localStorage.setItem("codevoir_user_profile", JSON.stringify(profile))
      setUserProfile(profile)
      setScreen("dashboard")
    } catch {
      window.localStorage.removeItem("codevoir_auth_token")
      window.localStorage.removeItem("codevoir_user_profile")
      setUserProfile({ authenticated: false, user_id: "local-user", name: "Candidate", email: "" })
      setScreen("welcome")
    }
  }

  async function authenticate() {
    try {
      const config = await apiFetch("/api/auth/config").then((r) => r.json())
      if (!config.configured) {
        setError("OAuth is not configured on the backend. Add OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET, then restart the backend.")
        window.setTimeout(() => setError(""), 7000)
        return
      }
      window.location.href = `${API}/api/auth/login`
    } catch (err) {
      setError(friendlyError(err))
      window.setTimeout(() => setError(""), 7000)
    }
  }

  function logout() {
    apiFetch("/api/auth/logout", { method: "POST" }).catch(() => {})
    window.localStorage.removeItem("codevoir_auth_token")
    window.localStorage.removeItem("codevoir_user_profile")
    setUserProfile({ authenticated: false, user_id: "local-user", name: "Candidate", email: "" })
    setDashboard(defaultDashboard)
    setSelectedReport(null)
    setFeedback(null)
    setScreen("welcome")
  }

  function startRound(roundType = "dsa") {
    setForm((prev) => ({ ...prev, round_type: roundType, difficulty: roundType === "dsa" ? prev.difficulty : "medium" }))
    setScreen("setup")
  }

  async function reportViolation(event_type, detail) {
    if (event_type === "tab_hidden" || event_type === "window_blur") {
      setWarning(event_type === "tab_hidden" ? "Tab switch detected and logged." : "Focus loss detected and logged.")
      window.setTimeout(() => setWarning(""), 5000)
    }
    if (!session) return
    await postJson("/api/interview/violation", { session_id: session.session_id, event_type, detail: { ...detail, ...(event_type === "code_telemetry" ? currentCodeContext("telemetry") : {}) } }).catch(() => {})
  }

  function currentCodeContext(source) {
    return {
      source,
      language: languageRef.current,
      code: codeRef.current,
      problem_id: currentProblem?.id,
      problem_title: currentProblem?.title,
      code_length: codeRef.current.length,
      line_count: codeRef.current.split("\n").length,
      ts: Date.now(),
    }
  }

  function _stopCurrentSpeech() {
    if (currentAudioRef.current) {
      try { currentAudioRef.current.pause() } catch {}
      currentAudioRef.current = null
    }
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }
    if (ttsTimeoutRef.current) { window.clearTimeout(ttsTimeoutRef.current); ttsTimeoutRef.current = null }
  }

  function speak(text) {
    if (!text) return
    if (voiceRestartTimerRef.current) window.clearTimeout(voiceRestartTimerRef.current)
    _stopCurrentSpeech()
    lastAiSpokenRef.current = text
    speakingRef.current = true
    setVoiceState("ai_speaking")

    const finishSpeaking = () => {
      if (!speakingRef.current) return
      speakingRef.current = false
      ttsEndedAtRef.current = Date.now()
      currentAudioRef.current = null
      setVoiceState(recognitionRef.current ? "listening" : "user_turn")
      if (autoVoiceRef.current && !recognitionRef.current) scheduleListen(300)
    }

    if (EL_API_KEY) {
      _elevenLabsTTS(text, (audio) => { currentAudioRef.current = audio })
        .then(finishSpeaking)
        .catch((err) => {
          console.warn("ElevenLabs TTS failed, falling back to browser TTS:", err)
          currentAudioRef.current = null
          _speakBrowserTTS(text, finishSpeaking)
        })
    } else {
      // Browser TTS conflicts with recognition on same audio channel — must pause mic
      if (recognitionRef.current) {
        intentionalStopRef.current = true
        recognitionRef.current.stop?.()
      }
      _speakBrowserTTS(text, () => {
        finishSpeaking()
        if (autoVoiceRef.current && !recognitionRef.current) scheduleListen(600)
      })
    }
  }

  function _speakBrowserTTS(text, onDone) {
    if (!("speechSynthesis" in window)) { onDone(); return }
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 1.02
    utterance.onend = onDone
    utterance.onerror = onDone
    window.speechSynthesis.speak(utterance)
    // Safety timeout: 60ms per char + 500ms buffer, capped at 30s
    ttsTimeoutRef.current = window.setTimeout(onDone, Math.min(30000, text.length * 60 + 500))
  }

  function startListening() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      setWarning("Speech recognition is only available in Chrome. Use manual text input.")
      window.setTimeout(() => setWarning(""), 5000)
      return
    }
    if (recognitionRef.current) return
    // Only block mic during browser TTS (same audio channel); ElevenLabs uses
    // a separate Audio element and Chrome AEC handles echo suppression.
    if (speakingRef.current && !EL_API_KEY) return
    const sinceLastEnd = Date.now() - lastListenEndedAtRef.current
    if (sinceLastEnd < 700) {
      scheduleListen(700 - sinceLastEnd)
      return
    }
    const recognition = new SpeechRecognition()
    recognition.lang = "en-US"
    recognition.interimResults = true
    recognition.continuous = true
    recognition.maxAlternatives = 1
    let finalText = ""
    let latestHeardText = ""
    let startedAt = Date.now()
    let hadRecoverableError = false
    let finalSpeechTimer = null
    let silenceTimer = null
    const pauseMs = voicePauseMs(activeRound)
    const stopAfterSpeech = (delayMs = pauseMs) => {
      if (silenceTimer) window.clearTimeout(silenceTimer)
      silenceTimer = window.setTimeout(() => {
        // Don't auto-stop during AI speech — candidate might be waiting to interrupt
        if (speakingRef.current) return
        intentionalStopRef.current = false
        recognition.stop()
      }, delayMs)
    }
    recognition.onstart = () => {
      intentionalStopRef.current = false
      startedAt = Date.now()
      setVoiceState("listening")
      setLiveTranscript("")
    }
    recognition.onresult = (event) => {
      let interim = ""
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const chunk = event.results[i][0]?.transcript || ""
        if (event.results[i].isFinal) {
          finalText += `${chunk} `
          // Candidate is actively speaking — if AI is still talking, interrupt it
          if (speakingRef.current && !isLikelyEcho(finalText.trim(), lastAiSpokenRef.current)) {
            _stopCurrentSpeech()
            speakingRef.current = false
            ttsEndedAtRef.current = Date.now()
            currentAudioRef.current = null
            setVoiceState("listening")
          }
          if (finalSpeechTimer) window.clearTimeout(finalSpeechTimer)
          finalSpeechTimer = window.setTimeout(() => {
            if (speakingRef.current) return
            intentionalStopRef.current = false
            recognition.stop()
          }, pauseMs)
        } else interim += chunk
      }
      latestHeardText = `${finalText}${interim}`.trim()
      setLiveTranscript(latestHeardText)
      if (latestHeardText) stopAfterSpeech(finalText.trim() ? pauseMs : Math.max(pauseMs, 4500))
    }
    recognition.onerror = (event) => {
      hadRecoverableError = ["aborted", "interrupted", "network", "no-speech"].includes(event.error)
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        setAutoVoice(false)
        autoVoiceRef.current = false
        setWarning("Microphone permission is blocked. Allow mic access in the browser, then click Start voice.")
      } else if (event.error === "audio-capture") {
        setAutoVoice(false)
        autoVoiceRef.current = false
        setWarning("No microphone was detected by the browser. Check Windows input settings, then click Start voice.")
      } else if (!hadRecoverableError) {
        setWarning(`Speech recognition error: ${event.error}. Click Start voice again.`)
      }
      if (event.error !== "aborted" && event.error !== "interrupted" && event.error !== "no-speech") {
        window.setTimeout(() => setWarning(""), 6000)
      }
    }
    recognition.onend = () => {
      if (finalSpeechTimer) window.clearTimeout(finalSpeechTimer)
      if (silenceTimer) window.clearTimeout(silenceTimer)
      lastListenEndedAtRef.current = Date.now()
      recognitionRef.current = null
      setVoiceState("user_turn")
      if (intentionalStopRef.current) {
        intentionalStopRef.current = false
        return
      }
      const clean = (finalText.trim() || latestHeardText.trim())
      if (clean) {
        const inEchoWindow = speakingRef.current || (Date.now() - ttsEndedAtRef.current < 500)
        if (inEchoWindow && isLikelyEcho(clean, lastAiSpokenRef.current)) {
          setLiveTranscript("")
          if (autoVoiceRef.current && !speakingRef.current) scheduleListen(900)
          return
        }
        sendMessage(clean, { speech_duration_ms: Date.now() - startedAt, voice_turn: true })
      } else if (autoVoiceRef.current && !speakingRef.current && hadRecoverableError && voiceRetryRef.current < 1) {
        voiceRetryRef.current += 1
        scheduleListen(1200)
      }
    }
    recognitionRef.current = recognition
    try {
      recognition.start()
    } catch {
      recognitionRef.current = null
      scheduleListen(900)
    }
  }

  function scheduleListen(delayMs) {
    if (!autoVoiceRef.current) return
    // Block during browser TTS only — ElevenLabs plays via Audio element,
    // Chrome AEC handles echo, so mic can stay alive during playback
    if (speakingRef.current && !EL_API_KEY) return
    if (voiceRestartTimerRef.current) window.clearTimeout(voiceRestartTimerRef.current)
    voiceRestartTimerRef.current = window.setTimeout(() => {
      voiceRestartTimerRef.current = null
      startListening()
    }, delayMs)
  }

  function stopListening() {
    if (voiceRestartTimerRef.current) window.clearTimeout(voiceRestartTimerRef.current)
    const clean = liveTranscriptRef.current.trim()
    autoVoiceRef.current = false
    setAutoVoice(false)
    intentionalStopRef.current = true
    recognitionRef.current?.stop?.()
    recognitionRef.current = null
    setVoiceState("user_turn")
    if (clean && session && !isBusy) {
      sendMessage(clean, { voice_turn: true, stopped_manually: true })
    }
  }

  function sendCapturedTranscript() {
    const clean = liveTranscriptRef.current.trim()
    if (clean && session && !isBusy) {
      sendMessage(clean, { voice_turn: true, sent_from_transcript: true })
    }
  }

  function toggleMic() {
    if (autoVoice || voiceState === "listening") {
      stopListening()
      return
    }
    autoVoiceRef.current = true
    voiceRetryRef.current = 0
    setAutoVoice(true)
    startListening()
  }

  function onEditorMount(editor) {
    editor.onDidPaste(() => {
      editorTelemetryRef.current.pasteEvents += 1
      reportViolation("paste", { surface: "monaco", language })
    })
    editor.onDidChangeModelContent((event) => {
      const now = Date.now()
      const telemetry = editorTelemetryRef.current
      const idleMs = now - telemetry.lastChangeAt
      const inserted = event.changes.reduce((sum, change) => sum + (change.text?.length || 0), 0)
      const removed = event.changes.reduce((sum, change) => sum + (change.rangeLength || 0), 0)
      telemetry.edits += 1
      telemetry.deletions += removed > inserted ? 1 : 0
      telemetry.largePastes += inserted > 160 ? 1 : 0
      telemetry.idleGaps += idleMs > 30000 ? 1 : 0
      telemetry.maxLines = Math.max(telemetry.maxLines, editor.getModel()?.getLineCount?.() || 0)
      telemetry.lastChangeAt = now
      if (telemetry.edits % 8 === 0 || inserted > 160) {
        reportViolation("code_telemetry", { ...telemetry, language, current_lines: editor.getModel()?.getLineCount?.() || 0, last_idle_ms: idleMs })
      }
    })
  }

  function startCameraDrag(event) {
    event.preventDefault()
    dragRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      originX: cameraPos.x,
      originY: cameraPos.y,
    }
    window.addEventListener("pointermove", moveCamera)
    window.addEventListener("pointerup", stopCameraDrag)
  }

  function moveCamera(event) {
    const drag = dragRef.current
    if (!drag) return
    const nextX = Math.min(Math.max(8, drag.originX + event.clientX - drag.startX), Math.max(8, window.innerWidth - 220))
    const nextY = Math.min(Math.max(56, drag.originY + event.clientY - drag.startY), Math.max(56, window.innerHeight - 180))
    setCameraPos({ x: nextX, y: nextY })
  }

  function stopCameraDrag() {
    dragRef.current = null
    window.removeEventListener("pointermove", moveCamera)
    window.removeEventListener("pointerup", stopCameraDrag)
  }

  if (screen === "welcome") {
    return <WelcomePage error={error} onAuthenticate={authenticate} />
  }

  if (screen === "dashboard") {
    return <DashboardHistory
      userProfile={userProfile}
      dashboard={dashboard}
      loading={dashboardLoading}
      error={error}
      onStart={startRound}
      onRefresh={loadDashboard}
      onOpenReport={openReport}
      onLogout={logout}
      isBusy={isBusy}
    />
  }

  if (screen === "feedback" && feedback) return <Feedback report={selectedReport || feedback} onRestart={() => startRound("dsa")} onBack={() => setScreen("dashboard")} />

  if (screen === "setup") {
    return (
      <main className="min-h-screen bg-slate-950 text-slate-100">
        {error && <div className="fixed left-1/2 top-4 z-30 max-w-xl -translate-x-1/2 rounded border border-red-400 bg-red-950 px-4 py-3 text-sm text-red-100">{error}</div>}
        <section className="border-b border-slate-800 bg-slate-900">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
            <div className="flex items-center gap-3">
              <button onClick={() => setScreen("dashboard")} className="grid h-10 w-10 place-items-center rounded border border-slate-700 bg-slate-950 text-slate-200" title="Back to dashboard"><ArrowLeft size={20} /></button>
              <div className="grid h-10 w-10 place-items-center rounded bg-cyan-400 text-slate-950"><Bot size={22} /></div>
              <div>
                <h1 className="text-xl font-semibold">Clio Interview Lab</h1>
                <p className="text-sm text-slate-400">Voice-first mock interviews with DSA, resume probing, and proctoring.</p>
              </div>
            </div>
            <div className="hidden items-center gap-2 text-sm text-slate-300 md:flex"><Shield size={16} /> Integrity monitoring enabled</div>
          </div>
        </section>

        <section className="mx-auto grid max-w-7xl gap-6 px-6 py-6 lg:grid-cols-[1.15fr_.85fr]">
          <div className="rounded border border-slate-800 bg-slate-900 p-5">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold"><Code2 size={19} className="text-cyan-300" /> Start Live Interview</h2>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Target company">
                <input list="company-options" value={form.target_company} onChange={(e) => setForm({ ...form, target_company: e.target.value })} placeholder="Search company with interview data" />
                <datalist id="company-options">
                  {(companyDirectory.length ? companyDirectory : companies.map((company) => ({ company, rounds: [] }))).map((item) => <option key={item.company} value={item.company} label={item.rounds?.map((round) => round.label).join(", ")} />)}
                </datalist>
              </Field>
              <Field label="Available round">
                <select value={selectedSetupRound ? form.round_type : ""} onChange={(e) => setForm({ ...form, round_type: e.target.value, difficulty: e.target.value === "dsa" ? form.difficulty : "medium" })} disabled={!availableSetupRounds.length}>
                  {!availableSetupRounds.length && <option value="">Select a company first</option>}
                  {availableSetupRounds.map((round) => <option key={round.id} value={round.id}>{round.label}</option>)}
                </select>
              </Field>
              <Field label="Job role"><input value={form.job_role} onChange={(e) => setForm({ ...form, job_role: e.target.value })} /></Field>
              <Field label="Experience"><select value={form.experience_level} onChange={(e) => setForm({ ...form, experience_level: e.target.value })}><option>fresher</option><option>mid</option><option>senior</option></select></Field>
              {form.round_type === "dsa" && <Field label="Difficulty"><select value={form.difficulty} onChange={(e) => setForm({ ...form, difficulty: e.target.value })}><option>easy</option><option>medium</option><option>hard</option></select></Field>}
              <Field label="Timer minutes"><input type="number" min="10" max="90" value={form.timer_minutes} onChange={(e) => setForm({ ...form, timer_minutes: Number(e.target.value) })} /></Field>
            </div>
            <div className="mt-4 rounded bg-slate-950 p-3 text-xs text-slate-400">
              {!form.target_company.trim() && `${companies.length.toLocaleString()} companies have at least one supported interview round. Search and select a company to see only the rounds backed by data.`}
              {form.target_company.trim() && companyLoading && "Checking company interview data..."}
              {form.target_company.trim() && !companyLoading && !companyRounds.resolved && "No interview data found for this company. Pick one from the suggestions."}
              {form.target_company.trim() && !companyLoading && companyRounds.resolved && availableSetupRounds.length > 0 && `${companyRounds.company} supports ${availableSetupRounds.map((round) => round.label).join(", ")}. Only these rounds can be started for this company.`}
              {form.target_company.trim() && !companyLoading && companyRounds.resolved && !availableSetupRounds.length && `${companyRounds.company} has no supported interview rounds in the dataset.`}
            </div>
            {isProjectRound && <label className="mt-4 grid gap-2 text-sm text-slate-300">
              <span>Job description</span>
              <textarea value={form.job_description} onChange={(e) => setForm({ ...form, job_description: e.target.value })} placeholder="Paste the job description for Project + Behavioural interview personalization" className="h-28 w-full resize-y rounded border border-slate-700 bg-slate-950 p-3 text-sm text-slate-100 outline-none focus:border-cyan-400" />
            </label>}
            {isProjectRound && <label className="mt-4 flex cursor-pointer items-center gap-3 rounded border border-dashed border-slate-700 p-4 text-sm text-slate-300">
              <Upload size={18} />
              <span>{resume ? resume.name : "Upload resume for personalised project and behavioural questions"}</span>
              <input className="hidden" type="file" accept=".pdf,.txt" onChange={(e) => setResume(e.target.files?.[0] || null)} />
            </label>}
            <button className="mt-5 inline-flex items-center gap-2 rounded bg-cyan-400 px-4 py-2 font-semibold text-slate-950 disabled:opacity-50" onClick={startSession} disabled={isBusy || !canStartConfiguredInterview}>
              <Play size={18} /> Start interview
            </button>
          </div>

          <div className="rounded border border-slate-800 bg-slate-900 p-5">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold"><FileText size={19} className="text-cyan-300" /> Critical Resume Review</h2>
            <label className="flex cursor-pointer items-center gap-3 rounded border border-dashed border-slate-700 p-4 text-sm text-slate-300">
              <Upload size={18} />
              <span>{resumeReviewFile ? resumeReviewFile.name : "Upload resume for instant critique"}</span>
              <input className="hidden" type="file" accept=".pdf,.txt" onChange={(e) => setResumeReviewFile(e.target.files?.[0] || null)} />
            </label>
            <button className="mt-4 rounded border border-slate-600 px-4 py-2 text-sm font-medium text-slate-100 disabled:opacity-50" onClick={reviewResume} disabled={!resumeReviewFile || isBusy}>Review resume</button>
            {resumeReview && <div className="mt-4 space-y-3 text-sm text-slate-300">
              <div className="text-2xl font-semibold text-cyan-300">{resumeReview.review.score}/100</div>
              {(resumeReview.review.critical_issues.length ? resumeReview.review.critical_issues : ["Resume is readable. Strengthen proof, scale, and project defense."]).map((x) => <p key={x} className="rounded bg-slate-950 p-3">{x}</p>)}
            </div>}
          </div>
        </section>
      </main>
    )
  }

  return (
    <main className="grid h-screen grid-rows-[auto_1fr] bg-slate-950 text-slate-100">
      {error && <div className="fixed left-1/2 top-4 z-50 max-w-xl -translate-x-1/2 rounded border border-red-400 bg-red-950 px-4 py-3 text-sm text-red-100">{error}</div>}
      <header className="flex items-center justify-between border-b border-slate-800 bg-slate-900 px-4 py-3">
        <div className="flex items-center gap-3">
          <button onClick={() => setScreen("dashboard")} className="rounded border border-slate-700 bg-slate-950 px-2 py-2 text-slate-200" title="Back to dashboard"><ArrowLeft size={18} /></button>
          <Bot className="text-cyan-300" />
          <div>
            <div className="font-semibold">{roundTitle}</div>
            <div className="text-xs text-slate-400">{voiceState.replace("_", " ")} - {form.difficulty}{liveTranscript ? ` - "${liveTranscript.slice(0, 70)}"` : ""}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isDsaRound && dsaProgress && (
            <div className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200">
              <div className="font-semibold text-cyan-300">{dsaProgress.label || `Question ${dsaProgress.current_question_index} of ${dsaProgress.total_questions}`}</div>
              <div className={dsaProgress.time_expired ? "text-red-300" : "text-slate-400"}>
                {formatTimer(dsaProgress.remaining_seconds)} left · {dsaProgress.allocated_minutes}m round · ~{dsaProgress.per_question_minutes}m / q
              </div>
            </div>
          )}
          {liveTranscript && voiceState !== "listening" && <button onClick={sendCapturedTranscript} disabled={isBusy} className="rounded border border-emerald-500 bg-emerald-950 px-3 py-2 text-sm text-emerald-100 disabled:opacity-50" title="Send captured speech"><Send size={16} /></button>}
          <button onClick={toggleMic} className={`rounded border px-3 py-2 text-sm ${autoVoice || voiceState === "listening" ? "border-red-400 bg-red-950 text-red-100" : "border-cyan-600 bg-cyan-950 text-cyan-100"}`}>{autoVoice || voiceState === "listening" ? "Stop voice" : "Start voice"}</button>
          <button onClick={() => setChatOpen(true)} className="rounded border border-cyan-600 bg-cyan-950 px-3 py-2 text-sm text-cyan-100">AI chat</button>
          <button onClick={() => setTranscriptOpen(true)} className="rounded border border-slate-600 px-3 py-2 text-sm">Transcript</button>
          <button onClick={finishInterview} className="rounded border border-slate-600 px-3 py-2 text-sm">End & report</button>
        </div>
      </header>

      {warning && <div className="fixed left-1/2 top-20 z-20 flex -translate-x-1/2 items-center gap-2 rounded bg-amber-300 px-4 py-2 font-medium text-slate-950"><AlertTriangle size={18} /> {warning}</div>}

      <div className="fixed z-20 w-48 rounded border border-slate-700 bg-slate-950/95 p-2 shadow-2xl" style={{ left: cameraPos.x, top: cameraPos.y }}>
        <div onPointerDown={startCameraDrag} className="mb-2 flex cursor-move touch-none select-none items-center justify-between px-1 text-xs text-slate-300"><span className="flex items-center gap-1"><Camera size={14} /> Candidate</span><span>{voiceState === "listening" ? "Listening" : voiceState === "ai_speaking" ? "AI speaking" : "Mic ready"}</span></div>
        <video ref={videoRef} autoPlay muted playsInline className="aspect-video w-full rounded bg-slate-900 object-cover" />
        {liveTranscript && <div className="mt-2 rounded bg-slate-900 p-2 text-xs text-cyan-100">{liveTranscript}</div>}
      </div>

      <section className="grid min-h-0 grid-cols-1 gap-4 p-4 lg:grid-cols-2">
        <aside className="h-[calc(100vh-96px)] overflow-y-auto rounded border border-slate-800 bg-slate-900">
          <div className="sticky top-0 z-10 border-b border-slate-800 bg-slate-900 px-5 py-4">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm text-slate-400">{isDsaRound ? (dsaProgress?.label || `Question ${dsaProgress?.current_question_index || 1} of ${dsaProgress?.total_questions || "?"}`) : isCsRound ? "Concept interview" : "Project interview"}</div>
                <h2 className="truncate text-xl font-semibold">{isDsaRound ? currentProblem?.title : isCsRound ? "CS Fundamentals" : "Project + Behavioural"}</h2>
              </div>
              {currentProblem && <span className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300">{currentProblem.difficulty}</span>}
            </div>
            {session?.dataset_size && <div className="mt-2 text-xs text-slate-500">Dataset: {session.dataset_size.toLocaleString()} {session.dataset_label || "public DSA problems"}{session.target_company ? ` - ${session.target_company}` : ""}</div>}
            {currentProblem?.companies?.length > 0 && <div className="mt-2 text-xs text-cyan-300">Seen in: {currentProblem.companies.slice(0, 5).join(", ")}{currentProblem.companies.length > 5 ? "..." : ""}</div>}
          </div>
          {isDsaRound ? (
            <div className="space-y-5 p-5 text-sm text-slate-300">
              <p className="leading-7">{currentProblem?.prompt}</p>
              <ProblemBlock title="Examples" items={(currentProblem?.examples || []).map((ex) => `Input: ${ex.input}\nOutput: ${ex.output}\n${ex.explanation || ""}`)} />
              <ProblemBlock title="Visible Test Cases" items={(currentProblem?.testcases || []).filter((tc) => tc.visible !== false).slice(0, 4).map((tc) => `stdin:\n${tc.input.trim()}\nexpected:\n${tc.expected_output}`)} />
              {currentProblem?.constraints?.length > 0 && <div><div className="mb-2 font-semibold text-slate-100">Constraints</div><ul className="grid gap-2 text-xs text-slate-400">{currentProblem.constraints.map((x) => <li key={x} className="rounded bg-slate-950 p-2">{x}</li>)}</ul></div>}
            </div>
          ) : isCsRound ? (
            <CsRoundPanel messages={messages} lastAiMessage={lastAiMessage} session={session} form={form} />
          ) : (
            <RoundContext title="Project + Behavioural" items={[`Company: ${session?.target_company || form.target_company || "General"}`, `Role: ${form.job_role}`, "Focus: resume projects, JD fit, ownership, tradeoffs, STAR examples", form.job_description ? "Job description was provided before the round." : "No job description was provided."]} />
          )}
        </aside>

        <section className="h-[calc(100vh-96px)] min-h-0">
          {isDsaRound ? <div className="h-full rounded border border-slate-800 bg-slate-900">
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <div className="flex items-center gap-2 font-semibold"><Code2 size={18} /> Code</div>
              <select className="w-40 py-2 text-sm" value={language} onChange={(e) => setLanguage(e.target.value)} aria-label="Coding language">
                <option value="python">Python</option>
                <option value="cpp">C++</option>
                <option value="c">C</option>
                <option value="java">Java</option>
              </select>
            </div>
            <div className="grid h-[calc(100%-57px)] grid-rows-[1fr_auto]">
              <Editor language={monacoLanguage(language)} theme="vs-dark" value={code} onChange={(value) => setCode(value || "")} onMount={onEditorMount} options={{ minimap: { enabled: false }, fontSize: 14 }} />
              <div className="grid gap-2 border-t border-slate-800 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <button onClick={runTests} disabled={isBusy} className="inline-flex items-center gap-2 rounded border border-slate-600 bg-slate-800 px-4 py-2 font-semibold text-slate-100 disabled:opacity-50"><Play size={17} /> Run</button>
                    <button onClick={submitCode} disabled={isBusy} className="inline-flex items-center gap-2 rounded bg-amber-300 px-4 py-2 font-semibold text-[#07120f] disabled:opacity-50"><Send size={17} /> Submit</button>
                  </div>
                  {codeResult && <span className="text-sm text-slate-300">{codeResult.passed_testcases}/{codeResult.total_testcases} tests passed · {codeResult.overall_score}% · {codeResult.language}</span>}
                </div>
                {codeResult && <div className="grid max-h-56 gap-2 overflow-y-auto md:grid-cols-2">
                  {(codeResult.testcase_results || []).map((tc, index) => <div key={`${testValue(tc.input)}-${index}`} className={`rounded border p-2 text-xs ${tc.passed ? "border-emerald-800 bg-emerald-950/80 text-emerald-100" : "border-red-800 bg-red-950/80 text-red-100"}`}>
                    <div className="mb-1 flex items-center justify-between gap-2 font-semibold">
                      <span>{tc.visible ? `Case ${index + 1}` : `Hidden ${index + 1}`}</span>
                      <span>{tc.passed ? "Passed" : "Failed"}</span>
                    </div>
                    <div className="grid gap-1 font-mono text-[11px] leading-5 text-slate-100">
                      <div><span className="text-slate-400">Input:</span> {testValue(tc.input)}</div>
                      <div><span className="text-slate-400">Expected:</span> {testValue(tc.expected_output)}</div>
                      <div><span className="text-slate-400">Actual:</span> {testValue(tc.actual_output)}</div>
                      {tc.stderr && <div className="whitespace-pre-wrap text-red-200"><span className="text-slate-400">Error:</span> {tc.stderr}</div>}
                    </div>
                  </div>)}
                </div>}
              </div>
            </div>
          </div> : <InterviewWorkspace input={input} setInput={setInput} isBusy={isBusy} sendMessage={sendMessage} toggleMic={toggleMic} autoVoice={autoVoice} voiceState={voiceState} liveTranscript={liveTranscript} lastAiMessage={lastAiMessage} isCsRound={isCsRound} scratchpad={scratchpad} setScratchpad={setScratchpad} scratchpadMode={scratchpadMode} setScratchpadMode={setScratchpadMode} />}
        </section>

        {transcriptOpen && <aside className="fixed bottom-0 right-0 top-0 z-30 flex w-[420px] max-w-[96vw] flex-col border-l border-slate-700 bg-slate-950 shadow-2xl">
          <div className="flex items-center justify-between border-b border-slate-800 p-3">
            <span className="font-semibold">Interview Transcript</span>
            <button onClick={() => setTranscriptOpen(false)} className="rounded border border-slate-700 px-2 py-1 text-xs">Close</button>
          </div>
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
            {messages.map((m, i) => m.role === "thinking" ? <div key={i} className="flex items-center gap-2 rounded bg-cyan-950/50 p-3 text-sm text-cyan-200 animate-pulse"><span className="inline-block h-2 w-2 rounded-full bg-cyan-400 animate-bounce" />Thinking...</div> : <div key={i} className={`rounded p-3 text-sm ${m.role === "candidate" ? "bg-slate-800" : m.role === "system" ? "border border-cyan-600 bg-cyan-900/30 text-cyan-300 text-xs" : "bg-cyan-950 text-cyan-50"}`}><b>{m.role === "candidate" ? "You" : m.role === "system" ? "↑" : "AI"}:</b> {m.content}{m.degraded && <span className="ml-2 rounded bg-amber-900/60 px-1.5 py-0.5 text-[10px] text-amber-300" title="AI service was temporarily unavailable — this is a pre-built response">offline mode</span>}</div>)}
            {liveTranscript && <div className="rounded border border-cyan-700 bg-slate-900 p-3 text-sm text-cyan-100"><b>Hearing now:</b> {liveTranscript}</div>}
          </div>
          <div className="border-t border-slate-800 p-3 text-xs text-slate-400">Live transcript of AI and candidate turns. Click Start voice once; browser permission is required.</div>
        </aside>}

        {chatOpen && <aside className="fixed bottom-5 right-5 z-40 flex h-[520px] w-[460px] max-w-[96vw] flex-col rounded border border-slate-700 bg-slate-950 shadow-2xl">
          <div className="flex items-center justify-between border-b border-slate-800 p-3">
            <span className="font-semibold">AI Interviewer Chat</span>
            <button onClick={() => setChatOpen(false)} className="rounded border border-slate-700 px-2 py-1 text-xs">Close</button>
          </div>
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
            <div className="rounded bg-slate-900 p-3 text-sm text-slate-300"><b>Current probe:</b> {lastAiMessage}</div>
            {messages.slice(-6).map((m, i) => m.role === "thinking" ? <div key={i} className="flex items-center gap-2 rounded bg-cyan-950/50 p-3 text-sm text-cyan-200 animate-pulse"><span className="inline-block h-2 w-2 rounded-full bg-cyan-400 animate-bounce" />Thinking...</div> : <div key={i} className={`rounded p-3 text-sm ${m.role === "candidate" ? "bg-slate-800" : m.role === "system" ? "border border-cyan-600 bg-cyan-900/30 text-cyan-300 text-xs" : "bg-cyan-950 text-cyan-50"}`}><b>{m.role === "candidate" ? "You" : m.role === "system" ? "↑" : "AI"}:</b> {m.content}{m.degraded && <span className="ml-2 rounded bg-amber-900/60 px-1.5 py-0.5 text-[10px] text-amber-300" title="AI service was temporarily unavailable — this is a pre-built response">offline mode</span>}</div>)}
          </div>
          <div className="border-t border-slate-800 p-3">
            <textarea value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask for clarification, request a hint, or answer..." className="h-24 w-full resize-none rounded border border-slate-700 bg-slate-950 p-3 text-sm outline-none focus:border-cyan-400" />
            <div className="mt-2 flex gap-2">
              <button onClick={() => sendMessage()} disabled={isBusy} className="flex-1 rounded bg-cyan-400 px-3 py-2 font-semibold text-slate-950 disabled:opacity-50">Send</button>
              <button onClick={toggleMic} className={`rounded border px-3 py-2 ${autoVoice || voiceState === "listening" ? "border-red-400 text-red-200" : "border-slate-600"}`} title="Toggle microphone">{autoVoice || voiceState === "listening" ? <Square size={18} /> : <Mic size={18} />}</button>
            </div>
            {liveTranscript && <div className="mt-2 rounded bg-slate-900 p-2 text-xs text-cyan-100">Hearing: {liveTranscript}</div>}
          </div>
        </aside>}
      </section>
    </main>
  )
}

function WelcomePage({ error, onAuthenticate }) {
  return (
    <main className="min-h-screen overflow-hidden bg-[#06110f] text-white">
      {error && <div className="fixed left-1/2 top-4 z-30 max-w-xl -translate-x-1/2 rounded border border-red-300 bg-red-950 px-4 py-3 text-sm text-red-100">{error}</div>}
      <section className="relative min-h-screen">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_18%,rgba(251,191,36,.22),transparent_28%),radial-gradient(circle_at_82%_12%,rgba(45,212,191,.18),transparent_30%),linear-gradient(135deg,#06110f_0%,#10241f_48%,#1d1526_100%)]" />
        <div className="relative mx-auto grid min-h-screen max-w-7xl gap-8 px-6 py-8 lg:grid-cols-[1.05fr_.95fr] lg:items-center">
          <div className="max-w-3xl">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-4 py-2 text-sm text-emerald-100">
              <Sparkles size={16} /> AI interview prep built around real company rounds
            </div>
            <h1 className="text-5xl font-black leading-tight tracking-normal text-white md:text-7xl">CodeVoir<span className="block text-amber-300">Interview Arena</span></h1>
            <p className="mt-5 max-w-2xl text-lg leading-8 text-emerald-50/80">Practice DSA, CS fundamentals, and project-behavioural rounds with live AI feedback, code execution, integrity signals, and a performance dashboard that remembers every company attempt.</p>
            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              <WelcomeStat icon={<Code2 size={20} />} label="DSA rounds" value="Company tagged" />
              <WelcomeStat icon={<Brain size={20} />} label="AI reports" value="Evidence based" />
              <WelcomeStat icon={<BarChart3 size={20} />} label="Dashboard" value="Score trends" />
            </div>
          </div>

          <section className="rounded border border-emerald-300/20 bg-[#07120f]/85 p-6 shadow-2xl shadow-black/40 backdrop-blur">
            <h2 className="text-2xl font-bold">Sign in with OAuth</h2>
            <p className="mt-2 text-sm leading-6 text-emerald-50/70">CodeVoir now uses backend OAuth. You will be redirected to the configured identity provider, then returned to this dashboard.</p>
            <button type="button" onClick={onAuthenticate} className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded bg-amber-300 px-4 py-3 font-bold text-[#07120f] shadow-lg shadow-amber-900/20">
              <LogIn size={18} /> Continue with OAuth
            </button>
            <p className="mt-4 text-xs leading-5 text-emerald-50/55">Backend setup required: set OAuth client id, secret, callback URL, and frontend URL in the backend environment.</p>
          </section>
        </div>
      </section>
    </main>
  )
}

function WelcomeStat({ icon, label, value }) {
  return <div className="rounded border border-white/10 bg-white/10 p-4 backdrop-blur">
    <div className="text-amber-200">{icon}</div>
    <div className="mt-3 text-sm text-emerald-50/60">{label}</div>
    <div className="font-semibold text-white">{value}</div>
  </div>
}

/*
function ResumeQuestZone({ error, form, setForm, companies, companyDirectory, companyRounds, companyLoading, file, setFile, result, savedResume, workspace, setWorkspace, onUploadSavedResume, onSaveWorkspace, onRescoreWorkspace, onExportPdf, onRun, onBack, isBusy }) {
  const resolved = companyRounds.resolved
  const canQuest = (file || savedResume) && resolved && form.job_description.trim().length >= 80
  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      {error && <div className="fixed left-1/2 top-4 z-30 max-w-xl -translate-x-1/2 rounded border border-red-400 bg-red-950 px-4 py-3 text-sm text-red-100">{error}</div>}
      <section className="border-b border-slate-800 bg-slate-900">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <button onClick={onBack} className="grid h-10 w-10 place-items-center rounded border border-slate-700 bg-slate-950 text-slate-200" title="Back to dashboard"><ArrowLeft size={20} /></button>
            <div>
              <h1 className="text-xl font-semibold">Resume Quest Zone</h1>
              <p className="text-sm text-slate-400">Company-specific resume enhancement before the interview loop.</p>
            </div>
          </div>
          <div className="hidden items-center gap-2 text-sm text-emerald-300 md:flex"><Sparkles size={16} /> Earn resume XP</div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-6 px-6 py-6 lg:grid-cols-[.85fr_1.15fr]">
        <div className="grid gap-6">
        <div className="rounded border border-slate-800 bg-slate-900 p-5">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold"><FileText size={19} className="text-emerald-300" /> Saved Resume</h2>
          {savedResume ? (
            <div className="rounded border border-slate-800 bg-slate-950 p-4">
              <div className="font-semibold text-slate-100">{savedResume.filename}</div>
              <div className="mt-1 text-sm text-slate-500">Version {savedResume.version} · updated {formatDate(savedResume.updated_at)}</div>
              <div className="mt-3 text-xs text-emerald-300">This resume is reused whenever you log in. Upload a new file to replace it.</div>
            </div>
          ) : (
            <div className="rounded border border-slate-800 bg-slate-950 p-4 text-sm text-slate-400">Upload your resume once. It will stay with your account and power future quests.</div>
          )}
          <label className="mt-4 flex cursor-pointer items-center gap-3 rounded border border-dashed border-slate-700 p-4 text-sm text-slate-300">
            <Upload size={18} />
            <span>{savedResume ? "Replace saved resume PDF/TXT" : "Upload resume PDF/TXT"}</span>
            <input className="hidden" type="file" accept=".pdf,.txt" onChange={(e) => onUploadSavedResume(e.target.files?.[0] || null)} />
          </label>
        </div>

        <div className="rounded border border-slate-800 bg-slate-900 p-5">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold"><Sparkles size={19} className="text-emerald-300" /> Start Resume Quest</h2>
          <div className="grid gap-4">
            <Field label="Target company">
              <input list="resume-company-options" value={form.target_company} onChange={(e) => setForm({ ...form, target_company: e.target.value })} placeholder="Search company with interview data" />
              <datalist id="resume-company-options">
                {(companyDirectory.length ? companyDirectory : companies.map((company) => ({ company }))).map((item) => <option key={item.company} value={item.company} />)}
              </datalist>
            </Field>
            <Field label="Job role"><input value={form.job_role} onChange={(e) => setForm({ ...form, job_role: e.target.value })} /></Field>
            <label className="grid gap-2 text-sm text-slate-300">
              <span>Company job description</span>
              <textarea value={form.job_description} onChange={(e) => setForm({ ...form, job_description: e.target.value })} placeholder="Paste the exact JD for this company role..." className="h-44 w-full resize-y rounded border border-slate-700 bg-slate-950 p-3 text-sm text-slate-100 outline-none focus:border-emerald-400" />
            </label>
            <label className="flex cursor-pointer items-center gap-3 rounded border border-dashed border-slate-700 p-4 text-sm text-slate-300">
              <Upload size={18} />
              <span>{file ? file.name : savedResume ? "Optional: use a different resume only for this quest" : "Upload current resume PDF/TXT"}</span>
              <input className="hidden" type="file" accept=".pdf,.txt" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            </label>
          </div>
          <div className="mt-4 rounded bg-slate-950 p-3 text-xs text-slate-400">
            {!form.target_company.trim() && "Select a company to personalize the resume quest."}
            {form.target_company.trim() && companyLoading && "Checking company data..."}
            {form.target_company.trim() && !companyLoading && !resolved && "Company not found in the interview data."}
            {form.target_company.trim() && !companyLoading && resolved && `${companyRounds.company} is ready for a company-specific resume quest.`}
          </div>
          <button onClick={onRun} disabled={isBusy || !canQuest} className="mt-5 inline-flex items-center gap-2 rounded bg-emerald-400 px-4 py-2 font-semibold text-slate-950 disabled:opacity-50">
            <Sparkles size={18} /> Generate quest
          </button>
        </div>
        </div>

        <div className="rounded border border-slate-800 bg-slate-900 p-5">
          <h2 className="mb-4 text-lg font-semibold">Quest Result</h2>
          {result ? <ResumeQuestResult quest={result.quest || result} workspace={workspace} setWorkspace={setWorkspace} onSave={onSaveWorkspace} onRescore={onRescoreWorkspace} onExportPdf={onExportPdf} isBusy={isBusy} /> : (
            <div className="grid gap-4">
              <div className="rounded border border-slate-800 bg-slate-950 p-6 text-sm leading-6 text-slate-400">Your quest result will show resume alignment score, XP earned, missing JD keywords, missions to complete, and suggested bullet rewrites.</div>
              {workspace && <ResumeWorkspaceEditor workspace={workspace} setWorkspace={setWorkspace} onSave={onSaveWorkspace} onExportPdf={onExportPdf} isBusy={isBusy} />}
            </div>
          )}
        </div>
      </section>
    </main>
  )
}

function ResumeQuestResult({ quest, workspace, setWorkspace, onSave, onRescore, onExportPdf, isBusy }) {
  const suggestions = quest.quest?.suggested_bullets || quest.suggested_bullets || []
  function applySuggestions() {
    if (!workspace) return
    const projects = workspace.projects?.length ? [...workspace.projects] : [{ name: "Selected Project", tech: [], bullets: [] }]
    projects[0] = { ...projects[0], bullets: [...(projects[0].bullets || []), ...suggestions].slice(0, 8) }
    setWorkspace({ ...workspace, projects })
  }
  return (
    <div className="grid gap-4">
      <div className="rounded border border-slate-800 bg-slate-950 p-4">
        <div className="text-sm text-slate-500">{quest.target_company || quest.company} · {quest.job_role}</div>
        <div className="mt-2 flex flex-wrap items-end gap-4">
          <div className="text-4xl font-semibold text-emerald-300">{quest.quest?.score ?? quest.score}/100</div>
          <div className="pb-1 text-cyan-300">{quest.quest?.xp ?? quest.xp} XP earned</div>
        </div>
        <p className="mt-3 text-sm leading-6 text-slate-400">{quest.quest?.summary || quest.summary}</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <ResumeQuestList title="Matched JD signals" items={quest.quest?.matched_keywords || quest.matched_keywords || []} tone="emerald" />
        <ResumeQuestList title="Keyword gaps" items={quest.quest?.missing_keywords || quest.missing_keywords || []} tone="amber" />
      </div>
      <div className="rounded border border-slate-800 bg-slate-950 p-4">
        <h3 className="text-sm font-semibold uppercase text-slate-400">Enhancement missions</h3>
        <div className="mt-3 grid gap-3">
          {(quest.quest?.missions || quest.missions || []).map((mission) => <div key={mission.title} className="rounded bg-slate-900 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="font-semibold text-slate-100">{mission.title}</div>
              <div className="text-xs text-emerald-300">{mission.xp} XP</div>
            </div>
            <p className="mt-1 text-sm text-slate-400">{mission.detail}</p>
          </div>)}
        </div>
      </div>
      <ResumeQuestList title="Suggested bullet rewrites" items={quest.quest?.suggested_bullets || quest.suggested_bullets || []} tone="cyan" />
      {workspace && (
        <div className="rounded border border-slate-800 bg-slate-950 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold text-slate-100">Editable Resume Workspace</h3>
              <p className="mt-1 text-sm text-slate-500">Apply suggestions, edit the resume, re-score it, then export a polished PDF.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={applySuggestions} disabled={!suggestions.length || isBusy} className="rounded border border-cyan-600 bg-cyan-950 px-3 py-2 text-sm text-cyan-100 disabled:opacity-50">Apply suggestions</button>
              <button onClick={() => onRescore(workspace)} disabled={isBusy} className="rounded border border-emerald-600 bg-emerald-950 px-3 py-2 text-sm text-emerald-100 disabled:opacity-50">Save + re-score</button>
              <button onClick={() => onExportPdf(workspace)} disabled={isBusy} className="rounded bg-emerald-400 px-3 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">Export PDF</button>
            </div>
          </div>
          <div className="mt-4">
            <ResumeWorkspaceEditor workspace={workspace} setWorkspace={setWorkspace} onSave={onSave} onExportPdf={onExportPdf} isBusy={isBusy} compact />
          </div>
        </div>
      )}
    </div>
  )
}

function ResumeWorkspaceEditor({ workspace, setWorkspace, onSave, onExportPdf, isBusy, compact = false }) {
  const projects = workspace.projects || []
  const skillsText = (workspace.skills || []).join(", ")
  const firstProject = projects[0] || { name: "", tech: [], bullets: [] }
  const projectBullets = (firstProject.bullets || []).join("\n")

  function patch(next) {
    setWorkspace({ ...workspace, ...next })
  }

  function patchHeader(field, value) {
    setWorkspace({ ...workspace, header: { ...(workspace.header || {}), [field]: value } })
  }

  function patchProject(field, value) {
    const nextProjects = projects.length ? [...projects] : [{ name: "", tech: [], bullets: [] }]
    nextProjects[0] = { ...nextProjects[0], [field]: value }
    setWorkspace({ ...workspace, projects: nextProjects })
  }

  return (
    <div className="grid gap-4">
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Name"><input value={workspace.header?.name || ""} onChange={(e) => patchHeader("name", e.target.value)} /></Field>
        <Field label="Email"><input value={workspace.header?.email || ""} onChange={(e) => patchHeader("email", e.target.value)} /></Field>
      </div>
      <Field label="Professional summary">
        <textarea value={workspace.summary || ""} onChange={(e) => patch({ summary: e.target.value })} className={`${compact ? "h-24" : "h-28"} w-full resize-y rounded border border-slate-700 bg-slate-950 p-3 text-sm text-slate-100 outline-none focus:border-emerald-400`} />
      </Field>
      <Field label="Skills">
        <textarea value={skillsText} onChange={(e) => patch({ skills: e.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} className="h-20 w-full resize-y rounded border border-slate-700 bg-slate-950 p-3 text-sm text-slate-100 outline-none focus:border-emerald-400" />
      </Field>
      <div className="rounded border border-slate-800 bg-slate-900 p-3">
        <div className="mb-3 text-sm font-semibold text-slate-300">Primary project</div>
        <div className="grid gap-3">
          <Field label="Project name"><input value={firstProject.name || ""} onChange={(e) => patchProject("name", e.target.value)} /></Field>
          <Field label="Tech"><input value={(firstProject.tech || []).join(", ")} onChange={(e) => patchProject("tech", e.target.value.split(",").map((item) => item.trim()).filter(Boolean))} /></Field>
          <Field label="Bullets">
            <textarea value={projectBullets} onChange={(e) => patchProject("bullets", e.target.value.split("\n").map((item) => item.trim()).filter(Boolean))} className="h-36 w-full resize-y rounded border border-slate-700 bg-slate-950 p-3 text-sm text-slate-100 outline-none focus:border-emerald-400" />
          </Field>
        </div>
      </div>
      {!compact && (
        <div className="flex flex-wrap gap-2">
          <button onClick={() => onSave(workspace)} disabled={isBusy} className="rounded border border-emerald-600 bg-emerald-950 px-3 py-2 text-sm text-emerald-100 disabled:opacity-50">Save workspace</button>
          <button onClick={() => onExportPdf(workspace)} disabled={isBusy} className="rounded bg-emerald-400 px-3 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">Export polished PDF</button>
        </div>
      )}
    </div>
  )
}

function ResumeQuestList({ title, items, tone }) {
  const color = tone === "emerald" ? "text-emerald-300" : tone === "amber" ? "text-amber-300" : "text-cyan-300"
  return <div className="rounded border border-slate-800 bg-slate-950 p-4">
    <h3 className={`text-sm font-semibold uppercase ${color}`}>{title}</h3>
    <div className="mt-3 flex flex-wrap gap-2">
      {items.length ? items.map((item) => <span key={typeof item === "string" ? item : item.title} className="rounded bg-slate-900 px-2 py-1 text-xs text-slate-300">{typeof item === "string" ? item : item.title}</span>) : <span className="text-sm text-slate-500">No items yet.</span>}
    </div>
  </div>
}

*/
function DashboardHistory({ userProfile, dashboard, loading, error, onStart, onRefresh, onOpenReport, onLogout, isBusy }) {
  const stats = dashboard.stats || defaultDashboard.stats
  const xp = dashboard.xp || defaultDashboard.xp
  const interviews = dashboard.interviews || []
  const completed = interviews.filter((item) => item.has_report)
  const topicInsights = buildTopicInsights(completed.filter((item) => item.round_type !== "cs_fundamentals"))
  const csReports = completed.filter((item) => item.round_type === "cs_fundamentals")
  const csTopicInsights = buildTopicInsights(csReports)
  const csSkillInsights = buildParameterInsights(csReports)
  const behaviorInsights = buildBehaviorInsights(completed)
  const grouped = interviews.reduce((acc, item) => {
    const company = item.target_company || "General"
    acc[company] = acc[company] || []
    acc[company].push(item)
    return acc
  }, {})
  const companyNames = Object.keys(grouped).sort((a, b) => a.localeCompare(b))

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      {error && <div className="fixed left-1/2 top-4 z-30 max-w-xl -translate-x-1/2 rounded border border-red-400 bg-red-950 px-4 py-3 text-sm text-red-100">{error}</div>}
      <section className="border-b border-slate-800 bg-slate-900">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <h1 className="text-xl font-semibold">Dashboard</h1>
            <p className="text-sm text-slate-400">{userProfile.name} - company interviews and past results</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={onRefresh} disabled={loading} className="rounded border border-slate-700 px-3 py-2 text-sm text-slate-200 disabled:opacity-50">Refresh</button>
            <button onClick={() => onStart("dsa")} className="inline-flex items-center gap-2 rounded bg-cyan-400 px-4 py-2 font-semibold text-slate-950"><Play size={18} /> Take new interview</button>
            <button onClick={onLogout} className="inline-flex items-center gap-2 rounded border border-slate-700 px-3 py-2 text-sm text-slate-300"><LogOut size={16} /> Logout</button>
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-6 px-6 py-6">
        <div className="grid gap-4 md:grid-cols-5">
          <DashboardMetric icon={<Briefcase size={18} />} label="Interviews taken" value={stats.total_interviews} />
          <DashboardMetric icon={<FileText size={18} />} label="Results ready" value={stats.completed_interviews} />
          <DashboardMetric icon={<Target size={18} />} label="Companies" value={stats.companies_practiced} />
          <DashboardMetric icon={<TrendingUp size={18} />} label="Average score" value={`${stats.average_score || 0}/100`} />
          <DashboardMetric icon={<Sparkles size={18} />} label="XP level" value={`L${xp.level || 1}`} />
        </div>

        <DashboardXp xp={xp} />

        <DashboardAnalytics topics={topicInsights} csTopics={csTopicInsights} csSkills={csSkillInsights} behavior={behaviorInsights} />

        <div className="rounded border border-slate-800 bg-slate-900">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-4">
            <div>
              <h2 className="text-lg font-semibold">Interview History By Company</h2>
              <p className="mt-1 text-sm text-slate-500">This section only shows interviews you have already taken and their generated results.</p>
            </div>
            <div className="text-sm text-slate-500">{completed.length} result{completed.length === 1 ? "" : "s"} ready</div>
          </div>

          {companyNames.length ? (
            <div className="divide-y divide-slate-800">
              {companyNames.map((company) => {
                const items = grouped[company]
                const ready = items.filter((item) => item.has_report)
                const average = ready.length ? Math.round(ready.reduce((sum, item) => sum + (Number(item.overall_score) || 0), 0) / ready.length) : 0
                return (
                  <section key={company} className="p-5">
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <h3 className="text-base font-semibold text-slate-100">{company}</h3>
                        <p className="text-sm text-slate-500">{items.length} interview{items.length === 1 ? "" : "s"} taken</p>
                      </div>
                      <div className="flex flex-wrap items-center gap-4 text-right">
                        <CompanyXpMini company={dashboard.companies?.find((entry) => entry.company === company)} />
                        <div>
                          <div className="text-xl font-semibold text-cyan-300">{average}</div>
                          <div className="text-xs text-slate-500">avg score</div>
                        </div>
                      </div>
                    </div>

                    <div className="grid gap-3">
                      {items.map((item) => (
                        <div key={item.session_id} className="grid gap-4 rounded border border-slate-800 bg-slate-950 p-4 lg:grid-cols-[1fr_auto]">
                          <div>
                            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                              <span className="inline-flex items-center gap-1"><Calendar size={14} /> {formatDate(item.completed_at || item.created_at)}</span>
                              <span>{prettyRound(item.round_type)}</span>
                              {item.problem_title && <span>{item.problem_title}</span>}
                            </div>
                            <h4 className="mt-2 font-semibold">{item.job_role || "Software Engineer"}</h4>
                            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">{item.summary || "Interview started. End the interview to generate a result report."}</p>
                          </div>
                          <div className="flex min-w-40 flex-col items-start gap-2 lg:items-end">
                            <ScoreBadge score={item.overall_score} />
                            <div className="text-sm text-slate-400">{item.hiring_signal || "In progress"}</div>
                            {item.has_report ? (
                              <button onClick={() => onOpenReport(item.session_id)} disabled={isBusy} className="rounded border border-cyan-600 bg-cyan-950 px-3 py-2 text-sm text-cyan-100 disabled:opacity-50">View result</button>
                            ) : (
                              <span className="rounded border border-slate-700 px-3 py-2 text-sm text-slate-500">No result yet</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                )
              })}
            </div>
          ) : (
            <div className="p-8">
              <h3 className="text-xl font-semibold">No interviews taken yet.</h3>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">After you complete an interview, this dashboard will show the company, round type, score, report status, and result details here.</p>
            </div>
          )}
        </div>
      </section>
    </main>
  )
}

function DashboardXp({ xp }) {
  const progress = Math.max(0, Math.min(100, Number(xp.level_progress) || 0))
  const cards = xp.company_cards || []
  const goals = xp.next_goals || []
  return (
    <section className="grid gap-4 lg:grid-cols-[.9fr_1.1fr]">
      <div className="rounded border border-cyan-700/50 bg-slate-900 p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 rounded bg-cyan-950 px-3 py-1 text-xs font-semibold uppercase text-cyan-200"><Sparkles size={14} /> XP System</div>
            <h2 className="mt-4 text-3xl font-semibold text-white">Level {xp.level || 1}</h2>
            <p className="mt-1 text-sm text-slate-400">{xp.title || "Interview Rookie"} · {(xp.total_xp || 0).toLocaleString()} XP earned</p>
          </div>
          <div className="rounded border border-slate-800 bg-slate-950 px-4 py-3 text-right">
            <div className="text-2xl font-semibold text-cyan-300">{xp.completed_company_sets || 0}</div>
            <div className="text-xs text-slate-500">company sets</div>
          </div>
        </div>
        <div className="mt-5">
          <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
            <span>Level progress</span>
            <span>{xp.xp_to_next_level || 0} XP to next level</span>
          </div>
          <div className="h-3 overflow-hidden rounded bg-slate-950">
            <div className="h-full rounded bg-cyan-400" style={{ width: `${progress}%` }} />
          </div>
        </div>
        <div className="mt-4 grid gap-2 text-xs text-slate-400">
          {(xp.rules || []).slice(0, 3).map((rule) => <div key={rule} className="rounded border border-slate-800 bg-slate-950 px-3 py-2">{rule}</div>)}
        </div>
      </div>

      <div className="rounded border border-slate-800 bg-slate-900 p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Company Mastery</h2>
            <p className="mt-1 text-sm text-slate-500">Finish every available round for a company to unlock the larger XP bonus.</p>
          </div>
          <Shield className="text-cyan-300" size={20} />
        </div>
        {cards.length ? (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {cards.slice(0, 4).map((card) => <CompanyXpCard key={card.company} card={card} />)}
          </div>
        ) : (
          <AnalyticsEmpty text="Complete your first company interview to begin earning XP." />
        )}
        {goals.length > 0 && (
          <div className="mt-4 rounded border border-slate-800 bg-slate-950 p-3">
            <div className="text-xs font-semibold uppercase text-slate-500">Next best targets</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {goals.map((goal) => <span key={goal.company} className="rounded bg-slate-900 px-2 py-1 text-xs text-slate-300">{goal.company}: {goal.missing_rounds.map((round) => round.label).join(", ")}</span>)}
            </div>
          </div>
        )}
      </div>
    </section>
  )
}

function CompanyXpCard({ card }) {
  const total = Math.max(1, Number(card.available_round_count) || 1)
  const done = Math.min(total, Number(card.completed_round_count) || 0)
  const progress = Math.round((done / total) * 100)
  return (
    <div className="rounded border border-slate-800 bg-slate-950 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-slate-100">{card.company}</h3>
          <p className="mt-1 text-xs text-slate-500">{done}/{total} rounds complete</p>
        </div>
        <div className={`rounded px-2 py-1 text-xs font-semibold ${card.complete ? "bg-emerald-950 text-emerald-300" : "bg-cyan-950 text-cyan-300"}`}>{card.xp || 0} XP</div>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded bg-slate-900">
        <div className={`h-full rounded ${card.complete ? "bg-emerald-400" : "bg-cyan-400"}`} style={{ width: `${progress}%` }} />
      </div>
      <p className="mt-3 text-xs text-slate-500">{card.complete ? "Mastery bonus unlocked." : `Next: ${card.missing_rounds?.[0]?.label || "another round"}`}</p>
    </div>
  )
}

function CompanyXpMini({ company }) {
  if (!company?.available_round_count) return null
  const total = Math.max(1, Number(company.available_round_count) || 1)
  const done = Math.min(total, Number(company.completed_round_count) || 0)
  return (
    <div className="min-w-32 text-right">
      <div className="text-sm font-semibold text-slate-200">{company.xp || 0} XP</div>
      <div className="text-xs text-slate-500">{done}/{total} rounds</div>
      <div className="mt-1 h-1.5 overflow-hidden rounded bg-slate-800">
        <div className={`h-full ${company.company_complete ? "bg-emerald-400" : "bg-cyan-400"}`} style={{ width: `${Math.round((done / total) * 100)}%` }} />
      </div>
    </div>
  )
}

function ResumeQuestDashboard({ quests, onStart }) {
  const latest = quests?.[0]
  return (
    <section className="rounded border border-emerald-800/60 bg-slate-900 p-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded bg-emerald-950 px-3 py-1 text-xs font-semibold uppercase text-emerald-200"><FileText size={14} /> Resume Quest Zone</div>
          <h2 className="mt-3 text-xl font-semibold">Tailor your resume for a specific company JD</h2>
          <p className="mt-1 text-sm text-slate-500">Upload your resume, paste the job description, and get quest missions, keyword gaps, suggested bullets, and resume XP.</p>
        </div>
        <button onClick={onStart} className="rounded bg-emerald-400 px-4 py-2 font-semibold text-slate-950">Enter quest zone</button>
      </div>
      {latest ? (
        <div className="mt-4 grid gap-3 md:grid-cols-[.7fr_1.3fr]">
          <div className="rounded border border-slate-800 bg-slate-950 p-4">
            <div className="text-sm text-slate-500">Latest quest</div>
            <div className="mt-1 font-semibold text-slate-100">{latest.company} · {latest.job_role}</div>
            <div className="mt-3 flex items-end gap-3">
              <div className="text-3xl font-semibold text-emerald-300">{latest.score}</div>
              <div className="pb-1 text-sm text-slate-500">resume score</div>
            </div>
            <div className="mt-2 text-sm text-cyan-300">{latest.xp} XP earned</div>
          </div>
          <div className="rounded border border-slate-800 bg-slate-950 p-4">
            <div className="text-sm font-semibold text-slate-300">Priority missions</div>
            <div className="mt-3 grid gap-2">
              {(latest.missions || []).slice(0, 3).map((mission) => <div key={mission.title} className="rounded bg-slate-900 p-3 text-sm text-slate-300">{mission.title}</div>)}
            </div>
          </div>
        </div>
      ) : (
        <div className="mt-4 rounded border border-slate-800 bg-slate-950 p-4 text-sm text-slate-500">No resume quests completed yet.</div>
      )}
    </section>
  )
}

function DashboardAnalytics({ topics, csTopics, csSkills, behavior }) {
  const strongTopics = topics.filter((topic) => topic.average >= 70).slice(0, 6)
  const weakTopics = topics.filter((topic) => topic.average < 70).slice(0, 6)
  const hasTopics = topics.length > 0
  const csGraph = csTopics.length ? csTopics : csSkills
  const strongCsTopics = csGraph.filter((topic) => topic.average >= 70).slice(0, 6)
  const weakCsTopics = csGraph.filter((topic) => topic.average < 70).slice(0, 6)
  const hasCsGraph = csGraph.length > 0
  const csGraphLabel = csTopics.length ? "CS topics" : "CS skills"
  const hasBehavior = behavior.length > 0

  return (
    <section className="grid gap-4">
      <div className="rounded border border-slate-800 bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold">CS Fundamentals Topics</h2>
            <p className="mt-1 text-sm text-slate-500">Overall CS strengths and weaknesses from DBMS, OS, CN, OOP, and related rounds.</p>
          </div>
          <Brain className="text-cyan-300" size={20} />
        </div>
        {hasCsGraph ? (
          <div className="grid gap-5 p-5 xl:grid-cols-2">
            <TopicColumn title={`Strong ${csGraphLabel}`} topics={strongCsTopics} empty={`No strong ${csGraphLabel} yet.`} tone="strong" />
            <TopicColumn title={`${csGraphLabel} to revise`} topics={weakCsTopics} empty={`No weak ${csGraphLabel} detected yet.`} tone="weak" />
          </div>
        ) : (
          <AnalyticsEmpty text="Complete CS Fundamentals interviews and generate reports to unlock this graph." />
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.2fr_.8fr]">
      <div className="rounded border border-slate-800 bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold">Topic Strengths & Gaps</h2>
            <p className="mt-1 text-sm text-slate-500">Aggregated from topics asked across completed interview reports.</p>
          </div>
          <BarChart3 className="text-cyan-300" size={20} />
        </div>
        {hasTopics ? (
          <div className="grid gap-5 p-5 xl:grid-cols-2">
            <TopicColumn title="Strong topics" topics={strongTopics} empty="No strong topics yet." tone="strong" />
            <TopicColumn title="Topics to work on" topics={weakTopics} empty="No weak topics detected yet." tone="weak" />
          </div>
        ) : (
          <AnalyticsEmpty text="Complete interviews with generated reports to unlock topic analytics." />
        )}
      </div>

      <div className="rounded border border-slate-800 bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold">Behavioural Focus</h2>
            <p className="mt-1 text-sm text-slate-500">Traits to strengthen for project and behavioural rounds.</p>
          </div>
          <Brain className="text-cyan-300" size={20} />
        </div>
        {hasBehavior ? (
          <div className="space-y-3 p-5">
            {behavior.slice(0, 5).map((trait) => <TraitBar key={trait.name} trait={trait} />)}
          </div>
        ) : (
          <AnalyticsEmpty text="Take a Project + Behavioural interview to see personality and communication focus areas." />
        )}
      </div>
      </div>
    </section>
  )
}

function TopicColumn({ title, topics, empty, tone }) {
  return <div>
    <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">{title}</h3>
    <div className="space-y-3">
      {topics.length ? topics.map((topic) => <TopicBar key={topic.name} topic={topic} tone={tone} />) : <div className="rounded border border-slate-800 bg-slate-950 p-4 text-sm text-slate-500">{empty}</div>}
    </div>
  </div>
}

function TopicBar({ topic, tone }) {
  const color = tone === "strong" ? "bg-emerald-400" : "bg-amber-400"
  const text = tone === "strong" ? "text-emerald-300" : "text-amber-300"
  return <div className="rounded border border-slate-800 bg-slate-950 p-3">
    <div className="flex items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-slate-100">{topic.name}</div>
        <div className="text-xs text-slate-500">{topic.count} report{topic.count === 1 ? "" : "s"}</div>
      </div>
      <div className={`text-lg font-semibold ${text}`}>{topic.average}</div>
    </div>
    <div className="mt-3 h-2 rounded bg-slate-800">
      <div className={`h-2 rounded ${color}`} style={{ width: `${Math.max(4, topic.average)}%` }} />
    </div>
  </div>
}

function TraitBar({ trait }) {
  const needsWork = trait.average < 70
  const color = needsWork ? "bg-amber-400" : "bg-emerald-400"
  return <div className="rounded border border-slate-800 bg-slate-950 p-3">
    <div className="mb-2 flex items-center justify-between gap-3">
      <div>
        <div className="text-sm font-medium text-slate-100">{trait.name}</div>
        <div className="text-xs text-slate-500">{needsWork ? "Focus area" : "Currently solid"} · {trait.count} signal{trait.count === 1 ? "" : "s"}</div>
      </div>
      <div className={needsWork ? "text-lg font-semibold text-amber-300" : "text-lg font-semibold text-emerald-300"}>{trait.average}</div>
    </div>
    <div className="h-2 rounded bg-slate-800"><div className={`h-2 rounded ${color}`} style={{ width: `${Math.max(4, trait.average)}%` }} /></div>
  </div>
}

function AnalyticsEmpty({ text }) {
  return <div className="p-5">
    <div className="rounded border border-dashed border-slate-700 bg-slate-950 p-5 text-sm leading-6 text-slate-500">{text}</div>
  </div>
}

function Dashboard({ userProfile, dashboard, loading, error, onStart, onRefresh, onOpenReport, onLogout, isBusy }) {
  const stats = dashboard.stats || defaultDashboard.stats
  const interviews = dashboard.interviews || []
  const companies = dashboard.companies || []
  const latest = interviews[0]
  const completed = interviews.filter((item) => item.has_report)
  const dsaReports = interviews.filter((item) => item.round_type === "dsa")
  const completedDsa = dsaReports.filter((item) => item.has_report)
  const dsaAverage = completedDsa.length ? Math.round(completedDsa.reduce((sum, item) => sum + (Number(item.overall_score) || 0), 0) / completedDsa.length) : 0

  return (
    <main className="min-h-screen bg-[#07120f] text-slate-100">
      {error && <div className="fixed left-1/2 top-4 z-30 max-w-xl -translate-x-1/2 rounded border border-red-400 bg-red-950 px-4 py-3 text-sm text-red-100">{error}</div>}
      <section className="border-b border-emerald-900/50 bg-[#0b1b17]">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded bg-amber-300 text-[#07120f]"><BarChart3 size={22} /></div>
            <div>
              <h1 className="text-xl font-semibold">Candidate Dashboard</h1>
              <p className="text-sm text-slate-400">{userProfile.name} · interview performance across company rounds</p>
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={onRefresh} disabled={loading} className="rounded border border-emerald-800 px-3 py-2 text-sm text-emerald-100 disabled:opacity-50">Refresh</button>
            <button onClick={() => onStart("dsa")} className="inline-flex items-center gap-2 rounded bg-amber-300 px-4 py-2 font-semibold text-[#07120f]"><Code2 size={18} /> Start DSA</button>
            <button onClick={onLogout} className="inline-flex items-center gap-2 rounded border border-rose-500/50 px-3 py-2 text-sm text-rose-100"><LogOut size={16} /> Logout</button>
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-6 px-6 py-6">
        <div className="grid gap-4 lg:grid-cols-[1.2fr_.8fr]">
          <div className="rounded border border-amber-300/30 bg-[#10241f] p-5 shadow-2xl shadow-emerald-950/20">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="text-xs uppercase text-amber-200">DSA Interview Track</div>
                <h2 className="mt-2 text-2xl font-bold">Company-style coding rounds are ready.</h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-emerald-50/70">Pick a company, solve runnable DSA questions in the Monaco editor, run tests, submit code, and generate a report that appears here.</p>
              </div>
              <button onClick={() => onStart("dsa")} className="inline-flex items-center gap-2 rounded bg-amber-300 px-4 py-2 font-bold text-[#07120f]"><Play size={18} /> Practice DSA</button>
            </div>
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              <MiniStat label="DSA attempts" value={dsaReports.length} />
              <MiniStat label="DSA reports" value={completedDsa.length} />
              <MiniStat label="DSA average" value={`${dsaAverage}/100`} />
            </div>
          </div>
          <div className="rounded border border-rose-300/20 bg-[#171423] p-5">
            <h2 className="flex items-center gap-2 text-lg font-semibold"><Sparkles size={18} className="text-rose-200" /> Round shortcuts</h2>
            <div className="mt-4 grid gap-2">
              <button onClick={() => onStart("dsa")} className="rounded border border-amber-300/40 bg-amber-300/10 px-3 py-3 text-left text-sm text-amber-100">DSA + code execution</button>
              <button onClick={() => onStart("cs_fundamentals")} className="rounded border border-teal-300/30 bg-teal-300/10 px-3 py-3 text-left text-sm text-teal-100">CS fundamentals</button>
              <button onClick={() => onStart("project_behavioral")} className="rounded border border-rose-300/30 bg-rose-300/10 px-3 py-3 text-left text-sm text-rose-100">Project + behavioural</button>
            </div>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
          <DashboardMetric icon={<Briefcase size={18} />} label="Interviews" value={stats.total_interviews} />
          <DashboardMetric icon={<Shield size={18} />} label="Reports" value={stats.completed_interviews} />
          <DashboardMetric icon={<Target size={18} />} label="Companies" value={stats.companies_practiced} />
          <DashboardMetric icon={<TrendingUp size={18} />} label="Average" value={`${stats.average_score || 0}/100`} />
          <DashboardMetric icon={<BarChart3 size={18} />} label="Best" value={`${stats.best_score || 0}/100`} />
        </div>

        {latest ? (
          <div className="grid gap-4 lg:grid-cols-[1fr_.8fr]">
            <div className="rounded border border-slate-800 bg-slate-900 p-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <div className="text-xs uppercase text-cyan-300">Latest interview</div>
                  <h2 className="mt-1 text-xl font-semibold">{latest.target_company || "General"} · {prettyRound(latest.round_type)}</h2>
                </div>
                <ScoreBadge score={latest.overall_score} />
              </div>
              <p className="min-h-12 text-sm leading-6 text-slate-300">{latest.summary || (latest.has_report ? "Report generated." : "Interview is in progress or has not produced enough report evidence yet.")}</p>
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <MiniStat label="Signal" value={latest.hiring_signal || "In progress"} />
                <MiniStat label="Round score" value={`${latest.round_score || 0}/100`} />
                <MiniStat label="Integrity" value={`${latest.integrity_score ?? 100}/100`} />
              </div>
              {latest.has_report && <button onClick={() => onOpenReport(latest.session_id)} disabled={isBusy} className="mt-4 rounded bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">Open full report</button>}
            </div>

            <div className="rounded border border-slate-800 bg-slate-900 p-5">
              <h2 className="mb-4 text-lg font-semibold">Company Performance</h2>
              <div className="space-y-3">
                {(companies.length ? companies.slice(0, 5) : [{ company: "No company data yet", completed_count: 0, interview_count: 0, average_score: 0 }]).map((company) => (
                  <div key={company.company} className="rounded border border-slate-800 bg-slate-950 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="font-medium text-slate-100">{company.company}</div>
                        <div className="text-xs text-slate-500">{company.completed_count}/{company.interview_count} reports complete</div>
                      </div>
                      <div className="text-right">
                        <div className="text-lg font-semibold text-cyan-300">{company.average_score || 0}</div>
                        <div className="text-xs text-slate-500">avg score</div>
                      </div>
                    </div>
                    <ProgressBar value={company.average_score || 0} />
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="rounded border border-slate-800 bg-slate-900 p-8">
            <div className="max-w-2xl">
              <div className="text-xs uppercase text-cyan-300">No interviews yet</div>
              <h2 className="mt-2 text-2xl font-semibold">Start a company-specific AI interview to build your dashboard.</h2>
              <p className="mt-3 text-sm leading-6 text-slate-400">Your completed rounds, scores, company trends, strengths, weak areas, and generated reports will appear here automatically.</p>
              <button onClick={onStart} className="mt-5 inline-flex items-center gap-2 rounded bg-cyan-400 px-4 py-2 font-semibold text-slate-950"><Play size={18} /> Start interview</button>
            </div>
          </div>
        )}

        <div className="rounded border border-slate-800 bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
            <h2 className="text-lg font-semibold">Interview Reports</h2>
            <div className="text-sm text-slate-500">{completed.length} completed</div>
          </div>
          <div className="divide-y divide-slate-800">
            {(interviews.length ? interviews : []).map((item) => (
              <div key={item.session_id} className="grid gap-4 p-5 lg:grid-cols-[1fr_auto]">
                <div>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span className="inline-flex items-center gap-1"><Calendar size={14} /> {formatDate(item.completed_at || item.created_at)}</span>
                    <span>{prettyRound(item.round_type)}</span>
                    {item.problem_title && <span>{item.problem_title}</span>}
                  </div>
                  <h3 className="mt-2 text-lg font-semibold">{item.target_company || "General"} · {item.job_role || "Software Engineer"}</h3>
                  <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">{item.summary || "No report generated yet. End the interview to produce a full analysis."}</p>
                  <DashboardHighlights title="Strengths" items={item.strengths} tone="emerald" />
                  <DashboardHighlights title="Focus areas" items={item.weak_areas} tone="amber" />
                </div>
                <div className="flex min-w-40 flex-col items-start gap-3 lg:items-end">
                  <ScoreBadge score={item.overall_score} />
                  <div className="text-sm text-slate-400">{item.hiring_signal || "In progress"}</div>
                  {item.has_report ? (
                    <button onClick={() => onOpenReport(item.session_id)} disabled={isBusy} className="rounded border border-cyan-600 bg-cyan-950 px-3 py-2 text-sm text-cyan-100 disabled:opacity-50">View report</button>
                  ) : (
                    <span className="rounded border border-slate-700 px-3 py-2 text-sm text-slate-500">In progress</span>
                  )}
                </div>
              </div>
            ))}
            {!interviews.length && <div className="p-5 text-sm text-slate-400">No interview history for this user yet.</div>}
          </div>
        </div>
      </section>
    </main>
  )
}

function DashboardMetric({ icon, label, value }) {
  return <div className="rounded border border-emerald-900/50 bg-[#0d1f1b] p-4">
    <div className="flex items-center gap-2 text-xs uppercase text-emerald-100/50">{icon}{label}</div>
    <div className="mt-3 text-2xl font-semibold text-amber-100">{value}</div>
  </div>
}

function MiniStat({ label, value }) {
  return <div className="rounded border border-white/10 bg-[#07120f] p-3">
    <div className="text-xs uppercase text-emerald-100/50">{label}</div>
    <div className="mt-1 text-sm font-semibold text-slate-100">{value}</div>
  </div>
}

function ScoreBadge({ score }) {
  const value = Math.round(Number(score) || 0)
  const tone = value >= 75 ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : value >= 55 ? "border-cyan-500/40 bg-cyan-500/10 text-cyan-300" : "border-amber-500/40 bg-amber-500/10 text-amber-300"
  return <div className={`rounded border px-3 py-2 text-right ${tone}`}>
    <div className="text-2xl font-semibold">{value}</div>
    <div className="text-xs opacity-80">score</div>
  </div>
}

function ProgressBar({ value }) {
  const width = Math.max(0, Math.min(100, Number(value) || 0))
  const color = width >= 75 ? "bg-emerald-400" : width >= 55 ? "bg-cyan-400" : "bg-amber-400"
  return <div className="mt-3 h-1.5 rounded bg-slate-800"><div className={`h-1.5 rounded ${color}`} style={{ width: `${width}%` }} /></div>
}

function DashboardHighlights({ title, items, tone }) {
  const visible = (items || []).filter(Boolean).slice(0, 2)
  if (!visible.length) return null
  const color = tone === "emerald" ? "text-emerald-300" : "text-amber-300"
  return <div className="mt-3">
    <div className={`mb-1 text-xs uppercase ${color}`}>{title}</div>
    <div className="grid gap-1">
      {visible.map((item, index) => <p key={`${title}-${index}`} className="text-xs leading-5 text-slate-400">{item}</p>)}
    </div>
  </div>
}

function formatDate(value) {
  if (!value) return "Not dated"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
}

function buildTopicInsights(reports) {
  const byTopic = {}
  reports.forEach((report) => {
    const topics = Array.isArray(report.topic_mastery) ? report.topic_mastery : []
    topics.forEach((topic) => {
      const name = String(topic.topic || topic.name || "").trim()
      if (!name) return
      const score = clampScore(topic.mastery ?? topic.score)
      byTopic[name] = byTopic[name] || { name, total: 0, count: 0 }
      byTopic[name].total += score
      byTopic[name].count += 1
    })
  })
  return Object.values(byTopic)
    .map((topic) => ({ ...topic, average: Math.round(topic.total / Math.max(1, topic.count)) }))
    .sort((a, b) => b.count - a.count || b.average - a.average || a.name.localeCompare(b.name))
}

function buildBehaviorInsights(reports) {
  const behavioralReports = reports.filter((report) => report.round_type === "project_behavioral")
  const byTrait = {}
  behavioralReports.forEach((report) => {
    const params = Array.isArray(report.parameter_scores) ? report.parameter_scores : []
    params.forEach((param) => {
      const name = String(param.name || "").trim()
      if (!name) return
      const score = clampScore(param.score)
      byTrait[name] = byTrait[name] || { name, total: 0, count: 0 }
      byTrait[name].total += score
      byTrait[name].count += 1
    })
  })
  return Object.values(byTrait)
    .map((trait) => ({ ...trait, average: Math.round(trait.total / Math.max(1, trait.count)) }))
    .sort((a, b) => a.average - b.average || b.count - a.count || a.name.localeCompare(b.name))
}

function buildParameterInsights(reports) {
  const byParameter = {}
  reports.forEach((report) => {
    const params = Array.isArray(report.parameter_scores) ? report.parameter_scores : []
    params.forEach((param) => {
      const name = String(param.name || "").trim()
      if (!name) return
      const score = clampScore(param.score)
      byParameter[name] = byParameter[name] || { name, total: 0, count: 0 }
      byParameter[name].total += score
      byParameter[name].count += 1
    })
  })
  return Object.values(byParameter)
    .map((param) => ({ ...param, average: Math.round(param.total / Math.max(1, param.count)) }))
    .sort((a, b) => b.count - a.count || b.average - a.average || a.name.localeCompare(b.name))
}

function clampScore(value) {
  const score = Number(value)
  if (!Number.isFinite(score)) return 0
  return Math.max(0, Math.min(100, Math.round(score)))
}

function Field({ label, children }) {
  return <label className="grid gap-2 text-sm text-slate-300"><span>{label}</span>{children}</label>
}

function Panel({ title, icon, children }) {
  return <div className="min-h-0 rounded border border-slate-800 bg-slate-900"><div className="flex items-center gap-2 border-b border-slate-800 px-3 py-2 text-sm font-semibold">{icon}{title}</div><div className="p-3">{children}</div></div>
}

function ProblemBlock({ title, items }) {
  if (!items.length) return null
  return <div><div className="mb-2 font-semibold text-slate-100">{title}</div><div className="grid gap-2">{items.map((item) => <pre key={item} className="whitespace-pre-wrap rounded bg-slate-950 p-3 text-xs leading-5 text-slate-300">{item}</pre>)}</div></div>
}

function RoundContext({ title, items }) {
  return <div className="space-y-4 p-5 text-sm text-slate-300"><div><div className="text-xs uppercase text-slate-500">Round context</div><h3 className="mt-1 text-lg font-semibold text-slate-100">{title}</h3></div><div className="grid gap-2">{items.filter(Boolean).map((item) => <div key={item} className="rounded bg-slate-950 p-3">{item}</div>)}</div></div>
}

function CsRoundPanel({ messages, lastAiMessage, session, form }) {
  const csMemory = session?.cs_fundamentals || {}
  const currentTopic = csMemory.current_topic || ""
  const topicsCovered = csMemory.topics_covered || []
  const weakTopics = csMemory.weak_topics || []
  const strongTopics = csMemory.strong_topics || []
  const history = messages.filter((m) => m.role !== "system").slice(0, -1)

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-800 p-5">
        <div className="mb-1 flex items-center gap-2 text-xs uppercase tracking-wider text-cyan-500">
          {currentTopic && <span className="rounded bg-cyan-900/50 px-2 py-0.5">{currentTopic}</span>}
          <span>Current question</span>
        </div>
        <div className="mt-2 rounded border border-cyan-700/60 bg-cyan-950/30 p-4 text-sm font-medium leading-7 text-cyan-50">
          {lastAiMessage || "Loading your first question\u2026"}
        </div>
      </div>

      {history.length > 0 && (
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4">
          <div className="mb-1 text-xs uppercase text-slate-500">Earlier in this interview</div>
          {history.map((m, i) => (
            <div key={i} className={`rounded p-2 text-xs leading-5 ${m.role === "interviewer" ? "border border-cyan-800/40 bg-cyan-950/25 text-cyan-100" : "bg-slate-800 text-slate-300"}`}>
              <span className="mr-1 font-semibold">{m.role === "interviewer" ? "Interviewer:" : "You:"}</span>
              {m.content.length > 260 ? `${m.content.slice(0, 260)}\u2026` : m.content}
            </div>
          ))}
        </div>
      )}

      <div className="border-t border-slate-800 p-4">
        <div className="grid gap-1 text-xs text-slate-400">
          <div>{session?.target_company || form.target_company ? `${session?.target_company || form.target_company} \u00b7 ` : ""}{form.job_role}</div>
          {topicsCovered.length > 0 && <div>Covered: {topicsCovered.join(" \u00b7 ")}</div>}
          {weakTopics.length > 0 && <div className="text-amber-400">Needs work: {weakTopics.join(", ")}</div>}
          {strongTopics.length > 0 && <div className="text-emerald-400">Strong: {strongTopics.join(", ")}</div>}
          {topicsCovered.length === 0 && <div>Topics: DBMS \u00b7 OOP \u00b7 OS \u00b7 Networks</div>}
          <div className="text-slate-500">Scratchpad notes are evaluated \u2014 nothing is executed.</div>
        </div>
      </div>
    </div>
  )
}

function InterviewWorkspace({ input, setInput, isBusy, sendMessage, toggleMic, autoVoice, voiceState, liveTranscript, lastAiMessage, isCsRound, scratchpad, setScratchpad, scratchpadMode, setScratchpadMode }) {
  return <div className={`grid h-full rounded border border-slate-800 bg-slate-900 ${isCsRound ? "grid-rows-[1fr_auto]" : "grid-rows-[auto_1fr_auto]"}`}>
    {!isCsRound && (
      <div className="border-b border-slate-800 px-4 py-3">
        <div className="text-sm text-slate-400">Current question</div>
        <div className="mt-2 rounded bg-slate-950 p-3 text-sm leading-6 text-cyan-50">{lastAiMessage || "The interviewer question will appear here."}</div>
      </div>
    )}
    <div className={`grid min-h-0 gap-3 p-4 ${isCsRound ? "lg:grid-cols-2" : "grid-cols-1"}`}>
      <div className="min-h-0 rounded border border-slate-800 bg-slate-950 p-3">
        <label className="grid h-full gap-2 text-sm text-slate-300">
          <span>Your answer</span>
          <textarea value={input} onChange={(e) => setInput(e.target.value)} placeholder="Answer the interviewer here, or use voice." className="min-h-0 flex-1 resize-none rounded border border-slate-700 bg-slate-900 p-3 text-sm outline-none focus:border-cyan-400" />
        </label>
      </div>
      {isCsRound && <div className="min-h-0 rounded border border-slate-800 bg-slate-950 p-3">
        <div className="mb-2 flex items-center justify-between gap-3">
          <label className="text-sm text-slate-300">Scratchpad</label>
          <select className="w-36 py-2 text-sm" value={scratchpadMode} onChange={(e) => setScratchpadMode(e.target.value)} aria-label="Scratchpad mode">
            <option value="text">Text</option>
            <option value="sql">SQL</option>
            <option value="pseudocode">Pseudocode</option>
            <option value="diagram">Diagram notes</option>
          </select>
        </div>
        <textarea value={scratchpad} onChange={(e) => setScratchpad(e.target.value)} placeholder="Optional whiteboard notes. Use it for SQL, pseudocode, diagrams, or examples when helpful." className="h-[calc(100%-44px)] w-full resize-none rounded border border-slate-700 bg-slate-900 p-3 font-mono text-sm outline-none focus:border-cyan-400" />
      </div>}
    </div>
    <div className="border-t border-slate-800 p-3">
      <div className="flex gap-2">
        <button onClick={() => sendMessage()} disabled={isBusy} className="flex-1 rounded bg-cyan-400 px-3 py-2 font-semibold text-slate-950 disabled:opacity-50">Send answer</button>
        <button onClick={toggleMic} className={`rounded border px-3 py-2 ${autoVoice || voiceState === "listening" ? "border-red-400 text-red-200" : "border-slate-600"}`} title="Toggle microphone">{autoVoice || voiceState === "listening" ? <Square size={18} /> : <Mic size={18} />}</button>
      </div>
      {liveTranscript && <div className="mt-2 rounded bg-slate-950 p-2 text-xs text-cyan-100">Hearing: {liveTranscript}</div>}
    </div>
  </div>
}

function Feedback({ report, onRestart, onBack }) {
  const breakdown = report.round_breakdown || {}
  const roundItems = roundBreakdownItems(breakdown)
  const integrity = report.integrity || {}

  return <main className="min-h-screen bg-slate-950 p-6 text-slate-100">
    <section className="mx-auto max-w-6xl rounded border border-slate-800 bg-slate-900 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <button onClick={onBack} className="mb-4 inline-flex items-center gap-2 rounded border border-slate-700 px-3 py-2 text-sm text-slate-200"><ArrowLeft size={16} /> Back to dashboard</button>
          <div className="text-sm uppercase text-cyan-300">{prettyRound(report.round_type)} Report</div>
          <h1 className="mt-1 text-2xl font-semibold">{report.hiring_signal}</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">{report.summary}</p>
        </div>
        <div className="text-right">
          <div className="text-5xl font-bold text-cyan-300">{report.overall_score}</div>
          <div className="text-sm text-slate-400">overall score</div>
        </div>
      </div>

      {report.parameter_scores?.length > 0 ? (
        <div className="mt-5 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {report.parameter_scores.map((p) => <ParameterCard key={p.name} param={p} />)}
        </div>
      ) : (
        <div className="mt-5 grid gap-4 md:grid-cols-5">
          {Object.entries(report.scores || {}).map(([k, v]) => <ScoreCard key={k} label={k} value={v} suffix="/4" />)}
        </div>
      )}

      {report.skill_gap && (
        <div className="mt-5 rounded border border-amber-500/30 bg-amber-500/5 p-4">
          <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-amber-300">Where You're Lagging</h2>
          <p className="text-sm leading-6 text-slate-300">{report.skill_gap}</p>
        </div>
      )}

      {report.topic_mastery?.length > 0 && (
        <div className="mt-5">
          <h2 className="mb-3 font-semibold">Topics Asked &amp; Mastery</h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {report.topic_mastery.map((t) => <ParameterCard key={t.topic} param={{ name: t.topic, score: t.mastery, note: t.note }} />)}
          </div>
        </div>
      )}

      <div className="mt-5 grid gap-4 md:grid-cols-3">
        <ScoreCard label="Round" value={breakdown.round_score || 0} suffix="/100" />
        <ScoreCard label="Integrity" value={integrity.score ?? 100} suffix="/100" />
        <ScoreCard label="Evidence" value={(breakdown.evidence || []).length} suffix=" items" />
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[1.15fr_.85fr]">
        <div className="space-y-5">
          <ReportPanel title="Round Breakdown" items={roundItems} />
          {breakdown.evidence?.length > 0 && <EvidencePanel evidence={breakdown.evidence} />}
        </div>
        <div className="space-y-5">
          <ReportPanel title="Strengths" items={report.strengths || []} />
          <ReportPanel title="Weak Areas" items={report.weak_areas || []} />
          <ReportPanel title="Suggestions to Work On" items={report.study_plan || []} />
          <ReportPanel title="Integrity" items={[`${integrity.score ?? 100}/100 integrity score`, `${integrity.violations?.length || 0} proctoring events`, `tab switches: ${integrity.focus_loss || 0}`, `paste events: ${integrity.paste_events || 0}`]} />
        </div>
      </div>

      <button onClick={onRestart} className="mt-6 rounded bg-cyan-400 px-4 py-2 font-semibold text-slate-950">Start DSA interview</button>
    </section>
  </main>
}

function ScoreCard({ label, value, suffix }) {
  return <div className="rounded bg-slate-950 p-3"><div className="text-xs uppercase text-slate-500">{label.replaceAll("_", " ")}</div><div className="mt-1 text-xl font-semibold">{value}{suffix}</div></div>
}

function ParameterCard({ param }) {
  const score = Math.max(0, Math.min(100, Number(param.score) || 0))
  const tone = score >= 75 ? "text-emerald-300" : score >= 50 ? "text-cyan-300" : "text-amber-300"
  const bar = score >= 75 ? "bg-emerald-400" : score >= 50 ? "bg-cyan-400" : "bg-amber-400"
  return <div className="rounded border border-slate-800 bg-slate-950 p-4">
    <div className="flex items-baseline justify-between">
      <div className="text-sm font-medium text-slate-200">{param.name}</div>
      <div className={`text-xl font-semibold ${tone}`}>{score}<span className="text-xs text-slate-500">/100</span></div>
    </div>
    <div className="mt-2 h-1.5 w-full rounded bg-slate-800"><div className={`h-1.5 rounded ${bar}`} style={{ width: `${score}%` }} /></div>
    {param.note && <p className="mt-2 text-xs leading-5 text-slate-400">{param.note}</p>}
  </div>
}

function ReportPanel({ title, items }) {
  const visible = (items || []).filter(Boolean)
  return <div className="rounded border border-slate-800 bg-slate-950 p-4"><h2 className="mb-3 font-semibold">{title}</h2><div className="space-y-2">{(visible.length ? visible : ["No evidence recorded for this section."]).map((x, i) => <p key={`${x}-${i}`} className="rounded bg-slate-900 p-3 text-sm leading-6 text-slate-300">{x}</p>)}</div></div>
}

function EvidencePanel({ evidence }) {
  return <div className="rounded border border-slate-800 bg-slate-950 p-4"><h2 className="mb-3 font-semibold">Evidence Used</h2><div className="space-y-2">{evidence.map((item, i) => <pre key={i} className="max-h-44 overflow-y-auto whitespace-pre-wrap rounded bg-slate-900 p-3 text-xs leading-5 text-slate-300">{formatEvidence(item)}</pre>)}</div></div>
}

function roundBreakdownItems(section) {
  if (!section?.type) return []
  if (section.type === "dsa") return [
    section.problem?.title && `Problem: ${section.problem.title} (${section.problem.difficulty || "difficulty unknown"})`,
    section.submission?.total_testcases ? `Tests: ${section.submission.passed_testcases}/${section.submission.total_testcases} passed in ${section.submission.language || "selected language"}` : "No code submission evidence was recorded.",
    section.problem?.topics?.length && `Topics: ${section.problem.topics.slice(0, 6).join(", ")}`,
  ].filter(Boolean)
  if (section.type === "project_behavioral") return [
    section.company_profile && `Company profile: ${section.company_profile}`,
    section.company_style && `Company style: ${section.company_style}`,
    section.resume_focus?.selected_project && `Project focus: ${section.resume_focus.selected_project}`,
    section.jd_signals?.skills?.length && `JD signals: ${section.jd_signals.skills.join(", ")}`,
    `Turns evaluated: ${section.turn_count || 0}`,
    ...(section.latest_flags || []),
  ].filter(Boolean)
  if (section.type === "cs_fundamentals") return [
    section.current_topic && `Current topic: ${section.current_topic}`,
    section.topic_plan?.length && `Topic plan: ${section.topic_plan.join(", ")}`,
    section.topics_covered?.length && `Topics covered: ${section.topics_covered.join(", ")}`,
    section.strong_topics?.length && `Strong topics: ${section.strong_topics.join(", ")}`,
    section.weak_topics?.length && `Weak topics: ${section.weak_topics.join(", ")}`,
    section.scratchpad_observations?.length && `Scratchpad turns: ${section.scratchpad_observations.length}`,
    ...(section.latest_flags || []),
  ].filter(Boolean)
  return []
}

function formatEvidence(item) {
  if (item.role && item.content) return `${item.role}: ${item.content}`
  if (item.topic) return `${item.topic} | ${item.question_type || "question"}\nAnswer: ${item.answer_excerpt || ""}\nScratchpad: ${item.scratchpad_excerpt || ""}`
  if (item.phase) return `${item.phase}\nAnswer: ${item.answer_text || item.answer_excerpt || ""}\nFlags: ${(item.flags || []).join("; ")}`
  return JSON.stringify(item, null, 2)
}

function prettyRound(roundType) {
  if (roundType === "project_behavioral") return "Project + Behavioural"
  if (roundType === "cs_fundamentals") return "CS Fundamentals"
  return "DSA"
}

async function postJson(path, body) {
  const res = await apiFetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
  if (!res.ok) {
    const error = new Error(await res.text())
    error.status = res.status
    throw error
  }
  return res.json()
}

async function apiFetch(path, options = {}) {
  let lastError = null
  for (const base of API_BASES) {
    try {
      const headers = new Headers(options.headers || {})
      if (authToken() && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${authToken()}`)
      const res = await fetch(`${base}${path}`, { ...options, headers })
      if (!res.ok && base === "" && [405, 501].includes(res.status)) {
        lastError = new Error(`${res.status} from local static server for ${path}`)
        continue
      }
      // Application-level 404 (e.g. "Session not found", "Problem not found"):
      // the body is a JSON {"detail":"..."} — return immediately, don't retry other bases.
      if (res.status === 404) {
        const clone = res.clone()
        try {
          const body = await clone.json()
          if (body && body.detail) return res   // real app error, surface it
        } catch {}
        // No JSON detail → might be wrong server, try next base (unless last)
        if (base !== API_BASES[API_BASES.length - 1]) {
          lastError = new Error(`404 from ${base}${path}`)
          continue
        }
      }
      return res
    } catch (err) {
      lastError = err
    }
  }
  throw lastError || new Error("Backend is not reachable.")
}

function getStarterCode(problem, selectedLanguage) {
  if (!problem?.starter_code) return defaultCode
  if (typeof problem.starter_code === "string") return problem.starter_code
  return problem.starter_code[selectedLanguage] || problem.starter_code.python || defaultCode
}

function monacoLanguage(selectedLanguage) {
  return { cpp: "cpp", c: "c", java: "java", python: "python" }[selectedLanguage] || "plaintext"
}

function formatTimer(seconds) {
  const total = Math.max(0, Number(seconds) || 0)
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${mins}:${String(secs).padStart(2, "0")}`
}

function friendlyError(err) {
  const text = err?.message || String(err || "")
  if (text.includes("Failed to fetch")) return "API is not reachable after trying the /api proxy and direct local backend ports. Hard refresh the page and confirm /api/health opens."
  try {
    const parsed = JSON.parse(text)
    if (typeof parsed.detail === "string") return parsed.detail
    return parsed.detail?.message || text
  } catch {
    return text.slice(0, 220)
  }
}

function parseErrorDetail(err) {
  try {
    return JSON.parse(err?.message || "{}")?.detail || null
  } catch {
    return null
  }
}

function isLikelyEcho(candidateText, aiText) {
  const candidate = normalizeSpeech(candidateText)
  const ai = normalizeSpeech(aiText)
  if (!candidate || !ai) return false
  // Very short fragments that appear at the start of AI text are almost always echo
  if (candidate.length < 24) {
    return ai.startsWith(candidate) || ai.includes(candidate)
  }
  if (ai.includes(candidate) || candidate.includes(ai.slice(0, Math.min(ai.length, 120)))) return true
  const candidateWords = candidate.split(" ").filter((word) => word.length > 3)
  const aiWords = new Set(ai.split(" ").filter((word) => word.length > 3))
  if (candidateWords.length < 4) return false
  let overlap = 0
  candidateWords.forEach((word) => {
    if (aiWords.has(word)) overlap += 1
  })
  // If >60% overlap, it's echo. Lowered from 72% to catch partial echoes
  // where AEC suppressed some words but not others
  return overlap / candidateWords.length > 0.6
}

function voicePauseMs(roundType) {
  if (roundType === "project_behavioral" || roundType === "combined") return 6500
  if (roundType === "cs_fundamentals") return 5000
  return 3500
}

function normalizeSpeech(text) {
  return (text || "").toLowerCase().replace(/[^a-z0-9+ ]/g, " ").replace(/\s+/g, " ").trim()
}
