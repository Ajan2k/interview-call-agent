import React, { useState, useEffect, useRef, ChangeEvent, FormEvent } from "react";
import {
  Phone, PhoneCall, Plus, Trash2, Play, Pause, Search,
  Sparkles, Database, ShieldAlert, CheckCircle, RefreshCw,
  LayoutDashboard, FileAudio, BarChart3, Settings, HelpCircle,
  Clock, Activity, Sparkle, PhoneIncoming, FileSpreadsheet, Upload
} from "lucide-react";
import { Metrics } from "./components/Metrics";
import { CallLogs } from "./components/CallLogs";
import { ScheduleTracker } from "./components/ScheduleTracker";
import { CallHistory } from "./components/CallHistory";
import { Reports } from "./components/Reports";
import { Contact, Campaign, CallLog } from "./types";
import { TeleforceAgent } from "./components/TeleforceAgent";
import { StratroomHeader, StratroomTable, StratroomThead, StratroomTh, StratroomTr, StratroomTd, StratroomActions, StratroomStatus } from "./components/ui";
import { parseExcelOrCsv, ParsedContact } from "./utils/excelParser";

export default function App() {
  // Application Data States
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [logs, setLogs] = useState<CallLog[]>([]);

  // Calculate incoming calls from real DB data
  const incomingCallsCount = contacts.filter((c) => c.isIncoming || c.is_incoming).length;

  // Dashboard Interactions
  const [activeContact, setActiveContact] = useState<Contact | null>(null);
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null);
  const [autodialerActive, setAutodialerActive] = useState(false);
  const [contactSearch, setContactSearch] = useState("");
  const [activeTab, setActiveTab] = useState<"contacts" | "campaigns">("contacts");

  // Sidebar navigation tabs based on the High Density design layout
  const [sidebarTab, setSidebarTab] = useState<"dashboard" | "dialer" | "scheduler" | "calls" | "reports" | "logs" | "voice">("dashboard");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      try {
        const parsed = await parseExcelOrCsv(e.target.files[0]);
        if (parsed.length === 0) {
          alert("No valid phone numbers found in the uploaded file.");
          return;
        }
        handleContactsUploaded(parsed, "Imported Excel/CSV Contacts");
      } catch (err: any) {
        alert("Could not parse file. Please upload a valid .xlsx, .xls, or .csv sheet.");
      }
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Form states for adding manual contact
  const [isAddContactOpen, setIsAddContactOpen] = useState(false);
  const [newContactName, setNewContactName] = useState("");
  const [newContactPhone, setNewContactPhone] = useState("+91 ");
  const [newContactNotes, setNewContactNotes] = useState("");

  // Server health state
  const [serverHealth, setServerHealth] = useState<{ status: string; hasApiKey: boolean } | null>(null);

  // Voice Config States
  const [speechMode, setSpeechMode] = useState("Natural Female Voice (Azure Neerja / Pallavi)");
  const [languageFocus, setLanguageFocus] = useState("Automatic API");
  const [promptTemplate, setPromptTemplate] = useState(`You are Daffy, a warm, confident AI Sales Consultant calling from Daffytel Technologies.
Daffytel sells: Cloud Telephony, IVR, Smart Call Routing, Call Recording, CRM, WhatsApp Business API, AI Calling, Auto Dialer, Bulk SMS.

YOUR PERSONALITY:
- Warm, conversational, never robotic
- Use natural acknowledgments: 'Oh got it!', 'Right, right', 'That makes sense'
- Ask ONE short question at a time
- Reply in MAX 1-2 sentences. Speak naturally!`);
  const [isSavingVoice, setIsSavingVoice] = useState(false);

  const handleSaveVoiceConfig = async () => {
    setIsSavingVoice(true);
    try {
      await fetch("/api/voice-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          speechMode,
          languageFocus,
          promptTemplate
        })
      });
      alert("AI Agent configuration saved successfully!");
    } catch (e: any) {
      console.error(e);
      alert("Failed to save configuration: " + e.message);
    } finally {
      setIsSavingVoice(false);
    }
  };

  // Fetch Data on Load & Setup Polling
  useEffect(() => {
    const fetchData = () => {
      fetch("/api/health")
        .then((res) => res.json())
        .then((data) => setServerHealth(data))
        .catch(() => setServerHealth(null));

      fetch("/api/voice-config")
        .then((res) => res.json())
        .then((data) => {
          if (data.speechMode) setSpeechMode(data.speechMode);
          if (data.languageFocus) setLanguageFocus(data.languageFocus);
          if (data.promptTemplate) setPromptTemplate(data.promptTemplate);
        })
        .catch(err => console.error(err));

      fetch("/api/campaigns")
        .then((res) => res.json())
        .then((data) => {
          if (Array.isArray(data)) {
            setCampaigns(data);
            if (data.length > 0 && !selectedCampaign) {
              setSelectedCampaign(data[0]);
            }
          }
        })
        .catch(err => console.error(err));

      fetch("/api/contacts")
        .then((res) => res.json())
        .then((data) => {
          if (Array.isArray(data)) setContacts(data);
        })
        .catch(err => console.error(err));

      fetch("/api/logs")
        .then((res) => res.json())
        .then((data) => {
          if (Array.isArray(data)) setLogs(data);
        })
        .catch(err => console.error(err));
    };

    fetchData(); // initial fetch

    // Poll every 5 seconds to get real-time updates from Twilio/Gemini backend
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [selectedCampaign]);

  // AUTOMATIC AUTODIALER QUEUE CHAIN
  useEffect(() => {
    if (autodialerActive && !activeContact) {
      const nextPending = contacts.find((c) => c.status === "Pending");
      if (nextPending) {
        // Wait 3.5 seconds before placing the next call (feels natural, cool break time)
        const timer = setTimeout(async () => {
          setActiveContact(nextPending);
          setContacts((prev) =>
            prev.map((c) =>
              c.id === nextPending.id ? { ...c, status: "Calling" } : c
            )
          );
          try {
            await fetch(`/api/contacts/${nextPending.id}`, {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ status: "Calling" }),
            });
            // The TeleforceAgent will pick up the activeContact and dial it automatically.
          } catch (e) { console.error(e); }
        }, 3500);
        return () => clearTimeout(timer);
      } else {
        // No more pending calls
        setAutodialerActive(false);
        alert("Campaign Completed! All contacts in the queue have been successfully dialed by SkyAgent.");
      }
    }
  }, [autodialerActive, activeContact, contacts]);

  // Sync LiveSimulator with Backend real calls
  useEffect(() => {
    if (activeContact && !activeContact.isIncoming) {
      // Find the active contact in the updated contacts list
      const updatedContact = contacts.find(c => c.id === activeContact.id);
      if (updatedContact && updatedContact.status === "Completed") {
        // The backend marked it completed, we should close the simulator automatically
        const logData: CallLog = {
          id: `log-backend-${Date.now()}`,
          contactName: updatedContact.name,
          phone: updatedContact.phone,
          campaignName: selectedCampaign?.name || "Campaign",
          duration: updatedContact.duration || 0,
          outcome: updatedContact.outcome as any || "No Answer",
          sentiment: "Neutral", // The backend voice.py sets this in its own logs, but we can default it for the UI
          time: updatedContact.callTime || new Date().toISOString(),
          transcript: [],
          notes: updatedContact.notes || "",
        };
        // End it from the UI side without pushing duplicate data since backend already saved it
        // We only need to clear the activeContact and update UI
        setActiveContact(null);

        // Let's refetch logs to ensure we have the actual log created by backend
        fetch("/api/logs")
          .then((res) => res.json())
          .then((data) => setLogs(data))
          .catch(err => console.error(err));
      }
    }
  }, [contacts, activeContact, selectedCampaign]);


  // Dial an arbitrary number (used by the Callback Scheduler's "Call Now").
  // Creates a transient contact so TeleforceAgent's auto-dial picks it up.
  const handleDialNumber = (phone: string, label: string) => {
    if (activeContact) {
      alert("A call is already active. Please end it before dialing a callback.");
      return;
    }
    setActiveContact({
      id: `callback-${Date.now()}`,
      name: label || "Callback",
      phone,
      status: "Calling",
    });
  };

  // Handlers
  const handleDialContact = async (contact: Contact) => {
    setActiveContact(contact);
    setContacts((prev) =>
      prev.map((c) => (c.id === contact.id ? { ...c, status: "Calling" } : c))
    );
    try {
      await fetch(`/api/contacts/${contact.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "Calling" }),
      });
      // Trigger Real Telephone Call via Twilio (Disabled for Teleforce)
      // await fetch(`/api/voice/outbound/${contact.id}?phone=${encodeURIComponent(contact.phone)}`, {
      //   method: "POST"
      // });
    } catch (e) { console.error(e); }
  };

  const handleContactsUploaded = async (parsedContacts: ParsedContact[], campaignName: string) => {
    const newCampaign: Campaign = {
      id: `camp-${Date.now()}`,
      name: campaignName,
      type: "sales",
      status: "Running",
      totalContacts: parsedContacts.length,
      completedContacts: 0,
      successRate: 0,
      createdAt: new Date().toISOString(),
    };
    setCampaigns((prev) => [newCampaign, ...prev]);
    setSelectedCampaign(newCampaign);

    try {
      await fetch("/api/campaigns", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newCampaign),
      });

      const newContactsList: Contact[] = parsedContacts.map((pc, idx) => ({
        id: `c-upload-${Date.now()}-${idx}`,
        name: pc.name || "Unknown Lead",
        phone: pc.phone || "",
        email: pc.email,
        status: "Pending",
        notes: pc.notes || "Uploaded from bulk Excel spreadsheet.",
        campaignId: newCampaign.id
      }));

      // Immediately show in UI
      setContacts((prev) => [...newContactsList, ...prev]);

      // Fire all posts in parallel for speed
      await Promise.all(
        newContactsList.map(c =>
          fetch("/api/contacts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(c),
          })
        )
      );

      // Force a refetch to ensure we are perfectly in sync with DB
      const res = await fetch("/api/contacts");
      const data = await res.json();
      setContacts(data);

    } catch (e: any) {
      console.error(e);
      alert("Error saving contacts: " + e.message);
    }
  };

  const handleAddContactSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!newContactName || !newContactPhone) return;
    const manualContact: Contact = {
      id: `c-manual-${Date.now()}`,
      name: newContactName,
      phone: newContactPhone,
      status: "Pending",
      notes: newContactNotes || "Manually added to dialing pool.",
      campaignId: selectedCampaign?.id || undefined
    };

    // Optimistic UI update
    setContacts((prev) => [manualContact, ...prev]);
    setNewContactName("");
    setNewContactPhone("");
    setNewContactNotes("");
    setIsAddContactOpen(false);

    try {
      await fetch("/api/contacts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(manualContact),
      });

      // Refetch to sync with DB
      const res = await fetch("/api/contacts");
      const data = await res.json();
      setContacts(data);
    } catch (e: any) {
      console.error(e);
      alert("Error adding manual contact: " + e.message);
    }
  };

  const handleDeleteContact = async (contactId: string) => {
    setContacts((prev) => prev.filter((c) => c.id !== contactId));
    if (activeContact?.id === contactId) setActiveContact(null);
    try {
      await fetch(`/api/contacts/${contactId}`, { method: "DELETE" });
    } catch (e) { console.error(e); }
  };

  const handleDeleteLog = async (logId: string) => {
    setLogs((prev) => prev.filter((l) => l.id !== logId));
    try {
      await fetch(`/api/logs/${logId}`, { method: "DELETE" });
    } catch (e) { console.error(e); }
  };

  const handleClearAllLogs = async () => {
    setLogs([]);
    try {
      await fetch("/api/logs", { method: "DELETE" });
    } catch (e) { console.error(e); }
  };

  const filteredContacts = contacts.filter(
    (c) =>
      c.name.toLowerCase().includes(contactSearch.toLowerCase()) ||
      c.phone.includes(contactSearch)
  );

  return (
    <div
      className={`min-h-screen flex flex-col font-sans relative overflow-hidden text-slate-800 ${sidebarTab !== "dashboard" ? "bg-[#faf9fa]" : ""}`}
      style={sidebarTab === "dashboard" ? { backgroundImage: "url('https://images.unsplash.com/photo-1514565131-fce0801e5785?auto=format&fit=crop&q=80')", backgroundSize: 'cover', backgroundPosition: 'center' } : {}}
    >
      {/* Dark gradient overlay that is darker on the left and transparent on the right (only on dashboard) */}
      {sidebarTab === "dashboard" && (
        <div className="absolute inset-0 bg-gradient-to-r from-slate-900/90 via-slate-800/50 to-transparent pointer-events-none z-0"></div>
      )}

      <div className="relative z-10 flex flex-col h-full">
        {/* Top Utility Bar */}
        <div className="h-8 bg-white/95 backdrop-blur-sm border-b border-gray-200 flex justify-end items-center px-8 text-[11px] text-gray-600 gap-6">
          <div className="flex items-center gap-1 cursor-pointer hover:text-indigo-600"><span className="w-3 h-3">📅</span> Jan, 2026 - Dec, 2026</div>
          <div className="flex items-center gap-1 border-l border-gray-300 pl-6 cursor-pointer hover:text-indigo-600"><span className="w-3 h-3">🌐</span> EN</div>
        </div>

        {/* Top Header Navigation */}
        <header className="h-16 bg-white px-4 md:px-8 flex items-center justify-between shrink-0 shadow-sm z-10">

          {/* Left Side: Logo & Name */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-indigo-950 font-black text-2xl mr-4 tracking-tighter">
              <div className="w-8 h-8 bg-emerald-500 rounded-lg flex items-center justify-center text-white shadow-md shadow-emerald-500/20">
                <Phone className="w-5 h-5 fill-white text-white" />
              </div>
              SkyAgent <span className="font-normal text-slate-500">Pro</span>
            </div>


          </div>

          {/* Right Side: Navigation Menu & Utilities */}
          <div className="flex items-center gap-6">



            <nav className="hidden xl:flex items-center gap-5">
              {['dashboard', 'dialer', 'scheduler', 'calls', 'reports', 'logs'].map((tab) => {
                const labels: any = { dashboard: 'Metrics', dialer: 'Queue', scheduler: 'Scheduler', calls: 'Calls', reports: 'Reports', logs: 'Logs' };
                return (
                  <button
                    key={tab}
                    onClick={() => setSidebarTab(tab as any)}
                    className={`font-bold text-[13px] transition-colors ${sidebarTab === tab
                        ? "text-indigo-900 border-b-2 border-indigo-900 pb-1 -mb-1"
                        : "text-slate-700 hover:text-indigo-900"
                      }`}
                  >
                    {labels[tab]}
                  </button>
                )
              })}
            </nav>

            {/* Settings / Language Menu Access */}
            <button
              onClick={() => setSidebarTab('voice')}
              className={`p-2 rounded-full transition-colors ${sidebarTab === 'voice'
                  ? "bg-indigo-100 text-indigo-700"
                  : "text-slate-400 hover:text-indigo-600 hover:bg-slate-100"
                }`}
              title="Agent Settings & Language"
            >
              <Settings className="w-5 h-5" />
            </button>

            <TeleforceAgent
              autoDialNumber={activeContact ? activeContact.phone : undefined}
              autoDialTriggerId={activeContact ? activeContact.id : undefined}
              onCallEnded={() => {
                if (activeContact) {
                  setContacts((prev) =>
                    prev.map((c) =>
                      c.id === activeContact.id ? { ...c, status: "Completed" } : c
                    )
                  );
                  setActiveContact(null);
                }
              }}
            />


          </div>
        </header>

        {/* Dynamic Scrollable Dashboard Content */}
        <div className="flex-1 overflow-y-auto">


          {sidebarTab === "dashboard" && (
            <div className="space-y-6 p-4 md:p-8">
              {/* Metrics Strip */}
              <Metrics />

            </div>
          )}

          {sidebarTab === "dialer" && (
            <>
              {/* Grid Workspace */}
              <div id="operational-workspace" className="grid grid-cols-1 gap-6">

                {/* Outbound queue management */}
                <div className="space-y-6 flex flex-col">

                  {/* Hidden file input */}
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileChange}
                    accept=".xlsx,.xls,.csv"
                    className="hidden"
                  />

                  {/* Contacts queue card */}
                  <div id="contacts-queue-card" className="flex-1 flex flex-col min-h-[480px]">
                    <StratroomHeader title="DIALER QUEUE" icon={PhoneCall}>
                      <div className="flex items-center bg-white border border-gray-200 rounded-md shadow-sm h-8 mr-2">
                        <Search className="w-3.5 h-3.5 text-slate-400 ml-2.5" />
                        <input
                          type="text"
                          value={contactSearch}
                          onChange={(e) => setContactSearch(e.target.value)}
                          placeholder="Search Queue..."
                          className="w-32 focus:w-48 transition-all px-2 py-1 text-[11px] focus:outline-none text-slate-800 placeholder-slate-400"
                        />
                      </div>

                      <button
                        id="btn-toggle-autodialer"
                        onClick={() => setAutodialerActive(!autodialerActive)}
                        className={`flex items-center gap-1.5 text-[10px] font-bold px-3 py-1.5 rounded border transition shadow-sm ${autodialerActive
                            ? "bg-amber-50 hover:bg-amber-100 text-amber-700 border-amber-200"
                            : "bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border-indigo-200"
                          }`}
                      >
                        {autodialerActive ? <><Pause className="w-3 h-3" /> Pause</> : <><Play className="w-3 h-3" /> Start</>}
                      </button>

                      <button
                        onClick={() => fileInputRef.current?.click()}
                        className="flex items-center gap-1 bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 text-[10px] font-bold px-3 py-1.5 rounded transition shadow-sm"
                      >
                        <Upload className="w-3 h-3 text-slate-500" /> Import
                      </button>

                      <button
                        onClick={() => setIsAddContactOpen(!isAddContactOpen)}
                        className="flex items-center gap-1 bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 text-[10px] font-bold px-3 py-1.5 rounded transition shadow-sm"
                      >
                        <Plus className="w-3 h-3 text-indigo-500" /> Add
                      </button>
                    </StratroomHeader>

                    {/* Add contact manual inline form */}
                    {isAddContactOpen && (
                      <form
                        onSubmit={handleAddContactSubmit}
                        className="bg-white p-4 border border-purple-100 shadow-sm rounded-xl mb-4 space-y-3 shrink-0"
                      >
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          <div>
                            <input
                              type="text"
                              required
                              value={newContactName}
                              onChange={(e) => setNewContactName(e.target.value)}
                              placeholder="Customer Name"
                              className="w-full px-3 py-2 bg-white border border-gray-200 rounded text-xs focus:outline-none focus:border-purple-300 text-slate-800"
                            />
                          </div>
                          <div>
                            <input
                              type="tel"
                              required
                              value={newContactPhone}
                              onChange={(e) => setNewContactPhone(e.target.value)}
                              placeholder="Phone Number (e.g. +91...)"
                              className="w-full px-3 py-2 bg-white border border-gray-200 rounded text-xs focus:outline-none focus:border-purple-300 text-slate-800"
                            />
                          </div>
                        </div>
                        <div>
                          <input
                            type="text"
                            value={newContactNotes}
                            onChange={(e) => setNewContactNotes(e.target.value)}
                            placeholder="Add brief callback context details..."
                            className="w-full px-3 py-2 bg-white border border-gray-200 rounded text-xs focus:outline-none focus:border-purple-300 text-slate-800"
                          />
                        </div>
                        <div className="flex gap-2 justify-end">
                          <button
                            type="button"
                            onClick={() => setIsAddContactOpen(false)}
                            className="px-3 py-1.5 text-slate-500 hover:bg-slate-50 border border-slate-200 text-xs font-semibold rounded transition"
                          >
                            Cancel
                          </button>
                          <button
                            type="submit"
                            className="bg-[#8b3d6a] hover:bg-purple-900 text-white px-4 py-1.5 text-xs font-semibold rounded shadow-sm"
                          >
                            Save Contact
                          </button>
                        </div>
                      </form>
                    )}

                    <StratroomTable>
                      <StratroomThead>
                        <StratroomTh>Contact Details</StratroomTh>
                        <StratroomTh>Phone Line</StratroomTh>
                        <StratroomTh>Status</StratroomTh>
                        <StratroomTh>Outcome</StratroomTh>
                        <StratroomTh className="text-right">Actions</StratroomTh>
                      </StratroomThead>
                      <tbody className="divide-y divide-gray-100">
                        {filteredContacts.length === 0 ? (
                          <tr>
                            <td colSpan={6} className="py-8 text-center text-slate-500 text-[11px] font-medium bg-white">
                              No contacts loaded. Drag-and-drop your Excel sheet above!
                            </td>
                          </tr>
                        ) : (
                          filteredContacts.map((contact) => (
                            <StratroomTr key={contact.id}>
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
                                <StratroomStatus status={contact.status} />
                              </StratroomTd>
                              <StratroomTd>
                                {contact.outcome ? (
                                  <span className="font-bold text-slate-700">{contact.outcome}</span>
                                ) : contact.scheduledTime ? (
                                  <span className="font-mono text-purple-600">
                                    {new Date(contact.scheduledTime).toLocaleDateString()}
                                  </span>
                                ) : (
                                  <span className="truncate block max-w-[140px] italic text-slate-400">
                                    {contact.notes || "Ready to dial"}
                                  </span>
                                )}
                              </StratroomTd>
                              <StratroomTd>
                                <StratroomActions
                                  onCall={() => handleDialContact(contact)}
                                  onDelete={() => handleDeleteContact(contact.id)}
                                />
                              </StratroomTd>
                            </StratroomTr>
                          ))
                        )}
                      </tbody>
                    </StratroomTable>
                  </div>
                </div>
              </div>
            </>
          )}

          {sidebarTab === "scheduler" && (
            <div className="w-full p-4 md:p-8">
              <ScheduleTracker
                activeContact={activeContact}
                onDialNumber={handleDialNumber}
              />
            </div>
          )}

          {sidebarTab === "calls" && <CallHistory />}

          {sidebarTab === "reports" && <Reports />}

          {sidebarTab === "logs" && (
            <CallLogs
              logs={logs}
              onDeleteLog={handleDeleteLog}
              onClearAllLogs={handleClearAllLogs}
            />
          )}

          {sidebarTab === "voice" && (
            <div className="bg-white/95 backdrop-blur-xl rounded-3xl border border-slate-200/80 shadow-2xl p-8 max-w-4xl mx-auto space-y-7 my-6">
              <div className="border-b border-slate-100 pb-5 flex items-center justify-between">
                <div>
                  <h2 className="font-extrabold text-slate-900 text-xl tracking-tight flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-indigo-600" /> Daffytel AI Voice Agent Configuration
                  </h2>
                  <p className="text-xs font-medium text-slate-500 mt-1">Configure AI agent persona, system prompt instructions, speech voices, and language defaults.</p>
                </div>
                <div className="px-3 py-1 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full text-[11px] font-bold flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> Active Pipeline
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="block text-xs font-bold text-slate-600 uppercase tracking-wider">AI Speech Mode & Voice</label>
                  <select
                    value={speechMode}
                    onChange={(e) => setSpeechMode(e.target.value)}
                    className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 text-xs font-semibold text-slate-800 shadow-sm transition">
                    <option value="Natural Female Voice (Azure Neerja / Pallavi)">Natural Female Voice (Azure Neerja / Pallavi)</option>
                    <option value="Premium Male Voice (Azure Valluvar / Deep)">Premium Male Voice (Azure Valluvar / Deep)</option>
                    <option value="Tamil Female Voice (Pallavi Neural)">Tamil Female Voice (Pallavi Neural)</option>
                    <option value="Tamil Male Voice (Valluvar Neural)">Tamil Male Voice (Valluvar Neural)</option>
                    <option value="Hindi Female Voice (Swara Neural)">Hindi Female Voice (Swara Neural)</option>
                    <option value="Telugu Female Voice (Shruti Neural)">Telugu Female Voice (Shruti Neural)</option>
                    <option value="Kannada Female Voice (Sapna Neural)">Kannada Female Voice (Sapna Neural)</option>
                    <option value="Malayalam Female Voice (Sobhana Neural)">Malayalam Female Voice (Sobhana Neural)</option>
                  </select>
                </div>

                <div className="space-y-2">
                  <label className="block text-xs font-bold text-slate-600 uppercase tracking-wider">Default Language Focus</label>
                  <div className="flex gap-2 flex-wrap">
                    {[
                      { name: "Automatic API", label: "Auto Detect" },
                      { name: "Tamil Support", label: "Tamil தமிழ்" },
                      { name: "Hindi Support", label: "Hindi हिंदी" },
                      { name: "English", label: "English" },
                      { name: "Telugu Support", label: "Telugu తెలుగు" },
                      { name: "Kannada Support", label: "Kannada ಕನ್ನಡ" },
                      { name: "Malayalam Support", label: "Malayalam മലയാളம்" }
                    ].map((lang) => (
                      <button
                        key={lang.name}
                        onClick={() => setLanguageFocus(lang.name)}
                        className={`px-3 py-2 text-[11px] font-bold rounded-xl transition border shadow-sm ${
                          languageFocus === lang.name
                            ? "bg-indigo-600 text-white border-indigo-600 shadow-indigo-200 shadow-md scale-105"
                            : "bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100"
                        }`}
                      >
                        {lang.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <label className="block text-xs font-bold text-slate-600 uppercase tracking-wider">System Prompt Directive Template</label>
                <textarea
                  value={promptTemplate}
                  onChange={(e) => setPromptTemplate(e.target.value)}
                  rows={8}
                  className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-xs font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 leading-relaxed text-slate-800 shadow-inner"
                />
              </div>

              <div className="p-4 bg-indigo-50/70 rounded-2xl flex items-start gap-3 border border-indigo-100/80">
                <Sparkles className="w-5 h-5 text-indigo-600 shrink-0 mt-0.5" />
                <div className="text-xs">
                  <p className="font-bold text-indigo-900">Dynamic Real-Time Conversational Grounding</p>
                  <p className="text-indigo-700/80 mt-1 leading-relaxed">
                    Daffytel AI dynamically parses incoming customer speech, switches between Tamil, Hindi, and English automatically, and streams response audio via sub-500ms neural pipelines.
                  </p>
                </div>
              </div>

              <div className="flex justify-end pt-3 border-t border-slate-100">
                <button
                  onClick={handleSaveVoiceConfig}
                  disabled={isSavingVoice}
                  className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-500 text-white font-bold py-3 px-8 rounded-2xl transition duration-150 flex items-center gap-2.5 text-xs tracking-wide shadow-lg shadow-indigo-100 active:scale-95 cursor-pointer"
                >
                  <CheckCircle className="w-4 h-4" />
                  {isSavingVoice ? "Saving..." : "Save Configuration"}
                </button>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}

