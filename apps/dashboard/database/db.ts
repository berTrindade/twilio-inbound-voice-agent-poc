import postgres from 'postgres';
import type { IntegrationsData } from '@/utils/types';

const connectionString = process.env.DATABASE_URL || 'postgresql://survey_user:survey_pass@localhost:5432/survey_db';

// Create a postgres connection
export const sql = postgres(connectionString, {
  max: 10,
  idle_timeout: 20,
  connect_timeout: 10,
  // Local/test only: opt-in disable of SSL via DATABASE_SSL=disable.
  // Production never sets this flag, so the default 'require' behavior is unchanged.
  ssl: process.env.DATABASE_SSL === 'disable' ? false : 'require',
});

// Types matching the database schema
export interface SurveyResponse {
  id: string;
  survey_id: string;
  participant_phone: string;
  status: 'in_progress' | 'completed' | 'abandoned';
  responses: {
    questions: Question[];
  };
  session_metadata: SessionMetadata | null;
  integrations: IntegrationsData | null;
  started_at: Date;
  completed_at: Date | null;
  created_at: Date;
}

export interface Question {
  question_id: string;
  question_text: string;
  node_type: string;
  started_at: string;
  completed_at?: string;
  duration_ms?: number;
  attempts: number;
  final_answer?: string | Record<string, unknown> | null;
  turns: Turn[];
}

interface Turn {
  turn_number: number;
  timestamp: string;
  assistant_message: string;
  user_message: string;
  llm_interpretation: string;
  llm_confidence: number | null;
  validation_result: ValidationResult | null;
  escalated: boolean;
}

interface ValidationResult {
  valid: boolean;
  reason?: string;
}

interface SessionMetadata {
  call_sid?: string;
  session_id?: string;
  correlation_id?: string;
  total_duration_ms?: number;
  total_questions?: number;
  total_turns?: number;
  completion_reason?: string;
  nodes_visited?: string[];
  escalations_count?: number;
  interruptions_count?: number;
}

