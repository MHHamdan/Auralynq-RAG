"use client";
import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";

export function AppBar({
  online,
  vectors,
  entities,
  onNewChat,
  onToggleInspector,
  inspectorOpen,
  onToggleSettings,
}: {
  online: boolean | null;
  vectors: number | null;
  entities?: number | null;
  onNewChat: () => void;
  onToggleInspector: () => void;
  inspectorOpen: boolean;
  onToggleSettings?: () => void;
}) {
  return (
    <header className="sticky top-0 z-40 border-b border-edge bg-ink/85 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-[1920px] items-center justify-between gap-3 px-3 md:px-5">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href="/"
            className="flex items-center gap-2 text-lg font-bold tracking-tight text-fg"
            aria-label="Auralynq home"
          >
            <span aria-hidden>🎙️</span>
            <span className="hidden sm:inline">
              <span className="text-brand">Aura</span>
              <span className="text-brand2">lynq</span>
            </span>
          </Link>
          <span
            className={`pill ${online === null ? "pill-neutral" : online ? "pill-ok" : "pill-bad"}`}
            title={online ? "Backend online" : online === false ? "Backend offline" : "Connecting"}
          >
            <span
              className={`inline-block h-1.5 w-1.5 rounded-full ${
                online === null ? "bg-fg3" : online ? "bg-ok animate-pulse-soft" : "bg-bad"
              }`}
            />
            {online === null ? "Connecting" : online ? "Online" : "Offline"}
          </span>
          {online && vectors !== null && (
            <span className="hidden text-xs text-fg2 md:inline">
              {vectors.toLocaleString()} vectors
              {entities != null && entities > 0 && (
                <span className="text-fg3"> · {entities.toLocaleString()} entities</span>
              )}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          <ThemeToggle compact />
          {onToggleSettings && (
            <button
              type="button"
              onClick={onToggleSettings}
              className="btn-ghost px-2 py-1.5 text-sm"
              aria-label="Display settings"
              title="Display settings"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4" aria-hidden>
                <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
              </svg>
            </button>
          )}
          <button
            type="button"
            onClick={onToggleInspector}
            aria-pressed={inspectorOpen}
            className="btn-ghost text-sm lg:hidden"
            aria-label="Toggle inspector panel"
          >
            {inspectorOpen ? "Hide panel" : "Inspector"}
          </button>
          <button
            type="button"
            onClick={onNewChat}
            className="btn-brand text-sm"
            title="New chat (⌘K)"
            aria-label="Start a new chat (Ctrl/Cmd+K)"
          >
            <span aria-hidden>＋</span>
            <span className="hidden sm:inline">New chat</span>
          </button>
        </div>
      </div>
    </header>
  );
}
