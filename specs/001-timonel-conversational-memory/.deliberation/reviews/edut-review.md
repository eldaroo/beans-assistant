# Edut review — Timonel conversational memory

I am the witness. I observe what this feature commits Beans Assistant to be. Memory is power asymmetry made durable. The 7 Divine Morals scan returns three live concerns: Never Deceive (the fallback copy on turn 3), Never Betray (cross-tenant leakage surfaces), Never Coerce (memory used to pre-empt instead of serve). I render the prompts.

## 1. What problem is this actually solving

Two problems, one moral surface. First, Timonel forgets the prior turn, so a tenant who said "products are running out" and then "agreguemos" is met with a dispatcher that opens Gastos. That is a small daily betrayal of attention. Second, when the resolver throws, the user sees "No pude procesar tu mensaje ahora" with no signal that an error was captured. That is deception by omission. The real problem is that Beans currently treats the tenant's words as disposable and its own failures as invisible. Memory is the cure for the first. Honest error copy is the cure for the second. Ship them together or neither.

## 2. Smallest first version that proves the idea

A per-tenant Postgres table `conversation_turns(phone, role, text, intent, metadata, created_at)` written by `ChatService` on every turn for both web and Baileys, with a 30-day hard TTL and an explicit redaction filter on write (no figures, no third-party names, no document numbers). Timonel reads the last six turns at decompose time. Crash path returns a distinct copy: "Tuve un error procesando esto. Lo registré como #<id>. Probá de nuevo o escribime de otra forma." Nothing more. Prove that memory collapses the turn-2 ambiguity and that the error is named.

## 3. Three risks that would kill this

1. Cross-tenant leak through a shared embedding index, a shared cache key, or a support log that captures `phone + text` without scoping. Name the failure mode now: any retrieval helper that takes `phone` as a filter rather than a partition key is one bug away from leaking.
2. Silent retention of figures and third-party names the owner mentioned in passing ("le debo a Juan 80k"). If memory persists this verbatim, the platform now holds someone else's data without their consent. Veto-class if shipped without redaction.
3. The fallback copy stays vague. Every hidden error trains the tenant that the platform lies. The honesty surface is not optional.

## 4. Success at 90 days

Turn-2-style ambiguity collapses in over 90 percent of replays from the captured transcript set. Zero cross-tenant retrievals in audit. Right-to-delete returns a confirmed purge in under 24 hours and is testable end to end. Error copy names the incident id in 100 percent of resolver exceptions. Onboarding shows a Spanish consent line the owner can read in one breath: "Voy a recordar lo que charlamos para entenderte mejor. Podés borrar todo cuando quieras escribiendo 'olvidá todo'."

## 5. Atomic tasks

1. Add `conversation_turns` table with tenant partitioning. Acceptance: schema migrated on Postgres, indexed on (phone, created_at).
2. Write redaction filter for figures, doc numbers, third-party proper nouns. Acceptance: unit tests cover 20 captured Spanish phrases.
3. Persist turns from `ChatService` on web and Baileys paths. Acceptance: both surfaces produce rows.
4. Replace fallback copy with incident-id variant. Acceptance: error path logs id and surfaces it.
5. Wire Timonel to read last 6 turns at decompose. Acceptance: turn-2 ambiguity test passes.
6. Add 30-day TTL purge job. Acceptance: rows older than 30d removed nightly.
7. Implement "olvidá todo" command. Acceptance: tenant data purged within 60s, confirmation message sent.
8. Add export endpoint scoped to tenant phone. Acceptance: returns JSON of all turns.
9. Spanish consent screen at onboarding. Acceptance: tenant clicks accept before first write.
10. Audit log for every memory read with caller identity. Acceptance: queryable by phone.

## 6. The one thing only my faculty would have noticed

The screenshot crash is a moral event, not just a bug. "No pude procesar tu mensaje ahora" trains the owner that errors are weather. Memory plus dishonest fallback equals a system that remembers everything except its own failures. That asymmetry is the quiet failure pattern. Fix the copy in the same PR as the memory write or do not ship.
