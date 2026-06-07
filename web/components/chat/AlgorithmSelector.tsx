"use client";
import { useEffect, useRef, useState } from "react";
import { RAGStrategyInfo, fetchRAGStrategies } from "@/lib/api";

const STATUS_CLS: Record<string, string> = {
  available: "text-ok",
  experimental: "text-warn",
  planned: "text-fg3",
};

const STATUS_LABEL: Record<string, string> = {
  available: "Available",
  experimental: "Experimental",
  planned: "Planned",
};

const LATENCY_CLS: Record<string, string> = {
  fast: "text-ok",
  medium: "text-warn",
  slow: "text-bad",
};

const STRATEGY_LS_KEY = "auralynq.rag_strategy.v1";

function loadStoredStrategy(): string {
  try {
    return localStorage.getItem(STRATEGY_LS_KEY) || "auralynq_rag";
  } catch {
    return "auralynq_rag";
  }
}

function saveStoredStrategy(id: string) {
  try {
    localStorage.setItem(STRATEGY_LS_KEY, id);
  } catch {
    /* ignore */
  }
}

export function AlgorithmSelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [strategies, setStrategies] = useState<RAGStrategyInfo[]>([]);
  const [defaultId, setDefaultId] = useState("auralynq_rag");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchRAGStrategies()
      .then(({ strategies, default_strategy }) => {
        setStrategies(strategies);
        setDefaultId(default_strategy);
      })
      .catch(() => {});
  }, []);

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const current = strategies.find((s) => s.id === value);
  const displayName = current?.name || value.replace(/_/g, " ");
  const isDefault = value === defaultId || value === "auralynq_rag";

  function select(id: string) {
    onChange(id);
    saveStoredStrategy(id);
    setOpen(false);
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        title="Select RAG strategy"
        className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition ${
          isDefault
            ? "border-brand/40 bg-brand/10 text-brand"
            : "border-edge bg-panel2 text-fg2 hover:text-fg"
        }`}
      >
        <span aria-hidden>⚡</span>
        <span className="max-w-[120px] truncate">{displayName}</span>
        <span aria-hidden className="text-fg3">▾</span>
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="RAG strategy"
          className="absolute bottom-full left-0 z-50 mb-2 max-h-[380px] w-72 overflow-y-auto rounded-xl border border-edge bg-panel shadow-lg"
        >
          <div className="sticky top-0 border-b border-edge bg-panel px-3 py-2">
            <p className="text-xs font-semibold text-fg">RAG Algorithm</p>
            <p className="text-[10px] text-fg3">Choose how Auralynq retrieves and answers</p>
          </div>
          {strategies.map((s) => {
            const selected = s.id === value;
            return (
              <button
                key={s.id}
                role="option"
                aria-selected={selected}
                onClick={() => s.available && select(s.id)}
                disabled={!s.available && s.status === "planned"}
                className={`flex w-full flex-col gap-0.5 px-3 py-2 text-left transition ${
                  selected
                    ? "bg-brand/10"
                    : s.available
                    ? "hover:bg-panel2"
                    : "cursor-default opacity-60"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className={`text-xs font-medium ${selected ? "text-brand" : "text-fg"}`}>
                    {selected && <span aria-hidden className="mr-1">✓</span>}
                    {s.name}
                  </span>
                  <div className="flex shrink-0 gap-1">
                    <span className={`text-[10px] ${STATUS_CLS[s.status]}`}>
                      {STATUS_LABEL[s.status]}
                    </span>
                    <span className={`text-[10px] ${LATENCY_CLS[s.expected_latency]}`}>
                      · {s.expected_latency}
                    </span>
                  </div>
                </div>
                <p className="text-[10px] text-fg3 leading-tight line-clamp-2">{s.description}</p>
                {!s.available && s.unavailable_reason && (
                  <p className="text-[10px] text-warn">{s.unavailable_reason.slice(0, 60)}</p>
                )}
                {s.required_features.length > 0 && (
                  <div className="flex flex-wrap gap-0.5">
                    {s.required_features.map((f) => (
                      <span key={f} className="tag text-[9px]">{f.replace(/_/g, " ")}</span>
                    ))}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export { loadStoredStrategy, saveStoredStrategy };
