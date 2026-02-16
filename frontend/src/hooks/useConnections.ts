import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import type { Connection } from '../types';

export function useConnections(connectorId?: string) {
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refetchTrigger, setRefetchTrigger] = useState(0);

  const load = useCallback(() => {
    setRefetchTrigger((prev) => prev + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;

    api.getConnections(connectorId)
      .then((data) => {
        if (!cancelled) {
          setConnections(data);
          setError(null);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load connections');
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [connectorId, refetchTrigger]);

  return { connections, loading, error, refetch: load };
}
