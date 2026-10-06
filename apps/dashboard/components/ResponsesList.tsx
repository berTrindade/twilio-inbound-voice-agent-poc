import ResponsesTable from './ResponsesTable';
import PaginationInfo from './PaginationInfo';
import PaginationControls from './PaginationControls';

interface ResponseListItem {
  id: string;
  participant_phone: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  questions_answered: number;
}

interface ResponsesListProps {
  items: ResponseListItem[];
  total: number;
  page: number;
  totalPages: number;
}

export default function ResponsesList({
  items,
  total,
  page,
  totalPages,
}: ResponsesListProps) {
  return (
    <div>
      <ResponsesTable responses={items} />
      <PaginationControls currentPage={page} totalPages={totalPages} />
      <PaginationInfo
        currentItems={items.length}
        totalItems={total}
        currentPage={page}
        totalPages={totalPages}
      />
    </div>
  );
}

