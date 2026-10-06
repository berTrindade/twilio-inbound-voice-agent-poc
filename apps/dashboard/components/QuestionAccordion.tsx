'use client';

import { useState } from 'react';
import { QuestionHeader, ConversationList } from '@/components/questions';
import type { QuestionDetail, SurveyNode } from '@/utils/types';

interface QuestionAccordionProps {
  question: QuestionDetail;
  questionNumber: number;
  surveyNode?: SurveyNode;
}

export default function QuestionAccordion({
  question,
  questionNumber,
  surveyNode,
}: QuestionAccordionProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  const turns = question?.turns || [];

  return (
    <div id={question?.question_id ? `question-${question.question_id}` : undefined} className="p-6 scroll-mt-4">
      <QuestionHeader
        question={question}
        questionNumber={questionNumber}
        surveyNode={surveyNode}
        isExpanded={isExpanded}
        onToggle={() => setIsExpanded(!isExpanded)}
      />

      <ConversationList turns={turns} isExpanded={isExpanded} />
    </div>
  );
}
