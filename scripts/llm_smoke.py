"""Provider smoke test (P10 step 3).

One LLM call to verify a provider config end-to-end (auth, endpoint, model)
and print token usage + latency - before you spend on a fleet run.

    $env:DEEPSEEK_API_KEY = "sk-..."   # PowerShell
    python scripts/llm_smoke.py --llm-config llm_configs/deepseek.json
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from syngen.llm.client import LLMClient, load_llm_config  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm-config", required=True)
    ap.add_argument("--prompt",
                    default='Reply with exactly this JSON: {"ok": true}')
    args = ap.parse_args()

    cfg = load_llm_config(args.llm_config)
    print("endpoint:", cfg.get("api_base") or cfg.get("endpoint"))
    print("backend :", cfg.get("backend"))
    print("model   :", cfg.get("model"))
    print("api_key :", "set" if cfg.get("api_key") else "MISSING")
    client = LLMClient(cfg)
    t0 = time.time()
    try:
        resp = client.chat("You are a terse assistant.", args.prompt,
                           max_tokens=64, max_attempts=1)
    except Exception as e:  # noqa: BLE001 - smoke test reports the failure
        print(f"FAILED: {type(e).__name__}: {e}")
        return 1
    print("elapsed_s:", round(time.time() - t0, 2))
    print("finish  :", resp.finish_reason, "| model:", resp.model)
    print("content :", resp.content[:200])
    print("usage   :", client.usage_totals())
    return 0


if __name__ == "__main__":
    sys.exit(main())
