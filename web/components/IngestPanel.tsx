"use client";
import { useCallback, useEffect, useState } from "react";
import { CorpusSummary, corpusSummary, fetchSuggestions, ingestFile } from "@/lib/api";

const ACCEPT = ".pdf,.docx,.html,.htm,.md,.txt,.wav,.mp3,.m4a";
const TYPES = ["PDF", "DOCX", "HTML", "Markdown", "TXT", "WAV", "MP3", "M4A"];

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "unknown";
  const mins = Math.round((Date.now() - t) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export function IngestPanel({ onAsk }: { onAsk?: (q: string) => void }) {
  const [status, setStatus] = useState<{ kind: "ok" | "err" | "info"; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [summary, setSummary] = useState<CorpusSummary | null>(null);
  const [samples, setSamples] = useState<string[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [s, sug] = await Promise.all([corpusSummary(), fetchSuggestions(3)]);
      setSummary(s);
      setSamples(sug.suggestions);
    } catch {
      /* backend may be warming up */
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const upload = useCallback(
    async (file: File) => {
      setBusy(true);
      setStatus({ kind: "info", msg: `Uploading ${file.name} — parsing → chunking → indexing…` });
      try {
        const r = await ingestFile(file);
        setStatus({
          kind: "ok",
          msg: `✓ Indexed ${r.documents} document(s), ${r.chunks} chunk(s)${
            r.skipped ? `, ${r.skipped} skipped` : ""
          }.`,
        });
        await refresh();
      } catch (err) {
        setStatus({ kind: "err", msg: `✗ ${(err as Error).message}` });
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDrag(false);
    const file = e.dataTransfer.files?.[0];
    if (file && !busy) void upload(file);
  }

  return (
    <div className="space-y-3">
      {/* corpus stats */}
      {summary && (
        <div className="grid grid-cols-3 gap-1.5 text-center">
          <div className="rounded-lg border border-edge bg-ink/40 px-2 py-1.5">
            <div className="text-sm font-semibold text-slate-100">
              {summary.indexed_document_count}
            </div>
            <div className="text-[10px] uppercase tracking-wide text-slate-400">docs</div>
          </div>
          <div className="rounded-lg border border-edge bg-ink/40 px-2 py-1.5">
            <div className="text-sm font-semibold text-slate-100">{summary.vector_count}</div>
            <div className="text-[10px] uppercase tracking-wide text-slate-400">vectors</div>
          </div>
          <div className="rounded-lg border border-edge bg-ink/40 px-2 py-1.5">
            <div className="text-sm font-semibold text-slate-100">{summary.entity_count}</div>
            <div className="text-[10px] uppercase tracking-wide text-slate-400">entities</div>
          </div>
        </div>
      )}
      {summary && (
        <p className="text-[11px] text-slate-400">Last indexed: {timeAgo(summary.last_indexed)}</p>
      )}

      {/* drag-and-drop zone */}
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed p-5 text-center transition ${
          drag ? "border-brand bg-brand/10" : "border-edge hover:border-brand/50"
        }`}
      >
        <span className="text-2xl" aria-hidden>
          {busy ? "⏳" : "⬆️"}
        </span>
        <span className="text-sm text-slate-200">
          {busy ? "Working…" : "Drag a file here, or click to upload"}
        </span>
        <span className="text-[11px] text-slate-400">Chunked with source spans → hybrid index + graph</span>
        <input
          type="file"
          className="hidden"
          disabled={busy}
          accept={ACCEPT}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void upload(f);
          }}
        />
      </label>

      <div className="flex flex-wrap gap-1">
        {TYPES.map((t) => (
          <span key={t} className="tag">
            {t}
          </span>
        ))}
      </div>

      {status && (
        <p
          className={`text-sm ${
            status.kind === "ok"
              ? "text-emerald-400"
              : status.kind === "err"
                ? "text-rose-300"
                : "text-slate-300"
          }`}
        >
          {status.msg}
        </p>
      )}

      {/* sample questions the current corpus can actually answer */}
      {samples.length > 0 && (
        <div>
          <p className="text-xs text-slate-400">Try these on the current corpus:</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {samples.map((q) => (
              <button
                key={q}
                onClick={() => onAsk?.(q)}
                className="rounded-full border border-edge bg-panel/60 px-3 py-1 text-xs text-slate-200 transition hover:border-brand hover:text-brand"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
