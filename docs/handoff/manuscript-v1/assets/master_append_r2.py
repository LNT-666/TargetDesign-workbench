import json, pathlib, datetime

repo = pathlib.Path(r"R:\songji\programfile")
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
print("now =", now)

rev = repo / "docs" / "handoff" / "manuscript-v1" / "review.md"
text = rev.read_text(encoding="utf-8")
marker = "## 6. master 追加复核"
if marker in text:
    print("review.md already carries section 6; skipping append")
else:
    add = """
## 6. master 追加复核（本轮独立复跑，结论不变：pass）

第 1-5 节写就后，本轮再次独立复跑，不采信任何转述：

```text
master 自写探针 assets/master_recheck_r2.py（difflib 与 round-2 快照逐行比对）
  SEED_PLAN_ANALYSIS.md   1 hunk  +1 -1       PAPER_FIGURE_CAPTIONS.md 3 hunks  +3 -3
  PAPER_REFERENCES.md     6 hunks +34 -11     PAPER_RESULTS_DRAFT.md   3 hunks +23 -18
  PAPER_TABLES_SUPP.md    4 hunks  +8 -4      PAPER_BACK_MATTER.md     1 hunk   +1 -1
  PAPER_DRAFT.md          3 hunks  +7 -6      TOTAL 21 hunks —— 与 report.md 自报一致
复跑 servant 探针 assets/servant_round2_selfcheck.py -> RESULT: ALL PASS (0 failing checks), exit 0
Crossref 独立反查 [27]-[30]：标题/期刊/年/卷/页逐字段命中
  （DeepCRISPR 条目 Crossref 无 page 字段，条目标 19(1):80，与 Europe PMC 一致）
规格点回读：SEED_PLAN_ANALYSIS.md:128、PAPER_FIGURE_CAPTIONS.md:50,58,62、PAPER_BACK_MATTER.md:34
  N1 省略号、N2 排序项、A/C/G/T 限定三处落点（PAPER_DRAFT.md:28/:87、PAPER_RESULTS_DRAFT.md:109）全部命中
边界：tools/ shared/ native/ example/ Target_xbp_*/ webapp/ 与仓库根文件在 14:20 后改动数均为 0；
  docs/PAPER_METHODS_DRAFT.md mtime 仍为 11:03:08（冻结件未被触碰）
```

新增两条观察（不改变本轮判定）：

1. `docs/PAPER_REFERENCES.md` 全部 30 条参考文献均带 `<!-- ... -->` 溯源注释（共 30 处）。这是工作稿的溯源约定，
   非本轮引入的问题；但投稿稿必须剥离，已列为 `manuscript-v2` 的必做项。
2. [27]-[30] 的编号顺序沿用 master 给定的模型清单顺序（Azimuth / DeepCRISPR / DeepCpf1 / CRISPR-M）；
   与正文首次引用顺序的对应关系留待合稿时统一。
"""
    rev.write_text(text.rstrip("\n") + "\n" + add, encoding="utf-8", newline="\n")
    print("review.md appended, bytes =", rev.stat().st_size)

st = repo / "docs" / "handoff" / "manuscript-v1" / "state.json"
data = json.loads(st.read_text(encoding="utf-8"))
data["round2_status"] = "master_verified_pass"
data["round2_verified_at"] = now
data["updated"] = now
if "PAPER_REFERENCES.md 30 条溯源注释须在投稿稿剥离" not in data["followups"]:
    data["followups"].append("PAPER_REFERENCES.md 30 条 <!-- --> 溯源注释须在投稿稿剥离")
st.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print("state.json status =", data["status"], "| round2_status =", data["round2_status"], "| bytes =", st.stat().st_size)