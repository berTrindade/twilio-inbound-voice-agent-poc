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
import type { VolumeByDayRow } from '@/utils/types';
import EmptyChartState from './EmptyChartState';

export default function VolumeChart({ data }: { data: VolumeByDayRow[] }) {
  if (data.length === 0) return <EmptyChartState />;

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="completed" stackId="a" fill="#22c55e" name="Completed" />
        <Bar dataKey="abandoned" stackId="a" fill="#f97316" name="Abandoned" />
        <Bar dataKey="in_progress" stackId="a" fill="#1b6df1" name="In Progress" />
      </BarChart>
    </ResponsiveContainer>
  );
}
