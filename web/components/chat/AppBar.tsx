"use client";
import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";

// Fixed top app bar for the chat workspace: identity · live status · theme ·
// new chat. Stays present so the product reads like an app, not a page.
export function AppBar({
  online,
  vectors,
  onNewChat,
  onToggleInspector,
  inspectorOpen,
}: {
  online: boolean | null;
  vectors: number | null;
  onNewChat: () => void;
  onToggleInspector: () => void;
  inspectorOpen: boolean;
}) {
  return (
    <header className="sticky top-0 z-40 border-b border-edge bg-ink/85 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center justify-between gap-3 px-3 md:px-5">
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
            <span className="hidden text-xs text-fg3 md:inline">
              {vectors.toLocaleString()} vectors indexed
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <ThemeToggle compact />
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
