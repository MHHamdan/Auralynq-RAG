#!/usr/bin/env bash
# Bring up the Auralynq stack with a hardened, rootless-Podman-correct network
# posture (ADR-0012). On this host the CNI `firewall` plugin is broken (needs
# root to fix), which disables container DNS and gateway binds. We therefore:
#   * publish Qdrant + Phoenix to 127.0.0.1 only (host loopback; NOT the public
#     NIC — verified unreachable from the external IP),
#   * reach Qdrant from the API/worker by its container *bridge IP* (the only
#     reliable container->container path here), resolved at start time,
#   * publish only the Web UI + API on 0.0.0.0 (public surface).
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="$(./scripts/check_container_runtime.sh)"
CF="compose.yml"

echo "→ starting internal services (qdrant, phoenix)…"
$COMPOSE -f "$CF" up -d qdrant phoenix

# Wait for Qdrant to answer on its loopback publish, then resolve bridge IPs.
http_port="$(grep -E '^AURALYNQ_QDRANT_HTTP_PORT=' .env 2>/dev/null | cut -d= -f2)"; http_port="${http_port:-6333}"
bind_internal="$(grep -E '^AURALYNQ_BIND_INTERNAL=' .env 2>/dev/null | cut -d= -f2)"; bind_internal="${bind_internal:-127.0.0.1}"

echo -n "→ waiting for Qdrant"
for _ in $(seq 1 30); do
  if curl -fsS "http://${bind_internal}:${http_port}/readyz" >/dev/null 2>&1; then echo " ✓"; break; fi
  echo -n "."; sleep 1
done

ip_of() { podman inspect "$1" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null; }
QIP="$(ip_of auralynq-qdrant)"
PIP="$(ip_of auralynq-phoenix)"
if [ -z "$QIP" ]; then echo "✗ could not resolve auralynq-qdrant bridge IP" >&2; exit 1; fi

# API/worker reach Qdrant by bridge IP:6333 (container-internal port, no publish
# dependency); Phoenix OTLP likewise by bridge IP:4317 when available.
export AURALYNQ_VECTOR_URL="http://${QIP}:6333"
export AURALYNQ_VECTOR_BACKEND="qdrant"
[ -n "$PIP" ] && export AURALYNQ_OTLP_ENDPOINT="http://${PIP}:4317" || export AURALYNQ_OTLP_ENDPOINT=""
echo "→ qdrant bridge IP = ${QIP}  (api will use ${AURALYNQ_VECTOR_URL})"

echo "→ starting api, worker, web…"
$COMPOSE -f "$CF" up -d api worker web

echo "✓ stack up:"
echo "    Web UI  : http://<SERVER_IP>:${AURALYNQ_WEB_PORT:-3000}   (public)"
echo "    API     : http://<SERVER_IP>:${AURALYNQ_API_PORT:-8000}   (public)"
echo "    Qdrant  : ${bind_internal}:${http_port}                    (internal only)"
echo "    Phoenix : ${bind_internal}:6006                            (internal only)"
