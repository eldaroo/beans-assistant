# WhatsApp Connector (Baileys)

This service connects WhatsApp using Baileys and forwards incoming messages to:

- `POST /api/tenants/{phone}/chat`

## Environment Variables

- `BACKEND_URL` (default: `http://backend:8000`)
- `BAILEYS_SESSION_DIR` (default: `/app/.baileys_auth`)
- `BAILEYS_LOG_LEVEL` (default: `info`)
- `BAILEYS_RECONNECT_DELAY_MS` (default: `5000`)
- `BAILEYS_AUTO_CREATE_TENANT` (default: `false`)
- `BAILEYS_DEFAULT_CURRENCY` (default: `USD`)
- `BAILEYS_DEFAULT_LANGUAGE` (default: `es`)

## Local Run

```bash
cd whatsapp_baileys
npm install
BACKEND_URL=http://localhost:8000 node server.js
```

On first start it prints a QR in terminal; scan it with WhatsApp.
