import { EmptyState } from '@/components/ui';
import ConversationTurn from './ConversationTurn';
import type { TurnDetail } from '@/utils/types';

interface ConversationListProps {
  turns: TurnDetail[];
  isExpanded: boolean;
}

export default function ConversationList({ turns, isExpanded }: ConversationListProps) {
  if (!isExpanded) return null;

  if (turns.length === 0) {
    return (
      <div className="mt-4">
        <EmptyState message="No conversation turns recorded for this question." />
      </div>
    );
  }

  return (
    <div className="mt-6">
      {/* Transcription header */}
      <div className="flex items-center gap-2 mb-4 pb-2 border-b border-gray-200">
        <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        <span className="text-sm font-medium text-gray-500 uppercase tracking-wide">
          Transcription
        </span>
      </div>
      
      <div className="space-y-4">
        {turns.map((turn, idx) => (
          <ConversationTurn key={idx} turn={turn} />
        ))}
      </div>
    </div>
  );
}

