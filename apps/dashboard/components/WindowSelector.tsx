'use client';

import { useRouter, useSearchParams, usePathname } from 'next/navigation';

const WINDOWS = [
  { value: '7', label: '7d' },
  { value: '14', label: '14d' },
  { value: '30', label: '30d' },
  { value: '90', label: '90d' },
];

export default function WindowSelector({ currentWindow }: { currentWindow: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function handleChange(value: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set('window', value);
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <div className="flex gap-1">
      {WINDOWS.map((w) => (
        <button
          key={w.value}
          onClick={() => handleChange(w.value)}
          className={`px-3 py-1 text-sm rounded-md transition-colors ${
            currentWindow === w.value
              ? 'bg-brand text-white'
              : 'bg-white text-gray-600 border border-gray-300 hover:bg-gray-50'
          }`}
        >
          {w.label}
        </button>
      ))}
    </div>
  );
}
