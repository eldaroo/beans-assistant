// Compound create-then-act (spec 009 M1 / AC1 / AC3 / D-047).
//
// When a stock or sale names a product that does not resolve, the old path returned a
// bare `product_not_found` error and the owner hit a dead end ("dale, registralo" ->
// "no pude interpretar eso"). Spec 009 heals that into a TWO-STEP compound: step 1 mints
// a minimal product from the name, step 2 is the original stock or sale, now threaded to
// the created product's id.
//
// The load-bearing invariant (AC3): the STEP stays the unit of commit. Each step has its
// own op_token, its own verdict, its own /api/ops/confirm. There is NO cross-step
// transaction. A late step's failure leaves earlier committed steps intact and never
// strands a partial, because there is nothing to roll back across steps -- step 1 is
// already a committed, independent fact. `driveCompound` below is that contract, pure and
// injectable so the atomicity property is tested without a DB.

import type { ParsedOp } from "@/lib/parse/types";

// The acts that can heal a product-not-found into a compound. C1 heals ADD_STOCK only:
// "me entraron 50 pulseras rojas" creates the product and loads the stock, which is the
// exact screenshot the spec set out to fix. A create-then-SELL is deliberately NOT here:
// a name-only minted product has zero stock and no price, so a PAID sale of it can never
// commit (registerSale validates stock-on-hand and needs a price). Shipping a sale-heal
// that always lands in "created-only" would reproduce the very dead-end spec 009 kills, so
// the sale-heal is deferred to its own cohort where the stock/price seeding is designed.
// `threadProductId` below still understands the sale shape so that work is a small step.
export const COMPOUND_ACT_OPS = new Set<string>(["ADD_STOCK"]);

export function isCompoundableAct(operationType: string): boolean {
  return COMPOUND_ACT_OPS.has((operationType || "").toUpperCase());
}

// The product reference a compoundable act names, or null. A sale carries it on its one
// item; stock carries it on the top-level args.
export function productRefOfStep(step: ParsedOp): string | null {
  const op = (step.operationType || "").toUpperCase();
  const args = step.args ?? {};
  if (op === "REGISTER_SALE") {
    const items = args.items as Array<{ productRef?: unknown }> | undefined;
    const ref = items?.[0]?.productRef;
    return typeof ref === "string" && ref.trim() ? ref.trim() : null;
  }
  const ref = (args as { productRef?: unknown }).productRef;
  return typeof ref === "string" && ref.trim() ? ref.trim() : null;
}

// Strip any product id the PARSER supplied, leaving descriptors (productRef) only. The
// parser is contracted to emit descriptors, never ids (D-050); a hijacked parser that
// emitted a numeric id would otherwise satisfy the server's determinism gate for the wrong
// product. The server mints and threads ids itself (threadProductId), so the only
// legitimate id arrives on the compound re-stage, not on the initial parser proposal. Pure.
export function stripModelProductIds(step: ParsedOp): ParsedOp {
  const op = (step.operationType || "").toUpperCase();
  const args = { ...(step.args ?? {}) };
  delete (args as Record<string, unknown>).productId;
  if (op === "REGISTER_SALE" && Array.isArray(args.items)) {
    args.items = (args.items as Array<Record<string, unknown>>).map((it) => {
      const copy = { ...it };
      delete copy.productId;
      return copy;
    });
  }
  return { operationType: step.operationType, args };
}

// Thread a freshly-created product id into the act step, replacing the unresolved ref.
// Pure: returns a new step, never mutates. This is how step 2 inherits step 1's result
// without a model ever supplying an id (D-050): the server mints the product and the
// server injects its id.
export function threadProductId(step: ParsedOp, productId: number): ParsedOp {
  const op = (step.operationType || "").toUpperCase();
  const args = { ...(step.args ?? {}) };
  if (op === "REGISTER_SALE") {
    const items = (args.items as Array<Record<string, unknown>> | undefined) ?? [];
    const [first, ...rest] = items;
    return {
      operationType: step.operationType,
      args: { ...args, items: [{ ...(first ?? {}), productId, productRef: undefined }, ...rest] },
    };
  }
  return { operationType: step.operationType, args: { ...args, productId, productRef: undefined } };
}

// Build the two ordered steps of a compound from an unresolved act. Step 1 is the
// name-only REGISTER_PRODUCT (its resolve mints the minimal product); step 2 is the
// original act, carried verbatim, to be threaded after step 1 commits.
export interface CompoundSteps {
  productName: string;
  register: ParsedOp;
  act: ParsedOp;
}
export function buildCompoundSteps(act: ParsedOp, productRef: string): CompoundSteps {
  return {
    productName: productRef,
    register: { operationType: "REGISTER_PRODUCT", args: { name: productRef } },
    act,
  };
}

// The step outcome shape the orchestrator reports.
export interface StepOutcome {
  step: number;
  role: "register" | "act";
  committed: boolean;
  result?: unknown;
  error?: string;
}

// Drive a compound in order, each step its own commit unit (AC3). Effects are injected:
//   confirmRegister()        commits step 1, returns the created product { id, ... }
//   stageAct(productId)      stages step 2 with the threaded id, returns its op_token
//   confirmAct(opToken)      commits step 2
// The contract this encodes and the test pins:
//   - step 1 commits first and independently;
//   - step 2 is threaded to step 1's product id;
//   - a failure in step 2 (stage OR confirm) is isolated: step 1 stays committed, the
//     function reports step 1 done and step 2 failed, and it NEVER rolls back step 1.
export async function driveCompound(effects: {
  confirmRegister: () => Promise<{ id: number } & Record<string, unknown>>;
  stageAct: (productId: number) => Promise<{ op_token: string }>;
  confirmAct: (opToken: string) => Promise<unknown>;
}): Promise<StepOutcome[]> {
  const outcomes: StepOutcome[] = [];

  // Step 1: create the product. If this throws, nothing committed; report and stop.
  let product: { id: number } & Record<string, unknown>;
  try {
    product = await effects.confirmRegister();
    outcomes.push({ step: 1, role: "register", committed: true, result: product });
  } catch (e) {
    outcomes.push({ step: 1, role: "register", committed: false, error: (e as Error).message });
    return outcomes;
  }

  // Step 2: stage (threaded to the new id) then commit. Any failure here is isolated:
  // step 1 remains a committed fact. There is deliberately no compensation of step 1 --
  // the product exists and is correct; only the act did not land, and the owner can
  // retry the act alone.
  try {
    const staged = await effects.stageAct(product.id);
    const result = await effects.confirmAct(staged.op_token);
    outcomes.push({ step: 2, role: "act", committed: true, result });
  } catch (e) {
    outcomes.push({ step: 2, role: "act", committed: false, error: (e as Error).message });
  }
  return outcomes;
}
