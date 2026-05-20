import { useEffect, useMemo, useRef, useState } from "react"
import Editor from "@monaco-editor/react"
import { AlertTriangle, Bot, Camera, Code2, FileText, Mic, Play, Shield, Square, Upload } from "lucide-react"

const API = import.meta.env.VITE_API_URL || "http://localhost:8000"
const API_BASES = [...new Set(["", API, "http://127.0.0.1:8010", "http://localhost:8010", "http://localhost:8000"])]

const languageLabels = {
  python: "Python",
  javascript: "JavaScript",
  cpp: "C++",
  c: "C",
  java: "Java",
}

const defaultCode = `# Select a language and start solving.
`

export default function App() {
  const [screen, setScreen] = useState("setup")
  const [session, setSession] = useState(null)
  const [form, setForm] = useState({ job_role: "Software Engineer", experience_level: "fresher", target_company: "", round_type: "dsa", difficulty: "medium", timer_minutes: 35 })
  const [resume, setResume] = useState(null)
  const [resumeReviewFile, setResumeReviewFile] = useState(null)
  const [resumeReview, setResumeReview] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
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
  const [isBusy, setIsBusy] = useState(false)
  const videoRef = useRef(null)
  const recognitionRef = useRef(null)
  const autoVoiceRef = useRef(false)
  const speakingRef = useRef(false)
  const ttsTimeoutRef = useRef(null)
  const voiceRestartTimerRef = useRef(null)
  const intentionalStopRef = useRef(false)
  const voiceRetryRef = useRef(0)
  const lastListenEndedAtRef = useRef(0)
  const lastAiSpokenRef = useRef("")
  const dragRef = useRef(null)
  const editorTelemetryRef = useRef({ lastChangeAt: Date.now(), edits: 0, pasteEvents: 0, largePastes: 0, deletions: 0, idleGaps: 0, maxLines: 0 })

  const currentProblem = session?.problem
  const lastAiMessage = useMemo(() => [...messages].reverse().find((m) => m.role === "interviewer")?.content || "", [messages])

  useEffect(() => {
    if (!currentProblem) return
    setCode(getStarterCode(currentProblem, language))
    setCodeResult(null)
  }, [language, currentProblem?.id])

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
    if (isLikelyEcho(clean, lastAiSpokenRef.current)) {
      setLiveTranscript("")
      if (autoVoiceRef.current && !speakingRef.current) scheduleListen(800)
      return
    }
    setInput("")
    setLiveTranscript("")
    setMessages((prev) => [...prev, { role: "candidate", content: clean }])
    setIsBusy(true)
    try {
      const reply = await postJson("/api/interview/message", { session_id: session.session_id, user_text: clean, behavioral_metrics: behavioralMetrics })
      setMessages((prev) => [...prev, { role: "interviewer", content: reply.ai_text }])
      speak(reply.ai_text)
    } catch (err) {
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
      setCodeResult(reply.result)
      setMessages((prev) => [...prev, { role: "candidate", content: `Submitted ${languageLabels[language]} code.` }, { role: "interviewer", content: reply.ai_text }])
      speak(reply.ai_text)
    } catch (err) {
      const detail = friendlyError(err)
      setError(detail)
      setMessages((prev) => [...prev, { role: "interviewer", content: `Code submission could not be evaluated: ${detail}` }])
      window.setTimeout(() => setError(""), 6000)
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
    await postJson("/api/interview/violation", { session_id: session.session_id, event_type, detail }).catch(() => {})
  }

  function speak(text) {
    if (!("speechSynthesis" in window)) return
    if (voiceRestartTimerRef.current) window.clearTimeout(voiceRestartTimerRef.current)
    if (recognitionRef.current) {
      intentionalStopRef.current = true
      recognitionRef.current.stop?.()
    }
    window.speechSynthesis.cancel()
    if (ttsTimeoutRef.current) window.clearTimeout(ttsTimeoutRef.current)
    lastAiSpokenRef.current = text
    speakingRef.current = true
    setVoiceState("ai_speaking")
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 1.02
    const finishSpeaking = () => {
      if (!speakingRef.current) return
      speakingRef.current = false
      setVoiceState("user_turn")
      if (autoVoiceRef.current) scheduleListen(900)
    }
    utterance.onend = finishSpeaking
    utterance.onerror = finishSpeaking
    window.speechSynthesis.speak(utterance)
    ttsTimeoutRef.current = window.setTimeout(finishSpeaking, Math.min(12000, text.length * 60 + 500))
  }

  function startListening() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      setWarning("Speech recognition is only available in Chrome. Use manual text input.")
      window.setTimeout(() => setWarning(""), 5000)
      return
    }
    if (speakingRef.current || recognitionRef.current) return
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
    const stopAfterSpeech = (delayMs = 1100) => {
      if (silenceTimer) window.clearTimeout(silenceTimer)
      silenceTimer = window.setTimeout(() => {
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
          if (finalSpeechTimer) window.clearTimeout(finalSpeechTimer)
          finalSpeechTimer = window.setTimeout(() => {
            intentionalStopRef.current = false
            recognition.stop()
          }, 900)
        } else interim += chunk
      }
      latestHeardText = `${finalText}${interim}`.trim()
      setLiveTranscript(latestHeardText)
      if (latestHeardText) stopAfterSpeech(finalText.trim() ? 900 : 1600)
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
        if (isLikelyEcho(clean, lastAiSpokenRef.current)) {
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
    if (!autoVoiceRef.current || speakingRef.current) return
    if (voiceRestartTimerRef.current) window.clearTimeout(voiceRestartTimerRef.current)
    voiceRestartTimerRef.current = window.setTimeout(() => {
      voiceRestartTimerRef.current = null
      startListening()
    }, delayMs)
  }

  function stopListening() {
    if (voiceRestartTimerRef.current) window.clearTimeout(voiceRestartTimerRef.current)
    autoVoiceRef.current = false
    setAutoVoice(false)
    intentionalStopRef.current = true
    recognitionRef.current?.stop?.()
    recognitionRef.current = null
    setVoiceState("user_turn")
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
      if (telemetry.edits % 12 === 0 || inserted > 160) {
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
              <Field label="Job role"><input value={form.job_role} onChange={(e) => setForm({ ...form, job_role: e.target.value })} /></Field>
              <Field label="Experience"><select value={form.experience_level} onChange={(e) => setForm({ ...form, experience_level: e.target.value })}><option>fresher</option><option>mid</option><option>senior</option></select></Field>
              <Field label="Target company"><input value={form.target_company} onChange={(e) => setForm({ ...form, target_company: e.target.value })} placeholder="Optional" /></Field>
              <Field label="Difficulty"><select value={form.difficulty} onChange={(e) => setForm({ ...form, difficulty: e.target.value })}><option>easy</option><option>medium</option><option>hard</option></select></Field>
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <Field label="Round type"><select value={form.round_type} onChange={(e) => setForm({ ...form, round_type: e.target.value })}><option value="dsa">DSA + Code</option><option value="combined">Projects + Behavioural</option></select></Field>
              <Field label="Timer minutes"><input type="number" min="10" max="90" value={form.timer_minutes} onChange={(e) => setForm({ ...form, timer_minutes: Number(e.target.value) })} /></Field>
            </div>
            <label className="mt-4 flex cursor-pointer items-center gap-3 rounded border border-dashed border-slate-700 p-4 text-sm text-slate-300">
              <Upload size={18} />
              <span>{resume ? resume.name : "Upload resume for personalised project and behavioural questions"}</span>
              <input className="hidden" type="file" accept=".pdf,.txt" onChange={(e) => setResume(e.target.files?.[0] || null)} />
            </label>
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
            <div className="font-semibold">{form.round_type === "dsa" ? "DSA + Code Interview" : "Projects + Behavioural Interview"}</div>
            <div className="text-xs text-slate-400">{voiceState.replace("_", " ")} - {form.difficulty}{liveTranscript ? ` - "${liveTranscript.slice(0, 70)}"` : ""}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
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
                <div className="text-sm text-slate-400">Problem {currentProblem?.frontend_id || currentProblem?.id}</div>
                <h2 className="truncate text-xl font-semibold">{currentProblem?.title || "Project Discussion"}</h2>
              </div>
              {currentProblem && <span className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300">{currentProblem.difficulty}</span>}
            </div>
            {currentProblem?.topics && <div className="mt-2 flex flex-wrap gap-2">{currentProblem.topics.slice(0, 8).map((topic) => <span key={topic} className="rounded bg-slate-950 px-2 py-1 text-xs text-slate-400">{topic}</span>)}</div>}
            {session?.dataset_size && <div className="mt-2 text-xs text-slate-500">Dataset: {session.dataset_size.toLocaleString()} public LeetCode problems</div>}
          </div>
          {form.round_type === "dsa" ? (
            <div className="space-y-5 p-5 text-sm text-slate-300">
              <p className="leading-7">{currentProblem?.prompt}</p>
              <ProblemBlock title="Examples" items={(currentProblem?.examples || []).map((ex) => `Input: ${ex.input}\nOutput: ${ex.output}\n${ex.explanation || ""}`)} />
              <ProblemBlock title="Visible Test Cases" items={(currentProblem?.testcases || []).filter((tc) => tc.visible !== false).slice(0, 4).map((tc) => `stdin:\n${tc.input.trim()}\nexpected:\n${tc.expected_output}`)} />
              {currentProblem?.constraints?.length > 0 && <div><div className="mb-2 font-semibold text-slate-100">Constraints</div><ul className="grid gap-2 text-xs text-slate-400">{currentProblem.constraints.map((x) => <li key={x} className="rounded bg-slate-950 p-2">{x}</li>)}</ul></div>}
            </div>
          ) : (
            <div className="p-5 text-slate-300">Use the voice or text panel to answer. The interviewer will probe resume claims, project decisions, STAR stories, and contradictions.</div>
          )}
        </aside>

        <section className="h-[calc(100vh-96px)] min-h-0">
          <div className="h-full rounded border border-slate-800 bg-slate-900">
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <div className="flex items-center gap-2 font-semibold"><Code2 size={18} /> Code</div>
              <select className="w-40 py-2 text-sm" value={language} onChange={(e) => setLanguage(e.target.value)} aria-label="Coding language">
                <option value="python">Python</option>
                <option value="javascript">JavaScript</option>
                <option value="cpp">C++</option>
                <option value="c">C</option>
                <option value="java">Java</option>
              </select>
            </div>
            <div className="grid h-[calc(100%-57px)] grid-rows-[1fr_auto]">
              <Editor language={monacoLanguage(language)} theme="vs-dark" value={code} onChange={(value) => setCode(value || "")} onMount={onEditorMount} options={{ minimap: { enabled: false }, fontSize: 14 }} />
              <div className="grid gap-2 border-t border-slate-800 p-3">
                <div className="flex items-center justify-between">
                  <button onClick={submitCode} disabled={isBusy} className="inline-flex items-center gap-2 rounded bg-cyan-400 px-4 py-2 font-semibold text-slate-950 disabled:opacity-50"><Play size={17} /> Run tests & submit</button>
                  {codeResult && <span className="text-sm text-slate-300">{codeResult.passed_testcases}/{codeResult.total_testcases} tests passed - {codeResult.overall_score}% - {codeResult.language}</span>}
                </div>
                {codeResult && <div className="grid max-h-28 gap-2 overflow-y-auto md:grid-cols-2">{codeResult.testcase_results.map((tc, index) => <div key={`${tc.input}-${index}`} className={`rounded p-2 text-xs ${tc.passed ? "bg-emerald-950 text-emerald-100" : "bg-red-950 text-red-100"}`}><b>{tc.visible ? `Case ${index + 1}` : `Hidden ${index + 1}`}:</b> {tc.passed ? "Passed" : `${tc.stderr || `Expected ${tc.expected_output}, got ${tc.actual_output || "no output"}`}`}</div>)}</div>}
              </div>
            </div>
          </div>
        </section>

        {transcriptOpen && <aside className="fixed bottom-0 right-0 top-0 z-30 flex w-[420px] max-w-[96vw] flex-col border-l border-slate-700 bg-slate-950 shadow-2xl">
          <div className="flex items-center justify-between border-b border-slate-800 p-3">
            <span className="font-semibold">Interview Transcript</span>
            <button onClick={() => setTranscriptOpen(false)} className="rounded border border-slate-700 px-2 py-1 text-xs">Close</button>
          </div>
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
            {messages.map((m, i) => <div key={i} className={`rounded p-3 text-sm ${m.role === "candidate" ? "bg-slate-800" : "bg-cyan-950 text-cyan-50"}`}><b>{m.role === "candidate" ? "You" : "AI"}:</b> {m.content}</div>)}
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
            {messages.slice(-6).map((m, i) => <div key={i} className={`rounded p-3 text-sm ${m.role === "candidate" ? "bg-slate-800" : "bg-cyan-950 text-cyan-50"}`}><b>{m.role === "candidate" ? "You" : "AI"}:</b> {m.content}</div>)}
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

function Feedback({ report, onRestart }) {
  return <main className="min-h-screen bg-slate-950 p-6 text-slate-100"><section className="mx-auto max-w-5xl rounded border border-slate-800 bg-slate-900 p-6"><div className="flex items-start justify-between gap-4"><div><h1 className="text-2xl font-semibold">Interview Feedback Report</h1><p className="text-slate-400">{report.hiring_signal}</p></div><div className="text-right"><div className="text-4xl font-bold text-cyan-300">{report.overall_score}</div><div className="text-sm text-slate-400">overall</div></div></div><div className="mt-6 grid gap-4 md:grid-cols-5">{Object.entries(report.scores).map(([k, v]) => <div key={k} className="rounded bg-slate-950 p-3"><div className="text-xs uppercase text-slate-500">{k}</div><div className="text-xl font-semibold">{v}/4</div></div>)}</div><div className="mt-6 grid gap-5 md:grid-cols-2"><Block title="Weak Areas" items={report.weak_areas} /><Block title="Study Plan" items={report.study_plan} /><Block title="Integrity" items={[`${report.integrity.score}/100 integrity score`, `${report.integrity.violations.length} proctoring events logged`]} /><Block title="Behavioral Signals" items={Object.entries(report.behavioral_signals).map(([k, v]) => `${k}: ${v}`)} /></div><button onClick={onRestart} className="mt-6 rounded bg-cyan-400 px-4 py-2 font-semibold text-slate-950">Start another interview</button></section></main>
}

function Block({ title, items }) {
  return <div><h2 className="mb-2 font-semibold">{title}</h2><div className="space-y-2">{items.map((x) => <p key={x} className="rounded bg-slate-950 p-3 text-sm text-slate-300">{x}</p>)}</div></div>
}

async function postJson(path, body) {
  const res = await apiFetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

async function apiFetch(path, options = {}) {
  let lastError = null
  for (const base of API_BASES) {
    try {
      const res = await fetch(`${base}${path}`, options)
      if (res.status === 404 && base !== API_BASES[API_BASES.length - 1]) {
        lastError = new Error(`404 from ${base}${path}`)
        continue
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
  return { cpp: "cpp", c: "c", java: "java", javascript: "javascript", python: "python" }[selectedLanguage] || "plaintext"
}

function friendlyError(err) {
  const text = err?.message || String(err || "")
  if (text.includes("Failed to fetch")) return "API is not reachable after trying the /api proxy and direct local backend ports. Hard refresh the page and confirm /api/health opens."
  try {
    const parsed = JSON.parse(text)
    return parsed.detail || text
  } catch {
    return text.slice(0, 220)
  }
}

function isLikelyEcho(candidateText, aiText) {
  const candidate = normalizeSpeech(candidateText)
  const ai = normalizeSpeech(aiText)
  if (!candidate || !ai || candidate.length < 24) return false
  if (ai.includes(candidate) || candidate.includes(ai.slice(0, Math.min(ai.length, 120)))) return true
  const candidateWords = new Set(candidate.split(" ").filter((word) => word.length > 3))
  const aiWords = new Set(ai.split(" ").filter((word) => word.length > 3))
  if (candidateWords.size < 5) return false
  let overlap = 0
  candidateWords.forEach((word) => {
    if (aiWords.has(word)) overlap += 1
  })
  return overlap / candidateWords.size > 0.72
}

function normalizeSpeech(text) {
  return (text || "").toLowerCase().replace(/[^a-z0-9+ ]/g, " ").replace(/\s+/g, " ").trim()
}
