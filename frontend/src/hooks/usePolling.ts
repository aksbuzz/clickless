import { useState, useEffect, useCallback } from 'react';

export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number = 5000,
  enabled: boolean = true,
): { data: T | null; loading: boolean; error: string | null; refresh: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await fetcher();
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [fetcher]);

  useEffect(() => {
    load();
    if (!enabled) return;
    const id = setInterval(load, intervalMs);
    return () => clearInterval(id);
  }, [load, intervalMs, enabled]);

  return { data, loading, error, refresh: load };
}
