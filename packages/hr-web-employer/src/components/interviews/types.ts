/**
 * Shared types across the Interview Copilot module.
 * Mirrors the dataclass shapes from app.services.interview_copilot_service
 * + interview_scorecard_service so the frontend can rely on a single
 * canonical contract.
 */
export type InterviewType = "screen" | "technical" | "onsite" | "culture" | "final";
export type ConsentStatus = "not_collected" | "requested" | "granted" | "denied";
export type Severity = "info" | "warn" | "block";

export type Interview = {
  id: string;
  org_id: string;
  candidate_id?: string;
  candidate_name: string;
  job_id?: string;
  job_title: string;
  interview_type: InterviewType;
  scheduled_at?: string | null;
  duration_minutes: number;
  status: "scheduled" | "live" | "completed" | "cancelled";
  consent_status: ConsentStatus;
  recording_enabled: boolean;
  interview_plan?: InterviewPlan | null;
  participants: { name?: string; role?: string; status?: string }[];
  created_by?: string | null;
  created_at: string;
};

export type InterviewPlan = {
  focus_areas: string[];
  agenda: { minutes: number; topic: string }[];
  verify: string[];
  concerns_to_explore: string[];
  positive_signals_to_confirm: string[];
  candidate_specific_notes: string;
  generated_by: "llm" | "local";
};

export type InterviewQuestion = {
  id: string;
  interview_id: string;
  text: string;
  competency: string;
  required: boolean;
  asked: boolean;
  generated_by_ai: boolean;
  rationale?: string;
};

export type TranscriptLine = {
  id: string;
  interview_id: string;
  speaker: "interviewer" | "candidate" | "unknown";
  speaker_name?: string;
  text: string;
  timestamp: string;
  confidence: number;
};

export type ConsentRecord = {
  interview_id: string;
  candidate_consent_status: ConsentStatus;
  interviewer_consent_status: ConsentStatus;
  consent_recorded_at?: string | null;
  consent_recorded_by?: string | null;
  policy_version: string;
  recording_enabled: boolean;
};

export type FairnessFlag = {
  severity: Severity;
  category: string;
  title: string;
  detail: string;
  span?: string | null;
  rule_id?: string | null;
  suggestion?: string | null;
};

export type InterviewInsight = {
  id: string;
  interview_id: string;
  type: "follow_up" | "missing_evidence" | "strong_signal" | "fairness" | "summary";
  severity: Severity;
  title: string;
  description: string;
  evidence: string[];
  recommended_action: string;
  created_at: string;
};

export type CompetencyScore = {
  competency: string;
  rating?: number | null;
  ai_suggested_rating?: number | null;
  notes: string;
  evidence_snippets: string[];
  final_rating?: number | null;
  fairness_flags: FairnessFlag[];
  rating_label?: string;
};

export type Scorecard = {
  id: string;
  interview_id: string;
  interviewer_id: string;
  interviewer_name: string;
  competencies: CompetencyScore[];
  overall_rating?: number | null;
  overall_recommendation?: string | null;
  interviewer_confidence?: number | null;
  submitted_at?: string | null;
  status: "draft" | "submitted";
  created_at: string;
};

export type LiveContext = {
  live_summary: string;
  missing_evidence: InterviewInsight[];
  scorecard_mapping: {
    competency: string;
    evidence_detected: boolean;
    matched_phrases: string[];
    confidence: number;
    suggested_rating: number | null;
    note: string;
  }[];
  follow_up_questions: { text: string; competency: string; rationale: string }[];
  transcript_lines: number;
};

export type PostSummary = {
  ready: boolean;
  candidate_name: string;
  job_title: string;
  overall_score?: number;
  band?: "strong" | "moderate" | "weak";
  recommendation?: "advance" | "advance_with_caveats" | "hold" | "decline";
  narrative?: string;
  strengths?: string[];
  concerns?: string[];
  competency_scores?: Record<string, number>;
  panel_debrief?: {
    interviewer_name: string;
    overall_rating: number | null;
    rating_label: string;
    confidence: number | null;
    headline_competency: string | null;
  }[];
  next_actions?: string[];
  candidate_feedback_draft?: string;
  offer_risk_notes?: string[];
  calibration?: any;
  fairness_note?: string;
  insights_recorded?: number;
};

export const RATING_LABEL = ["No hire", "Lean no hire", "Lean hire", "Hire", "Strong hire"];
