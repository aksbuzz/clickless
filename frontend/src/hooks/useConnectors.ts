import { useState, useEffect } from 'react';
import { api } from '../api';
import type { Connector } from '../types';

export function useConnectors() {
  const [connectors, setConnectors] = useState<Connector[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.getConnectors()
      .then((data) => {
        if (!cancelled) {
          setConnectors(data);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load connectors');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  return { connectors, loading, error };
}
