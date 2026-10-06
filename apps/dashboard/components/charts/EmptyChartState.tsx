export default function EmptyChartState({ message = 'No data for this period' }: { message?: string }) {
  return (
    <div className="flex items-center justify-center h-48 text-sm text-gray-400">
      {message}
    </div>
  );
}
