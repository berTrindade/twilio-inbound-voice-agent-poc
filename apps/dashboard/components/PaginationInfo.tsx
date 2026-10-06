interface PaginationInfoProps {
  currentItems: number;
  totalItems: number;
  currentPage: number;
  totalPages: number;
}

export default function PaginationInfo({
  currentItems,
  totalItems,
  currentPage,
  totalPages,
}: PaginationInfoProps) {
  if (totalItems === 0) return null;

  return (
    <div className="mt-4 text-center text-sm text-gray-500">
      Showing {currentItems} of {totalItems} responses
      {totalPages > 1 && ` (Page ${currentPage} of ${totalPages})`}
    </div>
  );
}

