import React, { useState } from "react";
import { Search, Clock, MessageSquare, Download, CheckCircle2, AlertCircle, Trash2, ArrowUpRight, Smile, Meh, Frown } from "lucide-react";
import { CallLog } from "../types";
import { StratroomHeader, StratroomTable, StratroomThead, StratroomTh, StratroomTr, StratroomTd, StratroomActions, StratroomStatus } from "./ui";

interface CallLogsProps {
  logs: CallLog[];
  onDeleteLog: (logId: string) => void;
  onClearAllLogs: () => void;
}

export const CallLogs: React.FC<CallLogsProps> = ({
  logs,
  onDeleteLog,
  onClearAllLogs,
}) => {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedLog, setSelectedLog] = useState<CallLog | null>(null);

  const filteredLogs = logs.filter(
    (log) => {
      if (!log) return false;
      const contactName = (log.contactName || log.message || "").toLowerCase();
      const phone = log.phone || "";
      const campaignName = (log.campaignName || "").toLowerCase();
      const term = searchTerm.toLowerCase();

      return contactName.includes(term) || phone.includes(searchTerm) || campaignName.includes(term);
    }
  );

  const formatDuration = (sec?: number) => {
    if (!sec) return "0m 0s";
    const mins = Math.floor(sec / 60);
    const secs = sec % 60;
    return `${mins}m ${secs}s`;
  };

  const formatDate = (isoStr: string) => {
    try {
      const date = new Date(isoStr);
      return date.toLocaleDateString() + " " + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
      return isoStr;
    }
  };

  const handleExportCSV = () => {
    if (logs.length === 0) return;
    
    const headers = ["ID", "Contact Name", "Phone", "Campaign", "Duration (s)", "Outcome", "Sentiment", "Time", "Notes"];
    const rows = logs.map((l) => [
      l.id,
      l.contactName,
      l.phone,
      l.campaignName,
      l.duration,
      l.outcome,
      l.sentiment,
      l.time,
      l.notes || "N/A"
    ]);

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((r) => r.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))].join("\n");
    
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `SkyAgent_CallLogs_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div id="call-logs-container" className="flex-1 flex flex-col min-h-[600px]">
      <StratroomHeader title="CAMPAIGN DIALOGUE LOGS" icon={MessageSquare}>
        <div className="flex items-center bg-white border border-gray-200 rounded-md shadow-sm h-8 mr-2">
          <Search className="w-3.5 h-3.5 text-slate-400 ml-2.5" />
          <input
            id="input-log-search"
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by name, campaign..."
            className="w-48 focus:w-64 transition-all px-2 py-1 text-[11px] focus:outline-none text-slate-800 placeholder-slate-400"
          />
        </div>
        <button
          id="btn-export-logs"
          onClick={handleExportCSV}
          disabled={logs.length === 0}
          className="flex items-center gap-1 bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 text-[10px] font-bold px-3 py-1.5 rounded transition shadow-sm disabled:opacity-50"
        >
          <Download className="w-3 h-3 text-slate-500" /> Export
        </button>
        <button
          id="btn-clear-logs"
          onClick={onClearAllLogs}
          disabled={logs.length === 0}
          className="flex items-center gap-1 bg-white hover:bg-rose-50 text-rose-600 border border-rose-200 text-[10px] font-bold px-3 py-1.5 rounded transition shadow-sm disabled:opacity-50"
        >
          <Trash2 className="w-3 h-3" /> Clear
        </button>
      </StratroomHeader>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Table List Column */}
        <div className="lg:col-span-2">
          <StratroomTable>
            <StratroomThead>
              <StratroomTh>Customer Details</StratroomTh>
              <StratroomTh>Campaign</StratroomTh>
              <StratroomTh>Duration</StratroomTh>
              <StratroomTh>Outcome</StratroomTh>
              <StratroomTh>Sentiment</StratroomTh>
              <StratroomTh className="text-right">Actions</StratroomTh>
            </StratroomThead>
            <tbody className="divide-y divide-gray-100">
              {filteredLogs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500 text-[11px] font-medium bg-transparent">
                    No matching dialogue logs found.
                  </td>
                </tr>
              ) : (
                filteredLogs.map((log) => (
                  <StratroomTr
                    key={log.id}
                    className={selectedLog?.id === log.id ? "bg-purple-50/50" : ""}
                  >
                    <StratroomTd>
                      <div className="flex items-center gap-3 cursor-pointer" onClick={() => setSelectedLog(log)}>
                        <div className="w-7 h-7 rounded-full bg-slate-100 border border-slate-200 text-slate-500 flex items-center justify-center font-bold text-[10px] uppercase shadow-sm">
                          {(log.contactName || log.message || "C").charAt(0)}
                        </div>
                        <div>
                          <div className="font-bold text-slate-800 text-xs">{log.contactName || log.message || "Call Log"}</div>
                          <div className="text-[9px] text-slate-500 font-semibold uppercase mt-0.5">{log.phone || log.timestamp || ""}</div>
                        </div>
                      </div>
                    </StratroomTd>
                    <StratroomTd>
                      <span className="font-bold text-slate-600 cursor-pointer" onClick={() => setSelectedLog(log)}>{log.campaignName || "Default Campaign"}</span>
                    </StratroomTd>
                    <StratroomTd>
                      <span className="font-mono font-medium text-slate-600">{formatDuration(log.duration)}</span>
                    </StratroomTd>
                    <StratroomTd>
                      <StratroomStatus status={log.outcome || "Completed"} />
                    </StratroomTd>
                    <StratroomTd>
                      <div className="flex items-center gap-1.5">
                        {log.sentiment === "Positive" && <Smile className="w-3.5 h-3.5 text-emerald-500" />}
                        {log.sentiment === "Negative" && <Frown className="w-3.5 h-3.5 text-rose-500" />}
                        {(log.sentiment === "Neutral" || !log.sentiment) && <Meh className="w-3.5 h-3.5 text-slate-400" />}
                        <span className={`text-[10px] font-bold ${
                          log.sentiment === "Positive" ? "text-emerald-600" :
                          log.sentiment === "Negative" ? "text-rose-600" : "text-slate-500"
                        }`}>
                          {log.sentiment || "Neutral"}
                        </span>
                      </div>
                    </StratroomTd>
                    <StratroomTd>
                      <StratroomActions 
                        onCall={() => setSelectedLog(log)}
                        onDelete={() => onDeleteLog(log.id)}
                      />
                    </StratroomTd>
                  </StratroomTr>
                ))
              )}
            </tbody>
            </StratroomTable>
        </div>

        {/* Selected Log Detail Inspection Box */}
        <div className="border border-sky-100 rounded-2xl bg-sky-50/5 p-5 flex flex-col h-[400px]">
          {selectedLog ? (
            <div id="log-inspector-details" className="flex flex-col h-full overflow-hidden">
              <div className="shrink-0 border-b border-sky-100/50 pb-3 mb-3">
                <p className="text-[9px] uppercase font-bold tracking-widest text-sky-500">Log Inspector</p>
                <h4 className="font-bold text-slate-800 text-sm mt-0.5">{selectedLog.contactName || selectedLog.message || "Call Log"}</h4>
                <div className="flex items-center justify-between text-[11px] text-slate-400 mt-1">
                  <span>{formatDate(selectedLog.time || selectedLog.timestamp || "")}</span>
                  <span className="font-mono">{formatDuration(selectedLog.duration)}</span>
                </div>
              </div>

              {/* Transcript Speech Bubbles */}
              <div className="flex-1 overflow-y-auto space-y-3 pr-1 text-xs min-h-0">
                <div className="p-3 bg-white rounded-xl border border-sky-100/30">
                  <p className="text-[10px] font-bold text-slate-400 uppercase">Calling Notes</p>
                  <p className="text-slate-600 mt-1 text-xs leading-relaxed italic">
                    "{selectedLog.notes || "No outbound caller summary generated."}"
                  </p>
                </div>

                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider sticky top-0 bg-transparent py-1">
                  Dialogue Transcript
                </p>

                {selectedLog.transcript && selectedLog.transcript.length > 0 ? (
                  selectedLog.transcript.map((msg, index) => (
                    <div
                      key={index}
                      className={`p-2.5 rounded-xl border ${
                        msg.role === "system"
                          ? "bg-slate-100/70 border-slate-200 text-slate-500 font-mono text-[10px] text-center"
                          : (msg.role === "model" || msg.role === "assistant")
                          ? "bg-sky-500 text-white border-sky-600 rounded-tl-sm"
                          : "bg-white text-slate-700 border-sky-50 rounded-tr-sm"
                      }`}
                    >
                      {msg.role !== "system" && (
                        <div className="font-bold text-[9px] uppercase tracking-wide opacity-80 mb-0.5">
                          {(msg.role === "model" || msg.role === "assistant") ? "SkyAgent" : "Customer"}
                        </div>
                      )}
                      <div className="leading-relaxed text-[11px]">{msg.text}</div>
                    </div>
                  ))
                ) : (
                  <p className="text-slate-400 italic text-center py-4">No transcription bubbles saved.</p>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-6 text-slate-400">
              <MessageSquare className="w-10 h-10 text-sky-200 mb-2" />
              <h5 className="font-semibold text-slate-600 text-xs">No Log Inspected</h5>
              <p className="text-[11px] text-slate-400 mt-1 max-w-xs leading-relaxed">
                Click on any call row in the list to inspect the full transcript, calling notes, and dialogue sentiment.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
