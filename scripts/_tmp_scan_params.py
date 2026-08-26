import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
src = open(r"syngen\packs\revops\checks.py", encoding="utf-8").read()
names = ["avg_discount_quarter", "avg_price_by_tier", "tier_share_shift",
         "coverage_ratio", "forecast_vs_actual", "unowned_account_share",
         "icp_creation_shift", "potential_coverage_gap",
         "region_discount_premium", "revenue_vs_plan", "quota_vs_potential",
         "effective_capacity", "gap_concentration"]
for n in names:
    m = re.search(r"def check_%s\(.*?(?=\ndef |\Z)" % n, src, re.S)
    body = m.group(0)
    direct = sorted(set(re.findall(r"params\[\s*['\"](\w+)['\"]\s*\]", body)))
    defaults = sorted(set(re.findall(r"\.get\(\s*['\"](\w+)['\"]", body)))
    print(n, "| direct:", ",".join(direct), "| get:", ",".join(defaults))
