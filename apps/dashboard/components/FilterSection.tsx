'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useTransition } from 'react';

interface FilterSectionProps {
  currentFilters: {
    status: string;
    date_range: string;
    duration: string;
    sort_by: string;
    sort_order: 'asc' | 'desc';
    page_size: string;
  };
}

export default function FilterSection({ currentFilters }: FilterSectionProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const updateFilter = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams);
    
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    
    // Reset to page 1 when filters change
    if (key !== 'page') {
      params.set('page', '1');
    }

    startTransition(() => {
      router.push(`/?${params.toString()}`);
    });
  };

  return (
    <div className="bg-white rounded-lg shadow p-4 mb-6 border border-gray-200">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Status
          </label>
          <select
            value={currentFilters.status}
            onChange={(e) => updateFilter('status', e.target.value)}
            disabled={isPending}
            className="w-full rounded-md border-gray-300 border p-2 text-sm focus:border-brand focus:ring-brand disabled:opacity-50"
          >
            <option value="">All</option>
            <option value="completed">Completed</option>
            <option value="abandoned">Abandoned</option>
            <option value="in_progress">In Progress</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Date Range
          </label>
          <select
            value={currentFilters.date_range}
            onChange={(e) => updateFilter('date_range', e.target.value)}
            disabled={isPending}
            className="w-full rounded-md border-gray-300 border p-2 text-sm focus:border-brand focus:ring-brand disabled:opacity-50"
          >
            <option value="">All Time</option>
            <option value="24h">Last 24 Hours</option>
            <option value="7d">Last 7 Days</option>
            <option value="30d">Last 30 Days</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Duration
          </label>
          <select
            value={currentFilters.duration}
            onChange={(e) => updateFilter('duration', e.target.value)}
            disabled={isPending}
            className="w-full rounded-md border-gray-300 border p-2 text-sm focus:border-brand focus:ring-brand disabled:opacity-50"
          >
            <option value="">All</option>
            <option value="0-120">Under 2 min</option>
            <option value="120-300">2-5 min</option>
            <option value="300-">Over 5 min</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Sort By
          </label>
          <select
            value={currentFilters.sort_by}
            onChange={(e) => updateFilter('sort_by', e.target.value)}
            disabled={isPending}
            className="w-full rounded-md border-gray-300 border p-2 text-sm focus:border-brand focus:ring-brand disabled:opacity-50"
          >
            <option value="started_at">Start Time</option>
            <option value="duration">Duration</option>
            <option value="status">Status</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Order
          </label>
          <select
            value={currentFilters.sort_order}
            onChange={(e) => updateFilter('sort_order', e.target.value)}
            disabled={isPending}
            className="w-full rounded-md border-gray-300 border p-2 text-sm focus:border-brand focus:ring-brand disabled:opacity-50"
          >
            <option value="desc">Newest First</option>
            <option value="asc">Oldest First</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Per Page
          </label>
          <select
            value={currentFilters.page_size}
            onChange={(e) => updateFilter('page_size', e.target.value)}
            disabled={isPending}
            className="w-full rounded-md border-gray-300 border p-2 text-sm focus:border-brand focus:ring-brand disabled:opacity-50"
          >
            <option value="25">25</option>
            <option value="50">50</option>
            <option value="100">100</option>
          </select>
        </div>
      </div>

      {isPending && (
        <div className="mt-3 flex items-center gap-2 text-sm text-gray-500">
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-brand"></div>
          Loading...
        </div>
      )}
    </div>
  );
}

