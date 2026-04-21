const fs = require('fs');
const http = require('http');
const pino = require('pino');
const qrcode = require('qrcode-terminal');
const QRCode = require('qrcode');
const {
  default: makeWASocket,
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
} = require('@whiskeysockets/baileys');
const {
  resolvePhoneFromMessageKey,
  resolvePhoneFromTenantHeuristics,
} = require('./lid_resolution');
const { sendOnboardingMessages } = require('./onboarding_messages');

const BACKEND_URL = (process.env.BACKEND_URL || 'http://backend:8000').replace(/\/$/, '');
const SESSION_DIR = process.env.BAILEYS_SESSION_DIR || '/app/.baileys_auth';
const LOG_LEVEL = process.env.BAILEYS_LOG_LEVEL || 'info';
const logger = pino({ level: LOG_LEVEL });
const AUTO_CREATE_TENANT = (process.env.BAILEYS_AUTO_CREATE_TENANT || 'false').toLowerCase() === 'true';
const DEFAULT_TENANT_CURRENCY = process.env.BAILEYS_DEFAULT_CURRENCY || 'USD';
const DEFAULT_TENANT_LANGUAGE = process.env.BAILEYS_DEFAULT_LANGUAGE || 'es';
const RECONNECT_DELAY_MS = Number(process.env.BAILEYS_RECONNECT_DELAY_MS || 5000);
const HEALTH_PORT = Number(process.env.BAILEYS_HEALTH_PORT || 3000);
const SCAN_PASSWORD = process.env.BAILEYS_SCAN_PASSWORD || 'beans123';
const BAILEYS_FALLBACK_VERSION = process.env.BAILEYS_FALLBACK_VERSION || '2,3000,1035194821';

logger.info({ AUTO_CREATE_TENANT, BAILEYS_FALLBACK_VERSION }, '[BAILEYS] Connector configuration');

// WhatsApp connection state exposed for health checks
let waStatus = 'starting'; // starting | connected | disconnected | logged_out
let latestQR = null; // latest QR string from Baileys

// Maps @lid JIDs to real phone numbers. Populated from the backend DB
// (tenants.whatsapp_lid) and from the self-identification flow.
const lidPhoneMap = new Map();

// Tracks JIDs that are mid-identification: waiting for the user to reply
// with their phone number.  value = true (simple flag).
const pendingIdentification = new Set();

// Tracks phones that are currently in onboarding so future messages go
// straight to the onboarding endpoint until the tenant is created.
const pendingOnboarding = new Set();

const healthServer = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    // Always return 200 — the server is running. WhatsApp status is in the body.
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', whatsapp: waStatus }));
  } else if (req.method === 'GET' && req.url.startsWith('/scan')) {
    const url = new URL(req.url, `http://${req.headers.host}`);
    const password = url.searchParams.get('password');
    if (!password || password !== SCAN_PASSWORD) {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>WhatsApp QR - Password Required</title>
        <style>body{font-family:sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;background:#f0f2f5;margin:0}</style>
        </head><body><h2>🔒 Password Required</h2><form method="get"><input type="password" name="password" placeholder="Enter password" required><button type="submit">Submit</button></form></body></html>`);
      return;
    }

    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });

    if (waStatus === 'connected') {
      res.end(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>WhatsApp QR</title>
        <style>body{font-family:sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;background:#f0f2f5;margin:0}</style>
        </head><body><h2 style="color:#25d366">✅ WhatsApp conectado</h2><p>No hace falta escanear nada.</p></body></html>`);
      return;
    }

    if (!latestQR) {
      res.end(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>WhatsApp QR</title>
        <meta http-equiv="refresh" content="3">
        <style>body{font-family:sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;background:#f0f2f5;margin:0}</style>
        </head><body><h2>Esperando QR...</h2><p>Esta página se recarga sola. Status: <b>${waStatus}</b></p></body></html>`);
      return;
    }

    try {
      const dataUrl = await QRCode.toDataURL(latestQR, { width: 300, margin: 2 });
      res.end(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>WhatsApp QR</title>
        <meta http-equiv="refresh" content="20">
        <style>body{font-family:sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;background:#f0f2f5;margin:0}
        .card{background:#fff;padding:2rem;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.1);text-align:center}
        img{display:block;margin:1rem auto}</style>
        </head><body><div class="card">
        <h2 style="color:#25d366">Escaneá con WhatsApp</h2>
        <img src="${dataUrl}" alt="QR Code" width="300" height="300">
        <p style="color:#888;font-size:.85rem">El QR expira en ~20 segundos. La página se recarga automáticamente.</p>
        </div></body></html>`);
    } catch (err) {
      res.end(`<html><body><pre>Error generando QR: ${err.message}</pre></body></html>`);
    }
  } else {
    res.writeHead(404);
    res.end();
  }
});
healthServer.listen(HEALTH_PORT, () => {
  logger.info({ port: HEALTH_PORT }, '[HEALTH] HTTP server listening');
});


function ensureSessionDir() {
  fs.mkdirSync(SESSION_DIR, { recursive: true });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseVersionString(versionString) {
  return versionString.split(',').map((part) => Number(part.trim()));
}

async function getBaileysVersion() {
  const maxAttempts = 3;
  let lastError = null;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      const version = await fetchLatestBaileysVersion();
      logger.info({ version }, '[BAILEYS] Using fetched Baileys version');
      return version;
    } catch (err) {
      lastError = err;
      logger.warn({ attempt, err: err?.message || err }, '[BAILEYS] Failed to fetch latest Baileys version');
      if (attempt < maxAttempts) {
        await sleep(5000);
      }
    }
  }

  logger.warn({ fallback: BAILEYS_FALLBACK_VERSION }, '[BAILEYS] Falling back to pinched Baileys version');
  return { version: parseVersionString(BAILEYS_FALLBACK_VERSION) };
}

function phoneFromJid(jid) {
  const base = String(jid || '').split('@')[0];
  if (!base) return '';

  const digits = base.replace(/\D/g, '');
  if (!digits) return '';
  return `+${digits}`;
}

// Resolve a JID to a real phone number.
// For @lid JIDs: checks the in-memory cache (populated from the backend DB).
// Returns '' if the LID isn't mapped yet (triggers identification flow).
function resolvePhone(jid) {
  if (!jid) return '';
  if (jid.endsWith('@lid')) return lidPhoneMap.get(jid) || '';
  return phoneFromJid(jid);
}

// Query the backend for the phone number associated with a given LID.
// Caches the result in lidPhoneMap on success.
async function lookupLidInBackend(lid) {
  try {
    const resp = await fetch(`${BACKEND_URL}/api/tenants/by-lid/${encodeURIComponent(lid)}`);
    if (!resp.ok) return null;
    const tenant = await resp.json();
    const phone = tenant.phone_number;
    if (phone) {
      lidPhoneMap.set(`${lid}@lid`, phone);
      logger.info({ lid, phone }, '[BAILEYS] LID resolved from backend DB');
    }
    return phone || null;
  } catch (err) {
    logger.warn({ lid, err: err.message }, '[BAILEYS] LID backend lookup failed');
    return null;
  }
}

// Store a LID→phone mapping in the backend and in the local cache.
async function saveLidMapping(jid, phone) {
  const lid = jid.split('@')[0];
  try {
    const resp = await fetch(`${BACKEND_URL}/api/tenants/${encodeURIComponent(phone)}/whatsapp-lid`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lid }),
    });
    if (resp.ok) {
      lidPhoneMap.set(jid, phone);
      logger.info({ jid, phone }, '[BAILEYS] LID→phone saved to backend');
      return true;
    }
    logger.warn({ jid, phone, status: resp.status }, '[BAILEYS] Backend rejected LID save');
    return false;
  } catch (err) {
    logger.warn({ jid, err: err.message }, '[BAILEYS] Failed to save LID mapping');
    return false;
  }
}

async function requestOnboardingReply(phone, messageText, senderName = '') {
  const url = `${BACKEND_URL}/api/onboarding/${encodeURIComponent(phone)}`;

  logger.info({ phone, url, messageLength: messageText.length }, '[BAILEYS] Requesting onboarding reply');

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: messageText, sender_name: senderName || undefined }),
    signal: AbortSignal.timeout(45000),
  });

  logger.info({ phone, status: response.status }, '[BAILEYS] Onboarding response status');

  if (!response.ok) {
    const detail = await response.text();
    logger.error({ phone, status: response.status, detail: detail.substring(0, 200) }, '[BAILEYS] Onboarding backend error response');
    throw new Error(`Onboarding ${response.status}: ${detail}`);
  }

  return response.json();
}

function extractText(messageContent = {}) {
  return (
    messageContent.conversation ||
    messageContent.extendedTextMessage?.text ||
    messageContent.imageMessage?.caption ||
    messageContent.videoMessage?.caption ||
    messageContent.documentMessage?.caption ||
    messageContent.buttonsResponseMessage?.selectedDisplayText ||
    messageContent.listResponseMessage?.title ||
    messageContent.templateButtonReplyMessage?.selectedDisplayText ||
    ''
  ).trim();
}

function isSupportedIncomingMessage(message) {
  if (!message || !message.key || !message.message) return false;
  if (message.key.fromMe) return false;

  const jid = String(message.key.remoteJid || '');
  if (!jid || jid === 'status@broadcast') return false;
  if (jid.endsWith('@g.us')) return false; // Ignore groups for now

  return true;
}

async function createTenantIfNeeded(phone, senderName = '') {
  logger.info({ phone, senderName, AUTO_CREATE_TENANT, BACKEND_URL }, '[BAILEYS] createTenantIfNeeded called');

  if (!AUTO_CREATE_TENANT) {
    logger.info({ phone, AUTO_CREATE_TENANT }, '[BAILEYS] AUTO_CREATE_TENANT disabled, cannot create tenant');
    return false;
  }

  logger.info({ phone }, '[BAILEYS] Attempting to auto-create tenant...');

  const payload = {
    phone_number: phone,
    business_name: `Tenant ${phone}`,
    owner_name: senderName || undefined,
    currency: DEFAULT_TENANT_CURRENCY,
    language: DEFAULT_TENANT_LANGUAGE,
  };

  try {
    const url = `${BACKEND_URL}/api/tenants`;
    logger.info({ phone, url, payload }, '[BAILEYS] Sending tenant creation request');
    
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(30000),
    });

    logger.info({ phone, status: response.status }, '[BAILEYS] Tenant creation response status');

    if (response.ok) {
      logger.info({ phone }, '[BAILEYS] Tenant auto-created successfully');
      return true;
    }

    if (response.status === 400) {
      const text = await response.text();
      logger.info({ phone, status: 400, detail: text }, '[BAILEYS] Got 400 response');
      if (text.toLowerCase().includes('already exists')) {
        logger.info({ phone }, '[BAILEYS] Tenant already exists (400)');
        return true;
      }
    }

    const detail = await response.text();
    logger.warn({ phone, status: response.status, detail }, '[BAILEYS] Failed to auto-create tenant');
    return false;
  } catch (err) {
    logger.error({ phone, err: err.message || err }, '[BAILEYS] Error during tenant auto-creation');
    return false;
  }
}

async function requestAgentReply(phone, messageText, senderName = '') {
  const url = `${BACKEND_URL}/api/tenants/${encodeURIComponent(phone)}/chat`;

  logger.info({ phone, url, messageLength: messageText.length }, '[BAILEYS] Requesting agent reply');

  let response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: messageText, sender_name: senderName || undefined }),
    signal: AbortSignal.timeout(45000),
  });

  logger.info({ phone, status: response.status }, '[BAILEYS] Initial response status');

  if (!response.ok) {
    const detail = await response.text();
    logger.error({ phone, status: response.status, detail: detail.substring(0, 200) }, '[BAILEYS] Backend error response');
    throw new Error(`Backend ${response.status}: ${detail}`);
  }

  const data = await response.json();
  logger.info({ phone, hasResponse: !!data.response }, '[BAILEYS] Agent reply received');
  return data.response || 'No pude generar una respuesta en este momento.';
}

async function startWhatsApp() {
  ensureSessionDir();

  const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);
  const { version } = await getBaileysVersion();

  logger.info({ sessionDir: SESSION_DIR, version, backend: BACKEND_URL }, '[BAILEYS] Starting WhatsApp connector');

  const sock = makeWASocket({
    auth: state,
    version,
    printQRInTerminal: false,
    logger,
    markOnlineOnConnect: false,
    syncFullHistory: false,
  });

  sock.ev.on('creds.update', saveCreds);

  // Build LID→phone map from contact sync events.
  // WhatsApp sends contacts with both id (@s.whatsapp.net) and lid (@lid);
  // we store the reverse mapping so @lid messages can be routed correctly.
  function indexContacts(contactList) {
    for (const c of contactList) {
      // contacts.upsert gives {id: "@s.whatsapp.net", lid: "@lid"} when both are known
      if (c.lid && c.id && c.id.endsWith('@s.whatsapp.net')) {
        const phone = phoneFromJid(c.id);
        if (phone) {
          lidPhoneMap.set(c.lid, phone);
          logger.info({ lid: c.lid, phone }, '[BAILEYS] LID→phone mapped via contacts');
        }
      }
    }
  }
  sock.ev.on('contacts.upsert', indexContacts);
  sock.ev.on('contacts.update', indexContacts);


  sock.ev.on('connection.update', (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      latestQR = qr;
      logger.info('[BAILEYS] QR ready — visit /scan to scan it');
      qrcode.generate(qr, { small: true });
    }

    if (connection === 'open') {
      waStatus = 'connected';
      latestQR = null;
      logger.info('[BAILEYS] WhatsApp connected');
      if (sock.user) {
        const userPhone = sock.user.id ? sock.user.id.split(':')[0] : 'unknown';
        logger.info({ boundToPhone: `+${userPhone}`, user: sock.user }, '[BAILEYS] Session bound');
      }
      return;
    }

    if (connection === 'close') {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      logger.warn({ statusCode, shouldReconnect }, '[BAILEYS] Connection closed');

      if (shouldReconnect) {
        waStatus = 'disconnected';
        setTimeout(() => {
          startWhatsApp().catch((err) => {
            logger.error({ err }, '[BAILEYS] Reconnect failed');
          });
        }, RECONNECT_DELAY_MS);
      } else {
        waStatus = 'logged_out';
        logger.error('[BAILEYS] Logged out. Delete session and re-scan QR.');
      }
    }
  });

  sock.ev.on('messages.upsert', async ({ type, messages }) => {
    logger.debug({ type, messageCount: messages.length }, '[BAILEYS] ===== MESSAGES UPSERT EVENT =====');
    
    if (type !== 'notify') {
      logger.debug({ type }, '[BAILEYS] Ignoring non-notify message type');
      return;
    }

    for (const msg of messages) {
      const jid = msg.key.remoteJid;
      const participant = msg.key.participant;
      
      logger.debug({
        jid,
        participant,
        fromMe: msg.key.fromMe,
        type: msg.key.type,
        messageType: Object.keys(msg.message || {})[0],
      }, '[BAILEYS] === RAW MESSAGE DEBUG ===');


      if (!isSupportedIncomingMessage(msg)) {
        logger.debug({ jid }, '[BAILEYS] Message type not supported, skipping');
        continue;
      }

      const phone = resolvePhone(jid);
      const text = extractText(msg.message);

      logger.info({
        jid,
        participant,
        phone,
        fromMe: msg.key.fromMe,
        text: text ? text.substring(0, 50) : 'N/A',
      }, '[BAILEYS] Incoming message details');

      if (!text) {
        logger.warn({ jid }, '[BAILEYS] Skipping: no text');
        continue;
      }

      // ── Identification flow for @lid JIDs ──────────────────────────────
      if (jid.endsWith('@lid') && !phone) {
        const lid = jid.split('@')[0];
        const keyPhone = resolvePhoneFromMessageKey(msg.key);
        const senderName = String(msg.pushName || '').trim();

        // 1. Prefer the phone number already exposed by Baileys in the message key.
        if (keyPhone) {
          lidPhoneMap.set(jid, keyPhone);
          logger.info({ jid, phone: keyPhone, senderPn: msg.key?.senderPn, participantPn: msg.key?.participantPn }, '[BAILEYS] Unknown LID resolved from message key');
          await saveLidMapping(jid, keyPhone);
        } else {
          // 2. Try to resolve from backend DB first (covers re-connects).
          const backendPhone = await lookupLidInBackend(lid);
          if (backendPhone) {
            lidPhoneMap.set(jid, backendPhone);
          } else {
            // 3. Try to infer the tenant from the active tenant list and the contact name.
            const heuristicPhone = await resolvePhoneFromTenantHeuristics(senderName);
            if (heuristicPhone) {
              lidPhoneMap.set(jid, heuristicPhone);
              logger.info({ jid, phone: heuristicPhone, senderName }, '[BAILEYS] Unknown LID resolved heuristically from tenant list');
              await saveLidMapping(jid, heuristicPhone);
            }
          }
        }

        if (!resolvePhone(jid) && pendingIdentification.has(jid)) {
          // 4. User is replying with their phone number.
          const candidate = text.replace(/[^\d+]/g, '');
          const normalized = candidate.startsWith('+') ? candidate : `+${candidate}`;
          try {
            const resp = await fetch(`${BACKEND_URL}/api/tenants/${encodeURIComponent(normalized)}`);
            if (resp.ok) {
              const saved = await saveLidMapping(jid, normalized);
              pendingIdentification.delete(jid);
              if (saved) {
                await sock.sendMessage(jid, { text: '✅ ¡Listo! Tu cuenta está vinculada. ¿En qué te puedo ayudar?' });
              } else {
                await sock.sendMessage(jid, { text: 'Hubo un error vinculando tu cuenta. Intentá de nuevo.' });
              }
            } else {
              await sock.sendMessage(jid, { text: 'No encontré una cuenta con ese número. Verificá e intentá de nuevo (ej: +541153695627).' });
            }
          } catch (err) {
            logger.error({ err, jid }, '[BAILEYS] Identification flow error');
          }
          continue;
        }

        if (!resolvePhone(jid)) {
          // 5. Last resort: ask for the phone number only when we could not infer it.
          pendingIdentification.add(jid);
          logger.info({ jid }, '[BAILEYS] Unknown LID — starting identification flow');
          await sock.sendMessage(jid, {
            text: 'Hola! Para conectarte a tu cuenta necesito verificar tu identidad.\n\n¿Cuál es tu número de WhatsApp? (ej: *+541153695627*)',
          });
          continue;
        }
      }
      const resolvedPhone = resolvePhone(jid);
      if (!resolvedPhone) {
        logger.warn({ jid }, '[BAILEYS] Could not resolve phone, skipping');
        continue;
      }

      logger.info({ phone: resolvedPhone, jid, text }, '[BAILEYS] Incoming message');

      try {
        await sock.sendPresenceUpdate('composing', jid);
        const senderName = String(msg.pushName || '').trim();
        let responseText;
        let onboardingPayload = null;

        if (pendingOnboarding.has(resolvedPhone)) {
          onboardingPayload = await requestOnboardingReply(resolvedPhone, text, senderName);
          responseText = onboardingPayload.response;
          if (onboardingPayload.metadata?.onboarding_complete) {
            pendingOnboarding.delete(resolvedPhone);
          } else {
            pendingOnboarding.add(resolvedPhone);
          }
        } else {
          try {
            responseText = await requestAgentReply(resolvedPhone, text, senderName);
          } catch (err) {
            const message = String(err?.message || '');
            if (message.startsWith('Backend 404')) {
              logger.info({ phone: resolvedPhone }, '[BAILEYS] Tenant missing, starting onboarding');
              onboardingPayload = await requestOnboardingReply(resolvedPhone, text, senderName);
              responseText = onboardingPayload.response;
              if (onboardingPayload.metadata?.onboarding_complete) {
                pendingOnboarding.delete(resolvedPhone);
              } else {
                pendingOnboarding.add(resolvedPhone);
              }
            } else {
              throw err;
            }
          }
        }

        if (onboardingPayload) {
          await sendOnboardingMessages(sock, jid, onboardingPayload, logger);
        } else {
          await sock.sendMessage(jid, { text: responseText });
        }
      } catch (err) {
        logger.error({ err, phone: resolvedPhone }, '[BAILEYS] Failed to process message');
        await sock.sendMessage(jid, {
          text: 'Perdón, tuve un problema procesando tu mensaje. Intentá de nuevo en unos segundos.',
        });
      }
    }
  });
}

startWhatsApp().catch((err) => {
  logger.error({ err }, '[BAILEYS] Fatal startup error');
  process.exit(1);
});
