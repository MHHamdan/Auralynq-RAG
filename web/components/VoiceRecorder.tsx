"use client";
import { useRef, useState } from "react";
import { audioUrl, sendVoice } from "@/lib/api";

// The product promise is "Talk to Your Data" — voice is central, so this control
// is a prominent, polished mic with explicit, honest states.
type VoiceState = "idle" | "listening" | "transcribing" | "speaking" | "failed";

const STATE_META: Record<VoiceState, { label: string; hint: string }> = {
  idle: { label: "Hold to talk", hint: "Ask your data out loud" },
  listening: { label: "Listening…", hint: "Release to send" },
  transcribing: { label: "Transcribing & thinking…", hint: "Grounding your answer" },
  speaking: { label: "Speaking…", hint: "Playing the answer" },
  failed: { label: "Voice failed — try again", hint: "Check microphone access" },
};

export function VoiceRecorder({
  onResult,
  compact = false,
}: {
  onResult: (r: any) => void;
  compact?: boolean;
}) {
  const [state, setState] = useState<VoiceState>("idle");
  const [partial, setPartial] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const busy = state === "transcribing";

  async function start() {
    if (busy) return;
    setPartial("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => e.data.size > 0 && chunksRef.current.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setState("transcribing");
        try {
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          const r = await sendVoice(blob);
          setPartial(r.transcript || "");
          onResult(r);
          const a = new Audio(audioUrl());
          setState("speaking");
          a.onended = () => setState("idle");
          a.onerror = () => setState("idle");
          a.play().catch(() => setState("idle"));
        } catch (err) {
          setState("failed");
          onResult({ answer: `Voice error: ${(err as Error).message}`, citations: [] });
        }
      };
      rec.start();
      recorderRef.current = rec;
      setState("listening");
    } catch {
      setState("failed");
    }
  }

  function stop() {
    if (state !== "listening") return;
    recorderRef.current?.stop();
  }

  const meta = STATE_META[state];
  const active = state === "listening";

  return (
    <div className={`flex items-center gap-3 ${compact ? "" : "flex-wrap"}`}>
      <button
        type="button"
        onMouseDown={start}
        onMouseUp={stop}
        onMouseLeave={stop}
        onTouchStart={start}
        onTouchEnd={stop}
        disabled={busy}
        aria-label={meta.label}
        aria-pressed={active}
        title={meta.label}
        className={`relative inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border transition ${
          active
            ? "border-bad/50 bg-bad/15 text-bad"
            : state === "transcribing"
              ? "border-brand/50 bg-brand/15 text-brand"
              : state === "speaking"
                ? "border-accent/50 bg-accent/15 text-accent"
                : state === "failed"
                  ? "border-warn/50 bg-warn/15 text-warn"
                  : "border-edge bg-panel2 text-fg hover:border-brand/50 hover:text-brand"
        }`}
      >
        {active && (
          <span className="absolute inset-0 rounded-full border-2 border-bad/40 animate-pulse-ring" aria-hidden />
        )}
        <MicGlyph spinning={state === "transcribing"} />
      </button>

      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-fg">{meta.label}</span>
          {active && (
            <span className="flex items-center gap-0.5" aria-hidden>
              {[0, 1, 2, 3].map((i) => (
                <span
                  key={i}
                  className="inline-block w-1 rounded-full bg-bad animate-pulse"
                  style={{ height: `${8 + ((i * 7) % 16)}px`, animationDelay: `${i * 120}ms` }}
                />
              ))}
            </span>
          )}
        </div>
        {partial ? (
          <p className="truncate text-xs text-fg3" title={partial}>
            “{partial}”
          </p>
        ) : (
          !compact && <p className="text-xs text-fg3">{meta.hint}</p>
        )}
      </div>
    </div>
  );
}

function MicGlyph({ spinning }: { spinning: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`h-5 w-5 ${spinning ? "animate-spin" : ""}`}
      aria-hidden
    >
      {spinning ? (
        <path d="M21 12a9 9 0 1 1-6.2-8.55" />
      ) : (
        <>
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8" />
        </>
      )}
    </svg>
  );
}
