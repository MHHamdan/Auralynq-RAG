#!/usr/bin/env bash
# Bring up the Auralynq stack (rootless Podman, no sudo). See ADR-0012/0013/0014.
#
# Networking: this host's CNI generates conflists with cniVersion 1.0.0, but the
# installed `firewall` plugin only supports up to 0.4.0 — so the network silently
# loses container DNS. The default `podman` network also ships without the
# `dnsname` plugin. We fix BOTH without sudo by rewriting the relevant conflist(s)
# under ~/.config/cni/net.d to cniVersion 0.4.0 + ensuring the dnsname plugin is
# present. With DNS working, services reach peers by container_name
# (auralynq-qdrant / auralynq-api / auralynq-web) — see ADR-0014.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="$(./scripts/check_container_runtime.sh)"
CF="compose.yml"
CNI_DIR="${HOME}/.config/cni/net.d"

# Patch a CNI conflist in place: pin cniVersion 0.4.0 and append dnsname if absent.
patch_conflist() {
  local f="$1"
  [ -f "$f" ] || return 0
  python3 - "$f" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
changed = False
if d.get("cniVersion") != "0.4.0":
    d["cniVersion"] = "0.4.0"; changed = True
types = [pl.get("type") for pl in d.get("plugins", [])]
if "dnsname" not in types:
    d.setdefault("plugins", []).append(
        {"type": "dnsname", "domainName": "dns.podman", "capabilities": {"aliases": True}})
    changed = True
if changed:
    json.dump(d, open(p, "w"), indent=2)
    print(f"  patched {p} -> 0.4.0 + dnsname")
PY
}

echo "→ ensuring rootless CNI networks have DNS (no sudo)…"
# The default podman network (used by podman-compose) + any project network.
shopt -s nullglob
for f in "${CNI_DIR}"/87-podman.conflist "${CNI_DIR}"/*podman*.conflist "${CNI_DIR}"/auralynq*.conflist; do
  patch_conflist "$f"
done
shopt -u nullglob

# Prefer an exported env var (e.g. from scripts/run_local.sh) over the .env file,
# matching podman-compose's own precedence so the printed URL is accurate.
bind_internal="${AURALYNQ_BIND_INTERNAL:-$(grep -E '^AURALYNQ_BIND_INTERNAL=' .env 2>/dev/null | cut -d= -f2)}"; bind_internal="${bind_internal:-127.0.0.1}"
https_port="${AURALYNQ_HTTPS_PORT:-$(grep -E '^AURALYNQ_HTTPS_PORT=' .env 2>/dev/null | cut -d= -f2)}"; https_port="${https_port:-8443}"

# ── Host Ollama reachability (rootless) ───────────────────────────────────────
# Containers on the rootless compose bridge cannot reach host loopback services,
# and Podman auto-injects host.containers.internal pointing at the bridge gateway
# (10.88.0.1) — which is NOT the host in rootless mode. If the user runs Ollama
# on the host, route the containers to the host's real LAN IP instead (Ollama
# binds 0.0.0.0, so the bridge can reach it there). Without this the API silently
# degrades to the extractive LLM fallback even when a local GPU model is present.
existing_base="${AURALYNQ_LLM__BASE_URL:-$(grep -E '^AURALYNQ_LLM__BASE_URL=' .env 2>/dev/null | cut -d= -f2- || true)}"
if [ -z "${existing_base}" ]; then
  host_ip="$(ip -4 route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' | head -1 || true)"
  if [ -n "${host_ip}" ] && curl -fsS -m 2 "http://${host_ip}:11434/api/tags" >/dev/null 2>&1; then
    export AURALYNQ_LLM__BASE_URL="http://${host_ip}:11434"
    echo "→ host Ollama reachable at ${host_ip}:11434 — routing containers there (local model, not extractive)."
  else
    echo "→ host Ollama not detected — API will use its configured/auto LLM (extractive fallback if none)."
  fi
fi

echo "→ starting stack…"
$COMPOSE -f "$CF" up -d

# The compose `up` above creates the project network at cniVersion 1.0.0, which
# the older `firewall` CNI plugin rejects (noisy validation warnings on every
# later podman command). Patch it down to 0.4.0 + dnsname now that it exists so
# subsequent `podman ps/logs/exec` and the next `up` run clean.
shopt -s nullglob
for f in "${CNI_DIR}"/*_default.conflist "${CNI_DIR}"/auralynq*.conflist; do
  patch_conflist "$f"
done
shopt -u nullglob

echo "✓ stack up (services resolve peers by container_name via dnsname):"
echo "    HTTPS   : https://<SERVER_IP>:${https_port}   (public — Caddy TLS proxy)"
echo "    web/api : internal (${bind_internal} loopback), fronted by Caddy"
echo "    Qdrant  : internal (${bind_internal} loopback)"
echo "    Phoenix : internal (${bind_internal} loopback)"
