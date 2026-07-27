"use client";
import { useCallback, useEffect, useState } from "react";
import { LLMBackendInfo, fetchLLMBackends } from "@/lib/api";

// Read-only view of the three local serving backends, shown next to the hardware
// probe because the two answer different halves of the same question: the
// hardware says what this machine *can* run, this says what is *running* to
// serve it. AirLLM is the case where they diverge — it runs models the hardware
// cannot hold, at minutes per answer — so speed is always on screen.

const SPEED_LABEL: Record<LLMBackendInfo["speed_class"], string> = {
  very_fast: "fastest",
  fast: "fast",
  very_slow: "minutes per answer",
};

const SPEED_CLS: Record<LLMBackendInfo["speed_class"], string> = {
  very_fast: "text-emerald-400",
  fast: "text-emerald-400",
  very_slow: "text-red-400",
};

export function ServingBackends() {
  const [backends, setBackends] = useState<LLMBackendInfo[]>([]);
  const [active, setActive] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (recheck = false) => {
    setLoading(true);
    try {
      const data = await fetchLLMBackends(recheck);
      setBackends(data.backends);
      setActive(data.active);
      setError(null);
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="rounded-xl border border-zinc-700 bg-zinc-900 p-4 space-y-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-zinc-400 font-semibold">Serving backends</p>
        <button
          onClick={() => void load(true)}
          className="rounded-md border border-zinc-700 px-2 py-0.5 text-[10px] text-zinc-400 hover:text-zinc-200"
        >
          ⟳ recheck
        </button>
      </div>

      {loading && backends.length === 0 && <p className="text-xs text-zinc-500">Probing…</p>}
      {error && <p className="text-xs text-red-400">{error}</p>}

      <ul className="space-y-2.5">
        {backends.map((b) => (
          <li key={b.id} className="space-y-0.5">
            <div className="flex items-center gap-2">
              <span
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                  b.available ? "bg-emerald-500" : "bg-zinc-600"
                }`}
              />
              <span className="text-xs font-medium text-zinc-200">{b.name}</span>
              {b.id === active && (
                <span className="rounded-full bg-sky-500/15 px-1.5 text-[9px] font-semibold text-sky-300">
                  serving
                </span>
              )}
              {b.status === "experimental" && (
                <span className="rounded-full bg-amber-500/15 px-1.5 text-[9px] font-semibold text-amber-400">
                  experimental
                </span>
              )}
              <span className={`ml-auto text-[10px] ${b.available ? SPEED_CLS[b.speed_class] : "text-zinc-600"}`}>
                {b.available ? SPEED_LABEL[b.speed_class] : "not detected"}
              </span>
            </div>

            <p className="pl-3.5 text-[11px] text-zinc-500">
              {b.available ? (
                <>
                  {b.detected_at && <span className="font-mono">{b.detected_at}</span>}
                  {b.version && <span> · v{b.version}</span>}
                  {b.models.length > 0 && (
                    <span>
                      {" "}
                      · {b.models.length} model{b.models.length === 1 ? "" : "s"}
                    </span>
                  )}
                  {b.active_model && <span className="font-mono"> · {b.active_model}</span>}
                </>
              ) : (
                <span className="text-amber-500/90">
                  {b.unavailable_reason}
                  {b.remediation ? ` — ${b.remediation}` : ""}
                </span>
              )}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
