"use client";
import { useEffect, useState } from "react";
import { statusSummary } from "@/lib/api";

// Subsystems we surface in the landing status strip, in display order.
const ORDER = ["llm", "vector_store", "embeddings", "rerank", "asr", "tts", "tracing"];
const NICE: Record<string, string> = {
  llm: "LLM",
  vector_store: "Vector store",
  embeddings: "Embeddings",
  rerank: "Rerank",
  asr: "ASR",
  tts: "TTS",
  tracing: "Tracing",
};

interface Row {
  subsystem: string;
  provider: string;
}

export function SystemStatus() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [vectors, setVectors] = useState<number | null>(null);
  const [up, setUp] = useState<boolean | null>(null);

  useEffect(() => {
    statusSummary()
      .then((s) => {
        setRows(s.providers || []);
        setVectors(s?.index?.vectors ?? null);
        setUp(true);
      })
      .catch(() => setUp(false));
  }, []);

  const byName = new Map((rows || []).map((r) => [r.subsystem, r.provider]));

  return (
    <div className="mx-auto mt-10 max-w-3xl rounded-2xl border border-edge bg-panel/50 p-3 backdrop-blur">
      <div className="mb-2 flex items-center justify-between px-1">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
          Live system status
        </span>
        <span className="flex items-center gap-1.5 text-xs text-slate-300">
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              up === null ? "bg-slate-500" : up ? "bg-emerald-400" : "bg-rose-400"
            } ${up ? "animate-pulse-soft" : ""}`}
          />
          {up === null ? "checking…" : up ? "API online" : "API offline"}
          {vectors !== null && up && (
            <span className="text-slate-400">· {vectors.toLocaleString()} vectors</span>
          )}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4 lg:grid-cols-7">
        {ORDER.map((key) => {
          const prov = byName.get(key);
          const ok = up && !!prov && prov !== "null";
          return (
            <div
              key={key}
              className="rounded-lg border border-edge bg-ink/40 px-2 py-1.5 text-center"
              title={prov ? `${NICE[key]}: ${prov}` : NICE[key]}
            >
              <div className="flex items-center justify-center gap-1 text-[10px] uppercase tracking-wide text-slate-400">
                <span
                  className={`inline-block h-1.5 w-1.5 rounded-full ${
                    ok ? "bg-emerald-400" : up === false ? "bg-rose-400" : "bg-slate-500"
                  }`}
                />
                {NICE[key]}
              </div>
              <div className="mt-0.5 truncate text-xs font-medium text-slate-200">
                {prov || "—"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
