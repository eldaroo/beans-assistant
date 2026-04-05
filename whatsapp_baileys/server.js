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

const BACKEND_URL = (process.env.BACKEND_URL || 'http://backend:8000').replace(/\/$/, '');
const SESSION_DIR = process.env.BAILEYS_SESSION_DIR || '/app/.baileys_auth';
const LOG_LEVEL = process.env.BAILEYS_LOG_LEVEL || 'info';
const AUTO_CREATE_TENANT = (process.env.BAILEYS_AUTO_CREATE_TENANT || 'false').toLowerCase() === 'true';
const DEFAULT_TENANT_CURRENCY = process.env.BAILEYS_DEFAULT_CURRENCY || 'USD';
const DEFAULT_TENANT_LANGUAGE = process.env.BAILEYS_DEFAULT_LANGUAGE || 'es';
const RECONNECT_DELAY_MS = Number(process.env.BAILEYS_RECONNECT_DELAY_MS || 5000);
const HEALTH_PORT = Number(process.env.BAILEYS_HEALTH_PORT || 3000);

const logger = pino({ level: LOG_LEVEL });

// WhatsApp connection state exposed for health checks
let waStatus = 'starting'; // starting | connected | disconnected | logged_out
let latestQR = null; // latest QR string from Baileys

const healthServer = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    // Always return 200 — the server is running. WhatsApp status is in the body.
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', whatsapp: waStatus }));
  } else if (req.method === 'GET' && req.url === '/scan') {
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

function phoneFromJid(jid) {
  const base = String(jid || '').split('@')[0];
  if (!base) return '';

  const digits = base.replace(/\D/g, '');
  if (!digits) return '';
  return `+${digits}`;
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

async function createTenantIfNeeded(phone) {
  logger.info({ phone, AUTO_CREATE_TENANT, BACKEND_URL }, '[BAILEYS] createTenantIfNeeded called');

  if (!AUTO_CREATE_TENANT) {
    logger.info({ phone, AUTO_CREATE_TENANT }, '[BAILEYS] AUTO_CREATE_TENANT disabled, cannot create tenant');
    return false;
  }

  logger.info({ phone }, '[BAILEYS] Attempting to auto-create tenant...');

  const payload = {
    phone_number: phone,
    business_name: `Tenant ${phone}`,
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

async function requestAgentReply(phone, messageText) {
  const url = `${BACKEND_URL}/api/tenants/${encodeURIComponent(phone)}/chat`;

  logger.info({ phone, url, messageLength: messageText.length }, '[BAILEYS] Requesting agent reply');

  let response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: messageText }),
    signal: AbortSignal.timeout(45000),
  });

  logger.info({ phone, status: response.status }, '[BAILEYS] Initial response status');

  if (response.status === 404 && AUTO_CREATE_TENANT) {
    logger.info({ phone, AUTO_CREATE_TENANT }, '[BAILEYS] Got 404, attempting to create tenant');
    const created = await createTenantIfNeeded(phone);
    logger.info({ phone, created }, '[BAILEYS] createTenantIfNeeded result');
    if (created) {
      logger.info({ phone }, '[BAILEYS] Tenant created/exists, retrying chat');
      await sleep(300);
      response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: messageText }),
        signal: AbortSignal.timeout(45000),
      });
      logger.info({ phone, retryStatus: response.status }, '[BAILEYS] Retry response status');
    } else {
      logger.warn({ phone }, '[BAILEYS] Failed to create tenant');
    }
  }

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
  const { version } = await fetchLatestBaileysVersion();

  logger.info({ version, backend: BACKEND_URL }, '[BAILEYS] Starting WhatsApp connector');

  const sock = makeWASocket({
    auth: state,
    version,
    printQRInTerminal: false,
    logger: pino({ level: LOG_LEVEL }),
    markOnlineOnConnect: false,
    syncFullHistory: false,
  });

  sock.ev.on('creds.update', saveCreds);

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
      
      // Log the phone number this session is bound to
      if (sock.user) {
        const userPhone = sock.user.id ? sock.user.id.split(':')[0] : 'unknown';
        logger.info({ boundToPhone: `+${userPhone}`, user: sock.user }, '[BAILEYS] ===== SESSION BOUND TO: +${userPhone} =====');
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

      const phone = phoneFromJid(jid);
      const text = extractText(msg.message);

      logger.info({
        jid,
        participant,
        phone,
        fromMe: msg.key.fromMe,
        text: text ? text.substring(0, 50) : 'N/A',
      }, '[BAILEYS] Incoming message details');

      if (!phone || !text) {
        logger.warn({ jid, phone, hasText: !!text }, '[BAILEYS] Skipping: missing phone or text');
        continue;
      }

      logger.info({ phone, jid, text }, '[BAILEYS] Incoming message');

      try {
        await sock.sendPresenceUpdate('composing', jid);
        const responseText = await requestAgentReply(phone, text);
        await sock.sendMessage(jid, { text: responseText });
      } catch (err) {
        logger.error({ err, phone }, '[BAILEYS] Failed to process message');
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
