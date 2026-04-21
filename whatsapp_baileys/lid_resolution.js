function normalizeText(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

function tokenize(value) {
  const normalized = normalizeText(value);
  return normalized ? normalized.split(' ') : [];
}

function scoreMatch(query, candidate) {
  const normalizedQuery = normalizeText(query);
  const normalizedCandidate = normalizeText(candidate);

  if (!normalizedQuery || !normalizedCandidate) return 0;
  if (normalizedQuery === normalizedCandidate) return 100;
  if (
    normalizedQuery.includes(normalizedCandidate) ||
    normalizedCandidate.includes(normalizedQuery)
  ) {
    return 80;
  }

  const queryTokens = new Set(tokenize(query));
  const candidateTokens = new Set(tokenize(candidate));
  if (!queryTokens.size || !candidateTokens.size) return 0;

  let sharedTokens = 0;
  for (const token of queryTokens) {
    if (candidateTokens.has(token)) sharedTokens += 1;
  }

  if (!sharedTokens) return 0;

  const coverage = sharedTokens / Math.max(queryTokens.size, candidateTokens.size);
  if (coverage >= 1) return 70;
  if (coverage >= 0.66) return 50;
  if (coverage >= 0.5) return 30;
  return 0;
}

function phoneFromPnJid(jid) {
  const base = String(jid || '').split('@')[0].trim();
  if (!base) return '';

  const digits = base.replace(/\D/g, '');
  if (!digits) return '';

  return `+${digits}`;
}

function isActiveTenant(tenant) {
  const status = String(tenant?.status || '').toLowerCase();
  return !status || status === 'active';
}

function resolveTenantPhoneFromHeuristics(tenants, senderName) {
  const normalizedSender = normalizeText(senderName);
  if (!normalizedSender) return '';

  const tenantList = Array.isArray(tenants) ? tenants : [];
  const activeTenants = tenantList.filter(isActiveTenant);
  const candidates = activeTenants.length > 0 ? activeTenants : tenantList;

  if (candidates.length === 1) {
    return String(candidates[0]?.phone_number || '').trim();
  }

  let bestPhone = '';
  let bestScore = 0;
  let hasTie = false;

  for (const tenant of candidates) {
    const phone = String(tenant?.phone_number || '').trim();
    if (!phone) continue;

    const ownerScore = scoreMatch(senderName, tenant?.owner_name);
    const businessScore = scoreMatch(senderName, tenant?.business_name);
    const score = Math.max(ownerScore, businessScore);

    if (score > bestScore) {
      bestScore = score;
      bestPhone = phone;
      hasTie = false;
    } else if (score > 0 && score === bestScore && phone !== bestPhone) {
      hasTie = true;
    }
  }

  if (hasTie || bestScore <= 0) {
    return '';
  }

  return bestPhone;
}

function resolvePhoneFromMessageKey(messageKey) {
  if (!messageKey) return '';

  return (
    phoneFromPnJid(messageKey.senderPn) ||
    phoneFromPnJid(messageKey.participantPn)
  );
}

async function fetchTenantsForLidResolution(fetchImpl = global.fetch) {
  if (typeof fetchImpl !== 'function') return [];

  const backendUrl = (process.env.BACKEND_URL || 'http://backend:8000').replace(/\/$/, '');
  const url = `${backendUrl}/api/tenants?limit=200`;

  try {
    const response = await fetchImpl(url, {
      signal: AbortSignal.timeout(15000),
    });

    if (!response.ok) {
      return [];
    }

    const data = await response.json();
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

async function resolvePhoneFromTenantHeuristicsAsync(senderName, fetchImpl = global.fetch) {
  const tenants = await fetchTenantsForLidResolution(fetchImpl);
  return resolveTenantPhoneFromHeuristics(tenants, senderName);
}

module.exports = {
  fetchTenantsForLidResolution,
  resolvePhoneFromMessageKey,
  resolvePhoneFromTenantHeuristics: resolvePhoneFromTenantHeuristicsAsync,
  resolveTenantPhoneFromHeuristics,
};
