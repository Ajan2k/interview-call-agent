export type ContactStatus = "Pending" | "Calling" | "Ringing" | "Active" | "Voicemail" | "Completed" | "Failed" | "Scheduled";
export type CampaignType = "reminder" | "support" | "sales" | "feedback";

export interface Contact {
  id: string;
  name: string;
  phone: string;
  email?: string;
  status: ContactStatus;
  outcome?: "Interested" | "Not Interested" | "No Answer" | "Scheduled Callback" | "DND" | "N/A";
  duration?: number; // in seconds
  callTime?: string;
  scheduledTime?: string;
  notes?: string;
  isIncoming?: boolean;
  is_incoming?: boolean;
  lastCalled?: string;
  campaignId?: string;
}

export interface Campaign {
  id: string;
  name: string;
  type: CampaignType;
  status: "Draft" | "Running" | "Paused" | "Completed";
  totalContacts: number;
  completedContacts: number;
  successRate: number; // e.g., 75%
  createdAt: string;
  systemInstruction?: string;
}

export interface CallMessage {
  id: string;
  role: "user" | "model" | "system";
  text: string;
  timestamp: string;
}

export interface CallLog {
  id: string;
  contactName: string;
  phone: string;
  campaignName: string;
  duration: number; // seconds
  outcome: "Interested" | "Not Interested" | "No Answer" | "Scheduled Callback" | "DND";
  sentiment: "Positive" | "Neutral" | "Negative";
  time: string;
  transcript: CallMessage[];
  notes?: string;
}
