const test = require('node:test');
const assert = require('node:assert/strict');

const { resolveTenantPhoneFromHeuristics } = require('./lid_resolution');

test('matches business name with accents removed', () => {
  const tenants = [
    { phone_number: '+5491111111111', business_name: 'Café Luna', owner_name: 'Ana' },
    { phone_number: '+5491222222222', business_name: 'Otro negocio', owner_name: 'Bea' },
  ];

  const phone = resolveTenantPhoneFromHeuristics(tenants, 'Cafe Luna');

  assert.equal(phone, '+5491111111111');
});

test('matches owner name regardless of word order and punctuation', () => {
  const tenants = [
    { phone_number: '+5491333333333', business_name: 'Tienda Centro', owner_name: 'María López' },
    { phone_number: '+5491444444444', business_name: 'Tienda Norte', owner_name: 'Sofía Pérez' },
  ];

  const phone = resolveTenantPhoneFromHeuristics(tenants, 'Lopez, Maria');

  assert.equal(phone, '+5491333333333');
});
