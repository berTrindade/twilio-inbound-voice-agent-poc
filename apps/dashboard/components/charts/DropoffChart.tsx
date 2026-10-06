'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { DropoffByQuestionRow } from '@/utils/types';
import EmptyChartState from './EmptyChartState';

function truncate(text: string, max = 35) {
  return text.length > max ? text.substring(0, max) + '…' : text;
}

export default function DropoffChart({ data }: { data: DropoffByQuestionRow[] }) {
  if (data.length === 0) return <EmptyChartState message="No abandoned calls in this period" />;

  const chartData = data.map((d) => ({
    ...d,
    label: truncate(d.question_text || d.question_id),
  }));

  const height = Math.max(200, chartData.length * 44);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
        <YAxis type="category" dataKey="label" tick={{ fontSize: 10 }} width={100} />
        <Tooltip
          formatter={(v) => [v, 'Abandonments']}
          labelFormatter={(label) => `Question: ${label}`}
        />
        <Bar dataKey="abandonment_count" fill="#f97316" name="Abandonments" radius={[0, 3, 3, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
