# Compass review — Beans native-tool-use chat (spec 006)

Faculty: Strategy and EOS. Angle: product discipline. The question I hold is not "can the chat do all 20-plus operations" but "which three or four jobs justify it existing, and what must stay out so it does those well."

## 1. What problem is this actually solving

One founder runs one business across three countries from scattered WhatsApp threads. The real problem is not "no software." The command center already exists. The problem is friction between a thought and a recorded fact: he sells something or spends something while mobile, and logging it later means opening a module and filling a form he will skip. The chat solves capture-at-the-moment and one-question status. It is a mouth and an ear for a surface he already has, not a second surface.

## 2. Smallest first version that proves the idea

Three jobs-to-be-done, nothing else:
- Log a sale fast (REGISTER_SALE) with the confirm card.
- Log an expense fast (REGISTER_EXPENSE) with the confirm card.
- Ask the state of the business: today's caja Resultado, current stock, what needs attention. These map to reads the command center already computes.

If those three feel instant and correct, the idea is proven. If they do not, no breadth of operations rescues it.

## 3. Three risks that would kill this

- Scope sprawl. Twelve writes and eight module snapshots wired at once produces a copilot that half-does everything and earns no daily habit. A tool the founder cannot trust to log a sale cleanly will be abandoned for WhatsApp.
- A confirmed-but-wrong write. The model proposing a plausible but incorrect sale amount, and the operator confirming on reflex, poisons the one database both the chat and the command center read. Trust dies on the first silent bad commit.
- The chat becoming the only write path for Costos, Produccion, Logistica, Proveedores. Those are read-only in the UI today. If the chat is the sole way to write them, it stops being optional and becomes load-bearing infrastructure, which the first version is not built to be.

## 4. Success at 90 days

A leading-indicator scorecard, not a feature count. Weekly: number of sales and expenses logged through the chat versus total, trending up and crossing half. Percent of write proposals confirmed without edit (a correctness proxy, target high). Count of confirmed writes later cancelled via CANCEL_SALE or CANCEL_EXPENSE (bad-commit proxy, target near zero). One qualitative check: does the founder ask the chat "how are we doing" before opening a module. If yes, it has replaced the WhatsApp reflex.

## 5. Atomic tasks (each one day or less)

1. Define the narrow MCP tool set: the three core tools only (register_sale, register_expense, business_status).
2. Wire each tool to the authenticated internal operation API; box holds no DB.
3. Resolve business from session cookie; drop phone from the chat URL per the packet default.
4. Build business_status to read caja Resultado, stock_current, and the attention aggregation.
5. Port the Wal confirm card into the chat widget for writes.
6. Swap ChatService.chat_with_tenant to drive the native tool loop; retire graph.py and agents/*.
7. Move child lifecycle to one child per request, tools-enabled, built-ins disallowed.
8. Add the four scorecard counters to metadata for the 90-day read.
9. End-to-end prod verify: log a sale, log an expense, ask status, cancel a sale.

## 6. The one thing only my faculty noticed

The chat's "what needs attention today" answer must be the same attention-strip the command center already aggregates (attention_service.py), not a second opinion the model invents. One source of truth, two voices. If the chat says one thing and the strip says another, the founder trusts neither, and the EOS discipline of a single honest scorecard is broken before it starts.
