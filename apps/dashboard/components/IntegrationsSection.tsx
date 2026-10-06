'use client';

import { useRef, useState } from 'react';
import type {
  IntegrationsData,
  LocalSubmissionIntegration,
} from '@/utils/types';

interface IntegrationsSectionProps {
  integrations: IntegrationsData | null;
}

// ─── Status badge helpers ──────────────────────────────────────────────────

function BoolBadge({ value, trueLabel = 'YES', falseLabel = 'NO' }: { value: boolean; trueLabel?: string; falseLabel?: string }) {
  return (
    <span
      className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
        value ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
      }`}
    >
      {value ? trueLabel : falseLabel}
    </span>
  );
}

// ─── Modal ────────────────────────────────────────────────────────────────

interface ModalResponseData {
  success?: boolean;
  status?: string;
  status_code?: number;
  response_body?: string;
  [key: string]: unknown;
}

interface ModalProps {
  title: string;
  dataSent: object;
  dialogRef: React.RefObject<HTMLDialogElement | null>;
  responseData?: ModalResponseData;
}

function formatResponseBody(body: string): string {
  try {
    return JSON.stringify(JSON.parse(body), null, 2);
  } catch {
    return body;
  }
}

function IntegrationModal({ title, dataSent, dialogRef, responseData }: ModalProps) {
  const [tab, setTab] = useState<'data' | 'response'>('data');
  const [responseCopied, setResponseCopied] = useState(false);

  const failed =
    responseData?.success === false ||
    responseData?.status === 'ERROR' ||
    (typeof responseData?.status_code === 'number' && responseData.status_code >= 400);
  const hasResponseDetails =
    !!responseData &&
    failed &&
    (responseData.status_code !== undefined || responseData.response_body !== undefined);

  const activeTab = tab === 'response' && !hasResponseDetails ? 'data' : tab;

  const handleCopyResponse = async () => {
    if (responseData?.response_body === undefined) return;
    try {
      await navigator.clipboard.writeText(formatResponseBody(responseData.response_body));
      setResponseCopied(true);
      setTimeout(() => setResponseCopied(false), 2000);
    } catch {
    }
  };

  const closeModal = () => {
    dialogRef.current?.close();
    setTab('data');
  };

  return (
    <dialog
      ref={dialogRef}
      className="rounded-xl shadow-2xl border border-gray-200 p-0 max-w-3xl w-[calc(100%-2rem)] sm:w-full backdrop:bg-black/40"
      style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', margin: 0 }}
      onClick={(e) => {
        if (e.target === dialogRef.current) closeModal();
      }}
    >
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
        <button
          onClick={closeModal}
          className="cursor-pointer text-gray-400 hover:text-gray-600 text-xl leading-none"
          aria-label="Close"
        >
          &times;
        </button>
      </div>

      <div className="flex border-b border-gray-200 px-6">
        <button
          onClick={() => setTab('data')}
          className={`cursor-pointer py-3 mr-4 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'data'
              ? 'border-brand text-brand'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Collected Answers
        </button>
        {hasResponseDetails && (
          <button
            onClick={() => setTab('response')}
            className={`cursor-pointer py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'response'
                ? 'border-red-500 text-red-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Response
          </button>
        )}
      </div>

      <div className="p-6 max-h-[60vh] overflow-auto">
        {activeTab === 'data' && (
          <pre className="text-xs font-mono bg-gray-50 rounded-lg p-4 text-gray-800 whitespace-pre-wrap">
            {JSON.stringify(dataSent, null, 2)}
          </pre>
        )}
        {activeTab === 'response' && responseData && (
          <div className="flex flex-col gap-3">
            {responseData.status_code !== undefined && (
              <div className="text-sm font-semibold text-gray-900">
                Status:{' '}
                <span className="text-red-600">{responseData.status_code}</span>
              </div>
            )}
            {responseData.response_body !== undefined ? (
              <div className="relative">
                <button
                  onClick={handleCopyResponse}
                  className="cursor-pointer absolute top-2 right-2 px-3 py-1 text-xs bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors"
                >
                  {responseCopied ? 'Copied!' : 'Copy'}
                </button>
                <pre className="text-xs font-mono bg-gray-50 rounded-lg p-4 pr-20 text-gray-800 whitespace-pre-wrap">
                  {formatResponseBody(responseData.response_body)}
                </pre>
              </div>
            ) : (
              <div className="text-xs text-gray-400 italic">No response body</div>
            )}
          </div>
        )}
      </div>
    </dialog>
  );
}

// ─── Integration cards ───────────────────────────────────────────────────

function SubmissionCard({ data }: { data: LocalSubmissionIntegration }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const answers = data.response.answers ?? {};
  const answerCount = data.response.answer_count ?? Object.keys(answers).length;
  return (
    <>
      <div className="bg-white border border-gray-200 rounded-lg p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-gray-700">Submission</span>
          <BoolBadge value={data.response.success} trueLabel="RECORDED" falseLabel="FAILED" />
        </div>
        {data.timestamp && (
          <div className="text-xs text-gray-500">{new Date(data.timestamp).toLocaleString()}</div>
        )}
        <div className="text-xs text-gray-600">
          {answerCount} answer{answerCount === 1 ? '' : 's'} recorded locally
        </div>
        {data.response.error && (
          <div className="text-xs text-red-600 truncate">{data.response.error}</div>
        )}
        <button
          onClick={() => dialogRef.current?.showModal()}
          className="cursor-pointer mt-auto text-xs text-brand hover:underline text-left"
        >
          View Details
        </button>
      </div>

      <IntegrationModal
        title="Submission"
        dataSent={answers}
        dialogRef={dialogRef}
        responseData={data.response}
      />
    </>
  );
}

// ─── Section ──────────────────────────────────────────────────────────────

export default function IntegrationsSection({ integrations }: IntegrationsSectionProps) {
  if (!integrations) {
    return null;
  }

  if (!integrations.local_submission) {
    return null;
  }

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6 border border-gray-200">
      <h2 className="text-xl font-semibold text-gray-900 mb-4">Integrations</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <SubmissionCard data={integrations.local_submission} />
      </div>
    </div>
  );
}
