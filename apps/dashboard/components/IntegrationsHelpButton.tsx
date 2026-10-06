'use client';

import { useRef } from 'react';

const SECTIONS = [
  {
    title: 'Submission',
    description: 'Records the collected survey answers to the local database when the call ends. The self-hosted build does not call any external service.',
    columns: ['response.success', 'response.answer_count', 'response.error', 'Badge'],
    rows: [
      ['true', 'present', 'null', '🟢 RECORDED'],
      ['true', '0', 'null', '🟢 RECORDED'],
      ['false', 'any', 'present', '🔴 FAILED + error text'],
      ['false', 'any', 'null', '🔴 FAILED'],
    ],
  },
];

export default function IntegrationsHelpButton() {
  const dialogRef = useRef<HTMLDialogElement>(null);

  return (
    <>
      <button
        onClick={() => dialogRef.current?.showModal()}
        className="cursor-pointer inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-white/80 hover:text-white hover:bg-white/10 border border-white/30 transition-colors"
        aria-label="Integration tiles reference"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.8}
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z" />
        </svg>
        Integration Reference
      </button>

      <dialog
        ref={dialogRef}
        className="rounded-xl shadow-2xl border border-gray-200 p-0 max-w-5xl w-full backdrop:bg-black/40"
        style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', margin: 0 }}
        onClick={(e) => {
          if (e.target === dialogRef.current) dialogRef.current?.close();
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 rounded-t-xl">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Integration Tiles — Reference</h2>
            <p className="text-sm text-gray-500 mt-0.5">All possible states and badge outcomes for each integration tile</p>
          </div>
          <button
            onClick={() => dialogRef.current?.close()}
            className="cursor-pointer text-gray-400 hover:text-gray-600 text-xl leading-none p-1"
            aria-label="Close"
          >
            &times;
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto max-h-[72vh] p-6 space-y-8">
          {SECTIONS.map((section) => (
            <div key={section.title}>
              <div className="mb-3">
                <h3 className="text-sm font-semibold text-gray-800">{section.title}</h3>
                <p className="text-xs text-gray-500 mt-0.5">{section.description}</p>
              </div>
              <div className="overflow-x-auto rounded-lg border border-gray-200">
                <table className="min-w-full text-xs divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      {section.columns.map((col) => (
                        <th
                          key={col}
                          className="px-3 py-2 text-left font-semibold text-gray-600 whitespace-nowrap font-mono"
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-100">
                    {section.rows.map((row, i) => (
                      <tr key={i} className={i % 2 === 0 ? '' : 'bg-gray-50/50'}>
                        {row.map((cell, j) => (
                          <td
                            key={j}
                            className={`px-3 py-2 text-gray-700 whitespace-nowrap ${
                              j === 0 ? 'font-mono font-medium text-brand' : ''
                            }`}
                          >
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}

          {/* Section visibility note */}
          <div>
            <div className="mb-3">
              <h3 className="text-sm font-semibold text-gray-800">Section Visibility</h3>
              <p className="text-xs text-gray-500 mt-0.5">When the Integrations section renders at all.</p>
            </div>
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="min-w-full text-xs divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 text-left font-semibold text-gray-600">Condition</th>
                    <th className="px-3 py-2 text-left font-semibold text-gray-600">Section renders?</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-100">
                  <tr>
                    <td className="px-3 py-2 font-mono font-medium text-brand">integrations === null</td>
                    <td className="px-3 py-2 text-red-600 font-medium">No</td>
                  </tr>
                  <tr className="bg-gray-50/50">
                    <td className="px-3 py-2 font-mono font-medium text-brand">local_submission absent / undefined</td>
                    <td className="px-3 py-2 text-red-600 font-medium">No</td>
                  </tr>
                  <tr>
                    <td className="px-3 py-2 font-mono font-medium text-brand">local_submission present</td>
                    <td className="px-3 py-2 text-green-700 font-medium">Yes</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </dialog>
    </>
  );
}
