'use client';

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts';
import type { CompletionRateTrendRow } from '@/utils/types';
import EmptyChartState from './EmptyChartState';

export default function CompletionTrendChart({ data }: { data: CompletionRateTrendRow[] }) {
  if (data.length === 0) return <EmptyChartState />;

  const avgRate =
    data.length > 0
      ? Math.round((data.reduce((sum, d) => sum + d.rate, 0) / data.length) * 100) / 100
      : 0;

  return (
    <ResponsiveContainer width="100%" height={250}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
        <Tooltip formatter={(v) => [`${v}%`, 'Completion Rate']} />
        <ReferenceLine
          y={avgRate}
          stroke="#94a3b8"
          strokeDasharray="4 4"
          label={{ value: `Avg ${avgRate}%`, position: 'insideTopRight', fontSize: 10, fill: '#94a3b8' }}
        />
        <Line
          type="monotone"
          dataKey="rate"
          stroke="#1b6df1"
          strokeWidth={2}
          dot={{ r: 4 }}
          name="Completion Rate"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
