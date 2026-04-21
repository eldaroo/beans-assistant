const fs = require('fs');
const path = require('path');

const ASSET_FILES = {
  onboarding_welcome: path.join(__dirname, 'assets', 'onboarding_welcome.png'),
};

function buildOutboundMessages(payload = {}) {
  const structuredMessages = Array.isArray(payload.messages) ? payload.messages : [];
  const outbound = [];

  for (const part of structuredMessages) {
    if (part?.type === 'image' && part.asset_key) {
      outbound.push({
        type: 'image',
        asset_key: part.asset_key,
        caption: part.caption || '',
      });
      continue;
    }

    if (part?.type === 'text' && String(part.text || '').trim()) {
      outbound.push({ text: String(part.text).trim() });
    }
  }

  if (!outbound.length && payload.response) {
    outbound.push({ text: payload.response });
  }

  return outbound;
}

function resolveOnboardingAssetPath(assetKey) {
  return ASSET_FILES[assetKey] || null;
}

async function sendOnboardingMessages(sock, jid, payload, logger) {
  const outboundMessages = buildOutboundMessages(payload);

  for (const outboundMessage of outboundMessages) {
    if (outboundMessage.type === 'image') {
      const assetPath = resolveOnboardingAssetPath(outboundMessage.asset_key);
      if (!assetPath || !fs.existsSync(assetPath)) {
        logger?.warn?.({ assetKey: outboundMessage.asset_key }, '[BAILEYS] Onboarding asset missing, falling back to text');
        if (payload.response) {
          await sock.sendMessage(jid, { text: payload.response });
          return;
        }
        continue;
      }

      try {
        await sock.sendMessage(jid, {
          image: { url: assetPath },
          caption: outboundMessage.caption || undefined,
        });
      } catch (err) {
        logger?.warn?.({ err, assetKey: outboundMessage.asset_key }, '[BAILEYS] Failed to send onboarding image, falling back to text');
        if (payload.response) {
          await sock.sendMessage(jid, { text: payload.response });
          return;
        }
      }
      continue;
    }

    if (outboundMessage.text) {
      await sock.sendMessage(jid, { text: outboundMessage.text });
    }
  }
}

module.exports = {
  buildOutboundMessages,
  resolveOnboardingAssetPath,
  sendOnboardingMessages,
};
