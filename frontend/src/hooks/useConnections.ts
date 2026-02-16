import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import type { Connection } from '../types';

export function useConnections(connectorId?: string) {
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    api.getConnections(connectorId)
      .then((data) => {
        setConnections(data);
        setError(null);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Failed to load connections');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [connectorId]);

  useEffect(() => {
    load();
  }, [load]);

  return { connections, loading, error, refetch: load };
}
