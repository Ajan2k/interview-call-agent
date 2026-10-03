import { useState, useEffect } from "react";
import { PhoneIncoming, PhoneOutgoing, History, FileAudio, MessageSquare } from "lucide-react";
import { ConversationModal } from "./ConversationModal";

interface CallRecord {
  id: string;
  direction: "incoming" | "outgoing";
  phone?: string;
  start: string;
  end: string;
  duration_sec: number;
  language: string;
  lead?: string;
  ended_by: string;
  recording: string | null;
}

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function CallHistory() {
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [openCall, setOpenCall] = useState<CallRecord | null>(null);

  useEffect(() => {
    const fetchData = () => {
      fetch("/api/call-history")
        .then((r) => r.json())
        .then((d) => Array.isArray(d) && setCalls(d))
        .catch(() => {});
    };
    fetchData();
    const iv = setInterval(fetchData, 5000);
    return () => clearInterval(iv);
  }, []);

  return (
    <div className="p-4 md:p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <History className="w-5 h-5 text-indigo-600" /> Interview Call Records & Transcripts
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Audio recordings, call durations, and full bilingual transcripts for all candidate phone interviews.
          </p>
        </div>
        <span className="text-xs font-bold bg-indigo-50 text-indigo-700 border border-indigo-200 px-3 py-1 rounded-full">
          {calls.length} Total Recorded Calls
        </span>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        {calls.length === 0 ? (
          <div className="p-12 text-center text-slate-400 text-xs italic">
            No interview calls recorded yet. Initiating a candidate interview call will save its audio and transcript here.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-bold border-b border-slate-200 uppercase text-[10px] tracking-wider">
                <tr>
                  <th className="py-3 px-4">Direction</th>
                  <th className="py-3 px-4">Candidate Phone</th>
                  <th className="py-3 px-4">Date & Time</th>
                  <th className="py-3 px-4">Duration</th>
                  <th className="py-3 px-4">Language</th>
                  <th className="py-3 px-4">Audio Recording</th>
                  <th className="py-3 px-4 text-right">Transcript</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {calls.map((call) => (
                  <tr key={call.id} className="hover:bg-slate-50/60 transition">
                    <td className="py-3 px-4">
                      {call.direction === "incoming" ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-100">
                          <PhoneIncoming className="w-3 h-3" /> Inbound
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-bold text-purple-600 bg-purple-50 px-2 py-0.5 rounded-full border border-purple-100">
                          <PhoneOutgoing className="w-3 h-3" /> Outbound
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 font-mono font-medium text-slate-700">
                      {call.phone || "Unknown Candidate"}
                    </td>
                    <td className="py-3 px-4 text-slate-500">
                      {call.start || "-"}
                    </td>
                    <td className="py-3 px-4 font-mono font-semibold text-slate-700">
                      {formatDuration(call.duration_sec)}
                    </td>
                    <td className="py-3 px-4">
                      <span className="text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                        {call.language || "en-IN"}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      {call.recording ? (
                        <audio
                          controls
                          src={`/api/recordings/${encodeURIComponent(call.recording.split("/").pop() || "")}`}
                          className="h-7 w-48"
                        />
                      ) : (
                        <span className="text-slate-400 text-[11px] italic flex items-center gap-1">
                          <FileAudio className="w-3 h-3" /> No Audio
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => setOpenCall(call)}
                        className="inline-flex items-center gap-1 text-[11px] font-bold text-indigo-600 hover:text-indigo-700 bg-indigo-50 hover:bg-indigo-100 px-2.5 py-1 rounded-lg border border-indigo-200 transition"
                      >
                        <MessageSquare className="w-3 h-3" /> View Transcript
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {openCall && (
        <ConversationModal
          callId={openCall.id}
          phone={openCall.phone}
          time={openCall.start}
          duration={openCall.duration_sec}
          onClose={() => setOpenCall(null)}
        />
      )}
    </div>
  );
}
