import { useEffect, useMemo, useRef, useState } from "react"
import Editor from "@monaco-editor/react"
import { Canvas, useFrame } from "@react-three/fiber"
import { motion } from "framer-motion"
import OpportunitiesPage from "./pages/OpportunitiesPage"
import { AlertTriangle, ArrowLeft, ArrowRight, BarChart3, Brain, Briefcase, Calendar, Camera, ChevronRight, Code2, FileText, LogIn, LogOut, Mic, MoreHorizontal, Play, Search, Send, Shield, ShieldCheck, Sparkles, Square, Target, TrendingUp, Trophy, Upload, Users, Lock, X, Zap } from "lucide-react"

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
    } catch {
      return { authenticated: false, user_id: "local-user", name: "Candidate", email: "" }
    }
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
  const [form, setForm] = useState({ job_role: "Software Engineer", experience_level: "fresher", target_company: "", job_description: "", round_type: "dsa", difficulty: "medium", timer_minutes: 45 })
  const [resume, setResume] = useState(null)
  const [resumeReviewFile, setResumeReviewFile] = useState(null)
  const [resumeReview, setResumeReview] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [scratchpad, setScratchpad] = useState("")
  const [scratchpadMode, setScratchpadMode] = useState("notes")
  const [language, setLanguage] = useState("python")
  const [code, setCode] = useState(defaultCode)
  const [codeResult, setCodeResult] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [warning, setWarning] = useState("")
  const [error, setError] = useState("")
  const [chatOpen, setChatOpen] = useState(false)
  const [cameraPos, setCameraPos] = useState({ x: 24, y: 88 })
  const [voiceState, setVoiceState] = useState("idle")
  const [autoVoice, setAutoVoice] = useState(false)
  const [liveTranscript, setLiveTranscript] = useState("")
  const [companies, setCompanies] = useState([])
  const [companyDirectory, setCompanyDirectory] = useState([])
  const [companyRounds, setCompanyRounds] = useState({ company: "", resolved: false, rounds: [] })
  const [companyLoading, setCompanyLoading] = useState(false)
  const [isBusy, setIsBusy] = useState(false)
  const [dsaProgress, setDsaProgress] = useState(null)
  const [llmOffline, setLlmOffline] = useState(false)
  const [llmConfigured, setLlmConfigured] = useState(true)
  const videoRef = useRef(null)
  const recognitionRef = useRef(null)
  const autoVoiceRef = useRef(false)
  const liveTranscriptRef = useRef("")
  const speakingRef = useRef(false)
  const ttsTimeoutRef = useRef(null)
  const voiceRestartTimerRef = useRef(null)
  const intentionalStopRef = useRef(false)
  const lastAiSpokenRef = useRef("")
  const ttsEndedAtRef = useRef(0)       // timestamp when TTS audio finished playing
  const speechTokenRef = useRef(0)
  const dragRef = useRef(null)
  const editorTelemetryRef = useRef({ lastChangeAt: Date.now(), edits: 0, pasteEvents: 0, largePastes: 0, deletions: 0, idleGaps: 0, maxLines: 0 })
  const codeRef = useRef(defaultCode)
  const languageRef = useRef("python")
  const currentAudioRef = useRef(null)   // tracks active ElevenLabs Audio element
  const flowTokenRef = useRef(0)

  const currentProblem = session?.problem
  const activeRound = session?.round_type || form.round_type
  const isDsaRound = activeRound === "dsa"
  const isCsRound = activeRound === "cs_fundamentals"
  const isProjectRound = !isDsaRound && !isCsRound
  const roundTitle = isDsaRound ? "DSA round" : isCsRound ? "CS Fundamentals Interview" : "Project and Behavioural Round"
  const availableSetupRounds = companyRounds.resolved ? companyRounds.rounds || [] : []
  const selectedSetupRound = availableSetupRounds.find((round) => round.id === form.round_type)
  const canStartConfiguredInterview = Boolean(companyRounds.resolved && selectedSetupRound && !companyLoading && form.target_company.trim())
  const lastAiMessage = useMemo(() => [...messages].reverse().find((m) => m.role === "interviewer")?.content ?? "", [messages])

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
      // eslint-disable-next-line react-hooks/set-state-in-effect
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
    const authError = params.get("auth_error")
    if (authError) {
      window.history.replaceState({}, "", window.location.pathname)
      setError("That sign-in link expired or was already used. Please click Sign in again.")
      window.setTimeout(() => setError(""), 6000)
      if (authToken()) loadAuthenticatedProfile()
      return
    }
    if (token) {
      window.localStorage.setItem("codevoir_auth_token", token)
      window.history.replaceState({}, "", window.location.pathname)
      loadAuthenticatedProfile(token)
      return
    }
    if (authToken()) loadAuthenticatedProfile()
  }, [])

  useEffect(() => {
    if (!form.target_company || form.round_type !== "dsa") return
    apiFetch(`/api/interview/company-config?company=${encodeURIComponent(form.target_company)}&round_type=dsa`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => {
        const minutes = data?.config?.minutes
        if (minutes && minutes > 10) setForm((prev) => ({ ...prev, timer_minutes: minutes }))
      })
      .catch(() => {})
  }, [form.target_company, form.round_type])

  useEffect(() => {
    if (!currentProblem) return
    const nextCode = getStarterCode(currentProblem, language)
    // eslint-disable-next-line react-hooks/set-state-in-effect
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

  // Poll LLM health across all rounds so the candidate sees an accurate
  // "AI online/offline" status (and it recovers automatically when the LLM is back).
  useEffect(() => {
    if (!session?.session_id) return undefined
    let stopped = false
    const check = () => {
      apiFetch("/api/health/llm")
        .then((res) => (res.ok ? res.json() : null))
        .then((payload) => {
          if (!payload) return
          if (typeof payload.configured === "boolean") setLlmConfigured(payload.configured)
          if (typeof payload.offline === "boolean") setLlmOffline(payload.offline)
        })
        .catch(() => {})
    }
    check()
    const timer = window.setInterval(() => { if (!stopped) check() }, 15000)
    return () => { stopped = true; window.clearInterval(timer) }
  }, [session?.session_id])

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
    const requestToken = flowTokenRef.current
    setIsBusy(true)
    setError("")
    try {
      const created = await postJson("/api/session/start", { ...form, user_id: userProfile.user_id })
      if (requestToken !== flowTokenRef.current) return
      if (resume) {
        const fd = new FormData()
        fd.append("session_id", created.session_id)
        fd.append("file", resume)
        await apiFetch("/api/resume/upload", { method: "POST", body: fd })
        if (requestToken !== flowTokenRef.current) return
      }
      setSession(created)
      setDsaProgress(created.dsa_progress || null)
      setMessages([{ role: "interviewer", content: created.ai_text }])
      setCode(getStarterCode(created.problem, language))
      setScreen("interview")
      speak(created.ai_text)
    } catch (err) {
      if (requestToken !== flowTokenRef.current) return
      setError(err.message || "Could not start interview. Check that the backend is running.")
    } finally {
      if (requestToken === flowTokenRef.current) setIsBusy(false)
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
      return
    }
    setInput("")
    setLiveTranscript("")
    setMessages((prev) => [...prev, { role: "candidate", content: clean }])
    const requestToken = flowTokenRef.current
    setIsBusy(true)
    // Show "thinking" indicator while backend retries LLM
    setMessages((prev) => [...prev, { role: "thinking", content: "" }])
    try {
      const payload = {
        session_id: session.session_id,
        user_text: clean,
        behavioral_metrics: behavioralMetrics,
        code_context: currentCodeContext("message"),
        scratchpad: scratchpad.trim() ? { content: scratchpad.trim(), mode: scratchpadMode } : {},
      }
      const reply = await postJson("/api/interview/message", payload)
      if (requestToken !== flowTokenRef.current) return
      // Remove thinking indicator
      setMessages((prev) => prev.filter((m) => m.role !== "thinking"))
      if (typeof reply.llm_offline === "boolean") setLlmOffline(reply.llm_offline)
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
      if (requestToken !== flowTokenRef.current) return
      setMessages((prev) => prev.filter((m) => m.role !== "thinking"))
      const detail = friendlyError(err)
      setError(detail)
      setMessages((prev) => [...prev, { role: "interviewer", content: `I hit a connection issue while replying: ${detail}. Please try again or use manual text for this turn.` }])
      window.setTimeout(() => setError(""), 6000)
    } finally {
      if (requestToken === flowTokenRef.current) setIsBusy(false)
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
    if (!session || isBusy) return
    const sessionId = session.session_id
    const requestToken = ++flowTokenRef.current
    stopVoiceCapture()
    _stopCurrentSpeech()
    setError("")
    setIsBusy(true)
    try {
      const res = await apiFetch(`/api/feedback/${sessionId}`)
      if (!res.ok) throw new Error(await res.text())
      const report = await res.json()
      if (requestToken !== flowTokenRef.current) return
      setFeedback(report)
      setSelectedReport(report)
      loadDashboard().catch(() => {})
      setScreen("feedback")
    } catch (err) {
      if (requestToken !== flowTokenRef.current) return
      setError(friendlyError(err))
      window.setTimeout(() => setError(""), 7000)
    } finally {
      if (requestToken === flowTokenRef.current) setIsBusy(false)
    }
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
    const requestToken = ++flowTokenRef.current
    setIsBusy(true)
    setError("")
    setFeedback(null)
    try {
      setScreen("feedback")
      const res = await apiFetch(`/api/feedback/${sessionId}`)
      if (!res.ok) throw new Error(await res.text())
      const report = await res.json()
      if (requestToken !== flowTokenRef.current) return
      setSelectedReport(report)
      setFeedback(report)
    } catch (err) {
      if (requestToken !== flowTokenRef.current) return
      setScreen("dashboard")
      setError(friendlyError(err))
      window.setTimeout(() => setError(""), 6000)
    } finally {
      if (requestToken === flowTokenRef.current) setIsBusy(false)
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
    flowTokenRef.current += 1
    stopVoiceCapture()
    _stopCurrentSpeech()
    setSession(null)
    setMessages([])
    setInput("")
    setScratchpad("")
    setCodeResult(null)
    setDsaProgress(null)
    setFeedback(null)
    setSelectedReport(null)
    setError("")
    setWarning("")
    setChatOpen(false)
    setIsBusy(false)
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
    speechTokenRef.current += 1
    if (currentAudioRef.current) {
      try { currentAudioRef.current.pause() } catch {
        currentAudioRef.current = null
      }
      currentAudioRef.current = null
    }
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }
    if (ttsTimeoutRef.current) { window.clearTimeout(ttsTimeoutRef.current); ttsTimeoutRef.current = null }
    speakingRef.current = false
    ttsEndedAtRef.current = Date.now()
    setVoiceState(recognitionRef.current ? "listening" : "user_turn")
  }

  function speak(text) {
    if (!text) return
    _stopCurrentSpeech()
    const speechToken = ++speechTokenRef.current
    lastAiSpokenRef.current = text
    speakingRef.current = true
    setVoiceState("ai_speaking")

    const finishSpeaking = () => {
      if (speechToken !== speechTokenRef.current) return
      if (!speakingRef.current) return
      speakingRef.current = false
      ttsEndedAtRef.current = Date.now()
      currentAudioRef.current = null
      // Push-to-talk: never auto-start the mic. The candidate presses the mic when
      // ready to answer — this is what removes the lag after the AI stops speaking.
      setVoiceState(recognitionRef.current ? "listening" : "user_turn")
    }

    if (EL_API_KEY) {
      _elevenLabsTTS(text, (audio) => { currentAudioRef.current = audio })
        .then(finishSpeaking)
        .catch((err) => {
          if (speechToken !== speechTokenRef.current) return
          console.warn("ElevenLabs TTS failed, using browser voice:", err)
          currentAudioRef.current = null
          _speakBrowserTTS(text, finishSpeaking, speechToken)
        })
    } else {
      _speakBrowserTTS(text, finishSpeaking, speechToken)
    }
  }

  function _speakBrowserTTS(text, onDone, speechToken) {
    if (!("speechSynthesis" in window)) { onDone(); return }
    const chunks = chunkSpeechText(text)
    if (!chunks.length) { onDone(); return }
    let index = 0
    let finished = false
    let utteranceId = 0

    const complete = () => {
      if (finished) return
      finished = true
      if (ttsTimeoutRef.current) {
        window.clearTimeout(ttsTimeoutRef.current)
        ttsTimeoutRef.current = null
      }
      onDone()
    }

    const speakNext = () => {
      if (speechToken !== speechTokenRef.current) return
      if (finished) return
      if (ttsTimeoutRef.current) {
        window.clearTimeout(ttsTimeoutRef.current)
        ttsTimeoutRef.current = null
      }
      const chunk = chunks[index]
      if (!chunk) { complete(); return }
      const currentId = ++utteranceId
      const utterance = new SpeechSynthesisUtterance(chunk)
      utterance.rate = 1.02
      utterance.onend = () => {
        if (speechToken !== speechTokenRef.current) return
        if (currentId !== utteranceId) return
        index += 1
        speakNext()
      }
      utterance.onerror = () => {
        if (speechToken !== speechTokenRef.current) return
        if (currentId === utteranceId) complete()
      }
      window.speechSynthesis.resume?.()
      window.speechSynthesis.speak(utterance)
      // Chrome can silently drop longer interviewer turns; advance instead of hanging.
      ttsTimeoutRef.current = window.setTimeout(() => {
        if (speechToken !== speechTokenRef.current) return
        if (currentId !== utteranceId) return
        utteranceId += 1
        window.speechSynthesis.cancel()
        index += 1
        speakNext()
      }, Math.min(16000, chunk.length * 75 + 900))
    }

    speakNext()
  }

  // ── Push-to-talk voice capture ───────────────────────────────────────────
  // The candidate explicitly presses the mic to start talking and presses again
  // to stop+send. There are NO silence timers, NO auto-restart cycle, and NO
  // TTS↔mic coordination — so there is no lag after the AI stops, and natural
  // pauses no longer fragment or drop speech.
  function startPushToTalk() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      setWarning("Voice needs Chrome. Type your answer in the box instead.")
      window.setTimeout(() => setWarning(""), 5000)
      return
    }
    if (recognitionRef.current) return
    // Barge-in: pressing the mic immediately silences the AI so you can talk.
    _stopCurrentSpeech()
    speakingRef.current = false
    const recognition = new SpeechRecognition()
    recognition.lang = "en-US"
    recognition.interimResults = true
    recognition.continuous = true
    recognition.maxAlternatives = 1
    let finalText = ""
    let latestHeardText = ""
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
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        autoVoiceRef.current = false
        setAutoVoice(false)
        setWarning("Microphone permission is blocked. Allow mic access, then press the mic again.")
        window.setTimeout(() => setWarning(""), 6000)
      } else if (event.error === "audio-capture") {
        autoVoiceRef.current = false
        setAutoVoice(false)
        setWarning("No microphone detected. Check your input device, then press the mic again.")
        window.setTimeout(() => setWarning(""), 6000)
      }
      // "no-speech" / "aborted" / "network" are recoverable — onend restarts while active.
    }
    recognition.onend = () => {
      // Chrome ends recognition on a long pause or ~60s. While the candidate is
      // still holding the mic, restart immediately (no delay) so capture is seamless.
      if (autoVoiceRef.current) {
        try { recognition.start(); return } catch { /* fall through to cleanup */ }
      }
      recognitionRef.current = null
      setVoiceState("user_turn")
    }
    recognitionRef.current = recognition
    autoVoiceRef.current = true
    setAutoVoice(true)
    setLiveTranscript("")
    try {
      recognition.start()
    } catch {
      recognitionRef.current = null
      autoVoiceRef.current = false
      setAutoVoice(false)
    }
  }

  function stopPushToTalkAndSend() {
    const clean = stopVoiceCapture()
    if (clean && session && !isBusy) {
      sendMessage(clean, { voice_turn: true })
    }
  }

  function stopVoiceCapture() {
    autoVoiceRef.current = false
    setAutoVoice(false)
    const recognition = recognitionRef.current
    recognitionRef.current = null
    if (recognition) {
      recognition.onend = null   // prevent the auto-restart on stop
      try { recognition.stop() } catch {
        setVoiceState("user_turn")
      }
    }
    setVoiceState("user_turn")
    const clean = liveTranscriptRef.current.trim()
    setLiveTranscript("")
    return clean
  }

  function sendCapturedTranscript() {
    const clean = liveTranscriptRef.current.trim()
    if (clean && session && !isBusy) {
      sendMessage(clean, { voice_turn: true, sent_from_transcript: true })
    }
  }

  function toggleMic() {
    if (autoVoiceRef.current || recognitionRef.current || voiceState === "listening") {
      stopPushToTalkAndSend()
    } else {
      startPushToTalk()
    }
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
    return <Dashboard
      userProfile={userProfile}
      dashboard={dashboard}
      loading={dashboardLoading}
      error={error}
      onStart={startRound}
      onRefresh={loadDashboard}
      onOpenReport={openReport}
      onLogout={logout}
      onOpportunities={() => setScreen("opportunities")}
      onDocsAssistant={() => alert("Documentation Assistant is coming soon!")}
      onReportsPage={() => setScreen("reports")}
      isBusy={isBusy}
    />
  }

  if (screen === "reports") {
    return <ReportsSearchPage dashboard={dashboard} onBack={() => setScreen("dashboard")} onOpenReport={openReport} isBusy={isBusy} />
  }

  if (screen === "feedback" && feedback) {
    const r = selectedReport || feedback
    const rt = r.round_type || "dsa"
    if (rt === "dsa") return <DSAFeedback report={r} onRestart={() => startRound("dsa")} onBack={() => setScreen("dashboard")} />
    if (rt === "cs_fundamentals") return <CSFeedback report={r} onRestart={() => startRound("cs_fundamentals")} onBack={() => setScreen("dashboard")} />
    if (rt === "project_behavioral") return <PBFeedback report={r} onRestart={() => startRound("project_behavioral")} onBack={() => setScreen("dashboard")} />
    return <Feedback report={r} onRestart={() => startRound(rt)} onBack={() => setScreen("dashboard")} />
  }

  if (screen === "opportunities") {
    return <OpportunitiesPage onBack={() => setScreen("dashboard")} />
  }

  if (screen === "setup") {
    return (
      <main className="dashboard-shell min-h-screen text-slate-100 codevoir-dashboard-page">
        <BackgroundCanvas />
        {error && <div className="fixed left-1/2 top-4 z-30 max-w-xl -translate-x-1/2 rounded border border-red-400 bg-red-950 px-4 py-3 text-sm text-red-100">{error}</div>}
        <header className="relative z-10 border-b border-white/10 backdrop-blur-xl">
          <div className="w-full flex items-center justify-between px-6 py-3">
            <div className="flex items-center gap-3">
              <button onClick={() => setScreen("dashboard")} className="setup-back-btn transition-all shadow-sm" title="Back to dashboard"><ArrowLeft size={20} /></button>
              <div>
                <h1 className="font-display text-xl font-semibold tracking-normal text-white">CodeVoir Interview Lab</h1>
              </div>
            </div>
          </div>
        </header>

        <section className="relative z-10 mx-auto grid min-h-[calc(100vh-100px)] w-full max-w-6xl xl:max-w-7xl content-center gap-6 px-4 py-6">
          <div className="interview-setup-card grid lg:grid-cols-[1.15fr_0.85fr] gap-8 items-center">
            <div>
              <div className="interview-setup-header">
                <div>
                  <h2 className="font-display text-3xl font-semibold tracking-normal text-white">Start live interview</h2>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">Select a company and CodeVoir will show only the interview rounds backed by available data.</p>
                </div>
              </div>
              <div className="mt-6 grid gap-5 md:grid-cols-2">
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
                {form.round_type === "dsa" && <Field label="Difficulty"><select value={form.difficulty} onChange={(e) => setForm({ ...form, difficulty: e.target.value })}><option>easy</option><option>medium</option><option>hard</option></select></Field>}
                <Field label="Timer minutes"><input type="number" min="10" max="90" value={form.timer_minutes} onChange={(e) => setForm({ ...form, timer_minutes: Number(e.target.value) })} /></Field>
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
              <button className="mt-6 inline-flex h-12 items-center gap-2 rounded-full bg-[#0a66c2] px-6 font-bold text-white shadow-[0_4px_14px_rgba(10,102,194,0.15)] transition hover:scale-[1.02] hover:bg-[#004182] disabled:opacity-50" onClick={startSession} disabled={isBusy || !canStartConfiguredInterview}>
                <Play size={18} /> Start interview
              </button>
            </div>
            <div className="hidden lg:flex flex-col items-center justify-center p-4">
              <SetupCarousel />
              <p className="text-xs text-slate-500 font-semibold tracking-wider uppercase mt-4 text-center">CodeVoir Interview Engine</p>
            </div>
          </div>

        </section>
      </main>
    )
  }

  return (
    <main className="dashboard-shell grid h-screen grid-rows-[auto_1fr] text-slate-100 codevoir-dashboard-page">
      <BackgroundCanvas />
      {error && <div className="fixed left-1/2 top-4 z-50 max-w-xl -translate-x-1/2 rounded border border-red-400 bg-red-950 px-4 py-3 text-sm text-red-100">{error}</div>}
      <header className="relative z-10 flex items-center justify-between border-b border-slate-800/80 bg-slate-950/70 px-4 py-3 backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <button onClick={() => setScreen("dashboard")} className="setup-back-btn transition-all shadow-sm" title="Back to dashboard"><ArrowLeft size={18} /></button>
          <div>
            <div className="font-semibold text-white">{roundTitle}</div>
            <div className="text-xs text-slate-200">{voiceState.replace("_", " ")}{liveTranscript ? ` - "${liveTranscript.slice(0, 70)}"` : ""}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${!llmConfigured ? "border-amber-600 bg-amber-950 text-amber-300" : llmOffline ? "border-red-500 bg-red-950 text-red-300" : "border-emerald-700 bg-emerald-950 text-emerald-300"}`} title={!llmConfigured ? "No API key set — add GROQ_API_KEY or GEMINI_API_KEY to .env" : llmOffline ? "The AI model can't be reached right now — replies are limited" : "AI model is responding normally"}>
            <span className={`h-2 w-2 rounded-full ${!llmConfigured ? "bg-amber-400" : llmOffline ? "bg-red-400" : "bg-emerald-400"}`} />
            {!llmConfigured ? "AI not configured" : llmOffline ? "AI offline" : "AI online"}
          </span>
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
          <button onClick={finishInterview} className="rounded border border-slate-600 px-3 py-2 text-sm">End & report</button>
        </div>
      </header>

      {warning && <div className="fixed left-1/2 top-20 z-20 flex -translate-x-1/2 items-center gap-2 rounded bg-amber-300 px-4 py-2 font-medium text-slate-950"><AlertTriangle size={18} /> {warning}</div>}

      {!llmConfigured && <div className="fixed left-1/2 top-32 z-20 flex -translate-x-1/2 items-center gap-2 rounded border border-amber-500 bg-amber-950 px-4 py-2 text-sm font-medium text-amber-100"><AlertTriangle size={16} /> No API key configured — add GROQ_API_KEY or GEMINI_API_KEY to your .env file for AI responses.</div>}
      {llmConfigured && llmOffline && <div className="fixed left-1/2 top-32 z-20 flex -translate-x-1/2 items-center gap-2 rounded border border-red-500 bg-red-950 px-4 py-2 text-sm font-medium text-red-100"><AlertTriangle size={16} /> AI is currently offline — answers are limited and may be generic until it reconnects.</div>}

      <div className="fixed z-20 w-48 rounded border border-slate-700 bg-slate-950/95 p-2 shadow-2xl" style={{ left: cameraPos.x, top: cameraPos.y }}>
        <div onPointerDown={startCameraDrag} className="mb-2 flex cursor-move touch-none select-none items-center justify-between px-1 text-xs text-slate-300"><span className="flex items-center gap-1"><Camera size={14} /> Candidate</span><span>{voiceState === "listening" ? "Listening" : voiceState === "ai_speaking" ? "AI speaking" : "Mic ready"}</span></div>
        <video ref={videoRef} autoPlay muted playsInline className="aspect-video w-full rounded bg-slate-900 object-cover" />
        {liveTranscript && <div className="mt-2 rounded bg-slate-900 p-2 text-xs text-cyan-100">{liveTranscript}</div>}
      </div>

      <section className={`relative z-10 grid min-h-0 grid-cols-1 gap-4 p-4 ${isDsaRound ? "lg:grid-cols-2" : ""}`}>
        <aside className={`dashboard-glass h-[calc(100vh-96px)] ${isCsRound ? "flex items-center justify-center overflow-hidden p-6" : "overflow-y-auto"}`}>
          {!isCsRound && <div className="sticky top-0 z-10 border-b border-slate-800/80 bg-slate-950/70 px-5 py-4 backdrop-blur-xl">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm text-slate-400">{isDsaRound ? (dsaProgress?.label || `Question ${dsaProgress?.current_question_index || 1} of ${dsaProgress?.total_questions || "?"}`) : "Project interview"}</div>
                <h2 className="truncate text-xl font-semibold">{isDsaRound ? currentProblem?.title : isCsRound ? "CS Fundamentals" : "Project + Behavioural"}</h2>
              </div>
              {currentProblem && <span className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300">{currentProblem.difficulty}</span>}
            </div>
            {isDsaRound && session?.dataset_size && <div className="mt-2 text-xs text-slate-500">Dataset: {session.dataset_size.toLocaleString()} {session.dataset_label || "public DSA problems"}{session.target_company ? ` - ${session.target_company}` : ""}</div>}
            {currentProblem?.companies?.length > 0 && <div className="mt-2 text-xs text-cyan-300">Seen in: {currentProblem.companies.slice(0, 5).join(", ")}{currentProblem.companies.length > 5 ? "..." : ""}</div>}
          </div>}
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
            <RoundContext items={[`Company: ${session?.target_company || form.target_company || "General"}`, `Role: ${form.job_role}`]} />
          )}
        </aside>

        <section className="h-[calc(100vh-96px)] min-h-0">
          {isDsaRound ? <div className="dashboard-glass h-full">
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
                    <button onClick={submitCode} disabled={isBusy} className="inline-flex items-center gap-2 rounded border border-cyan-600 bg-cyan-950 px-4 py-2 font-semibold text-cyan-100 disabled:opacity-50"><Send size={17} /> Submit</button>
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
    <main className="dashboard-shell min-h-screen text-white codevoir-welcome-page">
      <BackgroundCanvas />
      
      <header className="welcome-navbar">
        <div className="welcome-navbar-logo text-white font-extrabold text-2xl" style={{ cursor: 'default', userSelect: 'none' }}>CV</div>
        <div className="welcome-navbar-actions">
          <button type="button" onClick={onAuthenticate} className="welcome-nav-link">Log in</button>
          <button type="button" onClick={onAuthenticate} className="welcome-nav-btn">Sign in</button>
        </div>
      </header>

      {error && <div className="fixed left-1/2 top-4 z-30 max-w-xl -translate-x-1/2 rounded border border-red-300 bg-red-950 px-4 py-3 text-sm text-red-100">{error}</div>}
      <section className="relative z-10 mx-auto grid min-h-screen max-w-7xl gap-10 px-6 pb-10 pt-24 lg:grid-cols-[minmax(0,.95fr)_minmax(360px,.65fr)] lg:items-center">
        <motion.div className="grid max-w-3xl gap-6" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55 }}>
          <p className="welcome-greeting">Welcome to</p>
          <h1 className="font-display text-6xl font-semibold leading-[1.02] tracking-normal text-white md:text-8xl">
            <span className="welcome-title-brand">CodeVoir</span>
            <span className="block text-amber-300">Interview Arena</span>
          </h1>
          <p className="max-w-2xl text-lg leading-8 text-slate-300">Practice, learn, revise, and get discovered—all in one place. CodeVoir transforms complex documentation into interview-ready knowledge, generates intelligent revision resources, delivers company-focused interview preparation, and connects you with opportunities aligned to your skills and aspirations.</p>
          <div className="grid max-w-2xl gap-4 sm:grid-cols-3">
            <WelcomeStat icon={<Code2 size={20} />} label="AI interview rounds" value="DSA, CS, projects" iconBg="icon-bg-blue" />
            <WelcomeStat icon={<Zap size={20} />} label="Opportunities" value="Upskill and apply" iconBg="icon-bg-green" />
            <WelcomeStat icon={<FileText size={20} />} label="Simplified learning" value="Upload and study" iconBg="icon-bg-purple" />
          </div>

          <div className="welcome-trust-badge">
            <div className="trust-col">
              <ShieldCheck size={18} className="trust-icon" />
              <div className="trust-text">
                <span className="trust-label">Trusted by</span>
                <span className="trust-value">Top Companies</span>
              </div>
            </div>
            <div className="trust-divider" />
            <div className="trust-col">
              <Users size={18} className="trust-icon" />
              <div className="trust-text">
                <span className="trust-label">Personalized</span>
                <span className="trust-value">Preparation</span>
              </div>
            </div>
            <div className="trust-divider" />
            <div className="trust-col">
              <BarChart3 size={18} className="trust-icon" />
              <div className="trust-text">
                <span className="trust-label">Track Progress</span>
                <span className="trust-value">& Improve</span>
              </div>
            </div>
          </div>
        </motion.div>

        <motion.div className="welcome-auth-stack" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12, duration: 0.55 }}>
          <div className="welcome-logo-stage">
            <OrbitingLogoSystem stats={defaultDashboard.stats} />
          </div>
          <section className="welcome-signin-panel">
            <h3 className="welcome-panel-title">Elevate your interviews</h3>
            <p className="welcome-panel-subtitle">Access your personalized preparation space.</p>
            <button type="button" onClick={onAuthenticate} className="welcome-signin-btn">
              <LogIn size={18} /> Sign in to CodeVoir
            </button>
            <div className="welcome-secure-badge">
              <Lock size={12} /> Secure Authentication
            </div>
          </section>
        </motion.div>
      </section>
    </main>
  )
}

function WelcomeStat({ icon, label, value, iconBg }) {
  return (
    <div className="welcome-stat-card">
      <div className="welcome-stat-top">
        <div className={`welcome-stat-icon-box ${iconBg || ""}`}>{icon}</div>
        <div className="welcome-stat-arrow-btn">
          <ArrowRight size={14} />
        </div>
      </div>
      <div className="welcome-stat-content">
        <div className="welcome-stat-label">{label}</div>
        <div className="welcome-stat-value">{value}</div>
      </div>
    </div>
  )
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
// eslint-disable-next-line no-unused-vars
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

// eslint-disable-next-line no-unused-vars
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

function Dashboard({ userProfile, dashboard, loading, error, onStart, onRefresh, onOpenReport, onLogout, onOpportunities, onDocsAssistant, onReportsPage, isBusy }) {
  const [profileOpen, setProfileOpen] = useState(false)
  const stats = dashboard.stats || defaultDashboard.stats
  const interviews = dashboard.interviews || []
  const completed = interviews.filter((item) => item.has_report)
  const displayName = (userProfile.name || "Rishika Jain").toUpperCase()
  const metrics = [
    { icon: <Briefcase size={17} />, label: "Interviews", value: stats.total_interviews || 0 },
    { icon: <Target size={17} />, label: "Companies", value: stats.companies_practiced || 0 },
    { icon: <TrendingUp size={17} />, label: "Average", value: `${stats.average_score || 0}/100`, tone: "teal" },
    { icon: <Trophy size={17} />, label: "Best", value: `${stats.best_score || 0}/100`, tone: "amber" },
  ]

  return (
    <main className="dashboard-shell min-h-screen text-slate-100 codevoir-dashboard-page">
      <BackgroundCanvas />
      {error && <div className="fixed left-1/2 top-20 z-50 max-w-xl -translate-x-1/2 rounded border border-red-400 bg-red-950/95 px-4 py-3 text-sm text-red-100 shadow-2xl">{error}</div>}
      <DashboardNav
        displayName={displayName}
        onLogout={onLogout}
        onOpenProfile={() => setProfileOpen(true)}
      />

      <section className="relative z-10 mx-auto grid max-w-7xl gap-5 px-6 pb-14 pt-20">
        <DashboardHero
          displayName={displayName}
          stats={stats}
          completed={completed.length}
          onStart={() => onStart()}
          onOpportunities={onOpportunities}
          onDocsAssistant={onDocsAssistant}
          onRefresh={onRefresh}
          loading={loading}
        />
        <StatsBar metrics={metrics} />
        <DashboardReportsSection 
          interviews={interviews} 
          onOpenReport={onOpenReport} 
          onStart={() => onStart()} 
          isBusy={isBusy} 
          onReportsPage={onReportsPage}
        />

      </section>

      {profileOpen && (
        <>
          <button type="button" className="profile-drawer-backdrop" onClick={() => setProfileOpen(false)} aria-label="Close user panel" />
          <UserProfilePanel
            userProfile={userProfile}
            onClose={() => setProfileOpen(false)}
          />
        </>
      )}
    </main>
  )
}

const dashboardCard = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: "easeOut" } },
}

const dashboardStagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
}

function DashboardNav({ displayName, onLogout, onOpenProfile }) {
  const initial = displayName ? displayName[0] : "M"
  return (
    <header className="fixed inset-x-0 top-0 z-40 border-b border-white/10 bg-[#003366]/90 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-6">
        <div className="welcome-navbar-logo text-white font-extrabold text-2xl" style={{ cursor: 'default', userSelect: 'none' }}>CV</div>
        <div className="flex shrink-0 items-center justify-end gap-3">
          <DashboardButton onClick={onLogout} icon={<LogOut size={15} />} label="Logout" variant="ghost" />
          <button
            type="button"
            onClick={onOpenProfile}
            className="profile-avatar-btn"
            title="Open profile"
          >
            {initial}
          </button>
        </div>
      </div>
    </header>
  )
}

function DashboardButton({ icon, label, variant, ...props }) {
  const styles = {
    ghost: "border-white/10 bg-white/[.03] text-slate-200 hover:border-white/25 hover:bg-white/[.08]",
    purple: "border-purple-400/45 bg-purple-500/10 text-purple-200 hover:border-purple-300 hover:bg-purple-500/20",
    amber: "border-amber-300 bg-amber-400 text-slate-950 shadow-[0_0_28px_rgba(245,158,11,.25)] hover:bg-amber-300",
  }
  return <button {...props} className={`inline-flex h-10 items-center gap-2 rounded px-3 text-sm font-semibold transition hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]}`}>{icon}<span>{label}</span></button>
}

function DashboardHero({ displayName, stats, completed, onStart, onOpportunities, onDocsAssistant }) {
  return (
    <motion.section className="dashboard-hero" initial="hidden" animate="show" variants={dashboardStagger}>
      <motion.div variants={dashboardCard} className="dashboard-hero-copy">
        <h2 className="font-display text-5xl font-semibold leading-[1.02] tracking-normal text-white md:text-7xl">
          Discover. Prepare. <span className="text-accent-gradient">Get hired.</span>
        </h2>
        <p className="mt-2 max-w-2xl text-base md:text-lg text-slate-300 font-medium italic">
          Your AI career copilot. Discover jobs and hackathons, practice exact company rounds, and convert complex docs into interactive flashcards instantly.
        </p>

        <div className="dashboard-action-stack">
          <div className="dashboard-action-card">
            <img 
              src="/minimal_coder.png" 
              alt="Prep Interview" 
              className="dashboard-action-img" 
              style={{ objectFit: 'contain', padding: '16px 16px 0 16px' }}
            />
            <button onClick={onStart} className="dashboard-primary-action"><Play size={18} /> Start interview</button>
          </div>
          <div className="dashboard-action-card">
            <img 
              src="/minimal_career.png" 
              alt="Opportunities" 
              className="dashboard-action-img" 
              style={{ objectFit: 'contain', padding: '16px 16px 0 16px' }}
            />
            <button onClick={onOpportunities} className="dashboard-secondary-action"><Zap size={17} /> Opportunities</button>
          </div>
          <div className="dashboard-action-card">
            <img 
              src="/minimal_docs.png" 
              alt="Documentation Assistant" 
              className="dashboard-action-img" 
              style={{ objectFit: 'contain', padding: '16px 16px 0 16px' }}
            />
            <button onClick={onDocsAssistant} className="dashboard-secondary-action"><FileText size={17} /> Documentation Assistant</button>
          </div>
        </div>

      </motion.div>
      <motion.div variants={dashboardCard} className="dashboard-globe-panel" aria-hidden="true">
        <OrbitingLogoSystem stats={stats} />
      </motion.div>
    </motion.section>
  )
}

function DSATrackCard({ dsaReports, completedDsa, dsaAverage, onStart }) {
  return (
    <motion.section variants={dashboardCard} className="dashboard-glass border-l-4 border-l-amber-400 p-6">
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div className="max-w-2xl">
          <div className="text-xs font-semibold uppercase tracking-[.18em] text-amber-300">DSA Interview Track</div>
          <h2 className="mt-3 font-display text-3xl font-semibold leading-tight tracking-normal text-white md:text-4xl">Company-style coding rounds are ready.</h2>
          <p className="mt-3 max-w-xl text-sm leading-6 text-slate-300">Practice runnable coding interviews, compare attempts, and keep reports aligned with the companies you are preparing for.</p>
        </div>
        <button onClick={onStart} className="inline-flex h-11 shrink-0 items-center gap-2 rounded bg-amber-400 px-4 font-bold text-slate-950 shadow-[0_0_26px_rgba(245,158,11,.25)] transition hover:scale-[1.03] hover:bg-amber-300"><Play size={17} /> Practice DSA</button>
      </div>
      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <MiniStat label="DSA Attempts" value={dsaReports} />
        <MiniStat label="DSA Reports" value={completedDsa} />
        <MiniStat label="DSA Average" value={`${dsaAverage}/100`} />
      </div>
    </motion.section>
  )
}

function RoundShortcuts({ onStart }) {
  const rounds = [
    { label: "DSA + code execution", helper: "Monaco editor and runnable tests", tone: "amber", round: "dsa" },
    { label: "CS fundamentals", helper: "Core concepts and follow-ups", tone: "teal", round: "cs_fundamentals" },
    { label: "Project + behavioural", helper: "Resume evidence and STAR answers", tone: "purple", round: "project_behavioral" },
  ]
  return (
    <motion.section variants={dashboardCard} className="dashboard-glass p-6">
      <h2 className="flex items-center gap-2 font-display text-xl font-semibold tracking-normal text-white"><Sparkles size={19} className="text-purple-300" /> Round Shortcuts</h2>
      <div className="mt-5 grid gap-3">
        {rounds.map((round) => (
          <button key={round.round} onClick={() => onStart(round.round)} className={`round-shortcut round-shortcut-${round.tone}`}>
            <span className="font-semibold text-white">{round.label}</span>
            <span className="text-xs text-slate-400">{round.helper}</span>
          </button>
        ))}
      </div>
    </motion.section>
  )
}

function StatsBar({ metrics }) {
  return (
    <motion.section className="dashboard-glass grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4" initial="hidden" animate="show" variants={dashboardStagger}>
      {metrics.map((metric) => <DashboardMetric key={metric.label} {...metric} />)}
    </motion.section>
  )
}

function DashboardReportsSection({ interviews, onOpenReport, onStart, isBusy, onReportsPage }) {
  const completed = interviews.filter((item) => item.has_report)
  
  return (
    <motion.section 
      className="dashboard-reports-section mt-10" 
      initial={{ opacity: 0, y: 20 }} 
      animate={{ opacity: 1, y: 0 }} 
      transition={{ delay: 0.15, duration: 0.55 }}
    >
      <div className="flex items-center justify-between mb-6">
        <h2 
          className="font-display text-2xl font-bold text-slate-800 cursor-pointer hover:text-[#0a66c2] transition-colors flex items-center gap-1.5"
          onClick={onReportsPage}
        >
          Interview Reports
          <ChevronRight size={22} className="text-[#0a66c2]" />
        </h2>
      </div>

      {completed.length > 0 ? (
        <div className="report-empty-state cursor-pointer hover:shadow-lg transition-all duration-300" onClick={onReportsPage}>
          <div className="report-empty-grid">
            <div className="report-empty-copy">
              <span className="text-xs font-bold text-[#0a66c2] bg-[#eef2ff] px-2.5 py-1 rounded-full uppercase tracking-wider mb-3 inline-block">
                {completed.length} Report{completed.length === 1 ? "" : "s"} Available
              </span>
              <h3 className="report-empty-title">Detailed Performance Feedback</h3>
              <p className="report-empty-subtitle">
                Access comprehensive skill gap breakdowns, topic masteries, behavioral evaluations, and playback of your submitted code for all completed interview sessions.
              </p>
              <button onClick={(e) => { e.stopPropagation(); onReportsPage(); }} className="report-empty-btn">
                View All Reports <ArrowRight size={16} className="ml-1.5" />
              </button>
            </div>
            <div className="report-empty-visual">
              <img src="/dashboard_analytics_vector.png" alt="Reports feedback" className="report-empty-img" />
            </div>
          </div>
        </div>
      ) : (
        <div className="report-empty-state">
          <div className="report-empty-grid">
            <div className="report-empty-copy">
              <h3 className="report-empty-title">Your feedback dashboard is waiting</h3>
              <p className="report-empty-subtitle">
                Complete your first company-specific AI interview round to unlock detailed skill gaps, topic masteries, behavioral feedback, and runnable code playback.
              </p>
              <button onClick={onStart} className="report-empty-btn">
                <Play size={16} /> Start your first interview
              </button>
            </div>
            <div className="report-empty-visual">
              <img src="/interview_prep_vector.png" alt="No reports" className="report-empty-img" />
            </div>
          </div>
        </div>
      )}
    </motion.section>
  )
}

function DashboardWorkspace({ userProfile, stats, interviews, completed, onReportsPage, onStart }) {
  const dsaReports = interviews.filter((item) => item.round_type === "dsa").length
  const completedDsa = completed.filter((item) => item.round_type === "dsa").length
  const dsaAverage = stats.average_score || 0
  return (
    <motion.section className="dashboard-workspace" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2, duration: 0.55 }}>
      <DSATrackCard dsaReports={dsaReports} completedDsa={completedDsa} dsaAverage={dsaAverage} onStart={() => onStart("dsa")} />
      <RoundShortcuts onStart={onStart} />
    </motion.section>
  )
}

function UserProfilePanel({ userProfile, onClose }) {
  const initials = (userProfile.name || "Mridu").split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "M"
  return (
    <aside className="profile-side-panel profile-drawer-panel">
      <button type="button" onClick={onClose} className="profile-drawer-close" title="Close user panel" aria-label="Close user panel">
        <X size={13} />
      </button>
      <div className="flex items-center gap-3">
        <div className="profile-avatar flex-shrink-0">{initials}</div>
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold text-white truncate" style={{ margin: 0 }}>
            {userProfile.name || "Mridu"}
          </h2>
          <p className="text-xs text-slate-400 truncate mt-0.5" style={{ margin: 0 }}>
            {userProfile.email || "mridubd7454@gmail.com"}
          </p>
        </div>
      </div>
    </aside>
  )
}

function ReportsSearchPage({ dashboard, onBack, onOpenReport, isBusy }) {
  const [query, setQuery] = useState("")
  const interviews = dashboard.interviews || []
  const completed = interviews.filter((item) => item.has_report)
  const normalizedQuery = query.trim().toLowerCase()
  const visible = normalizedQuery
    ? interviews.filter((item) => (item.target_company || "General").toLowerCase().includes(normalizedQuery))
    : interviews
  const companies = [...new Set(interviews.map((item) => item.target_company || "General"))].sort()

  return (
    <main className="dashboard-shell min-h-screen text-slate-100 codevoir-dashboard-page">
      <BackgroundCanvas />
      <header className="relative z-10 border-b border-sky-400/10 bg-slate-950/70 backdrop-blur-xl">
        <div className="w-full flex items-center justify-between gap-4 px-4 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <button onClick={onBack} className="grid h-10 w-10 place-items-center rounded border border-sky-400/30 bg-sky-400/10 text-sky-100 shadow-[0_0_24px_rgba(56,189,248,.16)] transition hover:border-sky-300 hover:bg-sky-400/20" title="Back to dashboard"><ArrowLeft size={20} /></button>
            <div>
              <h1 className="font-display text-xl font-semibold tracking-normal text-white">Interview Reports</h1>
            </div>
          </div>
        </div>
      </header>

      <section className="relative z-10 mx-auto grid max-w-7xl gap-5 px-6 pb-8 pt-3">
        <div className="report-search-card p-5">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-sky-200" size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search a company you have interviewed for"
              className="h-12 w-full rounded border border-sky-400/25 bg-slate-950/80 pl-11 pr-4 text-sm text-slate-100 outline-none shadow-inner shadow-black/20 transition placeholder:text-slate-500 focus:border-sky-300 focus:shadow-[0_0_28px_rgba(56,189,248,.16)]"
            />
          </label>
          {companies.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {companies.slice(0, 10).map((company) => (
                <button key={company} onClick={() => setQuery(company)} className="rounded border border-sky-300/25 bg-sky-300/10 px-3 py-1.5 text-xs font-semibold text-sky-100 transition hover:scale-[1.02] hover:border-sky-200 hover:bg-sky-300/20">
                  {company}
                </button>
              ))}
            </div>
          )}
        </div>

        <section className="report-results-panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-sky-400/10 px-5 py-4">
            <h2 className="font-display text-xl font-semibold tracking-normal text-white">{normalizedQuery ? `Results for "${query.trim()}"` : "All company interviews"}</h2>
            <div className="rounded-full border border-sky-400/25 bg-sky-400/10 px-3 py-1 text-sm font-semibold text-sky-100">{visible.length} attempt{visible.length === 1 ? "" : "s"}</div>
          </div>
          {visible.length ? (
            <div className="grid gap-4 p-5">
              {visible.map((item) => (
                <div key={item.session_id} className="report-result-card grid gap-4 p-5 lg:grid-cols-[minmax(0,1fr)_auto]">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-sky-100/65">
                      <span className="inline-flex items-center gap-1 rounded-full border border-sky-400/20 bg-sky-400/10 px-2 py-1"><Calendar size={14} /> {formatDate(item.completed_at || item.created_at)}</span>
                      <span className="rounded-full border border-blue-300/25 bg-blue-300/10 px-2 py-1 text-blue-100">{prettyRound(item.round_type)}</span>
                    </div>
                    <h3 className="mt-2 font-display text-lg font-semibold tracking-normal text-white">{item.target_company || "General"} - {item.job_role || "Software Engineer"}</h3>
                    <DashboardHighlights title="Strengths" items={item.strengths} tone="blue" />
                    <DashboardHighlights title="Focus areas" items={item.weak_areas} tone="blue" />
                  </div>
                  <div className="flex min-w-40 flex-col items-start gap-3 lg:items-end">
                    <ScoreBadge score={item.overall_score} />
                    <div className="text-sm font-medium text-slate-300">{item.hiring_signal || "In progress"}</div>
                    {item.has_report ? (
                      <button onClick={() => onOpenReport(item.session_id)} disabled={isBusy} className="rounded bg-sky-400 px-4 py-2 text-sm font-bold text-slate-950 shadow-[0_0_24px_rgba(56,189,248,.25)] transition hover:scale-[1.03] hover:bg-sky-300 disabled:opacity-50">View report</button>
                    ) : (
                      <span className="rounded border border-blue-300/25 bg-blue-300/10 px-3 py-2 text-sm text-blue-100">Pending report</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-5">
              <div className="rounded border border-dashed border-slate-600/70 bg-slate-950/40 p-8 text-center text-sm text-slate-400">
                {normalizedQuery ? "No interview attempt found for that company." : "No interview history for this user yet."}
              </div>
            </div>
          )}
        </section>
      </section>
    </main>
  )
}

function EmptyStateCard({ hasInterviews, onStart }) {
  if (hasInterviews) return null
  return (
    <motion.section className="dashboard-glass empty-pulse p-8" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18, duration: 0.55 }}>
      <div className="max-w-2xl">
        <div className="text-xs font-semibold uppercase tracking-[.2em] text-slate-500">No Interviews Yet</div>
        <h2 className="mt-3 font-display text-3xl font-semibold tracking-normal text-white">Start a company-specific AI interview to build your dashboard.</h2>
        <p className="mt-3 text-sm leading-6 text-slate-300">Reports, company trends, score movement, strengths, and focus areas will appear here after your first completed round.</p>
        <button onClick={onStart} className="mt-5 inline-flex h-11 items-center gap-2 rounded bg-teal-400 px-4 font-bold text-slate-950 shadow-[0_0_26px_rgba(20,184,166,.22)] transition hover:scale-[1.03] hover:bg-teal-300"><Play size={17} /> Start interview</button>
      </div>
    </motion.section>
  )
}

function InterviewReports({ interviews, completed, onOpenReport, isBusy }) {
  return (
    <motion.section className="dashboard-glass overflow-hidden" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.24, duration: 0.55 }}>
      <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
        <h2 className="font-display text-xl font-semibold tracking-normal text-white">Interview Reports</h2>
        <div className="text-sm text-slate-400">{completed.length} completed</div>
      </div>
      {interviews.length ? (
        <div className="divide-y divide-white/10">
          {interviews.map((item) => (
            <div key={item.session_id} className="grid gap-4 p-5 lg:grid-cols-[minmax(0,1fr)_auto]">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span className="inline-flex items-center gap-1"><Calendar size={14} /> {formatDate(item.completed_at || item.created_at)}</span>
                  <span>{prettyRound(item.round_type)}</span>
                  {item.problem_title && <span className="truncate">{item.problem_title}</span>}
                </div>
                <h3 className="mt-2 font-display text-lg font-semibold tracking-normal text-white">{item.target_company || "General"} - {item.job_role || "Software Engineer"}</h3>
                <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">{item.summary || "No report generated yet. End the interview to produce a full analysis."}</p>
                <DashboardHighlights title="Strengths" items={item.strengths} tone="emerald" />
                <DashboardHighlights title="Focus areas" items={item.weak_areas} tone="amber" />
              </div>
              <div className="flex min-w-40 flex-col items-start gap-3 lg:items-end">
                <ScoreBadge score={item.overall_score} />
                <div className="text-sm text-slate-400">{item.hiring_signal || "In progress"}</div>
                {item.has_report ? (
                  <button onClick={() => onOpenReport(item.session_id)} disabled={isBusy} className="rounded border border-teal-400/40 bg-teal-400/10 px-3 py-2 text-sm font-semibold text-teal-100 disabled:opacity-50">View report</button>
                ) : (
                  <span className="rounded border border-white/10 px-3 py-2 text-sm text-slate-500">In progress</span>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="p-5">
          <div className="rounded border border-dashed border-slate-600/70 bg-slate-950/40 p-8 text-center text-sm text-slate-400">No interview history for this user yet.</div>
        </div>
      )}
    </motion.section>
  )
}

function BackgroundCanvas() {
  return (
    <div className="pointer-events-none fixed inset-0 z-0">
      <Canvas camera={{ position: [0, 0, 7.4], fov: 45 }} dpr={[1, 1.7]} gl={{ antialias: true, alpha: true }}>
        <ambientLight intensity={0.7} />
        <pointLight position={[2, 3, 4]} intensity={1.3} color="#f59e0b" />
        <ParticleField />
      </Canvas>
    </div>
  )
}

function OrbitingLogoSystem() {
  const companies = [
    { name: "Google", mark: "G", orbit: "orbit-a", delay: "0s", brand: "google" },
    { name: "Amazon", mark: "a", orbit: "orbit-b", delay: "-4s", brand: "amazon" },
    { name: "Adobe", mark: "A", orbit: "orbit-c", delay: "-8s", brand: "adobe" },
    { name: "Meta", mark: "∞", orbit: "orbit-a", delay: "-12s", brand: "meta" },
    { name: "Microsoft", mark: "⊞", orbit: "orbit-b", delay: "-16s", brand: "microsoft" },
    { name: "Netflix", mark: "N", orbit: "orbit-c", delay: "-20s", brand: "netflix" },
  ]
  return (
    <div className="logo-system">
      <div className="logo-orbit-ring logo-orbit-ring-1" />
      <div className="logo-orbit-ring logo-orbit-ring-2" />
      <div className="logo-orbit-ring logo-orbit-ring-3" />
      <div className="cv-sun">
        <div className="cv-swoosh cv-swoosh-blue" />
        <div className="cv-swoosh cv-swoosh-white" />
        <div className="cv-letters">CV</div>
        <div className="cv-dot cv-dot-1" />
        <div className="cv-dot cv-dot-2" />
      </div>
      {companies.map((company, index) => (
        <div key={company.name} className={`company-orbit ${company.orbit}`} style={{ animationDelay: company.delay }}>
          <span className={`company-planet company-planet-${company.brand}`} title={company.name}>
            <span className="company-logo-mark">{company.mark}</span>
            <span className="company-logo-name">{company.name}</span>
          </span>
        </div>
      ))}
    </div>
  )
}

function ParticleField() {
  const pointsRef = useRef(null)
  const vertices = useMemo(() => {
    const data = []
    for (let i = 0; i < 130; i += 1) {
      data.push((Math.random() - 0.5) * 10, (Math.random() - 0.5) * 6, (Math.random() - 0.5) * 4)
    }
    return new Float32Array(data)
  }, [])

  useFrame((state) => {
    if (!pointsRef.current) return
    pointsRef.current.rotation.y = state.clock.elapsedTime * 0.025
    pointsRef.current.position.y = Math.sin(state.clock.elapsedTime * 0.35) * 0.08
  })

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[vertices, 3]} />
      </bufferGeometry>
      <pointsMaterial color="#94a3b8" size={0.018} transparent opacity={0.48} sizeAttenuation />
    </points>
  )
}

function DashboardMetric({ icon, label, value, tone }) {
  const valueTone = tone === "teal" ? "text-teal-300" : tone === "amber" ? "text-amber-300" : "text-white"
  return <motion.div variants={dashboardCard} className="rounded border border-white/10 bg-slate-950/45 p-4">
    <div className="flex items-center gap-2 text-xs uppercase text-slate-400">{icon}{label}</div>
    <div className={`mt-3 font-display text-3xl font-semibold tracking-normal ${valueTone}`}>{value}</div>
  </motion.div>
}

function MiniStat({ label, value }) {
  return <div className="rounded border border-white/10 bg-slate-950/45 p-3">
    <div className="text-xs uppercase text-slate-500">{label}</div>
    <div className="mt-1 font-display text-lg font-semibold tracking-normal text-white">{value}</div>
  </div>
}

function ScoreBadge({ score }) {
  const value = Math.round(Number(score) || 0)
  const tone = "border-sky-400/40 bg-sky-400/10 text-sky-200 shadow-[0_0_24px_rgba(56,189,248,.12)]"
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
  const color = tone === "blue" ? "text-sky-300" : tone === "emerald" ? "text-emerald-300" : "text-amber-300"
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

function SetupCarousel() {
  const slides = [
    {
      img: "/setup_illustration.png",
      title: "Real-time Live Simulator",
      desc: "Interactive voice and code environment with real-time feedback."
    },
    {
      img: "/coding_prep_scene.png",
      title: "Targeted Coding Rounds",
      desc: "DSA prep tailored specifically to your target company."
    },
    {
      img: "/interview_prep_vector.png",
      title: "Behavioral Personalization",
      desc: "AI questions tailored to your resume and job description."
    }
  ];

  const [current, setCurrent] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrent((prev) => (prev + 1) % slides.length);
    }, 4000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="w-full flex flex-col items-center justify-center p-2">
      <div className="relative w-full max-w-[420px] aspect-square rounded-2xl overflow-hidden border border-slate-200/80 bg-white/40 shadow-sm backdrop-blur-sm flex items-center justify-center">
        {slides.map((slide, idx) => (
          <div
            key={idx}
            className={`absolute inset-0 transition-opacity duration-700 flex flex-col ${idx === current ? "opacity-100 z-10" : "opacity-0 z-0"}`}
          >
            <img src={slide.img} alt={slide.title} className="h-full w-full object-cover" />
          </div>
        ))}
      </div>
      <div className="mt-4 text-center">
        <h3 className="text-sm font-semibold text-slate-800 transition-all duration-300">{slides[current].title}</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-[320px] mx-auto transition-all duration-300">{slides[current].desc}</p>
      </div>
      <div className="flex gap-1.5 mt-3">
        {slides.map((_, idx) => (
          <button
            key={idx}
            onClick={() => setCurrent(idx)}
            className={`h-1.5 rounded-full transition-all duration-300 ${idx === current ? "w-4 bg-[#0a66c2]" : "w-1.5 bg-slate-300"}`}
            aria-label={`Slide ${idx + 1}`}
          />
        ))}
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return <label className="grid gap-2 text-sm text-slate-300"><span>{label}</span>{children}</label>
}

function FeedbackLoading({ onBack }) {
  return (
    <main className="dashboard-shell min-h-screen text-slate-100 codevoir-dashboard-page">
      <BackgroundCanvas />
      <section className="relative z-10 grid min-h-screen place-items-center px-6">
        <div className="dashboard-glass max-w-xl p-8 text-center">
          <div className="mx-auto mb-5 grid h-14 w-14 place-items-center rounded-2xl border border-cyan-300/40 bg-cyan-400/10 text-cyan-200 shadow-[0_0_36px_rgba(34,211,238,.18)]">
            <BarChart3 size={26} />
          </div>
          <div className="text-xs font-semibold uppercase tracking-[0.28em] text-cyan-300">Generating report</div>
          <h1 className="mt-3 font-display text-3xl font-semibold tracking-normal text-white">Building your interview feedback.</h1>
          <p className="mt-3 text-sm leading-6 text-slate-400">Your round is complete. CodeVoir is preparing the report now, so old interview replies will not leak into the next round.</p>
          <div className="mx-auto mt-6 h-2 max-w-xs overflow-hidden rounded-full bg-slate-900">
            <div className="h-full w-1/2 animate-pulse rounded-full bg-cyan-300" />
          </div>
          <button onClick={onBack} className="mt-6 rounded border border-slate-700 bg-slate-950 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:border-cyan-400 hover:text-cyan-100">
            Back to dashboard
          </button>
        </div>
      </section>
    </main>
  )
}

// eslint-disable-next-line no-unused-vars
function Panel({ title, icon, children }) {
  return <div className="min-h-0 rounded border border-slate-800 bg-slate-900"><div className="flex items-center gap-2 border-b border-slate-800 px-3 py-2 text-sm font-semibold">{icon}{title}</div><div className="p-3">{children}</div></div>
}

function ProblemBlock({ title, items }) {
  if (!items.length) return null
  return <div><div className="mb-2 font-semibold text-slate-100">{title}</div><div className="grid gap-2">{items.map((item) => <pre key={item} className="whitespace-pre-wrap rounded bg-slate-950 p-3 text-xs leading-5 text-slate-300">{item}</pre>)}</div></div>
}

function RoundContext({ title, items }) {
  return <div className="space-y-4 p-5 text-sm text-slate-300">{title && <div><div className="text-xs uppercase text-slate-500">Round context</div><h3 className="mt-1 text-lg font-semibold text-slate-100">{title}</h3></div>}<div className="grid gap-2">{items.filter(Boolean).map((item) => <div key={item} className="rounded bg-slate-950 p-3">{item}</div>)}</div></div>
}

function InterviewWorkspace({ input, setInput, isBusy, sendMessage, toggleMic, autoVoice, voiceState, liveTranscript, lastAiMessage, isCsRound, scratchpad, setScratchpad, scratchpadMode, setScratchpadMode }) {
  return (
    <div className="dashboard-glass grid h-full min-h-0 grid-rows-[auto_1fr_auto] overflow-hidden">
      <div className="border-b border-slate-800/80 px-5 py-4">
        <div className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-300">{isCsRound ? "CS fundamentals" : "Project + behavioural"}</div>
        <h2 className="mt-1 text-xl font-semibold text-slate-50">Live interview workspace</h2>
      </div>

      <div className="min-h-0 space-y-4 overflow-y-auto p-5">
        <section className="rounded-lg border border-cyan-400/25 bg-slate-950/80 p-5 shadow-[0_0_40px_rgba(34,211,238,.08)]">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-slate-300">Current question</div>
            {isBusy && <span className="rounded-full border border-cyan-400/30 bg-cyan-400/10 px-2.5 py-1 text-xs text-cyan-100">Thinking...</span>}
          </div>
          <p className="whitespace-pre-wrap text-balance text-2xl font-semibold leading-10 text-cyan-50">
            {lastAiMessage || "Loading your first question..."}
          </p>
        </section>

        {isCsRound && (
          <section className="rounded-lg border border-slate-800 bg-slate-950/70 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-slate-200">Scratchpad</div>
                <div className="text-xs text-slate-500">Use this for rough notes. It is sent as context with your answer.</div>
              </div>
              <select value={scratchpadMode} onChange={(event) => setScratchpadMode(event.target.value)} className="w-36 py-2 text-xs">
                <option value="notes">Notes</option>
                <option value="outline">Outline</option>
                <option value="examples">Examples</option>
              </select>
            </div>
            <textarea value={scratchpad} onChange={(event) => setScratchpad(event.target.value)} placeholder="Optional notes for this CS answer..." className="h-28 w-full resize-y rounded border border-slate-700 bg-slate-950 p-3 text-sm text-slate-100 outline-none focus:border-cyan-400" />
          </section>
        )}

        {liveTranscript && (
          <div className="rounded border border-cyan-400/25 bg-cyan-950/40 p-3 text-sm text-cyan-100">
            Hearing: {liveTranscript}
          </div>
        )}
      </div>

      <div className="border-t border-slate-800/80 p-5">
        <label className="mb-2 block text-sm font-semibold text-slate-300">Your answer</label>
        <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="Answer the interviewer here, or use voice." className="h-36 w-full resize-y rounded border border-slate-700 bg-slate-950 p-4 text-sm text-slate-100 outline-none focus:border-cyan-400" />
        <div className="mt-3 flex gap-3">
          <button onClick={() => sendMessage()} disabled={isBusy || !input.trim()} className="flex-1 rounded bg-cyan-400 px-4 py-3 font-bold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50">
            Send answer
          </button>
          <button onClick={toggleMic} className={`rounded border px-4 py-3 ${autoVoice || voiceState === "listening" ? "border-red-400 bg-red-950 text-red-100" : "border-cyan-600 bg-cyan-950 text-cyan-100"}`} title="Toggle microphone">
            {autoVoice || voiceState === "listening" ? <Square size={18} /> : <Mic size={18} />}
          </button>
        </div>
      </div>
    </div>
  )
}

function CsRoundPanel({ messages, lastAiMessage, session, form }) {
  const csMemory = session?.cs_fundamentals || {}
  const currentTopic = csMemory.current_topic || ""
  const company = session?.target_company || form.target_company || "General"
  const role = form.job_role || session?.job_role || "Software Engineer"
  const latestAnswer = [...messages].reverse().find((m) => m.role === "candidate")?.content || ""

  return (
    <div className="relative flex min-h-full w-full items-center justify-center">
      <div className="pointer-events-none absolute inset-0 opacity-80 [background-image:linear-gradient(rgba(34,211,238,.08)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,.08)_1px,transparent_1px)] [background-size:34px_34px]" />
      <div className="pointer-events-none absolute left-8 right-8 top-10 h-px bg-gradient-to-r from-transparent via-cyan-300/50 to-transparent" />
      <div className="pointer-events-none absolute bottom-10 left-8 right-8 h-px bg-gradient-to-r from-transparent via-amber-300/40 to-transparent" />

      <div className="relative w-full max-w-4xl overflow-hidden rounded-lg border border-cyan-300/40 bg-[#050b14]/95 shadow-[0_0_80px_rgba(6,182,212,.22)] backdrop-blur-xl">
        <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-cyan-200 via-sky-400 to-amber-300" />
        <div className="absolute left-0 top-0 h-20 w-20 border-l-2 border-t-2 border-cyan-300/60" />
        <div className="absolute right-0 top-0 h-20 w-20 border-r-2 border-t-2 border-amber-300/50" />
        <div className="absolute bottom-0 left-0 h-20 w-20 border-b-2 border-l-2 border-sky-300/40" />
        <div className="absolute bottom-0 right-0 h-20 w-20 border-b-2 border-r-2 border-cyan-300/50" />

        <div className="relative border-b border-cyan-300/15 px-6 py-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="min-w-0 space-y-3">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.24em] text-cyan-200">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-300 opacity-60" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-cyan-200" />
                </span>
                CS Fundamentals Round
              </div>
              <div className="flex flex-wrap items-center gap-2 text-sm text-slate-300">
                <span className="rounded border border-cyan-300/20 bg-cyan-300/10 px-3 py-1 text-cyan-50">Role: {role}</span>
                <span className="rounded border border-amber-300/20 bg-amber-300/10 px-3 py-1 text-amber-50">Company: {company}</span>
              </div>
            </div>
            {currentTopic && <span className="rounded border border-cyan-300/40 bg-cyan-300/10 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-100 shadow-[0_0_24px_rgba(34,211,238,.12)]">{currentTopic}</span>}
          </div>
        </div>

        <div className="relative px-6 py-8 md:px-10 md:py-12">
          <div className="mb-5 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded border border-cyan-300/50 bg-cyan-300/10 text-cyan-100 shadow-[0_0_24px_rgba(34,211,238,.14)]">
                <Brain size={22} />
              </div>
              <div>
                <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Question stream</div>
                <div className="text-sm text-cyan-100">Live interviewer prompt</div>
              </div>
            </div>
            <div className="hidden h-10 items-center gap-1 md:flex">
              <span className="h-6 w-1 rounded bg-cyan-300/70" />
              <span className="h-10 w-1 rounded bg-sky-300/80" />
              <span className="h-4 w-1 rounded bg-amber-300/80" />
              <span className="h-8 w-1 rounded bg-cyan-200/70" />
            </div>
          </div>

          <div className="relative overflow-hidden rounded-lg border border-cyan-300/25 bg-gradient-to-br from-slate-900/95 via-cyan-950/45 to-slate-950 p-6 shadow-inner shadow-cyan-950/40">
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-200/80 to-transparent" />
            <div className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-cyan-200 via-sky-400 to-amber-300" />
            <p className="relative text-balance text-2xl font-semibold leading-10 text-cyan-50 md:text-3xl md:leading-[3.1rem]">
              {lastAiMessage || "Loading your first question..."}
            </p>
          </div>

          {latestAnswer && (
            <div className="mt-5 rounded border border-slate-800 bg-slate-950/70 p-3 text-xs leading-5 text-slate-400">
              <span className="font-semibold text-slate-300">Latest answer: </span>
              {latestAnswer.length > 220 ? `${latestAnswer.slice(0, 220)}...` : latestAnswer}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ProjectBehavioralWorkspace({ lastAiMessage, contextItems }) {
  const company = contextItems.find((item) => item.startsWith("Company:"))?.replace("Company:", "").trim() || "General"
  const role = contextItems.find((item) => item.startsWith("Role:"))?.replace("Role:", "").trim() || "Software Engineer"

  return (
    <div className="grid w-full content-start overflow-hidden rounded-lg border border-cyan-400/40 bg-slate-950/86 font-sans shadow-[0_26px_95px_rgba(34,211,238,0.16)] backdrop-blur-xl">
      <div className="border-b border-cyan-400/20 bg-gradient-to-r from-sky-950/40 via-slate-950/70 to-cyan-950/20 px-6 py-5">
        <div className="mb-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2 font-display text-xs font-bold uppercase tracking-[0.24em] text-cyan-200">
            <span className="h-2.5 w-2.5 rounded-full bg-cyan-300 shadow-[0_0_14px_rgba(34,211,238,0.75)]" />
            Project + Behavioural Round
          </div>
          <div className="hidden rounded border border-cyan-400/30 bg-cyan-400/10 px-3 py-1.5 font-display text-xs font-bold uppercase tracking-[0.18em] text-cyan-100 sm:block">
            Live interview
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <span className="rounded border border-sky-400/20 bg-sky-400/10 px-3 py-1.5 text-sm font-semibold text-slate-100">
            Role: {role}
          </span>
          <span className="rounded border border-cyan-400/20 bg-cyan-400/10 px-3 py-1.5 text-sm font-semibold text-slate-100">
            Company: {company}
          </span>
        </div>
      </div>

      <div className="p-7">
        <div className="mb-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded border border-cyan-400/35 bg-cyan-400/10 text-cyan-200">
              <Brain size={18} />
            </div>
            <div>
              <div className="font-display text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Question stream</div>
              <div className="text-sm font-semibold text-cyan-50">Live interviewer prompt</div>
            </div>
          </div>
          <div className="flex h-10 items-center gap-1.5 text-cyan-300">
            <span className="h-4 w-1 rounded-full bg-cyan-300/60" />
            <span className="h-7 w-1 rounded-full bg-cyan-300" />
            <span className="h-5 w-1 rounded-full bg-cyan-300/70" />
          </div>
        </div>

        <div className="rounded-lg border border-cyan-400/45 bg-gradient-to-br from-sky-950/72 via-slate-950 to-cyan-950/38 p-6 shadow-[0_0_52px_rgba(34,211,238,0.14)]">
          <div className="border-l-4 border-cyan-300 pl-4 font-display text-2xl font-semibold leading-[1.45] tracking-normal text-cyan-50">
            {lastAiMessage || "The interviewer question will appear here."}
          </div>
        </div>
      </div>
    </div>
  )
}

function Feedback({ report, onRestart, onBack }) {
  const breakdown = report.round_breakdown || {}
  const roundItems = roundBreakdownItems(breakdown)
  const integrity = report.integrity || {}

  return <main className="dashboard-shell min-h-screen p-6 text-slate-100 codevoir-dashboard-page">
    <BackgroundCanvas />
    <section className="dashboard-glass relative z-10 mx-auto w-full max-w-[95%] xl:max-w-[1400px] p-6">
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

// ─────────────────────────────────────────────────────────────────────────────
// DSA COMPREHENSIVE REPORT COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────

function verdictColors(signal) {
  if (!signal) return { bg: "bg-slate-800", border: "border-slate-600", text: "text-slate-300", dot: "bg-slate-400" }
  const s = signal.toLowerCase()
  if (s.includes("strong hire")) return { bg: "bg-emerald-950", border: "border-emerald-500", text: "text-emerald-300", dot: "bg-emerald-400" }
  if (s === "hire") return { bg: "bg-cyan-950", border: "border-cyan-500", text: "text-cyan-300", dot: "bg-cyan-400" }
  if (s.includes("lean hire")) return { bg: "bg-blue-950", border: "border-blue-500", text: "text-blue-300", dot: "bg-blue-400" }
  if (s.includes("lean reject")) return { bg: "bg-amber-950", border: "border-amber-500", text: "text-amber-300", dot: "bg-amber-400" }
  return { bg: "bg-red-950", border: "border-red-500", text: "text-red-300", dot: "bg-red-400" }
}

function scoreColor(score) {
  if (score >= 80) return { bar: "bg-emerald-400", text: "text-emerald-300" }
  if (score >= 65) return { bar: "bg-cyan-400", text: "text-cyan-300" }
  if (score >= 50) return { bar: "bg-blue-400", text: "text-blue-300" }
  if (score >= 35) return { bar: "bg-amber-400", text: "text-amber-300" }
  return { bar: "bg-red-400", text: "text-red-300" }
}

function labelColor(label) {
  if (!label) return "text-slate-400"
  const l = label.toLowerCase()
  if (l === "exceptional") return "text-emerald-300"
  if (l === "strong") return "text-cyan-300"
  if (l === "competent") return "text-blue-300"
  if (l === "developing") return "text-amber-300"
  return "text-red-300"
}

function RadarChart({ metrics }) {
  if (!metrics || metrics.length === 0) return null
  const size = 280
  const cx = size / 2
  const cy = size / 2
  const r = 100
  const n = metrics.length
  const angles = metrics.map((_, i) => (i * 2 * Math.PI / n) - Math.PI / 2)

  const rings = [0.25, 0.5, 0.75, 1.0].map((scale) => {
    const pts = angles.map((a) => `${cx + r * scale * Math.cos(a)},${cy + r * scale * Math.sin(a)}`).join(" ")
    return <polygon key={scale} points={pts} fill="none" stroke="#1e293b" strokeWidth="1" />
  })

  const axes = angles.map((a, i) => (
    <line key={i} x1={cx} y1={cy} x2={cx + r * Math.cos(a)} y2={cy + r * Math.sin(a)} stroke="#334155" strokeWidth="1" />
  ))

  const dataPoints = metrics.map((m, i) => {
    const v = Math.max(0, Math.min(100, Number(m.score) || 0)) / 100
    return `${cx + r * v * Math.cos(angles[i])},${cy + r * v * Math.sin(angles[i])}`
  }).join(" ")

  const dots = metrics.map((m, i) => {
    const v = Math.max(0, Math.min(100, Number(m.score) || 0)) / 100
    return <circle key={i} cx={cx + r * v * Math.cos(angles[i])} cy={cy + r * v * Math.sin(angles[i])} r="3" fill="#22d3ee" />
  })

  const labels = metrics.map((m, i) => {
    const labelR = r * 1.28
    const x = cx + labelR * Math.cos(angles[i])
    const y = cy + labelR * Math.sin(angles[i])
    const anchor = Math.cos(angles[i]) > 0.15 ? "start" : Math.cos(angles[i]) < -0.15 ? "end" : "middle"
    const shortName = m.name.length > 14 ? m.name.slice(0, 12) + "…" : m.name
    return (
      <text key={i} x={x} y={y} textAnchor={anchor} fontSize="9.5" fill="#94a3b8" dominantBaseline="middle">
        {shortName}
      </text>
    )
  })

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="mx-auto block">
      {rings}
      {axes}
      <polygon points={dataPoints} fill="rgba(34,211,238,0.12)" stroke="#22d3ee" strokeWidth="1.5" />
      {dots}
      {labels}
    </svg>
  )
}

function MetricCard({ metric }) {
  const score = Math.max(0, Math.min(100, Number(metric.score) || 0))
  const { bar, text } = scoreColor(score)
  return (
    <motion.div className="report-pop-card rounded border border-slate-800 bg-slate-950 p-3" whileHover={{ y: -4, scale: 1.015 }} transition={{ type: "spring", stiffness: 320, damping: 22 }}>
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm font-semibold text-slate-200 leading-5">{metric.name}</div>
        <div className={`text-lg font-bold shrink-0 ${text}`}>{score}</div>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <div className="flex-1 h-1.5 rounded bg-slate-800">
          <div className={`h-1.5 rounded ${bar} transition-all`} style={{ width: `${score}%` }} />
        </div>
        {metric.label && <span className={`text-xs font-semibold shrink-0 ${labelColor(metric.label)}`}>{metric.label}</span>}
      </div>
      {metric.note && <p className="mt-2 text-[13px] leading-relaxed text-slate-400 font-medium">{metric.note}</p>}
    </motion.div>
  )
}

function VerdictCard({ verdict, overallScore }) {
  const signal = verdict?.signal || ""
  const { bg, border, text, dot } = verdictColors(signal)
  const confidence = Math.max(0, Math.min(100, Number(verdict?.confidence_score) || 0))
  const { bar: confBar } = scoreColor(confidence)
  return (
    <motion.div className={`verdict-glow rounded border-2 ${border} ${bg} p-5`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-widest text-slate-400 mb-1 font-semibold">Final Verdict</div>
          <div className="flex items-center gap-2">
            <div className={`h-3 w-3 rounded-full ${dot}`} />
            <span className={`text-xl font-bold ${text}`}>{signal || "Pending"}</span>
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className={`text-4xl font-bold ${text}`}>{Math.round(Number(overallScore) || 0)}</div>
          <div className="text-xs text-slate-500">overall</div>
        </div>
      </div>
      <div className="mt-3">
        <div className="flex items-center justify-between text-xs text-slate-400 mb-1 font-semibold">
          <span>Confidence</span><span>{confidence}%</span>
        </div>
        <div className="h-1.5 rounded bg-slate-800">
          <div className={`h-1.5 rounded ${confBar}`} style={{ width: `${confidence}%` }} />
        </div>
      </div>
      {verdict?.summary && <p className="mt-3 text-sm leading-relaxed text-slate-300 font-medium">{verdict.summary}</p>}
      {(verdict?.biggest_strength || verdict?.biggest_weakness || verdict?.most_important_next_step) && (
        <div className="mt-3 grid gap-2">
          {verdict.biggest_strength && (
            <div className="rounded bg-emerald-950/50 border border-emerald-800/40 px-3 py-2 text-[13px] leading-relaxed text-emerald-200 font-medium">
              <span className="font-semibold text-emerald-400">Top strength: </span>{verdict.biggest_strength}
            </div>
          )}
          {verdict.biggest_weakness && (
            <div className="rounded bg-amber-950/50 border border-amber-800/40 px-3 py-2 text-[13px] leading-relaxed text-amber-200 font-medium">
              <span className="font-semibold text-amber-400">Key gap: </span>{verdict.biggest_weakness}
            </div>
          )}
          {verdict.most_important_next_step && (
            <div className="rounded bg-blue-950/50 border border-blue-800/40 px-3 py-2 text-[13px] leading-relaxed text-blue-200 font-medium">
              <span className="font-semibold text-blue-400">Priority action: </span>{verdict.most_important_next_step}
            </div>
          )}
        </div>
      )}
    </motion.div>
  )
}

function DSAReportStat({ label, value, helper, tone = "cyan" }) {
  const tones = {
    cyan: "from-cyan-500/20 text-cyan-200 border-cyan-400/30",
    emerald: "from-emerald-500/20 text-emerald-200 border-emerald-400/30",
    amber: "from-amber-500/20 text-amber-200 border-amber-400/30",
    rose: "from-rose-500/20 text-rose-200 border-rose-400/30",
  }
  return (
    <motion.div className={`report-pop-card rounded border bg-gradient-to-br ${tones[tone] || tones.cyan} to-slate-950/80 p-4`} whileHover={{ y: -5, scale: 1.02 }}>
      <div className="text-xs uppercase tracking-wide text-slate-400 font-semibold">{label}</div>
      <div className="mt-2 text-3xl font-bold text-white">{value}</div>
      {helper && <div className="mt-1.5 text-[13px] leading-relaxed text-slate-400 font-medium">{helper}</div>}
    </motion.div>
  )
}

function WeaknessCard({ weakness }) {
  return (
    <div className="rounded border border-amber-800/30 bg-amber-950/20 p-4">
      <div className="flex items-center gap-2 mb-3">
        <div className="h-2 w-2 rounded-full bg-amber-400 shrink-0" />
        <h4 className="text-sm font-semibold text-amber-200">{weakness.area}</h4>
      </div>
      {weakness.specific_issue && (
        <p className="text-sm leading-6 text-slate-300 mb-2">{weakness.specific_issue}</p>
      )}
      <div className="grid gap-2 mt-2">
        {weakness.why_it_matters && (
          <div className="rounded bg-slate-900 px-3 py-2 text-xs leading-5 text-slate-400">
            <span className="font-semibold text-slate-300">Why it matters: </span>{weakness.why_it_matters}
          </div>
        )}
        {weakness.improvement && (
          <div className="rounded bg-slate-900 px-3 py-2 text-xs leading-5 text-cyan-200">
            <span className="font-semibold text-cyan-400">Fix: </span>{weakness.improvement}
          </div>
        )}
      </div>
    </div>
  )
}

function StrengthCard({ strength }) {
  return (
    <div className="rounded border border-emerald-800/30 bg-emerald-950/20 p-4">
      <div className="flex items-center gap-2 mb-2">
        <div className="h-2 w-2 rounded-full bg-emerald-400 shrink-0" />
        <h4 className="text-sm font-semibold text-emerald-200">{strength.strength}</h4>
      </div>
      {strength.evidence && <p className="text-xs leading-5 text-slate-400 mb-1">{strength.evidence}</p>}
      {strength.interview_value && (
        <div className="mt-1 rounded bg-slate-900 px-2 py-1 text-xs text-emerald-300">
          <span className="font-semibold">Interview value: </span>{strength.interview_value}
        </div>
      )}
    </div>
  )
}

function BehaviorCoachCard({ item }) {
  return (
    <div className="rounded border border-blue-800/30 bg-blue-950/20 p-4">
      <div className="mb-2">
        <span className="rounded bg-blue-900/60 px-2 py-0.5 text-xs font-medium text-blue-300">Observed</span>
      </div>
      <p className="text-sm font-medium text-slate-200 mb-2">{item.observation}</p>
      {item.impact && <p className="text-xs leading-5 text-slate-400 mb-2"><span className="font-semibold text-slate-300">Impact: </span>{item.impact}</p>}
      {item.coaching && (
        <div className="rounded bg-slate-900 px-3 py-2 text-xs leading-5 text-blue-200">
          <span className="font-semibold text-blue-400">Coach says: </span>{item.coaching}
        </div>
      )}
    </div>
  )
}

function RecommendationCard({ rec }) {
  const priorityStyle = { high: "bg-red-900/60 text-red-300", medium: "bg-amber-900/60 text-amber-300", low: "bg-slate-800 text-slate-400" }
  const catStyle = { "Practice Patterns": "text-cyan-400", "Interview Habits": "text-blue-400", "Optimization Strategy": "text-emerald-400", "Debugging Strategy": "text-amber-400", "Communication": "text-purple-400", "Edge Case Handling": "text-pink-400" }
  return (
    <div className="rounded border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${priorityStyle[rec.priority] || priorityStyle.low}`}>{rec.priority || "medium"}</span>
        <span className={`text-xs font-medium ${catStyle[rec.category] || "text-slate-400"}`}>{rec.category}</span>
      </div>
      <p className="text-sm leading-6 text-slate-300">{rec.recommendation}</p>
    </div>
  )
}

function QuestionPerformanceCard({ qp }) {
  const verdictColor = {
    Solved: "text-emerald-400 bg-emerald-950",
    Partial: "text-cyan-400 bg-cyan-950",
    Explained: "text-blue-400 bg-blue-950",
    Incorrect: "text-amber-400 bg-amber-950",
    "Not attempted": "text-red-400 bg-red-950",
    Strong: "text-emerald-400 bg-emerald-950",
    Satisfactory: "text-blue-400 bg-blue-950",
    "Needs Work": "text-amber-400 bg-amber-950",
    Weak: "text-red-400 bg-red-950",
  }
  const vc = verdictColor[qp.verdict] || verdictColor["Needs Work"]
  const metrics = qp.metrics || {}
  const bars = [
    { label: "Code Accuracy", val: metrics.code_correctness ?? metrics.implementation ?? 0 },
    { label: "Approach", val: metrics.explanation_credit ?? metrics.approach_quality ?? 0 },
    { label: "Communication", val: metrics.communication || 0 },
  ]
  return (
    <motion.div className="report-pop-card rounded-2xl border border-slate-700 bg-slate-900 p-5" whileHover={{ y: -4, scale: 1.01 }}>
      <div className="flex items-start justify-between mb-4">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Question {qp.question_index}</span>
          {qp.problem_excerpt && <p className="text-[13px] font-medium leading-relaxed text-slate-400 mt-1 line-clamp-2">{qp.problem_excerpt}</p>}
        </div>
        <div className="flex flex-col items-end gap-1.5 ml-3 shrink-0">
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${vc}`}>{qp.verdict}</span>
          <span className="text-xl font-extrabold text-slate-100">{qp.overall_score}<span className="text-xs font-semibold text-slate-500">/100</span></span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-3">
        {bars.map(({ label, val }) => {
          const { bar, text } = scoreColor(val)
          return (
            <div key={label}>
              <div className="flex justify-between text-[13px] font-semibold mb-1"><span className="text-slate-400">{label}</span><span className={text}>{val}</span></div>
              <div className="h-2 rounded-full bg-slate-800"><div className={`h-2 rounded-full ${bar}`} style={{ width: `${val}%` }} /></div>
            </div>
          )
        })}
      </div>
      {(qp.hints_used > 0 || (qp.followups_asked || []).length > 0) && (
        <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-800/60 pt-3">
          {qp.hints_used > 0 && <span className="rounded-full bg-amber-950/20 border border-amber-800/30 px-2.5 py-1 text-xs font-semibold text-amber-200">{qp.hints_used} hint{qp.hints_used !== 1 ? "s" : ""} used</span>}
          {(qp.followups_asked || []).slice(0, 1).map((f, i) => <span key={i} className="rounded-full bg-slate-850 px-2.5 py-1 text-xs font-semibold text-slate-300 max-w-xs truncate">{f}</span>)}
        </div>
      )}
    </motion.div>
  )
}

function AdvancedMetricCard({ title, score, children }) {
  const { bar, text } = scoreColor(Math.max(0, Math.min(100, Number(score) || 0)))
  const s = Math.max(0, Math.min(100, Number(score) || 0))
  return (
    <div className="rounded border border-slate-800 bg-slate-950 p-4">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-sm font-semibold text-slate-200">{title}</h4>
        <span className={`text-lg font-bold ${text}`}>{s}</span>
      </div>
      <div className="h-1.5 rounded bg-slate-800 mb-3">
        <div className={`h-1.5 rounded ${bar}`} style={{ width: `${s}%` }} />
      </div>
      {children}
    </div>
  )
}

function BenchmarkRow({ comparison }) {
  const c = Math.max(0, Math.min(100, Number(comparison.candidate_score) || 0))
  const f = Math.max(0, Math.min(100, Number(comparison.faang_bar) || 0))
  const { bar: cBar } = scoreColor(c)
  return (
    <div className="rounded border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-slate-200">{comparison.metric}</span>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-cyan-300 font-medium">You: {c}</span>
          <span className="text-slate-500">Bar: {f}</span>
        </div>
      </div>
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="w-10 text-xs text-slate-500 shrink-0">You</span>
          <div className="flex-1 h-2 rounded bg-slate-800">
            <div className={`h-2 rounded ${cBar}`} style={{ width: `${c}%` }} />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-10 text-xs text-slate-500 shrink-0">Bar</span>
          <div className="flex-1 h-2 rounded bg-slate-800">
            <div className="h-2 rounded bg-slate-600" style={{ width: `${f}%` }} />
          </div>
        </div>
      </div>
      {comparison.gap_note && <p className="mt-2 text-xs leading-5 text-slate-400">{comparison.gap_note}</p>}
    </div>
  )
}

function LearningPlanSection({ plan }) {
  const [tab, setTab] = useState("week1")
  if (!plan || (!plan.one_week && !plan.two_week)) return null
  const week1 = plan.one_week || {}
  const week2 = plan.two_week || {}
  const current = tab === "week1" ? week1 : week2
  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-5">
      <h2 className="mb-4 text-base font-semibold text-slate-100">Personalized Learning Plan</h2>
      <div className="flex gap-2 mb-4">
        <button onClick={() => setTab("week1")} className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${tab === "week1" ? "bg-cyan-500 text-slate-950" : "border border-slate-700 text-slate-400 hover:text-slate-200"}`}>Week 1</button>
        <button onClick={() => setTab("week2")} className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${tab === "week2" ? "bg-cyan-500 text-slate-950" : "border border-slate-700 text-slate-400 hover:text-slate-200"}`}>Week 2</button>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {current.daily_goals?.length > 0 && (
          <div>
            <h3 className="text-xs uppercase text-cyan-400 mb-2 font-semibold tracking-wide">Daily Goals</h3>
            <ul className="space-y-1.5">
              {current.daily_goals.map((g, i) => (
                <li key={i} className="flex gap-2 text-xs leading-5 text-slate-300">
                  <span className="shrink-0 text-cyan-500 font-bold">{i + 1}.</span>{g}
                </li>
              ))}
            </ul>
          </div>
        )}
        {current.focus_topics?.length > 0 && (
          <div>
            <h3 className="text-xs uppercase text-emerald-400 mb-2 font-semibold tracking-wide">Focus Topics</h3>
            <div className="flex flex-wrap gap-1.5">
              {current.focus_topics.map((t, i) => (
                <span key={i} className="rounded bg-emerald-900/40 border border-emerald-800/40 px-2 py-0.5 text-xs text-emerald-200">{t}</span>
              ))}
            </div>
          </div>
        )}
        {current.problem_types?.length > 0 && (
          <div>
            <h3 className="text-xs uppercase text-blue-400 mb-2 font-semibold tracking-wide">Problem Types</h3>
            <div className="flex flex-wrap gap-1.5">
              {current.problem_types.map((p, i) => (
                <span key={i} className="rounded bg-blue-900/40 border border-blue-800/40 px-2 py-0.5 text-xs text-blue-200">{p}</span>
              ))}
            </div>
          </div>
        )}
      </div>
      {plan.recommended_problems?.length > 0 && (
        <div className="mt-4 border-t border-slate-800 pt-4">
          <h3 className="text-xs uppercase text-amber-400 mb-2 font-semibold tracking-wide">Recommended Problem Patterns</h3>
          <div className="flex flex-wrap gap-2">
            {plan.recommended_problems.map((p, i) => (
              <span key={i} className="rounded bg-amber-900/30 border border-amber-800/30 px-2.5 py-1 text-xs text-amber-200">{p}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function DSAFeedback({ report, onRestart, onBack }) {
  const ev = (report.dsa_evaluation && report.dsa_evaluation.final_verdict)
    ? report.dsa_evaluation
    : {}
  const verdict = ev.final_verdict || {}
  const ct = ev.company_tailored || {}
  const adv = ev.advanced_metrics || {}
  const breakdown = report.round_breakdown || {}
  const integrity = report.integrity || {}
  const basis = breakdown.scoring_basis || {}
  const solved = basis.solved_questions ?? 0
  const assigned = basis.total_questions ?? 1
  const missingRuns = basis.missing_code_runs ?? 0
  const integrityEvents = integrity.violations?.length || 0
  const simpleMetrics = ev.core_metrics || []
  const metricScore = (name) => simpleMetrics.find((m) => m.name === name)?.score ?? 0
  const strongTopics = ev.strong_dsa_topics || []
  const weakTopics = ev.weak_dsa_topics || []

  return (
    <main className="dashboard-shell dsa-report-shell min-h-screen text-slate-100 codevoir-dashboard-page">
      <section className="relative z-20 bg-gradient-to-r from-[#004182] to-[#0a66c2] shadow-md border-b border-[#003366]">
        <div className="mx-auto w-full max-w-[95%] xl:max-w-[1400px] flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            {onBack && (
              <button onClick={onBack} className="inline-flex items-center gap-2 rounded-lg bg-white/10 hover:bg-white/20 border border-white/20 px-4 py-2 text-sm font-semibold text-white transition-all">
                <ArrowLeft size={16} /> Back to dashboard
              </button>
            )}
          </div>
        </div>
      </section>
      <BackgroundCanvas />
      <div className="relative z-10 mx-auto w-full max-w-[95%] xl:max-w-[1400px] px-4 md:px-6 py-8">

        {/* Header */}
        <motion.div className="report-hero mb-6 flex flex-col md:flex-row items-stretch justify-between gap-6 rounded border border-cyan-300/20 p-6" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
          <div className="flex-1 min-w-0 flex flex-col justify-center">
            <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-cyan-400 mb-2 font-bold">
              <span>Overall Evaluation Summary</span>
            </div>
            <h1 className="text-xl md:text-2xl font-bold tracking-tight text-slate-100 mb-2">
              {report.target_company ? `${report.target_company} — ` : ""}DSA Round Report
            </h1>
            {breakdown.problem && (
              <div className="flex flex-wrap items-center gap-3 text-xs md:text-sm text-slate-500 font-semibold mb-3">
                <span className="capitalize text-slate-700">{breakdown.problem.difficulty || "medium"} difficulty</span>
                {breakdown.problem.topics?.length > 0 && (
                  <>
                    <span className="text-slate-400">·</span>
                    <span className="text-slate-600">Topics: {breakdown.problem.topics.slice(0, 3).join(", ")}</span>
                  </>
                )}
                {breakdown.submission?.total_testcases > 0 && (
                  <>
                    <span className="text-slate-400">·</span>
                    <span className={breakdown.submission.passed_testcases === breakdown.submission.total_testcases ? "text-emerald-600" : "text-amber-600"}>
                      {breakdown.submission.passed_testcases}/{breakdown.submission.total_testcases} tests passed
                    </span>
                  </>
                )}
              </div>
            )}
            <p className="mt-1 max-w-3xl text-sm md:text-[15px] leading-relaxed text-slate-300 font-medium">{report.summary || verdict.summary}</p>
            {report.skill_gap && (
              <div className="mt-3 rounded border border-amber-700/30 bg-amber-950/20 px-3 py-2 text-xs md:text-sm leading-5 text-amber-200 max-w-2xl font-medium">
                <span className="font-semibold text-amber-400">Key skill gap: </span>{report.skill_gap}
              </div>
            )}
          </div>
          <div className="hidden lg:flex items-center justify-center shrink-0 w-56 p-1">
            <div className="h-28 w-full rounded-xl overflow-hidden border border-slate-200/60 bg-white/40 shadow-[0_4px_20px_rgba(0,0,0,0.05)] backdrop-blur-sm">
              <img src="/report_illustration.png" alt="Evaluation graph" className="h-full w-full object-cover" />
            </div>
          </div>
        </motion.div>

        <motion.div className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4" initial="hidden" animate="show" variants={dashboardStagger}>
          <DSAReportStat label="Overall score" value={`${Math.round(Number(report.overall_score) || 0)}/100`} helper="Correct code first; tab switches can reduce it." tone="cyan" />
          <DSAReportStat label="Coding solved" value={`${solved}/${assigned}`} helper="Questions with all testcases passed." tone="emerald" />
          <DSAReportStat label="Concept clarity" value={`${metricScore("Concept Clarity")}/100`} helper="Approach and DSA understanding." tone="cyan" />
          <DSAReportStat label="Integrity" value={`${integrity.score ?? 100}/100`} helper={`${integrityEvents} event${integrityEvents === 1 ? "" : "s"} shown separately.`} tone={integrityEvents ? "amber" : "emerald"} />
        </motion.div>

        {/* Main two-column layout */}
        <div className="grid gap-6 lg:grid-cols-[1fr_380px]">

          {/* Left column */}
          <div className="space-y-6">

            {/* Core metrics */}
            {ev.core_metrics?.length > 0 && (
              <motion.div className="report-panel rounded border border-slate-800 bg-slate-900 p-5" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                <h2 className="font-display mb-4 text-xl font-semibold text-slate-100">Core Result Fields</h2>
                <div className="grid gap-3 sm:grid-cols-2">
                  {ev.core_metrics.map((m) => <MetricCard key={m.name} metric={m} />)}
                </div>
              </motion.div>
            )}

            <div className="grid gap-4 md:grid-cols-2">
              <div className="report-panel rounded border border-slate-800 bg-slate-900 p-5">
                <h2 className="font-display text-lg font-semibold text-slate-100">Strong DSA Topics</h2>
                <div className="mt-4 flex flex-wrap gap-2">
                  {strongTopics.length ? strongTopics.map((topic) => <span key={topic} className="rounded border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-sm font-medium text-emerald-200">{topic}</span>) : <span className="text-sm text-slate-500">No clear strong topic signal yet.</span>}
                </div>
              </div>
              <div className="report-panel rounded border border-slate-800 bg-slate-900 p-5">
                <h2 className="font-display text-lg font-semibold text-slate-100">Weak DSA Topics</h2>
                <div className="mt-4 flex flex-wrap gap-2">
                  {weakTopics.length ? weakTopics.map((topic) => <span key={topic} className="rounded border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-sm font-medium text-amber-200">{topic}</span>) : <span className="text-sm text-slate-500">No weak topic signal yet.</span>}
                </div>
              </div>
            </div>

            {/* Advanced metrics */}
            {false && adv.company_fit && (
              <motion.div className="report-panel rounded border border-slate-800 bg-slate-900 p-5" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                <h2 className="mb-4 text-base font-semibold text-slate-100">Company Fit Analysis</h2>
                <AdvancedMetricCard title="Company Fit" score={adv.company_fit.score}>
                  <p className="text-xs leading-5 text-slate-400 mb-2">{adv.company_fit.note}</p>
                  <div className="space-y-1">
                    {adv.company_fit.fit_signals?.slice(0, 3).map((s, i) => (
                      <div key={i} className="flex gap-1 text-xs text-emerald-300"><span>+</span>{s}</div>
                    ))}
                    {adv.company_fit.concern_signals?.slice(0, 3).map((s, i) => (
                      <div key={i} className="flex gap-1 text-xs text-amber-300"><span>−</span>{s}</div>
                    ))}
                  </div>
                </AdvancedMetricCard>
              </motion.div>
            )}

            {/* Company-tailored */}
            {false && ct.company && (
              <motion.div className="report-panel rounded border border-slate-800 bg-slate-900 p-5" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-base font-semibold text-slate-100">{ct.company} — Company-Tailored Evaluation</h2>
                  {ct.bar_assessment && (
                    <span className={`rounded px-2.5 py-1 text-xs font-semibold ${ct.bar_assessment === "Above Bar" ? "bg-emerald-900 text-emerald-300" : ct.bar_assessment === "At Bar" ? "bg-cyan-900 text-cyan-300" : ct.bar_assessment === "Approaching Bar" ? "bg-amber-900 text-amber-300" : "bg-red-900 text-red-300"}`}>
                      {ct.bar_assessment}
                    </span>
                  )}
                </div>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {[
                    ["Optimization Quality", ct.optimization_quality],
                    ["Communication Clarity", ct.communication_clarity],
                    ["Follow-up Handling", ct.followup_handling],
                    ["Coding Speed", ct.coding_speed],
                    ["Debugging Behavior", ct.debugging_behavior],
                  ].filter(([, v]) => v).map(([label, val]) => (
                    <div key={label} className="rounded border border-slate-800 bg-slate-950 p-3">
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs font-medium text-slate-300">{label}</span>
                        <span className={`text-base font-bold ${scoreColor(Number(val.score) || 0).text}`}>{Math.max(0, Math.min(100, Number(val.score) || 0))}</span>
                      </div>
                      <div className="h-1 rounded bg-slate-800 mb-2">
                        <div className={`h-1 rounded ${scoreColor(Number(val.score) || 0).bar}`} style={{ width: `${Math.max(0, Math.min(100, Number(val.score) || 0))}%` }} />
                      </div>
                      <p className="text-xs leading-5 text-slate-400">{val.note}</p>
                    </div>
                  ))}
                </div>
                {ct.summary && (
                  <div className="mt-4 rounded border border-slate-700 bg-slate-950 px-4 py-3 text-sm leading-6 text-slate-300">
                    {ct.summary}
                  </div>
                )}
              </motion.div>
            )}

            {/* Benchmarking */}
            {false && ev.benchmarking && (
              <div className="rounded border border-slate-800 bg-slate-900 p-5">
                <div className="flex items-start justify-between mb-4 gap-4">
                  <h2 className="text-base font-semibold text-slate-100">Comparative Benchmarking</h2>
                  <div className="text-right shrink-0">
                    <div className={`text-2xl font-bold ${scoreColor(ev.benchmarking.faang_readiness_score || 0).text}`}>
                      {ev.benchmarking.faang_readiness_score || 0}
                    </div>
                    <div className="text-xs text-slate-500">FAANG readiness</div>
                    {ev.benchmarking.estimated_level && (
                      <div className="mt-0.5 text-xs font-medium text-slate-400">{ev.benchmarking.estimated_level}</div>
                    )}
                  </div>
                </div>
                {ev.benchmarking.overall_readiness_note && (
                  <p className="text-sm leading-6 text-slate-400 mb-4">{ev.benchmarking.overall_readiness_note}</p>
                )}
                <div className="grid gap-2 sm:grid-cols-2">
                  {(ev.benchmarking.comparisons || []).map((c, i) => <BenchmarkRow key={i} comparison={c} />)}
                </div>
              </div>
            )}

            {/* Topic mastery heatmap */}
            {false && report.topic_mastery?.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-5">
                <h2 className="mb-4 text-base font-semibold text-slate-100">Topic Mastery</h2>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {report.topic_mastery.map((t) => <ParameterCard key={t.topic} param={{ name: t.topic, score: t.mastery, note: t.note }} />)}
                </div>
              </div>
            )}

          </div>

          {/* Right column */}
          <div className="space-y-5">
            <VerdictCard verdict={verdict} overallScore={report.overall_score} />

            {false && ev.weakness_analysis?.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-4">
                <h2 className="mb-3 text-sm font-semibold text-slate-100 uppercase tracking-wide">Weakness Analysis</h2>
                <div className="space-y-3">
                  {ev.weakness_analysis.map((w, i) => <WeaknessCard key={i} weakness={w} />)}
                </div>
              </div>
            )}

            {false && ev.strength_recognition?.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-4">
                <h2 className="mb-3 text-sm font-semibold text-slate-100 uppercase tracking-wide">Strengths Recognized</h2>
                <div className="space-y-3">
                  {ev.strength_recognition.map((s, i) => <StrengthCard key={i} strength={s} />)}
                </div>
              </div>
            )}

            {false && ev.behavior_coaching?.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-4">
                <h2 className="mb-3 text-sm font-semibold text-slate-100 uppercase tracking-wide">Behavior Coaching</h2>
                <div className="space-y-3">
                  {ev.behavior_coaching.map((item, i) => <BehaviorCoachCard key={i} item={item} />)}
                </div>
              </div>
            )}

            {/* Integrity */}
            <div className="rounded border border-slate-800 bg-slate-900 p-4">
              <h2 className="mb-3 text-sm font-semibold text-slate-100 uppercase tracking-wide">Integrity</h2>
              <div className={`text-3xl font-bold mb-1 ${scoreColor(integrity.score ?? 100).text}`}>{integrity.score ?? 100}<span className="text-sm text-slate-500">/100</span></div>
              <div className="grid gap-1 text-xs text-slate-400">
                <span>{integrity.violations?.length || 0} proctoring event{integrity.violations?.length !== 1 ? "s" : ""}</span>
                <span>Tab switches: {integrity.focus_loss || 0}</span>
                <span>Paste events: {integrity.paste_events || 0}</span>
                {integrity.large_pastes > 0 && <span className="text-amber-400">Large pastes: {integrity.large_pastes}</span>}
              </div>
            </div>
          </div>
        </div>

        {/* Full-width bottom sections */}
        <div className="mt-6 space-y-6">

          {ev.question_performance?.length > 0 && (
            <div className="rounded border border-slate-800 bg-slate-900 p-5">
              <h2 className="mb-4 text-base font-semibold text-slate-100">Question-wise Performance</h2>
              <div className="grid gap-4 sm:grid-cols-2">
                {ev.question_performance.map((qp, i) => <QuestionPerformanceCard key={i} qp={qp} />)}
              </div>
            </div>
          )}

          {false && ev.improvement_recommendations?.length > 0 && (
            <div className="rounded border border-slate-800 bg-slate-900 p-5">
              <h2 className="mb-4 text-base font-semibold text-slate-100">Improvement Recommendations</h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {ev.improvement_recommendations.map((rec, i) => <RecommendationCard key={i} rec={rec} />)}
              </div>
            </div>
          )}

          {false && <LearningPlanSection plan={ev.learning_plan || {}} />}

          {/* Evidence */}
          {false && breakdown.evidence?.length > 0 && <EvidencePanel evidence={breakdown.evidence} />}

        </div>

        <button onClick={onRestart} className="mt-8 rounded bg-cyan-400 px-6 py-3 font-semibold text-slate-950 hover:bg-cyan-300 transition-colors">
          Start Another Interview
        </button>
      </div>
    </main>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// CS FUNDAMENTALS REPORT COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────

function depthStyle(level) {
  if (!level) return { bg: "bg-slate-900", text: "text-slate-400", border: "border-slate-700" }
  const l = String(level).toLowerCase()
  if (l === "expert") return { bg: "bg-emerald-950/50", text: "text-emerald-300", border: "border-emerald-800/50" }
  if (l === "practical") return { bg: "bg-cyan-950/50", text: "text-cyan-300", border: "border-cyan-800/50" }
  if (l === "theoretical") return { bg: "bg-blue-950/50", text: "text-blue-300", border: "border-blue-800/50" }
  return { bg: "bg-amber-950/50", text: "text-amber-300", border: "border-amber-800/50" }
}

function severityStyle(severity) {
  const s = String(severity || "").toLowerCase()
  if (s === "critical") return { bg: "bg-red-950/60", border: "border-red-700/40", badge: "bg-red-900/80 text-red-300", text: "text-red-200" }
  if (s === "moderate") return { bg: "bg-amber-950/60", border: "border-amber-700/40", badge: "bg-amber-900/80 text-amber-300", text: "text-amber-200" }
  return { bg: "bg-slate-900", border: "border-slate-700", badge: "bg-slate-800 text-slate-400", text: "text-slate-300" }
}

function followUpPatternStyle(pattern) {
  const p = String(pattern || "").toLowerCase()
  if (p.includes("consistently_strong")) return "text-emerald-300"
  if (p.includes("improved")) return "text-cyan-300"
  if (p.includes("degraded")) return "text-amber-300"
  if (p.includes("collapsed")) return "text-red-300"
  return "text-slate-400"
}

function balanceLabel(balance) {
  const map = { "Heavy_Theory": "Heavy Theory", "Theory_Leaning": "Theory-Leaning", "Balanced": "Balanced", "Practice_Leaning": "Practice-Leaning", "Heavy_Practice": "Heavy Practice" }
  return map[balance] || balance || "—"
}

function TopicProfileCard({ topic }) {
  const { bg, text, border } = depthStyle(topic.depth_level)
  const score = Math.max(0, Math.min(100, Number(topic.score) || 0))
  const { bar } = scoreColor(score)
  return (
    <div className={`rounded border ${border} ${bg} p-4`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <h4 className="text-sm font-semibold text-slate-100">{topic.topic}</h4>
          {topic.depth_level && <span className={`text-xs font-medium ${text}`}>{topic.depth_level}</span>}
        </div>
        <div className={`text-xl font-bold shrink-0 ${scoreColor(score).text}`}>{score}</div>
      </div>
      <div className="h-1.5 rounded bg-slate-800 mb-3">
        <div className={`h-1.5 rounded ${bar}`} style={{ width: `${score}%` }} />
      </div>
      {topic.highlight && (
        <div className="mb-2 rounded bg-emerald-950/40 border border-emerald-800/30 px-2 py-1.5 text-xs leading-5 text-emerald-200">
          <span className="font-semibold text-emerald-400">Strong: </span>{topic.highlight}
        </div>
      )}
      {topic.gap && (
        <div className="mb-2 rounded bg-amber-950/40 border border-amber-800/30 px-2 py-1.5 text-xs leading-5 text-amber-200">
          <span className="font-semibold text-amber-400">Gap: </span>{topic.gap}
        </div>
      )}
      {topic.misconceptions_detected?.length > 0 && (
        <div className="mb-2">
          {topic.misconceptions_detected.map((m, i) => (
            <div key={i} className="flex gap-1.5 text-xs leading-5 text-red-300">
              <span className="shrink-0 font-bold text-red-400">⚠</span>{m}
            </div>
          ))}
        </div>
      )}
      {topic.coaching && (
        <div className="rounded bg-slate-900 px-2 py-1.5 text-xs leading-5 text-blue-200">
          <span className="font-semibold text-blue-400">Coach: </span>{topic.coaching}
        </div>
      )}
    </div>
  )
}

function MisconceptionCard({ item }) {
  const { bg, border, badge, text } = severityStyle(item.severity)
  return (
    <div className={`rounded border ${border} ${bg} p-4`}>
      <div className="flex items-center gap-2 mb-3">
        <span className={`rounded px-2 py-0.5 text-xs font-semibold ${badge}`}>{item.severity || "Minor"}</span>
        <h4 className="text-sm font-semibold text-slate-100">{item.concept}</h4>
      </div>
      {item.what_was_said && (
        <div className="mb-2">
          <div className="text-xs font-semibold text-slate-500 mb-1">What was said</div>
          <p className={`text-xs leading-5 italic ${text}`}>"{item.what_was_said}"</p>
        </div>
      )}
      {item.what_is_correct && (
        <div className="mb-2 rounded bg-slate-900 px-3 py-2 text-xs leading-5 text-slate-300">
          <span className="font-semibold text-emerald-400">Correct: </span>{item.what_is_correct}
        </div>
      )}
      {item.interview_impact && (
        <p className="text-xs leading-5 text-slate-400"><span className="font-semibold text-slate-300">Interviewer reads this as: </span>{item.interview_impact}</p>
      )}
    </div>
  )
}

function FollowUpPanel({ analysis }) {
  if (!analysis) return null
  const score = Math.max(0, Math.min(100, Number(analysis.score) || 0))
  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-100">Follow-Up Resilience</h3>
        <div className="flex items-center gap-2">
          {analysis.pattern && <span className={`text-xs font-medium ${followUpPatternStyle(analysis.pattern)}`}>{analysis.pattern.replaceAll("_", " ")}</span>}
          <span className={`text-lg font-bold ${scoreColor(score).text}`}>{score}</span>
        </div>
      </div>
      <div className="h-1.5 rounded bg-slate-800 mb-3">
        <div className={`h-1.5 rounded ${scoreColor(score).bar}`} style={{ width: `${score}%` }} />
      </div>
      {analysis.observations?.length > 0 && (
        <div className="space-y-1.5 mb-3">
          {analysis.observations.map((obs, i) => (
            <div key={i} className="flex gap-2 text-xs leading-5 text-slate-300">
              <span className="shrink-0 text-slate-500">→</span>{obs}
            </div>
          ))}
        </div>
      )}
      {analysis.coaching && (
        <div className="rounded bg-blue-950/40 border border-blue-800/30 px-3 py-2 text-xs leading-5 text-blue-200">
          <span className="font-semibold text-blue-400">Coach: </span>{analysis.coaching}
        </div>
      )}
    </div>
  )
}

function EngineeringIntuitionPanel({ intuition }) {
  if (!intuition) return null
  const score = Math.max(0, Math.min(100, Number(intuition.score) || 0))
  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-slate-100">Engineering Intuition</h3>
        <span className={`text-lg font-bold ${scoreColor(score).text}`}>{score}</span>
      </div>
      <div className="h-1.5 rounded bg-slate-800 mb-3">
        <div className={`h-1.5 rounded ${scoreColor(score).bar}`} style={{ width: `${score}%` }} />
      </div>
      {intuition.balance && (
        <div className="mb-3 flex items-center gap-2">
          <span className="text-xs text-slate-500">Balance:</span>
          <span className={`text-xs font-medium ${intuition.balance === "Balanced" ? "text-cyan-300" : intuition.balance?.includes("Practice") ? "text-emerald-300" : "text-amber-300"}`}>
            {balanceLabel(intuition.balance)}
          </span>
        </div>
      )}
      <div className="grid gap-2 sm:grid-cols-2 mb-3">
        {intuition.strong_practical_areas?.length > 0 && (
          <div>
            <div className="text-xs font-semibold text-emerald-400 mb-1.5">Practical intuition shown</div>
            {intuition.strong_practical_areas.map((a, i) => (
              <div key={i} className="flex gap-1 text-xs leading-5 text-emerald-200"><span>+</span>{a}</div>
            ))}
          </div>
        )}
        {intuition.theory_only_areas?.length > 0 && (
          <div>
            <div className="text-xs font-semibold text-amber-400 mb-1.5">Definition-only answers</div>
            {intuition.theory_only_areas.map((a, i) => (
              <div key={i} className="flex gap-1 text-xs leading-5 text-amber-200"><span>−</span>{a}</div>
            ))}
          </div>
        )}
      </div>
      {intuition.coaching && (
        <div className="rounded bg-blue-950/40 border border-blue-800/30 px-3 py-2 text-xs leading-5 text-blue-200">
          <span className="font-semibold text-blue-400">Coach: </span>{intuition.coaching}
        </div>
      )}
    </div>
  )
}

function ExplanationCoachingCard({ item }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="rounded bg-blue-900/50 px-2 py-0.5 text-xs font-medium text-blue-300">{item.topic}</span>
      </div>
      {item.pattern_observed && <p className="text-xs leading-5 text-slate-400 mb-2">{item.pattern_observed}</p>}
      {item.coaching && (
        <div className="rounded bg-slate-900 px-2 py-1.5 text-xs leading-5 text-blue-200">
          <span className="font-semibold text-blue-400">Improve: </span>{item.coaching}
        </div>
      )}
    </div>
  )
}

function CSBenchmarkSection({ benchmarking }) {
  if (!benchmarking) return null
  const score = Math.max(0, Math.min(100, Number(benchmarking.readiness_score) || 0))
  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-5">
      <div className="flex items-start justify-between mb-4 gap-4">
        <h2 className="text-base font-semibold text-slate-100">Benchmarking</h2>
        <div className="text-right shrink-0">
          <div className={`text-2xl font-bold ${scoreColor(score).text}`}>{score}</div>
          <div className="text-xs text-slate-500">readiness</div>
          {benchmarking.level_estimate && <div className="text-xs font-medium text-slate-400">{benchmarking.level_estimate}</div>}
        </div>
      </div>
      {benchmarking.overall_note && <p className="text-sm leading-6 text-slate-400 mb-4">{benchmarking.overall_note}</p>}
      <div className="grid gap-2 sm:grid-cols-2">
        {(benchmarking.comparisons || []).map((c, i) => (
          <div key={i} className="rounded border border-slate-800 bg-slate-950 p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-slate-200">{c.topic}</span>
              <div className="flex items-center gap-2 text-xs">
                <span className={`font-medium ${scoreColor(c.candidate_score || 0).text}`}>You: {c.candidate_score || 0}</span>
                <span className="text-slate-500">Exp: {c.expectation || 0}</span>
              </div>
            </div>
            <div className="space-y-1 mb-2">
              <div className="flex items-center gap-2">
                <span className="w-8 text-xs text-slate-500 shrink-0">You</span>
                <div className="flex-1 h-1.5 rounded bg-slate-800">
                  <div className={`h-1.5 rounded ${scoreColor(c.candidate_score || 0).bar}`} style={{ width: `${c.candidate_score || 0}%` }} />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-8 text-xs text-slate-500 shrink-0">Exp</span>
                <div className="flex-1 h-1.5 rounded bg-slate-800">
                  <div className="h-1.5 rounded bg-slate-600" style={{ width: `${c.expectation || 0}%` }} />
                </div>
              </div>
            </div>
            {c.gap_note && <p className="text-xs leading-5 text-slate-400">{c.gap_note}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}

function CSFeedback({ report, onRestart, onBack }) {
  const ev = report.cs_evaluation || {}
  const verdict = ev.final_verdict || {}
  const breakdown = report.round_breakdown || {}
  const integrity = report.integrity || {}

  return (
    <main className="dashboard-shell min-h-screen text-slate-100 codevoir-dashboard-page">
      <section className="relative z-20 bg-gradient-to-r from-[#004182] to-[#0a66c2] shadow-md border-b border-[#003366]">
        <div className="mx-auto w-full max-w-[95%] xl:max-w-[1400px] flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            {onBack && (
              <button onClick={onBack} className="inline-flex items-center gap-2 rounded-lg bg-white/10 hover:bg-white/20 border border-white/20 px-4 py-2 text-sm font-semibold text-white transition-all">
                <ArrowLeft size={16} /> Back to dashboard
              </button>
            )}
          </div>
        </div>
      </section>
      <BackgroundCanvas />
      <div className="relative z-10 mx-auto w-full max-w-[95%] xl:max-w-[1400px] px-4 md:px-6 py-8">

        {/* Header */}
        <div className="report-hero mb-6 flex flex-col md:flex-row items-stretch justify-between gap-6 rounded border border-cyan-300/20 p-6">
          <div className="flex-1 min-w-0 flex flex-col justify-center">
            <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-widest text-cyan-400 mb-2 font-bold">
              <span>Overall Evaluation Summary</span>
            </div>
            <h1 className="text-xl md:text-2xl font-bold tracking-tight text-slate-100 mb-2">
              {report.target_company ? `${report.target_company} — ` : ""}CS Fundamentals Report
            </h1>
            <p className="mt-1 max-w-3xl text-sm md:text-[15px] leading-relaxed text-slate-300 font-medium">{report.summary || verdict.summary}</p>
            {report.skill_gap && (
              <div className="mt-3 rounded border border-amber-700/30 bg-amber-950/20 px-3 py-2 text-xs md:text-sm leading-5 text-amber-200 max-w-2xl font-medium">
                <span className="font-semibold text-amber-400">Key gap: </span>{report.skill_gap}
              </div>
            )}
          </div>
          <div className="hidden lg:flex items-center justify-center shrink-0 w-56 p-1">
            <div className="h-28 w-full rounded-xl overflow-hidden border border-slate-200/60 bg-white/40 shadow-[0_4px_20px_rgba(0,0,0,0.05)] backdrop-blur-sm">
              <img src="/report_illustration.png" alt="Evaluation graph" className="h-full w-full object-cover" />
            </div>
          </div>
          {breakdown.topics_covered?.length > 0 && (
            <div className="rounded border border-slate-800 bg-slate-900 px-5 py-4 text-sm shrink-0 flex flex-col justify-center">
              <div className="text-slate-500 text-xs mb-1 font-semibold">Topics covered</div>
              <div className="flex flex-wrap gap-1 mt-1">
                {breakdown.topics_covered.map((t) => (
                  <span key={t} className="rounded bg-cyan-900/40 px-2 py-0.5 text-xs text-cyan-300 font-medium">{t}</span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Two-column layout */}
        <div className="grid gap-6 lg:grid-cols-[1fr_380px]">

          {/* Left column */}
          <div className="space-y-6">

            {/* Core metrics */}
            {ev.core_metrics?.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-5">
                <h2 className="mb-4 text-base font-semibold text-slate-100">Core Evaluation Metrics</h2>
                <div className="grid gap-2 sm:grid-cols-2">
                  {ev.core_metrics.map((m) => <MetricCard key={m.name} metric={m} />)}
                </div>
              </div>
            )}

            {/* Topic profiles */}
            {ev.topic_profiles?.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-5">
                <h2 className="mb-4 text-base font-semibold text-slate-100">Topic-by-Topic Breakdown</h2>
                <div className="grid gap-3 sm:grid-cols-2">
                  {ev.topic_profiles.map((t, i) => <TopicProfileCard key={i} topic={t} />)}
                </div>
              </div>
            )}

            {/* Engineering intuition + follow-up */}
            <div className="grid gap-4 sm:grid-cols-2">
              <EngineeringIntuitionPanel intuition={ev.engineering_intuition} />
              <FollowUpPanel analysis={ev.follow_up_analysis} />
            </div>

            {/* Explanation coaching */}
            {ev.explanation_coaching?.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-5">
                <h2 className="mb-4 text-base font-semibold text-slate-100">Explanation Coaching</h2>
                <div className="grid gap-3 sm:grid-cols-2">
                  {ev.explanation_coaching.map((item, i) => <ExplanationCoachingCard key={i} item={item} />)}
                </div>
              </div>
            )}

            <CSBenchmarkSection benchmarking={ev.benchmarking} />

          </div>

          {/* Right column */}
          <div className="space-y-5">
            <VerdictCard verdict={verdict} overallScore={report.overall_score} />

            {ev.misconceptions?.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-4">
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-100">
                  Misconceptions Detected
                  <span className="ml-2 rounded bg-red-900/50 px-1.5 py-0.5 text-xs text-red-300">{ev.misconceptions.length}</span>
                </h2>
                <div className="space-y-3">
                  {ev.misconceptions.map((item, i) => <MisconceptionCard key={i} item={item} />)}
                </div>
              </div>
            )}

            {ev.improvement_recommendations?.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-4">
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-100">Recommendations</h2>
                <div className="space-y-2">
                  {ev.improvement_recommendations.map((rec, i) => <RecommendationCard key={i} rec={rec} />)}
                </div>
              </div>
            )}

            {/* Integrity */}
            <div className="rounded border border-slate-800 bg-slate-900 p-4">
              <h2 className="mb-3 text-sm font-semibold text-slate-100 uppercase tracking-wide">Integrity</h2>
              <div className={`text-3xl font-bold mb-1 ${scoreColor(integrity.score ?? 100).text}`}>{integrity.score ?? 100}<span className="text-sm text-slate-500">/100</span></div>
              <div className="grid gap-1 text-xs text-slate-400">
                <span>{integrity.violations?.length || 0} proctoring event{integrity.violations?.length !== 1 ? "s" : ""}</span>
                <span>Tab switches: {integrity.focus_loss || 0}</span>
              </div>
            </div>
          </div>
        </div>

        <button onClick={onRestart} className="mt-8 rounded bg-cyan-400 px-6 py-3 font-semibold text-slate-950 hover:bg-cyan-300 transition-colors">
          Start Another Interview
        </button>
      </div>
    </main>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PROJECT + BEHAVIORAL REPORT COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────

function ownershipPatternStyle(pattern) {
  const p = String(pattern || "").toLowerCase()
  if (p.includes("strong")) return { text: "text-emerald-300", badge: "bg-emerald-900/60 text-emerald-300" }
  if (p.includes("shared")) return { text: "text-cyan-300", badge: "bg-cyan-900/60 text-cyan-300" }
  if (p.includes("passive")) return { text: "text-amber-300", badge: "bg-amber-900/60 text-amber-300" }
  return { text: "text-red-300", badge: "bg-red-900/60 text-red-300" }
}

function conflictMaturityStyle(level) {
  const l = String(level || "").toLowerCase()
  if (l === "strategic") return "text-emerald-300"
  if (l === "assertive") return "text-cyan-300"
  if (l === "diplomatic") return "text-blue-300"
  return "text-amber-300"
}

function OwnershipPanel({ ownership }) {
  if (!ownership) return null
  const score = Math.max(0, Math.min(100, Number(ownership.ownership_score) || 0))
  const analysis = ownership.ownership_analysis || {}
  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-100">Project Ownership</h3>
        <span className={`text-xl font-bold ${scoreColor(score).text}`}>{score}</span>
      </div>
      <div className="h-1.5 rounded bg-slate-800 mb-4">
        <div className={`h-1.5 rounded ${scoreColor(score).bar}`} style={{ width: `${score}%` }} />
      </div>
      <div className="space-y-2">
        {analysis.strong_signals?.slice(0, 3).map((s, i) => (
          <div key={i} className="flex gap-2 text-xs leading-5 text-emerald-200">
            <span className="shrink-0 font-bold text-emerald-400">+</span>{s}
          </div>
        ))}
        {analysis.weak_signals?.slice(0, 3).map((s, i) => (
          <div key={i} className="flex gap-2 text-xs leading-5 text-amber-200">
            <span className="shrink-0 font-bold text-amber-400">−</span>{s}
          </div>
        ))}
      </div>
      {analysis.overall_note && (
        <p className="mt-3 text-xs leading-5 text-slate-400 border-t border-slate-800 pt-3">{analysis.overall_note}</p>
      )}
    </div>
  )
}

function EngineeringMaturityGrid({ maturity }) {
  if (!maturity) return null
  const indicators = [
    ["Production Thinking", maturity.production_thinking],
    ["Scalability Awareness", maturity.scalability_awareness],
    ["Failure Handling", maturity.failure_handling],
    ["Monitoring & Observability", maturity.monitoring_observability],
    ["Optimization Thinking", maturity.optimization_thinking],
  ].filter(([, v]) => v !== undefined && v !== null)
  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-100">Engineering Maturity</h3>
        <span className={`text-xl font-bold ${scoreColor(Number(maturity.score) || 0).text}`}>{Math.max(0, Math.min(100, Number(maturity.score) || 0))}</span>
      </div>
      <div className="space-y-2 mb-3">
        {indicators.map(([label, val]) => {
          const v = Math.max(0, Math.min(100, Number(val) || 0))
          return (
            <div key={label} className="grid grid-cols-[1fr_auto] items-center gap-2">
              <div>
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-xs text-slate-400">{label}</span>
                  <span className={`text-xs font-medium ${scoreColor(v).text}`}>{v}</span>
                </div>
                <div className="h-1 rounded bg-slate-800">
                  <div className={`h-1 rounded ${scoreColor(v).bar}`} style={{ width: `${v}%` }} />
                </div>
              </div>
            </div>
          )
        })}
      </div>
      {maturity.note && <p className="text-xs leading-5 text-slate-400 border-t border-slate-800 pt-3">{maturity.note}</p>}
    </div>
  )
}

function STARBreakdown({ starAnalysis }) {
  if (!starAnalysis) return null
  const components = [
    ["S — Situation", starAnalysis.situation],
    ["T — Task", starAnalysis.task],
    ["A — Action", starAnalysis.action],
    ["R — Result", starAnalysis.result],
  ]
  const overall = Math.max(0, Math.min(100, Number(starAnalysis.overall_score) || 0))
  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-100">STAR Framework Analysis</h3>
        <span className={`text-xl font-bold ${scoreColor(overall).text}`}>{overall}</span>
      </div>
      <div className="space-y-3">
        {components.map(([label, comp]) => {
          if (!comp) return null
          const s = Math.max(0, Math.min(100, Number(comp.score) || 0))
          return (
            <div key={label}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-slate-300">{label}</span>
                <span className={`text-sm font-bold ${scoreColor(s).text}`}>{s}</span>
              </div>
              <div className="h-1.5 rounded bg-slate-800 mb-1">
                <div className={`h-1.5 rounded ${scoreColor(s).bar}`} style={{ width: `${s}%` }} />
              </div>
              {comp.note && <p className="text-xs leading-4 text-slate-400">{comp.note}</p>}
            </div>
          )
        })}
      </div>
      {starAnalysis.coaching && (
        <div className="mt-3 rounded bg-blue-950/40 border border-blue-800/30 px-3 py-2 text-xs leading-5 text-blue-200">
          <span className="font-semibold text-blue-400">Coach: </span>{starAnalysis.coaching}
        </div>
      )}
    </div>
  )
}

function AuthenticityCard({ authenticity, title }) {
  if (!authenticity) return null
  const score = Math.max(0, Math.min(100, Number(authenticity.score) || 0))
  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-slate-100">{title || "Authenticity"}</h3>
        <span className={`text-xl font-bold ${scoreColor(score).text}`}>{score}</span>
      </div>
      <div className="h-1.5 rounded bg-slate-800 mb-3">
        <div className={`h-1.5 rounded ${scoreColor(score).bar}`} style={{ width: `${score}%` }} />
      </div>
      {(authenticity.overclaiming_detected || authenticity.generic_leadership_detected) && (
        <div className="mb-2 rounded bg-amber-950/40 border border-amber-800/30 px-2 py-1.5 text-xs text-amber-200">
          {authenticity.overclaiming_detected && <div>⚠ Overclaiming signals detected</div>}
          {authenticity.generic_leadership_detected && <div>⚠ Generic leadership story detected</div>}
        </div>
      )}
      <div className="space-y-1.5">
        {authenticity.scripted_indicators?.slice(0, 3).map((s, i) => (
          <div key={i} className="flex gap-2 text-xs leading-5 text-amber-200">
            <span className="shrink-0 text-amber-400">−</span>{s}
          </div>
        ))}
        {authenticity.genuine_technical_moments?.slice(0, 3).map((s, i) => (
          <div key={i} className="flex gap-2 text-xs leading-5 text-emerald-200">
            <span className="shrink-0 text-emerald-400">+</span>{s}
          </div>
        ))}
        {authenticity.authentic_moments?.slice(0, 2).map((s, i) => (
          <div key={i} className="flex gap-2 text-xs leading-5 text-emerald-200">
            <span className="shrink-0 text-emerald-400">+</span>{s}
          </div>
        ))}
      </div>
      {authenticity.note && <p className="mt-2 text-xs leading-5 text-slate-400 border-t border-slate-800 pt-2">{authenticity.note}</p>}
    </div>
  )
}

function BehavioralQualityCard({ title, score, note, pattern, patternStyleFn, badges }) {
  const s = Math.max(0, Math.min(100, Number(score) || 0))
  return (
    <div className="rounded border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-slate-200">{title}</span>
        <span className={`text-lg font-bold ${scoreColor(s).text}`}>{s}</span>
      </div>
      <div className="h-1.5 rounded bg-slate-800 mb-2">
        <div className={`h-1.5 rounded ${scoreColor(s).bar}`} style={{ width: `${s}%` }} />
      </div>
      {pattern && patternStyleFn && (
        <span className={`text-xs font-medium ${patternStyleFn(pattern).text}`}>{pattern.replaceAll("_", " ")}</span>
      )}
      {badges?.map((b, i) => b && <span key={i} className="ml-2 rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-400">{b}</span>)}
      {note && <p className="mt-2 text-xs leading-5 text-slate-400">{note}</p>}
    </div>
  )
}

function ProjectTechCard({ topic }) {
  const depth = Math.max(0, Math.min(100, Number(topic.depth_score) || 0))
  return (
    <div className="rounded border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-medium text-slate-200">{topic.topic}</span>
        <span className={`text-base font-bold ${scoreColor(depth).text}`}>{depth}</span>
      </div>
      <div className="h-1 rounded bg-slate-800 mb-2">
        <div className={`h-1 rounded ${scoreColor(depth).bar}`} style={{ width: `${depth}%` }} />
      </div>
      {topic.note && <p className="text-xs leading-5 text-slate-400">{topic.note}</p>}
    </div>
  )
}

function CoachingSection({ coaching }) {
  if (!coaching) return null
  const sections = [
    { label: "Project Explanation", items: coaching.project_coaching, color: "text-cyan-400" },
    { label: "Behavioral Stories", items: coaching.behavioral_coaching, color: "text-blue-400" },
    { label: "Communication", items: coaching.communication_coaching, color: "text-purple-400" },
  ].filter((s) => s.items?.length > 0)
  if (!sections.length) return null
  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-5">
      <h2 className="mb-4 text-base font-semibold text-slate-100">Personalized Coaching</h2>
      <div className="grid gap-4 sm:grid-cols-3">
        {sections.map(({ label, items, color }) => (
          <div key={label}>
            <h3 className={`text-xs uppercase font-semibold tracking-wide mb-2 ${color}`}>{label}</h3>
            <ul className="space-y-2">
              {items.map((item, i) => (
                <li key={i} className="flex gap-2 text-xs leading-5 text-slate-300">
                  <span className={`shrink-0 font-bold ${color}`}>{i + 1}.</span>{item}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

function PBBenchmarkSection({ benchmarking }) {
  if (!benchmarking) return null
  const score = Math.max(0, Math.min(100, Number(benchmarking.readiness_score) || 0))
  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-5">
      <div className="flex items-start justify-between mb-4 gap-4">
        <h2 className="text-base font-semibold text-slate-100">Benchmarking</h2>
        <div className="text-right shrink-0">
          <div className={`text-2xl font-bold ${scoreColor(score).text}`}>{score}</div>
          <div className="text-xs text-slate-500">readiness</div>
          {benchmarking.level_estimate && <div className="text-xs font-medium text-slate-400">{benchmarking.level_estimate}</div>}
        </div>
      </div>
      {benchmarking.note && <p className="text-sm leading-6 text-slate-400 mb-4">{benchmarking.note}</p>}
      <div className="grid gap-2 sm:grid-cols-2">
        {(benchmarking.comparisons || []).map((c, i) => (
          <div key={i} className="rounded border border-slate-800 bg-slate-950 p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-slate-200">{c.dimension}</span>
              <div className="flex items-center gap-2 text-xs">
                <span className={`font-medium ${scoreColor(c.candidate_score || 0).text}`}>You: {c.candidate_score || 0}</span>
                <span className="text-slate-500">Exp: {c.expectation || 0}</span>
              </div>
            </div>
            <div className="space-y-1 mb-2">
              <div className="flex items-center gap-2">
                <span className="w-8 text-xs text-slate-500 shrink-0">You</span>
                <div className="flex-1 h-1.5 rounded bg-slate-800">
                  <div className={`h-1.5 rounded ${scoreColor(c.candidate_score || 0).bar}`} style={{ width: `${c.candidate_score || 0}%` }} />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-8 text-xs text-slate-500 shrink-0">Exp</span>
                <div className="flex-1 h-1.5 rounded bg-slate-800">
                  <div className="h-1.5 rounded bg-slate-600" style={{ width: `${c.expectation || 0}%` }} />
                </div>
              </div>
            </div>
            {c.gap_note && <p className="text-xs leading-5 text-slate-400">{c.gap_note}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}

function PBFeedback({ report, onRestart, onBack }) {
  const integrity = report.integrity || {}
  const strengths = report.strengths || []
  const weaknesses = report.weak_areas || []
  const suggestions = report.study_plan || []
  const score = Math.max(0, Math.min(100, Number(report.overall_score) || 0))

  return (
    <main className="dashboard-shell min-h-screen text-slate-100 codevoir-dashboard-page">
      <section className="relative z-20 bg-gradient-to-r from-[#004182] to-[#0a66c2] shadow-md border-b border-[#003366]">
        <div className="mx-auto w-full max-w-[95%] xl:max-w-[1400px] flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            {onBack && (
              <button onClick={onBack} className="inline-flex items-center gap-2 rounded-lg bg-white/10 hover:bg-white/20 border border-white/20 px-4 py-2 text-sm font-semibold text-white transition-all">
                <ArrowLeft size={16} /> Back to dashboard
              </button>
            )}
          </div>
        </div>
      </section>
      <BackgroundCanvas />
      <div className="relative z-10 mx-auto w-full max-w-[95%] xl:max-w-[1400px] px-4 md:px-6 py-8">
        <div className="report-hero mb-6 flex flex-col md:flex-row items-stretch justify-between gap-6 rounded border border-cyan-300/20 p-6">
          <div className="flex-1 min-w-0 flex flex-col justify-center">
            <div className="font-display text-xs font-bold uppercase tracking-[0.22em] text-cyan-300 mb-2 font-semibold">Overall Evaluation Summary</div>
            <h1 className="mt-1 font-display text-2xl font-bold text-white mb-2">
              {report.target_company ? `${report.target_company} — ` : ""}Project + Behavioral Report
            </h1>
            <p className="mt-2 max-w-3xl text-sm md:text-[15px] leading-relaxed text-slate-300 font-medium">{report.summary}</p>
          </div>
          <div className="hidden lg:flex items-center justify-center shrink-0 w-56 p-1">
            <div className="h-28 w-full rounded-xl overflow-hidden border border-slate-200/60 bg-white/40 shadow-[0_4px_20px_rgba(0,0,0,0.05)] backdrop-blur-sm">
              <img src="/report_illustration.png" alt="Evaluation graph" className="h-full w-full object-cover" />
            </div>
          </div>
          <div className="rounded border border-cyan-400/30 bg-cyan-400/10 px-6 py-4 text-right shadow-[0_0_40px_rgba(34,211,238,0.12)] shrink-0 flex flex-col justify-center">
            <div className="text-xs uppercase tracking-widest text-cyan-300 font-semibold">Total score</div>
            <div className={`mt-1 text-5xl font-bold ${scoreColor(score).text}`}>{score}<span className="text-base text-slate-500">/100</span></div>
            <div className="mt-1 text-xs text-slate-400 font-medium">Answer quality only</div>
          </div>
        </div>

        <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
          <div className="grid gap-5">
            <SimpleReportPanel title="Strengths" items={strengths} empty="No clear strengths were demonstrated yet." />
            <SimpleReportPanel title="Weaknesses" items={weaknesses} empty="No specific weaknesses were recorded." />
            <SimpleReportPanel title="Suggestions" items={suggestions} empty="No suggestions available yet." />
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-5">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Integrity score</div>
            <div className={`mt-3 text-4xl font-bold ${scoreColor(integrity.score ?? 100).text}`}>{integrity.score ?? 100}<span className="text-base text-slate-500">/100</span></div>
            <div className="mt-3 grid gap-1 text-xs leading-5 text-slate-400">
              <span>{integrity.violations?.length || 0} proctoring event{integrity.violations?.length !== 1 ? "s" : ""}</span>
              <span>Tab switches: {integrity.focus_loss || 0}</span>
              <span>Paste events: {integrity.paste_events || 0}</span>
            </div>
            <p className="mt-4 border-t border-slate-800 pt-4 text-xs leading-5 text-slate-500">Integrity is shown separately and is not blended into the Project + Behavioral total score.</p>
          </div>
        </div>

        <button onClick={onRestart} className="mt-8 rounded bg-cyan-400 px-6 py-3 font-semibold text-slate-950 hover:bg-cyan-300 transition-colors">
          Start Another Interview
        </button>
      </div>
    </main>
  )

  return (
    <main className="dashboard-shell min-h-screen text-slate-100 codevoir-dashboard-page">
      <BackgroundCanvas />
      <div className="relative z-10 mx-auto max-w-7xl px-4 py-8">

        {/* Header */}
        <div className="mb-8 flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-6">
          <div>
            {onBack && <button onClick={onBack} className="mb-3 inline-flex items-center gap-2 rounded border border-slate-700 px-3 py-2 text-sm text-slate-200"><ArrowLeft size={16} /> Back to dashboard</button>}
            <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-widest text-cyan-400 mb-1">
              <span>Project + Behavioral Report</span>
              {report.target_company && <span className="rounded bg-cyan-900/40 px-2 py-0.5">{report.target_company}</span>}
              {report.job_role && <span className="text-slate-500">{report.job_role}</span>}
              {breakdown.company_style && <span className="text-slate-500">{breakdown.company_style}</span>}
            </div>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">{report.summary || verdict.summary}</p>
            {report.skill_gap && (
              <div className="mt-3 rounded border border-amber-700/30 bg-amber-950/20 px-3 py-2 text-xs leading-5 text-amber-200 max-w-2xl">
                <span className="font-semibold text-amber-400">Key gap: </span>{report.skill_gap}
              </div>
            )}
          </div>
          {breakdown.resume_focus?.selected_project && (
            <div className="rounded border border-slate-800 bg-slate-900 px-4 py-3 text-sm shrink-0">
              <div className="text-slate-500 text-xs mb-0.5">Project focus</div>
              <div className="font-semibold text-slate-100">{breakdown.resume_focus.selected_project}</div>
              {breakdown.jd_signals?.skills?.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {breakdown.jd_signals.skills.slice(0, 4).map((s) => (
                    <span key={s} className="rounded bg-blue-900/40 px-1.5 py-0.5 text-xs text-blue-300">{s}</span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Two-column layout */}
        <div className="grid gap-6 lg:grid-cols-[1fr_380px]">

          {/* Left column */}
          <div className="space-y-6">

            {/* Core metrics */}
            {ev.core_metrics?.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-5">
                <h2 className="mb-4 text-base font-semibold text-slate-100">Core Evaluation Metrics</h2>
                <div className="grid gap-2 sm:grid-cols-2">
                  {ev.core_metrics.map((m) => <MetricCard key={m.name} metric={m} />)}
                </div>
              </div>
            )}

            {/* Project evaluation */}
            {proj.ownership_score !== undefined && (
              <div className="rounded border border-slate-800 bg-slate-900 p-5">
                <h2 className="mb-4 text-base font-semibold text-slate-100">Project Evaluation</h2>
                <div className="grid gap-4 sm:grid-cols-2">
                  <OwnershipPanel ownership={proj} />
                  <EngineeringMaturityGrid maturity={proj.engineering_maturity} />
                </div>

                {proj.architecture_understanding && (
                  <div className="mt-4 rounded border border-slate-800 bg-slate-950 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-sm font-semibold text-slate-100">Architecture Understanding</h4>
                      <div className="flex items-center gap-2">
                        {proj.architecture_understanding.depth && (
                          <span className={`text-xs font-medium ${depthStyle(proj.architecture_understanding.depth.replace("_", "")).text}`}>
                            {proj.architecture_understanding.depth.replaceAll("_", " ")}
                          </span>
                        )}
                        <span className={`text-xl font-bold ${scoreColor(Number(proj.architecture_understanding.score) || 0).text}`}>
                          {Math.max(0, Math.min(100, Number(proj.architecture_understanding.score) || 0))}
                        </span>
                      </div>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {proj.architecture_understanding.strong_areas?.map((a, i) => (
                        <div key={i} className="flex gap-1 text-xs leading-5 text-emerald-200"><span className="text-emerald-400">+</span>{a}</div>
                      ))}
                      {proj.architecture_understanding.weak_areas?.map((a, i) => (
                        <div key={i} className="flex gap-1 text-xs leading-5 text-amber-200"><span className="text-amber-400">−</span>{a}</div>
                      ))}
                    </div>
                    {proj.architecture_understanding.note && (
                      <p className="mt-2 text-xs leading-5 text-slate-400">{proj.architecture_understanding.note}</p>
                    )}
                  </div>
                )}

                {proj.technical_depth_topics?.length > 0 && (
                  <div className="mt-4">
                    <h4 className="text-xs uppercase font-semibold tracking-wide text-slate-400 mb-2">Technical Depth by Technology</h4>
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {proj.technical_depth_topics.map((t, i) => <ProjectTechCard key={i} topic={t} />)}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Behavioral evaluation */}
            {beh.star_analysis && (
              <div className="rounded border border-slate-800 bg-slate-900 p-5">
                <h2 className="mb-4 text-base font-semibold text-slate-100">Behavioral Evaluation</h2>
                <div className="grid gap-4 sm:grid-cols-2">
                  <STARBreakdown starAnalysis={beh.star_analysis} />
                  <div className="space-y-3">
                    {beh.leadership_ownership && (
                      <BehavioralQualityCard
                        title="Leadership & Ownership"
                        score={beh.leadership_ownership.score}
                        note={beh.leadership_ownership.note}
                        pattern={beh.leadership_ownership.pattern}
                        patternStyleFn={ownershipPatternStyle}
                      />
                    )}
                    {beh.conflict_resolution && (
                      <BehavioralQualityCard
                        title="Conflict Resolution"
                        score={beh.conflict_resolution.score}
                        note={beh.conflict_resolution.note}
                        pattern={beh.conflict_resolution.maturity_level}
                        patternStyleFn={(p) => ({ text: conflictMaturityStyle(p) })}
                      />
                    )}
                    {beh.decision_quality && (
                      <BehavioralQualityCard
                        title="Decision Quality"
                        score={beh.decision_quality.score}
                        note={beh.decision_quality.note}
                        badges={[beh.decision_quality.reasoning_quality]}
                      />
                    )}
                    {beh.emotional_intelligence && (
                      <BehavioralQualityCard
                        title="Emotional Intelligence"
                        score={beh.emotional_intelligence.score}
                        note={beh.emotional_intelligence.note}
                      />
                    )}
                  </div>
                </div>
              </div>
            )}

            <CoachingSection coaching={ev.coaching} />
            <PBBenchmarkSection benchmarking={ev.benchmarking} />
          </div>

          {/* Right column */}
          <div className="space-y-5">
            <VerdictCard verdict={verdict} overallScore={report.overall_score} />

            {/* Authenticity panels */}
            <AuthenticityCard authenticity={proj.authenticity} title="Project Authenticity" />
            {beh.authenticity && <AuthenticityCard authenticity={beh.authenticity} title="Behavioral Authenticity" />}

            {/* Communication profile */}
            {comm.score !== undefined && (
              <div className="rounded border border-slate-800 bg-slate-900 p-4">
                <h3 className="text-sm font-semibold text-slate-100 mb-3">Communication Profile</h3>
                {[
                  ["Storytelling", comm.storytelling_quality],
                  ["Clarity Under Probing", comm.clarity_under_probing],
                  ["Confidence", comm.confidence_score],
                  ["Structure", comm.structure_score],
                ].filter(([, v]) => v !== undefined).map(([label, val]) => {
                  const v = Math.max(0, Math.min(100, Number(val) || 0))
                  return (
                    <div key={label} className="mb-2">
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-xs text-slate-400">{label}</span>
                        <span className={`text-xs font-medium ${scoreColor(v).text}`}>{v}</span>
                      </div>
                      <div className="h-1 rounded bg-slate-800">
                        <div className={`h-1 rounded ${scoreColor(v).bar}`} style={{ width: `${v}%` }} />
                      </div>
                    </div>
                  )
                })}
                {comm.key_observation && (
                  <p className="mt-3 text-xs leading-5 text-slate-400 border-t border-slate-800 pt-3">{comm.key_observation}</p>
                )}
              </div>
            )}

            {ev.improvement_recommendations?.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-4">
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-100">Recommendations</h2>
                <div className="space-y-2">
                  {ev.improvement_recommendations.map((rec, i) => <RecommendationCard key={i} rec={rec} />)}
                </div>
              </div>
            )}

            {/* STAR heuristic summary */}
            {breakdown.star_completeness_pct > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-4">
                <h3 className="text-sm font-semibold text-slate-100 mb-2">STAR Completeness</h3>
                <div className={`text-3xl font-bold mb-1 ${scoreColor(breakdown.star_completeness_pct).text}`}>
                  {breakdown.star_completeness_pct}<span className="text-sm text-slate-500">%</span>
                </div>
                <div className="h-1.5 rounded bg-slate-800 mb-2">
                  <div className={`h-1.5 rounded ${scoreColor(breakdown.star_completeness_pct).bar}`} style={{ width: `${breakdown.star_completeness_pct}%` }} />
                </div>
                <div className="grid grid-cols-4 gap-1">
                  {Object.entries(breakdown.star_breakdown || {}).map(([k, v]) => (
                    <div key={k} className="rounded bg-slate-950 px-1.5 py-1 text-center">
                      <div className="text-xs uppercase text-slate-500">{k}</div>
                      <div className="text-sm font-semibold">{v}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Integrity */}
            <div className="rounded border border-slate-800 bg-slate-900 p-4">
              <h2 className="mb-2 text-sm font-semibold text-slate-100 uppercase tracking-wide">Integrity</h2>
              <div className={`text-3xl font-bold mb-1 ${scoreColor(integrity.score ?? 100).text}`}>{integrity.score ?? 100}<span className="text-sm text-slate-500">/100</span></div>
              <div className="text-xs text-slate-400">{integrity.violations?.length || 0} proctoring event{integrity.violations?.length !== 1 ? "s" : ""}</div>
            </div>
          </div>
        </div>

        <button onClick={onRestart} className="mt-8 rounded bg-cyan-400 px-6 py-3 font-semibold text-slate-950 hover:bg-cyan-300 transition-colors">
          Start Another Interview
        </button>
      </div>
    </main>
  )
}

function SimpleReportPanel({ title, items, empty }) {
  const visible = (items || []).filter(Boolean)
  return (
    <section className="rounded-2xl border border-sky-400/18 bg-slate-950/70 p-5 shadow-[0_18px_58px_rgba(2,6,23,0.28)]">
      <h2 className="font-display text-xs font-bold uppercase tracking-[0.18em] text-cyan-300">{title}</h2>
      <div className="mt-4 grid gap-3">
        {visible.length ? visible.map((item, index) => (
          <div key={`${title}-${index}`} className="rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm leading-6 text-slate-200">
            {item}
          </div>
        )) : (
          <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-500">{empty}</div>
        )}
      </div>
    </section>
  )
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
    ...(section.latest_flags || []),
  ].filter(Boolean)
  return []
}

function formatEvidence(item) {
  if (item.role && item.content) return `${item.role}: ${item.content}`
  if (item.topic) return `${item.topic} | ${item.question_type || "question"}\nAnswer: ${item.answer_excerpt || ""}`
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
        } catch {
          lastError = new Error(`Could not parse 404 response for ${path}`)
        }
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
    if (Array.isArray(parsed.detail)) {
      return parsed.detail
        .map((item) => item?.msg || item?.message || "")
        .filter(Boolean)
        .join("; ") || "The request format was invalid."
    }
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

function chunkSpeechText(text, maxLength = 180) {
  const spoken = (text || "")
    .replace(/```[\s\S]*?```/g, " code omitted ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*|__/g, "")
    .replace(/[#>*_~\[\]()]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
  if (!spoken) return []

  const sentences = spoken.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [spoken]
  const chunks = []
  let current = ""
  sentences.forEach((sentence) => {
    const part = sentence.trim()
    if (!part) return
    if ((current ? current.length + 1 : 0) + part.length <= maxLength) {
      current = current ? `${current} ${part}` : part
      return
    }
    if (current) chunks.push(current)
    if (part.length <= maxLength) {
      current = part
      return
    }
    const words = part.split(" ")
    current = ""
    words.forEach((word) => {
      if ((current ? current.length + 1 : 0) + word.length <= maxLength) {
        current = current ? `${current} ${word}` : word
      } else {
        if (current) chunks.push(current)
        current = word
      }
    })
  })
  if (current) chunks.push(current)
  return chunks
}

function normalizeSpeech(text) {
  return (text || "").toLowerCase().replace(/[^a-z0-9+ ]/g, " ").replace(/\s+/g, " ").trim()
}
