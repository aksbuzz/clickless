const COLORS: Record<string, string> = {
  http: 'bg-blue-100 text-blue-700',
  webhook: 'bg-indigo-100 text-indigo-700',
  internal: 'bg-gray-100 text-gray-700',
  flow_control: 'bg-purple-100 text-purple-700',
  slack: 'bg-pink-100 text-pink-700',
  github: 'bg-gray-800 text-white',
  trello: 'bg-sky-100 text-sky-700',
  postgresql: 'bg-blue-100 text-blue-800',
  python: 'bg-yellow-100 text-yellow-700',
};

export function ConnectorIcon({ connectorId }: { connectorId: string }) {
  const colors = COLORS[connectorId] ?? 'bg-gray-100 text-gray-600';
  const label = connectorId.slice(0, 2).toUpperCase();

  return (
    <span className={`inline-flex items-center justify-center w-8 h-8 rounded text-xs font-bold ${colors}`}>
      {label}
    </span>
  );
}
