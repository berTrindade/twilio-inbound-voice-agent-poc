'use client';

import { useEffect } from 'react';
import Link from 'next/link';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Dashboard error:', error);
  }, [error]);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
      <div className="max-w-md w-full">
        <div className="bg-white rounded-lg shadow-lg p-8 border border-red-200">
          <div className="flex items-center justify-center w-12 h-12 mx-auto bg-red-100 rounded-full mb-4">
            <svg
              className="w-6 h-6 text-red-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
          
          <h2 className="text-2xl font-bold text-gray-900 text-center mb-2">
            Something went wrong
          </h2>
          
          <p className="text-gray-600 text-center mb-6">
            This page reads Postgres directly, so it is usually the database rather than the
            agent. Most likely:
          </p>

          <ul className="text-sm text-gray-600 space-y-2 mb-6 list-disc list-inside">
            <li>The migrations have not finished yet, so the tables do not exist</li>
            <li>Postgres is still starting, or has stopped</li>
            <li>DATABASE_URL points somewhere else</li>
          </ul>

          <div className="bg-gray-50 rounded p-4 mb-6">
            <p className="text-xs font-mono text-gray-700 break-all">
              {error.message}
            </p>
          </div>

          <div className="space-y-3">
            <button
              onClick={reset}
              className="w-full bg-brand text-white py-3 px-4 rounded-lg hover:bg-brand-dark transition-colors font-medium"
            >
              Try Again
            </button>
            
            <Link
              href="/"
              className="block w-full text-center bg-gray-100 text-gray-700 py-3 px-4 rounded-lg hover:bg-gray-200 transition-colors font-medium"
            >
              Go to Home
            </Link>
          </div>

          <div className="mt-6 pt-6 border-t border-gray-200">
            <p className="text-xs text-gray-500 text-center">
              The migrations run on the call runner&apos;s first boot. To watch them:
            </p>
            <p className="text-xs font-mono text-gray-700 text-center mt-1">make logs</p>
          </div>
        </div>
      </div>
    </div>
  );
}

