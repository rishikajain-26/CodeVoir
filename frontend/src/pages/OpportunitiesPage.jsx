import { AnimatePresence, motion } from "framer-motion"
import {
  AlertCircle,
  ArrowLeft,
  Briefcase,
  Building2,
  Calendar,
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  Code,
  ExternalLink,
  FolderGit2,
  Globe,
  Loader2,
  Search,
  Star,
  Tag,
  Target,
  Trophy,
  Upload,
  X,
  Zap,
} from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"

<<<<<<< HEAD
const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"
const API_BASES = [...new Set(["", API])]

async function opportunityFetch(path, options = {}) {
  let lastError = null
  for (const base of API_BASES) {
    try {
      const res = await fetch(`${base}${path}`, options)
      if (!res.ok && base === "" && [405, 501].includes(res.status)) {
        lastError = new Error(`${res.status} from local dev server`)
        continue
      }
      return res
    } catch (error) {
      lastError = error
    }
  }
  throw lastError || new Error("Opportunity service is unavailable")
}
=======
const API = ""
>>>>>>> b2a9557 (WIP: saving local work before sync)

// ── Constants ──────────────────────────────────────────────────────────────

const TYPE_CFG = {
<<<<<<< HEAD
  hackathon:   { label: "Hackathon",   bg: "bg-sky-400/10 text-sky-100 border border-sky-400/25", icon: "🏆", grad: "from-sky-950/60 to-blue-950/45" },
  competition: { label: "Competition", bg: "bg-cyan-400/10 text-cyan-100 border border-cyan-400/25",  icon: "🥇", grad: "from-cyan-950/55 to-slate-950/40" },
  job:         { label: "Job",         bg: "bg-blue-400/10 text-blue-100 border border-blue-400/25",        icon: "💼", grad: "from-blue-950/55 to-sky-950/45" },
  internship:  { label: "Internship",  bg: "bg-teal-400/10 text-teal-100 border border-teal-400/25",    icon: "🎓", grad: "from-teal-950/50 to-blue-950/45" },
}

const SOURCE_CFG = {
  unstop:   { label: "Unstop",   bg: "bg-sky-400/10 text-sky-100 border border-sky-400/20" },
  devfolio: { label: "Devfolio", bg: "bg-blue-400/10 text-blue-100 border border-blue-400/20" },
=======
  hackathon:   { label: "Hackathon",   bg: "bg-purple-500/20 text-purple-300 border border-purple-500/30", icon: "🏆", grad: "from-purple-900/40 to-indigo-900/40" },
  competition: { label: "Competition", bg: "bg-orange-500/20 text-orange-300 border border-orange-500/30",  icon: "🥇", grad: "from-orange-900/40 to-red-900/40" },
  job:         { label: "Job",         bg: "bg-blue-500/20 text-blue-300 border border-blue-500/30",        icon: "💼", grad: "from-blue-900/40 to-cyan-900/40" },
  internship:  { label: "Internship",  bg: "bg-green-500/20 text-green-300 border border-green-500/30",    icon: "🎓", grad: "from-green-900/40 to-teal-900/40" },
}

const SOURCE_CFG = {
  unstop:   { label: "Unstop",   bg: "bg-yellow-500/20 text-yellow-300" },
  devfolio: { label: "Devfolio", bg: "bg-indigo-500/20 text-indigo-300" },
>>>>>>> b2a9557 (WIP: saving local work before sync)
}

const CARDS_PER_VIEW = 3

const TYPE_FILTERS = [
  { key: "all", label: "All" },
  { key: "hackathon", label: "Hackathons" },
  { key: "competition", label: "Competitions" },
  { key: "internship", label: "Internships" },
  { key: "job", label: "Jobs" },
]

// ── OpportunityCard ────────────────────────────────────────────────────────

<<<<<<< HEAD
function OpportunityCard({ opp }) {
=======
function OpportunityCard({ opp, onPrepare }) {
>>>>>>> b2a9557 (WIP: saving local work before sync)
  const tc = TYPE_CFG[opp.type] || TYPE_CFG.hackathon
  const sc = SOURCE_CFG[opp.source] || SOURCE_CFG.unstop
  const skills = [...new Set([...(opp.skills_required || []), ...(opp.tags || [])])].slice(0, 4)
  const reward = opp.prize_pool || opp.stipend || ""
  const matchPct = Math.min(Math.round(opp.match_score || 0), 100)

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col h-full overflow-hidden rounded-lg border border-slate-700/60 bg-slate-950/60 backdrop-blur-xl
<<<<<<< HEAD
                 hover:border-sky-400/40 hover:shadow-[0_0_24px_rgba(56,189,248,0.12)] transition-all duration-300 group"
=======
                 hover:border-purple-500/40 hover:shadow-[0_0_24px_rgba(139,92,246,0.12)] transition-all duration-300 group"
>>>>>>> b2a9557 (WIP: saving local work before sync)
    >
      {/* Cover */}
      <div className={`relative h-32 bg-gradient-to-br ${tc.grad} overflow-hidden`}>
        {opp.cover_image ? (
          <img
            src={opp.cover_image}
            alt=""
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            onError={(e) => { e.currentTarget.style.display = "none" }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-5xl select-none opacity-70">
            {tc.icon}
          </div>
        )}

        {/* Type + source badges */}
        <div className="absolute top-2 left-2 flex gap-1.5 flex-wrap">
          <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${tc.bg}`}>{tc.label}</span>
          <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${sc.bg}`}>{sc.label}</span>
          {opp.platform_company && (
<<<<<<< HEAD
            <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-sky-400/90 text-slate-950 flex items-center gap-0.5">
              <Star size={8} className="fill-slate-950" /> Codevoir
=======
            <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/90 text-black flex items-center gap-0.5">
              <Star size={8} className="fill-black" /> Codevoir
>>>>>>> b2a9557 (WIP: saving local work before sync)
            </span>
          )}
        </div>

        {/* Match % + target company */}
        <div className="absolute top-2 right-2 flex flex-col gap-1 items-end">
          {matchPct > 0 && (
            <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
<<<<<<< HEAD
              matchPct >= 70 ? "bg-sky-400/90 text-slate-950" :
              matchPct >= 40 ? "bg-blue-400/80 text-white" :
              "bg-white/15 text-white"
=======
              matchPct >= 70 ? "bg-emerald-500/80 text-white" :
              matchPct >= 40 ? "bg-yellow-500/80 text-black" :
              "bg-white/20 text-white"
>>>>>>> b2a9557 (WIP: saving local work before sync)
            }`}>
              {matchPct}% match
            </span>
          )}
          {opp.target_company_match && (
            <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-sky-500/80 text-white flex items-center gap-0.5">
              <Target size={8} /> Target
            </span>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-col flex-1 p-4 gap-2.5">
        {/* Title + org */}
        <div>
          <h3 className="text-white font-semibold text-sm leading-snug line-clamp-2 mb-1">
            {opp.title}
          </h3>
          <p className="text-gray-400 text-xs flex items-center gap-1 truncate">
            <Building2 size={10} className="shrink-0" />
            {opp.organization || "Unknown"}
          </p>
        </div>

        {/* Meta row */}
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
          {opp.deadline_label && opp.deadline_label !== "Expired" && (
            <span className={`flex items-center gap-1 ${
              opp.deadline_label.includes("d left") && parseInt(opp.deadline_label) <= 7
<<<<<<< HEAD
                ? "text-sky-200" : "text-sky-300"
=======
                ? "text-red-300" : "text-orange-300"
>>>>>>> b2a9557 (WIP: saving local work before sync)
            }`}>
              <Calendar size={10} />
              {opp.deadline_label}
            </span>
          )}
          {reward && (
<<<<<<< HEAD
            <span className="flex items-center gap-1 text-cyan-300 truncate max-w-[120px]">
=======
            <span className="flex items-center gap-1 text-emerald-300 truncate max-w-[120px]">
>>>>>>> b2a9557 (WIP: saving local work before sync)
              <Trophy size={10} className="shrink-0" />
              {String(reward).slice(0, 22)}
            </span>
          )}
          {opp.is_remote && (
            <span className="flex items-center gap-1 text-blue-300">
              <Globe size={10} /> Remote
            </span>
          )}
          {opp.team_size && (
            <span className="text-gray-500">Team {opp.team_size}</span>
          )}
        </div>

        {/* Skills */}
        {skills.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {skills.map((s, i) => (
              <span key={i} className="px-1.5 py-0.5 bg-white/5 border border-white/10 rounded text-[10px] text-gray-300">
                {s}
              </span>
            ))}
          </div>
        )}

        {/* Matched skills callout */}
        {opp.matched_skills?.length > 0 && (
<<<<<<< HEAD
          <p className="text-[11px] text-sky-300 flex items-center gap-1">
=======
          <p className="text-[11px] text-purple-300 flex items-center gap-1">
>>>>>>> b2a9557 (WIP: saving local work before sync)
            <CheckCircle size={10} className="shrink-0" />
            Matches: {opp.matched_skills.join(", ")}
          </p>
        )}

        {/* Apply button */}
        <div className="mt-auto pt-1">
<<<<<<< HEAD
          <a
            href={opp.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="flex items-center justify-center gap-2 w-full px-4 py-2 rounded-lg
                       bg-teal-400 hover:bg-teal-300 text-slate-950 text-xs font-bold
                       transition-colors"
          >
            Apply Now <ExternalLink size={12} />
          </a>
=======
          <div className="grid gap-2">
            <button
              onClick={(e) => { e.stopPropagation(); onPrepare?.(opp) }}
              className="flex items-center justify-center gap-2 w-full px-4 py-2 rounded-lg
                         border border-purple-400/40 bg-purple-500/10 hover:bg-purple-500/20 text-purple-100 text-xs font-bold
                         transition-colors"
            >
              Prepare with AI <Zap size={12} />
            </button>
            <a
              href={opp.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="flex items-center justify-center gap-2 w-full px-4 py-2 rounded-lg
                         bg-teal-400 hover:bg-teal-300 text-slate-950 text-xs font-bold
                         transition-colors"
            >
              Apply Now <ExternalLink size={12} />
            </a>
          </div>
>>>>>>> b2a9557 (WIP: saving local work before sync)
        </div>
      </div>
    </motion.div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function OpportunitiesPage({ onBack }) {
  const [resumeFile, setResumeFile] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const [skills, setSkills] = useState("")
  const [targetCompanies, setTargetCompanies] = useState("")
  const [preferredTypes, setPreferredTypes] = useState([])
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null)
  const [errorMsg, setErrorMsg] = useState("")
  const [activeFilter, setActiveFilter] = useState("all")
  const [carouselIdx, setCarouselIdx] = useState(0)
  const [dbStatus, setDbStatus] = useState(null)
<<<<<<< HEAD
=======
  const [prepOutput, setPrepOutput] = useState("")
  const [prepLoading, setPrepLoading] = useState(false)
>>>>>>> b2a9557 (WIP: saving local work before sync)
  const fileRef = useRef(null)

  // Fetch DB status on mount
  useEffect(() => {
<<<<<<< HEAD
    opportunityFetch("/api/opportunities/status")
=======
    fetch(`${API}/api/opportunities/status`)
>>>>>>> b2a9557 (WIP: saving local work before sync)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => d && setDbStatus(d))
      .catch(() => {})
  }, [])

  const filteredOpps = (results?.opportunities || []).filter(
    (o) => activeFilter === "all" || o.type === activeFilter,
  )
  const totalPages = Math.ceil(filteredOpps.length / CARDS_PER_VIEW)
  const maxIdx = Math.max(0, filteredOpps.length - CARDS_PER_VIEW)
<<<<<<< HEAD
=======

  async function prepareOpportunity(opp) {
    setPrepLoading(true)
    setPrepOutput("")
    try {
      const response = await fetch(`${API}/api/learning/prepare-opportunity`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: opp.title,
          description: [opp.organization, ...(opp.skills_required || []), ...(opp.tags || [])].filter(Boolean).join(" | "),
          url: opp.url || "",
          resume_profile: results?.profile || {},
        }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "Could not prepare opportunity")
      setPrepOutput(data.output || "No preparation output returned.")
    } catch (err) {
      setPrepOutput(err.message || "Could not prepare this opportunity.")
    } finally {
      setPrepLoading(false)
    }
  }
>>>>>>> b2a9557 (WIP: saving local work before sync)
  const currentPage = Math.floor(carouselIdx / CARDS_PER_VIEW)

  const handleFile = (file) => {
    if (!file) return
    if (!/\.(pdf|txt)$/i.test(file.name)) {
      setErrorMsg("Please upload a PDF or TXT resume.")
      return
    }
    setResumeFile(file)
    setErrorMsg("")
  }

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setIsDragging(false)
    handleFile(e.dataTransfer.files?.[0])
  }, [])

  const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true) }
  const handleDragLeave = () => setIsDragging(false)

  const toggleType = (t) =>
    setPreferredTypes((prev) => prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t])

  const handleSubmit = async () => {
    if (!resumeFile && !skills.trim()) {
      setErrorMsg("Please upload a resume or enter your skills.")
      return
    }
    setLoading(true)
    setErrorMsg("")
    setResults(null)
    setCarouselIdx(0)
    setActiveFilter("all")

    try {
      const fd = new FormData()
      if (resumeFile) fd.append("resume", resumeFile)
      if (skills.trim()) fd.append("skills", skills.trim())
      if (targetCompanies.trim()) fd.append("target_companies", targetCompanies.trim())
      if (preferredTypes.length) fd.append("preferred_types", preferredTypes.join(","))

<<<<<<< HEAD
      const res = await opportunityFetch("/api/opportunities/analyze", { method: "POST", body: fd })
=======
      const res = await fetch(`${API}/api/opportunities/analyze`, { method: "POST", body: fd })
>>>>>>> b2a9557 (WIP: saving local work before sync)
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Server error ${res.status}`)
      }
      const data = await res.json()
      setResults(data)
      if (data.crawl_triggered) {
        setErrorMsg("First crawl started. Please try again in ~60 seconds.")
      }
    } catch (e) {
      setErrorMsg(e.message || "Analysis failed. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  const triggerCrawl = async () => {
<<<<<<< HEAD
    await opportunityFetch("/api/opportunities/crawl", { method: "POST" })
    const status = await opportunityFetch("/api/opportunities/status").then(r => r.json()).catch(() => null)
=======
    await fetch(`${API}/api/opportunities/crawl`, { method: "POST" })
    const status = await fetch(`${API}/api/opportunities/status`).then(r => r.json()).catch(() => null)
>>>>>>> b2a9557 (WIP: saving local work before sync)
    if (status) setDbStatus(status)
  }

  const prev = () => setCarouselIdx((i) => Math.max(0, i - CARDS_PER_VIEW))
  const next = () => setCarouselIdx((i) => Math.min(maxIdx, i + CARDS_PER_VIEW))
  const goPage = (p) => setCarouselIdx(Math.min(p * CARDS_PER_VIEW, maxIdx))

  const visible = filteredOpps.slice(carouselIdx, carouselIdx + CARDS_PER_VIEW)

  return (
    <div className="dashboard-shell min-h-screen text-white">
      {/* Sticky header */}
<<<<<<< HEAD
      <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-slate-950/70 px-6 py-4 backdrop-blur-xl">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-2 rounded border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-sm font-semibold text-sky-100 shadow-[0_0_24px_rgba(56,189,248,.14)] transition hover:border-sky-300 hover:bg-sky-400/20"
        >
          <ArrowLeft size={16} />
          Back to dashboard
        </button>
=======
      <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-slate-950/70 px-6 py-4 backdrop-blur-xl flex items-center justify-between">
        <button
          onClick={onBack}
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors text-sm"
        >
          <ArrowLeft size={15} />
          Back
        </button>
        <div className="flex items-center gap-2.5">
          <Zap size={17} className="text-purple-400" />
          <span className="font-display font-bold text-white tracking-normal">Opportunity Finder</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          {dbStatus && (
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              {dbStatus.total_opportunities?.toLocaleString()} cached
            </span>
          )}
          <button
            onClick={triggerCrawl}
            className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-gray-400 hover:text-white transition-all text-[11px]"
            title="Refresh opportunity data"
          >
            Refresh
          </button>
        </div>
>>>>>>> b2a9557 (WIP: saving local work before sync)
      </header>

      <div className="relative z-10 max-w-6xl mx-auto px-4 sm:px-6 py-8">
        {/* Hero */}
        <div className="dashboard-glass mb-10 px-6 py-8 text-center">
<<<<<<< HEAD
=======
          <div className="dashboard-kicker mx-auto mb-5"><Zap size={14} /> Matched opportunities</div>
>>>>>>> b2a9557 (WIP: saving local work before sync)
          <h1 className="font-display text-3xl sm:text-5xl font-semibold tracking-normal text-white mb-3">
            Find Your Perfect Opportunity
          </h1>
          <p className="text-gray-400 max-w-xl mx-auto text-sm sm:text-base">
            Upload your resume — we analyze your skills, year and interests to surface hackathons,
            jobs and internships matched to&nbsp;you.
          </p>
        </div>

        {/* Input grid */}
        <div className="dashboard-glass grid md:grid-cols-2 gap-6 mb-8 p-5">
          {/* Resume upload */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Resume <span className="text-gray-500 font-normal">(PDF or TXT)</span>
            </label>
            <div
              className={`relative rounded-lg border-2 border-dashed p-8 text-center cursor-pointer transition-all ${
<<<<<<< HEAD
                isDragging ? "border-sky-400 bg-sky-400/10" :
                resumeFile ? "border-sky-400/60 bg-sky-400/5" :
                "border-white/20 hover:border-sky-400/50 hover:bg-sky-400/5"
=======
                isDragging ? "border-purple-500 bg-purple-500/10" :
                resumeFile ? "border-emerald-500/60 bg-emerald-500/5" :
                "border-white/20 hover:border-purple-500/50 hover:bg-purple-500/5"
>>>>>>> b2a9557 (WIP: saving local work before sync)
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
            >
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.txt"
                className="hidden"
                onChange={(e) => handleFile(e.target.files?.[0])}
              />
              {resumeFile ? (
                <div className="flex items-center justify-center gap-3">
<<<<<<< HEAD
                  <CheckCircle size={22} className="text-sky-300 shrink-0" />
=======
                  <CheckCircle size={22} className="text-emerald-400 shrink-0" />
>>>>>>> b2a9557 (WIP: saving local work before sync)
                  <div className="text-left min-w-0">
                    <p className="text-white text-sm font-medium truncate">{resumeFile.name}</p>
                    <p className="text-gray-400 text-xs">{(resumeFile.size / 1024).toFixed(0)} KB</p>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); setResumeFile(null) }}
                    className="ml-auto text-gray-500 hover:text-red-400 transition-colors"
                  >
                    <X size={16} />
                  </button>
                </div>
              ) : (
                <>
                  <Upload size={30} className="mx-auto mb-3 text-gray-600" />
                  <p className="text-gray-400 text-sm">
<<<<<<< HEAD
                    Drop your resume or <span className="text-sky-300">click to browse</span>
=======
                    Drop your resume or <span className="text-purple-400">click to browse</span>
>>>>>>> b2a9557 (WIP: saving local work before sync)
                  </p>
                  <p className="text-gray-600 text-xs mt-1">PDF or TXT · max 5 MB</p>
                </>
              )}
            </div>
          </div>

          {/* Optional filters */}
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">
                Additional Skills <span className="text-gray-500 font-normal">(optional)</span>
              </label>
              <div className="relative">
                <Code size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                <input
                  type="text"
                  value={skills}
                  onChange={(e) => setSkills(e.target.value)}
                  placeholder="Python, React, Machine Learning..."
                  className="w-full pl-9 pr-4 py-3 bg-white/5 border border-white/15 rounded-xl text-white text-sm
<<<<<<< HEAD
                             placeholder-gray-500 focus:outline-none focus:border-sky-400/60 transition-colors"
                />
              </div>
=======
                             placeholder-gray-500 focus:outline-none focus:border-purple-500/60 transition-colors"
                />
              </div>
              <p className="text-xs text-gray-600 mt-1">Comma-separated, merged with resume skills</p>
>>>>>>> b2a9557 (WIP: saving local work before sync)
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">
                Target Companies <span className="text-gray-500 font-normal">(optional)</span>
              </label>
              <div className="relative">
                <Building2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                <input
                  type="text"
                  value={targetCompanies}
                  onChange={(e) => setTargetCompanies(e.target.value)}
                  placeholder="Google, Flipkart, Razorpay..."
                  className="w-full pl-9 pr-4 py-3 bg-white/5 border border-white/15 rounded-xl text-white text-sm
<<<<<<< HEAD
                             placeholder-gray-500 focus:outline-none focus:border-sky-400/60 transition-colors"
=======
                             placeholder-gray-500 focus:outline-none focus:border-purple-500/60 transition-colors"
>>>>>>> b2a9557 (WIP: saving local work before sync)
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Opportunity Type <span className="text-gray-500 font-normal">(optional)</span>
              </label>
              <div className="flex flex-wrap gap-2">
                {["hackathon", "internship", "job", "competition"].map((t) => (
                  <button
                    key={t}
                    onClick={() => toggleType(t)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all ${
                      preferredTypes.includes(t)
<<<<<<< HEAD
                        ? "bg-sky-400 text-slate-950 shadow-[0_0_10px_rgba(56,189,248,0.38)]"
=======
                        ? "bg-purple-600 text-white shadow-[0_0_10px_rgba(139,92,246,0.4)]"
>>>>>>> b2a9557 (WIP: saving local work before sync)
                        : "bg-white/5 text-gray-400 hover:bg-white/10 border border-white/10"
                    }`}
                  >
                    {TYPE_CFG[t].icon} {t}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Submit */}
        <div className="flex justify-center mb-8">
          <button
            onClick={handleSubmit}
            disabled={loading || (!resumeFile && !skills.trim())}
            className="px-8 py-3.5 bg-teal-400 hover:bg-teal-300 disabled:opacity-40 disabled:cursor-not-allowed
                       text-slate-950 font-bold rounded-lg transition-all shadow-[0_0_24px_rgba(20,184,166,0.25)]
                       hover:scale-[1.015] hover:shadow-[0_0_34px_rgba(20,184,166,0.34)] flex items-center gap-2.5 text-sm"
          >
            {loading ? (
              <><Loader2 size={18} className="animate-spin" /> Analysing resume…</>
            ) : (
              <><Search size={18} /> Find My Opportunities</>
            )}
          </button>
        </div>

        {/* Error */}
        <AnimatePresence>
          {errorMsg && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex items-start gap-2.5 bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3 mb-6 text-red-300 text-sm"
            >
              <AlertCircle size={16} className="shrink-0 mt-0.5" />
              {errorMsg}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Results */}
        {results && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>

            {/* Profile summary */}
            {results.profile && Object.values(results.profile).some(Boolean) && (
              <div className="dashboard-glass p-5 mb-6">
<<<<<<< HEAD
                <div className="flex items-center gap-2 text-sky-300 text-sm font-medium mb-4">
=======
                <div className="flex items-center gap-2 text-emerald-400 text-sm font-medium mb-4">
>>>>>>> b2a9557 (WIP: saving local work before sync)
                  <CheckCircle size={14} />
                  Resume Analysed
                </div>

                {/* Core profile fields */}
                <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm mb-4">
                  {results.profile.college_year && (
                    <span>
                      <span className="text-gray-500">Year: </span>
                      <span className="text-white font-medium">
                        {results.profile.college_year}
                        {["st","nd","rd","th"][results.profile.college_year - 1]} Year
                        {results.profile.graduation_year && (
                          <span className="text-gray-500 font-normal"> (Grad {results.profile.graduation_year})</span>
                        )}
                      </span>
                    </span>
                  )}
                  {results.profile.cgpa && (
                    <span>
                      <span className="text-gray-500">CGPA: </span>
                      <span className="text-white font-medium">{results.profile.cgpa.toFixed(1)} / 10</span>
                    </span>
                  )}
                  {results.profile.branch && (
                    <span>
                      <span className="text-gray-500">Branch: </span>
                      <span className="text-white font-medium capitalize">{results.profile.branch}</span>
                    </span>
                  )}
                  {results.profile.education_level && (
                    <span>
                      <span className="text-gray-500">Degree: </span>
                      <span className="text-white font-medium uppercase">{results.profile.education_level}</span>
                    </span>
                  )}
                </div>

                {/* Skills */}
                {results.profile.skills?.length > 0 && (
                  <div className="mb-3">
                    <p className="text-xs text-gray-500 mb-1.5 flex items-center gap-1">
                      <Code size={11} /> Skills detected ({results.profile.skills.length})
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {results.profile.skills.slice(0, 16).map((s, i) => (
<<<<<<< HEAD
                        <span key={i} className="px-2 py-0.5 bg-sky-400/10 border border-sky-400/25 rounded text-[11px] text-sky-100 capitalize">
=======
                        <span key={i} className="px-2 py-0.5 bg-purple-500/15 border border-purple-500/30 rounded text-[11px] text-purple-200 capitalize">
>>>>>>> b2a9557 (WIP: saving local work before sync)
                          {s}
                        </span>
                      ))}
                      {results.profile.skills.length > 16 && (
                        <span className="px-2 py-0.5 text-[11px] text-gray-500">
                          +{results.profile.skills.length - 16} more
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {/* Interests */}
                {results.profile.interests?.length > 0 && (
                  <div className="mb-3">
                    <p className="text-xs text-gray-500 mb-1.5 flex items-center gap-1">
                      <Tag size={11} /> Interests
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {results.profile.interests.map((int, i) => (
<<<<<<< HEAD
                        <span key={i} className="px-2 py-0.5 bg-blue-400/10 border border-blue-400/25 rounded text-[11px] text-blue-100 capitalize">
=======
                        <span key={i} className="px-2 py-0.5 bg-indigo-500/15 border border-indigo-500/30 rounded text-[11px] text-indigo-200 capitalize">
>>>>>>> b2a9557 (WIP: saving local work before sync)
                          {int}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Projects & Experience row */}
                <div className="flex flex-wrap gap-4 mt-1">
                  {results.profile.projects?.length > 0 && (
                    <div className="flex-1 min-w-[200px]">
                      <p className="text-xs text-gray-500 mb-1.5 flex items-center gap-1">
                        <FolderGit2 size={11} /> Projects ({results.profile.projects.length})
                      </p>
                      <ul className="space-y-1">
                        {results.profile.projects.slice(0, 3).map((p, i) => (
                          <li key={i} className="text-xs text-gray-300">
                            <span className="text-white font-medium">{p.title}</span>
                            {p.domain && <span className="text-gray-500"> · {p.domain}</span>}
                          </li>
                        ))}
                        {results.profile.projects.length > 3 && (
                          <li className="text-xs text-gray-600">+{results.profile.projects.length - 3} more</li>
                        )}
                      </ul>
                    </div>
                  )}

                  {results.profile.experience?.length > 0 && (
                    <div className="flex-1 min-w-[200px]">
                      <p className="text-xs text-gray-500 mb-1.5 flex items-center gap-1">
                        <Briefcase size={11} /> Experience
                      </p>
                      <ul className="space-y-1">
                        {results.profile.experience.slice(0, 3).map((e, i) => (
                          <li key={i} className="text-xs text-gray-300">
                            <span className="text-white font-medium">{e.role}</span>
<<<<<<< HEAD
                            {e.company && <span className="text-sky-300"> @ {e.company}</span>}
=======
                            {e.company && <span className="text-purple-300"> @ {e.company}</span>}
>>>>>>> b2a9557 (WIP: saving local work before sync)
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Filter bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
              <p className="text-gray-400 text-sm">
                Showing{" "}
                <span className="text-white font-semibold">{filteredOpps.length}</span>{" "}
                of {results.total_in_db?.toLocaleString()} cached opportunities
              </p>
              <div className="flex flex-wrap gap-2">
                {TYPE_FILTERS.map((f) => {
                  const count = f.key === "all"
                    ? results.opportunities.length
                    : results.opportunities.filter((o) => o.type === f.key).length
                  if (count === 0 && f.key !== "all") return null
                  return (
                    <button
                      key={f.key}
                      onClick={() => { setActiveFilter(f.key); setCarouselIdx(0) }}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                        activeFilter === f.key
<<<<<<< HEAD
                          ? "bg-sky-400 text-slate-950"
=======
                          ? "bg-purple-600 text-white"
>>>>>>> b2a9557 (WIP: saving local work before sync)
                          : "bg-white/5 text-gray-400 hover:bg-white/10 border border-white/10"
                      }`}
                    >
                      {f.label}{" "}
                      <span className="opacity-60">({count})</span>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Carousel */}
            {filteredOpps.length > 0 ? (
              <div className="relative">
                {/* Nav arrows */}
                <button
                  onClick={prev}
                  disabled={carouselIdx === 0}
                  aria-label="Previous"
                  className="absolute -left-5 top-1/2 -translate-y-1/2 z-10 w-10 h-10 rounded-full
<<<<<<< HEAD
                             bg-slate-950/80 border border-sky-400/20 flex items-center justify-center
                             text-sky-100 hover:bg-sky-400/10 disabled:opacity-20 disabled:cursor-not-allowed
=======
                             bg-[#1a1a30] border border-white/20 flex items-center justify-center
                             text-white hover:bg-white/10 disabled:opacity-20 disabled:cursor-not-allowed
>>>>>>> b2a9557 (WIP: saving local work before sync)
                             transition-all shadow-lg"
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  onClick={next}
                  disabled={carouselIdx >= maxIdx}
                  aria-label="Next"
                  className="absolute -right-5 top-1/2 -translate-y-1/2 z-10 w-10 h-10 rounded-full
<<<<<<< HEAD
                             bg-slate-950/80 border border-sky-400/20 flex items-center justify-center
                             text-sky-100 hover:bg-sky-400/10 disabled:opacity-20 disabled:cursor-not-allowed
=======
                             bg-[#1a1a30] border border-white/20 flex items-center justify-center
                             text-white hover:bg-white/10 disabled:opacity-20 disabled:cursor-not-allowed
>>>>>>> b2a9557 (WIP: saving local work before sync)
                             transition-all shadow-lg"
                >
                  <ChevronRight size={18} />
                </button>

                {/* Cards */}
                <AnimatePresence mode="wait">
                  <motion.div
                    key={`${carouselIdx}-${activeFilter}`}
                    initial={{ opacity: 0, x: 30 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -30 }}
                    transition={{ duration: 0.2 }}
                    className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
                  >
                    {visible.map((opp) => (
<<<<<<< HEAD
                      <OpportunityCard key={opp.id} opp={opp} />
=======
                      <OpportunityCard key={opp.id} opp={opp} onPrepare={prepareOpportunity} />
>>>>>>> b2a9557 (WIP: saving local work before sync)
                    ))}
                  </motion.div>
                </AnimatePresence>

                {/* Dot indicators */}
                {totalPages > 1 && (
                  <div className="flex justify-center gap-1.5 mt-6">
                    {Array.from({ length: totalPages }).map((_, i) => (
                      <button
                        key={i}
                        onClick={() => goPage(i)}
                        aria-label={`Page ${i + 1}`}
                        className={`rounded-full transition-all duration-300 ${
                          currentPage === i
<<<<<<< HEAD
                            ? "w-6 h-2 bg-sky-400"
=======
                            ? "w-6 h-2 bg-purple-500"
>>>>>>> b2a9557 (WIP: saving local work before sync)
                            : "w-2 h-2 bg-white/20 hover:bg-white/40"
                        }`}
                      />
                    ))}
                  </div>
                )}

                {/* Page label */}
                {totalPages > 1 && (
                  <p className="text-center text-xs text-gray-600 mt-2">
                    {currentPage + 1} / {totalPages}
                  </p>
                )}
              </div>
            ) : (
              <div className="text-center py-16 text-gray-500">
                <Trophy size={40} className="mx-auto mb-4 opacity-30" />
                <p className="text-lg font-medium mb-1">No {activeFilter !== "all" ? activeFilter + "s" : "opportunities"} found</p>
                <p className="text-sm">Try adjusting your filters or adding more skills.</p>
              </div>
            )}
          </motion.div>
        )}

        {/* Empty state (before search) */}
        {!results && !loading && (
          <div className="text-center py-12 text-gray-600">
            <Zap size={40} className="mx-auto mb-4 opacity-20" />
            <p className="text-sm">Upload your resume to discover tailored opportunities</p>
            {dbStatus && (
              <p className="text-xs mt-2 text-gray-700">
                {dbStatus.total_opportunities?.toLocaleString()} opportunities indexed from Unstop & Devfolio
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
