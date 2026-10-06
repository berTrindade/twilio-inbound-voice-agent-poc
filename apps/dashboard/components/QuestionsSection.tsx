import { Warning } from '@/components/ui';
import QuestionAccordion from './QuestionAccordion';
import type { QuestionDetail, SurveyLookup } from '@/utils/types';

interface QuestionsSectionProps {
  questions: QuestionDetail[];
  surveyLookup: SurveyLookup;
}

function SectionHeader() {
  return (
    <div className="px-6 py-4 border-b border-gray-200">
      <h2 className="text-xl font-semibold text-gray-900">Questions & Conversations</h2>
      <p className="text-sm text-gray-500 mt-1">
        Click on each question to expand/collapse the full conversation
      </p>
    </div>
  );
}

function NoResponsesWarning() {
  return (
    <div className="p-6">
      <Warning
        title="No responses recorded"
        description="This survey session has no question responses yet. The call may have ended before any questions were answered."
      />
    </div>
  );
}

function QuestionsList({
  questions,
  surveyLookup,
}: {
  questions: QuestionDetail[];
  surveyLookup: SurveyLookup;
}) {
  return (
    <div className="divide-y divide-gray-200">
      {questions.map((question, idx) => (
        <QuestionAccordion
          key={question?.question_id || `question-${idx}`}
          question={question}
          questionNumber={idx + 1}
          surveyNode={question?.question_id ? surveyLookup?.[question.question_id] : undefined}
        />
      ))}
    </div>
  );
}

export default function QuestionsSection({ questions, surveyLookup }: QuestionsSectionProps) {
  const hasQuestions = questions && questions.length > 0;

  return (
    <div className="bg-white rounded-lg shadow border border-gray-200">
      <SectionHeader />

      {hasQuestions ? (
        <QuestionsList questions={questions} surveyLookup={surveyLookup} />
      ) : (
        <NoResponsesWarning />
      )}
    </div>
  );
}
