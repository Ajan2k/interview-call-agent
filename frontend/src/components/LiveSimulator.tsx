import React, { useState, useEffect, useRef } from "react";
import { Phone, PhoneOff, Sparkles, PhoneIncoming, Activity } from "lucide-react";
import { Contact, CallLog } from "../types";

interface LiveSimulatorProps {
  activeContact: Contact | null;
  onCallEnded: (contactId: string, finalStatus: "Completed" | "Failed" | "Voicemail", log: CallLog) => void;
  campaignName: string;
}

export const LiveSimulator: React.FC<LiveSimulatorProps> = ({
  activeContact,
  onCallEnded,
  campaignName,
}) => {
  const [callState, setCallState] = useState<"idle" | "dialing" | "ringing" | "connected" | "ended">("idle");
  const [callDuration, setCallDuration] = useState(0);

  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // Handle Call Lifecycle Transitions
  useEffect(() => {
    if (!activeContact) {
      setCallState("idle");
      setCallDuration(0);
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }

    const isIncoming = (activeContact as any).isIncoming;

    if (isIncoming) {
      // INCOMING CALL FLOW
      setCallState("ringing");
      setCallDuration(0);

      // Wait 2.5 seconds, then answer
      const answerTimeout = setTimeout(() => {
        setCallState("connected");
        // Start call stopwatch
        timerRef.current = setInterval(() => {
          setCallDuration((d) => d + 1);
        }, 1000);
      }, 2500);

      return () => {
        clearTimeout(answerTimeout);
        if (timerRef.current) clearInterval(timerRef.current);
      };
    } else {
      // OUTBOUND CALL FLOW
      setCallState("dialing");
      setCallDuration(0);

      // Dialing for 1.5s
      const dialTimeout = setTimeout(() => {
        setCallState("ringing");

        // Ringing for 2s, then answer
        const answerTimeout = setTimeout(() => {
          setCallState("connected");
          // Start call stopwatch
          timerRef.current = setInterval(() => {
            setCallDuration((d) => d + 1);
          }, 1000);
        }, 2000);

        return () => clearTimeout(answerTimeout);
      }, 1500);

      return () => {
        clearTimeout(dialTimeout);
        if (timerRef.current) clearInterval(timerRef.current);
      };
    }
  }, [activeContact]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  // Hang up action (Manual override if needed)
  const handleHangUp = () => {
    if (!activeContact) return;

    if (timerRef.current) clearInterval(timerRef.current);
    setCallState("ended");

    // In a real scenario, this log might be incomplete if we abort manually.
    // Usually, the backend provides the actual final log via polling.
    const finalLog: CallLog = {
      id: `log-sim-${Date.now()}`,
      contactName: activeContact.name,
      phone: activeContact.phone,
      campaignName: campaignName,
      duration: callDuration,
      outcome: "No Answer" as any, // Default if manually aborted before backend responds
      sentiment: "Neutral",
      time: new Date().toISOString(),
      transcript: [],
      notes: `Call manually terminated from dashboard at ${callDuration}s.`,
    };

    onCallEnded(activeContact.id, "Completed", finalLog);
  };

  const formatTimer = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = sec % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <div id="live-simulator-panel" className="bg-transparent p-6 pt-2 overflow-hidden flex flex-col h-[640px]">
      {/* Panel Title */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-100 shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 bg-sky-500 rounded-full animate-ping" />
          <h3 className="font-bold text-slate-800 text-sm tracking-wide uppercase">Live Call Monitor</h3>
        </div>
        <div className="flex items-center gap-1.5 bg-sky-50 px-2.5 py-1 rounded-lg text-sky-600 font-mono text-xs font-semibold">
          {activeContact?.isIncoming ? (
            <>
              <PhoneIncoming className="w-3.5 h-3.5 text-sky-500 animate-pulse" /> Inbound Call Port
            </>
          ) : (
            <>
              <Phone className="w-3.5 h-3.5" /> Outbound Call Port
            </>
          )}
        </div>
      </div>

      {callState === "idle" ? (
        /* IDLE SCREEN */
        <div id="simulator-idle-view" className="flex-1 flex flex-col items-center justify-center text-center p-8">
          <div className="relative mb-6">
            <div className="w-20 h-20 bg-sky-50 rounded-full flex items-center justify-center text-sky-400">
              <Phone className="w-10 h-10" />
            </div>
            <div className="absolute -bottom-1 -right-1 w-6 h-6 bg-white rounded-full border border-sky-100 flex items-center justify-center text-sky-500 shadow-sm">
              <Sparkles className="w-3.5 h-3.5 animate-pulse" />
            </div>
          </div>
          <h4 className="font-bold text-slate-700 text-base">Dashboard Line Standby</h4>
          <p className="text-xs text-slate-400 max-w-xs mt-1 leading-relaxed">
            Select a customer from the queue below and click <strong>"Dial Customer"</strong> or start the <strong>"Auto-Dialer Campaign"</strong> to connect SkyAgent.
          </p>
        </div>
      ) : (
        /* CALL ACTIVE SCREEN */
        <div id="simulator-active-view" className="flex-1 flex flex-col overflow-hidden pt-4">
          {/* Active Contact Bar */}
          <div className="bg-slate-50 border border-slate-100 rounded-2xl p-4 shrink-0 flex items-center justify-between mb-4">
            <div>
              <p className="text-[10px] uppercase font-bold tracking-widest text-slate-400">
                {activeContact?.isIncoming ? "⚡ Active Inbound Call" : "Active Outbound Call"}
              </p>
              <h4 className="font-bold text-slate-800 text-sm mt-0.5">{activeContact?.name}</h4>
              <span className="text-xs text-slate-500 font-mono">{activeContact?.phone}</span>
            </div>
            <div className="text-right">
              <div className="text-xs font-mono font-bold text-sky-600 bg-sky-100/60 px-2.5 py-1 rounded-lg inline-block">
                {callState === "dialing" && "DIALING..."}
                {callState === "ringing" && "RINGING..."}
                {callState === "connected" && formatTimer(callDuration)}
                {callState === "ended" && "ENDED"}
              </div>
            </div>
          </div>

          {/* Pulse Monitor */}
          {callState !== "ended" && (
            <div className="flex-1 flex flex-col items-center justify-center py-4 bg-sky-50/20 border border-sky-100/50 rounded-2xl mb-4">
              <div className="relative flex items-center justify-center mb-6">
                <div className="absolute w-32 h-32 bg-sky-400/20 rounded-full animate-ping" />
                <div className="absolute w-24 h-24 bg-sky-400/30 rounded-full animate-pulse" />
                <div className="w-16 h-16 rounded-full bg-sky-500 flex items-center justify-center text-white shadow-md z-10">
                  <Activity className="w-8 h-8 animate-pulse" />
                </div>
              </div>
              <h4 className="text-lg font-bold text-slate-700">Real Phone Call In Progress</h4>
              <span className="text-xs text-slate-400 font-semibold tracking-wider uppercase mt-2 max-w-xs text-center">
                Waiting for Twilio backend to hang up and generate call summary...
              </span>
            </div>
          )}

          {/* Hangup Red button */}
          <div className="shrink-0 flex items-center justify-center py-4 px-1 mt-auto">
            <button
              id="btn-hangup"
              onClick={handleHangUp}
              className="flex items-center justify-center gap-2 w-full max-w-xs bg-rose-500 hover:bg-rose-600 text-white font-semibold text-sm px-6 py-3 rounded-xl shadow-sm shadow-rose-100 transition"
            >
              <PhoneOff className="w-5 h-5" /> Force End Call
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
