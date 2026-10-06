import Link from 'next/link';

interface ResponseListItem {
  id: string;
  participant_phone: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  questions_answered: number;
}

interface ResponsesTableProps {
  responses: ResponseListItem[];
}

export default function ResponsesTable({ responses }: ResponsesTableProps) {
  const formatDate = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatDuration = (seconds: number | null) => {
    if (seconds === null) return '-';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getStatusBadge = (status: string) => {
    const baseClasses = 'px-2 py-1 rounded-full text-xs font-medium';
    
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

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'in_progress':
        return 'In Progress';
      case 'completed':
        return 'Completed';
      case 'abandoned':
        return 'Abandoned';
      default:
        return status;
    }
  };

  if (responses.length === 0) {
    return (
      <div
        data-empty="responses"
        className="bg-white rounded-lg shadow border border-gray-200 p-8 text-center"
      >
        <p className="text-gray-900 font-medium">No calls yet</p>
        <p className="text-gray-500 text-sm mt-1">
          Every panel here fills in from real calls. Have one and it shows up.
        </p>
        <Link
          href="/chat"
          className="inline-block mt-4 bg-brand text-white py-2 px-4 rounded-lg hover:bg-brand-dark transition-colors text-sm font-medium"
        >
          Talk to the agent
        </Link>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow overflow-x-auto border border-gray-200">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Participant
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Status
            </th>
            <th className="hidden sm:table-cell px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Started
            </th>
            <th className="hidden sm:table-cell px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Duration
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Questions
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {responses.map((response) => (
            <tr key={response.id} className="hover:bg-gray-50">
              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                {response.participant_phone}
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <span className={getStatusBadge(response.status)}>
                  {getStatusLabel(response.status)}
                </span>
              </td>
              <td className="hidden sm:table-cell px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {formatDate(response.started_at)}
              </td>
              <td className="hidden sm:table-cell px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {formatDuration(response.duration_seconds)}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {response.questions_answered}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm">
                <Link
                  href={`/responses/${response.id}`}
                  className="text-brand hover:text-brand-dark font-medium"
                >
                  View Details
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
