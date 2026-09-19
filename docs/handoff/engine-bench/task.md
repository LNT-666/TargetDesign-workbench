# 任务：种子计划代价曲线 + 完备性 + 确定性 + 组合复杂度

- task-slug: `engine-bench`
- round: 1
- master: 会话 M（master）
- servant: 会话 S（servant）
- repo: `R:\songji\programfile`（镜像服务器 `/home/apool/songji/programfile`）
- 权威运行环境：ms01 `/home/apool/songji/programfile/.venv/bin/python`
- 本地环境：`python` = Python 3.14.7；`native\bin\offtarget-engine.exe` 在本地可直接运行（master 已实测）
- 基线快照：本任务只新增文件，不改既有文件，无需快照
- 上位文档：`docs/PAPER_OUTLINE.md` 第五节第 2、3 项

## 0. 目标与边界

背景：论文 C2（原生索引引擎）的立论依赖三样东西——种子计划的代价曲线与完备性、
线程数无关的结果确定性、motif 成对枚举的组合复杂度与剪枝。目标期刊 NAR 正刊。

要做到：

1. 新增 `tools/seed_plan_sweep.py` 采集网格数据与确定性证据。
2. 新增 `docs/SEED_PLAN_ANALYSIS.md`，含 W(s) 复现、网格表、确定性表、复杂度分析。

不做：不改引擎源码与 CLI；不改既有基准脚本；不安装竞品工具；不跑全量测试；
不做长时间跑批或 >1 Mbp 的 fixture。

## 1. 规则 / 契约（唯一权威版本，servant 不需要重新调研）

```text
C1  唯一驱动方式（master 已实测通过）：
    build:
      native\bin\offtarget-engine.exe build-index --genome <fa> --prefix <idx> --k <k> --threads <t> --force
    search:
      native\bin\offtarget-engine.exe search --genome <fa> --index <idx> --guides <tsv>
        --output <jsonl> --max-mismatch <M> --max-bulge <B> --seed-len <k>
        --threads <t> --progress-every 0
    summary = 输出 JSONL 中 "type":"summary" 的那一行，字段含：
      guides / hits / candidates / search_time_s / memory_peak_mb /
      estimated_peak_mb / observed_peak_mb / seed_plan_guaranteed /
      exhaustive_seed_plan / sequence_cache
C2  fixture 沿用 example/engine_benchmark_small/（synthetic_genome.fa + guides.tsv），
    不要新建大 fixture，不要改 fixture 文件。
C3  网格固定：M ∈ {0,1,2,3} × B ∈ {0,1} × k ∈ {8,10} = 16 组，每组 3 次重复取中位数。
C4  确定性验证：固定 M=2, B=0, k=10，threads ∈ {1,4,8,32}。
    只取 hits 行（grep '"type":"hit"'）单独计算 SHA-256，四个值必须完全相同。
C5  W(s) 必须先用 Python 独立复现，且分段规则必须逐条抄自 C++ 源码：
      native/offtarget_engine/src/seed_plan.cpp 的 build_seed_plan /
      partition_lengths / segmented_variant_work / binomial / power_three。
    若源码实现与任务描述里的公式摘要不一致，以源码为准，并在 md 中单列差异小节。
C6  复杂度分析必须引用真实代码：
      Target_xbp_Target/extract_complex_queries.py（左右 motif 枚举 + min_gap/max_gap）
      Target_xbp_Y_zbp_Target/extract_motifs.py（Y 锚定 + 左右独立距离区间）
    必须给出组合数上界、每个约束如何剪枝、以及最坏情况的行为。
C7  交付重心是「可核查的表 + 命令原文 + 原始输出」，不是叙述性文字。
```

## 2. 现状证据（master 已核实，可直接引用）

- `native\bin\offtarget-engine.exe --version` → `offtarget-engine 0.1.0 index-format=1`
- `native\bin\offtarget-engine.exe capabilities --json` →
  `{"engine":"indexed","implementation":"native-cpp","index_format":1,"max_build_k":12,"threads":true,"max_memory_mb":true,"indels":"dna_rna","pam_sides":["3prime","5prime"]}`
- master 本地实测一次完整 build + search（k=8、3 条 guide、M=0、B=0、threads=4）的 summary 原文：
  `{"type":"summary","guides":3,"hits":6,"candidates":6,"search_time_s":0.203,"memory_peak_mb":10.23,"memory_limit_mb":0,"estimated_peak_mb":244.00,"observed_peak_mb":10.23,"seed_plan_guaranteed":true,"exhaustive_seed_plan":true,"sequence_cache":true}`
- `example/engine_benchmark_small/` 含 `synthetic_genome.fa`（约 1 Mbp）、`guides.tsv`、
  `results_mm0.json`、`results_bulge0.json`、`results_bulge1.json`、`REPORT.md`
- 既有参考数据（**不要重写**）：`example/engine_benchmark_small/REPORT.md`（六引擎对比，
  含 BLAST 1-mismatch 只召回 31/36）、`docs/NATIVE_INDEXED_BENCHMARK.md`（ms01 线程扩展）
- `tools/benchmark_all_engines.py`（13538 B）与 `tools/benchmark_search.py`（3714 B）已存在，本任务**不改**它们
- seed plan 相关字段在 `native/offtarget_engine/include/offtarget/search.hpp` 的 `SearchSummary` 中定义

## 3. 必做改动

- [ ] P0-1 `tools/seed_plan_sweep.py`（新增）
  - 期望行为：纯标准库；参数 `--engine-exe --genome --guides --out --repeats`；
    按 C3 跑 16 组 × repeats 次取中位数；写出 `docs/seed_plan_sweep.json` 并打印表格
  - 每条记录字段：M, B, k, seed_len, threads, repeats, median_search_time_s,
    candidates, hits, seed_plan_guaranteed, exhaustive_seed_plan, build_time_s
  - 证据要求：贴出运行命令原文与生成 JSON 的首条记录
- [ ] P0-2 确定性验证（作为 `--determinism` 子命令或独立小脚本均可）
  - 期望行为：按 C4 跑四个线程数，输出四行 `threads, hits, sha256`
  - 证据要求：四个 SHA-256 必须完全一致；若不一致即为缺陷，写入 report 的「附带发现」
- [ ] P1-1 `docs/SEED_PLAN_ANALYSIS.md`（新增）
  - 必含四节：① C5 的 W(s) 复现（含源码行号引用）② C3 网格结果表
    ③ C4 确定性表 ④ C6 复杂度与剪枝分析
  - 每个结论后必须跟命令或 `文件:行`
- [ ] P1-2 「源码与规格摘要的差异」小节（若 C5 发现差异则必写；无差异也要写明「未发现差异」）

## 4. 不要做的事

- 不改 `native/` 下任何文件（只读）
- 不改既有 `tools/benchmark_all_engines.py` / `tools/benchmark_search.py`
- 不改 `shared/`、`basic/`、`designer_workbench.py`、`unified_gui.py`、`webapp/`
- 不改 `example/engine_benchmark_small/` 下的 fixture 与既有结果文件
- 不安装或运行 GuideScan2 / CRISPRitz / FlashFry（本轮不做竞品头对头，作为「附带发现」记录）
- 不跑全量测试套件；不做超过 1 Mbp 的 fixture；不做长时间跑批

## 5. 决策项（未确认则按推荐执行）

- 16 组 × 3 次太慢 → 推荐先保证 16 组全部跑完，repeats 可降到 1 并在 report 说明
- `--seed-len` 与 `--k` 的关系不明确 → 推荐先读 `native/offtarget_engine/src/main.cpp` 的 CLI 解析，
  按实际行为设置，并在 md 写明两者关系
- B=1 时 fixture 无真实 bulge 命中 → 推荐照跑并注明「测的是启用 bulge 的代价，不是召回」
  （沿用 `REPORT.md` 的口径）
- 输出路径 → 推荐 `docs/seed_plan_sweep.json`，不要写到 `example/` 下

## 6. 轻量自检（servant 的检验上限）

```powershell
cd R:\songji\programfile
.\native\bin\offtarget-engine.exe --version
python tools\seed_plan_sweep.py --engine-exe .\native\bin\offtarget-engine.exe --genome example\engine_benchmark_small\synthetic_genome.fa --guides example\engine_benchmark_small\guides.tsv --out docs\seed_plan_sweep.json --repeats 1
python tools\seed_plan_sweep.py --engine-exe .\native\bin\offtarget-engine.exe --genome example\engine_benchmark_small\synthetic_genome.fa --guides example\engine_benchmark_small\guides.tsv --determinism
```

预期：退出码 0；`docs/seed_plan_sweep.json` 至少 16 条记录；确定性子命令输出四个相同的 SHA-256。

## 7. 交付要求

- 完成后：`state.json` 置 `ready_for_review` 并更新 `updated`，写 `report.md`
- `report.md` 必填：改动文件+行号表格、命令原文与输出原文、未做项及原因、附带发现（只记录不修）、待明确项
- 不要自己裁定「通过」；核验归 master