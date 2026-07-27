"use client";
import { useEffect, useRef, useState } from "react";
import type { DiscoverEntry, DiscoverHardware, PullProgress } from "@/lib/modelfit";
import { formatBytes, formatEta, pullModel, streamPullProgress } from "@/lib/modelfit";
import { VERDICT_META } from "@/components/modelfit/verdict";

// Explicit "agree to pull" gate. The user sees exactly what will be downloaded
// (size, destination, command) and confirms with a size-labelled button before
// anything hits the network — no silent auto-pull.
//
// The download itself runs as a server-side job: this modal subscribes to its
// progress, so closing the modal does not cancel the pull and reopening it
// re-attaches to the running download.

type PullState = "idle" | "pulling" | "done" | "error";

const PHASE_LABEL: Record<PullProgress["phase"], string> = {
  queued: "Starting…",
  manifest: "Fetching manifest…",
  downloading: "Downloading",
  verifying: "Verifying…",
  success: "Installed",
  error: "Failed",
};

function ProgressBar({ progress }: { progress: PullProgress }) {
  const determinate = progress.total_bytes > 0;
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-zinc-200">{PHASE_LABEL[progress.phase]}</span>
        {determinate && (
          <span className="text-sm font-mono text-sky-300">{progress.percent.toFixed(1)}%</span>
        )}
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800">
        <div
          className={`h-full rounded-full bg-sky-500 transition-[width] duration-300 ${
            determinate ? "" : "w-1/3 animate-pulse"
          }`}
          style={determinate ? { width: `${Math.max(2, progress.percent)}%` } : undefined}
        />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-mono text-zinc-500">
        {determinate && (
          <span>
            {formatBytes(progress.completed_bytes)} / {formatBytes(progress.total_bytes)}
          </span>
        )}
        {progress.speed_bps > 0 && <span>{formatBytes(progress.speed_bps)}/s</span>}
        {progress.eta_s != null && <span>ETA {formatEta(progress.eta_s)}</span>}
        {progress.layers_total > 0 && (
          <span>
            layer {Math.min(progress.layers_done + 1, progress.layers_total)}/
            {progress.layers_total}
          </span>
        )}
      </div>
      <p className="text-[11px] text-zinc-600">
        You can close this — the download keeps running on the server.
      </p>
    </div>
  );
}

function Line({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-1.5 border-b border-zinc-800 last:border-0">
      <span className="text-zinc-500 text-xs">{label}</span>
      <span className="text-zinc-100 text-sm font-mono text-right">{value}</span>
    </div>
  );
}

export function PullConfirmModal({
  entry,
  hardware,
  onClose,
  onPulled,
}: {
  entry: DiscoverEntry;
  hardware: DiscoverHardware;
  onClose: () => void;
  onPulled: (modelId: string) => void;
}) {
  const [state, setState] = useState<PullState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<PullProgress | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Detach the stream on unmount; the server-side job is unaffected.
  useEffect(() => () => abortRef.current?.abort(), []);

  const re = entry.resource_estimate;
  const meta = entry.model_meta;
  const isOllama = entry.source === "ollama";
  const sizeGb = re?.estimated_disk_gb ?? null;
  const displayName = (meta.display_name || entry.model_id).replace(/^(ollama:|hf:|local:)/, "");
  const verdict = re?.verdict ? VERDICT_META[re.verdict] : null;

  async function confirmPull() {
    setState("pulling");
    setError(null);
    setProgress(null);
    try {
      const started = await pullModel(entry.model_id);

      // HF downloads are synchronous and return no job to follow.
      if (!started.job_id) {
        setState("done");
        onPulled(entry.model_id);
        return;
      }

      const controller = new AbortController();
      abortRef.current = controller;
      const final = await streamPullProgress(started.job_id, setProgress, controller.signal);

      if (final.phase === "error") {
        setState("error");
        setError(final.error || "The download failed.");
        return;
      }
      setState("done");
      onPulled(entry.model_id);
    } catch (e) {
      if ((e as Error)?.name === "AbortError") return;
      setState("error");
      setError(String(e).replace(/^Error:\s*/, ""));
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-zinc-700 bg-zinc-900 shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-zinc-800 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-zinc-100">Download this model?</h2>
            <p className="text-xs text-zinc-500 mt-0.5">
              You are about to fetch a model onto this machine.
            </p>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 text-xl leading-none">
            ×
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          {/* Verdict banner */}
          {verdict && (
            <div className={`flex items-center gap-2 rounded-lg px-3 py-2 ${verdict.badgeClass}`}>
              <verdict.icon className="h-4 w-4 shrink-0" aria-hidden />
              <span className="text-sm font-medium">{verdict.label}</span>
              {re && (
                <span className="ml-auto text-xs opacity-80 font-mono">
                  ~{re.estimated_vram_gb} GB {hardware.total_vram_gb > 0 ? "VRAM" : "RAM"}
                </span>
              )}
            </div>
          )}

          {/* Details */}
          <div>
            <Line label="Model" value={displayName} />
            <Line label="Source" value={isOllama ? "Ollama registry" : "Hugging Face Hub"} />
            {meta.parameter_count_b != null && <Line label="Parameters" value={`${meta.parameter_count_b}B`} />}
            <Line label="Quantization" value={entry.best_quantization} />
            {sizeGb != null && (
              <Line
                label="Download size"
                value={<span className="text-sky-300 font-semibold">≈ {sizeGb} GB</span>}
              />
            )}
            <Line label="License" value={meta.license} />
          </div>

          {/* Command preview */}
          {entry.pull_command && (
            <div className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2">
              <p className="text-[10px] uppercase tracking-wider text-zinc-600 mb-1">Command</p>
              <code className="text-xs text-zinc-300 font-mono break-all">{entry.pull_command}</code>
            </div>
          )}

          {/* Estimator warnings */}
          {re && re.warnings.length > 0 && state === "idle" && (
            <ul className="space-y-1">
              {re.warnings
                .filter((w) => !w.startsWith("Memory figures are estimates"))
                .slice(0, 2)
                .map((w, i) => (
                  <li key={i} className="text-[11px] text-amber-400/90 leading-snug">
                    ⚠ {w}
                  </li>
                ))}
            </ul>
          )}

          {/* State feedback */}
          {state === "pulling" &&
            (progress ? (
              <ProgressBar progress={progress} />
            ) : (
              <div className="flex items-center gap-2 text-sm text-zinc-300">
                <span className="animate-spin">⟳</span>
                <span>Starting download…</span>
              </div>
            ))}
          {state === "done" && (
            <div className="flex items-center gap-2 text-sm text-emerald-400">
              <span>✓</span> Installed — {displayName} is ready to use.
            </div>
          )}
          {state === "error" && (
            <div className="rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2">
              <p className="text-sm text-red-300">{error}</p>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="px-6 py-4 border-t border-zinc-800 flex justify-end gap-3">
          {state === "done" ? (
            <button
              onClick={onClose}
              className="px-5 py-2 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-sm text-white font-medium"
            >
              Done
            </button>
          ) : (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
              >
                {state === "pulling" ? "Continue in background" : "Cancel"}
              </button>
              {isOllama ? (
                <button
                  onClick={confirmPull}
                  disabled={state === "pulling"}
                  className="px-5 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-sm text-white font-semibold disabled:opacity-50 transition-colors"
                >
                  {state === "error"
                    ? "Retry download"
                    : sizeGb != null
                      ? `Agree & download ${sizeGb} GB`
                      : "Agree & download"}
                </button>
              ) : (
                <button
                  onClick={() => {
                    if (entry.pull_command) navigator.clipboard.writeText(entry.pull_command);
                    onClose();
                  }}
                  className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-sm text-white font-semibold transition-colors"
                >
                  Copy download command
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
