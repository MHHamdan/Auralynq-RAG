"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { LLMBackendInfo, fetchLLMBackends, setLLMBackend } from "@/lib/api";

// Picks which local engine serves generation: Ollama, vLLM, or AirLLM.
//
// Three axes that a single badge would flatten are kept distinct here, because
// they fail independently:
//   reachability — is the daemon/server answering, or the library importable?
//   hardware     — does this machine have what the backend needs?
//   speed        — 2 seconds or 20 minutes per answer?
// AirLLM is the reason the third axis is not optional: it runs models the
// hardware "cannot" run, by trading minutes per answer for VRAM. Showing it as
// simply "available" would be misleading, so its speed class is always visible.

const BACKEND_LS_KEY = "auralynq.llm_backend.v1";

const SPEED_META: Record<LLMBackendInfo["speed_class"], { label: string; cls: string }> = {
  very_fast: { label: "fastest", cls: "text-ok" },
  fast: { label: "fast", cls: "text-ok" },
  very_slow: { label: "minutes/answer", cls: "text-bad" },
};

const ICON: Record<string, string> = { ollama: "◆", vllm: "▲", airllm: "◈", auto: "⚙" };

export function loadStoredBackend(): string {
  try {
    return localStorage.getItem(BACKEND_LS_KEY) || "auto";
  } catch {
    return "auto";
  }
}

export function saveStoredBackend(id: string) {
  try {
    localStorage.setItem(BACKEND_LS_KEY, id);
  } catch {
    /* ignore */
  }
}

function BackendRow({
  b,
  selected,
  onSelect,
}: {
  b: LLMBackendInfo;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const speed = SPEED_META[b.speed_class];
  return (
    <button
      role="option"
      aria-selected={selected}
      onClick={() => b.available && onSelect(b.id)}
      disabled={!b.available}
      className={`flex w-full flex-col gap-0.5 px-3 py-2 text-left transition ${
        selected ? "bg-brand/10" : b.available ? "hover:bg-panel2" : "cursor-not-allowed opacity-60"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          {selected && <span aria-hidden className="text-brand text-xs">✓</span>}
          <span aria-hidden className="text-fg3 text-xs">{ICON[b.id]}</span>
          <span
            className={`text-xs font-medium ${
              selected ? "text-brand" : b.available ? "text-fg" : "text-fg3"
            }`}
          >
            {b.name}
          </span>
          {b.status === "experimental" && (
            <span className="rounded-full bg-warn/15 px-1.5 py-0 text-[9px] font-semibold text-warn">
              experimental
            </span>
          )}
        </div>
        <span className={`shrink-0 text-[10px] font-medium ${b.available ? speed.cls : "text-fg3"}`}>
          {b.available ? speed.label : "unavailable"}
        </span>
      </div>

      <p className="text-[10px] leading-snug text-fg3">{b.description}</p>

      {b.available ? (
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-fg3">
          {b.detected_at && <span className="font-mono">{b.detected_at}</span>}
          {b.version && <span>v{b.version}</span>}
          {b.models.length > 0 && (
            <span>
              {b.models.length} model{b.models.length === 1 ? "" : "s"}
            </span>
          )}
          {b.active_model && <span className="font-mono">{b.active_model}</span>}
        </div>
      ) : (
        <p className="mt-0.5 text-[10px] leading-snug text-warn">
          {b.unavailable_reason}
          {b.remediation ? ` — ${b.remediation}` : ""}
        </p>
      )}

      {/* Warnings are shown for available backends too: AirLLM's cost is the
          whole reason a user might change their mind about selecting it. */}
      {b.warnings.map((w, i) => (
        <p key={i} className="text-[10px] leading-snug text-warn/90">
          ⚠ {w}
        </p>
      ))}
    </button>
  );
}

export function BackendSelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [backends, setBackends] = useState<LLMBackendInfo[]>([]);
  const [active, setActive] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  const load = useCallback(async (recheck = false) => {
    try {
      const data = await fetchLLMBackends(recheck);
      setBackends(data.backends);
      setActive(data.active);
    } catch {
      /* leave the last known state rather than blanking the picker */
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  async function select(id: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await setLLMBackend(id);
      setActive(res.active);
      onChange(id);
      saveStoredBackend(id);
      setOpen(false);
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setBusy(false);
    }
  }

  const current = backends.find((b) => b.id === value);
  const label = value === "auto" ? `Auto (${active || "…"})` : current?.name || value;

  // A selected backend that has since gone away stays selected and says so,
  // rather than silently rewriting the user's choice.
  const degraded = value !== "auto" && current != null && !current.available;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        title="Select the local LLM serving backend"
        className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition ${
          degraded
            ? "border-bad/40 bg-bad/10 text-bad"
            : "border-edge bg-panel2 text-fg2 hover:text-fg"
        }`}
      >
        <span aria-hidden>{ICON[value] ?? "⚙"}</span>
        <span className="max-w-[140px] truncate">{label}</span>
        <span aria-hidden className="text-fg3">▾</span>
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="LLM serving backend"
          className="absolute bottom-full left-0 z-50 mb-2 max-h-[440px] w-96 overflow-y-auto rounded-xl border border-edge bg-panel shadow-lg"
        >
          <div className="sticky top-0 flex items-start justify-between gap-2 border-b border-edge bg-panel px-3 py-2">
            <div>
              <p className="text-xs font-semibold text-fg">Serving backend</p>
              <p className="text-[10px] text-fg3">Which local engine generates answers</p>
            </div>
            <button
              onClick={() => void load(true)}
              className="shrink-0 rounded-md border border-edge px-2 py-0.5 text-[10px] text-fg3 hover:text-fg"
            >
              ⟳ recheck
            </button>
          </div>

          <button
            role="option"
            aria-selected={value === "auto"}
            onClick={() => void select("auto")}
            className={`flex w-full flex-col gap-0.5 px-3 py-2 text-left transition ${
              value === "auto" ? "bg-brand/10" : "hover:bg-panel2"
            }`}
          >
            <div className="flex items-center gap-1.5">
              {value === "auto" && <span aria-hidden className="text-brand text-xs">✓</span>}
              <span aria-hidden className="text-fg3 text-xs">⚙</span>
              <span
                className={`text-xs font-medium ${value === "auto" ? "text-brand" : "text-fg"}`}
              >
                Auto
              </span>
              <span className="rounded-full bg-brand/15 px-1.5 py-0 text-[9px] font-semibold text-brand">
                default
              </span>
            </div>
            <p className="text-[10px] leading-snug text-fg3">
              Pick the fastest reachable backend, and fall back down the chain if it fails.
              {active ? ` Currently: ${active}.` : ""}
            </p>
          </button>

          {backends.map((b) => (
            <BackendRow key={b.id} b={b} selected={b.id === value} onSelect={(id) => void select(id)} />
          ))}

          {(error || degraded || busy) && (
            <div className="border-t border-edge px-3 py-2">
              {busy && <p className="text-[10px] text-fg3">Switching…</p>}
              {error && <p className="text-[10px] text-bad">{error}</p>}
              {degraded && !error && (
                <p className="text-[10px] text-warn">
                  {current?.name} is selected but unavailable — answers are coming from{" "}
                  {active || "the fallback chain"}.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
