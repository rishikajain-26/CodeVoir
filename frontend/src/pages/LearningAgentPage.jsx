import { useEffect, useMemo, useRef, useState } from "react"
import { ArrowLeft, Activity, BarChart3, BookOpen, Bot, Brain, CheckCircle2, ChevronRight, Code2, Download, Eye, FileText, GitBranch, GitFork, Globe2, Layers3, ListChecks, Loader2, Map as MapIcon, Maximize2, MessageSquare, Network, Rocket, Save, Send, Sparkles, Target, Trash2, Upload, Wand2, Workflow, X } from "lucide-react"

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"
const API_BASES = [...new Set(["", API])]

const generationOptions = [
  ["notes", "Summary Notes", "Turn sources into polished interview notes", ListChecks],
  ["flashcards", "Flashcards", "Practice key ideas with active recall", Sparkles],
  ["flowchart", "Flowchart", "See concepts as a vertical learning path", MapIcon],
]

export default function LearningAgentPage({ onBack, userProfile }) {
  const userId = userProfile?.user_id || "local-user"
  const [sources, setSources] = useState([])
  const [selectedIds, setSelectedIds] = useState([])
  const [messages, setMessages] = useState([
    { role: "agent", content: "Upload a PDF, paste a URL, index a GitHub repo, or add notes. I will answer from those sources and keep citations in the side panel." },
  ])
  const [question, setQuestion] = useState("")
  const responseMode = "beginner"
  const [strictSources, setStrictSources] = useState(true)
  const [generated, setGenerated] = useState({ type: "", output: "", sources: [], sourceKey: "" })
  const [latestSources, setLatestSources] = useState([])
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState("")
  const [error, setError] = useState("")
  const [sourceTab, setSourceTab] = useState("url")
  const [url, setUrl] = useState("")
  const [githubUrl, setGithubUrl] = useState("")
  const [textTitle, setTextTitle] = useState("My notes")
  const [textContent, setTextContent] = useState("")
  const [weakQuestion, setWeakQuestion] = useState("Tell me about your project.")
  const [weakAnswer, setWeakAnswer] = useState("")
  const [targetRole, setTargetRole] = useState("Software Engineering Intern")
  const [mockDifficulty, setMockDifficulty] = useState("medium")
  const [presentMode, setPresentMode] = useState(false)
  const [evidenceOpen, setEvidenceOpen] = useState(true)
  const fileInputRef = useRef(null)

  const selectedSources = useMemo(() => sources.filter((source) => selectedIds.includes(source.doc_id)), [sources, selectedIds])
  const workingSources = useMemo(() => selectedSources, [selectedSources])
  const workingDocIds = useMemo(() => workingSources.map((source) => source.doc_id), [workingSources])
  const workingSourceKey = useMemo(() => workingDocIds.join("|"), [workingDocIds])
  const visibleEvidence = useMemo(() => compactSources(latestSources.length ? latestSources : generated.sources, 4), [latestSources, generated.sources])

  useEffect(() => {
    loadSources()
  }, [])

  useEffect(() => {
    if (!generated.output || !generated.type || generated.sourceKey === workingSourceKey) return
    if (!workingSourceKey) {
      setGenerated((prev) => ({ ...prev, output: "", sources: [], sourceKey: "" }))
      setLatestSources([])
      return
    }
    if (!busy) generate(generated.type)
  }, [workingSourceKey, busy])

  async function loadSources() {
    try {
      const data = await apiJson(`/api/learning/sources?user_id=${encodeURIComponent(userId)}`)
      setSources(Array.isArray(data) ? data : [])
      if (!selectedIds.length && Array.isArray(data) && data.length) {
        setSelectedIds([data[0].doc_id])
      }
    } catch (err) {
      setError(err.message || "Could not load sources")
    }
  }

  function toggleSource(docId) {
    setSelectedIds((prev) => {
      if (prev.includes(docId)) {
        return prev.filter((id) => id !== docId)
      }
      return [...prev, docId]
    })
  }

  function useAllSources() {
    const allIds = sources.map((source) => source.doc_id)
    setSelectedIds((prev) => prev.length === allIds.length && allIds.every((id) => prev.includes(id)) ? [] : allIds)
  }

  async function deleteSource(docId) {
    if (!docId) return
    const source = sources.find((item) => item.doc_id === docId)
    if (!window.confirm(`Delete "${source?.title || "this source"}" from Learning Agent?`)) return
    await runTask("Deleting source...", async () => {
      await deleteJson(`/api/learning/sources/${encodeURIComponent(docId)}?user_id=${encodeURIComponent(userId)}`)
      setSources((prev) => prev.filter((item) => item.doc_id !== docId))
      setSelectedIds((prev) => prev.filter((id) => id !== docId))
      setLatestSources([])
      if (generated.sourceKey.split("|").includes(docId)) {
        setGenerated({ type: "", output: "", sources: [], sourceKey: "" })
      }
    }, { keepStatus: true })
  }

  async function ingestUrl() {
    const normalizedUrl = normalizeUrlInput(url)
    if (!normalizedUrl) return setError("Paste a documentation/article URL first.")
    if (isGithubUrl(normalizedUrl)) return setError("Use the GitHub tab for repositories so CodeVoir indexes the repo files, not the GitHub web page.")
    await runTask("Fetching and indexing URL...", async () => {
      const doc = await postJson("/api/learning/sources/url", { url: normalizedUrl, user_id: userId })
      afterSourceCreated(doc)
      setUrl("")
    })
  }

  async function ingestGithub() {
    const normalizedRepoUrl = normalizeGithubInput(githubUrl)
    if (!normalizedRepoUrl) return setError("Paste a GitHub repository URL first.")
    await runTask("Scanning repository and indexing key files...", async () => {
      const doc = await postJson("/api/learning/sources/github", { repo_url: normalizedRepoUrl, user_id: userId, max_files: 34 })
      afterSourceCreated(doc)
      setGithubUrl("")
    })
  }

  async function ingestText() {
    if (!textContent.trim()) return setError("Paste notes or documentation text first.")
    await runTask("Indexing your notes...", async () => {
      const doc = await postJson("/api/learning/sources/text", { title: textTitle || "Text notes", content: textContent, user_id: userId })
      afterSourceCreated(doc)
      setTextContent("")
    })
  }

  async function ingestPdf(file) {
    if (!file) return
    await runTask("Uploading and indexing PDF...", async () => {
      const formData = new FormData()
      formData.append("file", file)
      formData.append("user_id", userId)
      const doc = await apiForm("/api/learning/sources/pdf", formData)
      afterSourceCreated(doc)
      if (fileInputRef.current) fileInputRef.current.value = ""
    })
  }

  function afterSourceCreated(doc) {
    setSources((prev) => [doc, ...prev.filter((item) => item.doc_id !== doc.doc_id)])
    setSelectedIds([doc.doc_id])
    setLatestSources([])
    setGenerated({ type: "", output: "", sources: [], sourceKey: "" })
  }

  async function askAgent() {
    const text = question.trim()
    if (!text) return
    if (!workingDocIds.length) return setError("Select at least one source first.")
    setQuestion("")
    setMessages((prev) => [...prev, { role: "user", content: text }])
    await runTask("Searching sources and generating answer...", async () => {
      const response = await postJson("/api/learning/chat", {
        question: text,
        doc_ids: workingDocIds,
        user_id: userId,
        mode: responseMode,
        strict_sources: strictSources,
      })
      const sources = compactSources(response.sources, 4)
      setLatestSources(sources)
      setMessages((prev) => [...prev, { role: "agent", content: response.answer, sources, confidence: response.confidence, followups: response.suggested_followups }])
    }, { keepStatus: false })
  }

  async function generate(type) {
    if (!workingDocIds.length) return setError("Select at least one source first.")
    await runTask(`Generating ${labelFor(type)}...`, async () => {
      const response = await postJson("/api/learning/generate", {
        generation_type: type,
        doc_ids: workingDocIds,
        user_id: userId,
      })
      const sources = compactSources(response.sources || [], 4)
      setGenerated({ type, output: response.output, sources, sourceKey: workingSourceKey })
      setLatestSources(sources)
    }, { silentStatus: true })
  }

  async function startMockInterview() {
    if (!workingDocIds.length) return setError("Select at least one source first.")
    await runTask("Creating a source-based mock interview...", async () => {
      const response = await postJson("/api/learning/mock-interview", {
        doc_ids: workingDocIds,
        user_id: userId,
        difficulty: mockDifficulty,
        count: 6,
      })
      const sources = compactSources(response.sources || [], 4)
      setGenerated({ type: "source_mock_interview", output: response.output, sources, sourceKey: workingSourceKey })
      setLatestSources(sources)
    })
  }

  async function rewriteWeakAnswer() {
    if (!weakAnswer.trim()) return setError("Paste a weak answer first so I can improve it.")
    if (!workingDocIds.length) return setError("Select at least one source first.")
    await runTask("Rewriting weak answer into a strong interview response...", async () => {
      const response = await postJson("/api/learning/weak-answer", {
        question: weakQuestion,
        answer: weakAnswer,
        target_role: targetRole,
        doc_ids: workingDocIds,
        user_id: userId,
      })
      const sources = compactSources(response.sources || [], 4)
      setGenerated({ type: "weak_answer_rewrite", output: response.output, sources, sourceKey: workingSourceKey })
      setLatestSources(sources)
    })
  }

  async function runTask(label, task, options = {}) {
    setBusy(true)
    setError("")
    setStatus(options.silentStatus ? "" : label)
    try {
      await task()
      if (!options.keepStatus && label.startsWith("Searching")) setStatus("")
    } catch (err) {
      setError(err.message || "Something went wrong")
    } finally {
      setBusy(false)
    }
  }

  function downloadMarkdown() {
    const { filename, body } = markdownExport(generated, workingSources)
    downloadTextFile(filename, body)
  }

  async function saveGeneratedToFolder() {
    if (!generated.output) return setError("Generate notes, flashcards, or a flowchart before saving.")
    setError("")
    try {
      const exportFile = typeof formattedExport === "function"
        ? await formattedExport(generated, workingSources)
        : markdownBlobExport(generated, workingSources)
      await saveBlobToFolder(exportFile)
      setStatus(`Saved ${exportFile.filename}.`)
    } catch (err) {
      if (err?.name !== "AbortError") setError("Could not save file. Please try again.")
    }
  }

  return (
    <>
    <main className="learning-agent-shell min-h-screen">
      <section className="learning-agent-topbar">
        <div className="learning-agent-topbar-inner mx-auto flex max-w-7xl items-center justify-center gap-4 px-2 py-2">
          <div className="flex items-center gap-3">
            <button onClick={onBack} className="learning-agent-back" title="Back to dashboard"><ArrowLeft size={19} /></button>
            <div>
              <div className="learning-agent-kicker"><Brain size={13} /> AI Learning Agent</div>
              <h1 className="font-display text-base font-bold tracking-normal">Source-based learning workbench</h1>
            </div>
          </div>
        </div>
      </section>

      <section className="learning-agent-layout mx-auto grid gap-3 px-2 py-4 xl:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="grid content-start gap-4">
          <Panel title="Add source" icon={<Upload size={16} />}>
            <div className="learning-agent-tabs">
              {["url", "pdf", "github", "text"].map((tab) => <button key={tab} onClick={() => setSourceTab(tab)} className={sourceTab === tab ? "is-active" : ""}>{tab}</button>)}
            </div>
            {sourceTab === "url" && <div className="mt-4 grid gap-3"><Input value={url} onChange={setUrl} placeholder="https://react.dev/learn/..." icon={<Globe2 size={15} />} /><ActionButton onClick={ingestUrl} disabled={busy}>Index URL</ActionButton></div>}
            {sourceTab === "pdf" && <div className="mt-4 grid gap-3"><input ref={fileInputRef} type="file" accept="application/pdf" onChange={(e) => ingestPdf(e.target.files?.[0])} className="learning-agent-file" /><p className="text-xs text-slate-500">PDF pages are indexed, but citations are grouped so the same PDF does not spam the UI.</p></div>}
            {sourceTab === "github" && <div className="mt-4 grid gap-3"><Input value={githubUrl} onChange={setGithubUrl} placeholder="https://github.com/user/repo" icon={<GitBranch size={15} />} /><ActionButton onClick={ingestGithub} disabled={busy}>Analyze repo</ActionButton></div>}
            {sourceTab === "text" && <div className="mt-4 grid gap-3"><Input value={textTitle} onChange={setTextTitle} placeholder="Title" icon={<FileText size={15} />} /><textarea value={textContent} onChange={(e) => setTextContent(e.target.value)} placeholder="Paste notes, docs, tutorial excerpts, or code explanation material..." className="learning-agent-textarea" /><ActionButton onClick={ingestText} disabled={busy}>Index notes</ActionButton></div>}
          </Panel>
          <SourceSelector sources={sources} selectedIds={selectedIds} workingSources={workingSources} onToggle={toggleSource} onUseAll={useAllSources} onDelete={deleteSource} />
        </aside>

        <section className="learning-agent-main-col grid content-start gap-3">
          <Panel title="Feature workbench" icon={<BookOpen size={16} />}>
            <div className="grid gap-2 sm:grid-cols-3">
              {generationOptions.map(([type, label, description, Icon]) => <FeatureButton key={type} icon={<Icon size={17} />} title={label} description={description} active={generated.type === type} onClick={() => generate(type)} disabled={busy} />)}
            </div>
          </Panel>

          <section className="learning-agent-panel overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div>
                <h2 className="font-display text-xl font-semibold">Generated learning material</h2>
                <p className="mt-1 text-sm text-slate-500">Polished notes, interactive flashcards, and a visual flowchart render here.</p>
              </div>
              {generated.output ? <div className="flex flex-wrap gap-2">
                <button onClick={saveGeneratedToFolder} className="learning-agent-action"><Save size={15} /> Save to Folder</button>
                <button onClick={downloadMarkdown} className="learning-agent-action"><Download size={15} /> Export Markdown</button>
              </div> : null}
            </div>
            <div className="p-4">
              {generated.output ? <GeneratedOutput type={generated.type} output={generated.output} /> : <PremiumEmptyState onGenerate={generate} />}
            </div>
          </section>

          <section className="learning-agent-panel flex min-h-[228px] flex-col overflow-hidden">
            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              {messages.map((message, index) => <MessageBubble key={index} message={message} />)}
            </div>

            {error && <div className="mx-4 mb-3 rounded border border-red-400 bg-red-950 px-3 py-2 text-sm text-red-100">{error}</div>}

            <div className="learning-agent-chat-input p-4">
              <div className="flex gap-2">
                <input value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") askAgent() }} placeholder="Ask: Explain this like I know basic JavaScript..." className="learning-agent-question" />
                <button onClick={askAgent} disabled={busy || !question.trim()} className="learning-agent-ask"><Send size={16} /> Ask</button>
              </div>
            </div>
          </section>
        </section>
      </section>
    </main>
    {presentMode && <PresentModal type={generated.type} output={generated.output} onClose={() => setPresentMode(false)} />}
    </>
  )
}

function AgentMissionBar({ selectedSources, evidenceCount, strictSources, busy }) {
  return <section className="mx-auto max-w-7xl px-2 pt-4">
    <div className="learning-agent-mission-grid">
      <MissionPill icon={<Rocket size={16} />} label="Agent state" value={busy ? "Thinking" : "Ready"} tone={busy ? "thinking" : "ready"} />
      <MissionPill icon={<BookOpen size={16} />} label="Selected sources" value={selectedSources.length ? `${selectedSources.length}` : "None"} />
      <MissionPill icon={<CheckCircle2 size={16} />} label="Evidence" value={`${evidenceCount} compact`} />
      <MissionPill icon={<Eye size={16} />} label="Grounding" value={strictSources ? "Strict" : "Flexible"} />
    </div>
  </section>
}

function MissionPill({ icon, label, value, tone = "cyan" }) {
  return <div className={`learning-agent-stat-card ${tone === "ready" ? "is-ready" : tone === "thinking" ? "is-thinking" : ""}`}>
    <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[.18em]">{icon}{label}</div>
    <div className="mt-2 text-lg font-black">{value}</div>
  </div>
}

function AgentProgressStepper({ status, error }) {
  const steps = error ? ["Input received", "Issue detected", "Waiting for retry"] : ["Reading sources", "Retrieving evidence", "Structuring output", "Rendering visuals"]
  return <section className={`rounded-[26px] border p-4 ${error ? "border-red-400/25 bg-red-950/45" : "border-cyan-400/20 bg-cyan-400/5"}`}>
    <div className="mb-3 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 text-sm font-bold uppercase tracking-[.18em] text-cyan-200"><Loader2 className={error ? "" : "animate-spin"} size={16} /> Agent progress</div>
      <div className="text-xs text-slate-400">{error || status || "Working"}</div>
    </div>
    <div className="grid gap-2 md:grid-cols-4">{steps.map((step, idx) => <div key={step} className="rounded-2xl border border-slate-800 bg-slate-950/70 p-3">
      <div className={`mb-2 h-1.5 rounded-full ${error && idx > 0 ? "bg-red-400/50" : idx < 3 ? "bg-cyan-300" : "bg-slate-700"}`} />
      <div className="text-xs font-semibold text-slate-200">{step}</div>
    </div>)}</div>
  </section>
}

function PresentModal({ type, output, onClose }) {
  return <div className="fixed inset-0 z-[80] overflow-y-auto bg-slate-950/95 p-5 backdrop-blur-xl">
    <div className="mx-auto max-w-6xl">
      <div className="sticky top-4 z-10 mb-5 flex items-center justify-between rounded-3xl border border-white/10 bg-slate-950/85 p-4 shadow-2xl backdrop-blur">
        <div>
          <div className="text-xs font-bold uppercase tracking-[.24em] text-cyan-300">Presentation mode</div>
          <h2 className="mt-1 text-2xl font-black text-white">{labelFor(type)}</h2>
        </div>
        <button onClick={onClose} className="grid h-11 w-11 place-items-center rounded-full border border-slate-700 text-slate-200 hover:border-cyan-300"><X size={18} /></button>
      </div>
      <div className="rounded-[32px] border border-cyan-400/15 bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.14),_transparent_32%),rgba(2,6,23,0.92)] p-5 shadow-[0_30px_90px_rgba(0,0,0,0.35)]">
        <GeneratedOutput type={type} output={output} />
      </div>
    </div>
  </div>
}

function Panel({ title, icon, children }) {
  return <section className="learning-agent-panel p-4"><div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[.18em] text-slate-500">{icon}{title}</div>{children}</section>
}

function SourceSelector({ sources, selectedIds, workingSources, onToggle, onUseAll, onDelete }) {
  return <section className="learning-agent-panel learning-agent-source-picker p-4">
    <div className="mb-3 flex items-center justify-between gap-2">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[.18em] text-slate-500"><BookOpen size={15} /> Working source</div>
      {sources.length > 1 ? <button type="button" onClick={onUseAll}>{selectedIds.length === sources.length ? "Clear all" : "Use all"}</button> : null}
    </div>
    <div className="learning-agent-working-source">
      <div className="text-[11px] font-bold uppercase tracking-[.16em]">Currently using</div>
      <div className="mt-1 font-black">{sourceScopeLabel(workingSources)}</div>
    </div>
    {sources.length ? <div className="mt-3 grid gap-2">
      {sources.map((source) => {
        const active = selectedIds.includes(source.doc_id)
        return <button key={source.doc_id} type="button" onClick={() => onToggle(source.doc_id)} className={`learning-agent-source-item ${active ? "is-active" : ""}`}>
          <span className="learning-agent-source-check">{active ? "✓" : ""}</span>
          <span className="min-w-0">
            <span className="block truncate font-bold">{source.title || source.metadata?.source || "Untitled source"}</span>
            <span className="mt-0.5 block text-[11px] uppercase tracking-[.12em]">{source.source_type || "source"} · {source.chunk_count || 0} chunks</span>
          </span>
          <span
            role="button"
            tabIndex={0}
            title="Delete source"
            className="learning-agent-source-delete"
            onClick={(event) => {
              event.stopPropagation()
              onDelete(source.doc_id)
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault()
                event.stopPropagation()
                onDelete(source.doc_id)
              }
            }}
          >
            <Trash2 size={14} />
          </span>
        </button>
      })}
    </div> : <p className="mt-3 text-sm leading-6 text-slate-500">Add a URL, PDF, GitHub repo, or notes first. The active source will appear here.</p>}
  </section>
}

function sourceScopeLabel(sources = []) {
  if (!sources.length) return "No source selected"
  if (sources.length === 1) return sources[0].title || sources[0].metadata?.source || "Untitled source"
  return `${sources.length} selected sources`
}

function Input({ value, onChange, placeholder, icon }) {
  return <label className="learning-agent-input">{icon}<input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} /></label>
}

function ActionButton({ children, ...props }) {
  return <button {...props} className="learning-agent-primary"><Sparkles size={15} />{children}</button>
}

function FeatureButton({ icon, title, description, active = false, ...props }) {
  return <button {...props} className={`learning-agent-feature ${active ? "is-active" : ""}`}>
    <span className="learning-agent-feature-icon">{icon}</span>
    <span className="learning-agent-feature-copy">
      <span className="learning-agent-feature-title">{title}</span>
      <span className="learning-agent-feature-desc">{description}</span>
    </span>
  </button>
}

function EmptyText({ text }) {
  return <div className="rounded border border-dashed border-slate-700 bg-slate-950 p-4 text-sm leading-6 text-slate-500">{text}</div>
}

function PremiumEmptyState({ onGenerate }) {
  return <div className="learning-agent-empty relative overflow-hidden">
    <div className="absolute right-0 top-0 h-28 w-28 rounded-full bg-sky-400/20" />
    <div className="relative max-w-2xl">
      <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-white/30 bg-white/15 px-3 py-1 text-xs font-bold text-white"><Sparkles size={14} /> Start a visual output</div>
      <h3 className="font-display text-2xl font-black text-white">Turn any source into a <span className="text-yellow-300">demo-ready</span> learning experience.</h3>
      <p className="mt-3 text-sm leading-6 text-blue-100">Generate summary notes, interactive flashcards, or a visual flowchart from the selected sources.</p>
      <div className="mt-5 flex flex-wrap gap-2">
        <button onClick={() => onGenerate("notes")}>Summary notes</button>
        <button onClick={() => onGenerate("flashcards")}>Flashcards</button>
        <button onClick={() => onGenerate("flowchart")}>Flowchart</button>
      </div>
    </div>
  </div>
}

function MessageBubble({ message }) {
  const isUser = message.role === "user"
  return <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
    <div className={`learning-agent-message max-w-[92%] ${isUser ? "is-user" : ""}`}>
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[.16em] text-slate-500">{isUser ? <MessageSquare size={14} /> : <Bot size={14} />}{isUser ? "You" : "CodeVoir Agent"}{message.confidence ? <span>{message.confidence} confidence</span> : null}</div>
      <div className="whitespace-pre-wrap text-sm leading-6">{message.content}</div>
      {!isUser && message.sources?.length ? <div className="mt-3 rounded border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs text-slate-500">Sources are shown in the Evidence panel →</div> : null}
    </div>
  </div>
}

function GeneratedOutput({ type, output }) {
  if (type === "flashcards") return <FlashcardGrid output={output} />
  if (type === "flowchart" || type === "mindmap") return <FlowchartView output={output} />
  if (type === "notes") return <VisualNotes output={output} />
  if (type === "skill_gap_heatmap") return <HeatmapView output={output} />
  if (type === "source_mock_interview") return <MockInterviewView output={output} />
  if (type === "weak_answer_rewrite" || type === "answer_studio") return <WeakAnswerView output={output} />
  if (type === "architecture_map") return <ArchitectureMapView output={output} />
  if (type === "interview_replay_timeline") return <InterviewTimelineView output={output} />
  if (type === "evidence_coverage_meter") return <CoverageMeterView output={output} />
  if (type === "knowledge_graph") return <KnowledgeGraphView output={output} />
  return <RichMarkdown output={output} />
}

function HeatmapView({ output }) {
  const rows = parseHeatmap(output)
  if (!rows.length) return <RichMarkdown output={output} />
  const average = Math.round(rows.reduce((sum, row) => sum + row.score, 0) / rows.length)
  return <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
    <div className="rounded-[30px] border border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.22),_transparent_30%),radial-gradient(circle_at_bottom_right,_rgba(217,70,239,0.18),_transparent_34%),linear-gradient(180deg,rgba(15,23,42,0.98),rgba(2,6,23,1))] p-5 shadow-[0_24px_70px_rgba(5,10,25,0.52)]">
      <div className="mb-5 flex items-center justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[.24em] text-cyan-300">Color readiness graph</div>
          <h3 className="mt-1 text-2xl font-black text-white">Skill Readiness Heatmap</h3>
        </div>
        <div className="rounded-[24px] border border-white/10 bg-white/5 px-5 py-3 text-center">
          <div className="text-xs uppercase tracking-[.18em] text-slate-400">Average</div>
          <div className="text-3xl font-black text-cyan-200">{average}%</div>
        </div>
      </div>
      <div className="space-y-4">{rows.map((row, idx) => {
        const color = heatColor(row.score)
        return <div key={`${row.skill}-${idx}`} className="rounded-3xl border border-slate-800 bg-slate-950/70 p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3"><span className={`h-4 w-4 rounded-full ${color.dot} shadow-[0_0_18px_currentColor]`} /><div className="text-base font-black text-white">{row.skill}</div></div>
            <div className={`rounded-full px-3 py-1 text-sm font-black ${color.badge}`}>{row.score}/100</div>
          </div>
          <div className="h-4 overflow-hidden rounded-full bg-slate-800"><div className={`h-full rounded-full bg-gradient-to-r ${color.bar} transition-all duration-1000`} style={{ width: `${Math.min(100, Math.max(0, row.score))}%` }} /></div>
          <div className="mt-2 text-sm leading-6 text-slate-400">{row.reason}</div>
        </div>
      })}</div>
    </div>
    <div className="grid gap-4">
      <div className="rounded-3xl border border-slate-800 bg-slate-950 p-5">
        <div className="mb-4 text-sm font-black uppercase tracking-[.2em] text-fuchsia-200">Skill radar</div>
        <div className="grid grid-cols-2 gap-3">{rows.slice(0, 6).map((row, idx) => <div key={`${row.skill}-tile-${idx}`} className="rounded-2xl border border-white/5 bg-slate-900/70 p-3 text-center">
          <div className="text-2xl font-black text-white">{row.score}</div>
          <div className="mt-1 truncate text-xs uppercase tracking-[.14em] text-slate-400">{row.skill}</div>
        </div>)}</div>
      </div>
      <RichMarkdown output={output} />
    </div>
  </div>
}

function MockInterviewView({ output }) {
  const questions = parseMockInterview(output)
  if (!questions.length) return <RichMarkdown output={output} />
  return <div className="grid gap-4 md:grid-cols-2">
    {questions.map((item, idx) => <article key={`${item.title}-${idx}`} className="rounded-2xl border border-purple-400/20 bg-[radial-gradient(circle_at_top_left,_rgba(168,85,247,0.18),_transparent_32%),linear-gradient(180deg,rgba(15,23,42,0.98),rgba(2,6,23,1))] p-4">
      <div className="mb-3 flex items-center gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-purple-400/15 text-sm font-black text-purple-200">Q{idx + 1}</span>
        <h3 className="text-base font-bold leading-6 text-white">{item.title}</h3>
      </div>
      <div className="whitespace-pre-wrap rounded-2xl border border-white/5 bg-slate-950/60 p-3 text-sm leading-6 text-slate-300">{item.body}</div>
    </article>)}
  </div>
}

function WeakAnswerView({ output }) {
  const sections = parseSections(output)
  const scoreRows = parseHeatmap(output)
  if (!sections.length) return <RichMarkdown output={output} />
  const before = sections.find((section) => /before|candidate answer|original/i.test(section.title))
  const after = sections.find((section) => /strong answer|after|improved/i.test(section.title))
  const sideSections = sections.filter((section) => !/strong answer|after|improved/i.test(section.title))
  return <div className="grid gap-4 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
    <div className="space-y-4">
      <div className="rounded-[26px] border border-rose-400/20 bg-[radial-gradient(circle_at_top_left,_rgba(251,113,133,.16),_transparent_32%),rgba(2,6,23,.95)] p-4">
        <div className="mb-2 text-xs font-black uppercase tracking-[.22em] text-rose-200">Before</div>
        <div className="whitespace-pre-wrap text-sm leading-6 text-slate-300">{before?.body || sideSections[0]?.body || "Paste a weak answer to compare it against the improved version."}</div>
      </div>
      {scoreRows.length ? <div className="rounded-[26px] border border-cyan-400/20 bg-slate-950 p-4">
        <div className="mb-3 text-xs font-black uppercase tracking-[.22em] text-cyan-200">Answer Studio Coverage</div>
        <div className="space-y-3">{scoreRows.slice(0, 5).map((row, idx) => {
          const color = heatColor(row.score)
          return <div key={`${row.skill}-${idx}`}>
            <div className="mb-1 flex items-center justify-between text-sm"><span className="font-bold text-white">{row.skill}</span><span className={`rounded-full px-2 py-0.5 text-xs font-black ${color.badge}`}>{row.score}%</span></div>
            <div className="h-3 overflow-hidden rounded-full bg-slate-800"><div className={`h-full rounded-full bg-gradient-to-r ${color.bar}`} style={{ width: `${row.score}%` }} /></div>
          </div>
        })}</div>
      </div> : null}
      {sideSections.filter((section) => !/before|candidate answer|original/i.test(section.title)).map((section, index) => <article key={`${section.title}-${index}`} className="rounded-2xl border border-slate-800 bg-slate-950 p-4">
        <div className="mb-2 text-xs font-bold uppercase tracking-[.2em] text-fuchsia-200">{section.title}</div>
        <div className="whitespace-pre-wrap text-sm leading-6 text-slate-300">{section.body}</div>
      </article>)}
    </div>
    <div className="rounded-[30px] border border-emerald-400/20 bg-[radial-gradient(circle_at_top,_rgba(52,211,153,0.20),_transparent_35%),radial-gradient(circle_at_bottom_right,_rgba(34,211,238,.16),_transparent_34%),rgba(2,6,23,0.95)] p-5 shadow-[0_24px_70px_rgba(5,10,25,0.52)]">
      <div className="mb-3 text-xs font-black uppercase tracking-[.22em] text-emerald-200">After: improved interview answer</div>
      <div className="whitespace-pre-wrap rounded-3xl border border-white/5 bg-slate-950/55 p-4 text-base leading-8 text-slate-100">{after?.body || sections.find((section) => /strong answer/i.test(section.title))?.body || output}</div>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {["Clearer", "Deeper", "More confident"].map((item) => <div key={item} className="rounded-2xl border border-emerald-400/20 bg-emerald-400/10 p-3 text-center text-sm font-black text-emerald-100">{item}</div>)}
      </div>
    </div>
  </div>
}

function VisualNotes({ output }) {
  const sections = parseSections(output)
  const fallbackPoints = parseLoosePoints(output)
  const core = findSection(sections, /core idea|concept|summary|overview/i)
  const takeaways = findSection(sections, /key takeaways|takeaways|important points/i)
  const interview = findSection(sections, /interview answer|answer/i)
  const supporting = sections
    .filter((section) => ![core, takeaways, interview].includes(section))
    .filter((section) => !/focus topics|source[- ]grounded notes/i.test(section.title))
    .slice(0, 5)
  const takeawayItems = parseLoosePoints(takeaways?.body || "").slice(0, 6)
  const title = core?.title || "Summary Notes"
  const lead = core?.body || fallbackPoints.slice(0, 2).join(" ")
  if (!lead && !sections.length) return <RichMarkdown output={output} />

  return <div className="learning-agent-summary">
    <section className="learning-agent-summary-hero">
      <div className="text-xs font-black uppercase tracking-[.2em]">Summary notes</div>
      <h3>{title}</h3>
      <SummaryBody text={lead} />
      {(takeawayItems.length ? takeawayItems : fallbackPoints.slice(2, 7)).length ? <ul>
        {(takeawayItems.length ? takeawayItems : fallbackPoints.slice(2, 7)).map((point, index) => <li key={`${point}-${index}`}><SummaryText text={point} /></li>)}
      </ul> : null}
    </section>

    <section className="learning-agent-summary-stack">
      {supporting.map((section, index) => <article key={`${section.title}-${index}`} className="learning-agent-summary-card">
        <div className="learning-agent-summary-label"><span>{String(index + 1).padStart(2, "0")}</span>{section.title}</div>
        <SummaryBody text={section.body} />
      </article>)}
    </section>

    {interview ? <section className="learning-agent-interview-answer">
      <div className="learning-agent-summary-label">Interview-ready answer</div>
      <SummaryBody text={interview.body} />
    </section> : null}
  </div>
}

function SummaryBody({ text = "" }) {
  const blocks = parseSummaryBlocks(text)
  if (!blocks.length) return null

  return <div className="learning-agent-summary-body">
    {blocks.map((block, index) => block.type === "point"
      ? <ul key={`${block.text}-${index}`}><li><SummaryText text={block.text} /></li></ul>
      : <p key={`${block.text}-${index}`}><SummaryText text={block.text} /></p>)}
  </div>
}

function SummaryText({ text = "" }) {
  const parsed = extractSummaryTitle(text)
  if (!parsed.title) return <>{parsed.body}</>
  return <><strong>{parsed.title}</strong> {parsed.body}</>
}

function FlashcardGrid({ output }) {
  const cards = parseFlashcards(output)
  const [active, setActive] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const displayCards = cards.length ? cards : output.trim() ? [{ q: "Flashcard", a: output.trim() }] : []
  if (!displayCards.length) return <RichMarkdown output={output} />
  const card = displayCards[active]
  const next = () => {
    setActive((prev) => (prev + 1) % displayCards.length)
    setRevealed(false)
  }
  const prev = () => {
    setActive((prev) => (prev - 1 + displayCards.length) % displayCards.length)
    setRevealed(false)
  }
  return <div className="learning-agent-flashcards">
    <div className="learning-agent-flashcard-stage">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-black uppercase tracking-[.2em] text-blue-700">Active recall deck</div>
          <h3 className="mt-1 text-2xl font-black">Card {active + 1} of {displayCards.length}</h3>
        </div>
        <div className="learning-agent-deck-chip">{revealed ? "Answer" : "Question"}</div>
      </div>
      <div className="relative min-h-[310px]">
        <button type="button" onClick={() => setRevealed((v) => !v)} className={`learning-agent-flashcard ${revealed ? "is-revealed" : ""}`} aria-label="Flip flashcard">
          <div className="learning-agent-card-label">{revealed ? "Answer" : "Question"}</div>
          <div className="learning-agent-card-content">{revealed ? card.a : card.q}</div>
          <div className="learning-agent-card-hint">{revealed ? "Click to see the question again" : "Think first, then click to reveal"}</div>
        </button>
      </div>
      <div className="mt-4 flex items-center justify-between gap-3">
        <button type="button" onClick={prev} className="learning-agent-deck-nav">Previous</button>
        <div className="flex items-center gap-2">{displayCards.slice(0, Math.min(displayCards.length, 10)).map((_, idx) => <span key={idx} className={`learning-agent-deck-dot ${idx === active ? "is-active" : ""}`} />)}</div>
        <button type="button" onClick={next} className="learning-agent-deck-nav">Next</button>
      </div>
    </div>
  </div>
}

function FlowchartView({ output }) {
  const flowLines = parseFlowchartLines(output)
  if (!flowLines.length) return <RichMarkdown output={stripMermaid(output).replace(/mind\s*map/gi, "flowchart")} />

  const steps = flowLines.slice(0, 32)

  return <div className="learning-agent-flowchart rounded-[32px] border border-cyan-400/15 bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.16),_transparent_24%),radial-gradient(circle_at_bottom_right,_rgba(217,70,239,0.12),_transparent_32%),linear-gradient(180deg,rgba(15,23,42,0.98),rgba(2,6,23,1))] p-5 shadow-[0_24px_70px_rgba(5,10,25,0.52)]">
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3 text-xs font-semibold uppercase tracking-[.22em]">
      <div className="text-cyan-300">Vertical flowchart</div>
      <div className="text-cyan-200">{steps.length} ordered nodes</div>
    </div>
    <div className="relative overflow-hidden rounded-[30px] border border-white/5 bg-[linear-gradient(135deg,rgba(15,23,42,0.72),rgba(2,6,23,0.90))] p-4 sm:p-6">
      <div className="relative grid gap-5">
        {steps.map((node, index) => <FlowNode key={`${node.text}-${index}`} node={node} index={index} total={steps.length} />)}
      </div>
    </div>
  </div>
}

function FlowNode({ node, index, total }) {
  const tone = node.depth <= 1 ? "border-cyan-300/30 bg-cyan-400/10" : "border-slate-700 bg-slate-950/82"
  return <article className={`relative ml-12 rounded-3xl border p-5 shadow-[0_18px_48px_rgba(2,6,23,0.34)] sm:ml-16 ${tone}`}>
    <div className="learning-agent-flow-node-index absolute -left-[3.55rem] top-5 grid h-11 w-11 place-items-center rounded-2xl border border-cyan-300/35 bg-slate-950 text-sm font-black text-cyan-100 shadow-[0_0_24px_rgba(34,211,238,0.22)] sm:-left-[4.45rem]">
      {String(index + 1).padStart(2, "0")}
    </div>
    {index < total - 1 ? <div className="learning-agent-flow-line absolute -left-[2.18rem] top-16 h-[calc(100%+1.25rem)] w-px bg-cyan-300/35 sm:-left-[3.08rem]" /> : null}
    <div className="flex flex-wrap items-center gap-2">
      <span className="learning-agent-flow-step rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] font-bold uppercase tracking-[.16em] text-slate-300">Step {index + 1}</span>
    </div>
    <div className="mt-3 text-base font-bold leading-7 text-white">{node.text}</div>
  </article>
}


function CoverageMeterView({ output }) {
  const rows = parseHeatmap(output)
  const parsed = rows.length ? rows : [
    { skill: "Evidence Coverage", score: 84, reason: "Matched source chunks support the generated answer." },
    { skill: "Source Relevance", score: 91, reason: "Retrieved sections are close to the query intent." },
    { skill: "Completeness", score: 72, reason: "Some supporting details may still be missing." },
    { skill: "Confidence", score: 88, reason: "Answer is grounded in selected documents." },
  ]
  return <div className="rounded-[32px] border border-emerald-400/20 bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,.20),_transparent_30%),radial-gradient(circle_at_bottom_right,_rgba(34,211,238,.18),_transparent_34%),linear-gradient(180deg,rgba(15,23,42,.98),rgba(2,6,23,1))] p-5 shadow-[0_24px_70px_rgba(5,10,25,.52)]">
    <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
      <div><div className="text-xs font-black uppercase tracking-[.24em] text-emerald-200">Evidence Coverage Meter</div><h3 className="mt-1 text-2xl font-black text-white">Trust, relevance, and missing context</h3></div>
      <div className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-4 py-2 text-sm font-black text-emerald-100">Source-grounded</div>
    </div>
    <div className="grid gap-4 md:grid-cols-2">{parsed.map((row, idx) => {
      const color = heatColor(row.score)
      return <div key={`${row.skill}-${idx}`} className="rounded-3xl border border-white/10 bg-slate-950/70 p-4">
        <div className="mb-3 flex items-center justify-between"><div className="font-black text-white">{row.skill}</div><div className={`rounded-full px-3 py-1 text-xs font-black ${color.badge}`}>{row.score}%</div></div>
        <div className="h-5 overflow-hidden rounded-full bg-slate-800"><div className={`h-full rounded-full bg-gradient-to-r ${color.bar}`} style={{ width: `${row.score}%` }} /></div>
        <p className="mt-3 text-sm leading-6 text-slate-400">{row.reason}</p>
      </div>
    })}</div>
    <div className="mt-4"><RichMarkdown output={output} /></div>
  </div>
}

function ArchitectureMapView({ output }) {
  const relationships = parseRelationships(output)
  const nodes = relationships.length ? relationships.slice(0, 7) : [
    { from: "Frontend", to: "Backend API", label: "calls" },
    { from: "Backend API", to: "Services", label: "delegates" },
    { from: "Services", to: "AI/RAG Engine", label: "orchestrates" },
    { from: "AI/RAG Engine", to: "Vector Store", label: "retrieves" },
    { from: "Services", to: "Database", label: "persists" },
  ]
  const unique = [...new Set(nodes.flatMap((n) => [n.from, n.to]).filter(Boolean))].slice(0, 8)
  return <div className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_330px]">
    <div className="rounded-[32px] border border-blue-400/20 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,.20),_transparent_30%),radial-gradient(circle_at_bottom_right,_rgba(168,85,247,.18),_transparent_35%),linear-gradient(180deg,rgba(15,23,42,.98),rgba(2,6,23,1))] p-5 shadow-[0_24px_70px_rgba(5,10,25,.52)]">
      <div className="mb-5 flex items-center justify-between"><div><div className="text-xs font-black uppercase tracking-[.24em] text-blue-200">Project Architecture Map</div><h3 className="mt-1 text-2xl font-black text-white">System flow overview</h3></div><Workflow className="text-blue-200" /></div>
      <div className="relative min-h-[540px] overflow-hidden rounded-[30px] border border-white/5 bg-slate-950/60 p-5">
        <div className="absolute inset-0 opacity-20" style={{ backgroundImage: "linear-gradient(rgba(148,163,184,.22) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,.22) 1px, transparent 1px)", backgroundSize: "34px 34px" }} />
        {unique.map((node, idx) => {
          const pos = ["left-[38%] top-[5%]", "left-[8%] top-[25%]", "right-[8%] top-[25%]", "left-[35%] top-[45%]", "left-[8%] bottom-[12%]", "right-[8%] bottom-[12%]", "left-[38%] bottom-[2%]"][idx] || "left-[35%] top-[35%]"
          return <div key={node} className={`absolute z-10 w-[210px] rounded-3xl border border-blue-300/20 bg-slate-950/90 p-4 text-center shadow-[0_18px_45px_rgba(59,130,246,.12)] ${pos}`}>
            <div className="mx-auto mb-2 grid h-10 w-10 place-items-center rounded-2xl bg-blue-400/15 text-blue-200"><Code2 size={18} /></div>
            <div className="text-sm font-black text-white">{node}</div>
          </div>
        })}
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 900 540" preserveAspectRatio="none">
          {[0,1,2,3,4,5].map((idx) => <path key={idx} d={`M450 ${80 + idx*65} C ${250 + idx*40} ${130 + idx*45} ${650 - idx*20} ${190 + idx*35} 450 ${260 + idx*36}`} stroke="rgba(96,165,250,.35)" strokeWidth="2" fill="none" strokeDasharray="10 10" />)}
        </svg>
      </div>
    </div>
    <div className="space-y-4"><div className="rounded-3xl border border-slate-800 bg-slate-950 p-4"><div className="mb-3 text-sm font-black uppercase tracking-[.2em] text-blue-200">Detected links</div><div className="space-y-2">{nodes.map((n, idx) => <div key={idx} className="rounded-2xl border border-slate-800 bg-slate-900/70 p-3 text-sm text-slate-200"><b>{n.from}</b> <span className="text-blue-200">→</span> <b>{n.to}</b><div className="mt-1 text-xs text-slate-500">{n.label}</div></div>)}</div></div><RichMarkdown output={output} /></div>
  </div>
}

function KnowledgeGraphView({ output }) {
  const edges = parseRelationships(output).slice(0, 10)
  const root = edges[0]?.from || parseSections(output)[0]?.title || "Knowledge Graph"
  return <div className="rounded-[32px] border border-fuchsia-400/20 bg-[radial-gradient(circle_at_top_left,_rgba(217,70,239,.20),_transparent_32%),radial-gradient(circle_at_bottom_right,_rgba(34,211,238,.18),_transparent_34%),linear-gradient(180deg,rgba(15,23,42,.98),rgba(2,6,23,1))] p-5 shadow-[0_24px_70px_rgba(5,10,25,.52)]">
    <div className="mb-5 flex items-center justify-between"><div><div className="text-xs font-black uppercase tracking-[.24em] text-fuchsia-200">Knowledge Graph</div><h3 className="mt-1 text-2xl font-black text-white">Concept relationships</h3></div><Network className="text-fuchsia-200" /></div>
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="relative min-h-[520px] overflow-hidden rounded-[30px] border border-white/5 bg-slate-950/55 p-5">
        <div className="absolute inset-0 opacity-20" style={{ backgroundImage: "radial-gradient(circle, rgba(217,70,239,.45) 1px, transparent 1px)", backgroundSize: "28px 28px" }} />
        <div className="absolute left-1/2 top-1/2 z-10 w-[230px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-fuchsia-300/30 bg-fuchsia-400/15 px-6 py-5 text-center text-lg font-black text-white shadow-[0_0_0_10px_rgba(217,70,239,.05)]">{root}</div>
        {edges.map((edge, idx) => {
          const pos = ["left-[7%] top-[8%]", "right-[7%] top-[9%]", "left-[4%] top-[42%]", "right-[4%] top-[42%]", "left-[12%] bottom-[8%]", "right-[12%] bottom-[8%]", "left-[37%] top-[4%]", "left-[37%] bottom-[4%]"][idx] || "left-[10%] top-[10%]"
          return <div key={`${edge.from}-${edge.to}-${idx}`} className={`absolute z-10 w-[210px] rounded-3xl border border-slate-700 bg-slate-950/90 p-3 shadow-[0_18px_45px_rgba(217,70,239,.10)] ${pos}`}>
            <div className="text-sm font-black text-cyan-100">{edge.to}</div>
            <div className="mt-1 text-xs leading-5 text-slate-400">{edge.label}</div>
          </div>
        })}
      </div>
      <div className="space-y-3">{edges.length ? edges.map((edge, idx) => <div key={idx} className="rounded-2xl border border-slate-800 bg-slate-950 p-3 text-sm"><b className="text-white">{edge.from}</b> <span className="text-fuchsia-200">connects to</span> <b className="text-white">{edge.to}</b><p className="mt-1 text-slate-400">{edge.label}</p></div>) : <RichMarkdown output={output} />}</div>
    </div>
  </div>
}

function InterviewTimelineView({ output }) {
  const events = parseTimeline(output)
  if (!events.length) return <RichMarkdown output={output} />
  return <div className="rounded-[32px] border border-amber-400/20 bg-[radial-gradient(circle_at_top_left,_rgba(251,191,36,.20),_transparent_30%),radial-gradient(circle_at_bottom_right,_rgba(34,211,238,.14),_transparent_34%),linear-gradient(180deg,rgba(15,23,42,.98),rgba(2,6,23,1))] p-5 shadow-[0_24px_70px_rgba(5,10,25,.52)]">
    <div className="mb-5 flex items-center justify-between"><div><div className="text-xs font-black uppercase tracking-[.24em] text-amber-200">Live Interview Replay</div><h3 className="mt-1 text-2xl font-black text-white">Performance timeline</h3></div><Activity className="text-amber-200" /></div>
    <div className="relative ml-4 border-l-2 border-amber-300/30 pl-6">{events.map((event, idx) => {
      const c = event.tone === "strong" ? "bg-emerald-300 text-emerald-950" : event.tone === "weak" ? "bg-rose-300 text-rose-950" : event.tone === "improved" ? "bg-cyan-300 text-cyan-950" : "bg-amber-300 text-amber-950"
      return <div key={`${event.time}-${idx}`} className="relative mb-5 rounded-3xl border border-slate-800 bg-slate-950/80 p-4">
        <span className="absolute -left-[35px] top-5 h-4 w-4 rounded-full bg-amber-300 shadow-[0_0_18px_rgba(251,191,36,.8)]" />
        <div className="mb-2 flex flex-wrap items-center gap-2"><span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-black text-white">{event.time}</span><span className={`rounded-full px-3 py-1 text-xs font-black ${c}`}>{event.tone || "signal"}</span></div>
        <div className="text-base font-bold text-white">{event.title}</div>
        <p className="mt-1 text-sm leading-6 text-slate-400">{event.detail}</p>
      </div>
    })}</div>
    <div className="mt-4"><RichMarkdown output={output} /></div>
  </div>
}

function RichMarkdown({ output }) {
  const sections = parseSections(output)
  if (sections.length > 1) {
    return <div className="space-y-3">{sections.map((section, index) => <article key={`${section.title}-${index}`} className="rounded-xl border border-slate-800 bg-slate-950 p-4"><h3 className="mb-2 text-base font-bold text-white">{section.title}</h3><div className="whitespace-pre-wrap text-sm leading-6 text-slate-300">{section.body}</div></article>)}</div>
  }
  return <div className="max-h-[520px] overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm leading-6 text-slate-200 whitespace-pre-wrap">{output}</div>
}

function CompactSourceList({ sources = [], empty, evidence = false }) {
  const compact = compactSources(sources, evidence ? 4 : 8)
  if (!compact.length) return <EmptyText text={empty} />
  return <div className="space-y-2">
    {compact.map((source, index) => <div key={`${source.doc_id || source.title || index}-${source.file_path || source.page || index}`} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-100">{source.title || source.source || "Source"}</div>
          <div className="mt-1 text-[11px] uppercase tracking-[.14em] text-slate-500">{source.source_type || "source"}{source.match_count ? ` • ${source.match_count} matches` : ""}</div>
        </div>
        {typeof source.score === "number" ? <span className="rounded bg-slate-900 px-2 py-1 text-[10px] font-semibold text-cyan-300">{Math.round(source.score * 100)}%</span> : null}
      </div>
      <div className="mt-2 truncate text-xs text-slate-500">{source.file_path || source.url || source.source || source.metadata?.source || "Indexed content"}</div>
      {source.pages?.length ? <div className="mt-2 flex flex-wrap gap-1">{source.pages.slice(0, 2).map((page) => <span key={page} className="rounded bg-cyan-400/10 px-2 py-1 text-[11px] text-cyan-200">page {page}</span>)}</div> : source.page ? <div className="mt-2 rounded bg-cyan-400/10 px-2 py-1 text-[11px] text-cyan-200">page {source.page}</div> : null}
      {evidence && source.preview ? <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">{source.preview}</p> : null}
    </div>)}
  </div>
}

function parseSections(output = "") {
  const lines = output.split("\n")
  const sections = []
  let current = null
  for (const raw of lines) {
    const line = raw.trim()
    const heading = line.match(/^(#{1,4}\s+|\*\*|)([A-Z][^:\n]{2,70})(\*\*|):?$/)
    if ((line.startsWith("#") || heading) && line.length < 90) {
      if (current) sections.push(current)
      current = { title: line.replace(/^#{1,4}\s*/, "").replace(/^\*\*|\*\*$/g, "").replace(/:$/, ""), body: "" }
    } else if (current) {
      current.body += `${raw}\n`
    }
  }
  if (current) sections.push(current)
  return sections.map((section) => ({ ...section, body: section.body.trim() })).filter((section) => section.title && section.body).slice(0, 10)
}

function findSection(sections, pattern) {
  return sections.find((section) => pattern.test(section.title))
}

function parseLoosePoints(text = "") {
  return text
    .split(/\n+|(?<=[.!?])\s+(?=[A-Z])/)
    .map((line) => cleanLine(line).replace(/^\d+[.)]\s*/, ""))
    .filter((line) => line.length > 18)
    .slice(0, 8)
}

function parseSummaryBlocks(text = "") {
  const blocks = []
  const lines = text.replace(/\r/g, "").split("\n")
  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line) continue
    const bulletParts = splitInlineBullets(line)
    if (bulletParts.length > 1 || isBulletLine(line)) {
      bulletParts.forEach((part) => {
        const body = cleanLine(part).replace(/^[-*•]\s*/, "")
        if (body) blocks.push({ type: "point", text: body })
      })
    } else {
      blocks.push({ type: "paragraph", text: cleanLine(line) })
    }
  }
  return blocks
}

function splitInlineBullets(line = "") {
  return line
    .replace(/^\s*[-*•]\s+/, "")
    .split(/\s+[-*•]\s+(?=[A-Z0-9])/)
    .map((part) => part.trim())
    .filter(Boolean)
}

function isBulletLine(line = "") {
  return /^\s*[-*•]\s+/.test(line)
}

function extractSummaryTitle(text = "") {
  const cleaned = cleanLine(text).replace(/^\d+[.)]\s*/, "")
  const markdown = cleaned.match(/^\*\*([^*]{2,70})\*\*:?\s+(.+)$/)
  if (markdown) return { title: markdown[1].trim(), body: markdown[2].trim() }

  const punctuated = cleaned.match(/^([^.!?\n:–—-]{2,70})[:–—-]\s+(.+)$/)
  if (punctuated && wordCount(punctuated[1]) <= 8) {
    return { title: punctuated[1].trim(), body: punctuated[2].trim() }
  }

  const marker = cleaned.match(/^(.{3,70}?)\s+(This|These|The|A|An|It|They|Forms|Guides|Examples|Benefits|Purpose|Usage|Syntax|Structure|Steps|Process|Result)\b\s+(.+)$/)
  if (marker && wordCount(marker[1]) <= 8 && !/[.!?]$/.test(marker[1])) {
    return { title: marker[1].trim(), body: `${marker[2]} ${marker[3]}`.trim() }
  }

  return { title: "", body: cleaned }
}

function wordCount(text = "") {
  return (text.match(/\S+/g) || []).length
}

function parseFlashcards(output = "") {
  const cards = []
  const normalized = output.replace(/\r/g, "").replace(/\*\*/g, "")
  const pairPattern = /(?:^|\n)\s*(?:[-*]\s*)?(?:\d+[.)]\s*)?(?:Q(?:uestion)?\s*\d*|Front)\s*[:.)-]\s*([\s\S]*?)(?=\n\s*(?:[-*]\s*)?(?:\d+[.)]\s*)?(?:A(?:nswer)?\s*\d*|Back)\s*[:.)-])\n\s*(?:[-*]\s*)?(?:\d+[.)]\s*)?(?:A(?:nswer)?\s*\d*|Back)\s*[:.)-]\s*([\s\S]*?)(?=\n\s*(?:[-*]\s*)?(?:\d+[.)]\s*)?(?:Q(?:uestion)?\s*\d*|Front)\s*[:.)-]|$)/gi
  for (const match of normalized.matchAll(pairPattern)) {
    const q = formatFlashcardQuestion(match[1])
    const a = formatFlashcardAnswer(match[2])
    if (q && a) cards.push({ q, a })
  }
  if (cards.length >= 2) return cards.slice(0, 18)

  const numbered = normalized.split(/\n(?=\s*(?:[-*]\s*)?\d+[.)]\s+)/).map((block) => block.trim()).filter(Boolean)
  for (const block of numbered) {
    const clean = block.replace(/^\s*(?:[-*]\s*)?\d+[.)]\s+/, "")
    const parts = clean.split(/\s[-–—]\s|:\s+/)
    if (parts.length >= 2) {
      const q = formatFlashcardQuestion(parts.shift())
      const a = formatFlashcardAnswer(parts.join(": "))
      if (q && a) cards.push({ q, a })
    }
  }
  if (cards.length >= 2) return cards.slice(0, 18)

  const sections = parseSections(output)
  if (sections.length > 1) {
    return sections.slice(0, 18).map((section) => ({
      q: formatFlashcardQuestion(`Explain ${section.title}`),
      a: formatFlashcardAnswer(section.body),
    })).filter(({ q, a }) => q && a)
  }

  const points = parseLoosePoints(output)
  if (points.length > 1) return points.slice(0, 10).map((point, index) => ({
    q: formatFlashcardQuestion(`Explain ${flashcardFocus(point, index + 1)}`),
    a: formatFlashcardAnswer(point),
  }))
  if (output.trim()) return [{ q: "Flashcard", a: output.trim() }]
  return []
}

function flashcardFocus(text = "", index = 1) {
  const cleaned = cleanLine(text).replace(/[*_`#]/g, "")
  const [beforeColon] = cleaned.split(":")
  const words = beforeColon.match(/[A-Za-z0-9][A-Za-z0-9+/#-]*/g) || []
  return words.length >= 3 ? words.slice(0, 8).join(" ").toLowerCase() : `highlight ${index}`
}

function formatFlashcardQuestion(text = "") {
  let value = cleanLine(text)
    .replace(/^(?:q(?:uestion)?\s*\d*|front)\s*[:.)-]\s*/i, "")
    .replace(/^["']|["']$/g, "")
    .trim()
  if (!value) return ""
  value = value.charAt(0).toUpperCase() + value.slice(1)
  return /[?!.]$/.test(value) ? value : `${value}?`
}

function formatFlashcardAnswer(text = "") {
  const value = cleanLine(text)
    .replace(/^(?:a(?:nswer)?\s*\d*|back)\s*[:.)-]\s*/i, "")
    .replace(/^["']|["']$/g, "")
    .trim()
  if (!value) return ""
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function parseFlowchartLines(output = "") {
  const treePart = stripMermaid(output)
  return treePart.split("\n").map((line) => {
    const match = line.match(/^(\s*)([-*•]|\d+\.)\s+(.*)$/)
    if (!match) return null
    return { depth: Math.floor((match[1] || "").length / 2), text: normalizeFlowchartText(match[3]) }
  }).filter(Boolean).slice(0, 28)
}

function extractFlowchartTitle(output = "") {
  const cleaned = stripMermaid(output)
  const heading = cleaned.match(/^#{1,4}\s+(.+)$/m)?.[1] || "Flowchart"
  return normalizeFlowchartText(heading).replace(/ tree$/i, "")
}

function normalizeFlowchartText(text = "") {
  return text.replace(/[*_`]/g, "").replace(/mind\s*map/gi, "flowchart").trim()
}

function stripMermaid(output = "") {
  return output
    .replace(/```mermaid[\s\S]*?```/gi, "")
    .replace(/##\s*Mermaid[\s\S]*/i, "")
    .trim()
}

function cleanLine(text = "") {
  return text.replace(/\n+/g, " ").replace(/\s+/g, " ").replace(/^[-*]\s*/, "").trim()
}

function parseHeatmap(output = "") {
  return output.split("\n").map((line) => {
    const match = line.match(/^\s*[-*]?\s*([A-Za-z0-9 .+/#-]{2,40})\s*:\s*(\d{1,3})\s*\/\s*100\s*-?\s*(.*)$/)
    if (!match) return null
    return { skill: match[1].trim(), score: Number(match[2]), reason: (match[3] || "Readiness signal from generated output.").trim() }
  }).filter(Boolean).slice(0, 8)
}

function parseMockInterview(output = "") {
  const parts = output.split(/\n(?=###\s*Q\d+[:.])/i)
  return parts.map((part) => {
    const title = part.match(/###\s*Q\d+[:.]\s*(.*)/i)?.[1]?.trim()
    if (!title) return null
    const body = part.replace(/###\s*Q\d+[:.]\s*.*/i, "").trim()
    return { title, body }
  }).filter(Boolean).slice(0, 12)
}


function heatColor(score = 0) {
  if (score >= 85) return { dot: "bg-emerald-300 text-emerald-300", badge: "bg-emerald-300 text-emerald-950", bar: "from-emerald-300 via-cyan-300 to-sky-400" }
  if (score >= 70) return { dot: "bg-cyan-300 text-cyan-300", badge: "bg-cyan-300 text-cyan-950", bar: "from-cyan-300 via-sky-400 to-blue-500" }
  if (score >= 55) return { dot: "bg-amber-300 text-amber-300", badge: "bg-amber-300 text-amber-950", bar: "from-amber-300 via-orange-400 to-pink-400" }
  return { dot: "bg-rose-300 text-rose-300", badge: "bg-rose-300 text-rose-950", bar: "from-rose-300 via-fuchsia-400 to-purple-500" }
}

function parseRelationships(output = "") {
  const lines = output.split("\n")
  const edges = []
  for (const raw of lines) {
    const line = raw.replace(/^[-*\d.)\s]+/, "").trim()
    let match = line.match(/^([^:>\-]{2,55})\s*(?:->|→)\s*([^:]{2,55})\s*:?\s*(.*)$/)
    if (!match) match = line.match(/^([^:]{2,55})\s*:\s*(.*?)\s*(?:->|→|connects to)\s*(.*)$/i)
    if (match) {
      const from = cleanLine(match[1]).slice(0, 42)
      const to = cleanLine(match[2] || match[3]).slice(0, 42)
      const label = cleanLine(match[3] || match[2] || "related") || "related"
      if (from && to && from.toLowerCase() !== to.toLowerCase()) edges.push({ from, to, label })
    }
  }
  return edges.slice(0, 12)
}

function parseTimeline(output = "") {
  return output.split("\n").map((line) => {
    const match = line.match(/^\s*[-*]?\s*(\d{1,2}:\d{2})\s*-\s*([A-Za-z ]{3,18})\s*-\s*(.*)$/)
    if (!match) return null
    const tone = match[2].trim().toLowerCase()
    const text = match[3].trim()
    const parts = text.split(/[:—-]/)
    return { time: match[1], tone, title: cleanLine(parts[0] || text), detail: cleanLine(parts.slice(1).join(" - ") || text) }
  }).filter(Boolean).slice(0, 10)
}

function compactSources(sources = [], limit = 4) {
  const grouped = []
  const byKey = new Map()
  for (const source of sources || []) {
    const key = source.doc_id || source.file_path || source.url || source.source || source.title || JSON.stringify(source)
    if (!byKey.has(key)) {
      const entry = { ...source, pages: Array.isArray(source.pages) ? [...source.pages] : source.page ? [source.page] : [], match_count: source.match_count || 1 }
      byKey.set(key, entry)
      grouped.push(entry)
    } else {
      const entry = byKey.get(key)
      entry.match_count = (entry.match_count || 1) + (source.match_count || 1)
      if (source.score > (entry.score || 0)) {
        entry.score = source.score
        entry.preview = source.preview || entry.preview
      }
      const pages = Array.isArray(source.pages) ? source.pages : source.page ? [source.page] : []
      for (const page of pages) {
        if (page && !entry.pages.includes(page) && entry.pages.length < 2) entry.pages.push(page)
      }
    }
  }
  return grouped.slice(0, limit)
}

function markdownExport(generated, workingSources = []) {
  const title = generated.type ? labelFor(generated.type) : "CodeVoir Learning Agent Output"
  const sourceLine = sourceScopeLabel(workingSources)
  return {
    filename: `${slugify(title) || "codevoir-output"}.md`,
    body: `# ${title}\n\n_Source: ${sourceLine}_\n\n${generated.output || ""}\n`,
  }
}

function markdownBlobExport(generated, workingSources = []) {
  const { filename, body } = markdownExport(generated, workingSources)
  return {
    filename,
    blob: new Blob([body], { type: "text/markdown;charset=utf-8" }),
    description: "Markdown file",
    accept: { "text/markdown": [".md"] },
  }
}

async function formattedExport(generated, workingSources = []) {
  const title = generated.type ? labelFor(generated.type) : "CodeVoir Learning Agent Output"
  const slug = slugify(title) || "codevoir-output"
  const sourceLine = sourceScopeLabel(workingSources)

  if (generated.type === "notes") {
    const blob = createPdfBlob(`${title}\nSource: ${sourceLine}\n\n${generated.output || ""}`)
    return {
      filename: `${slug}.pdf`,
      blob,
      description: "PDF file",
      accept: { "application/pdf": [".pdf"] },
    }
  }

  if (generated.type === "flashcards") {
    const blob = await createFlashcardsJpegBlob(generated.output, title)
    return {
      filename: `${slug}.jpg`,
      blob,
      description: "JPEG image",
      accept: { "image/jpeg": [".jpg", ".jpeg"] },
    }
  }

  return markdownBlobExport(generated, workingSources)
}

async function saveBlobToFolder({ filename, blob, description, accept }) {
  if (!window.showSaveFilePicker) {
    downloadBlobFile(filename, blob)
    return
  }
  const handle = await window.showSaveFilePicker({
    suggestedName: filename,
    types: [{ description, accept }],
  })
  const writable = await handle.createWritable()
  await writable.write(blob)
  await writable.close()
}

function createPdfBlob(text = "") {
  const pageWidth = 612
  const pageHeight = 792
  const margin = 54
  const lineHeight = 16
  const maxLines = Math.floor((pageHeight - margin * 2) / lineHeight)
  const lines = wrapPdfText(text, 88)
  const pages = []

  for (let i = 0; i < lines.length; i += maxLines) {
    pages.push(lines.slice(i, i + maxLines))
  }
  if (!pages.length) pages.push([""])

  const objects = []
  const addObject = (value) => {
    objects.push(value)
    return objects.length
  }

  const fontId = addObject("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
  const pageIds = []
  const contentIds = []

  pages.forEach((pageLines) => {
    const commands = ["BT", "/F1 11 Tf", "14 TL", `${margin} ${pageHeight - margin} Td`]
    pageLines.forEach((line, index) => {
      if (index) commands.push("T*")
      commands.push(`(${escapePdfText(line)}) Tj`)
    })
    commands.push("ET")
    const stream = commands.join("\n")
    const contentId = addObject(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`)
    contentIds.push(contentId)
    pageIds.push(null)
  })

  const pagesId = objects.length + pages.length + 1
  pages.forEach((_, index) => {
    pageIds[index] = addObject(`<< /Type /Page /Parent ${pagesId} 0 R /MediaBox [0 0 ${pageWidth} ${pageHeight}] /Resources << /Font << /F1 ${fontId} 0 R >> >> /Contents ${contentIds[index]} 0 R >>`)
  })
  addObject(`<< /Type /Pages /Kids [${pageIds.map((id) => `${id} 0 R`).join(" ")}] /Count ${pageIds.length} >>`)
  const catalogId = addObject(`<< /Type /Catalog /Pages ${pagesId} 0 R >>`)

  let pdf = "%PDF-1.4\n"
  const offsets = [0]
  objects.forEach((object, index) => {
    offsets.push(pdf.length)
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`
  })
  const xref = pdf.length
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
  for (let i = 1; i < offsets.length; i += 1) {
    pdf += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`
  }
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root ${catalogId} 0 R >>\nstartxref\n${xref}\n%%EOF`
  return new Blob([pdf], { type: "application/pdf" })
}

function wrapPdfText(text = "", width = 88) {
  const normalized = text.replace(/\r/g, "").replace(/[•–—]/g, "-").replace(/[“”]/g, '"').replace(/[‘’]/g, "'")
  const output = []
  normalized.split("\n").forEach((line) => {
    const clean = line.replace(/\s+/g, " ").trim()
    if (!clean) {
      output.push("")
      return
    }
    let current = ""
    clean.split(" ").forEach((word) => {
      if (`${current} ${word}`.trim().length > width) {
        output.push(current)
        current = word
      } else {
        current = `${current} ${word}`.trim()
      }
    })
    if (current) output.push(current)
  })
  return output
}

function escapePdfText(text = "") {
  return text.replace(/[^\x09\x0A\x0D\x20-\x7E]/g, "?").replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)")
}

async function createFlashcardsJpegBlob(output = "", title = "Flashcards") {
  const cards = parseFlashcards(output)
  const canvas = document.createElement("canvas")
  const width = 1600
  const cardHeight = 460
  const gap = 34
  const padding = 64
  const height = Math.max(720, padding * 2 + 100 + cards.length * cardHeight + Math.max(0, cards.length - 1) * gap)
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext("2d")

  ctx.fillStyle = "#f2f0ea"
  ctx.fillRect(0, 0, width, height)
  ctx.fillStyle = "#071126"
  ctx.font = "900 46px Arial"
  ctx.fillText(title, padding, 78)
  ctx.fillStyle = "#004f8f"
  ctx.font = "800 24px Arial"
  ctx.fillText(`${cards.length} flashcards`, padding, 118)

  cards.forEach((card, index) => {
    const y = padding + 110 + index * (cardHeight + gap)
    drawRoundRect(ctx, padding, y, width - padding * 2, cardHeight, 24, "#ffffff", "#0878c9")
    ctx.fillStyle = "#fece02"
    drawPill(ctx, padding + 34, y + 30, `CARD ${index + 1}`)
    ctx.fillStyle = "#071126"
    ctx.font = "900 34px Arial"
    drawWrappedCanvasText(ctx, card.q, padding + 34, y + 105, width - padding * 2 - 68, 42, 4)
    ctx.fillStyle = "#064c86"
    ctx.fillRect(padding + 34, y + 250, width - padding * 2 - 68, 3)
    ctx.fillStyle = "#243044"
    ctx.font = "700 27px Arial"
    drawWrappedCanvasText(ctx, card.a, padding + 34, y + 302, width - padding * 2 - 68, 36, 4)
  })

  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("Could not create JPEG.")), "image/jpeg", 0.92)
  })
}

function drawRoundRect(ctx, x, y, width, height, radius, fill, stroke) {
  ctx.beginPath()
  ctx.moveTo(x + radius, y)
  ctx.lineTo(x + width - radius, y)
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius)
  ctx.lineTo(x + width, y + height - radius)
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height)
  ctx.lineTo(x + radius, y + height)
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius)
  ctx.lineTo(x, y + radius)
  ctx.quadraticCurveTo(x, y, x + radius, y)
  ctx.closePath()
  ctx.fillStyle = fill
  ctx.fill()
  ctx.lineWidth = 4
  ctx.strokeStyle = stroke
  ctx.stroke()
}

function drawPill(ctx, x, y, text) {
  ctx.font = "900 18px Arial"
  const width = ctx.measureText(text).width + 32
  drawRoundRect(ctx, x, y, width, 36, 18, "#fece02", "#fece02")
  ctx.fillStyle = "#07142d"
  ctx.fillText(text, x + 16, y + 25)
}

function drawWrappedCanvasText(ctx, text, x, y, maxWidth, lineHeight, maxLines) {
  const words = cleanLine(text).split(/\s+/)
  let line = ""
  let lines = 0
  words.forEach((word) => {
    if (lines >= maxLines) return
    const test = `${line} ${word}`.trim()
    if (ctx.measureText(test).width > maxWidth && line) {
      ctx.fillText(line, x, y + lines * lineHeight)
      lines += 1
      line = word
    } else {
      line = test
    }
  })
  if (line && lines < maxLines) ctx.fillText(line, x, y + lines * lineHeight)
}

function downloadTextFile(filename, body) {
  const blob = new Blob([body], { type: "text/markdown;charset=utf-8" })
  downloadBlobFile(filename, blob)
}

function downloadBlobFile(filename, blob) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function slugify(value = "") {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "")
}

function labelFor(type) {
  return generationOptions.find(([value]) => value === type)?.[1] || type.replace(/_/g, " ")
}

function normalizeUrlInput(value = "") {
  const trimmed = extractFirstUrl(value)
  if (!trimmed) return ""
  const normalized = /^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`
  return normalized.replace(/^(https?:\/\/share\.google\/[^/?#]+)\/$/i, "$1")
}

function extractFirstUrl(value = "") {
  const trimmed = value.trim()
  const match = trimmed.match(/(https?:\/\/[^\s<>()]+|(?:share\.google|www\.[^\s<>()]+|[a-z0-9.-]+\.[a-z]{2,})(?:\/[^\s<>()]*)?)/i)
  return (match ? match[1] : trimmed).replace(/[.,;:!?)"']+$/g, "")
}

function normalizeGithubInput(value = "") {
  const trimmed = value.trim()
  const sshMatch = trimmed.match(/git@github\.com:([^/\s]+)\/([^/\s#?]+)/i)
  if (sshMatch) return `https://github.com/${sshMatch[1]}/${sshMatch[2].replace(/\.git$/i, "").replace(/\/$/g, "")}`
  const match = trimmed.match(/(?:https?:\/\/)?github\.com\/([^/\s<>()]+)\/([^/\s<>()#?]+)/i)
  if (!match) return ""
  return `https://github.com/${match[1]}/${match[2].replace(/\.git$/i, "").replace(/[.,;:!?)"'\/]+$/g, "")}`
}

function isGithubUrl(value = "") {
  return /^https?:\/\/(?:www\.)?github\.com\//i.test(value)
}

async function apiJson(path) {
  const response = await fetchWithFallback(path)
  if (!response.ok) throw new Error(await errorText(response))
  return response.json()
}

async function postJson(path, body) {
  const response = await fetchWithFallback(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error(await errorText(response))
  return response.json()
}

async function apiForm(path, formData) {
  const response = await fetchWithFallback(path, { method: "POST", body: formData })
  if (!response.ok) throw new Error(await errorText(response))
  return response.json()
}

async function deleteJson(path) {
  const response = await fetchWithFallback(path, { method: "DELETE" })
  if (!response.ok) throw new Error(await errorText(response))
  return response.json()
}

async function fetchWithFallback(path, options = {}) {
  let lastError
  for (const base of API_BASES) {
    try {
      const response = await fetch(`${base}${path}`, options)
      if (response.status !== 404 || base === API_BASES[API_BASES.length - 1]) return response
    } catch (err) {
      lastError = err
    }
  }
  throw lastError || new Error("Backend is not reachable")
}

async function errorText(response) {
  try {
    const data = await response.json()
    return data.detail || data.message || JSON.stringify(data)
  } catch {
    return response.statusText || "Request failed"
  }
}
