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

echo "→ starting stack…"
$COMPOSE -f "$CF" up -d

echo "✓ stack up (services resolve peers by container_name via dnsname):"
echo "    HTTPS   : https://<SERVER_IP>:${https_port}   (public — Caddy TLS proxy)"
echo "    web/api : internal (${bind_internal} loopback), fronted by Caddy"
echo "    Qdrant  : internal (${bind_internal} loopback)"
echo "    Phoenix : internal (${bind_internal} loopback)"
