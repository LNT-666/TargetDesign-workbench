import json, pathlib, datetime
repo = pathlib.Path(r"R:\songji\programfile")
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

rev = repo / "docs/handoff/manuscript-v1/review.md"
t = rev.read_text(encoding="utf-8")
old = ("1. `scy-test/` 是否授权为证据来源 —— **待用户拍板**；未授权前 Results 案例小节与 Figure S1 保持 `[TO FILL]`。")
new = ("1. Results 案例小节与 Figure S1 的取舍 —— **master 14:50 更正框定**：`scy-test/` 里唯一的「数据」是公共参考序列\n"
       "   （`scy-test/blastdb/GCF_000001405.40_GRCh38.p14_genomic.blastdb`，787 MB），其余约 66 GB / 10,389 个文件\n"
       "   （122 个 `*_scores.tsv`、123 个 `*_offtargets.tsv`、112 个 `*_blast_results.tsv`、9,739 个 `.fa` 中间件）\n"
       "   全部是程序自身输出，跨 9/2-9/19 多次运行、命名不一致且无生成命令/版本记录；位点 FASTA 头只有 `>PPP1R12C-intron1`，\n"
       "   无坐标与基因组版本，仓库文档中亦无坐标记录（grep 0 命中）。故它不是「第三方数据源」，不能作独立验证，\n"
       "   只能作 use-case demonstration。真正待用户拍板的是：删掉该小节（方案 A），或按记录在案的命令重跑一次（方案 B）。")
if old in t:
    rev.write_text(t.replace(old, new), encoding="utf-8", newline="\n")
    print("review.md section 4 item 1 corrected")
else:
    print("pattern not found; left unchanged")

st = repo / "docs/handoff/manuscript-v1/state.json"
d = json.loads(st.read_text(encoding="utf-8"))
d["user_decisions_pending"] = [
    "Results 案例小节 / Figure S1 取舍：A 删除（推荐）或 B 用记录命令重跑公共位点（scy-test 现有文件不可复用，属程序自身输出且无坐标/命令/版本记录）",
    "仓库 URL / Zenodo 版本 DOI / accession / keywords"
]
d["scy_test_finding"] = ("非数据源：仅公共 GRCh38.p14 BLAST 库属输入数据；其余 66 GB 为程序输出，"
                         "跨多日运行、命名不一致、无命令与版本记录；位点坐标未记录于仓库任何文档")
d["updated"] = now
st.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print("state.json updated:", d["user_decisions_pending"][0][:40], "...")