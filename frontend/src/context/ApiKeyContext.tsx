import { createContext, useCallback, useContext, useState } from "react";
import type { ReactNode } from "react";
import { API_KEY_STORE, readApiKey } from "../api/client";

interface ApiKeyValue {
  apiKey: string;
  hasKey: boolean;
  save: (key: string) => void;
  clear: () => void;
}

const ApiKeyContext = createContext<ApiKeyValue | null>(null);

export function ApiKeyProvider({ children }: { children: ReactNode }) {
  // the key lives in localStorage because client.ts reads it there on every
  // request; this state just keeps the UI in step with it
  const [apiKey, setApiKey] = useState(readApiKey);

  const save = useCallback((key: string) => {
    const trimmed = key.trim();
    try {
      localStorage.setItem(API_KEY_STORE, trimmed);
    } catch {
      // storage blocked — the key works until the tab closes
    }
    setApiKey(trimmed);
  }, []);

  const clear = useCallback(() => {
    try {
      localStorage.removeItem(API_KEY_STORE);
    } catch {
      /* nothing to remove */
    }
    setApiKey("");
  }, []);

  return (
    <ApiKeyContext.Provider value={{ apiKey, hasKey: apiKey.length > 0, save, clear }}>
      {children}
    </ApiKeyContext.Provider>
  );
}

export function useApiKey(): ApiKeyValue {
  const value = useContext(ApiKeyContext);
  if (!value) throw new Error("useApiKey must be used inside ApiKeyProvider");
  return value;
}
