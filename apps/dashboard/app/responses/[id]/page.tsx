import { getResponseById } from '@/database/queries';
import { notFound } from 'next/navigation';
import ResponseDetailHeader from '@/components/ResponseDetailHeader';
import CallOverview from '@/components/CallOverview';
import IntegrationsSection from '@/components/IntegrationsSection';
import QuestionsSection from '@/components/QuestionsSection';
import { ScrollToTop } from '@/components/ui';

interface PageProps {
  params: Promise<{
    id: string;
  }>;
}

export default async function ResponseDetailPage({ params }: PageProps) {
  const { id } = await params;
  
  const response = await getResponseById(id);

  if (!response) {
    notFound();
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <ResponseDetailHeader />

      <div className="max-w-7xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <CallOverview
          participantPhone={response.participant_phone}
          status={response.status}
          durationSeconds={response.duration_seconds}
          startedAt={response.started_at}
          completedAt={response.completed_at}
          completionReason={response.completion_reason}
          callSid={response.call_sid}
          sessionId={response.session_id}
          correlationId={response.correlation_id}
          totalQuestions={response.total_questions}
          totalTurns={response.total_turns}
          escalationsCount={response.escalations_count}
          interruptionsCount={response.interruptions_count}
          nodesVisited={response.nodes_visited}
        />

        <IntegrationsSection integrations={response.integrations} />

        <QuestionsSection questions={response.questions} surveyLookup={response.surveyLookup} />
      </div>

      <ScrollToTop />
    </div>
  );
}
