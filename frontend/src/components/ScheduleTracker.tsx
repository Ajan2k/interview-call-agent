import React, { useState } from "react";
import { Clock, CheckCircle2, PhoneCall, Play, Info, AlertCircle, Sparkles, Plus } from "lucide-react";
import { Contact } from "../types";
import { StratroomHeader, StratroomTable, StratroomThead, StratroomTh, StratroomTr, StratroomTd, StratroomActions, StratroomStatus } from "./sampleUI";
interface ScheduleTrackerProps {
  contacts: Contact[];
  autodialerActive: boolean;
  onToggleAutodialer: () => void;
  activeContact: Contact | null;
  onSingleCallScheduled?: (name: string, phone: string, time: string, notes: string) => void;
}

export const ScheduleTracker: React.FC<ScheduleTrackerProps> = ({
  contacts,
  autodialerActive,
  onToggleAutodialer,
  activeContact,
  onSingleCallScheduled,
}) => {
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [time, setTime] = useState("");
  const [notes, setNotes] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (onSingleCallScheduled && name && phone && time) {
      onSingleCallScheduled(name, phone, time, notes);
      setName("");
      setPhone("");
      setTime("");
      setNotes("");
      setIsFormOpen(false);
    }
  };

  // Filter contacts that requested a callback
  const scheduledContacts = contacts.filter((c) => c.status === "Scheduled" || c.outcome === "Scheduled Callback" || c.outcome?.includes("Schedule"));
  const completedCount = contacts.filter((c) => c.status === "Completed").length;
  


  // Calculate predicted calling schedules (each call averages ~3 minutes in active autodialer interval)
  const getPredictedTime = (index: number) => {
    if (index === 0) return "Next Up (Immediate)";
    const minutesAhead = index * 3;
    return `+${minutesAhead} mins approx`;
  };

  return (
    <div id="bulk-schedule-tracker" className="flex-1 flex flex-col min-h-[600px]">
      <StratroomHeader title="SCHEDULED CALLBACKS" icon={Clock}>
        <button
          onClick={() => setIsFormOpen(!isFormOpen)}
          className="flex items-center gap-1 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-[10px] font-bold px-3 py-1.5 rounded transition shadow-sm mr-2"
        >
          <Plus className="w-3 h-3 text-indigo-500" /> Add Manual
        </button>
        
        <button
          onClick={onToggleAutodialer}
          className={`flex items-center gap-1.5 text-[10px] font-bold px-3 py-1.5 rounded border transition shadow-sm ${
            autodialerActive
              ? "bg-amber-50 hover:bg-amber-100 text-amber-700 border-amber-200"
              : "bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border-indigo-200"
          }`}
        >
          {autodialerActive ? (
            <><Clock className="w-3 h-3 animate-spin" /> Active</>
          ) : (
            <><Play className="w-3 h-3" /> Start Scheduler</>
          )}
        </button>
      </StratroomHeader>

      {isFormOpen && (
        <form onSubmit={handleSubmit} className="bg-white p-4 border border-purple-100 shadow-sm rounded-xl mb-4 space-y-3 shrink-0">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <input type="text" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Customer Name" className="w-full px-3 py-2 bg-white border border-gray-200 rounded text-xs focus:outline-none focus:border-purple-300" />
            </div>
            <div>
              <input type="tel" required value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Phone Number (e.g. +91...)" className="w-full px-3 py-2 bg-white border border-gray-200 rounded text-xs focus:outline-none focus:border-purple-300" />
            </div>
            <div>
              <input type="datetime-local" required value={time} onChange={(e) => setTime(e.target.value)} className="w-full px-3 py-2 bg-white border border-gray-200 rounded text-xs focus:outline-none focus:border-purple-300" />
            </div>
          </div>
          <div className="flex gap-3">
            <input type="text" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes (Optional)" className="w-full px-3 py-2 bg-white border border-gray-200 rounded text-xs focus:outline-none focus:border-purple-300 flex-1" />
            <button type="submit" className="bg-[#8b3d6a] hover:bg-purple-900 text-white text-xs font-semibold px-4 py-1.5 rounded shadow-sm">
              Schedule Call
            </button>
          </div>
        </form>
      )}

      {/* Tanglish Explanation Notice Banner */}
      <div className="bg-sky-50/70 border border-sky-100 rounded-xl p-3 flex items-start gap-3 mb-4 shrink-0">
        <Sparkles className="w-4 h-4 text-sky-600 shrink-0 mt-0.5" />
        <div className="text-[11px] space-y-0.5">
          <p className="font-bold text-sky-800">
            How the Auto-Scheduler works:
          </p>
          <p className="text-sky-700/90 leading-relaxed">
            When a customer tells the AI <em>"call me back at 6 PM"</em>, their number is automatically extracted and queued here. 
            Click <strong>"Start Scheduler"</strong> to let the system automatically dial them!
          </p>
        </div>
      </div>

      <div className="flex-1">
        <StratroomTable>
          <StratroomThead>
            <StratroomTh>#</StratroomTh>
            <StratroomTh>Customer Details</StratroomTh>
            <StratroomTh>Phone Line</StratroomTh>
            <StratroomTh>Schedule Details</StratroomTh>
            <StratroomTh>Status</StratroomTh>
            <StratroomTh className="text-right">Actions</StratroomTh>
          </StratroomThead>
          <tbody className="divide-y divide-gray-100">
            {scheduledContacts.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-slate-500 text-[11px] font-medium bg-transparent">
                  No scheduled callbacks yet!
                </td>
              </tr>
            ) : (
              scheduledContacts.map((contact, idx) => {
                const isCalling = activeContact?.id === contact.id;
                return (
                  <StratroomTr 
                    key={contact.id} 
                    className={isCalling ? "bg-amber-50" : ""}
                  >
                    <StratroomTd>
                      <span className="font-mono text-slate-400 font-bold">{idx + 1}</span>
                    </StratroomTd>
                    <StratroomTd>
                      <div className="flex items-center gap-3">
                        <div className="w-7 h-7 rounded-full bg-slate-100 border border-slate-200 text-slate-500 flex items-center justify-center font-bold text-[10px] uppercase shadow-sm">
                          {contact.name.charAt(0)}
                        </div>
                        <div>
                          <div className="font-bold text-slate-800 text-xs">{contact.name}</div>
                          <div className="text-[9px] text-slate-500 font-semibold uppercase mt-0.5">ID: {contact.id.substring(0, 4)}</div>
                        </div>
                      </div>
                    </StratroomTd>
                    <StratroomTd>
                      <span className="font-mono font-medium text-slate-600">{contact.phone}</span>
                    </StratroomTd>
                    <StratroomTd>
                      {contact.status === "Scheduled" && contact.scheduledTime ? (
                        <span className="font-mono text-purple-600 text-[11px] font-semibold">
                          {new Date(contact.scheduledTime).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                        </span>
                      ) : (
                        <span className="text-slate-500 italic text-[11px]">
                          {autodialerActive ? getPredictedTime(idx) : "Waiting in queue"}
                        </span>
                      )}
                    </StratroomTd>
                    <StratroomTd>
                      {isCalling ? (
                        <div className="flex items-center gap-1.5 text-[11px] font-bold text-amber-600">
                          <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
                          Dialing Now
                        </div>
                      ) : (
                        <StratroomStatus status={contact.status} />
                      )}
                    </StratroomTd>
                    <StratroomTd>
                      <StratroomActions 
                        onCall={() => {}}
                        onDelete={() => {}}
                      />
                    </StratroomTd>
                  </StratroomTr>
                );
              })
            )}
          </tbody>
        </StratroomTable>
      </div>
    </div>
  );
};
