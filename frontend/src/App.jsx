import { useEffect, useMemo, useRef, useState } from "react"
import Editor from "@monaco-editor/react"
import { AlertTriangle, Bot, Camera, Code2, FileText, Mic, Play, Send, Shield, Square, Upload } from "lucide-react"

const API = import.meta.env.VITE_API_URL || "http://localhost:8000"
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
  const [screen, setScreen] = useState("setup")
  const [session, setSession] = useState(null)
  const [form, setForm] = useState({ job_role: "Software Engineer", experience_level: "fresher", target_company: "", job_description: "", round_type: "dsa", difficulty: "medium", timer_minutes: 45 })
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
  const [roundOptions, setRoundOptions] = useState([])
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
  const lastAiMessage = useMemo(() => [...messages].reverse().find((m) => m.role === "interviewer")?.content ?? "", [messages])

  useEffect(() => {
    apiFetch("/api/interview/round-options")
      .then((res) => res.ok ? res.json() : null)
      .then((meta) => setRoundOptions(meta?.rounds || []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    apiFetch(`/api/interview/companies?round_type=${encodeURIComponent(form.round_type)}`)
      .then((res) => res.ok ? res.json() : null)
      .then((meta) => setCompanies(meta?.companies || []))
      .catch(() => {
        apiFetch("/api/problems/companies")
          .then((res) => res.ok ? res.json() : null)
          .then((meta) => setCompanies(meta?.companies || []))
          .catch(() => {})
      })
  }, [form.round_type])

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
    setIsBusy(true)
    setError("")
    try {
      const created = await postJson("/api/session/start", form)
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
      if (typeof reply.llm_offline === "boolean") setLlmOffline(reply.llm_offline)
      if (reply.dsa_progress) setDsaProgress(reply.dsa_progress)
      if (reply.problem_changed && reply.problem) {
        setSession((prev) => ({ ...prev, problem: reply.problem }))
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
    setScreen("feedback")
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
    _stopCurrentSpeech()
    lastAiSpokenRef.current = text
    speakingRef.current = true
    setVoiceState("ai_speaking")

    const finishSpeaking = () => {
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
          console.warn("ElevenLabs TTS failed, using browser voice:", err)
          currentAudioRef.current = null
          _speakBrowserTTS(text, finishSpeaking)
        })
    } else {
      _speakBrowserTTS(text, finishSpeaking)
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
    recognition.onstart = () => setVoiceState("listening")
    recognition.onresult = (event) => {
      let interim = ""
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const chunk = event.results[i][0]?.transcript || ""
        if (event.results[i].isFinal) finalText += `${chunk} `
        else interim += chunk
      }
      setLiveTranscript(`${finalText}${interim}`.trim())
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
    autoVoiceRef.current = false
    setAutoVoice(false)
    const recognition = recognitionRef.current
    recognitionRef.current = null
    if (recognition) {
      recognition.onend = null   // prevent the auto-restart on stop
      try { recognition.stop() } catch {}
    }
    setVoiceState("user_turn")
    const clean = liveTranscriptRef.current.trim()
    setLiveTranscript("")
    if (clean && session && !isBusy) {
      sendMessage(clean, { voice_turn: true })
    }
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

  if (screen === "feedback" && feedback) return <Feedback report={feedback} onRestart={() => window.location.reload()} />

  if (screen === "setup") {
    return (
      <main className="min-h-screen bg-slate-950 text-slate-100">
        {error && <div className="fixed left-1/2 top-4 z-30 max-w-xl -translate-x-1/2 rounded border border-red-400 bg-red-950 px-4 py-3 text-sm text-red-100">{error}</div>}
        <section className="border-b border-slate-800 bg-slate-900">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
            <div className="flex items-center gap-3">
              <div className="grid h-10 w-10 place-items-center rounded bg-cyan-500 text-slate-950"><Bot size={22} /></div>
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
            <h2 className="mb-4 text-lg font-semibold">Start Live Interview</h2>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Round type"><select value={form.round_type} onChange={(e) => setForm({ ...form, round_type: e.target.value })}>{(roundOptions.length ? roundOptions : [{ id: "dsa", label: "DSA + Code" }, { id: "combined", label: "Projects + Behavioural" }, { id: "cs_fundamentals", label: "CS Fundamentals" }]).map((round) => <option key={round.id} value={round.id}>{round.label}</option>)}</select></Field>
              <Field label="Target company"><input list="company-options" value={form.target_company} onChange={(e) => setForm({ ...form, target_company: e.target.value })} placeholder="Amazon, Google, Meta..." /><datalist id="company-options">{companies.map((company) => <option key={company} value={company} />)}</datalist></Field>
              <Field label="Job role"><input value={form.job_role} onChange={(e) => setForm({ ...form, job_role: e.target.value })} /></Field>
              <Field label="Experience"><select value={form.experience_level} onChange={(e) => setForm({ ...form, experience_level: e.target.value })}><option>fresher</option><option>mid</option><option>senior</option></select></Field>
              {form.round_type === "dsa" && <Field label="Difficulty"><select value={form.difficulty} onChange={(e) => setForm({ ...form, difficulty: e.target.value })}><option>easy</option><option>medium</option><option>hard</option></select></Field>}
              <Field label="Timer minutes"><input type="number" min="10" max="90" value={form.timer_minutes} onChange={(e) => setForm({ ...form, timer_minutes: Number(e.target.value) })} /></Field>
            </div>
            {selectedRoundOption && <div className="mt-4 rounded bg-slate-950 p-3 text-xs text-slate-400">{selectedRoundOption.company_count?.toLocaleString?.() || selectedRoundOption.company_count || companies.length} companies available for {selectedRoundOption.label}. {selectedRoundOption.requires_resume ? "Resume recommended." : "Resume optional."} {selectedRoundOption.requires_job_description ? "Job description recommended." : ""}</div>}
            {isProjectRound && <label className="mt-4 grid gap-2 text-sm text-slate-300">
              <span>Job description</span>
              <textarea value={form.job_description} onChange={(e) => setForm({ ...form, job_description: e.target.value })} placeholder="Paste the job description for Project + Behavioural interview personalization" className="h-28 w-full resize-y rounded border border-slate-700 bg-slate-950 p-3 text-sm text-slate-100 outline-none focus:border-cyan-400" />
            </label>}
            {isProjectRound && <label className="mt-4 flex cursor-pointer items-center gap-3 rounded border border-dashed border-slate-700 p-4 text-sm text-slate-300">
              <Upload size={18} />
              <span>{resume ? resume.name : "Upload resume for personalised project and behavioural questions"}</span>
              <input className="hidden" type="file" accept=".pdf,.txt" onChange={(e) => setResume(e.target.files?.[0] || null)} />
            </label>}
            <button className="mt-5 inline-flex items-center gap-2 rounded bg-cyan-400 px-4 py-2 font-semibold text-slate-950 disabled:opacity-50" onClick={startSession} disabled={isBusy}>
              <Play size={18} /> Start interview
            </button>
          </div>

          <div className="rounded border border-slate-800 bg-slate-900 p-5">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold"><FileText size={19} /> Critical Resume Review</h2>
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
          <Bot className="text-cyan-300" />
          <div>
            <div className="font-semibold">{roundTitle}</div>
            <div className="text-xs text-slate-400">{voiceState.replace("_", " ")} - {form.difficulty}{liveTranscript ? ` - "${liveTranscript.slice(0, 70)}"` : ""}</div>
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
          <button onClick={() => setTranscriptOpen(true)} className="rounded border border-slate-600 px-3 py-2 text-sm">Transcript</button>
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

// Build a client-side dsa_evaluation from heuristic report data when backend
// deep eval is unavailable (old session, LLM down, or pre-update backend).
function _buildClientDSAEval(report) {
  const bd = report.round_breakdown || {}
  const overall = Number(report.overall_score) || 50
  const paramScores = report.parameter_scores || []

  function _sl(s) {
    if (s >= 85) return "Exceptional"
    if (s >= 70) return "Strong"
    if (s >= 55) return "Competent"
    if (s >= 40) return "Developing"
    return "Weak"
  }

  const coreNames = ["Problem Solving Ability","DSA Knowledge","Optimization Skill","Coding Accuracy","Communication & Explanation","Confidence During Interview","Hint Dependency","Adaptability","Complexity Analysis","Edge Case Awareness"]

  let core_metrics
  if (paramScores.length >= 5) {
    const extended = [...paramScores]
    while (extended.length < 10) {
      extended.push({ name: coreNames[extended.length] || `Metric ${extended.length + 1}`, score: Math.round(overall * 0.9), note: "Score derived from session signals." })
    }
    core_metrics = extended.slice(0, 10).map((p, i) => ({
      name: coreNames[i] || p.name,
      score: Math.max(0, Math.min(100, Number(p.score) || Math.round(overall * 0.9))),
      label: _sl(Math.max(0, Math.min(100, Number(p.score) || Math.round(overall * 0.9)))),
      note: p.note || "Derived from session evaluation signals.",
    }))
  } else {
    const base = Math.round(overall)
    core_metrics = coreNames.map((name, i) => {
      const nudge = [0, 2, -5, bd.submission?.passed_testcases && bd.submission?.total_testcases ? Math.round((bd.submission.passed_testcases / bd.submission.total_testcases) * 100) - base : 0, 0, 0, 0, -3, -5, -8][i] || 0
      const s = Math.max(0, Math.min(100, base + nudge))
      return { name, score: s, label: _sl(s), note: "Score derived from heuristic session evaluation." }
    })
  }

  const signalMap = { "Strong hire": "Strong Hire", "Leaning hire": "Hire", "Needs targeted preparation": "Lean Hire", "Needs significant preparation": "Lean Reject" }
  const verdictSignal = signalMap[report.hiring_signal] || (overall >= 82 ? "Strong Hire" : overall >= 68 ? "Hire" : overall >= 52 ? "Lean Hire" : "Lean Reject")

  const weakAreas = report.weak_areas || []
  const strengths = report.strengths || []

  return {
    core_metrics,
    advanced_metrics: {
      company_fit: { score: Math.round(overall), fit_signals: strengths.slice(0, 3), concern_signals: weakAreas.slice(0, 3), note: "Company fit estimated from session signals." },
    },
    company_tailored: {
      company: report.target_company || "Target Company",
      bar_assessment: overall >= 82 ? "Above Bar" : overall >= 68 ? "At Bar" : overall >= 52 ? "Approaching Bar" : "Below Bar",
      optimization_quality: { score: Math.round(overall * 0.9), note: "Optimization quality derived from session approach signals." },
      communication_clarity: { score: Math.round(overall * 0.88), note: "Communication clarity from explanation quality signals." },
      followup_handling: { score: Math.round(overall * 0.85), note: "Follow-up handling estimated from session response patterns." },
      coding_speed: { score: bd.submission?.total_testcases ? Math.round((bd.submission.passed_testcases / bd.submission.total_testcases) * 100) : Math.round(overall * 0.85), note: bd.submission?.total_testcases ? `${bd.submission.passed_testcases}/${bd.submission.total_testcases} tests passed.` : "No code submission recorded." },
      debugging_behavior: { score: Math.round(overall * 0.82), note: "Debugging behavior estimated from session signals." },
      summary: `Performance at ${report.target_company || "the target company"} maps to a ${overall >= 75 ? "strong" : overall >= 58 ? "borderline" : "developing"} candidate profile based on session signals.`,
    },
    weakness_analysis: weakAreas.slice(0, 4).map((w) => ({
      area: w.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()).slice(0, 60),
      specific_issue: w,
      why_it_matters: "Identified as a key gap during this session's evaluation.",
      improvement: "Practice this area with deliberate focus — state complexity before coding and cover edge cases.",
    })),
    improvement_recommendations: (() => {
      const recs = []
      const weakRec = {
        approach_quality: ["Problem Solving", "Your session flagged approach quality as a gap. Practice stating the brute-force first, then explicitly narrate the optimization step — 'I can trade space for time using a hash map.' Interviewers score the transition, not just the final answer.", "high"],
        complexity_analysis: ["Complexity Analysis", "Complexity analysis was flagged as weak. Before writing any code, write the Big-O as a comment. After coding, trace one example to verify the claim. Incorrect complexity claims are an immediate red flag.", "high"],
        code_quality: ["Code Quality", "Code quality signals suggest rushed or unclean submissions. Practice clean variable names, no magic numbers, and one-line inline comments for non-obvious logic.", "high"],
        communication: ["Communication", "Communication was flagged as weak. Narrate every decision as you make it: 'I'm using a sliding window here because the constraint is contiguous subarray.' Silent coding gives interviewers nothing to evaluate.", "high"],
        debugging: ["Debugging", "Debugging signals were weak. When a test fails, state the failing case, trace through your code manually for that input, identify the exact diverging line, then fix it. Narrate this process out loud.", "high"],
        edge_cases: ["Edge Case Handling", "Edge case handling was flagged. Before submitting, explicitly list: empty input, single element, all-same values, max size, and negatives. Then verify each with a 30-second trace.", "medium"],
        dsa_knowledge: ["DSA Knowledge", "DSA knowledge gaps were identified. Revisit the flagged topic area with 3–5 focused problems. For each, understand why the data structure fits — not just how to code it.", "medium"],
      }
      for (const w of weakAreas.slice(0, 3)) {
        const key = w.toLowerCase().replace(/\s+/g, "_")
        if (weakRec[key]) {
          const [cat, rec, pri] = weakRec[key]
          recs.push({ category: cat, recommendation: rec, priority: pri })
        }
      }
      const bd2 = report.round_breakdown || {}
      const hintCount = report.dsa?.hints_given || 0
      const passedTC = bd2.submission?.passed_testcases ?? null
      const totalTC = bd2.submission?.total_testcases ?? null
      if (hintCount >= 2 && recs.length < 5) recs.push({ category: "Independent Problem Solving", recommendation: `You requested ${hintCount} hints this session. Practice 20-minute timed attempts with no hints — when stuck, speak partial thinking aloud. Demonstrating process is as valuable as finding the answer.`, priority: "high" })
      if (totalTC && passedTC < totalTC && recs.length < 5) recs.push({ category: "Code Correctness", recommendation: `Your code passed ${passedTC}/${totalTC} test cases. Trace through each failing case manually — identify the exact value that diverges from expected before resubmitting.`, priority: "high" })
      const defaults = [
        ["Interview Habits", "Before writing any code, state your approach, the invariant, and the time/space complexity. Interviewers score this narration as heavily as the code.", "high"],
        ["Optimization Strategy", "After reaching a brute-force, explicitly ask: 'Can I reduce time complexity by trading space?' Narrate the transition — that moment is what senior interviewers watch for.", "medium"],
        ["Edge Case Discipline", "Before submitting, enumerate edge cases out loud: empty input, single element, duplicates, negatives, overflow. Then trace one through your code manually.", "medium"],
      ]
      for (const [cat, rec, pri] of defaults) { if (recs.length >= 5) break; recs.push({ category: cat, recommendation: rec, priority: pri }) }
      return recs.slice(0, 5)
    })(),
    behavior_coaching: [{
      observation: "Report generated from session heuristic signals.",
      impact: "Complete voice interaction and code narration enable deeper behavioral analysis.",
      coaching: "In your next session: narrate every decision, ask clarifying questions before coding, and explain time/space complexity before submitting.",
    }],
    learning_plan: {
      one_week: {
        daily_goals: ["Solve 2 LeetCode problems daily (1 easy + 1 medium). State complexity before writing code.", "Review the optimal solution after each problem — understand the pattern, not just the answer.", "Practice 1 weak area topic per day with deliberate focus.", "Set a 25-minute timer per problem — simulate real interview pressure.", "Write brute-force first always, then optimize. Never skip this step."],
        focus_topics: weakAreas.slice(0, 4).map((w) => w.replace(/_/g, " ")).filter(Boolean).concat(["Arrays", "Hash Maps"]).slice(0, 4),
        problem_types: ["Two Sum variants (hash map)", "Sliding Window", "BFS/DFS on matrices", "Binary Search"],
      },
      two_week: {
        daily_goals: ["Solve 3 problems daily including 1 hard. Full verbal narration throughout.", "Mock interview: record yourself, watch it back — are you explaining decisions clearly?", "For each problem: identify the pattern category before starting.", "Optimize every brute-force — what trade-off improves time or space?", "Review 5 past failed solutions — understand the root cause of each failure."],
        focus_topics: (weakAreas.slice(0, 2).map((w) => w.replace(/_/g, " ")).filter(Boolean)).concat(["Dynamic Programming", "Graph Traversal", "Trees"]).slice(0, 5),
        problem_types: ["DP: Knapsack / LCS", "Graph BFS/DFS", "Binary Search on answer", "Monotonic Stack", "Prefix Sum"],
      },
      recommended_problems: ["Two Sum & 3Sum", "Sliding Window Maximum", "Number of Islands", "Merge Intervals", "LRU Cache", "Word Search II"],
    },
    benchmarking: {
      faang_readiness_score: Math.round(overall * 0.92),
      estimated_level: overall >= 85 ? "L5/Senior" : overall >= 70 ? "L4/Mid" : overall >= 55 ? "L3/Junior" : "Below L3",
      comparisons: [
        { metric: "Problem Solving", candidate_score: core_metrics[0].score, faang_bar: 80, gap_note: core_metrics[0].score >= 80 ? "On target." : `Gap of ${80 - core_metrics[0].score} pts — practice structured approach to optimization.` },
        { metric: "Code Correctness", candidate_score: core_metrics[3].score, faang_bar: 85, gap_note: core_metrics[3].score >= 85 ? "On target." : `Gap of ${85 - core_metrics[3].score} pts — enumerate edge cases before submitting.` },
        { metric: "Communication", candidate_score: core_metrics[4].score, faang_bar: 75, gap_note: core_metrics[4].score >= 75 ? "On target." : `Gap of ${75 - core_metrics[4].score} pts — narrate every decision throughout.` },
        { metric: "Complexity Analysis", candidate_score: core_metrics[8].score, faang_bar: 80, gap_note: core_metrics[8].score >= 80 ? "On target." : `Gap of ${80 - core_metrics[8].score} pts — always state O() before coding.` },
      ],
      overall_readiness_note: `Current performance places you at approximately ${Math.round(overall * 0.92)}/100 FAANG readiness. ${bd.submission?.total_testcases ? `With ${bd.submission.passed_testcases}/${bd.submission.total_testcases} tests passing, the next focus should be edge case coverage and optimization narration.` : "Submit code solutions in every session to generate precise correctness signals."}`,
    },
    strength_recognition: strengths.slice(0, 3).map((s) => ({
      strength: s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()).slice(0, 60),
      evidence: s,
      interview_value: "A recognized strength in your session evaluation profile.",
    })),
    final_verdict: {
      signal: verdictSignal,
      confidence_score: Math.min(85, Math.round(overall)),
      summary: report.summary || `Session score: ${Math.round(overall)}/100. ${bd.submission?.total_testcases ? `Code correctness (${bd.submission.passed_testcases}/${bd.submission.total_testcases} tests) was a primary evaluation signal.` : "No code submission recorded — submit code for a full evaluation."}`,
      biggest_strength: strengths[0] || (bd.submission?.passed_testcases === bd.submission?.total_testcases && bd.submission?.total_testcases ? "Code correctness — all tests passed" : "Session engagement"),
      biggest_weakness: weakAreas[0] || (bd.submission?.total_testcases ? "Edge case coverage" : "No code submission recorded"),
      most_important_next_step: (report.study_plan || [])[0] || "State your approach, complexity, and edge cases out loud before every code submission.",
    },
    question_performance: [],
    _source: "client_fallback",
  }
}

function Feedback({ report, onRestart }) {
  if (report.round_type === "dsa") {
    return <DSAFeedback report={report} onRestart={onRestart} />
  }
  if (report.round_type === "cs_fundamentals") {
    return <CSFeedback report={report} onRestart={onRestart} />
  }
  if (report.round_type === "project_behavioral") {
    return <PBFeedback report={report} onRestart={onRestart} />
  }
  const breakdown = report.round_breakdown || {}
  const roundItems = roundBreakdownItems(breakdown)
  const integrity = report.integrity || {}

  return <main className="min-h-screen bg-slate-950 p-6 text-slate-100">
    <section className="mx-auto max-w-6xl rounded border border-slate-800 bg-slate-900 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
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

      <button onClick={onRestart} className="mt-6 rounded bg-cyan-400 px-4 py-2 font-semibold text-slate-950">Start another interview</button>
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
    <div className="rounded border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm font-medium text-slate-200 leading-5">{metric.name}</div>
        <div className={`text-lg font-bold shrink-0 ${text}`}>{score}</div>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <div className="flex-1 h-1.5 rounded bg-slate-800">
          <div className={`h-1.5 rounded ${bar} transition-all`} style={{ width: `${score}%` }} />
        </div>
        {metric.label && <span className={`text-xs font-medium shrink-0 ${labelColor(metric.label)}`}>{metric.label}</span>}
      </div>
      {metric.note && <p className="mt-2 text-xs leading-5 text-slate-400">{metric.note}</p>}
    </div>
  )
}

function VerdictCard({ verdict, overallScore }) {
  const signal = verdict?.signal || ""
  const { bg, border, text, dot } = verdictColors(signal)
  const confidence = Math.max(0, Math.min(100, Number(verdict?.confidence_score) || 0))
  const { bar: confBar } = scoreColor(confidence)
  return (
    <div className={`rounded border-2 ${border} ${bg} p-5`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-widest text-slate-400 mb-1">Final Verdict</div>
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
        <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
          <span>Confidence</span><span>{confidence}%</span>
        </div>
        <div className="h-1.5 rounded bg-slate-800">
          <div className={`h-1.5 rounded ${confBar}`} style={{ width: `${confidence}%` }} />
        </div>
      </div>
      {verdict?.summary && <p className="mt-3 text-sm leading-6 text-slate-300">{verdict.summary}</p>}
      {(verdict?.biggest_strength || verdict?.biggest_weakness || verdict?.most_important_next_step) && (
        <div className="mt-3 grid gap-2">
          {verdict.biggest_strength && (
            <div className="rounded bg-emerald-950/50 border border-emerald-800/40 px-3 py-2 text-xs text-emerald-200">
              <span className="font-semibold text-emerald-400">Top strength: </span>{verdict.biggest_strength}
            </div>
          )}
          {verdict.biggest_weakness && (
            <div className="rounded bg-amber-950/50 border border-amber-800/40 px-3 py-2 text-xs text-amber-200">
              <span className="font-semibold text-amber-400">Key gap: </span>{verdict.biggest_weakness}
            </div>
          )}
          {verdict.most_important_next_step && (
            <div className="rounded bg-blue-950/50 border border-blue-800/40 px-3 py-2 text-xs text-blue-200">
              <span className="font-semibold text-blue-400">Priority action: </span>{verdict.most_important_next_step}
            </div>
          )}
        </div>
      )}
    </div>
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
  const verdictColor = { Strong: "text-emerald-400 bg-emerald-900/40", Satisfactory: "text-blue-400 bg-blue-900/40", "Needs Work": "text-amber-400 bg-amber-900/40", Weak: "text-red-400 bg-red-900/40" }
  const vc = verdictColor[qp.verdict] || verdictColor["Needs Work"]
  const metrics = qp.metrics || {}
  const bars = [
    { label: "Approach", val: metrics.approach_quality || 0 },
    { label: "Implementation", val: metrics.implementation || 0 },
    { label: "Communication", val: metrics.communication || 0 },
    { label: "Debugging", val: metrics.debugging || 0 },
  ]
  return (
    <div className="rounded border border-slate-700 bg-slate-900 p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">Question {qp.question_index}</span>
          {qp.problem_excerpt && <p className="text-xs text-slate-400 mt-1 line-clamp-2">{qp.problem_excerpt}</p>}
        </div>
        <div className="flex flex-col items-end gap-1 ml-3 shrink-0">
          <span className={`rounded px-2 py-0.5 text-xs font-semibold ${vc}`}>{qp.verdict}</span>
          <span className="text-lg font-bold text-slate-100">{qp.overall_score}<span className="text-xs font-normal text-slate-500">/100</span></span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        {bars.map(({ label, val }) => {
          const { bar, text } = scoreColor(val)
          return (
            <div key={label}>
              <div className="flex justify-between text-xs mb-0.5"><span className="text-slate-500">{label}</span><span className={text}>{val}</span></div>
              <div className="h-1 rounded bg-slate-800"><div className={`h-1 rounded ${bar}`} style={{ width: `${val}%` }} /></div>
            </div>
          )
        })}
      </div>
      {(qp.hints_used > 0 || (qp.followups_asked || []).length > 0) && (
        <div className="mt-3 flex flex-wrap gap-2">
          {qp.hints_used > 0 && <span className="rounded bg-amber-900/30 px-2 py-0.5 text-xs text-amber-400">{qp.hints_used} hint{qp.hints_used !== 1 ? "s" : ""} used</span>}
          {(qp.followups_asked || []).slice(0, 1).map((f, i) => <span key={i} className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-400 max-w-xs truncate">{f}</span>)}
        </div>
      )}
    </div>
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

function DSAFeedback({ report, onRestart }) {
  const ev = (report.dsa_evaluation && report.dsa_evaluation.final_verdict)
    ? report.dsa_evaluation
    : _buildClientDSAEval(report)
  const verdict = ev.final_verdict || {}
  const ct = ev.company_tailored || {}
  const adv = ev.advanced_metrics || {}
  const breakdown = report.round_breakdown || {}
  const integrity = report.integrity || {}

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-7xl px-4 py-8">

        {/* Header */}
        <div className="mb-8 flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-6">
          <div>
            <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-cyan-400 mb-1">
              <span>DSA Interview Report</span>
              {report.target_company && <span className="rounded bg-cyan-900/40 px-2 py-0.5">{report.target_company}</span>}
              {report.job_role && <span className="text-slate-500">{report.job_role}</span>}
            </div>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">{report.summary || verdict.summary}</p>
            {report.skill_gap && (
              <div className="mt-3 rounded border border-amber-700/30 bg-amber-950/20 px-3 py-2 text-xs leading-5 text-amber-200 max-w-2xl">
                <span className="font-semibold text-amber-400">Key skill gap: </span>{report.skill_gap}
              </div>
            )}
          </div>
          {breakdown.problem?.title && (
            <div className="rounded border border-slate-800 bg-slate-900 px-4 py-3 text-right text-sm shrink-0">
              <div className="text-slate-500 text-xs mb-0.5">Problem</div>
              <div className="font-semibold text-slate-100">{breakdown.problem.title}</div>
              <div className="text-slate-400 text-xs mt-0.5">{breakdown.problem.difficulty} · {(breakdown.problem.topics || []).slice(0, 3).join(", ")}</div>
              {breakdown.submission?.total_testcases > 0 && (
                <div className={`mt-1 text-xs font-medium ${breakdown.submission.passed_testcases === breakdown.submission.total_testcases ? "text-emerald-400" : "text-amber-400"}`}>
                  {breakdown.submission.passed_testcases}/{breakdown.submission.total_testcases} tests passed
                </div>
              )}
            </div>
          )}
        </div>

        {/* Main two-column layout */}
        <div className="grid gap-6 lg:grid-cols-[1fr_380px]">

          {/* Left column */}
          <div className="space-y-6">

            {/* Radar + core metrics header */}
            {ev.core_metrics?.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-5">
                <h2 className="mb-4 text-base font-semibold text-slate-100">Core Evaluation Metrics</h2>
                <div className="grid gap-6 md:grid-cols-[280px_1fr] items-start">
                  <RadarChart metrics={ev.core_metrics} />
                  <div className="grid gap-2 sm:grid-cols-2">
                    {ev.core_metrics.map((m) => <MetricCard key={m.name} metric={m} />)}
                  </div>
                </div>
              </div>
            )}

            {/* Advanced metrics */}
            {adv.company_fit && (
              <div className="rounded border border-slate-800 bg-slate-900 p-5">
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
              </div>
            )}

            {/* Company-tailored */}
            {ct.company && (
              <div className="rounded border border-slate-800 bg-slate-900 p-5">
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
              </div>
            )}

            {/* Benchmarking */}
            {ev.benchmarking && (
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
            {report.topic_mastery?.length > 0 && (
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

            {ev.weakness_analysis?.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-4">
                <h2 className="mb-3 text-sm font-semibold text-slate-100 uppercase tracking-wide">Weakness Analysis</h2>
                <div className="space-y-3">
                  {ev.weakness_analysis.map((w, i) => <WeaknessCard key={i} weakness={w} />)}
                </div>
              </div>
            )}

            {ev.strength_recognition?.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900 p-4">
                <h2 className="mb-3 text-sm font-semibold text-slate-100 uppercase tracking-wide">Strengths Recognized</h2>
                <div className="space-y-3">
                  {ev.strength_recognition.map((s, i) => <StrengthCard key={i} strength={s} />)}
                </div>
              </div>
            )}

            {ev.behavior_coaching?.length > 0 && (
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

          {ev.improvement_recommendations?.length > 0 && (
            <div className="rounded border border-slate-800 bg-slate-900 p-5">
              <h2 className="mb-4 text-base font-semibold text-slate-100">Improvement Recommendations</h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {ev.improvement_recommendations.map((rec, i) => <RecommendationCard key={i} rec={rec} />)}
              </div>
            </div>
          )}

          <LearningPlanSection plan={ev.learning_plan || {}} />

          {/* Evidence */}
          {breakdown.evidence?.length > 0 && <EvidencePanel evidence={breakdown.evidence} />}

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

function CSFeedback({ report, onRestart }) {
  const ev = report.cs_evaluation || {}
  const verdict = ev.final_verdict || {}
  const breakdown = report.round_breakdown || {}
  const integrity = report.integrity || {}

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-7xl px-4 py-8">

        {/* Header */}
        <div className="mb-8 flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-6">
          <div>
            <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-widest text-cyan-400 mb-1">
              <span>CS Fundamentals Report</span>
              {report.target_company && <span className="rounded bg-cyan-900/40 px-2 py-0.5">{report.target_company}</span>}
              {report.job_role && <span className="text-slate-500">{report.job_role}</span>}
            </div>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">{report.summary || verdict.summary}</p>
            {report.skill_gap && (
              <div className="mt-3 rounded border border-amber-700/30 bg-amber-950/20 px-3 py-2 text-xs leading-5 text-amber-200 max-w-2xl">
                <span className="font-semibold text-amber-400">Key gap: </span>{report.skill_gap}
              </div>
            )}
          </div>
          {breakdown.topics_covered?.length > 0 && (
            <div className="rounded border border-slate-800 bg-slate-900 px-4 py-3 text-sm shrink-0">
              <div className="text-slate-500 text-xs mb-1">Topics covered</div>
              <div className="flex flex-wrap gap-1">
                {breakdown.topics_covered.map((t) => (
                  <span key={t} className="rounded bg-cyan-900/40 px-2 py-0.5 text-xs text-cyan-300">{t}</span>
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

function PBFeedback({ report, onRestart }) {
  const ev = report.pb_evaluation || {}
  const verdict = ev.final_verdict || {}
  const proj = ev.project_evaluation || {}
  const beh = ev.behavioral_evaluation || {}
  const comm = ev.communication_profile || {}
  const breakdown = report.round_breakdown || {}
  const integrity = report.integrity || {}

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-7xl px-4 py-8">

        {/* Header */}
        <div className="mb-8 flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-6">
          <div>
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
  if (item.phase) return `${item.phase}\nAnswer: ${item.answer_excerpt || ""}\nFlags: ${(item.flags || []).join("; ")}`
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
      const res = await fetch(`${base}${path}`, options)
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

function normalizeSpeech(text) {
  return (text || "").toLowerCase().replace(/[^a-z0-9+ ]/g, " ").replace(/\s+/g, " ").trim()
}
