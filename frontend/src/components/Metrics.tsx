import { useState, useEffect, type ReactNode } from "react";
import {
  Users,
  CheckCircle,
  Clock,
  Sparkles,
  TrendingUp,
  Award,
  AlertCircle,
  ThumbsUp,
} from "lucide-react";
import { Candidate } from "../types";

function Card({
  icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  sub?: string;
  accent: string;
}) {
  return (
    <div className="bg-white/95 backdrop-blur-sm rounded-xl p-4 shadow-lg border border-white/40 h-[120px] flex flex-col justify-between hover:shadow-xl transition-shadow">
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] font-bold text-slate-600 leading-snug">{label}</h3>
        <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${accent}`}>{icon}</div>
      </div>
      <div>
        <p className="text-3xl font-black text-slate-800 leading-none">{value}</p>
        {sub && <p className="text-[10px] text-slate-400 font-semibold mt-1">{sub}</p>}
      </div>
    </div>
  );
}

export const Metrics = () => {
  const [candidates, setCandidates] = useState<Candidate[]>([]);

  useEffect(() => {
    const fetchData = () => {
      fetch("/api/candidates")
        .then((r) => r.json())
        .then((d) => Array.isArray(d) && setCandidates(d))
        .catch(() => {});
    };
    fetchData();
    const iv = setInterval(fetchData, 5000);
    return () => clearInterval(iv);
  }, []);

  const total = candidates.length;
  const evaluated = candidates.filter((c) => c.status === "evaluated" || c.scorecard);
  const hireCount = evaluated.filter((c) => c.scorecard?.recommendation?.toLowerCase().includes("hire")).length;
  const considerCount = evaluated.filter((c) => c.scorecard?.recommendation?.toLowerCase().includes("consider")).length;
  const inProgress = candidates.filter((c) => c.status === "in_progress").length;

  const avgOverallScore =
    evaluated.length > 0
      ? Math.round(
          evaluated.reduce((acc, c) => acc + (c.scorecard?.overall_score || 0), 0) / evaluated.length
        )
      : 0;

  const avgTechScore =
    evaluated.length > 0
      ? Math.round(
          evaluated.reduce((acc, c) => acc + (c.scorecard?.technical_score || 0), 0) / evaluated.length
        )
      : 0;

  return (
    <div className="w-full lg:w-4/5 xl:w-[72%] mt-8 pr-4 md:pr-8">
      <h2 className="text-white font-bold text-sm mb-6 tracking-wide drop-shadow-md">
        AI Interview Pipeline Analytics
      </h2>
      <div id="metrics-container" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-2">
        <Card
          icon={<Users className="w-4 h-4 text-white" />}
          accent="bg-indigo-600"
          label="Total Candidates"
          value={total}
          sub="dossiers ingested"
        />
        <Card
          icon={<CheckCircle className="w-4 h-4 text-white" />}
          accent="bg-emerald-500"
          label="Interviews Completed"
          value={evaluated.length}
          sub="scorecard generated"
        />
        <Card
          icon={<ThumbsUp className="w-4 h-4 text-white" />}
          accent="bg-blue-500"
          label="Hire Recommendations"
          value={hireCount}
          sub="top qualified candidates"
        />
        <Card
          icon={<AlertCircle className="w-4 h-4 text-white" />}
          accent="bg-amber-500"
          label="Under Consideration"
          value={considerCount}
          sub="further review advised"
        />
        <Card
          icon={<Award className="w-4 h-4 text-white" />}
          accent="bg-purple-600"
          label="Avg Overall Score"
          value={evaluated.length > 0 ? `${avgOverallScore}/100` : "N/A"}
          sub="across all interviews"
        />
        <Card
          icon={<TrendingUp className="w-4 h-4 text-white" />}
          accent="bg-teal-500"
          label="Avg Technical Rating"
          value={evaluated.length > 0 ? `${avgTechScore}/100` : "N/A"}
          sub="JD competency match"
        />
        <Card
          icon={<Clock className="w-4 h-4 text-white" />}
          accent="bg-rose-500"
          label="In Progress / Queued"
          value={inProgress}
          sub="active screening calls"
        />
        <Card
          icon={<Sparkles className="w-4 h-4 text-white" />}
          accent="bg-indigo-800"
          label="Autonomous Mode"
          value="100%"
          sub="resume + JD tailored"
        />
      </div>
    </div>
  );
};
