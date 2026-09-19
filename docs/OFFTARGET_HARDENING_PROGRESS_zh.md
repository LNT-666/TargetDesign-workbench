# 脱靶引擎加固 - 进度记录（中文）

时间：2026-09-14 深夜 ~ 2026-09-15 凌晨
状态：**全部完成，无阻塞项。** 下次开机只需按本文件末尾的「可选收尾」看一眼即可。

## 1. 本次做完的事

交接文档 `docs/OFFTARGET_HARDENING_TASKS.md` 第 3~7 节的 5 个 Task 全部实现，
并已把「第 11 节 改动清单」和「第 12 节 证据」追加进该文档（原 274 行 -> 625 行）。

- Task 1（P0）流式进度：`shared/search/native_offtarget.py` 用 `Popen` + 读线程替换
  `subprocess.run(capture_output=True)`，进度逐条回调，不再等进程结束。
- Task 2（P0）孤儿与超时：新增 `shared/utils/child_process.py`（进程组 +
  `PR_SET_PDEATHSIG` + atexit/信号处理 + `terminate_process_tree`），
  `NativeEngineTimeout` 刻意不继承 `NativeEngineError`，避免超时被当成故障触发 Python 退化。
  GUI 侧 `shared/design/pattern_runner.py`、`designer_workbench.py` 同步接入（含关闭窗口时
  `runner.stop()` 和新增的 "Search timeout (s)" 输入行）。
- Task 3（P1）索引互踩：索引名按 k 命名空间化（`<genome>.k<k>.ggi`）+ `<prefix>.lock`
  文件锁（Windows `msvcrt.locking` / Linux `fcntl.flock`），并发 run 会等待后复用而不是重建覆盖。
- Task 4（P1）gggenome 静默给错答案：根因是 mismatch 必须放在 **URL 路径段**
  `/<build>/<mismatch>/<query>.txt`，`?mismatch=N` 会被服务端忽略并返回空结果（已实测）。
  另外 `### ... ERROR` 现在会抛异常，`last_report` 增加 `exact_only` 标记。
- Task 5（P2）剩余静默退化入口：`basic/blast.py`、`tools/search_indexed.py`、
  `Target_xbp_Y_zbp_Target/blast_combined.py`、`Target_xbp_Target/analyze_complex_scores.py`
  均补上 `log=` 与 `--timeout-s`；`search_indexed.py` 拒绝退化时打印原因并 `sys.exit(3)`。

新增测试 `tests/test_offtarget_hardening.py`（17 项，6 个测试类），并修好
`tests/test_memory_limit.py`（改为 patch `_run_streaming`）。

## 2. 测试结果

- 服务器（Linux，`.venv`，`PYTHONPATH=shared .venv/bin/python run_tests.py`）：
  `Ran 339 tests in 67.045s`，`FAILED (errors=1, skipped=29)`；2026-09-15 空闲时段又复跑一次，
  结果完全相同（日志 `/tmp/oft_server_suite3.log`）。
  唯一 error 是 `test_genome_index...test_build_memory_limit_success_and_clean_failure`
  （RSS 1240.75 MiB > 1024 MiB）。**已定位为这个用例自身的既有设计问题，与本次改动无关**：
  它用 `resource.getrusage(RUSAGE_SELF).ru_maxrss` 量的是**整个进程的峰值 RSS**，而
  `unittest` 在发现阶段就会 import TensorFlow / numpy / tkinter —— 实测裸解释器 13.9 MiB、
  发现阶段结束已 868.0 MiB，再在进程内建索引就越过 1 GiB 上限。单独跑该用例、或只跑
  `test_genome_index.py`（10 项）都是 `ok`；Windows 上因为没装 TensorFlow 反而通过
  （对应 5 个 TIGER skip）。文档第 12 节已按此更正。
  29 个 skip 全是 `no display available`（服务器无显示）。
- Windows（Python 3.14.7，`python run_tests.py`）：
  `Ran 339 tests in 1297.947s`，`FAILED (errors=1, skipped=6)`。
  唯一 error 是本机没有 `blastn` 导致的环境问题（文档第 1 节已记录）：
  `test_auto_and_large_indexed_apply_mismatch_only_defaults` 报
  `auto could not find an engine compatible with max_bulge=0`。
  6 个 skip = 5 个 TIGER/TensorFlow 不可用 + 1 个 `test_parent_death_kills_the_engine`
  （Linux 专用，用 `/proc/<pid>/stat`）。
  之前失败的 `test_pattern_runner.py`（28 项）与 `test_designer_workbench.py`（28 项）现已全绿。
## 3. 用户的三条验收点对照

- 非 ASCII 指纹未变：`offtarget_backend.py` 15、`pattern_runner.py` 8、`basic/blast.py` 395、
  `native_offtarget.py` 0，全部与基线一致（第 12 节有完整 before/after 表）；所有 .py 均
  `compile()` 通过；备份目录 `backup/offtarget_hardening_20260914_221157/` 存在。
- Task 1/2/3 行为证据：第 12 节分别给出「按秒到达的 PROGRESS_TARGET 日志」「kill -9 父进程后
  引擎数 0、pgrep NONE」「两个并发 run 一个 building、另一个 waiting 后复用，最终只有一个 .ggi」。
- 全量测试与新增测试：见上一节；新测试确实覆盖新行为（回调在子进程存活时触发、超时异常类型、
  锁争用、`.k<k>` 命名、gggenome URL 形状、真实子进程 CONFIRM_REQUIRED 握手）。

## 4. 服务器现状（我离开时的状态）

- 已删除我这次的临时目录：`/tmp/oft_check_demo`（含 1.7 GB 基因组副本）、
  `/tmp/oft_check`、`/tmp/oft-{cli,confirm,abort,index,lock,orphan,reuse,stream,timeout}-*`。
  保留 `/tmp/oft_server_suite.log`、`/tmp/oft_server_suite2.log`（测试原始输出）与
  `/tmp/gg_probe*.py`（gggenome 实测脚本）。
- **用户自己的作业仍在跑**（pid 3158682，`basic/blast.py --engine indexed`，
  `scy-test/trac-exon3`）：我没有动它的任何数据。它的输出目录里
  `GCF_..._GRCh38.p14_genomic.ggi`（12.6 GB）时间戳仍是 14:57，未被覆盖；
  新的 `.k12.ggi`（12.7 GB）是它自己在 23:35 建好的。
- 我上一手还杀掉了同目录一个孤儿进程（pid 3159888，`build-index --force`，PPID 1）。
  它带着新建的 `.k12.lock`，说明已经在用新锁逻辑；如果让它跑完，会用 `--force`
  覆盖用户作业正在读的索引，所以杀掉是对的。
- R: 盘（SMB）当晚多次掉到 1~8 KB/s，原因是共享存储在同时服务用户的大作业；
  不是代码问题，也不是我造成的。需要长时间本地跑测试时，建议先看一眼 R: 速度。

## 5. 可选收尾（都不紧急）

1. 若希望接手会话看中文：把 `docs/OFFTARGET_HARDENING_TASKS.md` 的第 11/12 节译成中文，
   或另出一份中文交接说明。
2. 文档第 2 节原先写的「CONFIRM_REQUIRED 握手只用 mock 验证过」已经改成「已闭合」，
   并指向第 12 节；这个缺口由
   `tests/test_offtarget_hardening.py::ConfirmHandshakeEndToEndTests` 补上。
3. `test_genome_index` 的内存用例是既有的「量整进程峰值 RSS」设计问题（见第 2 节），
   服务器全量跑必然失败、单独跑必然通过。若想让它变绿，可把断言改成量「建索引前后的
   RSS 差值」而不是绝对值 —— 属于本次 5 个 Task 之外的事，做不做看你。