import { useState, useEffect, type ReactNode } from "react";
import {
  Phone, PhoneIncoming, PhoneOutgoing, CalendarCheck,
  Flame, Clock, PhoneForwarded, ThermometerSun,
} from "lucide-react";

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

function fmtDur(sec: number) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m ${s}s`;
}

function Card({ icon, label, value, sub, accent }: { icon: ReactNode; label: string; value: string | number; sub?: string; accent: string }) {
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
  const [s, setS] = useState<Summary | null>(null);
  const [pendingCallbacks, setPendingCallbacks] = useState(0);

  useEffect(() => {
    const fetchData = () => {
      fetch("/api/report")
        .then((r) => r.json())
        .then((d) => d.summary && setS(d.summary))
        .catch(() => {});
      fetch("/api/callbacks")
        .then((r) => r.json())
        .then((d) => Array.isArray(d) && setPendingCallbacks(d.filter((c: any) => !c.done).length))
        .catch(() => {});
    };
    fetchData();
    const iv = setInterval(fetchData, 5000);
    return () => clearInterval(iv);
  }, []);

  const v = s || { total: 0, incoming: 0, outgoing: 0, hot: 0, warm: 0, cold: 0, incomplete: 0, demos_booked: 0, total_duration_sec: 0, avg_duration_sec: 0 };

  return (
    <div className="w-full lg:w-4/5 xl:w-[72%] mt-8 pr-4 md:pr-8">
      <h2 className="text-white font-bold text-sm mb-6 tracking-wide drop-shadow-md">Call Center Overview</h2>
      <div id="metrics-container" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-2">
        <Card icon={<Phone className="w-4 h-4 text-white" />} accent="bg-slate-700"
          label="Total Calls" value={v.total} sub="all AI conversations" />
        <Card icon={<PhoneIncoming className="w-4 h-4 text-white" />} accent="bg-indigo-500"
          label="Incoming Calls" value={v.incoming} sub="customers called in" />
        <Card icon={<PhoneOutgoing className="w-4 h-4 text-white" />} accent="bg-purple-500"
          label="Outgoing Calls" value={v.outgoing} sub="agent dialed out" />
        <Card icon={<CalendarCheck className="w-4 h-4 text-white" />} accent="bg-emerald-500"
          label="Demos Booked" value={v.demos_booked} sub="scheduled from calls" />
        <Card icon={<Flame className="w-4 h-4 text-white" />} accent="bg-rose-500"
          label="Hot Leads" value={v.hot} sub="very interested" />
        <Card icon={<ThermometerSun className="w-4 h-4 text-white" />} accent="bg-amber-500"
          label="Warm Leads" value={v.warm} sub="interested / callback" />
        <Card icon={<PhoneForwarded className="w-4 h-4 text-white" />} accent="bg-orange-500"
          label="Pending Callbacks" value={pendingCallbacks} sub="to call back later" />
        <Card icon={<Clock className="w-4 h-4 text-white" />} accent="bg-sky-500"
          label="Avg Call Duration" value={fmtDur(v.avg_duration_sec)} sub="per conversation" />
      </div>
    </div>
  );
};
