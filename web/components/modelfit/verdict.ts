import type { Verdict } from "@/lib/modelfit";

// Shared presentation for the estimator's will-it-run verdict, so the report
// card, the pull modal, and the ranked rows all speak the same language.
export interface VerdictMeta {
  label: string;
  icon: string;
  /** For a solid banner/pill background. */
  badgeClass: string;
  /** For a coloured accent / bar fill. */
  barClass: string;
  /** For a text-only accent. */
  textClass: string;
}

export const VERDICT_META: Record<Verdict, VerdictMeta> = {
  runs_great: {
    label: "Runs great",
    icon: "✓",
    badgeClass: "bg-emerald-900/50 text-emerald-300 ring-1 ring-emerald-600/40",
    barClass: "bg-emerald-500",
    textClass: "text-emerald-400",
  },
  runs_ok: {
    label: "Runs (tight fit)",
    icon: "✓",
    badgeClass: "bg-sky-900/50 text-sky-300 ring-1 ring-sky-600/40",
    barClass: "bg-sky-500",
    textClass: "text-sky-400",
  },
  runs_offload: {
    label: "Runs with CPU offload — slower",
    icon: "◐",
    badgeClass: "bg-amber-900/50 text-amber-300 ring-1 ring-amber-600/40",
    barClass: "bg-amber-500",
    textClass: "text-amber-400",
  },
  runs_cpu: {
    label: "Runs on CPU",
    icon: "✓",
    badgeClass: "bg-sky-900/50 text-sky-300 ring-1 ring-sky-600/40",
    barClass: "bg-sky-500",
    textClass: "text-sky-400",
  },
  runs_cpu_tight: {
    label: "Runs on CPU — low RAM headroom",
    icon: "◐",
    badgeClass: "bg-amber-900/50 text-amber-300 ring-1 ring-amber-600/40",
    barClass: "bg-amber-500",
    textClass: "text-amber-400",
  },
  too_big: {
    label: "Too big for this machine",
    icon: "✕",
    badgeClass: "bg-red-900/50 text-red-300 ring-1 ring-red-600/40",
    barClass: "bg-red-500",
    textClass: "text-red-400",
  },
};

export function verdictMeta(v: Verdict | undefined | null): VerdictMeta {
  return (v && VERDICT_META[v]) || VERDICT_META.runs_cpu;
}
