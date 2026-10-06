import {
  getResponses,
  getResponseStats,
  getIntegrationSuccessRates,
  getDemoCallCount,
} from '@/database/queries';
import type { IntegrationSuccessRateRow } from '@/utils/types';
import DashboardHeader from '@/components/DashboardHeader';
import PageHeader from '@/components/PageHeader';
import StatsCards from '@/components/StatsCards';
import DemoDataBanner from '@/components/DemoDataBanner';
import FilterSection from '@/components/FilterSection';
import ResponsesList from '@/components/ResponsesList';

interface SearchParams {
  page?: string;
  page_size?: string;
  status?: string;
  date_range?: string;
  duration?: string;
  sort_by?: string;
  sort_order?: string;
}

interface DashboardPageProps {
  searchParams: Promise<SearchParams>;
}

// null rather than 100 when nothing has run: a green "100% composite success"
// over zero integration calls is the one number on this page that can mislead.
function computeIntegrationHealth(rates: IntegrationSuccessRateRow[]): number | null {
  const relevant = rates.filter((r) => r.total > 0);
  if (relevant.length === 0) return null;
  const avg = relevant.reduce((sum, r) => sum + (r.success / r.total) * 100, 0) / relevant.length;
  return Math.round(avg * 100) / 100;
}

async function getPageData(params: SearchParams) {
  const page = parseInt(params.page || '1');
  const pageSize = parseInt(params.page_size || '25');

  let minDuration: number | undefined;
  let maxDuration: number | undefined;
  if (params.duration) {
    const [min, max] = params.duration.split('-');
    if (min) minDuration = parseInt(min);
    if (max) maxDuration = parseInt(max);
  }

  const [stats, responses, integrationRates, demoCallCount] = await Promise.all([
    getResponseStats(),
    getResponses({
      page,
      pageSize,
      status: params.status,
      dateRange: params.date_range,
      minDuration,
      maxDuration,
      sortBy: params.sort_by || 'started_at',
      sortOrder: (params.sort_order as 'asc' | 'desc') || 'desc',
    }),
    getIntegrationSuccessRates(7),
    getDemoCallCount(),
  ]);

  const integration_health = computeIntegrationHealth(integrationRates);

  return {
    stats: { ...stats, integration_health },
    responses,
    page,
    pageSize,
    demoCallCount,
  };
}

export default async function DashboardPage({ searchParams }: DashboardPageProps) {
  const params = await searchParams;
  const { stats, responses, page, pageSize, demoCallCount } =
    await getPageData(params);

  return (
    <div className="min-h-screen bg-gray-50">
      <DashboardHeader />

      <div className="max-w-7xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <DemoDataBanner count={demoCallCount} />

        <StatsCards stats={stats} />

        <PageHeader title="All Responses" />

        <FilterSection
          currentFilters={{
            status: params.status || '',
            date_range: params.date_range || '',
            duration: params.duration || '',
            sort_by: params.sort_by || 'started_at',
            sort_order: (params.sort_order as 'asc' | 'desc') || 'desc',
            page_size: pageSize.toString(),
          }}
        />

        <ResponsesList
          items={responses.items}
          total={responses.total}
          page={page}
          totalPages={responses.total_pages}
        />
      </div>
    </div>
  );
}
