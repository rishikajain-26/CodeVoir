import { AnimatePresence, motion } from "framer-motion"
import {
  ArrowLeft,
  BookOpen,
  Brain,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  FileText,
  HelpCircle,
  Plus,
  RotateCw,
  Search,
  Send,
  Sparkles,
  Volume2,
} from "lucide-react"
import { useState } from "react"

const PRELOADED_DOCS = [
  {
    id: "react-hooks",
    title: "React Hooks Deep Dive",
    category: "Frontend Architecture",
    summary: "Complete guide to React hooks lifecycle, state transitions, optimization hooks, and custom hook design patterns.",
    flashcards: [
      {
        question: "What is the primary difference between useMemo and useCallback?",
        answer: "useMemo caches the calculated value of a function execution, while useCallback caches the function definition itself to prevent unnecessary re-renders of child components that depend on function references."
      },
      {
        question: "When does the cleanup function of useEffect run?",
        answer: "The cleanup function runs: 1) Immediately before the effect is re-executed due to dependency changes, and 2) When the component unmounts from the DOM."
      },
      {
        question: "Why can't React hooks be called inside loops or conditions?",
        answer: "React relies on the calling order of hooks to link state variables across renders. Calling hooks conditionally disrupts this order, causing React to mismatch state values on subsequent renders."
      },
      {
        question: "What is the purpose of the useImperativeHandle hook?",
        answer: "It customizes the instance value exposed to parent components when using ref. It should be used in conjunction with forwardRef to limit direct access to DOM nodes."
      }
    ],
    qa: [
      { q: "How do I trigger an effect only on component update, not mount?", a: "You can use a useRef to track whether the component has mounted. Initialize the ref to true, and in the useEffect, check if it's true. If so, set it to false and skip execution; otherwise, run your update logic." },
      { q: "What happens if we omit dependency array in useEffect?", a: "The effect runs on every single render of the component. This can lead to performance degradation or infinite loops if state changes occur within the effect." }
    ]
  },
  {
    id: "system-design",
    title: "System Design: Scaling Databases",
    category: "Backend & Systems",
    summary: "Strategies for high scalability, including replication, sharding, CAP Theorem, and database consistency trade-offs.",
    flashcards: [
      {
        question: "What is Database Sharding?",
        answer: "Sharding is a horizontal partitioning method where a single database database is split into multiple smaller, faster databases (shards) across different servers based on a shard key."
      },
      {
        question: "Explain the CAP Theorem.",
        answer: "CAP Theorem states that a distributed data store can simultaneously provide at most two of three guarantees: Consistency (every read gets the latest write), Availability (every request gets a non-error response), and Partition Tolerance (system continues to operate despite network partition)."
      },
      {
        question: "What is the difference between Master-Slave and Master-Master Replication?",
        answer: "Master-Slave replication writes to the master, which replicates data to slaves for reading. Master-Master allows writes on any node, requiring conflict-resolution strategies but offering higher write availability."
      },
      {
        question: "What are the trade-offs of eventual consistency?",
        answer: "Eventual consistency offers high availability and low latency, but reads might temporarily return stale data. Over time, all updates propagate and nodes reconcile to show the same state."
      }
    ],
    qa: [
      { q: "Which database is better for high write throughput?", a: "NoSQL databases using LSM-tree engines (like Cassandra or ScyllaDB) are optimized for extremely high write throughput as they write sequentially to memory tables and flush to disk." },
      { q: "How does caching help database performance?", a: "Caching (e.g., Redis) stores frequently requested database query results in memory, reducing the read load on the database disk and achieving sub-millisecond latencies." }
    ]
  },
  {
    id: "git-workflows",
    title: "Git Branching & Workflow Mastery",
    category: "DevOps & Collaboration",
    summary: "Modern version control strategies, rebase operations, stashing, and conflict resolution guide for high-performing engineering teams.",
    flashcards: [
      {
        question: "What is the difference between git merge and git rebase?",
        answer: "git merge creates a new merge commit combining the history of both branches, preserving commit history as-is. git rebase reapplies commits of the current branch on top of another branch, rewriting commit history to create a clean linear timeline."
      },
      {
        question: "What does git cherry-pick do?",
        answer: "git cherry-pick takes a specific commit from one branch and applies it as a brand new commit on the current active branch."
      },
      {
        question: "How do you recover a commit that was deleted or lost?",
        answer: "You can use `git reflog` to view a history of all head movements and checkouts. Find the commit hash of the lost commit, and use `git checkout <hash>` or `git merge <hash>` to restore it."
      },
      {
        question: "What is the purpose of git stash pop vs git stash apply?",
        answer: "Both apply stashed changes. `git stash pop` applies the changes and deletes them from the stash list. `git stash apply` applies changes but retains them in the stash list for reuse."
      }
    ],
    qa: [
      { q: "How to resolve a rebase conflict?", a: "Identify conflict files using `git status`, fix the conflict markers in code editor, stage the files with `git add`, and continue the rebase using `git rebase --continue`." },
      { q: "What is a detached HEAD state?", a: "It happens when you checkout a specific commit instead of a branch. Commits made in this state won't belong to any branch and can easily get lost when checking out another branch." }
    ]
  }
]

export default function DocumentationPage({ onBack }) {
  const [selectedDoc, setSelectedDoc] = useState(PRELOADED_DOCS[0])
  const [customDocs, setCustomDocs] = useState([])
  const [textInput, setTextInput] = useState("")
  const [docTitle, setDocTitle] = useState("")
  const [uploadFile, setUploadFile] = useState(null)
  
  // Flashcard states
  const [currentCardIdx, setCurrentCardIdx] = useState(0)
  const [isFlipped, setIsFlipped] = useState(false)
  const [studiedCount, setStudiedCount] = useState(0)
  
  // AI Q&A states
  const [userQuery, setUserQuery] = useState("")
  const [chatHistory, setChatHistory] = useState([
    { role: "assistant", text: "Hello! Ask me any question related to this document, and I'll find the answer for you." }
  ])
  const [chatLoading, setChatLoading] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)

  const handleDocSelect = (doc) => {
    setSelectedDoc(doc)
    setCurrentCardIdx(0)
    setIsFlipped(false)
    setStudiedCount(0)
    setChatHistory([
      { role: "assistant", text: `Hello! Ask me any question related to "${doc.title}", and I'll extract answers instantly.` }
    ])
  }

  const handleFileUpload = (e) => {
    const file = e.target.files[0]
    if (file) {
      setUploadFile(file)
      setDocTitle(file.name.replace(/\.[^/.]+$/, ""))
    }
  }

  const handleGenerate = () => {
    if (!docTitle.trim()) return
    if (!textInput.trim() && !uploadFile) return

    setIsGenerating(true)
    
    // Simulate smart AI analysis and generation
    setTimeout(() => {
      const newDoc = {
        id: `custom-${Date.now()}`,
        title: docTitle.trim(),
        category: "Custom Analysis",
        summary: `AI analyzed documentation from "${docTitle.trim()}". Extracted core structural terms and key concept mappings.`,
        flashcards: [
          {
            question: `What is the core theme of "${docTitle.trim()}"?`,
            answer: `The primary theme revolves around ${textInput ? textInput.slice(0, 120) : "the uploaded file contents"}... and key implementation parameters.`
          },
          {
            question: "What are the primary usage directives specified?",
            answer: "Deploy modular definitions, inspect return constraints, and run test suites to ensure standard compliance."
          },
          {
            question: "Are there any optimization or refactoring considerations?",
            answer: "Yes, reduce deep dependencies, leverage browser-level cache buffers, and maintain linear execution contexts."
          }
        ],
        qa: [
          { q: "What should I know before deployment?", a: "Ensure env contexts are set up and verify all build dependencies compile without side effects." },
          { q: "How to handle memory issues?", a: "Implement proper dispose pattern on unmounts and profile closures in event listeners." }
        ]
      }

      setCustomDocs([newDoc, ...customDocs])
      setSelectedDoc(newDoc)
      
      // Reset inputs
      setTextInput("")
      setDocTitle("")
      setUploadFile(null)
      setCurrentCardIdx(0)
      setIsFlipped(false)
      setStudiedCount(0)
      setIsGenerating(false)
      
      setChatHistory([
        { role: "assistant", text: `Custom document "${newDoc.title}" has been parsed successfully! Ask me anything about it.` }
      ])
    }, 1800)
  }

  const handleAskAI = (e) => {
    e.preventDefault()
    if (!userQuery.trim() || chatLoading) return

    const query = userQuery.trim()
    setUserQuery("")
    setChatHistory(prev => [...prev, { role: "user", text: query }])
    setChatLoading(true)

    // Simulate AI semantic search matching
    setTimeout(() => {
      let answer = "I couldn't find a specific section addressing that in the document. Try asking about core definitions or configuration setups."
      
      // Look for fuzzy match in document QA or summary
      const lowerQuery = query.toLowerCase()
      const matchedQA = selectedDoc.qa.find(
        item => item.q.toLowerCase().includes(lowerQuery) || lowerQuery.includes(item.q.toLowerCase())
      )

      if (matchedQA) {
        answer = matchedQA.a
      } else if (lowerQuery.includes("summary") || lowerQuery.includes("about") || lowerQuery.includes("what is")) {
        answer = selectedDoc.summary
      } else {
        // Fallback simulated smart answer
        answer = `Based on our index of "${selectedDoc.title}", the configuration maps to: "${selectedDoc.flashcards[0].answer.slice(0, 100)}..." Feel free to ask more specific questions.`
      }

      setChatHistory(prev => [...prev, { role: "assistant", text: answer }])
      setChatLoading(false)
    }, 1000)
  }

  const handlePrevCard = () => {
    setIsFlipped(false)
    setTimeout(() => {
      setCurrentCardIdx(prev => Math.max(0, prev - 1))
    }, 150)
  }

  const handleNextCard = () => {
    setIsFlipped(false)
    setTimeout(() => {
      if (currentCardIdx === selectedDoc.flashcards.length - 1) {
        // Wrap around or count as done
        setStudiedCount(prev => Math.min(selectedDoc.flashcards.length, prev + 1))
      }
      setCurrentCardIdx(prev => Math.min(selectedDoc.flashcards.length - 1, prev + 1))
    }, 150)
  }

  const handleMarkAsStudied = () => {
    if (studiedCount < selectedDoc.flashcards.length) {
      setStudiedCount(prev => prev + 1)
    }
  }

  const speakText = (text) => {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.rate = 1.0
      window.speechSynthesis.speak(utterance)
    }
  }

  const allDocs = [...PRELOADED_DOCS, ...customDocs]

  return (
    <div className="dashboard-shell min-h-screen text-slate-900 codevoir-dashboard-page">
      {/* Sticky header */}
      <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-slate-950/70 px-6 py-4 backdrop-blur-xl">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-2 rounded border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-sm font-semibold text-sky-100 shadow-[0_0_24px_rgba(56,189,248,.14)] transition hover:border-sky-300 hover:bg-sky-400/20"
        >
          <ArrowLeft size={16} />
          Back to dashboard
        </button>
      </header>

      <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 py-8">
        {/* Hero */}
        <div className="mb-10 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-purple-500/10 text-purple-600 border border-purple-500/20 shadow-[0_0_15px_rgba(168,85,247,0.15)]">
            <Brain size={24} className="animate-pulse" />
          </div>
          <h1 className="font-display text-3xl sm:text-5xl font-bold tracking-tight text-slate-900 mb-3">
            Documentation Assistant
          </h1>
          <p className="text-slate-600 max-w-xl mx-auto text-sm sm:text-base leading-relaxed">
            Convert coding docs, guides, and text into interactive smart flashcards. Use semantic AI chat to query any document instantly.
          </p>
        </div>

        <div className="grid lg:grid-cols-[300px_1fr] gap-8 items-start">
          
          {/* LEFT COLUMN: Document Selection & Custom Input */}
          <div className="space-y-6">
            
            {/* 1. Document Kit Selection list */}
            <div className="dashboard-glass p-5 rounded-xl border border-slate-200 bg-white/90 shadow-sm">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
                <BookOpen size={13} /> Select Document
              </h3>
              
              <div className="space-y-2">
                {allDocs.map((doc) => {
                  const isActive = selectedDoc.id === doc.id
                  return (
                    <button
                      key={doc.id}
                      onClick={() => handleDocSelect(doc)}
                      className={`w-full text-left p-3 rounded-lg border text-sm transition-all flex items-start justify-between ${
                        isActive
                          ? "bg-purple-50 border-purple-300 text-purple-950 font-semibold shadow-sm"
                          : "bg-transparent border-slate-200/60 text-slate-600 hover:bg-slate-50/70"
                      }`}
                    >
                      <div className="min-w-0 pr-2">
                        <div className="truncate text-sm">{doc.title}</div>
                        <div className={`text-[10px] mt-0.5 ${isActive ? "text-purple-600" : "text-slate-400"}`}>
                          {doc.category}
                        </div>
                      </div>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                        isActive ? "bg-purple-200/60 text-purple-800" : "bg-slate-100 text-slate-500"
                      }`}>
                        {doc.flashcards.length} cards
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* 2. Generation Panel */}
            <div className="dashboard-glass p-5 rounded-xl border border-slate-200 bg-white/90 shadow-sm">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4 flex items-center gap-1.5">
                <Plus size={13} /> Upload New Doc
              </h3>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-500 mb-1">DOCUMENT TITLE</label>
                  <input
                    type="text"
                    value={docTitle}
                    onChange={(e) => setDocTitle(e.target.value)}
                    placeholder="e.g. Docker Fundamentals"
                    className="w-full px-3 py-2 bg-slate-50/50 border border-slate-200 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:border-purple-400 transition-colors"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-slate-500 mb-1">PASTE TEXT / MARKDOWN</label>
                  <textarea
                    value={textInput}
                    onChange={(e) => setTextInput(e.target.value)}
                    placeholder="Paste documentation paragraphs here..."
                    rows={4}
                    className="w-full px-3 py-2 bg-slate-50/50 border border-slate-200 rounded-lg text-sm placeholder-slate-400 focus:outline-none focus:border-purple-400 transition-colors resize-none"
                  />
                </div>

                <div className="relative">
                  <div className="flex items-center justify-between mb-1">
                    <label className="block text-[11px] font-semibold text-slate-500">OR UPLOAD FILE</label>
                    {uploadFile && (
                      <button onClick={() => setUploadFile(null)} className="text-[10px] text-red-500 hover:underline">
                        Remove
                      </button>
                    )}
                  </div>
                  <div className="border border-dashed border-slate-200 rounded-lg p-3 text-center bg-slate-50/20 hover:bg-slate-50/50 transition-colors cursor-pointer relative">
                    <input
                      type="file"
                      accept=".txt,.md,.pdf"
                      onChange={handleFileUpload}
                      className="absolute inset-0 opacity-0 cursor-pointer"
                    />
                    <FileText size={16} className="mx-auto mb-1 text-slate-400" />
                    <span className="text-[11px] text-slate-500 block truncate">
                      {uploadFile ? uploadFile.name : "Select .txt, .md or .pdf"}
                    </span>
                  </div>
                </div>

                <button
                  onClick={handleGenerate}
                  disabled={isGenerating || !docTitle.trim() || (!textInput.trim() && !uploadFile)}
                  className="w-full py-2.5 rounded-lg font-bold text-sm bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-[0_4px_12px_rgba(168,85,247,0.2)] flex items-center justify-center gap-1.5"
                >
                  {isGenerating ? (
                    <>
                      <div className="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      <span>Parsing Doc...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles size={14} />
                      <span>Generate Study Kit</span>
                    </>
                  )}
                </button>
              </div>
            </div>

          </div>

          {/* RIGHT COLUMN: Active Document Study View */}
          <div className="space-y-6">
            
            {/* Document Header Panel */}
            <div className="dashboard-glass p-5 rounded-xl border border-slate-200 bg-white/90 shadow-sm relative overflow-hidden">
              <div className="absolute right-0 top-0 h-32 w-32 bg-purple-500/5 rounded-full blur-2xl" />
              <span className="px-2 py-0.5 rounded bg-purple-100 text-purple-800 text-[10px] font-bold uppercase tracking-wider">
                {selectedDoc.category}
              </span>
              <h2 className="mt-2 text-2xl font-bold text-slate-900">{selectedDoc.title}</h2>
              <p className="mt-2 text-sm text-slate-600 leading-relaxed max-w-3xl">
                {selectedDoc.summary}
              </p>
            </div>

            {/* Main Interactive Tabs Grid */}
            <div className="grid md:grid-cols-2 gap-6 items-stretch">
              
              {/* STUDY TAB: Flashcard Sandbox */}
              <div className="dashboard-glass p-5 rounded-xl border border-slate-200 bg-white/90 shadow-sm flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                      <Brain size={14} className="text-purple-600" /> Flashcard Study
                    </span>
                    <span className="text-xs text-slate-400">
                      Card {currentCardIdx + 1} of {selectedDoc.flashcards.length}
                    </span>
                  </div>

                  {/* 3D Flip Card */}
                  <div 
                    onClick={() => setIsFlipped(!isFlipped)}
                    className="group relative h-48 w-full cursor-pointer perspective-1000 mb-4"
                  >
                    <div 
                      className={`relative h-full w-full rounded-xl border transition-all duration-500 transform-style-3d ${
                        isFlipped 
                          ? "rotate-y-180 bg-purple-950 border-purple-900 text-purple-100 shadow-md" 
                          : "bg-white border-slate-200 text-slate-800 hover:border-purple-300 hover:shadow-[0_4px_16px_rgba(168,85,247,0.06)]"
                      }`}
                    >
                      {/* FRONT OF THE CARD */}
                      <div className={`absolute inset-0 p-5 flex flex-col justify-between backface-hidden ${isFlipped ? "opacity-0" : "opacity-100"}`}>
                        <div className="text-[10px] text-purple-600 font-bold tracking-wider uppercase">QUESTION</div>
                        <p className="text-base font-semibold leading-snug text-slate-800 text-center my-auto px-4">
                          {selectedDoc.flashcards[currentCardIdx]?.question}
                        </p>
                        <div className="text-center text-[10px] text-slate-400 italic">Click card to reveal answer</div>
                      </div>

                      {/* BACK OF THE CARD */}
                      <div className={`absolute inset-0 p-5 flex flex-col justify-between backface-hidden rotate-y-180 ${isFlipped ? "opacity-100" : "opacity-0"}`}>
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] text-purple-400 font-bold tracking-wider uppercase">ANSWER</span>
                          <button 
                            onClick={(e) => {
                              e.stopPropagation();
                              speakText(selectedDoc.flashcards[currentCardIdx]?.answer);
                            }}
                            className="p-1 rounded bg-white/10 text-purple-300 hover:bg-white/20 transition-colors"
                            title="Speak answer"
                          >
                            <Volume2 size={12} />
                          </button>
                        </div>
                        <p className="text-sm font-medium leading-relaxed text-purple-100 text-center my-auto px-3 overflow-y-auto max-h-[110px]">
                          {selectedDoc.flashcards[currentCardIdx]?.answer}
                        </p>
                        <div className="text-center text-[10px] text-purple-300/60 italic">Click card to see question</div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Card Controls */}
                <div className="space-y-4">
                  <div className="flex items-center justify-between gap-4">
                    <button
                      onClick={handlePrevCard}
                      disabled={currentCardIdx === 0}
                      className="p-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    >
                      <ChevronLeft size={16} />
                    </button>

                    <button
                      onClick={handleMarkAsStudied}
                      className="flex-1 py-2 rounded-lg border border-purple-300 bg-purple-50 hover:bg-purple-100 text-purple-700 font-bold text-xs transition-colors flex items-center justify-center gap-1.5"
                    >
                      <CheckCircle size={13} /> Mark studied
                    </button>

                    <button
                      onClick={handleNextCard}
                      disabled={currentCardIdx === selectedDoc.flashcards.length - 1 && studiedCount === selectedDoc.flashcards.length}
                      className="p-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    >
                      <ChevronRight size={16} />
                    </button>
                  </div>

                  {/* Progress Bar */}
                  <div>
                    <div className="flex justify-between text-[10px] text-slate-400 font-bold mb-1">
                      <span>PROGRESS</span>
                      <span>{Math.round((studiedCount / selectedDoc.flashcards.length) * 100)}% COMPLETE</span>
                    </div>
                    <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-purple-500 rounded-full transition-all duration-300"
                        style={{ width: `${(studiedCount / selectedDoc.flashcards.length) * 100}%` }}
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* SEARCH TAB: AI Query & Chat assistant */}
              <div className="dashboard-glass p-5 rounded-xl border border-slate-200 bg-white/90 shadow-sm flex flex-col justify-between h-[390px]">
                <div>
                  <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-3">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                      <HelpCircle size={14} className="text-purple-600" /> Semantic AI Query
                    </span>
                    <span className="flex items-center gap-1 text-[10px] text-purple-600 bg-purple-50 border border-purple-100 rounded-full px-1.5 py-0.5">
                      <Sparkles size={8} /> Document Index Ready
                    </span>
                  </div>

                  {/* Chat Message Window */}
                  <div className="space-y-3 overflow-y-auto h-[240px] pr-1.5 flex flex-col">
                    {chatHistory.map((msg, index) => {
                      const isUser = msg.role === "user"
                      return (
                        <div
                          key={index}
                          className={`max-w-[85%] rounded-xl p-3 text-xs leading-relaxed ${
                            isUser
                              ? "bg-purple-600 text-white self-end rounded-br-none"
                              : "bg-slate-100 text-slate-700 self-start rounded-bl-none border border-slate-200/50"
                          }`}
                        >
                          {msg.text}
                        </div>
                      )
                    })}
                    {chatLoading && (
                      <div className="bg-slate-100 text-slate-500 border border-slate-200/50 rounded-xl rounded-bl-none p-3 text-xs self-start flex items-center gap-2 max-w-[80%]">
                        <div className="flex gap-1">
                          <span className="h-1.5 w-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                          <span className="h-1.5 w-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                          <span className="h-1.5 w-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                        </div>
                        <span>Scanning document...</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Query Input */}
                <form onSubmit={handleAskAI} className="relative mt-2">
                  <input
                    type="text"
                    value={userQuery}
                    onChange={(e) => setUserQuery(e.target.value)}
                    placeholder={`Ask about "${selectedDoc.title}"...`}
                    className="w-full bg-slate-50 border border-slate-200 rounded-full pl-4 pr-10 py-2.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-purple-400 transition-colors"
                  />
                  <button
                    type="submit"
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1.5 rounded-full bg-purple-600 text-white hover:bg-purple-500 transition-colors disabled:opacity-40"
                    disabled={!userQuery.trim() || chatLoading}
                  >
                    <Send size={12} />
                  </button>
                </form>
              </div>

            </div>

          </div>

        </div>

      </div>
    </div>
  )
}
