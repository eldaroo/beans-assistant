const fs = require('fs');
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
const ADMIN_PHONE = process.env.BAILEYS_ADMIN_PHONE || '+541153695627';
const ONBOARDING_STATE_FILE =
  process.env.BAILEYS_ONBOARDING_STATE_FILE || `${SESSION_DIR}/onboarding_state.json`;

const logger = pino({ level: LOG_LEVEL });
let onboardingState = defaultOnboardingState();

function ensureSessionDir() {
  fs.mkdirSync(SESSION_DIR, { recursive: true });
}

function defaultOnboardingState() {
  return {
    sessions: {},
    approvals: {},
    nextApprovalId: 1,
  };
}

function saveOnboardingState() {
  fs.writeFileSync(ONBOARDING_STATE_FILE, JSON.stringify(onboardingState, null, 2), 'utf8');
}

function loadOnboardingState() {
  try {
    if (!fs.existsSync(ONBOARDING_STATE_FILE)) {
      onboardingState = defaultOnboardingState();
      saveOnboardingState();
      return;
    }

    const raw = fs.readFileSync(ONBOARDING_STATE_FILE, 'utf8');
    const parsed = raw ? JSON.parse(raw) : {};
    onboardingState = {
      sessions: parsed.sessions || {},
      approvals: parsed.approvals || {},
      nextApprovalId: Number.isInteger(parsed.nextApprovalId) ? parsed.nextApprovalId : 1,
    };
  } catch (err) {
    logger.error({ err }, '[BAILEYS] Failed to load onboarding state, resetting it');
    onboardingState = defaultOnboardingState();
    saveOnboardingState();
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function phoneFromJid(jid) {
  const raw = String(jid || '');
  const [base, domain] = raw.split('@');
  if (!base || !domain) return '';

  // Only treat canonical phone JIDs as tenant identifiers.
  // LID JIDs are WhatsApp-internal identifiers and must not map to tenants.
  if (domain !== 's.whatsapp.net') return '';

  // Baileys can deliver device-specific JIDs like `5491153695627:76@s.whatsapp.net`.
  // The backend tenant key is the phone number only, so strip the device suffix.
  const user = base.split(':')[0];
  if (!user) return '';

  return user.startsWith('+') ? user : `+${user}`;
}

function normalizePhoneNumber(value) {
  const raw = String(value || '');
  if (!raw) return '';

  // `senderPn` / `participantPn` may already come as a phone or as a JID.
  if (raw.includes('@')) return phoneFromJid(raw);

  const user = raw.split(':')[0];
  if (!user) return '';
  return user.startsWith('+') ? user : `+${user}`;
}

function resolveMessagePhone(message) {
  if (!message?.key) return '';

  // Prefer the explicit phone-number fields Baileys exposes when the chat is LID-addressed.
  const directPhone =
    normalizePhoneNumber(message.key.senderPn) ||
    normalizePhoneNumber(message.key.participantPn);

  if (directPhone) return directPhone;
  return phoneFromJid(message.key.remoteJid);
}

function phoneToJid(phone) {
  const normalized = normalizePhoneNumber(phone);
  if (!normalized) return '';
  return `${normalized.replace(/^\+/, '')}@s.whatsapp.net`;
}

function normalizeText(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

function tokenizeNormalized(value) {
  const normalized = normalizeText(value);
  if (!normalized) return [];
  return normalized.split(/\s+/).filter(Boolean);
}

function isAffirmative(value) {
  const firstToken = tokenizeNormalized(value)[0];
  return ['si', 's', 'yes', 'y', 'ok', 'dale', 'quiero'].includes(firstToken);
}

function isNegative(value) {
  const firstToken = tokenizeNormalized(value)[0];
  return ['no', 'n', 'nop', 'cancelar', 'cancel'].includes(firstToken);
}

function getOnboardingSession(phone) {
  return onboardingState.sessions[phone] || null;
}

function updateOnboardingSession(phone, updates) {
  const nextSession = {
    ...(onboardingState.sessions[phone] || {}),
    ...updates,
    phone,
    updatedAt: new Date().toISOString(),
  };
  onboardingState.sessions[phone] = nextSession;
  saveOnboardingState();
  return nextSession;
}

function clearOnboardingSession(phone) {
  const existing = onboardingState.sessions[phone];
  if (!existing) return;

  if (existing.approvalId) {
    delete onboardingState.approvals[String(existing.approvalId)];
  }

  delete onboardingState.sessions[phone];
  saveOnboardingState();
}

function createApprovalRequest(session) {
  const id = String(onboardingState.nextApprovalId || 1);
  onboardingState.nextApprovalId = Number(id) + 1;
  onboardingState.approvals[id] = {
    id,
    phone: session.phone,
    contactName: session.contactName || '',
    businessName: session.businessName || '',
    replyJid: session.replyJid || phoneToJid(session.phone),
    status: 'pending',
    createdAt: new Date().toISOString(),
  };
  saveOnboardingState();
  return onboardingState.approvals[id];
}

function listPendingApprovals() {
  return Object.values(onboardingState.approvals)
    .filter((approval) => approval?.status === 'pending')
    .sort((a, b) => String(a.id).localeCompare(String(b.id), undefined, { numeric: true }));
}

function removeApprovalRequest(id) {
  if (!id) return;
  delete onboardingState.approvals[String(id)];
  saveOnboardingState();
}

async function tenantExists(phone) {
  const response = await fetch(`${BACKEND_URL}/api/tenants/${encodeURIComponent(phone)}`, {
    method: 'GET',
    signal: AbortSignal.timeout(15000),
  });

  if (response.ok) return true;
  if (response.status === 404) return false;

  const detail = await response.text();
  throw new Error(`Tenant lookup ${response.status}: ${detail}`);
}

async function createTenantFromApproval(approval) {
  const payload = {
    phone_number: approval.phone,
    business_name: approval.businessName,
    currency: DEFAULT_TENANT_CURRENCY,
    language: DEFAULT_TENANT_LANGUAGE,
  };

  const response = await fetch(`${BACKEND_URL}/api/tenants`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(30000),
  });

  if (response.ok || response.status === 409) return true;

  const detail = await response.text();
  throw new Error(`Tenant create ${response.status}: ${detail}`);
}

async function notifyAdminOfApprovalRequest(sock, approval) {
  const adminJid = phoneToJid(ADMIN_PHONE);
  if (!adminJid) {
    throw new Error('BAILEYS_ADMIN_PHONE is invalid');
  }

  const adminMessage = [
    '*Nueva solicitud de servicio*',
    `ID: ${approval.id}`,
    `Numero: ${approval.phone}`,
    `Nombre: ${approval.contactName || 'Sin nombre'}`,
    `Empresa: ${approval.businessName || 'Sin empresa'}`,
    '',
    'Respondeme con:',
    `SI ${approval.id} para autorizar`,
    `NO ${approval.id} para rechazar`,
  ].join('\n');

  await sock.sendMessage(adminJid, { text: adminMessage });
}

function parseAdminDecision(text) {
  const tokens = tokenizeNormalized(text);
  if (!tokens.length) return null;

  let approved = null;
  if (['si', 's', 'yes', 'y', 'autorizar', 'aprobar', 'approve'].includes(tokens[0])) {
    approved = true;
  } else if (['no', 'n', 'rechazar', 'denegar', 'deny'].includes(tokens[0])) {
    approved = false;
  } else {
    return null;
  }

  const explicitId = tokens.find((token) => /^\d+$/.test(token));
  if (explicitId) {
    return { approved, approvalId: explicitId };
  }

  const pending = listPendingApprovals();
  if (pending.length === 1) {
    return { approved, approvalId: pending[0].id };
  }

  return { approved, approvalId: '', needsExplicitId: pending.length > 1 };
}

async function handleAdminApprovalMessage(sock, jid, text) {
  const decision = parseAdminDecision(text);
  if (!decision) return false;

  if (decision.needsExplicitId) {
    await sock.sendMessage(jid, {
      text: 'Hay varias solicitudes pendientes. Respondeme con SI <id> o NO <id>.',
    });
    return true;
  }

  if (!decision.approvalId) {
    await sock.sendMessage(jid, {
      text: 'No hay solicitudes pendientes para procesar.',
    });
    return true;
  }

  const approval = onboardingState.approvals[decision.approvalId];
  if (!approval || approval.status !== 'pending') {
    await sock.sendMessage(jid, {
      text: `No encontré una solicitud pendiente con ID ${decision.approvalId}.`,
    });
    return true;
  }

  const clientJid = approval.replyJid || phoneToJid(approval.phone);

  if (decision.approved) {
    try {
      await createTenantFromApproval(approval);
    } catch (err) {
      logger.error({ err, approval }, '[BAILEYS] Failed to create tenant from approval');
      await sock.sendMessage(jid, {
        text: `No pude crear la base para la solicitud ${approval.id}. Reintentá más tarde.`,
      });
      return true;
    }

    clearOnboardingSession(approval.phone);
    if (clientJid) {
      await sock.sendMessage(clientJid, {
        text: 'Listo, tu acceso ya fue autorizado y tu base de datos fue creada. Ya podés usar el servicio.',
      });
    }
    await sock.sendMessage(jid, {
      text: `Solicitud ${approval.id} autorizada. Ya quedó creada la base para ${approval.phone}.`,
    });
    return true;
  }

  updateOnboardingSession(approval.phone, {
    status: 'blocked_by_admin',
    replyJid: clientJid,
    contactName: approval.contactName,
    businessName: approval.businessName,
    approvalId: null,
  });
  removeApprovalRequest(approval.id);

  if (clientJid) {
    await sock.sendMessage(clientJid, {
      text: 'Por ahora tu solicitud no fue autorizada. No voy a seguir respondiendo a este número.',
    });
  }
  await sock.sendMessage(jid, {
    text: `Solicitud ${approval.id} rechazada. ${approval.phone} quedó sin acceso.`,
  });
  return true;
}

async function handleUnknownTenantMessage(sock, jid, phone, text) {
  const current = getOnboardingSession(phone);

  if (current?.status === 'opted_out' || current?.status === 'blocked_by_admin') {
    logger.info({ phone, status: current.status }, '[BAILEYS] Ignoring blocked contact');
    return true;
  }

  if (!current) {
    updateOnboardingSession(phone, {
      status: 'awaiting_service_confirmation',
      replyJid: jid,
    });
    await sock.sendMessage(jid, {
      text: 'Hola. Tu número todavía no está habilitado. ¿Querés usar el servicio? Respondeme SI o NO.',
    });
    return true;
  }

  if (current.status === 'awaiting_service_confirmation') {
    if (isAffirmative(text)) {
      updateOnboardingSession(phone, {
        status: 'awaiting_contact_name',
        replyJid: jid,
      });
      await sock.sendMessage(jid, {
        text: 'Perfecto. ¿Cómo te llamás?',
      });
      return true;
    }

    if (isNegative(text)) {
      updateOnboardingSession(phone, {
        status: 'opted_out',
        replyJid: jid,
      });
      await sock.sendMessage(jid, {
        text: 'Entendido. No te voy a seguir respondiendo por este número.',
      });
      return true;
    }

    await sock.sendMessage(jid, {
      text: 'Necesito que me respondas SI si querés usar el servicio o NO si no te interesa.',
    });
    return true;
  }

  if (current.status === 'awaiting_contact_name') {
    const contactName = String(text || '').trim();
    if (!contactName) {
      await sock.sendMessage(jid, {
        text: 'Necesito tu nombre para continuar.',
      });
      return true;
    }

    updateOnboardingSession(phone, {
      status: 'awaiting_business_name',
      replyJid: jid,
      contactName,
    });
    await sock.sendMessage(jid, {
      text: `Gracias, ${contactName}. ¿Para qué empresa sería?`,
    });
    return true;
  }

  if (current.status === 'awaiting_business_name') {
    const businessName = String(text || '').trim();
    if (!businessName) {
      await sock.sendMessage(jid, {
        text: 'Necesito el nombre de la empresa para continuar.',
      });
      return true;
    }

    const session = updateOnboardingSession(phone, {
      status: 'awaiting_business_name',
      replyJid: jid,
      businessName,
    });
    const approval = createApprovalRequest({
      ...session,
      status: 'pending_admin_approval',
      businessName,
      replyJid: jid,
    });

    updateOnboardingSession(phone, {
      status: 'pending_admin_approval',
      replyJid: jid,
      contactName: session.contactName,
      businessName,
      approvalId: approval.id,
    });

    await notifyAdminOfApprovalRequest(sock, approval);
    await sock.sendMessage(jid, {
      text: 'Gracias. Ya envié tu solicitud de alta. Te aviso apenas quede autorizada.',
    });
    return true;
  }

  if (current.status === 'pending_admin_approval') {
    updateOnboardingSession(phone, { replyJid: jid });
    await sock.sendMessage(jid, {
      text: 'Tu solicitud sigue pendiente de aprobación. Te aviso apenas quede habilitada.',
    });
    return true;
  }

  return false;
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
  loadOnboardingState();

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
      logger.info('[BAILEYS] WhatsApp connected');
      return;
    }

    if (connection === 'close') {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      logger.warn({ statusCode, shouldReconnect }, '[BAILEYS] Connection closed');

      if (shouldReconnect) {
        setTimeout(() => {
          startWhatsApp().catch((err) => {
            logger.error({ err }, '[BAILEYS] Reconnect failed');
          });
        }, RECONNECT_DELAY_MS);
      } else {
        logger.error('[BAILEYS] Logged out. Delete session and re-scan QR.');
      }
    }
  });

  sock.ev.on('messages.upsert', async ({ type, messages }) => {
    if (type !== 'notify') return;

    for (const msg of messages) {
      if (!isSupportedIncomingMessage(msg)) continue;

      const jid = msg.key.remoteJid;
      const phone = resolveMessagePhone(msg);
      const text = extractText(msg.message);

      if (!phone || !text) {
        logger.warn(
          {
            jid,
            senderPn: msg.key.senderPn,
            participantPn: msg.key.participantPn,
            senderLid: msg.key.senderLid,
            participantLid: msg.key.participantLid,
          },
          '[BAILEYS] Skipping message without canonical phone mapping'
        );
        continue;
      }

      logger.info({ phone, jid, text }, '[BAILEYS] Incoming message');

      try {
        const adminApprovalHandled = phone === ADMIN_PHONE
          ? await handleAdminApprovalMessage(sock, jid, text)
          : false;

        if (adminApprovalHandled) continue;

        const knownTenant = await tenantExists(phone);
        if (knownTenant) {
          if (getOnboardingSession(phone)) {
            clearOnboardingSession(phone);
          }

          await sock.sendPresenceUpdate('composing', jid);
          const responseText = await requestAgentReply(phone, text);
          await sock.sendMessage(jid, { text: responseText });
          continue;
        }

        if (phone === ADMIN_PHONE) {
          logger.info({ phone }, '[BAILEYS] Admin message ignored because there is no tenant and no approval command');
          continue;
        }

        const handled = await handleUnknownTenantMessage(sock, jid, phone, text);
        if (handled) continue;
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
