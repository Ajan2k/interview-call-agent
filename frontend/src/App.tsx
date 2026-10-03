import React, { useState, useEffect } from "react";
import {
  Sparkles,
  Settings,
  CheckCircle,
} from "lucide-react";
import { Metrics } from "./components/Metrics";
import { CallLogs } from "./components/CallLogs";
import { CallHistory } from "./components/CallHistory";
import { CallLog, Candidate } from "./types";
import { TeleforceAgent } from "./components/TeleforceAgent";
import { CandidateManager } from "./components/CandidateManager";

export default function App() {
  const [logs, setLogs] = useState<CallLog[]>([]);
  const [activeCandidate, setActiveCandidate] = useState<Candidate | null>(null);
  const [autoDialNumber, setAutoDialNumber] = useState<string | undefined>(undefined);
  const [autoDialTriggerId, setAutoDialTriggerId] = useState<string | undefined>(undefined);

  // Navigation tabs - default to Candidate Interview Hub
  const [sidebarTab, setSidebarTab] = useState<"interviews" | "dashboard" | "calls" | "logs" | "voice">("interviews");

  // Server health state
  const [serverHealth, setServerHealth] = useState<{ status: string; hasApiKey: boolean } | null>(null);

  // Voice Config States
  const [speechMode, setSpeechMode] = useState("Natural Female Voice (Azure Neerja / Pallavi)");
  const [languageFocus, setLanguageFocus] = useState("Automatic API");
  const [promptTemplate, setPromptTemplate] = useState(`You are Alex, an intelligent, empathetic, and professional AI Technical Recruiter and Interviewer.
Your goal is to conduct an objective, warm, and structured screening interview for the candidate.

INTERVIEW PROTOCOL:
1. Greet the candidate warmly and confirm they have 10-15 minutes for their screening call.
2. Ask 5 behavioral questions using the STAR framework.
3. Ask up to 10 personalized technical questions generated from their resume and target JD.
4. Listen attentively, allow them to fully express their experience, and ask relevant follow-up questions if their answer is incomplete.
5. Keep your responses concise (1-2 sentences) and maintain an encouraging, conversational tone.`);
  const [isSavingVoice, setIsSavingVoice] = useState(false);

  const handleSaveVoiceConfig = async () => {
    setIsSavingVoice(true);
    try {
      await fetch("/api/voice-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          speechMode,
          languageFocus,
          promptTemplate,
        }),
      });
      alert("AI Interviewer configuration saved successfully!");
    } catch (e: any) {
      console.error(e);
      alert("Failed to save configuration: " + e.message);
    } finally {
      setIsSavingVoice(false);
    }
  };

  // Fetch Data on Load & Setup Polling
  useEffect(() => {
    const fetchData = () => {
      fetch("/api/health")
        .then((res) => res.json())
        .then((data) => setServerHealth(data))
        .catch(() => setServerHealth(null));

      fetch("/api/voice-config")
        .then((res) => res.json())
        .then((data) => {
          if (data.speechMode) setSpeechMode(data.speechMode);
          if (data.languageFocus) setLanguageFocus(data.languageFocus);
          if (data.promptTemplate) setPromptTemplate(data.promptTemplate);
        })
        .catch((err) => console.error(err));

      fetch("/api/logs")
        .then((res) => res.json())
        .then((data) => {
          if (Array.isArray(data)) setLogs(data);
        })
        .catch((err) => console.error(err));
    };

    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleDeleteLog = async (logId: string) => {
    setLogs((prev) => prev.filter((l) => l.id !== logId));
    try {
      await fetch(`/api/logs/${logId}`, { method: "DELETE" });
    } catch (e) {
      console.error(e);
    }
  };

  const handleClearAllLogs = async () => {
    setLogs([]);
    try {
      await fetch("/api/logs", { method: "DELETE" });
    } catch (e) {
      console.error(e);
    }
  };

  const handleStartInterviewCall = (cand: Candidate) => {
    setActiveCandidate(cand);
    setAutoDialNumber(cand.phone);
    setAutoDialTriggerId(`call-${cand.id}-${Date.now()}`);
  };

  return (
    <div
      className={`min-h-screen flex flex-col font-sans relative overflow-hidden text-slate-800 ${
        sidebarTab !== "dashboard" ? "bg-[#faf9fa]" : ""
      }`}
      style={
        sidebarTab === "dashboard"
          ? {
              backgroundImage:
                "url('https://images.unsplash.com/photo-1514565131-fce0801e5785?auto=format&fit=crop&q=80')",
              backgroundSize: "cover",
              backgroundPosition: "center",
            }
          : {}
      }
    >
      {/* Dark gradient overlay that is darker on the left and transparent on the right (only on dashboard) */}
      {sidebarTab === "dashboard" && (
        <div className="absolute inset-0 bg-gradient-to-r from-slate-900/90 via-slate-800/50 to-transparent pointer-events-none z-0"></div>
      )}

      <div className="relative z-10 flex flex-col h-full">
        {/* Top Utility Bar */}
        <div className="h-8 bg-white/95 backdrop-blur-sm border-b border-gray-200 flex justify-end items-center px-8 text-[11px] text-gray-600 gap-6">
          <div className="flex items-center gap-1 cursor-pointer hover:text-indigo-600">
            <span className="w-3 h-3">📅</span> Screening Cohort 2026
          </div>
          <div className="flex items-center gap-1 border-l border-gray-300 pl-6 cursor-pointer hover:text-indigo-600">
            <span className="w-3 h-3">🌐</span> EN
          </div>
        </div>

        {/* Top Header Navigation */}
        <header className="h-16 bg-white px-4 md:px-8 flex items-center justify-between shrink-0 shadow-sm z-10">
          {/* Left Side: Logo & Brand */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-indigo-950 font-black text-2xl mr-4 tracking-tighter">
              <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center text-white shadow-md shadow-indigo-600/20">
                <Sparkles className="w-5 h-5 fill-white text-white" />
              </div>
              TalentAI <span className="font-normal text-slate-500">Autonomous Interviewer</span>
            </div>
          </div>

          {/* Right Side: Navigation Menu & Call Agent */}
          <div className="flex items-center gap-6">
            <nav className="hidden md:flex items-center gap-6">
              {[
                { id: "interviews", label: "Candidates & Pipeline" },
                { id: "dashboard", label: "Interview Analytics" },
                { id: "calls", label: "Call Records" },
                { id: "logs", label: "System Logs" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setSidebarTab(tab.id as any)}
                  className={`font-bold text-[13px] transition-colors ${
                    sidebarTab === tab.id
                      ? "text-indigo-900 border-b-2 border-indigo-900 pb-1 -mb-1"
                      : "text-slate-700 hover:text-indigo-900"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </nav>

            {/* Settings Menu Access */}
            <button
              onClick={() => setSidebarTab("voice")}
              className={`p-2 rounded-full transition-colors ${
                sidebarTab === "voice"
                  ? "bg-indigo-100 text-indigo-700"
                  : "text-slate-400 hover:text-indigo-600 hover:bg-slate-100"
              }`}
              title="Agent Settings & Prompt Configuration"
            >
              <Settings className="w-5 h-5" />
            </button>

            {/* Live Audio & Dialer Console */}
            <TeleforceAgent
              autoDialNumber={autoDialNumber}
              autoDialTriggerId={autoDialTriggerId}
              candidateId={activeCandidate ? activeCandidate.id : undefined}
              candidateName={activeCandidate ? activeCandidate.name : undefined}
              candidateRole={activeCandidate ? activeCandidate.position : undefined}
              onCallEnded={() => {
                setActiveCandidate(null);
                setAutoDialNumber(undefined);
              }}
            />
          </div>
        </header>

        {/* Dynamic Scrollable Body Content */}
        <div className="flex-1 overflow-y-auto">
          {sidebarTab === "interviews" && (
            <div className="p-4 md:p-8">
              <CandidateManager onStartInterviewCall={handleStartInterviewCall} />
            </div>
          )}

          {sidebarTab === "dashboard" && (
            <div className="space-y-6 p-4 md:p-8">
              <Metrics />
            </div>
          )}

          {sidebarTab === "calls" && <CallHistory />}

          {sidebarTab === "logs" && (
            <CallLogs
              logs={logs}
              onDeleteLog={handleDeleteLog}
              onClearAllLogs={handleClearAllLogs}
            />
          )}

          {sidebarTab === "voice" && (
            <div className="bg-white/95 backdrop-blur-xl rounded-3xl border border-slate-200/80 shadow-2xl p-8 max-w-4xl mx-auto space-y-7 my-6">
              <div className="border-b border-slate-100 pb-5 flex items-center justify-between">
                <div>
                  <h2 className="font-extrabold text-slate-900 text-xl tracking-tight flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-indigo-600" /> AI Interviewer Persona & Voice Configuration
                  </h2>
                  <p className="text-xs font-medium text-slate-500 mt-1">
                    Configure interviewer persona, behavioral & technical screening directive, speech voices, and language defaults.
                  </p>
                </div>
                <div className="px-3 py-1 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full text-[11px] font-bold flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> Interview Pipeline Active
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="block text-xs font-bold text-slate-600 uppercase tracking-wider">
                    AI Speech Mode & Voice
                  </label>
                  <select
                    value={speechMode}
                    onChange={(e) => setSpeechMode(e.target.value)}
                    className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 text-xs font-semibold text-slate-800 shadow-sm transition"
                  >
                    <option value="Natural Female Voice (Azure Neerja / Pallavi)">Natural Female Voice (Azure Neerja / Pallavi)</option>
                    <option value="Premium Male Voice (Azure Valluvar / Deep)">Premium Male Voice (Azure Valluvar / Deep)</option>
                    <option value="Tamil Female Voice (Pallavi Neural)">Tamil Female Voice (Pallavi Neural)</option>
                    <option value="Tamil Male Voice (Valluvar Neural)">Tamil Male Voice (Valluvar Neural)</option>
                    <option value="Hindi Female Voice (Swara Neural)">Hindi Female Voice (Swara Neural)</option>
                    <option value="Telugu Female Voice (Shruti Neural)">Telugu Female Voice (Shruti Neural)</option>
                    <option value="Kannada Female Voice (Sapna Neural)">Kannada Female Voice (Sapna Neural)</option>
                    <option value="Malayalam Female Voice (Sobhana Neural)">Malayalam Female Voice (Sobhana Neural)</option>
                  </select>
                </div>

                <div className="space-y-2">
                  <label className="block text-xs font-bold text-slate-600 uppercase tracking-wider">
                    Default Language Focus
                  </label>
                  <div className="flex gap-2 flex-wrap">
                    {[
                      { name: "Automatic API", label: "Auto Detect" },
                      { name: "English", label: "English" },
                      { name: "Tamil Support", label: "Tamil தமிழ்" },
                      { name: "Hindi Support", label: "Hindi हिंदी" },
                      { name: "Telugu Support", label: "Telugu తెలుగు" },
                      { name: "Kannada Support", label: "Kannada ಕನ್ನಡ" },
                      { name: "Malayalam Support", label: "Malayalam മലയാളം" },
                    ].map((lang) => (
                      <button
                        key={lang.name}
                        onClick={() => setLanguageFocus(lang.name)}
                        className={`px-3 py-2 text-[11px] font-bold rounded-xl transition border shadow-sm ${
                          languageFocus === lang.name
                            ? "bg-indigo-600 text-white border-indigo-600 shadow-indigo-200 shadow-md scale-105"
                            : "bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100"
                        }`}
                      >
                        {lang.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <label className="block text-xs font-bold text-slate-600 uppercase tracking-wider">
                  System Prompt Directive Template
                </label>
                <textarea
                  value={promptTemplate}
                  onChange={(e) => setPromptTemplate(e.target.value)}
                  rows={8}
                  className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-xs font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 leading-relaxed text-slate-800 shadow-inner"
                />
              </div>

              <div className="p-4 bg-indigo-50/70 rounded-2xl flex items-start gap-3 border border-indigo-100/80">
                <Sparkles className="w-5 h-5 text-indigo-600 shrink-0 mt-0.5" />
                <div className="text-xs">
                  <p className="font-bold text-indigo-900">Autonomous Conversational Interview Engine</p>
                  <p className="text-indigo-700/80 mt-1 leading-relaxed">
                    TalentAI autonomously evaluates candidate responses against the job description and resume, administering 5 behavioral and up to 10 tailored technical questions with sub-500ms voice streaming.
                  </p>
                </div>
              </div>

              <div className="flex justify-end pt-3 border-t border-slate-100">
                <button
                  onClick={handleSaveVoiceConfig}
                  disabled={isSavingVoice}
                  className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-500 text-white font-bold py-3 px-8 rounded-2xl transition duration-150 flex items-center gap-2.5 text-xs tracking-wide shadow-lg shadow-indigo-100 active:scale-95 cursor-pointer"
                >
                  <CheckCircle className="w-4 h-4" />
                  {isSavingVoice ? "Saving..." : "Save Configuration"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
