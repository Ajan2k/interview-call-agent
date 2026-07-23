import React from "react";
import { Target } from "lucide-react";

interface MetricsProps {
  totalCalls: number;
  activeCampaigns: number;
  successRate: number;
  avgDuration: number; // in seconds
  dialedToday: number;
  incomingCallsCount: number;
}

export const Metrics: React.FC<MetricsProps> = ({
  totalCalls,
  activeCampaigns,
  successRate,
  avgDuration,
  dialedToday,
  incomingCallsCount,
}) => {
  const formatDuration = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const secs = sec % 60;
    return `${mins}m ${secs}s`;
  };

  // Reusable card component mimicking the requested UI
  const PriorityCard = ({ title, actual, target, actualColor = "text-yellow-500", showLine = true }: any) => (
    <div className="bg-white rounded-lg p-4 flex flex-col justify-between shadow-sm border border-gray-200 h-[120px] hover:shadow-md transition-shadow">
      <div>
        <div className="flex items-center justify-between mb-2">
           <Target className="w-3.5 h-3.5 text-gray-500" strokeWidth={2.5} />
        </div>
        <h3 className="text-xs font-bold text-slate-800 leading-snug">{title}</h3>
      </div>
      <div className="flex justify-between items-end mt-auto">
        <div className="flex gap-5">
          <div>
            <p className="text-[10px] text-gray-500 mb-0.5">Actual</p>
            <p className={`text-xs font-bold ${actualColor}`}>{actual}</p>
          </div>
          {target && (
            <div>
              <p className="text-[10px] text-gray-500 mb-0.5">Target</p>
              <p className="text-xs font-bold text-slate-700">{target}</p>
            </div>
          )}
        </div>
        {showLine && (
          <div className="w-3 h-[2px] bg-gray-400 rounded-full mb-1"></div>
        )}
      </div>
    </div>
  );

  return (
    <div className="w-full lg:w-4/5 xl:w-[70%] mt-8 pr-4 md:pr-8">
      <h2 className="text-white font-bold text-sm mb-6 tracking-wide drop-shadow-md">My Priorities</h2>
      <div id="metrics-container" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-2">
        
        <PriorityCard 
          title="Calls Dialed Today (Outbound)" 
          actual={dialedToday} 
          target="150" 
          actualColor="text-yellow-500"
        />
        
        <PriorityCard 
          title="Success Rate (Benchmark %)" 
          actual={`${successRate.toFixed(1)}%`} 
          target="75.0%" 
          actualColor="text-emerald-600"
        />
        
        <PriorityCard 
          title="Avg Call Duration (minutes)" 
          actual={formatDuration(avgDuration)} 
          target="1m 30s" 
          actualColor="text-yellow-500"
        />
        
        <PriorityCard 
          title="Active Campaigns (running)" 
          actual={activeCampaigns} 
          target="5" 
          actualColor="text-red-500"
        />
        
        <PriorityCard 
          title="Incoming Calls Answered" 
          actual={incomingCallsCount} 
          target="50" 
          actualColor="text-emerald-600"
        />
        
        <PriorityCard 
          title="Total Contacts Synced" 
          actual={totalCalls} 
          target={Math.max(200, totalCalls + 50)} 
          actualColor="text-yellow-500"
        />
        
        <PriorityCard 
          title="Agent Utilization Rate %" 
          actual="85.4%" 
          target="90.0%" 
          actualColor="text-emerald-600"
        />
        
        <PriorityCard 
          title="System Uptime %" 
          actual="99.9%" 
          target="99.9%" 
          actualColor="text-emerald-600"
        />
        
      </div>
    </div>
  );
};
