/**
 * Shared types for the dashboard
 */

interface ValidationResult {
  valid: boolean;
  reason?: string;
}

export interface TurnDetail {
  turn_number: number;
  timestamp: string;
  assistant_message: string;
  user_message: string;
  llm_interpretation: string;
  llm_confidence: number | null;
  validation_result: ValidationResult | null;
  escalated: boolean;
}

export interface QuestionDetail {
  question_id: string;
  question_text: string;
  node_type: string;
  started_at: string;
  completed_at?: string;
  duration_ms?: number;
  attempts: number;
  final_answer?: string | Record<string, unknown> | null;
  turns: TurnDetail[];
}

export interface SurveyNode {
  id: string;
  type: string;
  text: string;
  options?: { value: string; label: string }[];
}

export type SurveyLookup = Record<string, SurveyNode>;

// The self-hosted build records a single integration event when the call ends:
// LocalSubmissionHandler persists the collected answers under the "local_submission"
// key. This shape must match the backend handler's update_integration_event payload.
export interface LocalSubmissionIntegration {
  timestamp?: string;
  response: {
    success: boolean;
    answer_count?: number;
    answers?: Record<string, unknown>;
    error?: string | null;
    status_code?: number;
    response_body?: string;
  };
}

export interface IntegrationsData {
  local_submission?: LocalSubmissionIntegration;
}

// Analytics types
export interface VolumeByDayRow {
  date: string;
  completed: number;
  abandoned: number;
  in_progress: number;
}

export interface CompletionRateTrendRow {
  date: string;
  rate: number;
}

export interface DropoffByQuestionRow {
  question_id: string;
  question_text: string;
  abandonment_count: number;
}

export interface AvgConfidenceByQuestionRow {
  question_id: string;
  question_text: string;
  avg_confidence: number;
}

export interface IntegrationSuccessRateRow {
  integration: string;
  success: number;
  failure: number;
  total: number;
}

export interface AnalyticsData {
  volumeByDay: VolumeByDayRow[];
  completionRateTrend: CompletionRateTrendRow[];
  dropoffByQuestion: DropoffByQuestionRow[];
  avgConfidenceByQuestion: AvgConfidenceByQuestionRow[];
  integrationSuccessRates: IntegrationSuccessRateRow[];
}
