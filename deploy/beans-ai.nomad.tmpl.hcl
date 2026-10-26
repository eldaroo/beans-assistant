# beans-ai — a WARM Claude-subscription gateway for Timonel (spec 005).
#
# TEMPLATE. Do not edit deploy/beans-ai.nomad.hcl by hand: it is generated from this file and
# deploy/gateway.mjs by `node deploy/build-hcl.mjs`. The embed marker below (alone on its line)
# is where the gateway source is injected (indented to the heredoc). deploy/gateway.test.mjs
# asserts the committed .hcl is in sync with gateway.mjs, so the box and the tests never drift.
#
# A FORK of wal-parse (clients/personal/wal-ledger/deploy/wal-parse.nomad.hcl) with the warm
# process Wal deferred. Timonel fires several model calls per turn (router + resolver + read),
# so a one-shot cold start would make a turn unusable in chat; this box keeps Claude warm.
#
# LOAD-BEARING INVARIANT (same as wal-parse / quinn-full): the secret template is a POSITIVE
# ALLOWLIST. It carries exactly two inert values — CLAUDE_CODE_OAUTH_TOKEN (a DEDICATED beans
# subscription token, NOT the shared Quinn/Wal token) and BEANS_AI_SHARED_SECRET (the bearer).
# No org keyring, no DATABASE_URL, no GOOGLE/GitHub/Vercel/Supabase value ever lands here. The
# box reads NO tenant data: beans calls it with text and gets back text; the app owns the DB.
#
# Create the Nomad Variable before submitting (Dario generates the token via `claude setup-token`):
#   nomad/jobs/beans-ai -> { CLAUDE_CODE_OAUTH_TOKEN: <dedicated beans sub token>, BEANS_AI_SHARED_SECRET: <random> }
#
# Public URL (Traefik + Let's Encrypt, wildcard *.mdlautomations.duckdns.org):
#   https://beans-ai.mdlautomations.duckdns.org/run   (POST, bearer)
#   https://beans-ai.mdlautomations.duckdns.org/health (GET)

job "beans-ai" {
  datacenters = ["dc1"]
  namespace   = "default"
  type        = "service"

  meta {
    rev = "1"
  }

  # Co-locate on node2 (node1 is Nomad-memory-tight; quinn-full and wal-parse pin here too).
  constraint {
    attribute = "${attr.unique.network.ip-address}"
    value     = "80.241.214.201"
  }

  group "beans-ai" {
    count = 1

    update {
      max_parallel      = 1
      health_check      = "task_states"
      min_healthy_time  = "20s"
      healthy_deadline  = "5m"
      progress_deadline = "8m"
      auto_revert       = true
    }

    ephemeral_disk {
      size    = 600
      sticky  = false
      migrate = false
    }

    restart {
      attempts = 5
      interval = "30m"
      delay    = "15s"
      mode     = "delay"
    }

    reschedule {
      attempts       = 3
      interval       = "1h"
      delay          = "30s"
      delay_function = "exponential"
      max_delay      = "5m"
      unlimited      = false
    }

    network {
      port "http" {}
    }

    task "gateway" {
      driver = "docker"

      config {
        # Reuse the pre-baked brain image (git, Claude CLI, Node 22). force_pull picks up refresh.
        image      = "ghcr.io/light-brands/quinn-brain:latest"
        command    = "/bin/bash"
        args       = ["-c", "/local/entrypoint.sh"]
        force_pull = true
        ports      = ["http"]
        # NET_ADMIN lets the entrypoint apply the network egress firewall (spec 010 M5, T-026,
        # AC-T7): a deny-all-except control that is the LOAD-BEARING egress guard, with the in-code
        # egress-guard.mjs as the second layer. Without this cap the firewall step fails closed.
        cap_add = ["NET_ADMIN"]
      }

      # NON-SECRET env only. The two secrets live in the allowlist template below.
      env {
        HOME                = "/root"
        CLAUDE_BIN          = "claude"
        GIT_TERMINAL_PROMPT = "0"
        IS_SANDBOX          = "1"
        ALLOC_DATA          = "/alloc/data"
      }

      # POSITIVE ALLOWLIST (same discipline as wal-parse). With env=true every key is on its own
      # line; never place a {{- ... -}} comment between two KEY=VALUE lines (it merges them).
      template {
        destination = "secrets/beans-ai.env"
        env         = true
        change_mode = "restart"
        data        = <<-EOH
          {{- with nomadVar "nomad/jobs/beans-ai" -}}
          CLAUDE_CODE_OAUTH_TOKEN={{ .CLAUDE_CODE_OAUTH_TOKEN }}
          CLAUDE_CODE_OAUTH_TOKENS={{ .CLAUDE_CODE_OAUTH_TOKENS }}
          BEANS_AI_SHARED_SECRET={{ .BEANS_AI_SHARED_SECRET }}
          INTERNAL_SERVICE_TOKEN={{ .INTERNAL_SERVICE_TOKEN }}
          BEANS_OPS_URL={{ .BEANS_OPS_URL }}
          BEANS_TENANT_PHONE={{ .BEANS_TENANT_PHONE }}
          {{- end -}}
        EOH
      }

      template {
        destination = "local/entrypoint.sh"
        perms       = "0755"
        data        = <<-EOS
          #!/bin/bash
          set -euo pipefail
          ts()  { date -u +%Y-%m-%dT%H:%M:%SZ; }
          log() { echo "[beans-ai $(ts)] $*"; }

          if [ -z "$${CLAUDE_CODE_OAUTH_TOKENS:-}" ] && [ -z "$${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
            log "FATAL: no CLAUDE_CODE_OAUTH_TOKENS or CLAUDE_CODE_OAUTH_TOKEN present"; exit 1
          fi
          : "$${BEANS_AI_SHARED_SECRET:?BEANS_AI_SHARED_SECRET required}"
          : "$${NOMAD_PORT_http:?http port required}"

          # Isolation self-check: no org-keyring value may be present. Fail closed.
          log "isolation self-check: scanning env for org-keyring shapes"
          LEAK="$(env | grep -iE '^(GITHUB|SUPABASE|VERCEL|STRIPE|DATABASE|CLOUDFLARE|GOOGLE|GEMINI|SIGNNOW|LB_SHARE|OPENAI|DISCORD|NEON)_' || true)"
          if [ -n "$${LEAK}" ]; then
            log "FATAL: org-keyring value present, isolation broken:"
            echo "$${LEAK}" | sed 's/=.*/=<redacted>/' >&2
            exit 1
          fi
          log "isolation OK: no org-keyring value; env carries the model token(s), the bearer, and the beans internal-op wiring"
          log "toolchain: node $(node --version) · $(claude --version 2>/dev/null | head -1)"

          # Pin the Claude CLI to a version where MCP servers connect BEFORE the first turn (2.1.304).
          # The image's 2.1.215 connects MCP asynchronously, so the beans tools are not callable at
          # turn start and the agent cannot use them (verified on the box). Skip if already pinned.
          WANT_CLAUDE="2.1.304"
          HAVE_CLAUDE="$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
          if [ "$${HAVE_CLAUDE}" != "$${WANT_CLAUDE}" ]; then
            log "pinning Claude CLI $${HAVE_CLAUDE} -> $${WANT_CLAUDE}"
            npm i -g @anthropic-ai/claude-code@$${WANT_CLAUDE} >/dev/null 2>&1 || { log "FATAL: claude pin failed"; exit 1; }
            log "pinned: $(claude --version 2>/dev/null | head -1)"
          fi

          # ── Network egress firewall (spec 010 M5, T-026, AC-T7) ─────────────────────────────
          # The LOAD-BEARING egress control: default-DROP on OUTPUT, allow only loopback, already-
          # established flows, DNS to the box's resolvers, and TCP/443 to the resolved IPs of the
          # Next internal-ops host (BEANS_OPS_URL) and api.anthropic.com. The in-code
          # egress-guard.mjs is the SECOND layer (it cannot stop a compromised dependency calling
          # fetch directly; this can). It runs AFTER the Claude-CLI pin on purpose (council: Tamir
          # HIGH): the pin's `npm i` reaches registry.npmjs.org, which is NOT on the allowlist, so a
          # firewall applied before the pin would fail-closed and brick the boot. By here the only
          # egress the running gateway needs is the ops host + Anthropic. Fail CLOSED: if the
          # firewall cannot be applied the box must not serve, because an un-firewalled tool-use box
          # is the exact exfiltration surface spec 007 forbids. BEANS_EGRESS_FIREWALL=0 is the
          # documented deploy escape hatch (relies on the in-code guard only) for a host where
          # NET_ADMIN or nft is unavailable; Dario sets it explicitly at deploy (#273), never default.
          if [ "$${BEANS_EGRESS_FIREWALL:-1}" != "0" ]; then
            OPS_HOST="$(node -e 'try{process.stdout.write(new URL(process.env.BEANS_OPS_URL).hostname)}catch(e){process.exit(3)}')" || { log "FATAL: BEANS_OPS_URL invalid, cannot firewall"; exit 1; }
            log "egress firewall: default-drop, allow DNS + 443 to $${OPS_HOST} + api.anthropic.com"
            command -v nft >/dev/null 2>&1 || { log "FATAL: nft absent and BEANS_EGRESS_FIREWALL!=0 (fail closed)"; exit 1; }
            resolve_ips() { getent ahosts "$1" 2>/dev/null | awk '{print $1}' | sort -u; }
            ALLOW_IPS="$(resolve_ips "$${OPS_HOST}"; resolve_ips api.anthropic.com)"
            [ -n "$${ALLOW_IPS}" ] || { log "FATAL: could not resolve any allowed egress IP (fail closed)"; exit 1; }
            # External (non-loopback) resolvers to pin DNS to (council: Tamir/Binyan MED — DNS-to-any
            # is a covert exfil channel). Loopback resolvers (systemd-resolved 127.0.0.53, Docker
            # embedded 127.0.0.11) are already covered by `oif lo accept`. SAFE FALLBACK: if no
            # external resolver is found, leave 53 open rather than risk bricking DNS (the firewall
            # is deploy-validated, #273, and must never fail-closed on a resolver topology we did not
            # test). The tighter the better, but availability wins over a NIT-grade channel here.
            RESOLVERS="$(awk '/^nameserver/ && $2 !~ /^127\./ && $2 !~ /:/ {print $2}' /etc/resolv.conf 2>/dev/null | sort -u)"
            nft flush ruleset 2>/dev/null || true
            nft add table inet beans_egress
            nft 'add chain inet beans_egress output { type filter hook output priority 0 ; policy drop ; }'
            nft add rule inet beans_egress output oif lo accept
            nft add rule inet beans_egress output ct state established,related accept
            if [ -n "$${RESOLVERS}" ]; then
              for r in $${RESOLVERS}; do
                nft add rule inet beans_egress output ip daddr "$${r}" udp dport 53 accept
                nft add rule inet beans_egress output ip daddr "$${r}" tcp dport 53 accept
              done
              log "egress firewall: DNS pinned to resolvers [$$(echo $${RESOLVERS} | tr '\n' ' ')]"
            else
              nft add rule inet beans_egress output udp dport 53 accept
              nft add rule inet beans_egress output tcp dport 53 accept
              log "egress firewall: no external resolver in resolv.conf; DNS left open (loopback resolver assumed)"
            fi
            for ip in $${ALLOW_IPS}; do
              case "$${ip}" in *:*) continue;; esac   # v4 allowlist; the box reaches both hosts over v4
              nft add rule inet beans_egress output ip daddr "$${ip}" tcp dport 443 accept
            done
            log "egress firewall applied: allow 443 -> [$$(echo $${ALLOW_IPS} | tr '\n' ' ')]"
          else
            log "egress firewall DISABLED by BEANS_EGRESS_FIREWALL=0; relying on the in-code guard only"
          fi

          log "starting warm gateway on :$${NOMAD_PORT_http}"
          exec node /local/gateway.mjs
        EOS
      }

      # The warm gateway. Shipped inline so the box needs no repo clone. Embedded from
      # deploy/gateway.mjs by deploy/build-hcl.mjs — DO NOT edit the generated .hcl copy.
      template {
        destination = "local/gateway.mjs"
        perms       = "0644"
        data        = <<-EOJS
@@GATEWAY_MJS@@
        EOJS
      }

      # Sibling module imported by gateway.mjs (subscription-token rotation). Shipped next to
      # gateway.mjs so `import './token-pool.mjs'` resolves on the box. Embedded by build-hcl.mjs.
      template {
        destination = "local/token-pool.mjs"
        perms       = "0644"
        data        = <<-EOJS
@@TOKEN_POOL_MJS@@
        EOJS
      }

      # Boot tool-posture self-check, imported by gateway.mjs (spec 007 D-035). Embedded by build-hcl.mjs.
      template {
        destination = "local/tool-posture.mjs"
        perms       = "0644"
        data        = <<-EOJS
@@TOOL_POSTURE_MJS@@
        EOJS
      }

      # Boot egress allowlist self-check, imported by gateway.mjs (spec 007 M4, AC12). Embedded by build-hcl.mjs.
      template {
        destination = "local/egress-guard.mjs"
        perms       = "0644"
        data        = <<-EOJS
@@EGRESS_GUARD_MJS@@
        EOJS
      }

      # The beans MCP tool server the agent child loads. Holds no DB credentials; calls the internal
      # operation API with the internal token and the pinned tenant from env. Embedded by build-hcl.mjs.
      template {
        destination = "local/beans-mcp.mjs"
        perms       = "0644"
        data        = <<-EOJS
@@BEANS_MCP_MJS@@
        EOJS
      }

      # Static MCP config the agent child runs with: launches /local/beans-mcp.mjs as server "beans".
      # The MCP server inherits BEANS_OPS_URL / INTERNAL_SERVICE_TOKEN / BEANS_TENANT_PHONE from the
      # gateway env (single business: the tenant is a fixed, out-of-band value, never a model param).
      template {
        destination = "local/mcp-beans.json"
        perms       = "0644"
        data        = <<-EOJSON
          {"mcpServers":{"beans":{"command":"node","args":["/local/beans-mcp.mjs"]}}}
        EOJSON
      }

      service {
        name     = "beans-ai"
        port     = "http"
        provider = "consul"
        tags = [
          "traefik.enable=true",
          "traefik.http.routers.beans-ai.rule=Host(`beans-ai.mdlautomations.duckdns.org`)",
          "traefik.http.routers.beans-ai.entrypoints=websecure",
          "traefik.http.routers.beans-ai.tls.certresolver=le",
        ]
        check {
          type     = "http"
          path     = "/health"
          interval = "20s"
          timeout  = "5s"
        }
      }

      resources {
        cpu        = 1200
        memory     = 768
        memory_max = 2560
      }
    }
  }
}
