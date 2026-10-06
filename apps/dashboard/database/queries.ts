import { sql } from './db';
import type { SurveyResponse, Question } from './db';
import { decrypt, decryptJson } from '@/utils/encryption';
import type {
  SurveyNode,
  SurveyLookup,
  VolumeByDayRow,
  CompletionRateTrendRow,
  DropoffByQuestionRow,
  AvgConfidenceByQuestionRow,
  IntegrationSuccessRateRow,
  AnalyticsData,
} from '@/utils/types';

/** Query result that includes a computed duration_seconds column */
type ResponseWithDuration = SurveyResponse & { duration_seconds: number | null };

// Stats for dashboard cards (extended with trend data + new KPIs)
export async function getResponseStats() {
  try {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterdayStart = new Date(todayStart.getTime() - 24 * 60 * 60 * 1000);
    const weekStart = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    const prevWeekStart = new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000);

    const [stats] = await sql`
      SELECT
        COUNT(CASE WHEN started_at >= ${todayStart} THEN 1 END)::int as total_today,
        COUNT(CASE WHEN started_at >= ${yesterdayStart} AND started_at < ${todayStart} THEN 1 END)::int as total_yesterday,
        COUNT(CASE WHEN started_at >= ${weekStart} THEN 1 END)::int as total_this_week,
        COUNT(CASE WHEN started_at >= ${prevWeekStart} AND started_at < ${weekStart} THEN 1 END)::int as total_prev_week,
        COUNT(*)::int as total_all,
        COUNT(CASE WHEN status != 'in_progress' THEN 1 END)::int as closed_count,
        COUNT(CASE WHEN status = 'completed' THEN 1 END)::int as completed_count,
        COUNT(CASE WHEN status = 'completed' AND started_at >= ${weekStart} THEN 1 END)::int as completed_this_week,
        COUNT(CASE WHEN started_at >= ${weekStart} AND status != 'in_progress' THEN 1 END)::int as closed_this_week,
        COUNT(CASE WHEN status = 'completed' AND started_at >= ${prevWeekStart} AND started_at < ${weekStart} THEN 1 END)::int as completed_prev_week,
        COUNT(CASE WHEN started_at >= ${prevWeekStart} AND started_at < ${weekStart} AND status != 'in_progress' THEN 1 END)::int as closed_prev_week,
        AVG(CASE
          WHEN status = 'completed' AND completed_at IS NOT NULL
          THEN EXTRACT(EPOCH FROM (completed_at - started_at))
        END)::float as average_duration_seconds,
        AVG(CASE
          WHEN status = 'completed' AND completed_at IS NOT NULL AND started_at >= ${prevWeekStart} AND started_at < ${weekStart}
          THEN EXTRACT(EPOCH FROM (completed_at - started_at))
        END)::float as avg_duration_prev_week,
        COUNT(CASE WHEN status = 'in_progress' THEN 1 END)::int as active_calls,
        ROUND(
          COUNT(CASE WHEN COALESCE(escalations_count, 0) > 0 THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0),
          2
        )::float as escalation_rate
      FROM survey_responses
    `;

    // Completed over *closed*, not over everything. A call still in progress
    // has not failed to complete, it just has not finished yet, so counting it
    // against the rate drags the headline figure down whenever calls are live
    // and makes it disagree with the weekly rates beside it, which have always
    // been computed this way.
    const completion_rate = stats.closed_count > 0
      ? Math.round((stats.completed_count / stats.closed_count) * 100 * 100) / 100
      : 0;

    const completion_rate_this_week = stats.closed_this_week > 0
      ? Math.round((stats.completed_this_week / stats.closed_this_week) * 100 * 100) / 100
      : 0;

    const completion_rate_prev_week = stats.closed_prev_week > 0
      ? Math.round((stats.completed_prev_week / stats.closed_prev_week) * 100 * 100) / 100
      : 0;

    return {
      total_today: stats.total_today,
      total_yesterday: stats.total_yesterday,
      total_this_week: stats.total_this_week,
      total_prev_week: stats.total_prev_week,
      completion_rate,
      completion_rate_this_week,
      completion_rate_prev_week,
      average_duration_seconds: stats.average_duration_seconds,
      avg_duration_prev_week: stats.avg_duration_prev_week ?? null,
      active_calls: stats.active_calls,
      escalation_rate: stats.escalation_rate ?? 0,
    };
  } catch (e) {
    console.error('[DB] getResponseStats failed:', e);
    return {
      total_today: 0,
      total_yesterday: 0,
      total_this_week: 0,
      total_prev_week: 0,
      completion_rate: 0,
      completion_rate_this_week: 0,
      completion_rate_prev_week: 0,
      average_duration_seconds: null,
      avg_duration_prev_week: null,
      active_calls: 0,
      escalation_rate: 0,
    };
  }
}

// Analytics: call volume grouped by day
async function getVolumeByDay(windowDays: number): Promise<VolumeByDayRow[]> {
  try {
    const rows = await sql`
      SELECT
        DATE(started_at)::text as date,
        COUNT(CASE WHEN status = 'completed' THEN 1 END)::int as completed,
        COUNT(CASE WHEN status = 'abandoned' THEN 1 END)::int as abandoned,
        COUNT(CASE WHEN status = 'in_progress' THEN 1 END)::int as in_progress
      FROM survey_responses
      WHERE started_at >= NOW() - INTERVAL '1 day' * ${windowDays}
      GROUP BY DATE(started_at)
      ORDER BY date ASC
    `;
    return rows as unknown as VolumeByDayRow[];
  } catch (e) {
    console.error('[DB] getVolumeByDay failed:', e);
    return [];
  }
}

// Analytics: completion rate trend by day
async function getCompletionRateTrend(windowDays: number): Promise<CompletionRateTrendRow[]> {
  try {
    const rows = await sql`
      SELECT
        DATE(started_at)::text as date,
        CASE
          WHEN COUNT(CASE WHEN status != 'in_progress' THEN 1 END) > 0
          THEN ROUND(
            COUNT(CASE WHEN status = 'completed' THEN 1 END) * 100.0 /
            NULLIF(COUNT(CASE WHEN status != 'in_progress' THEN 1 END), 0),
            2
          )::float
          ELSE 0
        END as rate
      FROM survey_responses
      WHERE started_at >= NOW() - INTERVAL '1 day' * ${windowDays}
      GROUP BY DATE(started_at)
      ORDER BY date ASC
    `;
    return rows as unknown as CompletionRateTrendRow[];
  } catch (e) {
    console.error('[DB] getCompletionRateTrend failed:', e);
    return [];
  }
}

// Analytics: which question abandoned calls dropped off at
async function getDropoffByQuestion(windowDays: number): Promise<DropoffByQuestionRow[]> {
  try {
    const rows = await sql`
      SELECT
        last_question_id as question_id,
        last_question_text as question_text,
        COUNT(*)::int as abandonment_count
      FROM survey_responses
      WHERE status = 'abandoned'
        AND started_at >= NOW() - INTERVAL '1 day' * ${windowDays}
        AND last_question_id IS NOT NULL
      GROUP BY last_question_id, last_question_text
      ORDER BY abandonment_count DESC
      LIMIT 15
    `;
    return rows as unknown as DropoffByQuestionRow[];
  } catch (e) {
    console.error('[DB] getDropoffByQuestion failed:', e);
    return [];
  }
}

// Analytics: average LLM confidence score per question
async function getAvgConfidenceByQuestion(windowDays: number): Promise<AvgConfidenceByQuestionRow[]> {
  try {
    const rows = await sql`
      SELECT responses
      FROM survey_responses
      WHERE started_at >= NOW() - INTERVAL '1 day' * ${windowDays}
    `;

    // Decrypt and compute averages in-memory
    const questionStats = new Map<string, { text: string; sum: number; count: number }>();

    for (const row of rows) {
      const data = decryptJson(row.responses);
      const questions = data?.questions;
      if (!Array.isArray(questions)) continue;

      for (const q of questions) {
        const turns = q.turns;
        if (!Array.isArray(turns)) continue;

        for (const t of turns) {
          const conf = t.llm_confidence;
          if (conf == null || conf === 'null') continue;
          const numConf = typeof conf === 'number' ? conf : parseFloat(conf);
          if (isNaN(numConf)) continue;

          const key = q.question_id;
          if (!key) continue;
          const existing = questionStats.get(key);
          if (existing) {
            existing.sum += numConf;
            existing.count += 1;
          } else {
            questionStats.set(key, { text: q.question_text || '', sum: numConf, count: 1 });
          }
        }
      }
    }

    const result: AvgConfidenceByQuestionRow[] = [];
    for (const [question_id, stats] of questionStats) {
      result.push({
        question_id,
        question_text: stats.text,
        avg_confidence: Math.round((stats.sum / stats.count) * 10000) / 10000,
      });
    }

    return result
      .sort((a, b) => a.avg_confidence - b.avg_confidence)
      .slice(0, 15);
  } catch (e) {
    console.error('[DB] getAvgConfidenceByQuestion failed:', e);
    return [];
  }
}

// Analytics: integration success/failure counts
export async function getIntegrationSuccessRates(windowDays: number): Promise<IntegrationSuccessRateRow[]> {
  try {
    const rows = await sql`
      SELECT 'Submission' as integration,
        COUNT(CASE WHEN integration_outcomes->'local_submission'->>'success' = 'true' THEN 1 END)::int as success,
        COUNT(CASE WHEN integration_outcomes->'local_submission'->>'success' = 'false' THEN 1 END)::int as failure,
        COUNT(CASE WHEN integration_outcomes ? 'local_submission' THEN 1 END)::int as total
      FROM survey_responses
      WHERE started_at >= NOW() - INTERVAL '1 day' * ${windowDays}
    `;
    return rows as unknown as IntegrationSuccessRateRow[];
  } catch (e) {
    console.error('[DB] getIntegrationSuccessRates failed:', e);
    return [];
  }
}

// Unified analytics fetch (all 5 queries in parallel)
export async function getAnalyticsData(windowDays: number): Promise<AnalyticsData> {
  try {
    const [
      volumeByDay,
      completionRateTrend,
      dropoffByQuestion,
      avgConfidenceByQuestion,
      integrationSuccessRates,
    ] = await Promise.all([
      getVolumeByDay(windowDays),
      getCompletionRateTrend(windowDays),
      getDropoffByQuestion(windowDays),
      getAvgConfidenceByQuestion(windowDays),
      getIntegrationSuccessRates(windowDays),
    ]);
    return { volumeByDay, completionRateTrend, dropoffByQuestion, avgConfidenceByQuestion, integrationSuccessRates };
  } catch (e) {
    console.error('[DB] getAnalyticsData failed:', e);
    return {
      volumeByDay: [],
      completionRateTrend: [],
      dropoffByQuestion: [],
      avgConfidenceByQuestion: [],
      integrationSuccessRates: [],
    };
  }
}

// Sortable columns, by the value the UI puts in the URL. Anything not on this
// map is not sortable; see the ORDER BY note in getResponses.
const SORT_COLUMNS: Record<string, string> = {
  started_at: 'started_at',
  completed_at: 'completed_at',
  status: 'status',
  duration: 'EXTRACT(EPOCH FROM (completed_at - started_at))',
};

// List responses with filters and pagination
export async function getResponses({
  page = 1,
  pageSize = 25,
  status,
  dateRange,
  minDuration,
  maxDuration,
  sortBy = 'started_at',
  sortOrder = 'desc',
}: {
  page?: number;
  pageSize?: number;
  status?: string;
  dateRange?: string;
  minDuration?: number;
  maxDuration?: number;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}) {
  try {
    const offset = (page - 1) * pageSize;

    // Calculate date cutoff if needed
    let cutoffDate: Date | null = null;
    if (dateRange) {
      const now = new Date();
      if (dateRange === '24h') {
        cutoffDate = new Date(now.getTime() - 24 * 60 * 60 * 1000);
      } else if (dateRange === '7d') {
        cutoffDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      } else if (dateRange === '30d') {
        cutoffDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      }
    }

    // Build base query with all possible conditions
    const baseWhere = `
      WHERE 1=1
      ${status ? `AND status = $1` : ''}
      ${cutoffDate ? `AND started_at >= $${status ? 2 : 1}` : ''}
      ${minDuration !== undefined || maxDuration !== undefined ? 'AND completed_at IS NOT NULL' : ''}
      ${minDuration !== undefined ? `AND EXTRACT(EPOCH FROM (completed_at - started_at)) >= $${[status, cutoffDate].filter(Boolean).length + 1}` : ''}
      ${maxDuration !== undefined ? `AND EXTRACT(EPOCH FROM (completed_at - started_at)) <= $${[status, cutoffDate, minDuration !== undefined].filter(Boolean).length + 1}` : ''}
    `;

    // Collect all parameters in order
    const params: (string | number | Date)[] = [];
    if (status) params.push(status);
    if (cutoffDate) params.push(cutoffDate);
    if (minDuration !== undefined) params.push(minDuration);
    if (maxDuration !== undefined) params.push(maxDuration);

    // Get total count
    const countResult = await sql.unsafe(`
      SELECT COUNT(*)::int as total
      FROM survey_responses
      ${baseWhere}
    `, params);

    const total = countResult[0].total;

    // Build ORDER BY. sortBy and sortOrder reach this query as raw
    // searchParams and are interpolated into SQL rather than bound as
    // parameters, because a column name cannot be a bind parameter. They are
    // therefore resolved through a fixed map instead of being trusted: an
    // unrecognised value falls back to the default rather than reaching the
    // database.
    const orderByCol = SORT_COLUMNS[sortBy] ?? SORT_COLUMNS.started_at;
    const orderDir = sortOrder.toLowerCase() === 'asc' ? 'ASC' : 'DESC';
    const nullsLast = sortBy === 'duration' ? 'NULLS LAST' : '';

    // Get paginated results with all parameters plus pagination
    const allParams = [...params, pageSize, offset];

    const responses = await sql.unsafe(`
      SELECT
        id,
        participant_phone,
        status,
        started_at,
        completed_at,
        responses,
        CASE
          WHEN completed_at IS NOT NULL
          THEN EXTRACT(EPOCH FROM (completed_at - started_at))::int
          ELSE NULL
        END as duration_seconds
      FROM survey_responses
      ${baseWhere}
      ORDER BY ${orderByCol} ${orderDir} ${nullsLast}
      LIMIT $${params.length + 1}
      OFFSET $${params.length + 2}
    `, allParams) as ResponseWithDuration[];

    const items = responses.map((r) => {
      // Decrypt and mask phone number
      const phone = decrypt(r.participant_phone);
      const masked_phone = phone.length > 4
        ? phone.substring(0, 4) + '***'
        : '***';

      // Decrypt responses and count questions
      const responsesData = decryptJson(r.responses);
      const questions_answered = responsesData?.questions?.length || 0;

      return {
        id: r.id,
        participant_phone: masked_phone,
        status: r.status,
        started_at: r.started_at.toISOString(),
        completed_at: r.completed_at ? r.completed_at.toISOString() : null,
        duration_seconds: r.duration_seconds,
        questions_answered,
      };
    });

    const totalPages = Math.ceil(total / pageSize);

    return {
      items,
      total,
      page,
      page_size: pageSize,
      total_pages: totalPages,
    };
  } catch (e) {
    console.error('[DB] getResponses failed:', e);
    return {
      items: [],
      total: 0,
      page,
      page_size: pageSize,
      total_pages: 0,
    };
  }
}

// Get single response detail
export async function getResponseById(id: string) {
  try {
    // Fetch response with joined survey data
    const [result] = await sql`
      SELECT
        sr.id,
        sr.participant_phone,
        sr.status,
        sr.started_at,
        sr.completed_at,
        sr.responses,
        sr.session_metadata,
        sr.integrations,
        s.data as survey_data,
        CASE
          WHEN sr.completed_at IS NOT NULL
          THEN EXTRACT(EPOCH FROM (sr.completed_at - sr.started_at))::int
          ELSE NULL
        END as duration_seconds
      FROM survey_responses sr
      LEFT JOIN surveys s ON sr.survey_id = s.id
      WHERE sr.id = ${id}
    `;

    if (!result) {
      return null;
    }

    const response = result as ResponseWithDuration & { survey_data: SurveyNode[] | null };

    // Decrypt and mask phone number
    const phone = decrypt(response.participant_phone);
    const masked_phone = phone.length > 4
      ? phone.substring(0, 4) + '***'
      : '***';

    // Decrypt JSONB columns
    const sessionMeta = decryptJson(response.session_metadata);
    const responsesData = decryptJson(response.responses);
    const integrationsData = decryptJson(response.integrations);

    // Build survey lookup map from survey data
    const surveyLookup: SurveyLookup = {};
    if (response.survey_data && Array.isArray(response.survey_data)) {
      for (const node of response.survey_data) {
        surveyLookup[node.id] = node;
      }
    }

    // Transform questions to map 'answer' field to 'final_answer' for consistency
    const questions = (responsesData?.questions || []).map((q: Question & { answer?: unknown }) => ({
      ...q,
      final_answer: q.final_answer ?? q.answer, // Use final_answer if exists, otherwise use answer
    }));

    return {
      id: response.id,
      participant_phone: masked_phone,
      status: response.status,
      started_at: response.started_at.toISOString(),
      completed_at: response.completed_at ? response.completed_at.toISOString() : null,
      duration_seconds: response.duration_seconds,
      call_sid: sessionMeta.call_sid || null,
      session_id: sessionMeta.session_id || null,
      correlation_id: sessionMeta.correlation_id || null,
      completion_reason: sessionMeta.completion_reason || null,
      total_questions: sessionMeta.total_questions || 0,
      total_turns: sessionMeta.total_turns || 0,
      escalations_count: sessionMeta.escalations_count || 0,
      interruptions_count: sessionMeta.interruptions_count || 0,
      nodes_visited: sessionMeta.nodes_visited || [],
      integrations: integrationsData || null,
      questions,
      surveyLookup,
    };
  } catch (e) {
    console.error('[DB] getResponseById failed:', e);
    return null;
  }
}

/**
 * How many of the rows on screen are example data.
 *
 * The seeder writes calls with a CAdemo prefix where a real call carries a
 * Twilio CallSid, which is what lets the dashboard say plainly that these are
 * invented rather than letting someone read them as traffic.
 */
export async function getDemoCallCount(): Promise<number> {
  try {
    const [row] = await sql`
      SELECT COUNT(*)::int as count
      FROM survey_responses
      WHERE call_sid LIKE 'CAdemo%'
    `;
    return row?.count ?? 0;
  } catch (e) {
    console.error('[DB] getDemoCallCount failed:', e);
    return 0;
  }
}
