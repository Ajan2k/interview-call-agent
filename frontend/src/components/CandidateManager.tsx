import React, { useState, useEffect, useRef } from "react";
import {
  Users,
  UserPlus,
  FileText,
  Upload,
  Phone,
  Briefcase,
  Award,
  CheckCircle,
  Clock,
  AlertCircle,
  Sparkles,
  Play,
  Trash2,
  RefreshCw,
  Eye,
  ChevronRight,
  ChevronLeft,
  Search,
  HelpCircle,
  Edit3,
  X,
  TrendingUp,
  FileCheck,
} from "lucide-react";
import { Candidate, InterviewQuestion, Scorecard } from "../types";

interface CandidateManagerProps {
  onStartInterviewCall?: (candidate: Candidate) => void;
}

export const CandidateManager: React.FC<CandidateManagerProps> = ({ onStartInterviewCall }) => {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState<boolean>(false);
  const [isDossierOpen, setIsDossierOpen] = useState<boolean>(false);
  const [dossierTab, setDossierTab] = useState<"scorecard" | "questions" | "resume">("scorecard");

  // Pagination & Filtering state
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize] = useState<number>(25);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // Form states for adding candidate
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [position, setPosition] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [customBehavioral, setCustomBehavioral] = useState<string[]>([]);
  const [showBehavioralEditor, setShowBehavioralEditor] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load candidates with pagination and filters
  const loadCandidates = async (page = currentPage, search = searchQuery, status = statusFilter) => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      params.set("limit", String(pageSize));
      params.set("offset", String((page - 1) * pageSize));
      if (search && search.trim()) params.set("search", search.trim());
      if (status && status !== "all") params.set("status", status);

      const res = await fetch(`/api/candidates?${params.toString()}`);
      if (res.ok) {
        const totalHeader = res.headers.get("X-Total-Count");
        const data = await res.json();
        setCandidates(data);
        if (totalHeader !== null) {
          setTotalCount(parseInt(totalHeader, 10) || 0);
        } else {
          setTotalCount(data.length);
        }
      }
    } catch (err) {
      console.error("Error loading candidates:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadDefaultBehavioral = async () => {
    try {
      const res = await fetch("/api/candidates/behavioral-defaults");
      if (res.ok) {
        const data = await res.json();
        if (data.questions && Array.isArray(data.questions)) {
          setCustomBehavioral(data.questions.map((q: any) => q.text));
        }
      }
    } catch (err) {
      console.error("Error loading behavioral defaults:", err);
    }
  };

  useEffect(() => {
    loadCandidates(currentPage, searchQuery, statusFilter);
  }, [currentPage, statusFilter]);

  useEffect(() => {
    loadDefaultBehavioral();
  }, []);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentPage(1);
    loadCandidates(1, searchQuery, statusFilter);
  };

  const handleClearSearch = () => {
    setSearchQuery("");
    setCurrentPage(1);
    loadCandidates(1, "", statusFilter);
  };

  const handleFileDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (file.name.endsWith(".pdf") || file.name.endsWith(".docx") || file.name.endsWith(".doc")) {
        setResumeFile(file);
      } else {
        alert("Please upload a PDF or DOCX resume file.");
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setResumeFile(e.target.files[0]);
    }
  };

  const handleCreateCandidate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resumeFile) {
      setSubmitError("Please upload a candidate resume file (PDF or DOCX).");
      return;
    }
    if (!name || !phone || !position || !jobDescription) {
      setSubmitError("All fields are required.");
      return;
    }

    try {
      setSubmitting(true);
      setSubmitError(null);

      const formData = new FormData();
      formData.append("name", name);
      formData.append("phone", phone);
      formData.append("position", position);
      formData.append("job_description", jobDescription);
      formData.append("resume", resumeFile);
      if (customBehavioral && customBehavioral.length === 5) {
        formData.append("behavioral_questions", JSON.stringify(customBehavioral));
      }

      const res = await fetch("/api/candidates", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || "Failed to create candidate");
      }

      await loadCandidates(1, searchQuery, statusFilter);
      setCurrentPage(1);
      setIsAddModalOpen(false);
      // Reset form
      setName("");
      setPhone("");
      setPosition("");
      setJobDescription("");
      setResumeFile(null);
    } catch (err: any) {
      setSubmitError(err.message || "An unexpected error occurred");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteCandidate = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this candidate?")) return;
    try {
      const res = await fetch(`/api/candidates/${id}`, { method: "DELETE" });
      if (res.ok) {
        setCandidates((prev) => prev.filter((c) => c.id !== id));
        setTotalCount((prev) => Math.max(0, prev - 1));
        if (selectedCandidate?.id === id) {
          setIsDossierOpen(false);
          setSelectedCandidate(null);
        }
      }
    } catch (err) {
      console.error("Failed to delete candidate:", err);
    }
  };

  const handleReevaluate = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const res = await fetch(`/api/candidates/${id}/evaluate`, { method: "POST" });
      if (res.ok) {
        const updated = await res.json();
        setCandidates((prev) => prev.map((c) => (c.id === id ? updated : c)));
        if (selectedCandidate?.id === id) {
          setSelectedCandidate(updated);
        }
      }
    } catch (err) {
      console.error("Evaluation trigger failed:", err);
    }
  };

  // Stats calculation
  const totalCandidates = totalCount;
  const completedInterviews = candidates.filter((c) => c.status === "completed" || c.status === "evaluated").length;
  const hireCount = candidates.filter(
    (c) => c.scorecard && (c.scorecard.recommendation === "Strong Hire" || c.scorecard.recommendation === "Hire")
  ).length;
  const avgScore =
    completedInterviews > 0
      ? Math.round(
          candidates.reduce((acc, c) => acc + (c.scorecard?.overall_score || 0), 0) /
            (candidates.filter((c) => c.scorecard).length || 1)
        )
      : 0;

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  return (
    <div className="space-y-6">
      {/* Top Banner & Quick Metrics */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900/60 border border-slate-800 p-6 rounded-2xl backdrop-blur-xl">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Sparkles className="w-5 h-5 text-indigo-400" />
            <h1 className="text-xl font-bold text-white">Autonomous AI Interview Agent</h1>
          </div>
          <p className="text-sm text-slate-400">
            Automated resume parsing, 10 personalized technical questions + 5 STAR behavioral questions, and instant hiring scorecards.
          </p>
        </div>
        <button
          onClick={() => setIsAddModalOpen(true)}
          className="flex items-center justify-center gap-2 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white px-5 py-2.5 rounded-xl font-medium shadow-lg shadow-indigo-500/20 transition-all hover:scale-[1.02] active:scale-[0.98]"
        >
          <UserPlus className="w-4 h-4" />
          <span>Add Candidate & Generate Questions</span>
        </button>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-900/40 border border-slate-800/80 p-4 rounded-xl">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium uppercase mb-2">
            <span>Total Candidates</span>
            <Users className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-bold text-white">{totalCandidates}</div>
          <div className="text-xs text-slate-500 mt-1">Uploaded resumes</div>
        </div>

        <div className="bg-slate-900/40 border border-slate-800/80 p-4 rounded-xl">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium uppercase mb-2">
            <span>Interviews Done</span>
            <CheckCircle className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-white">{completedInterviews}</div>
          <div className="text-xs text-slate-500 mt-1">Full sessions completed</div>
        </div>

        <div className="bg-slate-900/40 border border-slate-800/80 p-4 rounded-xl">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium uppercase mb-2">
            <span>Hire Recommended</span>
            <Award className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-2xl font-bold text-white">{hireCount}</div>
          <div className="text-xs text-slate-500 mt-1">Strong Hire / Hire signals</div>
        </div>

        <div className="bg-slate-900/40 border border-slate-800/80 p-4 rounded-xl">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium uppercase mb-2">
            <span>Average Score</span>
            <TrendingUp className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold text-white">{avgScore > 0 ? `${avgScore}/100` : "N/A"}</div>
          <div className="text-xs text-slate-500 mt-1">Across all competencies</div>
        </div>
      </div>

      {/* Candidate List Table */}
      <div className="bg-slate-900/50 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
        <div className="p-4 border-b border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">Candidate Pipeline</h2>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 font-medium">
              {totalCount} total
            </span>
          </div>

          <div className="flex items-center gap-2.5 flex-wrap sm:flex-nowrap">
            <form onSubmit={handleSearchSubmit} className="relative flex-1 sm:w-64">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                placeholder="Search name or phone..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-8 pr-7 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={handleClearSearch}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </form>

            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="bg-slate-950 border border-slate-800 rounded-xl px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
            >
              <option value="all">All Statuses</option>
              <option value="ready">Ready</option>
              <option value="in_progress">In Progress</option>
              <option value="completed">Completed</option>
              <option value="evaluated">Evaluated</option>
            </select>

            <button
              onClick={() => loadCandidates(currentPage, searchQuery, statusFilter)}
              title="Refresh"
              className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-white rounded-xl transition-colors border border-slate-800"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>

        {loading ? (
          <div className="p-12 text-center text-slate-400">Loading candidates...</div>
        ) : candidates.length === 0 ? (
          <div className="p-12 text-center">
            <div className="inline-flex p-4 rounded-full bg-indigo-500/10 text-indigo-400 mb-3">
              <Users className="w-8 h-8" />
            </div>
            <h3 className="text-base font-semibold text-slate-200">No candidates enrolled yet</h3>
            <p className="text-sm text-slate-400 max-w-md mx-auto mt-1 mb-4">
              Upload a candidate's resume (PDF/DOCX) and Job Description to automatically generate 10 tailored technical questions and launch autonomous voice interviews.
            </p>
            <button
              onClick={() => setIsAddModalOpen(true)}
              className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-xl text-sm font-medium transition-colors"
            >
              <UserPlus className="w-4 h-4" />
              Add First Candidate
            </button>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/60">
            {candidates.map((cand) => {
              const rec = cand.scorecard?.recommendation;
              const score = cand.scorecard?.overall_score;

              let badgeColor = "bg-slate-800 text-slate-300";
              if (cand.status === "ready") badgeColor = "bg-blue-500/10 text-blue-400 border border-blue-500/20";
              else if (cand.status === "in_progress") badgeColor = "bg-amber-500/10 text-amber-400 border border-amber-500/20";
              else if (cand.status === "evaluated") badgeColor = "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";

              let recColor = "text-slate-400 bg-slate-800";
              if (rec === "Strong Hire") recColor = "text-emerald-300 bg-emerald-950/80 border border-emerald-700/50";
              else if (rec === "Hire") recColor = "text-green-300 bg-green-950/80 border border-green-700/50";
              else if (rec === "Consider") recColor = "text-amber-300 bg-amber-950/80 border border-amber-700/50";
              else if (rec === "Do Not Hire") recColor = "text-rose-300 bg-rose-950/80 border border-rose-700/50";

              return (
                <div
                  key={cand.id}
                  onClick={() => {
                    setSelectedCandidate(cand);
                    setIsDossierOpen(true);
                  }}
                  className="p-4 hover:bg-slate-800/40 transition-colors flex flex-col md:flex-row md:items-center justify-between gap-4 cursor-pointer"
                >
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500/20 to-purple-500/20 border border-indigo-500/30 flex items-center justify-center text-indigo-300 font-bold text-base flex-shrink-0">
                      {cand.name.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-100">{cand.name}</span>
                        <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${badgeColor}`}>
                          {cand.status.replace("_", " ").toUpperCase()}
                        </span>
                      </div>
                      <div className="flex items-center gap-4 text-xs text-slate-400 mt-1">
                        <span className="flex items-center gap-1 text-slate-300">
                          <Briefcase className="w-3.5 h-3.5 text-slate-500" />
                          {cand.position}
                        </span>
                        <span className="flex items-center gap-1">
                          <Phone className="w-3.5 h-3.5 text-slate-500" />
                          {cand.phone}
                        </span>
                        <span className="flex items-center gap-1 text-indigo-400">
                          <FileText className="w-3.5 h-3.5" />
                          {cand.resume_filename}
                        </span>
                        <span>{cand.questions?.length || 0} Questions Ready</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {/* Score Badge */}
                    {score !== undefined && (
                      <div className="text-right">
                        <div className="text-sm font-bold text-white">{score}/100</div>
                        <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${recColor}`}>
                          {rec}
                        </span>
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => {
                          if (onStartInterviewCall) onStartInterviewCall(cand);
                        }}
                        title="Start Voice Interview Call"
                        className="flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-3 py-1.5 rounded-lg font-medium transition-colors shadow-sm"
                      >
                        <Play className="w-3.5 h-3.5 fill-current" />
                        <span>Call</span>
                      </button>

                      <button
                        onClick={(e) => handleReevaluate(cand.id, e)}
                        title="Re-run AI Evaluation"
                        className="p-1.5 hover:bg-slate-700 text-slate-400 hover:text-white rounded-lg transition-colors"
                      >
                        <RefreshCw className="w-4 h-4" />
                      </button>

                      <button
                        onClick={(e) => handleDeleteCandidate(cand.id, e)}
                        title="Delete candidate"
                        className="p-1.5 hover:bg-rose-500/20 text-slate-400 hover:text-rose-400 rounded-lg transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>

                      <ChevronRight className="w-4 h-4 text-slate-600" />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Pagination Bar */}
        {totalCount > pageSize && (
          <div className="p-3.5 border-t border-slate-800 bg-slate-950/40 flex items-center justify-between text-xs text-slate-400">
            <div>
              Showing <span className="font-semibold text-slate-200">{(currentPage - 1) * pageSize + 1}</span> to{" "}
              <span className="font-semibold text-slate-200">
                {Math.min(currentPage * pageSize, totalCount)}
              </span>{" "}
              of <span className="font-semibold text-slate-200">{totalCount}</span> candidates
            </div>
            <div className="flex items-center gap-2">
              <button
                disabled={currentPage <= 1 || loading}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-800 bg-slate-900 text-slate-300 hover:text-white hover:bg-slate-800 disabled:opacity-40 disabled:pointer-events-none transition-colors"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                <span>Previous</span>
              </button>
              <span className="px-2 text-slate-400 font-medium">
                Page {currentPage} of {totalPages}
              </span>
              <button
                disabled={currentPage >= totalPages || loading}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-800 bg-slate-900 text-slate-300 hover:text-white hover:bg-slate-800 disabled:opacity-40 disabled:pointer-events-none transition-colors"
              >
                <span>Next</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Add Candidate Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl my-8">
            <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-900/80">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-indigo-400" />
                <h3 className="text-base font-bold text-white">Enroll Candidate for AI Interview</h3>
              </div>
              <button
                onClick={() => setIsAddModalOpen(false)}
                className="p-1 hover:bg-slate-800 text-slate-400 hover:text-white rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateCandidate} className="p-6 space-y-4">
              {submitError && (
                <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <span>{submitError}</span>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Candidate Name *</label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Arjun Sharma"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Phone Number *</label>
                  <input
                    type="tel"
                    required
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="e.g. +91 98765 43210"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Position / Role Title *</label>
                <input
                  type="text"
                  required
                  value={position}
                  onChange={(e) => setPosition(e.target.value)}
                  placeholder="e.g. Senior AI / Backend Engineer"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              {/* Resume File Upload Dropzone */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Candidate Resume (PDF / DOCX only) *
                </label>
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileChange}
                  accept=".pdf,.docx,.doc"
                  className="hidden"
                />
                <div
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={handleFileDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition-colors ${
                    resumeFile
                      ? "border-emerald-500/50 bg-emerald-500/5 text-emerald-300"
                      : "border-slate-750 bg-slate-950 hover:border-indigo-500/50 hover:bg-slate-900/60"
                  }`}
                >
                  <Upload className="w-7 h-7 mx-auto mb-2 text-slate-400" />
                  {resumeFile ? (
                    <div>
                      <span className="font-semibold text-emerald-400">{resumeFile.name}</span>
                      <p className="text-xs text-slate-400 mt-1">{(resumeFile.size / 1024).toFixed(1)} KB — Ready to parse</p>
                    </div>
                  ) : (
                    <div>
                      <p className="text-sm font-medium text-slate-200">
                        Drag & drop candidate resume here, or <span className="text-indigo-400 underline">browse</span>
                      </p>
                      <p className="text-xs text-slate-500 mt-1">Supports PDF or DOCX formats</p>
                    </div>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Job Description (JD) *</label>
                <textarea
                  rows={4}
                  required
                  value={jobDescription}
                  onChange={(e) => setJobDescription(e.target.value)}
                  placeholder="Paste the core responsibilities, required technical skills, and stack for this position..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              {/* Behavioral Questions Toggle */}
              <div className="pt-2">
                <button
                  type="button"
                  onClick={() => setShowBehavioralEditor(!showBehavioralEditor)}
                  className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-medium"
                >
                  <span>{showBehavioralEditor ? "Hide" : "Customize"} 5 Fixed Behavioral Questions (STAR Method)</span>
                </button>

                {showBehavioralEditor && (
                  <div className="mt-3 space-y-2.5 bg-slate-950/60 p-4 rounded-xl border border-slate-800">
                    <p className="text-xs text-slate-400 mb-2">
                      These 5 behavioral questions will be asked alongside the 10 autonomously generated technical questions.
                    </p>
                    {customBehavioral.map((qText, idx) => (
                      <div key={idx} className="flex items-start gap-2">
                        <span className="text-xs font-bold text-slate-500 mt-2">B{idx + 1}.</span>
                        <input
                          type="text"
                          value={qText}
                          onChange={(e) => {
                            const updated = [...customBehavioral];
                            updated[idx] = e.target.value;
                            setCustomBehavioral(updated);
                          }}
                          className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="pt-4 flex items-center justify-end gap-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm px-5 py-2.5 rounded-xl font-medium transition-all shadow-lg shadow-indigo-600/20"
                >
                  {submitting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Parsing Resume & Generating Questions...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      <span>Generate 10 Questions & Save</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Candidate Dossier & Scorecard Modal */}
      {isDossierOpen && selectedCandidate && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl my-8 overflow-hidden">
            {/* Modal Header */}
            <div className="p-6 border-b border-slate-800 flex items-start justify-between bg-slate-900/90">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-2xl bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center text-indigo-300 font-bold text-lg">
                  {selectedCandidate.name.charAt(0).toUpperCase()}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-xl font-bold text-white">{selectedCandidate.name}</h2>
                    <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                      {selectedCandidate.position}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-slate-400 mt-1">
                    <span>Phone: {selectedCandidate.phone}</span>
                    <span>Resume: {selectedCandidate.resume_filename}</span>
                    <span>Status: {selectedCandidate.status.toUpperCase()}</span>
                  </div>
                </div>
              </div>
              <button
                onClick={() => setIsDossierOpen(false)}
                className="p-1 hover:bg-slate-800 text-slate-400 hover:text-white rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Navigation Tabs */}
            <div className="flex border-b border-slate-800 bg-slate-950/60 px-6">
              <button
                onClick={() => setDossierTab("scorecard")}
                className={`py-3 px-4 text-xs font-semibold border-b-2 transition-colors flex items-center gap-2 ${
                  dossierTab === "scorecard"
                    ? "border-indigo-500 text-indigo-400"
                    : "border-transparent text-slate-400 hover:text-slate-200"
                }`}
              >
                <Award className="w-4 h-4" />
                <span>AI Evaluation Scorecard</span>
              </button>
              <button
                onClick={() => setDossierTab("questions")}
                className={`py-3 px-4 text-xs font-semibold border-b-2 transition-colors flex items-center gap-2 ${
                  dossierTab === "questions"
                    ? "border-indigo-500 text-indigo-400"
                    : "border-transparent text-slate-400 hover:text-slate-200"
                }`}
              >
                <HelpCircle className="w-4 h-4" />
                <span>Interview Roadmap ({selectedCandidate.questions?.length || 0} Questions)</span>
              </button>
              <button
                onClick={() => setDossierTab("resume")}
                className={`py-3 px-4 text-xs font-semibold border-b-2 transition-colors flex items-center gap-2 ${
                  dossierTab === "resume"
                    ? "border-indigo-500 text-indigo-400"
                    : "border-transparent text-slate-400 hover:text-slate-200"
                }`}
              >
                <FileText className="w-4 h-4" />
                <span>Resume & JD Content</span>
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 overflow-y-auto space-y-6 flex-1">
              {dossierTab === "scorecard" && (
                <div>
                  {selectedCandidate.scorecard ? (
                    <div className="space-y-6">
                      {/* Overall Decision Banner */}
                      <div className="p-6 rounded-2xl bg-gradient-to-r from-slate-950 to-slate-900 border border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-6">
                        <div>
                          <div className="text-xs uppercase font-bold text-slate-400 tracking-wider">Hiring Recommendation</div>
                          <div className="text-2xl font-black text-white mt-1">
                            {selectedCandidate.scorecard.recommendation}
                          </div>
                          <p className="text-xs text-slate-400 mt-2 max-w-md">
                            {selectedCandidate.scorecard.summary}
                          </p>
                        </div>
                        <div className="flex flex-col items-center justify-center p-4 rounded-xl bg-slate-900/80 border border-slate-750 min-w-[120px]">
                          <span className="text-3xl font-extrabold text-indigo-400">
                            {selectedCandidate.scorecard.overall_score}
                          </span>
                          <span className="text-[11px] font-medium text-slate-400">Overall Score</span>
                        </div>
                      </div>

                      {/* Competency Ratings */}
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                          <span className="text-xs text-slate-400 font-medium">Technical Competency</span>
                          <div className="text-xl font-bold text-white mt-1">
                            {selectedCandidate.scorecard.technical_score}/100
                          </div>
                          <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                            <div
                              className="bg-indigo-500 h-full rounded-full"
                              style={{ width: `${selectedCandidate.scorecard.technical_score}%` }}
                            />
                          </div>
                        </div>

                        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                          <span className="text-xs text-slate-400 font-medium">Behavioral & Culture</span>
                          <div className="text-xl font-bold text-white mt-1">
                            {selectedCandidate.scorecard.behavioral_score}/100
                          </div>
                          <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                            <div
                              className="bg-purple-500 h-full rounded-full"
                              style={{ width: `${selectedCandidate.scorecard.behavioral_score}%` }}
                            />
                          </div>
                        </div>

                        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                          <span className="text-xs text-slate-400 font-medium">Communication Clarity</span>
                          <div className="text-xl font-bold text-white mt-1">
                            {selectedCandidate.scorecard.communication_score}/100
                          </div>
                          <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                            <div
                              className="bg-cyan-500 h-full rounded-full"
                              style={{ width: `${selectedCandidate.scorecard.communication_score}%` }}
                            />
                          </div>
                        </div>
                      </div>

                      {/* Strengths & Weaknesses */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                          <h4 className="text-xs font-bold text-emerald-400 uppercase tracking-wider mb-2">Key Strengths</h4>
                          <ul className="space-y-1.5">
                            {selectedCandidate.scorecard.strengths?.map((str, idx) => (
                              <li key={idx} className="text-xs text-slate-300 flex items-start gap-2">
                                <span className="text-emerald-400 font-bold">•</span>
                                <span>{str}</span>
                              </li>
                            ))}
                          </ul>
                        </div>

                        <div className="bg-slate-950 p-4 rounded-xl border border-slate-800">
                          <h4 className="text-xs font-bold text-amber-400 uppercase tracking-wider mb-2">Areas for Improvement</h4>
                          <ul className="space-y-1.5">
                            {selectedCandidate.scorecard.areas_for_improvement?.map((gap, idx) => (
                              <li key={idx} className="text-xs text-slate-300 flex items-start gap-2">
                                <span className="text-amber-400 font-bold">•</span>
                                <span>{gap}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="p-12 text-center text-slate-400">
                      <Clock className="w-8 h-8 mx-auto mb-2 text-slate-500" />
                      <p className="text-sm font-medium text-slate-300">No evaluation scorecard generated yet</p>
                      <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                        Once the candidate completes their voice interview, an automated scorecard will be generated here.
                      </p>
                      <button
                        onClick={(e) => handleReevaluate(selectedCandidate.id, e)}
                        className="mt-4 inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-4 py-2 rounded-xl font-medium"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                        Run AI Evaluation Now
                      </button>
                    </div>
                  )}
                </div>
              )}

              {dossierTab === "questions" && (
                <div className="space-y-3">
                  <div className="text-xs text-slate-400 mb-2">
                    5 Behavioral Questions + 10 Tailored Technical Questions created from candidate's resume and target JD.
                  </div>
                  {selectedCandidate.questions?.map((q, idx) => (
                    <div
                      key={q.id || idx}
                      className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/80 hover:border-slate-700 transition-colors"
                    >
                      <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                        <span className="font-bold text-indigo-400">
                          Question {q.order} — {q.category.toUpperCase()}
                        </span>
                        <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-medium">
                          {q.competency}
                        </span>
                      </div>
                      <p className="text-sm text-slate-200 mt-1">{q.text}</p>
                    </div>
                  ))}
                </div>
              )}

              {dossierTab === "resume" && (
                <div className="space-y-4">
                  <div>
                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Target Job Description</h4>
                    <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 whitespace-pre-line leading-relaxed max-h-48 overflow-y-auto">
                      {selectedCandidate.job_description}
                    </div>
                  </div>

                  <div>
                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                      Parsed Resume Text ({selectedCandidate.resume_filename})
                    </h4>
                    <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 whitespace-pre-line leading-relaxed max-h-60 overflow-y-auto">
                      {selectedCandidate.resume_text || "No text available."}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-800 bg-slate-950 flex items-center justify-between">
              <span className="text-xs text-slate-500">Candidate ID: {selectedCandidate.id}</span>
              <button
                onClick={() => {
                  setIsDossierOpen(false);
                  if (onStartInterviewCall) onStartInterviewCall(selectedCandidate);
                }}
                className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-4 py-2 rounded-xl font-medium transition-colors shadow-lg shadow-emerald-600/20"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Launch Live Interview Call</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
