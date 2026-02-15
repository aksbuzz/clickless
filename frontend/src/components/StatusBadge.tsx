import type { InstanceStatus } from '../types';

const styles: Record<InstanceStatus, string> = {
  pending: 'bg-gray-100 text-gray-700',
  running: 'bg-blue-100 text-blue-700 animate-pulse',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  cancelled: 'bg-yellow-100 text-yellow-700',
};

export function StatusBadge({ status }: { status: string }) {
  const s = status as InstanceStatus;
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${styles[s] ?? 'bg-gray-100 text-gray-700'}`}>
      {status}
    </span>
  );
}
