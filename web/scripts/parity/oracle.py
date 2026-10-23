#!/usr/bin/env python3
"""M7 parity oracle (spec 008 AC4).

Runs the REAL Python business-logic cores (the incumbent production
implementation) over a shared fixture corpus and emits a golden JSON of
{fixtures (inputs), golden (the Python outputs)}. The TypeScript parity runner
(`web/scripts/m7-parity.mts`) reads the SAME fixtures, runs the ported TS
functions, and asserts byte-equal output against this golden. The committed
golden.json is the durable record of the oracle so the suite still runs after
the Python app is retired at M8.

Honesty note: this oracle imports the real `backend.services.write_verdict`,
`backend.services.costing_service`, `backend.services.cost_scenario`, and the
costing repository's `usd_cents_from`. The costing/scenario modules import a DB
repository at module load for the (unrelated) read paths; the PURE functions we
exercise here never touch a DB. We stub the DB modules in sys.modules before
import so no database is contacted. The function source that computes every
golden value is the unmodified production source.

Run from the repo root (the worktree root), with that root importable:
    python3 web/scripts/parity/oracle.py > web/scripts/parity/golden.json
"""
from __future__ import annotations

import json
import os
import sys
import types

# --- make the repo root importable and stub the DB layer -------------------
# This file lives at <root>/web/scripts/parity/oracle.py; the repo root is three
# directories up. `backend` and `database_config` resolve from there.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _stub(name: str, **attrs) -> None:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod


# database_config exposes `db` (a module-like object). The pure functions never
# call it; a bare object is enough for the import to succeed.
_stub("database_config", db=object(), USE_POSTGRES=False, fetch_all=lambda *a, **k: [])


class _StubRepo:
    def __init__(self, *a, **k):
        pass


_stub("backend.repositories.costing_repository", CostingRepository=_StubRepo)
_stub("backend.repositories.production_repository", ProductionRepository=_StubRepo)

# Now import the real cores.
from backend.services import write_verdict as wv  # noqa: E402
from backend.services import costing_service as cs  # noqa: E402
from backend.services import cost_scenario as scen  # noqa: E402
from backend.repositories.costing_repository import CostingRepository  # stub  # noqa: E402

# usd_cents_from is a @staticmethod on the real repository class; the real repo
# module was stubbed above (it pulls database_config at import), so we re-load
# the genuine staticmethod source directly from the file to keep it as oracle.
import importlib.util  # noqa: E402

_repo_path = os.path.join(ROOT, "backend", "repositories", "costing_repository.py")
_spec = importlib.util.spec_from_file_location("_real_costing_repo", _repo_path)
_real_repo = importlib.util.module_from_spec(_spec)
# costing_repository imports `from database_config import db` — already stubbed.
_spec.loader.exec_module(_real_repo)
usd_cents_from = _real_repo.CostingRepository.usd_cents_from


# ---------------------------------------------------------------------------
# Fixture corpus. Each section is {cases: [...], golden: [...]} after compute.
# Inputs are JSON-serializable so the TS side consumes the identical fixtures.
# ---------------------------------------------------------------------------

def section_money():
    parse_tokens = [
        "300", "1.500", "1,500", "1.5", "1,5", "12.50", "12,50",
        "1.500.000", "1,500,000", "2.5", "0,5", "100", "1.234,56",
        "1,234.56", "abc", "", "10", "0", "999.999",
    ]
    parse_numbers_texts = [
        "vendi 2 medias a 300",
        "compre 1.500 de cafe por 12,50",
        "gaste 1.234,56 en flete",
        "nada numerico aca",
        "stock 10 y 20 y 10",
    ]
    grounded_cases = [
        {"value": 300, "utterance": "vendi a 300"},
        {"value": 1500, "utterance": "compre 1.500"},
        {"value": 1.5, "utterance": "15"},        # scale-collision: must be False
        {"value": 15, "utterance": "1.5"},        # scale-collision: must be False
        {"value": 12.5, "utterance": "a 12,50"},
        {"value": 400, "utterance": "vendi una tabla"},  # ungrounded
        {"value": None, "utterance": "nada"},
    ]
    return {
        "parse_one": [{"raw": t, "out": wv._parse_one(t)} for t in parse_tokens],
        "parse_numbers": [
            {"text": t, "out": sorted(wv.parse_numbers(t))} for t in parse_numbers_texts
        ],
        "numeral_is_grounded": [
            {**c, "out": wv.numeral_is_grounded(c["value"], wv.parse_numbers(c["utterance"]))}
            for c in grounded_cases
        ],
    }


def section_verdict():
    cases = [
        # reversible, grounded, single candidate, in caps -> AUTO
        dict(operation_type="REGISTER_SALE", utterance="registra una venta por 400 de una tabla",
             grounded_amounts=[400], product_name="tabla", candidate_count=1),
        # expense, no product to ground -> AUTO
        dict(operation_type="REGISTER_EXPENSE", utterance="gaste 500 en envio",
             grounded_amounts=[500], product_name=None, candidate_count=1),
        # add stock, grounded, single -> AUTO
        dict(operation_type="ADD_STOCK", utterance="llegaron 10 termos",
             grounded_amounts=[10], product_name="termos", candidate_count=1),
        # irreversible short-circuit -> CARD
        dict(operation_type="UPDATE_PRICE", utterance="subi el precio a 800",
             grounded_amounts=[800], product_name="tabla", candidate_count=1, irreversible=True),
        # bare confirmation -> CARD
        dict(operation_type="REGISTER_SALE", utterance="dale",
             grounded_amounts=[400], product_name="tabla", candidate_count=1),
        # ungrounded numeral -> CARD
        dict(operation_type="REGISTER_SALE", utterance="vendi una tabla",
             grounded_amounts=[400], product_name="tabla", candidate_count=1),
        # product not in utterance -> CARD
        dict(operation_type="REGISTER_SALE", utterance="vendi algo por 400",
             grounded_amounts=[400], product_name="pulsera verde", candidate_count=1),
        # zero candidates -> CARD
        dict(operation_type="REGISTER_SALE", utterance="vendi una tabla por 400",
             grounded_amounts=[400], product_name="tabla", candidate_count=0),
        # ambiguous (>1) -> CARD  (ADD_STOCK disambiguation)
        dict(operation_type="ADD_STOCK", utterance="llegaron 10 medias",
             grounded_amounts=[10], product_name="medias", candidate_count=2),
        # over cap -> CARD
        dict(operation_type="REGISTER_SALE", utterance="vendi una tabla por 400",
             grounded_amounts=[400], product_name="tabla", candidate_count=1, within_caps=False),
        # not-in-reversible-set -> CARD
        dict(operation_type="REGISTER_PRODUCT", utterance="nueva pulsera por 400",
             grounded_amounts=[400], product_name="pulsera", candidate_count=1),
    ]
    out = []
    for c in cases:
        v = wv.compute_verdict(
            operation_type=c["operation_type"],
            utterance=c["utterance"],
            grounded_amounts=c["grounded_amounts"],
            product_name=c.get("product_name"),
            candidate_count=c["candidate_count"],
            within_caps=c.get("within_caps", True),
            irreversible=c.get("irreversible", False),
        )
        # reason_codes: the code before the first ':' (tolerates float-repr tails
        # like ungrounded-numerals:[400.0] vs [400]). auto / review are byte-exact.
        reason_codes = sorted({r.split(":", 1)[0] for r in v.reasons})
        out.append({"case": c, "auto": v.auto, "requires_human_review": v.requires_human_review,
                    "reason_codes": reason_codes})
    return out


def section_costing():
    week_cases = ["2026-W01", "2020-W53", "2025-W52", "2025-W01", "2024-W01", "2015-W53", "2020-W01"]
    units_rows = [
        {"period_week": "2026-W01", "units": 10},
        {"period_week": "2026-W02", "units": 5},
        {"period_week": "2026-W05", "units": 7},
    ]
    units_months = ["2025-12", "2026-01", "2026-02"]
    labor_cases = [
        {"batch_payment_cents": 1000, "units_completed": 0},   # None
        {"batch_payment_cents": 1000, "units_completed": 3},   # 333.33 -> 333
        {"batch_payment_cents": 250, "units_completed": 4},    # 62.5 (banker -> 62)
        {"batch_payment_cents": 300, "units_completed": 8},    # 37.5 (banker -> 38)
        {"batch_payment_cents": 1000, "units_completed": 1},   # 1000
    ]
    fx_cases = [
        {"original_amount_cents": 10000, "fx_rate": 4000},  # 2.5 (banker -> 2)
        {"original_amount_cents": 10000, "fx_rate": 3},     # 3333.33 -> 3333
        {"original_amount_cents": 50, "fx_rate": 1},        # 50
        {"original_amount_cents": 30000, "fx_rate": 4000},  # 7.5 (banker -> 8)
        {"original_amount_cents": 15000, "fx_rate": 4000},  # 3.75 -> 4
    ]
    # recompute over a six-component list, some pending.
    C = cs.CostComponent
    comp_full = [C("materials", "Materiales", 100, ""), C("labor", "Mano de obra", 50, ""),
                 C("packaging", "Empaque", 20, ""), C("shipping", "Envio", 30, ""),
                 C("customs", "Aduana", 10, ""), C("indirect", "Indirectos", 5, "")]
    comp_partial = [C("materials", "Materiales", 100, ""), C("labor", "Mano de obra", None, ""),
                    C("packaging", "Empaque", 20, ""), C("shipping", "Envio", None, ""),
                    C("customs", "Aduana", 10, ""), C("indirect", "Indirectos", 5, "")]

    def rc(components, overrides):
        resolved, total, status, pending = cs.recompute(components, overrides)
        return {"total_cents": total, "status": status, "pending_labels": pending}

    def comps_json(components):
        return [{"key": c.key, "label": c.label, "cents": c.cents, "detail": c.detail} for c in components]

    recompute_cases = [
        {"name": "all-filled", "components": comps_json(comp_full), "overrides": {}, "out": rc(comp_full, None)},
        {"name": "two-pending", "components": comps_json(comp_partial), "overrides": {}, "out": rc(comp_partial, None)},
        {"name": "override-force-pending", "components": comps_json(comp_full),
         "overrides": {"materials": None}, "out": rc(comp_full, {"materials": None})},
        {"name": "override-fill", "components": comps_json(comp_partial),
         "overrides": {"labor": 40, "shipping": 25}, "out": rc(comp_partial, {"labor": 40, "shipping": 25})},
    ]
    return {
        "month_of_iso_week": [{"week": w, "out": cs.month_of_iso_week(w)} for w in week_cases],
        "units_rows": units_rows,
        "units_in_month": [{"month": m, "out": cs.units_in_month(units_rows, m)} for m in units_months],
        "labor_per_unit": [{**c, "out": cs.labor_per_unit(c["batch_payment_cents"], c["units_completed"])}
                           for c in labor_cases],
        "usd_cents_from": [{**c, "out": usd_cents_from(c["original_amount_cents"], c["fx_rate"])}
                           for c in fx_cases],
        "recompute": recompute_cases,
    }


def section_scenario():
    is_cases = [
        "que pasa si produzco en colombia",
        "escenario costa rica",
        "cuanto costaria moverlo a armenia",
        "y si lo hago en costa rica",
        "vendi 2 medias a 300",          # not a scenario
        "cuanto vendi hoy",              # not a scenario
    ]
    # format_reply over constructed ScenarioResult fixtures (the string math).
    R = scen.ScenarioResult
    results = [
        R(product_id=1, product_name="pulsera verde", baseline_country="Colombia",
          scenario_country="Colombia", baseline_total_cents=5000, scenario_total_cents=5000,
          delta_cents=0, baseline_status="completo", scenario_status="completo", moved=False),
        R(product_id=1, product_name="pulsera verde", baseline_country="Colombia",
          scenario_country="Costa Rica", baseline_total_cents=5000, scenario_total_cents=4200,
          delta_cents=-800, baseline_status="completo", scenario_status="completo", moved=True),
        R(product_id=1, product_name="pulsera verde", baseline_country="Colombia",
          scenario_country="Costa Rica", baseline_total_cents=5000, scenario_total_cents=5800,
          delta_cents=800, baseline_status="completo", scenario_status="completo", moved=True),
        R(product_id=1, product_name="pulsera verde", baseline_country="Colombia",
          scenario_country="Costa Rica", baseline_total_cents=5000, scenario_total_cents=5000,
          delta_cents=0, baseline_status="completo", scenario_status="completo", moved=True),
        R(product_id=1, product_name="pulsera verde", baseline_country="Colombia",
          scenario_country="Costa Rica", baseline_total_cents=5000, scenario_total_cents=4200,
          delta_cents=-800, baseline_status="completo", scenario_status="parcial", moved=True),
        R(product_id=1, product_name="pulsera verde", baseline_country="Colombia",
          scenario_country="Costa Rica", baseline_total_cents=3000, scenario_total_cents=4200,
          delta_cents=1200, baseline_status="parcial", scenario_status="completo", moved=True),
    ]
    reply_cases = []
    for i, r in enumerate(results):
        reply_cases.append({
            "result": {
                "productName": r.product_name, "baselineCountry": r.baseline_country,
                "scenarioCountry": r.scenario_country, "baselineTotalCents": r.baseline_total_cents,
                "scenarioTotalCents": r.scenario_total_cents, "deltaCents": r.delta_cents,
                "baselineStatus": r.baseline_status, "scenarioStatus": r.scenario_status,
                "moved": r.moved, "bothComplete": r.both_complete,
            },
            "out": scen.format_reply(r),
        })
    return {
        "is_scenario": [{"message": m, "out": scen.is_scenario(m)} for m in is_cases],
        "format_reply": reply_cases,
    }


def main():
    payload = {
        "_meta": {
            "generated_by": "web/scripts/parity/oracle.py",
            "oracle": "backend.services.{write_verdict,costing_service,cost_scenario} + costing_repository.usd_cents_from",
            "note": "Golden is the real Python output. TS parity asserts byte-equal against it (AC4). "
                    "verdict reasons compared as reason-code set (float-repr tail tolerated); auto/review byte-exact.",
        },
        "money": section_money(),
        "verdict": section_verdict(),
        "costing": section_costing(),
        "scenario": section_scenario(),
    }
    # Write the golden directly in UTF-8 (never via a shell redirect, whose
    # encoding is the Windows console codepage, not UTF-8 — that corrupted the
    # accented scenario strings and broke parity). The file is the durable record.
    out_path = os.path.join(os.path.dirname(__file__), "golden.json")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    sys.stderr.write(f"wrote {out_path}\n")


if __name__ == "__main__":
    main()
