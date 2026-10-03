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
  message?: string;
}

export interface InterviewQuestion {
  id: string;
  category: "behavioral" | "technical";
  text: string;
  competency: string;
  order: number;
  completed?: boolean;
  answer_notes?: string;
}

export interface Scorecard {
  overall_score: number;
  recommendation: "Strong Hire" | "Hire" | "Consider" | "Do Not Hire";
  technical_score: number;
  behavioral_score: number;
  communication_score: number;
  summary: string;
  strengths: string[];
  areas_for_improvement: string[];
  question_evaluations?: Array<{
    question: string;
    summary_of_answer?: string;
    score?: number;
    feedback?: string;
  }>;
  evaluated_at?: string;
}

export interface Candidate {
  id: string;
  name: string;
  phone: string;
  position: string;
  job_description: string;
  resume_filename: string;
  resume_text?: string;
  status: "ready" | "in_progress" | "completed" | "evaluated";
  questions: InterviewQuestion[];
  scorecard?: Scorecard;
  call_id?: string;
  created_at: string;
  updated_at: string;
}
