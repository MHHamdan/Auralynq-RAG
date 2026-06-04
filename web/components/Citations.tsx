import { Citation } from "@/lib/api";
import { displaySource } from "@/lib/format";

// Clean, user-facing locator (page / speaker+timestamp) — never raw char spans.
function cleanLocator(c: Citation): string {
  if (c.speaker || c.start_s != null) {
    const t = (s?: number | null) => {
      if (s == null) return "";
      const m = Math.floor(s / 60);
      const sec = Math.round(s % 60);
      return `${m}:${String(sec).padStart(2, "0")}`;
    };
    const range = c.start_s != null ? `${t(c.start_s)}–${t(c.end_s)}` : "";
    return [c.speaker, range].filter(Boolean).join(" · ");
  }
  if (c.page != null) return `p.${c.page}`;
  return "";
}

export function Citations({ citations }: { citations: Citation[] }) {
  if (!citations?.length) return null;
  return (
    <div className="mt-3 space-y-1">
      <div className="overline text-fg3">Citations</div>
      <ol className="space-y-1">
        {citations.map((c) => {
          const loc = cleanLocator(c);
          return (
            <li key={c.marker} className="flex items-start gap-2 text-sm">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand2/15 text-xs font-semibold text-brand2">
                {c.marker}
              </span>
              <span className="min-w-0">
                <span className="text-fg" title={displaySource(c.source)}>
                  {displaySource(c.source)}
                </span>{" "}
                {loc && <span className="text-fg3">· {loc}</span>}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
