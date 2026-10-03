import { useState, useEffect } from "react";
import { X, Languages, PhoneIncoming, PhoneOutgoing, Loader2 } from "lucide-react";

interface Turn {
  role: "caller" | "agent";
  text: string;
  lang: string;
  time: string;
}

interface TranscriptData {
  found: boolean;
  phone?: string;
  direction?: string;
  start?: string;
  transcript: Turn[];
}

interface ConversationModalProps {
  callId: string;
  phone: string;
  direction: string;
  onClose: () => void;
}

export function ConversationModal({ callId, phone, direction, onClose }: ConversationModalProps) {
  const [data, setData] = useState<TranscriptData | null>(null);
  const [loading, setLoading] = useState(true);
  const [translated, setTranslated] = useState<Record<number, string>>({});
  const [translating, setTranslating] = useState(false);
  const [showTranslation, setShowTranslation] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/call-history/${encodeURIComponent(callId)}/transcript`)
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => setData({ found: false, transcript: [] }))
      .finally(() => setLoading(false));
  }, [callId]);

  const turns = data?.transcript || [];

  const translateAll = async () => {
    if (showTranslation) {
      setShowTranslation(false);
      return;
    }
    if (Object.keys(translated).length === turns.length) {
      setShowTranslation(true);
      return;
    }
    setTranslating(true);
    const results: Record<number, string> = { ...translated };
    await Promise.all(
      turns.map(async (t, i) => {
        if (results[i] !== undefined) return;
        try {
          const res = await fetch("/api/translate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: t.text, source_language_code: t.lang || "auto", target_language_code: "en-IN" }),
          });
          const j = await res.json();
          results[i] = j.translated || t.text;
        } catch {
          results[i] = t.text;
        }
      })
    );
    setTranslated(results);
    setTranslating(false);
    setShowTranslation(true);
  };

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[85vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center gap-3 p-4 border-b border-slate-200">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center ${direction === "incoming" ? "bg-indigo-50 text-indigo-600" : "bg-purple-50 text-purple-600"}`}>
            {direction === "incoming" ? <PhoneIncoming className="w-5 h-5" /> : <PhoneOutgoing className="w-5 h-5" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-bold text-slate-800 text-sm font-mono">{phone || "unknown"}</div>
            <div className="text-[10px] text-slate-500 font-semibold uppercase">
              {direction} {data?.start ? `• ${data.start}` : ""}
            </div>
          </div>
          <button
            onClick={translateAll}
            disabled={translating || turns.length === 0}
            className={`flex items-center gap-1.5 text-[11px] font-bold px-3 py-1.5 rounded-lg border transition ${
              showTranslation ? "bg-indigo-600 text-white border-indigo-600" : "bg-white text-indigo-600 border-indigo-200 hover:bg-indigo-50"
            } disabled:opacity-50`}
          >
            {translating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Languages className="w-3.5 h-3.5" />}
            {showTranslation ? "Original" : "Translate"}
          </button>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-slate-50/50">
          {loading ? (
            <div className="flex items-center justify-center py-10 text-slate-400 text-xs gap-2">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading conversation…
            </div>
          ) : turns.length === 0 ? (
            <p className="text-center text-slate-400 text-xs italic py-10">
              No conversation recorded for this call.
            </p>
          ) : (
            turns.map((t, i) => {
              const isAgent = t.role === "agent";
              return (
                <div key={i} className={`flex ${isAgent ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[78%] rounded-2xl px-3.5 py-2 ${isAgent ? "bg-indigo-600 text-white rounded-br-sm" : "bg-white border border-slate-200 text-slate-800 rounded-bl-sm"}`}>
                    <div className={`text-[9px] font-bold uppercase tracking-wide mb-0.5 ${isAgent ? "text-indigo-200" : "text-slate-400"}`}>
                      {isAgent ? "Interviewer (AI)" : "Candidate"}
                    </div>
                    <div className="text-[13px] leading-snug whitespace-pre-wrap">
                      {showTranslation && translated[i] !== undefined ? translated[i] : t.text}
                    </div>
                    {showTranslation && translated[i] !== undefined && translated[i] !== t.text && (
                      <div className={`text-[10px] mt-1 pt-1 border-t ${isAgent ? "border-indigo-400/40 text-indigo-200" : "border-slate-100 text-slate-400"}`}>
                        {t.text}
                      </div>
                    )}
                    <div className={`text-[9px] mt-1 ${isAgent ? "text-indigo-200/80" : "text-slate-400"}`}>
                      {t.time} • {t.lang}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
