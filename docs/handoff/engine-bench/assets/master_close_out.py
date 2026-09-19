import io, os, json
ROOT = r"R:\songji\programfile"
p = os.path.join(ROOT, "docs/handoff/engine-bench/state.json")
j = json.loads(io.open(p, encoding="utf-8").read())
j["open_items_resolved"] = True
j["open_items"] = []
j["resolution"] = "两项遗留（docs/SEED_PLAN_ANALYSIS.md 与 --determinism 实跑证据）已作为 manuscript-v1 的 P0-1 交付，master 于 manuscript-v1 round 1/round 2 核验中确认（含 master 亲自重跑 --determinism）。"
j["updated"] = "2026-09-19 15:00"
with io.open(p, "w", encoding="utf-8", newline="") as f:
    f.write(json.dumps(j, ensure_ascii=False, indent=2) + "\n")
print("WROTE engine-bench/state.json")

r = os.path.join(ROOT, "docs/handoff/engine-bench/review.md")
cur = io.open(r, encoding="utf-8").read()
add = "\n## 5. 遗留项结清（2026-09-19 15:00）\n\n本任务接管时留下的两项（`docs/SEED_PLAN_ANALYSIS.md` 与 `--determinism` 实跑证据）已作为\n`docs/handoff/manuscript-v1/task.md` 的 P0-1 交付并通过核验：\n\n- `docs/SEED_PLAN_ANALYSIS.md`：220 行，四节齐备；§2 的 16 行网格表与 `docs/seed_plan_sweep.json` 逐值一致（master 比对 0 处不符）。\n- 确定性证据：master 亲自重跑 `python tools\\seed_plan_sweep.py --determinism`，四个线程数 hits=36 且 sha256 全等\n  `0549c426662a2fa2994b8696971c51366f330456ed7392adaa58d7be62cbf499`。\n- round 1 核验发现的 `SEED_PLAN_ANALYSIS.md:128` 命中数口径错误（66 vs 67）已于 manuscript-v1 round 2 修正并通过复核。\n\n至此本任务无未结项；`tools/seed_plan_sweep.py` 与 `docs/seed_plan_sweep.json` 维持只读冻结。\n"
if "遗留项结清" in cur:
    print("SKIP engine-bench/review.md")
else:
    with io.open(r, "w", encoding="utf-8", newline="") as f:
        f.write(cur.rstrip("\n") + "\n" + add)
    print("WROTE engine-bench/review.md")