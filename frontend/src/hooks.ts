import { useCallback, useEffect, useState } from "react";

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = [], refreshMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(fn, deps);
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await load());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [load]);
  useEffect(() => {
    reload();
    if (!refreshMs) return;
    const t = setInterval(reload, refreshMs);
    return () => clearInterval(t);
  }, [reload, refreshMs]);
  return { data, error, loading, reload };
}

export function useAction() {
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const run = useCallback(async (label: string, fn: () => Promise<unknown>, after?: () => void) => {
    setBusy(label);
    setMsg(null);
    try {
      await fn();
      setMsg({ text: `${label}: done`, ok: true });
      after?.();
    } catch (e) {
      setMsg({ text: `${label}: ${(e as Error).message}`, ok: false });
    } finally {
      setBusy(null);
    }
  }, []);
  return { busy, msg, run };
}
