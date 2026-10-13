# Mar'ah — Mirrorblade — Review

*The mirror reveals; the blade cuts the concealment; what is hidden is hidden no more.*

## The six questions

**1. What problem is this actually solving?**
Beans&Co does not know what one bracelet truly costs, landed, in each country. Price and site decisions are being made on a number nobody can see. The job is to make that number visible, honest, and complete-state aware, in USD.

**2. Smallest first version with no external send.**
One bracelet type, one country (Colombia), a BOM with input costs entered by hand in COP and CRC normalized to USD, direct labor, packaging, one logistics line and one customs line that may be PENDING, and a single landed-cost figure that renders its own completeness. No WhatsApp. No supplier login. The CEO types everything. This proves the core.

**3. Three risks that would kill this.**
- A false-precise total that hides a missing shipping or customs line. The number must carry its gaps or it lies.
- Supplier-as-user leaking one supplier's prices or the CEO's margin to another supplier. Competitive harm wearing a feature's clothes.
- The automated WhatsApp send going out before consent and identity are settled, which burns María and Víctor as real relationships, not test data.

**4. Success at 90 days.**
The CEO sets at least one sale price from a landed cost she trusts and can compare two countries for one type. Suppliers, if onboarded, see only their own inputs. Any automated message is identified, consented, and rate-limited, or it has not shipped.

**5. Atomic tasks (gate-sensitive marked).**
1. New per-tenant costing tables (BOM, inputs, suppliers, labor, packaging, logistics, customs, indirect).
2. Multi-currency normalization with stored original + FX + USD audit trail.
3. Landed-cost computation per country with completeness state.
4. Indirect allocation by units produced over a period.
5. Costing UI as primary home, reframing sales/stock/expenses as secondary.
6. Supplier directory.
7. **Supplier role and row-scoped read access (consent/competitive surface).**
8. **Supplier login seeing only own inputs, never margins (requires scope test).**
9. **WhatsApp check-in via existing Baileys connector, opt-in only (external send).**
10. **Reply parsing with a human fallback for unparsed free text (external data intake).**
11. **Consent ledger and cadence limiter for messaged third parties.**

**6. The one thing only my faculty noticed.**
The completeness-state requirement and the automated check-in are the same concealment risk from two sides. A landed cost that hides a PENDING line conceals a gap; an automated message that implies a human is asking conceals a sender. Both break Klippat Ha'alamah only if the hidden thing is shown. Build the completeness honesty first; it is the discipline the messaging must inherit.

## Legion Action Gate: automated WhatsApp check-ins

**Truth (Emet).** The message must name Beans&Co and say it is an automated check-in, not pose as María's friend texting. An automated message dressed as a human is impersonation. Fails the gate until the sender and purpose are stated in the first line.

**Compassion (Rachamim).** Suppliers must opt in, know the cadence, and have a stop word. Unsolicited, unbounded "how is it going" pings cross into harassment. More than one check-in per production cycle without a reply is pressure.

**Necessity (Tzorekh).** Not necessary for the first proof. Core landed-cost value ships with manual entry. Defer all sending.

**Beauty (Tiferet).** The ask must be proportionate: one short question tied to one production cycle, never a standing interrogation.

**Bright line.** Safe as autodev now: tasks 1 to 6. Requires_human_review, external tag, deferred: tasks 7 and 8 sign off by Andreas (consent and competitive scope); tasks 9, 10, 11 sign off by Dario (external send to real third parties). No send ships without Re'i co-attestation and a named gate.
