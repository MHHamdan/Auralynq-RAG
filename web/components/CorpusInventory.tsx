"use client";
import type { CorpusSummary } from "@/lib/api";
import { displaySource, timeAgo } from "@/lib/format";

// Renders a corpus-inventory answer (what's *in* the collection) instead of an
// evidence failure — for questions like "Is there any Arabic document in my
// collection?". Built from corpus metadata, so it's honest and instant.
export function CorpusInventory({
  summary,
  question,
}: {
  summary: CorpusSummary;
  question?: string;
}) {
  const types = Object.entries(summary.source_types || {});
  const langs = summary.languages || [];
  const failed = summary.failed_files || [];
  const titles = summary.document_titles || [];
  const topics = summary.top_entities || [];

  // If the user asked about a specific language, answer it directly first.
  const askedLang = detectAskedLanguage(question || "");
  const langMatch =
    askedLang && langs.length
      ? langs.some((l) => l.toLowerCase().includes(askedLang.toLowerCase()))
      : null;

  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2">
        <span aria-hidden className="text-lg leading-none">
          🗂️
        </span>
        <div>
          <p className="font-semibold text-fg">Corpus inventory</p>
          <p className="mt-0.5 text-sm text-fg2">
            {summary.indexed
              ? `${summary.indexed_document_count} document${
                  summary.indexed_document_count === 1 ? "" : "s"
                } · ${summary.vector_count.toLocaleString()} vectors · indexed ${timeAgo(
                  summary.last_indexed,
                )}.`
              : "Nothing is indexed yet — upload documents to build your collection."}
          </p>
        </div>
      </div>

      {askedLang && langMatch !== null && (
        <div className={`rounded-xl border p-3 text-sm ${langMatch ? "evidence-strong" : "evidence-weak"}`}>
          {langMatch ? (
            <span className="text-fg">
              ✓ Yes — your collection includes <strong>{askedLang}</strong> content.
            </span>
          ) : (
            <span className="text-fg">
              No <strong>{askedLang}</strong> documents detected. Languages found:{" "}
              {langs.length ? langs.join(", ") : "unknown"}.
            </span>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <Field label="Documents">
          <span className="text-sm font-semibold text-fg">{summary.indexed_document_count}</span>
        </Field>
        <Field label="Languages">
          {langs.length ? (
            <div className="flex flex-wrap gap-1">
              {langs.map((l) => (
                <span key={l} className="tag">
                  {l}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-xs text-fg3">not detected</span>
          )}
        </Field>
        <Field label="File types">
          {types.length ? (
            <div className="flex flex-wrap gap-1">
              {types.map(([t, n]) => (
                <span key={t} className="tag">
                  {t} · {n}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-xs text-fg3">none</span>
          )}
        </Field>
        <Field label="Last indexed">
          <span className="text-sm text-fg2">{timeAgo(summary.last_indexed)}</span>
        </Field>
      </div>

      {titles.length > 0 && (
        <Field label={`Indexed files (${titles.length})`}>
          <ul className="space-y-0.5 text-xs text-fg2">
            {titles.slice(0, 8).map((d) => (
              <li key={d} className="truncate" title={displaySource(d)}>
                📄 {displaySource(d)}
              </li>
            ))}
            {titles.length > 8 && <li className="text-fg3">+{titles.length - 8} more</li>}
          </ul>
        </Field>
      )}

      {topics.length > 0 && (
        <Field label="Top topics">
          <div className="flex flex-wrap gap-1">
            {topics.slice(0, 8).map((e) => (
              <span key={e.name} className="tag border-brand2/30 text-brand2">
                {e.name}
              </span>
            ))}
          </div>
        </Field>
      )}

      {failed.length > 0 && (
        <Field label={`Failed to ingest (${failed.length})`}>
          <ul className="space-y-0.5 text-xs text-bad">
            {failed.slice(0, 5).map((f) => (
              <li key={f} className="truncate" title={f}>
                ⚠ {displaySource(f)}
              </li>
            ))}
          </ul>
        </Field>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="card-inset">
      <p className="stat-label mb-1">{label}</p>
      {children}
    </div>
  );
}

const LANGUAGES = [
  "arabic",
  "english",
  "french",
  "spanish",
  "german",
  "chinese",
  "japanese",
  "korean",
  "russian",
  "hindi",
  "portuguese",
  "italian",
  "dutch",
  "turkish",
  "persian",
  "urdu",
  "hebrew",
];

function detectAskedLanguage(q: string): string | null {
  const s = q.toLowerCase();
  for (const l of LANGUAGES) {
    if (s.includes(l)) return l.charAt(0).toUpperCase() + l.slice(1);
  }
  return null;
}
