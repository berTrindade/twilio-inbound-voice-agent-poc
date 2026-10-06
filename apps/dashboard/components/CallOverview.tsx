import CopyButton from './CopyButton';

interface CallOverviewProps {
  participantPhone: string;
  status: string;
  durationSeconds: number | null;
  startedAt: string;
  completedAt: string | null;
  completionReason: string | null;
  callSid: string | null;
  sessionId: string | null;
  correlationId: string | null;
  totalQuestions: number;
  totalTurns: number;
  escalationsCount: number;
  interruptionsCount: number;
  nodesVisited: string[];
}

function CopyableDetail({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <span className="text-gray-500">{label}:</span>
      {value ? (
        <span className="ml-2 inline-flex items-center gap-1 align-middle">
          <span className="font-mono text-gray-900 break-all">{value}</span>
          <CopyButton value={value} label={`Copy ${label}`} />
        </span>
      ) : (
        <span className="ml-2 font-mono text-gray-900">N/A</span>
      )}
    </div>
  );
}

export default function CallOverview({
  participantPhone,
  status,
  durationSeconds,
  startedAt,
  completedAt,
  completionReason,
  callSid,
  sessionId,
  correlationId,
  totalQuestions,
  totalTurns,
  escalationsCount,
  interruptionsCount,
  nodesVisited,
}: CallOverviewProps) {
  const formatDate = (isoString: string | null) => {
    if (!isoString) return 'N/A';
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const formatDuration = (seconds: number | null) => {
    if (seconds === null) return 'N/A';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}m ${secs}s`;
  };

  const getStatusBadge = (status: string) => {
    const baseClasses = 'px-3 py-1 rounded-full text-sm font-medium';
    
    switch (status) {
      case 'completed':
        return `${baseClasses} bg-green-100 text-green-800`;
      case 'abandoned':
        return `${baseClasses} bg-red-100 text-red-800`;
      case 'in_progress':
        return `${baseClasses} bg-blue-100 text-blue-800`;
      default:
        return `${baseClasses} bg-gray-100 text-gray-800`;
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-4 sm:p-6 mb-6 border border-gray-200">
      <h2 className="text-xl font-semibold text-gray-900 mb-4">Call Overview</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div>
          <div className="text-sm font-medium text-gray-500">Participant</div>
          <div className="text-lg font-mono text-gray-900 mt-1">{participantPhone}</div>
        </div>

        <div>
          <div className="text-sm font-medium text-gray-500">Status</div>
          <div className="mt-1">
            <span className={getStatusBadge(status)}>
              {status.replace('_', ' ').toUpperCase()}
            </span>
          </div>
        </div>

        <div>
          <div className="text-sm font-medium text-gray-500">Duration</div>
          <div className="text-lg text-gray-900 mt-1">{formatDuration(durationSeconds)}</div>
        </div>

        <div>
          <div className="text-sm font-medium text-gray-500">Started</div>
          <div className="text-sm text-gray-900 mt-1">{formatDate(startedAt)}</div>
        </div>

        <div>
          <div className="text-sm font-medium text-gray-500">Completed</div>
          <div className="text-sm text-gray-900 mt-1">{formatDate(completedAt)}</div>
        </div>

        <div>
          <div className="text-sm font-medium text-gray-500">Completion Reason</div>
          <div className="text-sm text-gray-900 mt-1">{completionReason || 'N/A'}</div>
        </div>
      </div>

      <div className="mt-6 pt-6 border-t border-gray-200">
        <h3 className="text-sm font-medium text-gray-500 mb-3">Technical Details</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
          <CopyableDetail label="Call SID" value={callSid} />
          <div>
            <span className="text-gray-500">Session ID:</span>
            <span className="ml-2 font-mono text-gray-900 break-all">{sessionId || 'N/A'}</span>
          </div>
          <CopyableDetail label="Correlation ID" value={correlationId} />
        </div>
      </div>

      <div className="mt-6 pt-6 border-t border-gray-200">
        <h3 className="text-sm font-medium text-gray-500 mb-3">Summary Metrics</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-gray-50 rounded p-3 text-center">
            <div className="text-xl sm:text-2xl font-bold text-gray-900">{totalQuestions}</div>
            <div className="text-xs text-gray-500 mt-1">Questions</div>
          </div>
          <div className="bg-gray-50 rounded p-3 text-center">
            <div className="text-xl sm:text-2xl font-bold text-gray-900">{totalTurns}</div>
            <div className="text-xs text-gray-500 mt-1">Total Turns</div>
          </div>
          <div className="bg-gray-50 rounded p-3 text-center">
            <div className="text-xl sm:text-2xl font-bold text-gray-900">{escalationsCount}</div>
            <div className="text-xs text-gray-500 mt-1">Escalations</div>
          </div>
          <div className="bg-gray-50 rounded p-3 text-center">
            <div className="text-xl sm:text-2xl font-bold text-gray-900">{interruptionsCount}</div>
            <div className="text-xs text-gray-500 mt-1">Interruptions</div>
          </div>
        </div>
      </div>

      {nodesVisited.length > 0 && (
        <div className="mt-6 pt-6 border-t border-gray-200">
          <h3 className="text-sm font-medium text-gray-500 mb-3">Survey Flow (Nodes Visited)</h3>
          <div className="flex flex-wrap gap-2">
            {nodesVisited.map((node, idx) => (
              <a
                key={idx}
                href={`#question-${node}`}
                className="px-3 py-1 bg-brand/10 text-brand rounded-full text-xs font-medium hover:bg-brand/15 transition-colors cursor-pointer"
              >
                {node}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

