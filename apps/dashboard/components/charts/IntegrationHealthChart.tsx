'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { IntegrationSuccessRateRow } from '@/utils/types';
import EmptyChartState from './EmptyChartState';

export default function IntegrationHealthChart({ data }: { data: IntegrationSuccessRateRow[] }) {
  if (data.every((d) => d.total === 0)) return <EmptyChartState message="No integration calls in this period" />;

  const chartData = data.map((d) => ({
    name: d.integration,
    Success: d.success,
    Failure: d.failure,
    Other: Math.max(0, d.total - d.success - d.failure),
  }));

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="name" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
        <Tooltip />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="Success" fill="#22c55e" radius={[3, 3, 0, 0]} />
        <Bar dataKey="Failure" fill="#ef4444" radius={[3, 3, 0, 0]} />
        <Bar dataKey="Other" fill="#94a3b8" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
