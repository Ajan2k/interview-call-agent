import React from 'react';
import { PhoneCall, Trash2 } from 'lucide-react';

export const StratroomHeader = ({ title, icon: Icon, children }: any) => {
  return (
    <div className="bg-transparent overflow-hidden relative border-b border-gray-200 pb-2">
      {/* Background Banner Image - Top Right */}
      <div
        className="absolute top-0 right-0 w-1/2 md:w-2/3 h-full bg-no-repeat bg-right bg-cover opacity-90 pointer-events-none"
        style={{
          backgroundImage: "url('https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?auto=format&fit=crop&q=80')",
          maskImage: 'linear-gradient(to right, transparent, black 50%)',
          WebkitMaskImage: 'linear-gradient(to right, transparent, black 50%)'
        }}
      ></div>

      <div className="p-5 relative z-10 flex flex-col sm:flex-row justify-between items-start min-h-[120px]">
        <div className="mt-auto">
          <div className="w-10 h-10 rounded-full bg-emerald-600 text-white flex items-center justify-center mb-3 shadow-md">
            <Icon className="w-5 h-5" />
          </div>
          <h2 className="text-[14px] font-black text-slate-900 tracking-wider uppercase">{title}</h2>
        </div>

        <div className="mt-4 sm:mt-0 flex items-center gap-2 sm:absolute sm:bottom-5 sm:right-5">
          {children}
        </div>
      </div>
    </div>
  );
};

export const StratroomTable = ({ children }: { children: React.ReactNode }) => (
  <div className="bg-transparent overflow-x-auto mb-8">
    <table className="w-full text-left border-collapse">
      {children}
    </table>
  </div>
);

export const StratroomThead = ({ children }: { children: React.ReactNode }) => (
  <thead>
    <tr className="bg-[#dcfce7] border-y border-emerald-200">
      <th className="py-3 px-4 w-12 text-center">
        <input type="checkbox" className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-600 w-3 h-3" />
      </th>
      {children}
    </tr>
  </thead>
);

export const StratroomTh = ({ children, className = "" }: any) => (
  <th className={`py-3 px-4 text-[10px] font-bold text-slate-800 uppercase tracking-widest ${className}`}>
    {children}
  </th>
);

export const StratroomTr = ({ children, className = "" }: any) => (
  <tr className={`border-b border-gray-200 hover:bg-slate-50 transition-colors ${className}`}>
    <td className="py-4 px-4 text-center align-middle">
      <input type="checkbox" className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-600 w-3 h-3" />
    </td>
    {children}
  </tr>
);

export const StratroomTd = ({ children, className = "" }: any) => (
  <td className={`py-4 px-4 text-[11px] align-middle text-slate-700 ${className}`}>
    {children}
  </td>
);

export const StratroomActions = ({ onCall, onDelete }: any) => (
  <div className="flex items-center justify-end gap-1.5">
    <button onClick={onCall} className="p-1.5 text-slate-400 hover:text-emerald-600 bg-white border border-slate-200 rounded-md hover:bg-emerald-50 transition" title="Call">
      <PhoneCall className="w-3.5 h-3.5" />
    </button>
    <button onClick={onDelete} className="p-1.5 text-slate-400 hover:text-rose-600 bg-white border border-slate-200 rounded-md hover:bg-rose-50 transition" title="Delete">
      <Trash2 className="w-3.5 h-3.5" />
    </button>
  </div>
);

export const StratroomStatus = ({ status }: { status: string }) => {
  let colorClass = "bg-slate-400";
  let textClass = "text-slate-500";

  const s = status.toLowerCase();
  if (s.includes("complete") || s.includes("active") || s.includes("success")) {
    colorClass = "bg-emerald-500";
    textClass = "text-emerald-600";
  } else if (s.includes("progress") || s.includes("run") || s.includes("call") || s.includes("ring")) {
    colorClass = "bg-amber-500";
    textClass = "text-amber-600";
  } else if (s.includes("fail") || s.includes("error") || s.includes("reject")) {
    colorClass = "bg-rose-500";
    textClass = "text-rose-600";
  } else if (s.includes("schedule")) {
    colorClass = "bg-purple-500";
    textClass = "text-purple-600";
  }

  return (
    <div className={`flex items-center gap-1.5 text-[11px] font-bold ${textClass}`}>
      <span className={`w-2 h-2 rounded-full ${colorClass}`}></span>
      {status}
    </div>
  );
};
