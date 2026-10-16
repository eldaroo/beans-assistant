"""deploy/demo_drive.py — spec 005 end-to-end demonstration.

Stands up the REAL beans-ai gateway (deploy/demo-server.mjs, leaf `claude` call stubbed since we
have no subscription token in-run) and drives REAL Timonel turns through the REAL Python client:
get_llm(backend=gateway) -> ChatGateway -> HTTP /run -> warm child pool -> JsonOutputParser. Then
it proves /health and the never-hard-fail fallback. Everything but the model leaf is production
code. Run: python deploy/demo_drive.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SECRET = "demo-secret"
# Beans&Co domain turns (pulseras + coffee), the real Timonel domain.
TURNS = [
    "hola, buenas",
    "vendí 2 pulseras negras",
    "gasté 30 dólares en envíos",
    "cuánto facturé esta semana",
    "cuántas pulseras tengo",
]


def _start_server() -> tuple[subprocess.Popen, int]:
    env = dict(os.environ, BEANS_AI_SHARED_SECRET=SECRET)
    proc = subprocess.Popen(
        ["node", str(HERE / "demo-server.mjs")],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, cwd=str(HERE),
    )
    for _ in range(100):
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        if line.startswith("DEMO_GATEWAY_READY"):
            return proc, int(line.strip().split()[1])
    raise RuntimeError("gateway did not become ready")


def main() -> int:
    print("=" * 72)
    print("beans-ai gateway — spec 005 end-to-end demonstration")
    print("(real HTTP gateway + real Python ChatGateway; only the leaf claude call is stubbed)")
    print("=" * 72)

    proc, port = _start_server()
    base = f"http://127.0.0.1:{port}"
    try:
        # 1. /health on the real server
        with urllib.request.urlopen(base + "/health", timeout=5) as r:
            health = json.loads(r.read())
        print(f"\n[1] GET /health -> {json.dumps(health)}")

        # 2. Real Timonel brain over the gateway backend
        os.environ["BEANS_AI_GATEWAY_URL"] = base
        os.environ["BEANS_AI_SHARED_SECRET"] = SECRET
        os.environ["TIMONEL_LLM_BACKEND"] = "gateway"
        os.environ.pop("GOOGLE_API_KEY", None)  # prove the gateway path needs no Gemini key

        from langchain_core.output_parsers import JsonOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from llm import get_llm, resolve_backend

        print(f"\n[2] TIMONEL_LLM_BACKEND resolves to: {resolve_backend()}  (no GOOGLE_API_KEY set)")
        prompt = ChatPromptTemplate.from_messages(
            [("system", "Sos el router de Timonel. Clasificá la intención. Devolvé solo JSON."), ("human", "{input}")]
        )
        chain = prompt | get_llm() | JsonOutputParser()
        print("    Driving real Timonel turns through the gateway (PROMPT | ChatGateway | JsonOutputParser):")
        for t in TURNS:
            result = chain.invoke({"input": t})
            print(f"      {t!r:<48} -> {json.dumps(result, ensure_ascii=False)}")

        # 3. Never-hard-fail: gateway unreachable, no Gemini key -> safe deterministic {}
        os.environ["BEANS_AI_GATEWAY_URL"] = "http://127.0.0.1:9"  # nothing listening
        safe_chain = ChatPromptTemplate.from_messages([("human", "{input}")]) | get_llm()
        msg = safe_chain.invoke({"input": "esto deberia degradar con gracia"})
        print(f"\n[3] Gateway down + no Gemini key -> safe fallback returns: {msg.content!r}  (Timonel never hard-fails)")

        print("\nAll demonstration steps completed.")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
