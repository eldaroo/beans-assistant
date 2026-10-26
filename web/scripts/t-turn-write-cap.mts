// Named test for spec 010 M5 T-023 (AC-T6): the per-turn write cap bounds auto-post fan-out.
// PURE: no DB, no model, no network. Run: npx tsx scripts/t-turn-write-cap.mts
//
// THE RISK (Tamir): numeralIsGrounded is SET-MEMBERSHIP, not consumption. One grounded numeral
// in the operator's turn ("vendi 3 medias") grounds the quantity 3 for AS MANY auto-sales as the
// model chooses to stage from that one turn; the per-session window cap (lib/audit, 60/window)
// would let a whole burst auto-post. demoteOverTurnCap holds the fan-out of a SINGLE turn to
// TURN_AUTO_CAP: the first `cap` auto writes auto-post, every further one is demoted to a confirm
// card. This test drives a loop of staged auto writes from one turn and asserts the cap holds.
import { demoteOverTurnCap, TURN_AUTO_CAP, type Verdict } from "@/lib/verdict";

let fails = 0;
function check(name: string, cond: boolean, detail = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  :: " + detail : ""}`);
  if (!cond) fails++;
}

const auto: Verdict = { auto: true, requiresHumanReview: false, reasons: [] };
const confirm: Verdict = { auto: false, requiresHumanReview: true, reasons: ["irreversible-op"] };

// --- 1. below the cap: an auto write stays auto ------------------------------------------------
check("prior=0 (first write) stays auto", demoteOverTurnCap(auto, 0, 3).auto === true);
check("prior=cap-1 stays auto", demoteOverTurnCap(auto, 2, 3).auto === true);

// --- 2. at/above the cap: an auto write is demoted to a confirm card ----------------------------
const atCap = demoteOverTurnCap(auto, 3, 3);
check("prior=cap -> demoted to auto:false", atCap.auto === false, atCap.reasons.join(","));
check("  ...requires human review", atCap.requiresHumanReview === true);
check("  ...reason names the per-turn cap", atCap.reasons.some((r) => r.startsWith("per-turn-write-cap")), atCap.reasons.join(","));
check("prior>cap -> still demoted", demoteOverTurnCap(auto, 9, 3).auto === false);

// --- 3. a non-auto verdict is NEVER touched (the cap only demotes, never promotes) -------------
const keptConfirm = demoteOverTurnCap(confirm, 99, 3);
check("a confirm-only verdict is unchanged regardless of count", keptConfirm.auto === false && keptConfirm.reasons.join(",") === "irreversible-op", keptConfirm.reasons.join(","));

// --- 4. the loop: one turn stages N auto writes; exactly `cap` auto-post, the rest confirm ------
// Model `countAutoForTurn` as monotonically counting the PRIOR auto writes: write i sees i-1 prior
// auto (because each prior auto write incremented the count). This mirrors stageOperation staging
// the current row auto=NULL first, so it is never in its own prior count.
const cap = 3;
let priorAuto = 0;
const outcomes: boolean[] = [];
for (let i = 0; i < 7; i++) {
  const v = demoteOverTurnCap(auto, priorAuto, cap);
  outcomes.push(v.auto);
  if (v.auto) priorAuto++; // only an actually-auto write increments the fan-out count
}
check(`loop of 7 auto attempts -> exactly ${cap} auto-post`, outcomes.filter(Boolean).length === cap, JSON.stringify(outcomes));
check("  ...the first `cap` auto-post, the rest are confirm-only", outcomes.slice(0, cap).every(Boolean) && outcomes.slice(cap).every((x) => x === false), JSON.stringify(outcomes));

// --- 5. the shipped default cap is a sane, human-sized number ----------------------------------
check(`TURN_AUTO_CAP default is sane (1..10), is ${TURN_AUTO_CAP}`, TURN_AUTO_CAP >= 1 && TURN_AUTO_CAP <= 10);

console.log(fails === 0 ? "\nT-TURN-WRITE-CAP: ALL-PASS" : `\nT-TURN-WRITE-CAP: ${fails} FAIL`);
process.exit(fails === 0 ? 0 : 1);
