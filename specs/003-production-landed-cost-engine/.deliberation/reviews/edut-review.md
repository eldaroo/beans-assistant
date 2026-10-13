# Edut Review: Production and Landed-Cost Engine

I observe. I do not vote. I write the moral slice.

## 1. What problem is this solving, and for whom

The CEO wants to know what one bracelet truly costs, landed, per country, so he can price and decide where to produce. That is his problem and it is legitimate. But the platform reaches further than him. The stakeholders:

- The CEO, who gains the margin number and the sourcing decision.
- María, a supplier with her own team, who will log in and enter her production and her input costs.
- Víctor, an independent supplier, same.
- Input suppliers (coffee, roasting, wood, thread, stones, clasps) who will receive automated WhatsApp messages asking for status.
- María's team members, who are behind her login and never see the platform at all.

María and Víctor did not ask for this. They are being asked to do unpaid data entry that feeds a margin calculation they may never see. The input suppliers did not consent to being messaged by a machine. Name them now, because the spec is built for the CEO and the others arrive as data sources.

## 2. Smallest first version that crosses no moral line

Landed cost for one bracelet type in one country, entered by the CEO alone. No supplier logins yet. No automated WhatsApp yet. This proves the core number with zero third party touched. Supplier access and automated messaging are each their own cohort, gated behind explicit consent, never bundled into the proof.

## 3. Three risks that would kill this

1. A supplier whose own cost data is used to squeeze their margin. María enters her labor cost in good faith; the CEO uses it to negotiate her down. This is Never Exploit. The data was given for costing, not for leverage against the giver.
2. A supplier messaged without consent or at a harassing cadence. Scheduled "how is it going" messages to real people, on behalf of the business, with no opt-in and no frequency cap, is coercion by cadence. This is Never Coerce.
3. One supplier sees another's prices, or sees the CEO's margin. Competitive harm and betrayal of confidence. This is Never Betray and Never Exclude at once.

## 4. Success at 90 days, measured by partnership

Every supplier who logs in has given recorded consent and can see and correct every field entered about them. Zero automated message went out without a prior yes. Zero supplier can see another supplier's data. No supplier's entered cost was used to renegotiate their own rate without a conversation they were part of. If those hold, the suppliers are partners. If margins look great and María never saw her own numbers, it failed regardless of the margin.

## 5. Atomic tasks, consent and dignity angle

1. Consent capture before any supplier login is issued; record who, when, for what.
2. Consent capture before any automated WhatsApp send, per recipient, separate from login consent.
3. A supplier's read view of every field stored about them.
4. A supplier's correction path on their own data, with an edit trail.
5. Data-scope isolation at the query layer: a supplier's session can never read another supplier's costs or the margin.
6. Truthful sender identification in the first automated message (this is an automated message from Beans&Co).
7. Frequency cap as schema, not convention, on check-ins.
8. One-tap opt-out of check-ins, honored immediately, logged.
9. Fallback for a free-text reply that does not parse: route to a human, never silently drop.
10. Audit log of every supplier-facing action.

## 6. The one thing only I would have noticed

María "works with a team." Those people are behind her login, doing the labor, and the platform never names them. Consent asked of María is not consent from them. The most affected humans here are the ones who never appear on any screen. Hold that.
