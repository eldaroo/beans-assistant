#!/usr/bin/env node
/**
 * Baileys Session Diagnostic
 * Inspects the session directory to understand which phone Baileys is bound to
 */

const fs = require('fs');
const path = require('path');

const SESSION_DIR = process.env.BAILEYS_SESSION_DIR || '/app/.baileys_auth';

console.log('\n' + '='.repeat(60));
console.log('BAILEYS SESSION DIAGNOSTIC');
console.log('='.repeat(60));

console.log(`\nChecking session dir: ${SESSION_DIR}`);

if (!fs.existsSync(SESSION_DIR)) {
  console.log('❌ Session directory does not exist!');
  process.exit(1);
}

// List all files in session dir
console.log('\nSession files found:');
const files = fs.readdirSync(SESSION_DIR);
files.forEach(f => {
  const fullPath = path.join(SESSION_DIR, f);
  const stat = fs.statSync(fullPath);
  const size = stat.isDirectory() ? '[DIR]' : `${stat.size} bytes`;
  console.log(`  - ${f} ${size}`);
});

// Try to read creds.json to see which phone this session is bound to
const credsPath = path.join(SESSION_DIR, 'creds.json');
if (fs.existsSync(credsPath)) {
  try {
    console.log('\n[CREDS.JSON CONTENTS]');
    const creds = JSON.parse(fs.readFileSync(credsPath, 'utf8'));
    
    if (creds.me) {
      console.log(`  Me ID: ${creds.me.id}`);
      console.log(`  Me JID: ${creds.me.jid || 'N/A'}`);
      console.log(`  Me name: ${creds.me.name || 'N/A'}`);
    }
    
    if (creds.account) {
      console.log(`  Account First Name: ${creds.account.firstNameL || 'N/A'}`);
      console.log(`  Account Status: ${creds.account.status || 'N/A'}`);
    }
    
    if (creds.me && creds.me.id) {
      const parts = creds. me.id.split(':');
      console.log(`\n✓ This session is bound to phone: +${parts[0]}`);
    }
  } catch (e) {
    console.log(`  Error reading creds: ${e.message}`);
  }
} else {
  console.log('\n❌ creds.json not found - session not authenticated yet');
}

// Try to read pre-keys to estimate activity
const preKeysPath = path.join(SESSION_DIR, 'pre-keys');
if (fs.existsSync(preKeysPath)) {
  const preKeyFiles = fs.readdirSync(preKeysPath);
  console.log(`\n[PRE-KEYS COUNT]: ${preKeyFiles.length} (normal: 20-100)`);
}

console.log('\n' + '='.repeat(60));
