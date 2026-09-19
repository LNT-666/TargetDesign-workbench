import json, pathlib, datetime
repo = pathlib.Path(r"R:\songji\programfile")
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

rev = repo / "docs/handoff/manuscript-v1/review.md"
t = rev.read_text(encoding="utf-8")
anchor = "   只能作 use-case demonstration。真正待用户拍板的是：删掉该小节（方案 A），或按记录在案的命令重跑一次（方案 B）。"
add = ("\n   **结论（用户 2026-09-19 拍板）：方案 A** —— 删除案例小节与 Figure S1，`scy-test/` 不作为任何来源；\n"
       "   落地任务为 `docs/handoff/manuscript-v2/`（task.md 的 P0-1..P0-4）。")
if anchor in t and "方案 A ---- " not in t and "**结论（用户 2026-09-19 拍板）：方案 A**" not in t:
    rev.write_text(t.replace(anchor, anchor + add), encoding="utf-8", newline="\n")
    print("review.md: decision A recorded")
else:
    print("review.md: already recorded or anchor missing")

st = repo / "docs/handoff/manuscript-v1/state.json"
d = json.loads(st.read_text(encoding="utf-8"))
d["user_decisions_pending"] = ["仓库 URL / Zenodo 版本 DOI / accession / keywords"]
d["user_decision_resolved"] = {
    "item": "Results 案例小节与 Figure S1 取舍",
    "decision": "A —— 删除；scy-test/ 不作为证据来源",
    "by": "用户",
    "at": "2026-09-19",
    "carried_out_by": "docs/handoff/manuscript-v2/ (P0-1..P0-4)"
}
d["updated"] = now
st.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print("state.json: decision recorded, pending =", d["user_decisions_pending"])