import Link from 'next/link';

export default function ResponseDetailHeader() {
  return (
    <div className="bg-white border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-8 py-6">
        <Link href="/" className="text-brand hover:text-brand-dark mb-2 inline-block">
          ← Back to Dashboard
        </Link>
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Response Details</h1>
        <p className="text-gray-500 mt-1">Full conversation transcript and metadata</p>
      </div>
    </div>
  );
}

