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

// ── Constants ──────────────────────────────────────────────────────────────

const TYPE_CFG = {
  hackathon:   { label: "Hackathon",   bg: "bg-sky-400/10 text-sky-100 border border-sky-400/25", icon: "🏆", grad: "from-sky-950/60 to-blue-950/45" },
  competition: { label: "Competition", bg: "bg-cyan-400/10 text-cyan-100 border border-cyan-400/25",  icon: "🥇", grad: "from-cyan-950/55 to-slate-950/40" },
  job:         { label: "Job",         bg: "bg-blue-400/10 text-blue-100 border border-blue-400/25",        icon: "💼", grad: "from-blue-950/55 to-sky-950/45" },
  internship:  { label: "Internship",  bg: "bg-teal-400/10 text-teal-100 border border-teal-400/25",    icon: "🎓", grad: "from-teal-950/50 to-blue-950/45" },
}

const SOURCE_CFG = {
  unstop:   { label: "Unstop",   bg: "bg-sky-400/10 text-sky-100 border border-sky-400/20" },
  devfolio: { label: "Devfolio", bg: "bg-blue-400/10 text-blue-100 border border-blue-400/20" },
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

function OpportunityCard({ opp }) {
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
                 hover:border-sky-400/40 hover:shadow-[0_0_24px_rgba(56,189,248,0.12)] transition-all duration-300 group opportunity-card"
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
            <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-sky-400/90 text-slate-950 flex items-center gap-0.5">
              <Star size={8} className="fill-slate-950" /> Codevoir
            </span>
          )}
        </div>

        {/* Match % + target company */}
        <div className="absolute top-2 right-2 flex flex-col gap-1 items-end">
          {matchPct > 0 && (
            <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
              matchPct >= 70 ? "bg-sky-400/90 text-slate-950" :
              matchPct >= 40 ? "bg-blue-400/80 text-white" :
              "bg-white/15 text-white"
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
                ? "text-sky-200" : "text-sky-300"
            }`}>
              <Calendar size={10} />
              {opp.deadline_label}
            </span>
          )}
          {reward && (
            <span className="flex items-center gap-1 text-cyan-300 truncate max-w-[120px]">
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
          <p className="text-[11px] text-sky-300 flex items-center gap-1">
            <CheckCircle size={10} className="shrink-0" />
            Matches: {opp.matched_skills.join(", ")}
          </p>
        )}

        {/* Apply button */}
        <div className="mt-auto pt-1">
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
  const fileRef = useRef(null)

  // Fetch DB status on mount
  useEffect(() => {
    opportunityFetch("/api/opportunities/status")
      .then((r) => r.ok ? r.json() : null)
      .then((d) => d && setDbStatus(d))
      .catch(() => {})
  }, [])

  const filteredOpps = (results?.opportunities || []).filter(
    (o) => activeFilter === "all" || o.type === activeFilter,
  )
  const totalPages = Math.ceil(filteredOpps.length / CARDS_PER_VIEW)
  const maxIdx = Math.max(0, filteredOpps.length - CARDS_PER_VIEW)
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

      const res = await opportunityFetch("/api/opportunities/analyze", { method: "POST", body: fd })
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
    await opportunityFetch("/api/opportunities/crawl", { method: "POST" })
    const status = await opportunityFetch("/api/opportunities/status").then(r => r.json()).catch(() => null)
    if (status) setDbStatus(status)
  }

  const prev = () => setCarouselIdx((i) => Math.max(0, i - CARDS_PER_VIEW))
  const next = () => setCarouselIdx((i) => Math.min(maxIdx, i + CARDS_PER_VIEW))
  const goPage = (p) => setCarouselIdx(Math.min(p * CARDS_PER_VIEW, maxIdx))

  const visible = filteredOpps.slice(carouselIdx, carouselIdx + CARDS_PER_VIEW)

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
          <h1 className="font-display text-3xl sm:text-5xl font-bold tracking-tight text-slate-900 mb-3">
            Find Your Perfect Opportunity
          </h1>
          <p className="text-slate-600 max-w-xl mx-auto text-sm sm:text-base leading-relaxed">
            Upload your resume — we analyze your skills, year and interests to surface hackathons,
            jobs and internships matched to&nbsp;you.
          </p>
        </div>

        {/* Input grid */}
        <div className="dashboard-glass opp-form-card grid md:grid-cols-2 gap-16 mb-8 p-5">
          {/* Resume upload */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2.5">
              Resume <span className="text-gray-500 font-normal">(PDF or TXT)</span>
            </label>
            <div
              className={`relative rounded-lg border-2 border-dashed p-8 text-center cursor-pointer transition-all opp-dropzone ${
                isDragging ? "active border-sky-400 bg-sky-400/10" :
                resumeFile ? "active border-sky-400/60 bg-sky-400/5" :
                "border-white/20 hover:border-sky-400/50 hover:bg-sky-400/5"
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
                  <CheckCircle size={22} className="text-sky-300 shrink-0" />
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
                    Drop your resume or <span className="text-sky-300">click to browse</span>
                  </p>
                  <p className="text-gray-600 text-xs mt-1">PDF or TXT · max 5 MB</p>
                </>
              )}
            </div>
          </div>

          {/* Optional filters */}
          <div className="space-y-6 opp-filters-stack">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Additional Skills <span className="text-gray-500 font-normal">(optional)</span>
              </label>
              <div className="relative">
                <Code size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                <input
                  type="text"
                  value={skills}
                  onChange={(e) => setSkills(e.target.value)}
                  placeholder="Python, React, Machine Learning..."
                  className="w-full pl-9 pr-4 py-3 bg-white/5 border border-white/15 rounded-xl text-white text-sm opp-input
                             placeholder-gray-500 focus:outline-none focus:border-sky-400/60 transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Target Companies <span className="text-gray-500 font-normal">(optional)</span>
              </label>
              <div className="relative">
                <Building2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                <input
                  type="text"
                  value={targetCompanies}
                  onChange={(e) => setTargetCompanies(e.target.value)}
                  placeholder="Google, Flipkart, Razorpay..."
                  className="w-full pl-9 pr-4 py-3 bg-white/5 border border-white/15 rounded-xl text-white text-sm opp-input
                             placeholder-gray-500 focus:outline-none focus:border-sky-400/60 transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2.5">
                Opportunity Type <span className="text-gray-500 font-normal">(optional)</span>
              </label>
              <div className="flex flex-wrap gap-2">
                {["hackathon", "internship", "job", "competition"].map((t) => (
                  <button
                    key={t}
                    onClick={() => toggleType(t)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all opp-tag-btn ${
                      preferredTypes.includes(t)
                        ? "active bg-sky-400 text-slate-950 shadow-[0_0_10px_rgba(56,189,248,0.38)]"
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
            className="px-8 py-3.5 bg-teal-400 hover:bg-teal-300 disabled:opacity-40 disabled:cursor-not-allowed opp-submit-btn
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
            {/* Profile summary */}
            {results.profile && Object.values(results.profile).some(Boolean) && (
              <div className="dashboard-glass opp-profile-summary p-5 mb-6 relative overflow-hidden rounded-xl border border-slate-200 bg-white/95 shadow-sm">
                <div className="flex flex-col gap-4">
                  {/* Header */}
                  <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                    <div className="flex items-center gap-2 text-blue-600 font-bold text-sm">
                      <CheckCircle size={15} className="stroke-[2.5]" />
                      <span>Resume Analysed</span>
                    </div>
                    {results.opportunities?.length > 0 && (
                      <span className="text-xs text-slate-500 font-medium">
                        Matched with {results.opportunities.length} opportunities
                      </span>
                    )}
                  </div>

                  {/* Core profile fields as flat inline badges */}
                  <div className="flex flex-wrap gap-2 text-xs">
                    {results.profile.college_year && (
                      <span className="px-3 py-1 bg-blue-50 border border-blue-100 rounded-lg text-slate-700">
                        <strong className="text-blue-600 font-semibold">Year: </strong>
                        {results.profile.college_year}
                        {["st","nd","rd","th"][results.profile.college_year - 1] || "th"} Year
                        {results.profile.graduation_year && ` (Grad ${results.profile.graduation_year})`}
                      </span>
                    )}
                    {results.profile.cgpa && (
                      <span className="px-3 py-1 bg-teal-50 border border-teal-100 rounded-lg text-slate-700">
                        <strong className="text-teal-600 font-semibold">CGPA: </strong>
                        {results.profile.cgpa.toFixed(1)} / 10
                      </span>
                    )}
                    {results.profile.branch && (
                      <span className="px-3 py-1 bg-purple-50 border border-purple-100 rounded-lg text-slate-700 capitalize">
                        <strong className="text-purple-600 font-semibold">Branch: </strong>
                        {results.profile.branch}
                      </span>
                    )}
                    {results.profile.education_level && (
                      <span className="px-3 py-1 bg-indigo-50 border border-indigo-100 rounded-lg text-slate-700 uppercase">
                        <strong className="text-indigo-600 font-semibold">Degree: </strong>
                        {results.profile.education_level}
                      </span>
                    )}
                  </div>

                  {/* Skills detected */}
                  {results.profile.skills?.length > 0 && (
                    <div className="space-y-1">
                      <div className="text-slate-500 text-[11px] font-semibold flex items-center gap-1">
                        <Code size={11} className="text-slate-400" />
                        <span>Skills detected ({results.profile.skills.length})</span>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {results.profile.skills.slice(0, 10).map((s, i) => (
                          <span key={i} className="px-2 py-0.5 bg-slate-100 border border-slate-200/65 rounded text-[11px] text-slate-600 capitalize">
                            {s}
                          </span>
                        ))}
                        {results.profile.skills.length > 10 && (
                          <span className="px-2 py-0.5 text-[11px] text-slate-400 font-medium">
                            +{results.profile.skills.length - 10} more
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Interests */}
                  {results.profile.interests?.length > 0 && (
                    <div className="space-y-1">
                      <div className="text-slate-500 text-[11px] font-semibold flex items-center gap-1">
                        <Tag size={11} className="text-slate-400" />
                        <span>Interests</span>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {results.profile.interests.map((int, i) => (
                          <span key={i} className="px-2 py-0.5 bg-slate-100 border border-slate-200/65 rounded text-[11px] text-slate-600 capitalize">
                            {int}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                </div>
              </div>
            )}

            {/* Filter bar */}
            <div className="flex flex-wrap items-center justify-end gap-3 mb-5">
              <div className="flex flex-wrap gap-2">
                {TYPE_FILTERS.map((f) => {
                  const count = f.key === "all"
                    ? results.opportunities.length
                    : results.opportunities.filter((o) => o.type === f.key).length
                  if (count === 0 && f.key !== "all") return null
                  const isActive = activeFilter === f.key
                  return (
                    <button
                      key={f.key}
                      onClick={() => { setActiveFilter(f.key); setCarouselIdx(0) }}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all opp-filter-btn ${
                        isActive ? "active" : ""
                      }`}
                    >
                      {f.label}{" "}
                      <span className={isActive ? "text-white/80" : "text-slate-400"}>({count})</span>
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
                             bg-slate-950/80 border border-sky-400/20 flex items-center justify-center opp-nav-arrow
                             text-sky-100 hover:bg-sky-400/10 disabled:opacity-20 disabled:cursor-not-allowed
                             transition-all shadow-lg"
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  onClick={next}
                  disabled={carouselIdx >= maxIdx}
                  aria-label="Next"
                  className="absolute -right-5 top-1/2 -translate-y-1/2 z-10 w-10 h-10 rounded-full
                             bg-slate-950/80 border border-sky-400/20 flex items-center justify-center opp-nav-arrow
                             text-sky-100 hover:bg-sky-400/10 disabled:opacity-20 disabled:cursor-not-allowed
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
                      <OpportunityCard key={opp.id} opp={opp} />
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
                            ? "w-6 h-2 bg-sky-400"
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
