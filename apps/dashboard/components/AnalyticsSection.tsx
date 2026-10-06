import { Suspense } from 'react';
import type { AnalyticsData } from '@/utils/types';
import WindowSelector from './WindowSelector';
import VolumeChart from './charts/VolumeChart';
import CompletionTrendChart from './charts/CompletionTrendChart';
import DropoffChart from './charts/DropoffChart';
import ConfidenceChart from './charts/ConfidenceChart';
import IntegrationHealthChart from './charts/IntegrationHealthChart';

interface AnalyticsSectionProps {
  data: AnalyticsData;
  currentWindow: string;
}

function ChartCard({
  title,
  children,
  className = '',
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`bg-white rounded-lg shadow border border-gray-200 p-4 sm:p-6 ${className}`}>
      <h3 className="text-sm font-semibold text-gray-700 mb-4">{title}</h3>
      {children}
    </div>
  );
}

export default function AnalyticsSection({ data, currentWindow }: AnalyticsSectionProps) {
  return (
    <div className="mb-8">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">Analytics</h2>
        <Suspense
          fallback={
            <div className="flex gap-1">
              {['7d', '14d', '30d', '90d'].map((l) => (
                <div key={l} className="px-3 py-1 text-sm rounded-md bg-gray-100 text-gray-400 border border-gray-200">
                  {l}
                </div>
              ))}
            </div>
          }
        >
          <WindowSelector currentWindow={currentWindow} />
        </Suspense>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
        <ChartCard title="Call Volume & Outcomes">
          <VolumeChart data={data.volumeByDay} />
        </ChartCard>

        <ChartCard title="Completion Rate Trend">
          <CompletionTrendChart data={data.completionRateTrend} />
        </ChartCard>

        <ChartCard title="Drop-off by Question">
          <DropoffChart data={data.dropoffByQuestion} />
        </ChartCard>

        <ChartCard title="Avg Confidence by Question">
          <ConfidenceChart data={data.avgConfidenceByQuestion} />
        </ChartCard>

        <ChartCard title="Integration Success Rates" className="md:col-span-2">
          <IntegrationHealthChart data={data.integrationSuccessRates} />
        </ChartCard>
      </div>
    </div>
  );
}
