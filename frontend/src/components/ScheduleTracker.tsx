import React, { useState, useEffect, useCallback } from "react";
import {
  Clock, PhoneCall, Plus, Sparkles, CheckCircle2, Trash2,
  PhoneIncoming, PhoneOutgoing, RotateCcw,
} from "lucide-react";
import { StratroomHeader } from "./ui";

interface Callback {
  id: number;
  time: string;
  call_id: string;
  direction: string;
  phone?: string;
  language: string;
  callback_time: string;
  done: boolean;
}

interface ScheduleTrackerProps {
  activeContact: { id: string; phone: string } | null;
  onDialNumber?: (phone: string, label: string) => void;
}

export const ScheduleTracker: React.FC<ScheduleTrackerProps> = ({ activeContact, onDialNumber }) => {
  const [callbacks, setCallbacks] = useState<Callback[]>([]);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [phone, setPhone] = useState("+91 ");
  const [when, setWhen] = useState("");

  const fetchCallbacks = useCallback(() => {
    fetch("/api/callbacks")
      .then((r) => r.json())
      .then((d) => Array.isArray(d) && setCallbacks(d))
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetchCallbacks();
    const iv = setInterval(fetchCallbacks, 5000);
    return () => clearInterval(iv);
  }, [fetchCallbacks]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!phone.trim() || !when.trim()) return;
    await fetch("/api/callbacks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone: phone.trim(), callback_time: when.trim() }),
    }).catch(() => {});
    setPhone("+91 ");
    setWhen("");
    setIsFormOpen(false);
    fetchCallbacks();
  };

  const markDone = async (id: number, done: boolean) => {
    await fetch(`/api/callbacks/${id}/done`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ done }),
    }).catch(() => {});
    fetchCallbacks();
  };

  const remove = async (id: number) => {
    await fetch(`/api/callbacks/${id}`, { method: "DELETE" }).catch(() => {});
    fetchCallbacks();
  };

  const pending = callbacks.filter((c) => !c.done);
  const done = callbacks.filter((c) => c.done);

  return (
    <div id="callback-scheduler" className="flex-1 flex flex-col min-h-[600px]">
      <StratroomHeader title="CALLBACK SCHEDULER" icon={Clock}>
        <button
          onClick={() => setIsFormOpen(!isFormOpen)}
          className="flex items-center gap-1 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-[10px] font-bold px-3 py-1.5 rounded transition shadow-sm mr-2"
        >
          <Plus className="w-3 h-3 text-indigo-500" /> Add Manual
        </button>
        <span className="flex items-center gap-1.5 text-[10px] font-bold px-3 py-1.5 rounded border bg-amber-50 text-amber-700 border-amber-200">
          {pending.length} pending
        </span>
      </StratroomHeader>

      {isFormOpen && (
        <form onSubmit={handleSubmit} className="bg-white p-4 border border-purple-100 shadow-sm rounded-xl mb-4 space-y-3 shrink-0">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input type="tel" required value={phone} onChange={(e) => setPhone(e.target.value)}
              placeholder="Phone Number (e.g. +91...)"
              className="w-full px-3 py-2 bg-white border border-gray-200 rounded text-xs focus:outline-none focus:border-purple-300" />
            <input type="text" required value={when} onChange={(e) => setWhen(e.target.value)}
              placeholder="Callback time (e.g. Tomorrow 11 AM)"
              className="w-full px-3 py-2 bg-white border border-gray-200 rounded text-xs focus:outline-none focus:border-purple-300" />
          </div>
          <div className="flex justify-end">
            <button type="submit" className="bg-[#8b3d6a] hover:bg-purple-900 text-white text-xs font-semibold px-4 py-1.5 rounded shadow-sm">
              Add Callback
            </button>
          </div>
        </form>
      )}

      {/* Explanation banner */}
      <div className="bg-sky-50/70 border border-sky-100 rounded-xl p-3 flex items-start gap-3 mb-4 shrink-0">
        <Sparkles className="w-4 h-4 text-sky-600 shrink-0 mt-0.5" />
        <div className="text-[11px] space-y-0.5">
          <p className="font-bold text-sky-800">How callbacks work:</p>
          <p className="text-sky-700/90 leading-relaxed">
            When a customer tells the AI <em>"I'm busy, call me back at 6 PM"</em>, their number and time land here automatically.
            Click <strong>Call Now</strong> to dial them, then <strong>Mark Done</strong> once handled.
          </p>
        </div>
      </div>

      {/* PENDING CALLBACKS */}
      <div className="flex-1 space-y-3">
        {pending.length === 0 ? (
          <div className="py-10 text-center text-slate-400 text-[11px] italic bg-white rounded-xl border border-slate-100">
            No pending callbacks. Busy customers who ask for a callback appear here.
          </div>
        ) : (
          pending.map((cb) => {
            const isCalling = activeContact?.phone === cb.phone;
            return (
              <div key={cb.id} className={`flex items-center gap-3 bg-white rounded-xl border p-4 shadow-sm ${isCalling ? "border-amber-300 bg-amber-50/50" : "border-slate-200"}`}>
                <div className="w-10 h-10 rounded-full bg-amber-50 border border-amber-200 text-amber-600 flex items-center justify-center shrink-0">
                  <Clock className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-slate-800 text-sm">{cb.callback_time || "No time given"}</div>
                  <div className="flex items-center gap-2 mt-1 text-[10px] text-slate-500 font-semibold flex-wrap">
                    {cb.direction === "incoming" ? (
                      <span className="flex items-center gap-1 text-indigo-600"><PhoneIncoming className="w-3 h-3" /> Incoming</span>
                    ) : (
                      <span className="flex items-center gap-1 text-purple-600"><PhoneOutgoing className="w-3 h-3" /> Outgoing</span>
                    )}
                    <span className="font-mono text-slate-700">{cb.phone || "unknown"}</span>
                    {cb.language && <><span>•</span><span>{cb.language}</span></>}
                    <span>•</span><span>requested {cb.time}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {isCalling ? (
                    <span className="flex items-center gap-1.5 text-[11px] font-bold text-amber-600 px-3">
                      <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span> Dialing…
                    </span>
                  ) : (
                    <button
                      onClick={() => cb.phone && onDialNumber?.(cb.phone, cb.callback_time)}
                      disabled={!cb.phone || !!activeContact}
                      className="flex items-center gap-1 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-100 disabled:text-slate-400 text-white text-[11px] font-bold px-3 py-1.5 rounded-lg transition"
                    >
                      <PhoneCall className="w-3.5 h-3.5" /> Call Now
                    </button>
                  )}
                  <button onClick={() => markDone(cb.id, true)} title="Mark done"
                    className="flex items-center gap-1 bg-slate-100 hover:bg-emerald-50 text-slate-600 hover:text-emerald-700 text-[11px] font-bold px-2.5 py-1.5 rounded-lg transition">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => remove(cb.id)} title="Delete"
                    className="flex items-center bg-slate-100 hover:bg-rose-50 text-slate-500 hover:text-rose-600 px-2.5 py-1.5 rounded-lg transition">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })
        )}

        {/* DONE CALLBACKS */}
        {done.length > 0 && (
          <div className="pt-2">
            <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-wider mb-2 px-1">Completed ({done.length})</h4>
            {done.map((cb) => (
              <div key={cb.id} className="flex items-center gap-3 bg-slate-50/60 rounded-xl border border-slate-100 p-3 mb-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <span className="text-xs font-semibold text-slate-500 line-through">{cb.callback_time}</span>
                  <span className="ml-2 text-[10px] font-mono text-slate-400">{cb.phone}</span>
                </div>
                <button onClick={() => markDone(cb.id, false)} title="Reopen"
                  className="flex items-center bg-white hover:bg-slate-100 text-slate-400 px-2 py-1 rounded transition">
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
                <button onClick={() => remove(cb.id)} title="Delete"
                  className="flex items-center bg-white hover:bg-rose-50 text-slate-400 hover:text-rose-600 px-2 py-1 rounded transition">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
