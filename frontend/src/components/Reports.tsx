import { useState, useEffect, useCallback, type ReactNode } from "react";
import {
  BarChart3, Download, PhoneIncoming, PhoneOutgoing, Filter,
  Flame, CalendarCheck, Clock, Phone,
} from "lucide-react";

interface CallRecord {
  id: string;
  direction: "incoming" | "outgoing";
  phone?: string;
  start: string;
  end: string;
  duration_sec: number;
  language: string;
  lead: string;
  lead_status?: string;
  meeting: string;
  ended_by: string;
  recording: string | null;
}

interface Summary {
  total: number;
  incoming: number;
  outgoing: number;
  hot: number;
  warm: number;
  cold: number;
  incomplete: number;
  demos_booked: number;
  total_duration_sec: number;
  avg_duration_sec: number;
}

const LANGS = [
  { code: "", label: "All Languages" },
  { code: "ta-IN", label: "Tamil" },
  { code: "te-IN", label: "Telugu" },
  { code: "kn-IN", label: "Kannada" },
  { code: "ml-IN", label: "Malayalam" },
  { code: "hi-IN", label: "Hindi" },
  { code: "en-IN", label: "English" },
];

const LEAD_BADGE: Record<string, string> = {
  HOT: "bg-emerald-50 text-emerald-700 border-emerald-200",
  WARM: "bg-amber-50 text-amber-700 border-amber-200",
  COLD: "bg-slate-50 text-slate-500 border-slate-200",
  INCOMPLETE: "bg-rose-50 text-rose-600 border-rose-200",
};

function fmtDur(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function leadOf(c: CallRecord): string {
  if (c.lead_status) return c.lead_status.toUpperCase();
  const m = (c.lead || "").match(/status\s*=\s*([A-Za-z_]+)/i);
  return m ? m[1].toUpperCase() : "";
}

function StatCard({ icon, label, value, tone }: { icon: ReactNode; label: string; value: string | number; tone: string }) {
  return (
    <div className={`rounded-xl border p-4 flex flex-col gap-1 ${tone}`}>
      <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider opacity-80">
        {icon} {label}
      </div>
      <div className="text-2xl font-black">{value}</div>
    </div>
  );
}

export function Reports() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [direction, setDirection] = useState("");
  const [lead, setLead] = useState("");
  const [language, setLanguage] = useState("");

  const [summary, setSummary] = useState<Summary | null>(null);
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [loading, setLoading] = useState(false);

  const queryString = useCallback(() => {
    const p = new URLSearchParams();
    if (from) p.set("from", from);
    if (to) p.set("to", to);
    if (direction) p.set("direction", direction);
    if (lead) p.set("lead", lead);
    if (language) p.set("language", language);
    return p.toString();
  }, [from, to, direction, lead, language]);

  const fetchReport = useCallback(() => {
    setLoading(true);
    fetch(`/api/report?${queryString()}`)
      .then((r) => r.json())
      .then((d) => {
        setSummary(d.summary || null);
        setCalls(Array.isArray(d.calls) ? d.calls : []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [queryString]);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  const downloadCsv = () => {
    window.open(`/api/report/export?${queryString()}`, "_blank");
  };

  const resetFilters = () => {
    setFrom(""); setTo(""); setDirection(""); setLead(""); setLanguage("");
  };

  return (
    <div className="p-4 md:p-8 space-y-6">
      {/* HEADER */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-6 h-6 text-indigo-600" />
          <h1 className="font-extrabold text-slate-900 text-xl tracking-tight">Reports</h1>
        </div>
        <button
          onClick={downloadCsv}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow-sm transition"
        >
          <Download className="w-4 h-4" /> Export CSV
        </button>
      </div>

      {/* FILTERS */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
        <div className="flex items-center gap-2 mb-4">
          <Filter className="w-4 h-4 text-slate-500" />
          <h2 className="font-bold text-slate-700 text-xs uppercase tracking-wider">Filters</h2>
          <button onClick={resetFilters} className="ml-auto text-[11px] font-semibold text-indigo-600 hover:underline">
            Reset
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-bold text-slate-500 uppercase">From</label>
            <input type="date" value={from} onChange={(e) => setFrom(e.target.value)}
              className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-bold text-slate-500 uppercase">To</label>
            <input type="date" value={to} onChange={(e) => setTo(e.target.value)}
              className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-bold text-slate-500 uppercase">Direction</label>
            <select value={direction} onChange={(e) => setDirection(e.target.value)}
              className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="">All</option>
              <option value="incoming">Incoming</option>
              <option value="outgoing">Outgoing</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-bold text-slate-500 uppercase">Lead Status</label>
            <select value={lead} onChange={(e) => setLead(e.target.value)}
              className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="">All</option>
              <option value="HOT">Hot</option>
              <option value="WARM">Warm</option>
              <option value="COLD">Cold</option>
              <option value="INCOMPLETE">Incomplete</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-bold text-slate-500 uppercase">Language</label>
            <select value={language} onChange={(e) => setLanguage(e.target.value)}
              className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              {LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* SUMMARY CARDS */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <StatCard icon={<Phone className="w-3 h-3" />} label="Total Calls" value={summary.total} tone="bg-white border-slate-200 text-slate-800" />
          <StatCard icon={<PhoneIncoming className="w-3 h-3" />} label="Incoming" value={summary.incoming} tone="bg-indigo-50 border-indigo-200 text-indigo-700" />
          <StatCard icon={<PhoneOutgoing className="w-3 h-3" />} label="Outgoing" value={summary.outgoing} tone="bg-purple-50 border-purple-200 text-purple-700" />
          <StatCard icon={<Flame className="w-3 h-3" />} label="Hot Leads" value={summary.hot} tone="bg-emerald-50 border-emerald-200 text-emerald-700" />
          <StatCard icon={<CalendarCheck className="w-3 h-3" />} label="Demos Booked" value={summary.demos_booked} tone="bg-teal-50 border-teal-200 text-teal-700" />
          <StatCard icon={<Clock className="w-3 h-3" />} label="Avg Duration" value={fmtDur(summary.avg_duration_sec)} tone="bg-white border-slate-200 text-slate-800" />
        </div>
      )}

      {/* RESULTS TABLE */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <div className="flex items-center gap-2 mb-4">
          <h2 className="font-extrabold text-slate-900 text-sm uppercase tracking-wider">Results</h2>
          <span className="ml-auto text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200 px-2 py-0.5 rounded-full">
            {loading ? "Loading…" : `${calls.length} calls`}
          </span>
        </div>
        {calls.length === 0 ? (
          <p className="text-xs text-slate-400 italic py-6 text-center">No calls match these filters.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-slate-200">
                  {["Direction", "Phone", "Time", "Duration", "Lang", "Lead", "Demo"].map((h) => (
                    <th key={h} className="py-2 pr-4 text-[10px] font-black text-slate-500 uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {calls.map((c) => {
                  const status = leadOf(c);
                  return (
                    <tr key={c.id} className="hover:bg-slate-50/60">
                      <td className="py-2.5 pr-4">
                        {c.direction === "incoming" ? (
                          <span className="flex items-center gap-1.5 text-indigo-600 font-bold text-xs"><PhoneIncoming className="w-3.5 h-3.5" /> Incoming</span>
                        ) : (
                          <span className="flex items-center gap-1.5 text-purple-600 font-bold text-xs"><PhoneOutgoing className="w-3.5 h-3.5" /> Outgoing</span>
                        )}
                      </td>
                      <td className="py-2.5 pr-4 font-mono text-xs font-bold text-slate-800">
                        {c.phone || <span className="text-slate-300 font-normal">unknown</span>}
                      </td>
                      <td className="py-2.5 pr-4 font-mono text-[11px] text-slate-600">{c.start}</td>
                      <td className="py-2.5 pr-4 font-mono text-xs font-bold text-slate-700">{fmtDur(c.duration_sec)}</td>
                      <td className="py-2.5 pr-4 text-[11px] font-semibold text-slate-500">{c.language}</td>
                      <td className="py-2.5 pr-4">
                        <span className={`text-[9px] font-black px-2 py-0.5 rounded-full border ${LEAD_BADGE[status] || LEAD_BADGE.COLD}`} title={c.lead}>
                          {status || "-"}
                        </span>
                      </td>
                      <td className="py-2.5 pr-4 text-[11px] font-semibold text-emerald-700">
                        {c.meeting || <span className="text-slate-300">—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
