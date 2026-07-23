import { useState, useEffect } from "react";
import { PhoneIncoming, PhoneOutgoing, CalendarCheck, History, FileAudio, MessageSquare } from "lucide-react";
import { ConversationModal } from "./ConversationModal";

interface CallRecord {
  id: string;
  direction: "incoming" | "outgoing";
  phone?: string;
  start: string;
  end: string;
  duration_sec: number;
  language: string;
  lead: string;
  meeting: string;
  ended_by: string;
  recording: string | null;
}

interface Meeting {
  time: string;
  call_id: string;
  direction: string;
  phone?: string;
  language: string;
  details: string;
}


function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function leadStatus(lead: string): string {
  const m = lead.match(/status\s*=\s*([A-Z_]+)/i);
  return m ? m[1].toUpperCase() : "-";
}

const LEAD_BADGE: Record<string, string> = {
  HOT: "bg-emerald-50 text-emerald-700 border-emerald-200",
  WARM: "bg-amber-50 text-amber-700 border-amber-200",
  COLD: "bg-slate-50 text-slate-500 border-slate-200",
  INCOMPLETE: "bg-rose-50 text-rose-600 border-rose-200",
};

export function CallHistory() {
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [openCall, setOpenCall] = useState<CallRecord | null>(null);
  const [view, setView] = useState<"history" | "demos">("history");

  useEffect(() => {
    const fetchData = () => {
      fetch("/api/call-history")
        .then((r) => r.json())
        .then((d) => Array.isArray(d) && setCalls(d))
        .catch(() => {});
      fetch("/api/meetings")
        .then((r) => r.json())
        .then((d) => Array.isArray(d) && setMeetings(d))
        .catch(() => {});
    };
    fetchData();
    const iv = setInterval(fetchData, 5000);
    return () => clearInterval(iv);
  }, []);

  return (
    <div className="p-4 md:p-8 space-y-6">
      {/* SUB-TAB SWITCHER */}
      <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-xl p-1 w-fit shadow-sm">
        <button
          onClick={() => setView("history")}
          className={`flex items-center gap-2 text-xs font-bold px-4 py-2 rounded-lg transition ${
            view === "history" ? "bg-indigo-600 text-white shadow" : "text-slate-600 hover:bg-slate-50"
          }`}
        >
          <History className="w-4 h-4" /> Call History
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${view === "history" ? "bg-indigo-500" : "bg-slate-100 text-slate-500"}`}>{calls.length}</span>
        </button>
        <button
          onClick={() => setView("demos")}
          className={`flex items-center gap-2 text-xs font-bold px-4 py-2 rounded-lg transition ${
            view === "demos" ? "bg-emerald-600 text-white shadow" : "text-slate-600 hover:bg-slate-50"
          }`}
        >
          <CalendarCheck className="w-4 h-4" /> Booked Demos
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${view === "demos" ? "bg-emerald-500" : "bg-slate-100 text-slate-500"}`}>{meetings.length}</span>
        </button>
      </div>

      {/* BOOKED DEMOS */}
      {view === "demos" && (
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <div className="flex items-center gap-2 mb-4">
          <CalendarCheck className="w-5 h-5 text-emerald-600" />
          <h2 className="font-extrabold text-slate-900 text-sm uppercase tracking-wider">Booked Demos</h2>
          <span className="ml-auto text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full">
            {meetings.length} booked
          </span>
        </div>
        {meetings.length === 0 ? (
          <p className="text-xs text-slate-400 italic py-4 text-center">
            No demos booked yet. When the AI agent books a demo on a call, it appears here.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {meetings.map((m, i) => (
              <div key={i} className="border border-emerald-100 bg-emerald-50/40 rounded-xl p-4">
                <div className="font-bold text-slate-800 text-sm">{m.details}</div>
                <div className="flex items-center gap-2 mt-2 text-[10px] text-slate-500 font-semibold flex-wrap">
                  {m.direction === "incoming" ? (
                    <span className="flex items-center gap-1 text-indigo-600"><PhoneIncoming className="w-3 h-3" /> Incoming</span>
                  ) : (
                    <span className="flex items-center gap-1 text-purple-600"><PhoneOutgoing className="w-3 h-3" /> Outgoing</span>
                  )}
                  {m.phone && (
                    <>
                      <span>•</span>
                      <span className="font-mono text-slate-700">{m.phone}</span>
                    </>
                  )}
                  <span>•</span>
                  <span>{m.language}</span>
                  <span>•</span>
                  <span>{m.time}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      )}

      {/* CALL HISTORY */}
      {view === "history" && (
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <div className="flex items-center gap-2 mb-4">
          <History className="w-5 h-5 text-indigo-600" />
          <h2 className="font-extrabold text-slate-900 text-sm uppercase tracking-wider">Call History</h2>
          <span className="ml-auto text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200 px-2 py-0.5 rounded-full">
            {calls.length} calls
          </span>
        </div>
        {calls.length === 0 ? (
          <p className="text-xs text-slate-400 italic py-4 text-center">
            No calls recorded yet. Completed calls appear here with their recording.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="py-2 pr-4 text-[10px] font-black text-slate-500 uppercase tracking-wider">Direction</th>
                  <th className="py-2 pr-4 text-[10px] font-black text-slate-500 uppercase tracking-wider">Phone</th>
                  <th className="py-2 pr-4 text-[10px] font-black text-slate-500 uppercase tracking-wider">Time</th>
                  <th className="py-2 pr-4 text-[10px] font-black text-slate-500 uppercase tracking-wider">Duration</th>
                  <th className="py-2 pr-4 text-[10px] font-black text-slate-500 uppercase tracking-wider">Lang</th>
                  <th className="py-2 pr-4 text-[10px] font-black text-slate-500 uppercase tracking-wider">Lead</th>
                  <th className="py-2 pr-4 text-[10px] font-black text-slate-500 uppercase tracking-wider">Demo</th>
                  <th className="py-2 text-[10px] font-black text-slate-500 uppercase tracking-wider">Recording</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {calls.map((c) => {
                  const status = leadStatus(c.lead);
                  return (
                    <tr key={c.id} className="hover:bg-slate-50/60">
                      <td className="py-2.5 pr-4">
                        {c.direction === "incoming" ? (
                          <span className="flex items-center gap-1.5 text-indigo-600 font-bold text-xs">
                            <PhoneIncoming className="w-3.5 h-3.5" /> Incoming
                          </span>
                        ) : (
                          <span className="flex items-center gap-1.5 text-purple-600 font-bold text-xs">
                            <PhoneOutgoing className="w-3.5 h-3.5" /> Outgoing
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 pr-4">
                        <button
                          onClick={() => setOpenCall(c)}
                          className="flex items-center gap-1.5 font-mono text-xs font-bold text-indigo-600 hover:text-indigo-800 hover:underline"
                          title="View full conversation"
                        >
                          <MessageSquare className="w-3.5 h-3.5" />
                          {c.phone || "unknown"}
                        </button>
                      </td>
                      <td className="py-2.5 pr-4 font-mono text-[11px] text-slate-600">{c.start}</td>
                      <td className="py-2.5 pr-4 font-mono text-xs font-bold text-slate-700">{formatDuration(c.duration_sec)}</td>
                      <td className="py-2.5 pr-4 text-[11px] font-semibold text-slate-500">{c.language}</td>
                      <td className="py-2.5 pr-4">
                        <span className={`text-[9px] font-black px-2 py-0.5 rounded-full border ${LEAD_BADGE[status] || LEAD_BADGE.COLD}`} title={c.lead}>
                          {status}
                        </span>
                      </td>
                      <td className="py-2.5 pr-4 text-[11px] font-semibold text-emerald-700">
                        {c.meeting || <span className="text-slate-300">—</span>}
                      </td>
                      <td className="py-2.5">
                        {c.recording ? (
                          <audio controls preload="none" className="h-8 max-w-[220px]" src={`/api/recordings/${c.recording}`} />
                        ) : (
                          <span className="flex items-center gap-1 text-slate-300 text-[10px]"><FileAudio className="w-3 h-3" /> none</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      )}

      {openCall && (
        <ConversationModal
          callId={openCall.id}
          phone={openCall.phone || ""}
          direction={openCall.direction}
          onClose={() => setOpenCall(null)}
        />
      )}
    </div>
  );
}
