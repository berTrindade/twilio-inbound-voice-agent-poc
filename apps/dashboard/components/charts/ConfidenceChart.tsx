'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import type { AvgConfidenceByQuestionRow } from '@/utils/types';
import EmptyChartState from './EmptyChartState';

function truncate(text: string, max = 35) {
  return text.length > max ? text.substring(0, max) + '…' : text;
}

// Confidence values are 0–1 (stored as fractions); display as 0–100%
function toPercent(value: number) {
  return value > 1 ? Math.round(value) : Math.round(value * 100);
}

function getColor(value: number) {
  const pct = toPercent(value);
  if (pct >= 80) return '#22c55e';
  if (pct >= 50) return '#eab308';
  return '#ef4444';
}

export default function ConfidenceChart({ data }: { data: AvgConfidenceByQuestionRow[] }) {
  if (data.length === 0) return <EmptyChartState message="No confidence data in this period" />;

  const chartData = data.map((d) => ({
    ...d,
    label: truncate(d.question_text || d.question_id),
    pct: toPercent(d.avg_confidence),
  }));

  const height = Math.max(200, chartData.length * 44);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
        <YAxis type="category" dataKey="label" tick={{ fontSize: 10 }} width={100} />
        <Tooltip formatter={(v) => [`${v}%`, 'Avg Confidence']} />
        <Bar dataKey="pct" name="Avg Confidence" radius={[0, 3, 3, 0]}>
          {chartData.map((entry, index) => (
            <Cell key={index} fill={getColor(entry.avg_confidence)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
