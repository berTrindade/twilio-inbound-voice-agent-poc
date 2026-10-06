import { getAnalyticsData, getDemoCallCount } from '@/database/queries';
import DashboardHeader from '@/components/DashboardHeader';
import AnalyticsSection from '@/components/AnalyticsSection';
import DemoDataBanner from '@/components/DemoDataBanner';

interface SearchParams {
  window?: string;
}

interface AnalyticsPageProps {
  searchParams: Promise<SearchParams>;
}

export default async function AnalyticsPage({ searchParams }: AnalyticsPageProps) {
  const params = await searchParams;
  const windowDays = Math.max(1, Math.min(90, parseInt(params.window || '7') || 7));
  const [analyticsData, demoCallCount] = await Promise.all([
    getAnalyticsData(windowDays),
    getDemoCallCount(),
  ]);

  return (
    <div className="min-h-screen bg-gray-50">
      <DashboardHeader />

      <div className="max-w-7xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <DemoDataBanner count={demoCallCount} />

        <AnalyticsSection data={analyticsData} currentWindow={String(windowDays)} />
      </div>
    </div>
  );
}
