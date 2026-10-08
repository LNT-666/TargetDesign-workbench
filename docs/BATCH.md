# 批量运行（Batch Run）

## 用途

一次提交可以由两个轴组合出多个「单元（unit）」：

- 轴 1 **search scope**：搜索范围（序列 FASTA 或 BED 区域文件），命令与文档中只能叫 search scope，不要叫 target。
- 轴 2 **pattern 配置**：一整份 `PatternSpec` 的描述（kind + overlay），不要叫 motif。

`tools/batch_run.py` 把这些单元**串行**跑完现有的 `PatternRunner` 管道，逐个单元写入自己的输出目录，并汇总成一张评分总表。每次运行分配一个当日唯一的四位编号（run id），全部产物落在程序目录的 `output/<YYYYMMDD>-<ID>/`（不接受绝对路径；编号规则见「运行编号（run id）」一节）。

## `batch.json` schema

```json
{
  "batch_label": "example-batch",
  "shared": { "genome_fasta": "...", "...": "..." },
  "scopes": [
    { "scope_id": "scope_fa", "search_fasta": "example/chr21_22.fa", "mask_same_as_target": true },
    { "scope_id": "scope_bed", "regions": "example/chr21_22_regions.bed", "mask_same_as_target": true }
  ],
  "patterns": [
    { "pattern_id": "TTAG", "mode": "single_motif_flank",
      "overlay": { "motif": "TTAG", "flank": 20, "side": "downstream" } }
  ],
  "groups": [
    { "group_id": "G1", "scope_ids": ["scope_fa", "scope_bed"], "pattern_ids": ["TTAG"] }
  ]
}
```

完整可运行示例见 `example/batch/example_batch.json`（随仓库入库）。

字段约定：

- `scopes[].scope_id` / `patterns[].pattern_id` / `groups[].group_id` / `batch_label` 只允许 `[A-Za-z0-9._-]`，且各自批内唯一；`scope_id` 非空，`pattern_id` 在下述 Web/API 路径可按默认规则省略。
- 每个 scope **必须有且只有一个** 输入：`search_fasta`（序列，`input_mode=sequence`）或 `regions`（BED，`input_mode=bed`）。
- mask 是 scope-owned：`scopes[].mask_same_as_target`（默认 `true`，用当前 scope 的有效 search FASTA 作为 mask）与 `scopes[].mask_fasta`（显式覆盖 mask）互斥，必须二选一。sequence scope 的默认 mask 就是 `search_fasta`；bed scope 的默认 mask 是 `PatternRunner` 从 `regions + genome_fasta` 抽出的临时 window FASTA。显式 `mask_fasta` 文件缺失时 `--dry-run` 只警告，正式运行前报错。
- `shared` 是所有单元共用的表单值（`genome_fasta`、`annotation`、模型、内存、引擎、GC 过滤、索引路径等）；mask 不属于 `shared`。
- `patterns[].overlay` 是该 pattern 独有的表单值（`motif`/`flank`/`side`/`left_*`/`right_*`/`min_gap`/`max_gap`/`y_sequence` 等），`mode` 决定 kind。
- 保留键（出现在 `shared` 或任一 `overlay` 即报错）：`search_fasta`、`bed_regions`、`input_mode`、`result_label`、`output_dir`、`mask_fasta`、`mask_same_as_target`。`search_fasta`/`bed_regions`/`input_mode` 与两个 mask 键由 scope 决定，`result_label`/`output_dir` 由批量内核决定。
- 每组 `g` 展开为 `scopes_g × patterns_g` 的笛卡尔积；整批 units 为所有组的并集，`(scope_id, pattern_id)` 重复只保留第一次出现的顺序。
- units 顺序固定：组按声明顺序 → 组内 scope 按声明顺序 → 组内 pattern 按声明顺序。
- 校验：scope 未被任何组指派 → 报错；pattern 未被任何组使用 → 警告（不失败）；缺少输入文件在 `--dry-run` 下降级为警告，便于在无数据的机器上预览。

Web/API payload 省略 `patterns[].pattern_id` 时，服务端按 pattern 定义生成合法、可读的默认名：

| mode | 默认名 | 示例 |
| --- | --- | --- |
| `single_motif_flank` | `<motif>` | `TTAG` |
| `motif_gap_motif` | `<left>_<min_gap>-<max_gap>_<right>` | `TTAG_10-40_TCAA` |
| `y_centered_motifs` | `<left>_<y_sequence>_<right>` | `TTAT_TTAA_TTAT` |

自动名仅保留 `[A-Za-z0-9._-]`，并去掉首尾的 `._-`；批内撞名时追加 `_2`、`_3`……
显式 ID 不参与自动改写，重复仍报错。`batch.json` 与 `--units-tsv` 是复现入口，仍要求显式 `pattern_id`。

单元身份：`unit_id = <scope_id>__<pattern_id>`；超过 80 字符时截断到 80 并追加 `_` + 6 位 sha1，保证稳定且唯一。

## CLI 用法

```bash
# 预览（不跑管道；缺文件只警告）
python tools/batch_run.py --spec example/batch/example_batch.json --dry-run

# 正式运行（默认续跑）
python tools/batch_run.py --spec my_batch.json

# 覆盖标签；重跑所有 unit（旧 manifest 会被备份）
python tools/batch_run.py --spec my_batch.json --label my-batch --no-resume

# 只跑指定 (scope_id, pattern_id)，可重复
python tools/batch_run.py --spec my_batch.json --only scope_fa,TTAG

# 复用某一次运行的编号（配合默认 --resume 续跑）
python tools/batch_run.py --spec my_batch.json --run-id 0114

# 高级入口：每行一个 unit 的 TSV
python tools/batch_run.py --units-tsv units.tsv
```

| 参数 | 说明 |
| --- | --- |
| `--spec <batch.json>` | 主入口（与 `--units-tsv` 二选一，必须给一个） |
| `--units-tsv <tsv>` | 高级入口：列 `scope_id  pattern_id  search_fasta  regions  mask_fasta  mask_same_as_target  pattern_json`（`mask_fasta`/`mask_same_as_target` 为可选列），`pattern_json` 为该 pattern 的 overlay（JSON 字符串，`mode` 也在其中）。`mask_fasta` 与 `mask_same_as_target=true` 互斥；两列都空/缺省时默认 same-as-target=true；`mask_same_as_target=false` 且 `mask_fasta` 为空表示显式不使用 mask。该入口仍要求显式 `pattern_id`，不使用默认命名 |
| `--label <name>` | 覆盖 `batch_label`（只影响汇总里的 `batch_id`，不再决定目录名） |
| `--run-id <ID>` | 复用已有运行目录，接受 `0114`、`20261006-0114` 或 `20261006/0114`；不传则每次分配新编号 |
| `--resume` / `--no-resume` | 是否跳过已完成的 unit（默认 `--resume`）；仅在指定同一次运行（`--run-id`）时跨调用生效 |
| `--dry-run` | 只打印校验结果与 units 表，不跑管道 |
| `--only <scope_id>,<pattern_id>` | 过滤最终 units，可重复；过滤后为空报错（退出码 2） |

另有便利函数 `design.batch_spec.expand_scope_dir(directory, suffixes)`：把目录下匹配的 FASTA 展开成 scopes，`scope_id` 取文件名去掉 `.fa`/`.fasta`/`.fna`（含 `.gz` 双层）后缀，按文件名排序，重名追加 `_2`、`_3`。当前 CLI 不暴露目录扫描参数。

## 运行编号（run id）

每次正式运行都会新建 `output/<YYYYMMDD>-<ID>/`：`<YYYYMMDD>` 是分配当天的本地日期，`<ID>` 是当天的四位递增编号。日期做前缀，因此每天都有独立的 0001 到 9999 编号空间（一天最多 9999 次运行）。

- 每天前四次运行固定使用 `0114`、`0514`、`1919`、`0810`（见 `shared/utils/run_index.py` 的 `RESERVED_IDS`；纯属私货）。
- 之后从 `0005` 起依次递增；若递到的数字当天已占用或是保留号就跳过。例如某天第 114 次运行拿到 `0115`，因为 `0114` 已是当天第一次。
- 编号写入 `run.json`，并在 `run.log` 头部记一行；目录一旦存在即视为已占用，因此不会复用编号。
- 不给 `--run-id` 时每次都是全新编号、全新目录，所以默认的 `--resume` 只在同一次运行的目录内生效；想续跑某一次就带上 `--run-id`。
- 事后查看：`python tools/run_lookup.py` 列出最近的运行，`python tools/run_lookup.py 0114` 定位某次运行（跨天重号时显示最近一天，可用 `--day 20261006` 指定）。

## 产物目录结构

```text
output/<YYYYMMDD>-<ID>/
  run.json                   # 运行元数据（run_id、day、label、batch_label、unit_count、created）
  run.log                    # 本次运行的完整控制台日志
  batch.json                 # 规范化后的 spec（含 units / groups），用于复现
  manifest.tsv               # 每个 unit 一行
  manifest.<时间戳>.tsv      # --no-resume 时对旧 manifest 的备份
  summary/batch_scores.tsv   # 纵向拼接的评分汇总
  <unit_id>/                 # 该 unit 的全部产物（沿用 PatternRunner 既有文件名）
```

batch 单元的 `run_label` 固定为空串，仍直接写 `<unit_dir>`，不建运行子目录、
不写 `params.json`；批量复现参数仍以 `batch.json` 与 `manifest.tsv` 为准；运行编号与日志见 `run.json`、`run.log`。

`manifest.tsv` 列固定顺序：

```text
unit_id  scope_id  pattern_id  status  returncode  started  finished  unit_dir  main_table  message
```

- `status ∈ {ok, failed, skipped, stopped}`；`started`/`finished` 为 `%Y-%m-%d %H:%M:%S` 本地时间。
- `unit_dir`、`main_table` 是相对批量根目录的正斜杠路径。
- 每完成一个 unit 立刻重写 manifest（进程被杀也不丢已完成记录）。
- `--only` 局部运行时，manifest = 本次运行的行 + 旧 manifest 中未参与本次运行的 unit 行（保持旧顺序、字段原样）；因此局部重跑不会丢掉其它 unit 的记录，随后整批续跑仍能正确 `skipped`。`--no-resume` 不合并（先备份旧 manifest，再当作空账本）。被 `--only` 跳过的 unit 在随后整批续跑时视为已完成（`skipped`），不会重算。

主评分表（唯一权威定义，见 `docs/OUTPUTS.md`）：

- `single_motif_flank` / `motif_gap_motif` → `<unit_dir>/query_scores_sorted.tsv`
- `y_centered_motifs` → `<unit_dir>/scores.sorted.tsv`

`summary/batch_scores.tsv` 按 manifest 顺序纵向拼接各 unit 主表，只在最前面插入 `batch_id  unit_id  scope_id  pattern_id` 四列，其余列名与顺序原样保留；列取并集、缺列留空。若某主表已有同名四列之一，则注入列改名为 `batch_<name>` 并在日志中说明。

`--only` 局部重跑时，汇总表同样按 manifest 合并规则拼装：本次运行的行 + 旧 manifest 中状态为 `ok`/`skipped` 的未运行 unit 行，因此局部重跑不会截短已有汇总。

## 退出码

| 码 | 含义 |
| --- | --- |
| `0` | 全部 unit `ok`/`skipped` |
| `1` | 至少一个 unit `failed`（失败隔离，不中断整批） |
| `2` | 参数非法或校验失败 |
| `130` | 收到中断（`STOPPED_RETURN_CODE`），立即停止整批 |

## 进度行语义

沿用既有解析器 `webapp/jobs.py:parse_progress_line`，格式不自创：

- 每个 unit 开始时输出 `PROGRESS_TARGET: i/n`（`i` 从 1 起，`n` 为 units 总数）。
- 每个 unit 结束时输出 `PROGRESS: batch <pct>`（0-100 整数）。
- unit 内部 `run_pipeline` 的行通过 `on_line` 原样透传。

## Web 入口

webapp 也提供批量入口（`POST /api/batch/preview`、`POST /api/batch/jobs`，页面 Batch 区块）：payload 字段、`assignments → groups` 转换与 units 顺序（UI 路径为 pattern 主序）见 `docs/WEBAPP.md` 的「批量（Batch）」小节。Batch 区块顶部另有「Task code (Run id)」面板，可复制本次任务码、按任务码查看某一次运行，或列出最近运行（`GET /api/batch/runs`、`GET /api/batch/runs/<run_id>`）。

## 未做项（P2）

- 桌面 GUI 批量面板。
- 并发 / 多进程执行（当前固定串行 1 路）。
- XLSX 汇总（可后续用 `shared/output/xlsx_utils.tsv_to_xlsx` 增加）。
- 目录监听、断点续跑的跨进程锁。
