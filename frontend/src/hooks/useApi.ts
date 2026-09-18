import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/services/api";

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/** Run an async loader on mount, with a manual refresh. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> & {
  refresh: () => void;
} {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: true, error: null });
  const [nonce, setNonce] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    let cancelled = false;
    setState((previous) => ({ ...previous, loading: true, error: null }));

    loaderRef
      .current()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const message =
          error instanceof ApiError ? error.message : "Something went wrong loading this view.";
        setState({ data: null, loading: false, error: message });
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const refresh = useCallback(() => setNonce((value) => value + 1), []);
  return { ...state, refresh };
}
