interface ResponseStats {
  total_today: number;
  total_yesterday: number;
  total_this_week: number;
  total_prev_week: number;
  completion_rate: number;
  completion_rate_this_week: number;
  completion_rate_prev_week: number;
  average_duration_seconds: number | null;
  avg_duration_prev_week: number | null;
  active_calls: number;
  escalation_rate: number;
  integration_health: number | null;
}

interface StatsCardsProps {
  stats: ResponseStats;
}

function TrendBadge({
  current,
  previous,
  invert = false,
}: {
  current: number;
  previous: number;
  invert?: boolean;
}) {
  if (previous === 0 || current === 0) return null;
  const delta = ((current - previous) / previous) * 100;
  const isPositive = delta > 0;
  const isGood = invert ? !isPositive : isPositive;
  return (
    <span className={`inline-flex items-center text-xs font-medium ml-1 ${isGood ? 'text-green-600' : 'text-red-500'}`}>
      {isPositive ? '↑' : '↓'} {Math.abs(Math.round(delta))}%
    </span>
  );
}

export default function StatsCards({ stats }: StatsCardsProps) {
  const formatDuration = (seconds: number | null) => {
    if (seconds === null) return 'N/A';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}m ${secs}s`;
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3 sm:gap-4 mb-6">
      <div className="bg-white rounded-lg shadow p-4 sm:p-6 border border-gray-200">
        <div className="text-sm font-medium text-gray-500 mb-1">Today</div>
        <div className="flex items-baseline">
          <div className="text-2xl sm:text-3xl font-bold text-gray-900">{stats.total_today}</div>
          <TrendBadge current={stats.total_today} previous={stats.total_yesterday} />
        </div>
        <div className="text-xs text-gray-400 mt-1">vs yesterday: {stats.total_yesterday}</div>
      </div>

      <div className="bg-white rounded-lg shadow p-4 sm:p-6 border border-gray-200">
        <div className="text-sm font-medium text-gray-500 mb-1">This Week</div>
        <div className="flex items-baseline">
          <div className="text-2xl sm:text-3xl font-bold text-gray-900">{stats.total_this_week}</div>
          <TrendBadge current={stats.total_this_week} previous={stats.total_prev_week} />
        </div>
        <div className="text-xs text-gray-400 mt-1">vs prior week: {stats.total_prev_week}</div>
      </div>

      <div className="bg-white rounded-lg shadow p-4 sm:p-6 border border-gray-200">
        <div className="text-sm font-medium text-gray-500 mb-1">Completion Rate</div>
        <div className="flex items-baseline">
          <div className="text-2xl sm:text-3xl font-bold text-gray-900">{stats.completion_rate}%</div>
          <TrendBadge current={stats.completion_rate_this_week} previous={stats.completion_rate_prev_week} />
        </div>
        <div className="text-xs text-gray-400 mt-1">this week: {stats.completion_rate_this_week}%</div>
      </div>

      <div className="bg-white rounded-lg shadow p-4 sm:p-6 border border-gray-200">
        <div className="text-sm font-medium text-gray-500 mb-1">Avg Duration</div>
        <div className="flex items-baseline">
          <div className="text-2xl sm:text-3xl font-bold text-gray-900">
            {formatDuration(stats.average_duration_seconds)}
          </div>
          {stats.average_duration_seconds !== null && stats.avg_duration_prev_week !== null && (
            <TrendBadge
              current={stats.average_duration_seconds}
              previous={stats.avg_duration_prev_week}
              invert={true}
            />
          )}
        </div>
        <div className="text-xs text-gray-400 mt-1">
          {stats.active_calls} active {stats.active_calls === 1 ? 'call' : 'calls'}
        </div>
      </div>

      <div className="bg-white rounded-lg shadow p-4 sm:p-6 border border-gray-200">
        <div className="text-sm font-medium text-gray-500 mb-1">Escalation Rate</div>
        <div className="text-2xl sm:text-3xl font-bold text-gray-900">
          {stats.escalation_rate !== null ? `${stats.escalation_rate}%` : 'N/A'}
        </div>
        <div className="text-xs text-gray-400 mt-1">calls escalated</div>
      </div>

      <div className="bg-white rounded-lg shadow p-4 sm:p-6 border border-gray-200">
        <div className="text-sm font-medium text-gray-500 mb-1">Integration Health</div>
        <div className={`text-2xl sm:text-3xl font-bold ${
          stats.integration_health === null ? 'text-gray-900' :
          stats.integration_health >= 80 ? 'text-green-600' :
          stats.integration_health >= 50 ? 'text-yellow-500' : 'text-red-500'
        }`}>
          {stats.integration_health === null ? 'N/A' : `${stats.integration_health}%`}
        </div>
        <div className="text-xs text-gray-400 mt-1">
          {stats.integration_health === null ? 'no integration calls yet' : 'composite success'}
        </div>
      </div>
    </div>
  );
}
