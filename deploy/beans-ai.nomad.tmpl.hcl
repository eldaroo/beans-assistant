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
          BEANS_AI_SHARED_SECRET={{ .BEANS_AI_SHARED_SECRET }}
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

          : "$${CLAUDE_CODE_OAUTH_TOKEN:?CLAUDE_CODE_OAUTH_TOKEN required}"
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
          log "isolation OK: env carries only the model token and the bearer"
          log "toolchain: node $(node --version) · $(claude --version 2>/dev/null | head -1)"
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
