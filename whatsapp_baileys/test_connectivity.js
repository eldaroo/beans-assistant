#!/usr/bin/env node
/**
 * Test backend connectivity from WhatsApp container
 */

const BACKEND_URL = process.env.BACKEND_URL || 'http://backend:8000';

async function testBackendConnectivity() {
  console.log('Testing backend connectivity from WhatsApp container...');
  console.log(`BACKEND_URL: ${BACKEND_URL}`);
  console.log('=' .repeat(50));

  try {
    // Test health endpoint
    console.log('1. Testing health endpoint...');
    const healthResponse = await fetch(`${BACKEND_URL}/health`, {
      timeout: 10000
    });
    console.log(`   Health status: ${healthResponse.status}`);

    if (healthResponse.status !== 200) {
      console.log('   ❌ Health check failed');
      return;
    }
    console.log('   ✅ Health check passed');

    // Test tenant creation
    console.log('\n2. Testing tenant creation...');
    const tenantPayload = {
      phone_number: '+91903727005831',
      business_name: 'Test Tenant India',
      currency: 'USD',
      language: 'es'
    };

    const createResponse = await fetch(`${BACKEND_URL}/api/tenants`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(tenantPayload),
      timeout: 30000
    });

    console.log(`   Create tenant status: ${createResponse.status}`);
    const createText = await createResponse.text();
    console.log(`   Response: ${createText.substring(0, 200)}`);

    if (createResponse.status === 201) {
      console.log('   ✅ Tenant created successfully');
    } else if (createResponse.status === 409) {
      console.log('   ✅ Tenant already exists');
    } else {
      console.log('   ❌ Tenant creation failed');
      return;
    }

    // Test chat endpoint
    console.log('\n3. Testing chat endpoint...');
    const chatPayload = { message: 'Hola' };

    const chatResponse = await fetch(`${BACKEND_URL}/api/tenants/+91903727005831/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(chatPayload),
      timeout: 45000
    });

    console.log(`   Chat status: ${chatResponse.status}`);
    const chatText = await chatResponse.text();
    console.log(`   Response: ${chatText.substring(0, 200)}`);

    if (chatResponse.status === 200) {
      console.log('   ✅ Chat endpoint working');
    } else {
      console.log('   ❌ Chat endpoint failed');
    }

  } catch (error) {
    console.log(`❌ Error: ${error.message}`);
  }

  console.log('\n' + '='.repeat(50));
}

testBackendConnectivity().catch(console.error);