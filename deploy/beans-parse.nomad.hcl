# beans-parse — the stateless Beans & Co parser sidecar (spec 008 M6).
#
# A port of wal-parse: expose POST /parse over HTTPS and, for each utterance, run
# the Claude Code CLI headless (`claude -p`) on the subscription token and return a
# schema-shaped JSON PROPOSAL for the app to validate and execute. No repo clone, no
# Postgres, no business data on the box — just the model, behind a bearer.
#
# LOAD-BEARING INVARIANT: the secret template is a POSITIVE ALLOWLIST carrying exactly
# two inert values — CLAUDE_CODE_OAUTH_TOKEN (the Beans subscription token, reused) and
# BEANS_PARSE_SHARED_SECRET (the bearer). No DATABASE_URL, no org keyring ever lands
# here. The box reads NO business data: the app sends a raw utterance and gets back a
# proposal; the app owns the DB and computes the verdict.
#
# Nomad Variable (created out of band):
#   nomad/jobs/beans-parse -> { CLAUDE_CODE_OAUTH_TOKEN, BEANS_PARSE_SHARED_SECRET }
#
# Public URL (Traefik + Let's Encrypt, *.mdlautomations.duckdns.org):
#   https://beans-parse.mdlautomations.duckdns.org/parse

job "beans-parse" {
  datacenters = ["dc1"]
  namespace   = "default"
  type        = "service"

  meta {
    rev = "1"
  }

  # No node pin: the primary Beans node (212.56.44.209) is CPU-saturated, so at
  # cpu=1000 the scheduler places beans-parse on a node with real headroom (an
  # Oracle node). Traefik discovers it via the Consul catalog and routes to its alloc.

  group "beans-parse" {
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

    task "parse" {
      driver = "docker"

      config {
        image      = "ghcr.io/light-brands/quinn-brain:latest"
        command    = "/bin/bash"
        args       = ["-c", "/local/entrypoint.sh"]
        force_pull = true
        ports      = ["http"]
      }

      env {
        HOME                = "/root"
        CLAUDE_BIN          = "claude"
        GIT_TERMINAL_PROMPT = "0"
        IS_SANDBOX          = "1"
        # Single-user business: one warm worker is enough and keeps the box lean so
        # it fits alongside the other services on the shared node.
        BEANS_POOL_SIZE     = "1"
      }

      template {
        destination = "secrets/beans-parse.env"
        env         = true
        change_mode = "restart"
        data        = <<-EOH
          {{- with nomadVar "nomad/jobs/beans-parse" -}}
          CLAUDE_CODE_OAUTH_TOKEN={{ .CLAUDE_CODE_OAUTH_TOKEN }}
          BEANS_PARSE_SHARED_SECRET={{ .BEANS_PARSE_SHARED_SECRET }}
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
          log() { echo "[beans-parse $(ts)] $*"; }

          : "$${CLAUDE_CODE_OAUTH_TOKEN:?CLAUDE_CODE_OAUTH_TOKEN required}"
          : "$${BEANS_PARSE_SHARED_SECRET:?BEANS_PARSE_SHARED_SECRET required}"
          : "$${NOMAD_PORT_http:?http port required}"

          # Isolation self-check: no org-keyring / DB value may be present. Fail closed.
          log "isolation self-check: scanning env for org-keyring shapes"
          LEAK="$(env | grep -iE '^(GITHUB|SUPABASE|VERCEL|STRIPE|DATABASE|CLOUDFLARE|GOOGLE|SIGNNOW|LB_SHARE|OPENAI|DISCORD|NEON|POSTGRES)_' || true)"
          if [ -n "$${LEAK}" ]; then
            log "FATAL: org-keyring/DB value present, isolation broken:"
            echo "$${LEAK}" | sed 's/=.*/=<redacted>/' >&2
            exit 1
          fi
          log "isolation OK: env carries only the model token and the bearer"
          log "toolchain: node $(node --version) · $(claude --version 2>/dev/null | head -1)"
          log "starting parse http server on :$${NOMAD_PORT_http}"
          exec node /local/server.mjs
        EOS
      }

      template {
        destination = "local/server.mjs"
        perms       = "0644"
        data        = <<-EOJS
          import http from 'node:http';
          import { spawn } from 'node:child_process';

          const PORT = process.env.NOMAD_PORT_http;
          const SECRET = process.env.BEANS_PARSE_SHARED_SECRET;

          // The Beans parser contract (spec 008). Claude returns ONLY a JSON object:
          // a single PROPOSAL { "operationType": ..., "args": {...} } or { "none": true }.
          // The app re-validates every field, re-derives the verdict, and is the only
          // thing that commits. Amounts are in CENTS (the whole number the operator
          // said, times 100); the app re-grounds each amount against the literal text,
          // so a model that invents or mis-scales a number can never auto-post.
          const SYS = [
            'Sos el parser de Beans & Co, un negocio que vende productos (medias, termos, etc.) en Argentina (rioplatense).',
            'Convertís UNA frase del dueño en UNA sola operacion propuesta, o en {"none":true} si no es una operacion.',
            'Devolvés EXCLUSIVAMENTE un objeto JSON, sin texto antes ni despues. Las operaciones posibles:',
            '- REGISTER_SALE (una venta): {"operationType":"REGISTER_SALE","args":{"items":[{"productRef":<nombre del producto, string>,"quantity":<entero>,"unitPriceCents":<precio en centavos = numero dicho x 100, OMITIR si no dijo precio>}]}}',
            '- REGISTER_EXPENSE (un gasto/egreso): {"operationType":"REGISTER_EXPENSE","args":{"amountCents":<monto en centavos = numero x 100>,"description":<texto corto>}}',
            '- ADD_STOCK (entro stock/mercaderia): {"operationType":"ADD_STOCK","args":{"productRef":<nombre>,"quantity":<entero>}}',
            '- CANCEL_SALE (cancelar/anular una venta): {"operationType":"CANCEL_SALE","args":{"saleRef":<texto del dueño que describe la venta, p.ej. "la ultima venta" o "la venta de Juan">}}',
            '- CANCEL_EXPENSE (cancelar/anular un gasto): {"operationType":"CANCEL_EXPENSE","args":{"expenseRef":<texto que describe el gasto, p.ej. "el gasto de luz">}}',
            '- CANCEL_STOCK (revertir/borrar una entrada de stock): {"operationType":"CANCEL_STOCK","args":{"movementRef":<texto que describe la entrada, p.ej. "la entrada de termos">}}',
            '- UPDATE_PRICE (cambiar el precio de un producto): {"operationType":"UPDATE_PRICE","args":{"productRef":<nombre del producto>,"unitPriceCents":<precio nuevo en centavos = numero x 100>}}',
            '- DEACTIVATE_PRODUCT (desactivar/dar de baja un producto): {"operationType":"DEACTIVATE_PRODUCT","args":{"productRef":<nombre del producto>}}',
            '- RECORD_PRODUCTION (registrar produccion de una semana): {"operationType":"RECORD_PRODUCTION","args":{"productRef":<nombre, opcional>,"country":<pais, opcional>,"unitsProduced":<entero>,"periodWeek":<"YYYY-Www", opcional>}}',
            '- CREATE_SUPPLIER (alta de un proveedor): {"operationType":"CREATE_SUPPLIER","args":{"name":<nombre>,"country":<pais, opcional>,"contact":<contacto, opcional>}}',
            '- RECORD_CHECKIN (registrar que un proveedor contesto/lo atendiste): {"operationType":"RECORD_CHECKIN","args":{"supplierRef":<texto que describe el proveedor, p.ej. "el proveedor Acme" o "el de China">}}',
            '- EDIT_PRODUCT (editar nombre, sku o costo de un producto, NO el precio): {"operationType":"EDIT_PRODUCT","args":{"productRef":<nombre actual>,"name":<nombre nuevo, opcional>,"sku":<sku nuevo, opcional>,"unitCostCents":<costo en centavos, opcional>}}',
            'REGLA CRITICA de referencias: para cancelar o editar, devolve SIEMPRE el DESCRIPTOR en texto (saleRef, expenseRef, movementRef, productRef, supplierRef). NUNCA inventes ni devuelvas un id numerico (saleId, expenseId, movementId, productId, supplierId): el servidor resuelve el descriptor al id correcto. Un id del modelo se descarta.',
            'Expansion de atributos: si una venta nombra dos variantes que comparten el sustantivo ("medias azules y grises a 5"), devolve UN REGISTER_SALE con DOS items, uno por variante ("medias azules", "medias grises"), cada uno con la misma cantidad y precio.',
            'Reglas de montos: "a 300" / "por 300" = precio 300 (unitPriceCents 30000). NO sumes, NO calcules nada mas que x100 sobre el numero EXACTO que aparece. Si no hay numero para un monto obligatorio, usa {"none":true}.',
            'Un numero de dia ("el 15") no es monto. "cada uno" indica precio unitario. Si la frase no es una venta, gasto ni ingreso de stock (un saludo, una pregunta, un escenario de costos), devolve {"none":true}.',
            '',
            'EJEMPLOS:',
            'Frase: "vendi 2 medias a 300" => {"operationType":"REGISTER_SALE","args":{"items":[{"productRef":"medias","quantity":2,"unitPriceCents":30000}]}}',
            'Frase: "vendi un termo stanley" => {"operationType":"REGISTER_SALE","args":{"items":[{"productRef":"termo stanley","quantity":1}]}}',
            'Frase: "gaste 500 en envio" => {"operationType":"REGISTER_EXPENSE","args":{"amountCents":50000,"description":"envio"}}',
            'Frase: "pague 1200 de luz" => {"operationType":"REGISTER_EXPENSE","args":{"amountCents":120000,"description":"luz"}}',
            'Frase: "llegaron 10 termos" => {"operationType":"ADD_STOCK","args":{"productRef":"termos","quantity":10}}',
            'Frase: "sume 20 medias al stock" => {"operationType":"ADD_STOCK","args":{"productRef":"medias","quantity":20}}',
            'Frase: "cancela la ultima venta" => {"operationType":"CANCEL_SALE","args":{"saleRef":"la ultima venta"}}',
            'Frase: "anula la venta de Juan" => {"operationType":"CANCEL_SALE","args":{"saleRef":"la venta de Juan"}}',
            'Frase: "cancela el gasto de luz" => {"operationType":"CANCEL_EXPENSE","args":{"expenseRef":"el gasto de luz"}}',
            'Frase: "borra la entrada de termos" => {"operationType":"CANCEL_STOCK","args":{"movementRef":"la entrada de termos"}}',
            'Frase: "cambia el precio de las medias a 500" => {"operationType":"UPDATE_PRICE","args":{"productRef":"medias","unitPriceCents":50000}}',
            'Frase: "da de baja el termo stanley" => {"operationType":"DEACTIVATE_PRODUCT","args":{"productRef":"termo stanley"}}',
            'Frase: "vendi medias azules y grises a 5" => {"operationType":"REGISTER_SALE","args":{"items":[{"productRef":"medias azules","quantity":1,"unitPriceCents":500},{"productRef":"medias grises","quantity":1,"unitPriceCents":500}]}}',
            'Frase: "produje 100 termos en colombia" => {"operationType":"RECORD_PRODUCTION","args":{"productRef":"termos","country":"colombia","unitsProduced":100}}',
            'Frase: "nuevo proveedor Acme de China" => {"operationType":"CREATE_SUPPLIER","args":{"name":"Acme","country":"China"}}',
            'Frase: "me contesto el proveedor Acme" => {"operationType":"RECORD_CHECKIN","args":{"supplierRef":"el proveedor Acme"}}',
            'Frase: "renombra las medias a medias premium" => {"operationType":"EDIT_PRODUCT","args":{"productRef":"medias","name":"medias premium"}}',
            'Frase: "el sku de termos es TRM-01" => {"operationType":"EDIT_PRODUCT","args":{"productRef":"termos","sku":"TRM-01"}}',
            'Frase: "hola todo bien" => {"none":true}',
            'Frase: "cuanto me queda de stock" => {"none":true}'
          ].join('\n');

          const POOL_SIZE = Number(process.env.BEANS_POOL_SIZE || 2);
          const WARM_MS = 3500;
          const REQ_TIMEOUT_MS = 50000;
          const CLAUDE_ARGS = [
            '-p', '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose',
            '--system-prompt', SYS,
            '--strict-mcp-config',
            '--disallowedTools', 'Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,NotebookEdit,Task,TodoWrite',
            '--dangerously-skip-permissions', '--max-turns', '1',
          ];

          class Worker {
            constructor() {
              this.born = Date.now(); this.used = false; this.dead = false; this.buf = '';
              this.p = spawn('claude', CLAUDE_ARGS, { stdio: ['pipe', 'pipe', 'pipe'], cwd: '/alloc/data' });
              this.p.on('exit', () => { this.dead = true; });
              this.p.on('error', () => { this.dead = true; });
              this.p.stderr.on('data', () => {});
            }
            ready() { return !this.used && !this.dead; }
            prime() { return this.ready() && (Date.now() - this.born) >= WARM_MS; }
            run(utterance) {
              this.used = true;
              return new Promise((resolve, reject) => {
                let settled = false;
                const fin = (fn, v) => { if (settled) return; settled = true; clearTimeout(tm);
                  try { this.p.stdin.end(); } catch (e) {} try { this.p.kill(); } catch (e) {} fn(v); };
                const tm = setTimeout(() => fin(reject, new Error('timeout')), REQ_TIMEOUT_MS);
                this.p.stdout.on('data', (d) => { this.buf += d; let i;
                  while ((i = this.buf.indexOf('\n')) >= 0) {
                    const ln = this.buf.slice(0, i); this.buf = this.buf.slice(i + 1); if (!ln.trim()) continue;
                    let ev; try { ev = JSON.parse(ln); } catch (e) { continue; }
                    if (ev.type === 'result') {
                      if (ev.subtype !== 'success') return fin(reject, new Error('result:' + ev.subtype));
                      const t = String(ev.result || ''); const m = t.match(/\{[\s\S]*\}/);
                      if (!m) return fin(reject, new Error('no json in model output'));
                      let parsed; try { parsed = JSON.parse(m[0]); } catch (e) { return fin(reject, new Error('bad json')); }
                      if (!parsed || (typeof parsed.operationType !== 'string' && parsed.none !== true)) {
                        return fin(reject, new Error('model did not return a proposal'));
                      }
                      return fin(resolve, parsed);
                    }
                  }
                });
                this.p.on('exit', () => fin(reject, new Error('worker exited')));
                const content = 'Frase: ' + JSON.stringify(utterance) + '\n\nJSON:';
                try { this.p.stdin.write(JSON.stringify({ type: 'user', message: { role: 'user', content } }) + '\n'); }
                catch (e) { fin(reject, e); }
              });
            }
          }

          const pool = [];
          function refill() {
            for (let i = pool.length - 1; i >= 0; i--) if (pool[i].dead || pool[i].used) pool.splice(i, 1);
            while (pool.filter((w) => w.ready()).length < POOL_SIZE) pool.push(new Worker());
          }
          setInterval(refill, 1000); refill();
          function take() {
            const w = pool.find((x) => x.prime()) || pool.find((x) => x.ready());
            if (w) { pool.splice(pool.indexOf(w), 1); return w; }
            return new Worker();
          }
          async function parseText(text) {
            const w = take();
            try { return await w.run(text); } finally { setImmediate(refill); }
          }

          const server = http.createServer((req, res) => {
            if (req.method === 'GET' && req.url === '/health') {
              res.writeHead(200, { 'content-type': 'application/json' });
              res.end(JSON.stringify({ ok: true, svc: 'beans-parse' }));
              return;
            }
            if (req.method === 'POST' && req.url === '/parse') {
              if ((req.headers['authorization'] || '') !== 'Bearer ' + SECRET) {
                res.writeHead(401, { 'content-type': 'application/json' });
                res.end('{"none":true,"error":"unauthorized"}');
                return;
              }
              let body = '';
              req.on('data', (d) => { body += d; if (body.length > 8000) req.destroy(); });
              req.on('end', async () => {
                let text;
                try { const b = JSON.parse(body || '{}'); text = (b.message || b.text || '').toString(); }
                catch { res.writeHead(400, { 'content-type': 'application/json' }); res.end('{"none":true,"error":"bad-json"}'); return; }
                if (!text.trim()) { res.writeHead(400, { 'content-type': 'application/json' }); res.end('{"none":true,"error":"empty"}'); return; }
                try {
                  const proposal = await parseText(text.slice(0, 2000));
                  res.writeHead(200, { 'content-type': 'application/json' });
                  res.end(JSON.stringify(proposal));
                } catch (e) {
                  res.writeHead(502, { 'content-type': 'application/json' });
                  res.end(JSON.stringify({ none: true, error: String((e && e.message) || e).slice(0, 300) }));
                }
              });
              return;
            }
            res.writeHead(404); res.end();
          });
          server.listen(PORT, () => console.log('[beans-parse] http on ' + PORT));
        EOJS
      }

      service {
        name     = "beans-parse"
        port     = "http"
        provider = "consul"
        tags = [
          "traefik.enable=true",
          "traefik.http.routers.beans-parse.rule=Host(`beans-parse.mdlautomations.duckdns.org`)",
          "traefik.http.routers.beans-parse.entrypoints=websecure",
          "traefik.http.routers.beans-parse.tls.certresolver=le",
        ]
        check {
          type     = "http"
          path     = "/health"
          interval = "20s"
          timeout  = "5s"
        }
      }

      resources {
        # Right-sized to the shared node's headroom (wal-parse + the Beans services
        # already fill most of it). The parse is I/O-bound on the model API, so a
        # lean CPU share with one warm worker handles the single-user load; memory_max
        # allows an inference burst via oversubscription.
        cpu        = 1000
        memory     = 1024
        memory_max = 2560
      }
    }
  }
}
