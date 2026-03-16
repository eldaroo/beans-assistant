const fs = require('fs');
const http = require('http');
const pino = require('pino');
const qrcode = require('qrcode-terminal');
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

const healthServer = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    const healthy = waStatus === 'connected';
    res.writeHead(healthy ? 200 : 503, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: healthy ? 'healthy' : 'unhealthy', whatsapp: waStatus }));
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
  return base.startsWith('+') ? base : `+${base}`;
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
  if (!AUTO_CREATE_TENANT) return false;

  const payload = {
    phone_number: phone,
    business_name: `Tenant ${phone}`,
    currency: DEFAULT_TENANT_CURRENCY,
    language: DEFAULT_TENANT_LANGUAGE,
  };

  const response = await fetch(`${BACKEND_URL}/api/tenants`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(30000),
  });

  if (response.ok) {
    logger.info({ phone }, '[BAILEYS] Tenant auto-created');
    return true;
  }

  if (response.status === 400) {
    const text = await response.text();
    if (text.toLowerCase().includes('already exists')) return true;
  }

  const detail = await response.text();
  logger.warn({ phone, status: response.status, detail }, '[BAILEYS] Failed to auto-create tenant');
  return false;
}

async function requestAgentReply(phone, messageText) {
  const url = `${BACKEND_URL}/api/tenants/${encodeURIComponent(phone)}/chat`;

  let response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: messageText }),
    signal: AbortSignal.timeout(45000),
  });

  if (response.status === 404 && AUTO_CREATE_TENANT) {
    const created = await createTenantIfNeeded(phone);
    if (created) {
      await sleep(300);
      response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: messageText }),
        signal: AbortSignal.timeout(45000),
      });
    }
  }

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Backend ${response.status}: ${detail}`);
  }

  const data = await response.json();
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
      logger.info('[BAILEYS] Scan this QR to login:');
      qrcode.generate(qr, { small: true });
    }

    if (connection === 'open') {
      waStatus = 'connected';
      logger.info('[BAILEYS] WhatsApp connected');
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
    if (type !== 'notify') return;

    for (const msg of messages) {
      if (!isSupportedIncomingMessage(msg)) continue;

      const jid = msg.key.remoteJid;
      const phone = phoneFromJid(jid);
      const text = extractText(msg.message);

      if (!phone || !text) continue;

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
