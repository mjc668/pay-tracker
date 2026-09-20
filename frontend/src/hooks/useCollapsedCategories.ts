"use client";

import { useCallback, useSyncExternalStore } from "react";

const EMPTY_COLLAPSED = new Set<string>();

function readFromStorage(storageKey: string): Set<string> {
  if (typeof window === "undefined") return new Set<string>();
  try {
    const raw = localStorage.getItem(storageKey);
    if (raw) {
      const parsed: unknown = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return new Set(parsed as string[]);
      }
    }
  } catch {
    // ignore malformed storage
  }
  return new Set<string>();
}

// Module-level cache and listener registry turn the collapsed preference into
// an external store: SSR and hydration render EMPTY_COLLAPSED, then React
// re-reads the stored value after hydration and every toggle notifies all
// subscribers. Reading localStorage in a useState initializer instead would
// make the hydration render disagree with the server HTML (React #418).
const snapshots = new Map<string, Set<string>>();
const listeners = new Map<string, Set<() => void>>();

function getSnapshot(storageKey: string): Set<string> {
  let cached = snapshots.get(storageKey);
  if (!cached) {
    cached = readFromStorage(storageKey);
    snapshots.set(storageKey, cached);
  }
  return cached;
}

function subscribe(storageKey: string, onChange: () => void): () => void {
  let forKey = listeners.get(storageKey);
  if (!forKey) {
    forKey = new Set();
    listeners.set(storageKey, forKey);
  }
  forKey.add(onChange);
  return () => {
    forKey.delete(onChange);
  };
}

function writeSnapshot(storageKey: string, next: Set<string>): void {
  snapshots.set(storageKey, next);
  try {
    localStorage.setItem(storageKey, JSON.stringify([...next]));
  } catch {
    // ignore storage errors (e.g. private browsing quota)
  }
  listeners.get(storageKey)?.forEach((listener) => listener());
}

export function useCollapsedCategories(
  storageKey: string,
  allKeys: readonly string[],
) {
  const collapsed = useSyncExternalStore(
    useCallback(
      (onChange: () => void) => subscribe(storageKey, onChange),
      [storageKey],
    ),
    useCallback(() => getSnapshot(storageKey), [storageKey]),
    () => EMPTY_COLLAPSED,
  );

  const toggle = useCallback(
    (key: string) => {
      const next = new Set(getSnapshot(storageKey));
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      writeSnapshot(storageKey, next);
    },
    [storageKey],
  );

  const collapseAll = useCallback(() => {
    writeSnapshot(storageKey, new Set(allKeys));
  }, [allKeys, storageKey]);

  const expandAll = useCallback(() => {
    writeSnapshot(storageKey, new Set<string>());
  }, [storageKey]);

  const allCollapsed = allKeys.length > 0 && allKeys.every((k) => collapsed.has(k));
  const anyExpanded = allKeys.some((k) => !collapsed.has(k));

  return { collapsed, toggle, collapseAll, expandAll, allCollapsed, anyExpanded };
}
