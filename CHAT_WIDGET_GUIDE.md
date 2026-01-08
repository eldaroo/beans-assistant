# Chat Widget - Quick Start Guide

## Overview

A chat widget has been integrated into the tenant detail pages, allowing users to interact with the AI agent specific to each tenant's database.

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- `fastapi`
- `uvicorn`
- `langchain`
- `langchain-google-genai`
- `langgraph`
- `python-dotenv`

### 2. Configure Environment

Make sure your `.env` file contains:
```
GOOGLE_API_KEY=your_api_key_here
```

### 3. Start the Backend

```bash
python backend/app.py
```

Server will start on `http://localhost:8000`

## Usage

1. Navigate to a tenant page: `http://localhost:8000/tenants/{phone}`
2. Click the purple chat button (💬) in the bottom-right corner
3. Type your message and press Enter

### Example Messages

- **Analytics**: "cuántos productos tengo?"
- **Sales**: "registra una venta de 5 pulseras negras"
- **Stock**: "muéstrame el stock actual"

## Files Created

- `backend/api/chat_tenant.py` - Chat API endpoint
- `backend/static/css/chat_widget.css` - Widget styles
- `backend/static/js/chat_widget.js` - Widget JavaScript

## Files Modified

- `backend/app.py` - Registered chat router
- `backend/templates/base.html` - Added CSS link
- `backend/templates/tenant_detail.html` - Added JS script

## API Endpoint

```
POST /api/tenants/{phone}/chat
Body: {"message": "your message here"}
Response: {"response": "agent response", "metadata": {...}}
```

## Troubleshooting

**Widget doesn't appear**: Check browser console for errors, verify you're on a tenant detail page

**No response**: Ensure backend is running and `GOOGLE_API_KEY` is set

**Import errors**: Run `pip install -r requirements.txt`

For detailed documentation, see [walkthrough.md](file:///C:/Users/loko_/.gemini/antigravity/brain/301b700d-8ce0-438d-ae0d-edf58ee26a64/walkthrough.md)
