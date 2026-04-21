const test = require('node:test');
const assert = require('node:assert/strict');

const { buildOutboundMessages } = require('./onboarding_messages');

test('keeps fallback text when structured messages are missing', () => {
  const outbound = buildOutboundMessages({
    response: 'Solo texto',
    metadata: {},
  });

  assert.deepEqual(outbound, [{ text: 'Solo texto' }]);
});

test('translates onboarding structured messages into outbound sends', () => {
  const outbound = buildOutboundMessages({
    response: 'fallback',
    messages: [
      { type: 'image', asset_key: 'onboarding_welcome', caption: 'Beans assistant' },
      { type: 'text', text: 'Paso 1 de 2' },
    ],
    metadata: {},
  });

  assert.equal(outbound[0].type, 'image');
  assert.equal(outbound[0].asset_key, 'onboarding_welcome');
  assert.equal(outbound[0].caption, 'Beans assistant');
  assert.deepEqual(outbound[1], { text: 'Paso 1 de 2' });
});
