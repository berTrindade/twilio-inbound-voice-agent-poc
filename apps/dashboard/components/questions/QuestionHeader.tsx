import { Badge } from '@/components/ui';
import { formatDuration } from '@/utils/formatters';
import type { QuestionDetail, SurveyNode } from '@/utils/types';

interface QuestionHeaderProps {
  question: QuestionDetail;
  questionNumber: number;
  surveyNode?: SurveyNode;
  isExpanded: boolean;
  onToggle: () => void;
}

export default function QuestionHeader({
  question,
  questionNumber,
  surveyNode,
  isExpanded,
  onToggle,
}: QuestionHeaderProps) {
  const nodeType = question?.node_type || 'unknown';
  const questionText = question?.question_text || 'N/A';
  const attempts = question?.attempts || 0;
  const turnsCount = question?.turns?.length || 0;

  // Get raw answer value
  const rawAnswer = question?.final_answer;
  const hasAnswer = rawAnswer !== null && rawAnswer !== undefined;
  const isHandover = nodeType === 'handover_to_coach' ||
    (typeof rawAnswer === 'object' && rawAnswer?.mode === 'handover_to_coach') ||
    (typeof rawAnswer === 'string' && rawAnswer.includes("'mode': 'handover_to_coach'"));

  // Extract whisper text from the answer (stored as Python repr string or object)
  const parseWhisperText = (): string | null => {
    if (!hasAnswer) return null;
    if (typeof rawAnswer === 'object' && rawAnswer?.whisper_text) {
      return String(rawAnswer.whisper_text);
    }
    if (typeof rawAnswer === 'string') {
      const match = rawAnswer.match(/'whisper_text':\s*'([^']+)'/);
      return match?.[1] ?? null;
    }
    return null;
  };

  const whisperText = isHandover ? parseWhisperText() : null;

  // Format the answer for display (just the value/ID)
  const formatAnswer = (): string => {
    if (!hasAnswer) return 'N/A';
    if (isHandover) return 'Transferred to coach';
    if (Array.isArray(rawAnswer)) {
      return rawAnswer.length > 0 ? rawAnswer.join(', ') : 'N/A';
    }
    if (typeof rawAnswer === 'object' && rawAnswer !== null) {
      return JSON.stringify(rawAnswer);
    }
    return String(rawAnswer);
  };

  const answerDisplay = formatAnswer();
  const isNA = answerDisplay === 'N/A';
  
  // Check if this is a choice question with options
  const hasOptions = surveyNode?.options && surveyNode.options.length > 0;

  return (
    <button onClick={onToggle} className="cursor-pointer w-full text-left">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          {/* Question metadata badges */}
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className="text-sm font-medium text-gray-500">
              Question {questionNumber}
            </span>
            <Badge>{nodeType}</Badge>
            {question?.question_id && (
              <span className="px-3 py-1 bg-brand/10 text-brand rounded-full text-xs font-medium">
                {question.question_id}
              </span>
            )}
            {attempts > 1 && (
              <Badge variant="warning">{attempts} attempts</Badge>
            )}
          </div>

          {/* Question text */}
          <h3 className="text-lg font-medium text-gray-900 mb-2">
            {questionText}
          </h3>

          {/* Question stats */}
          <div className="flex items-center gap-4 text-sm text-gray-500">
            <span>Duration: {formatDuration(question?.duration_ms)}</span>
            <span>•</span>
            <span>{turnsCount} turns</span>
          </div>

          {/* Handover display — two distinct blocks */}
          {isHandover ? (
            <div className="mt-4 space-y-2">
              {/* Spoken to caller */}
              <div className="p-3 rounded-lg flex items-start gap-3 bg-amber-50 border border-amber-200">
                <div className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-amber-500 text-white">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium uppercase tracking-wider text-amber-600">
                    Transferred to Coach
                  </p>
                  <p className="text-sm text-amber-900 mt-0.5">
                    {questionText}
                  </p>
                </div>
              </div>
              {/* Whisper context for coach */}
              {whisperText && (
                <div className="p-3 rounded-lg flex items-start gap-3 bg-violet-50 border border-violet-200">
                  <div className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-violet-500 text-white">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                    </svg>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium uppercase tracking-wider text-violet-600">
                      Whisper to Coach
                    </p>
                    <p className="text-sm text-violet-900 mt-0.5">
                      {whisperText}
                    </p>
                  </div>
                </div>
              )}
            </div>
          ) : (
          /* Regular answer display */
          <div className={`mt-4 p-3 rounded-lg flex items-center gap-3 ${
            isNA
              ? 'bg-gray-50 border border-gray-200'
              : 'bg-emerald-50 border border-emerald-200'
          }`}>
            <div className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
              isNA
                ? 'bg-gray-200 text-gray-500'
                : 'bg-emerald-500 text-white'
            }`}>
              {isNA ? (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-xs font-medium uppercase tracking-wider ${
                isNA ? 'text-gray-500' : 'text-emerald-600'
              }`}>
                Answer
              </p>
              <code className={`text-sm font-mono font-semibold ${
                isNA ? 'text-gray-600' : 'text-emerald-800'
              }`}>
                {answerDisplay}
              </code>
            </div>
          </div>
          )}

          {/* Options reference block */}
          {hasOptions && (
            <div className="mt-2 p-2 bg-slate-50 border border-slate-200 rounded-lg">
              <p className="text-xs font-medium text-slate-500 mb-1.5 flex items-center gap-1">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Available options
              </p>
              <div className="flex flex-wrap gap-1.5">
                {surveyNode!.options!.map((opt) => (
                  <span
                    key={opt.value}
                    className={`inline-flex items-center text-xs px-2 py-0.5 rounded ${
                      answerDisplay.split(', ').includes(opt.value)
                        ? 'bg-emerald-100 text-emerald-700 font-medium'
                        : 'bg-white text-slate-600 border border-slate-200'
                    }`}
                  >
                    <code className="font-mono mr-1">{opt.value}</code>
                    <span className="text-slate-400">=</span>
                    <span className="ml-1">{opt.label}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Expand/collapse chevron */}
        <div className="ml-4">
          <svg
            className={`w-6 h-6 text-gray-400 transition-transform ${
              isExpanded ? 'transform rotate-180' : ''
            }`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </div>
      </div>
    </button>
  );
}

