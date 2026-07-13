"use client";
import { useCallback, useEffect, useState } from "react";
import { Cloud, RefreshCw, CheckCircle2, AlertTriangle, Plug } from "lucide-react";
import { connectorsStatus, connectorSync, type ConnectorStatus, type ConnectorSyncResult } from "@/lib/api";

const LABELS: Record<string, string> = { notion: "Notion", slack: "Slack", gdrive: "Google Drive" };

/**
 * Cloud connectors: Notion / Slack / Google Drive. Each syncs incrementally via
 * a cursor (like the Watch Folder, over the cloud). Single-token / service-account
 * auth — no OAuth app. Shows setup instructions until a token is provided.
 */
export function ConnectorsPanel({ onSynced }: { onSynced?: () => void }) {
  const [items, setItems] = useState<ConnectorStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [last, setLast] = useState<Record<string, ConnectorSyncResult>>({});

  const load = useCallback(() => {
    setLoading(true);
    connectorsStatus()
      .then(setItems)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const sync = (name: string) => {
    setSyncing(name);
    connectorSync(name)
      .then((r) => {
        setLast((p) => ({ ...p, [name]: r }));
        if (r.added || r.updated || r.removed) onSynced?.();
      })
      .catch((e) => setLast((p) => ({ ...p, [name]: { connector: name, configured: false, added: 0, updated: 0, removed: 0, unchanged: 0, chunks_indexed: 0, errors: [String(e.message || e)] } })))
      .finally(() => {
        setSyncing(null);
        load();
      });
  };

  return (
    <div id="connectors-panel" className="space-y-2 scroll-mt-4">
      <div className="flex items-center justify-between">
        <h3 className="inline-flex items-center gap-1.5 text-sm font-semibold text-fg">
          <Cloud className="h-4 w-4 text-brand" aria-hidden /> Cloud connectors
        </h3>
        <button type="button" onClick={load} aria-label="Refresh connectors" className="text-fg3 transition hover:text-fg">
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} aria-hidden />
        </button>
      </div>

      <ul className="space-y-2">
        {items.map((c) => {
          const r = last[c.name];
          return (
            <li key={c.name} className="rounded-lg border border-edge bg-panel2 p-2.5 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 text-sm font-medium text-fg">
                  <Plug className="h-3.5 w-3.5 text-fg3" aria-hidden />
                  {LABELS[c.name] ?? c.name}
                </span>
                {c.configured ? (
                  <span className="inline-flex items-center gap-1 text-[10px] font-medium text-ok">
                    <CheckCircle2 className="h-3 w-3" aria-hidden /> Connected
                  </span>
                ) : (
                  <span className="text-[10px] font-medium text-fg3">Not configured</span>
                )}
              </div>

              {c.configured ? (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => sync(c.name)}
                    disabled={syncing === c.name}
                    className="btn-outline inline-flex items-center gap-1.5 px-2.5 py-1 text-xs disabled:opacity-60"
                  >
                    <RefreshCw className={`h-3 w-3 ${syncing === c.name ? "animate-spin" : ""}`} aria-hidden />
                    {syncing === c.name ? "Syncing…" : "Sync"}
                  </button>
                  {c.docs > 0 && <span className="text-[10px] text-fg3 font-mono">{c.docs} docs</span>}
                  {c.synced_at && <span className="text-[10px] text-fg3">· {new Date(c.synced_at).toLocaleString()}</span>}
                </div>
              ) : (
                <p className="text-[10px] leading-relaxed text-fg3">{c.setup_hint}</p>
              )}

              {r && (
                <div className="text-[11px]">
                  {r.errors.length > 0 ? (
                    <span className="inline-flex items-center gap-1.5 text-warn">
                      <AlertTriangle className="h-3 w-3" aria-hidden /> {r.errors[0]}
                    </span>
                  ) : (
                    <span className="text-fg2">
                      {r.added + r.updated + r.removed === 0
                        ? "Up to date"
                        : `+${r.added} added · ${r.updated} updated · ${r.removed} removed`}
                    </span>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <p className="text-[10px] text-fg3">
        Connectors sync incrementally and never require an OAuth app — paste one token or a service-account key.
      </p>
    </div>
  );
}
