# 交付打包（release bundle）

把一个可以直接交给导师或合作者查看的包打出来：当前工作区的代码（包含尚未
提交的改动）加上投稿用的稿件、补充材料和图件。

## 前置条件

- 仓库根目录可读，`git` 可用；`native/bin/` 下至少有一个已编译的
  `offtarget-engine` 或 `offtarget-engine.exe`。
- 稿件门禁依赖 `tools/manuscript_lineage.py` 记录的印章状态。
- `docs/submission/` 与 `docs/figures/` 是本机内部材料。只打纯代码包时使用
  `--skip-submission`；缺少这些材料且未加该开关时，脚本会直接退出并提示。

## 使用

```powershell
python tools\build_release_bundle.py
python tools\build_release_bundle.py --out D:\handoff
python tools\build_release_bundle.py --date 2026-10-27
python tools\build_release_bundle.py --no-zip     # 只保留目录
python tools\build_release_bundle.py --zip-only   # 只出 zip，不落目录（最快）
python tools\build_release_bundle.py --jobs 8     # 并发复制线程数
python tools\build_release_bundle.py --skip-submission     # 纯代码包，不收录投稿材料
python tools\build_release_bundle.py --skip-lineage       # 跳过稿件印章检查
python tools\build_release_bundle.py --skip-import-smoke  # 跳过入口导入冒烟
python tools\build_release_bundle.py --skip-leak-scan     # 跳过站点信息扫描
python tools\build_release_bundle.py --include-vendored   # 把 external_tools/ 一并打包
```

`--include-vendored` 反转第三方 vendored 源码的默认策略，见下文「排除内容」第一条：
不加该开关时 `external_tools/` 不随包分发（默认口径），加上后整个目录连同许可证
文件进入 `code/external_tools/`。两种口径构建出的 `PACKAGE_CONTENTS.md` 都会写明
本包采用哪一种，`MANIFEST.md` 也记录 `vendored third-party sources` 一行，因此
拿到包的人不会靠猜。若请求了 `--include-vendored` 但工作树里没有
`external_tools/`，脚本直接退出（`--include-vendored was requested but nothing
under external_tools/ was copied`），不会生成声称随包分发却缺文件的包。

三个门禁默认开启：稿件印章检查、入口导入冒烟、整包站点信息扫描。只有明确知道
为什么跳过时才使用 `--skip-*`；跳过扫描不会把命中写进清单。

在 SMB 共享盘上打包时，脚本只读一遍源码：复制、SHA256 和 zip 条目共用
同一份内存字节，目录遍历使用 `scandir` 的元数据，已压缩格式（docx/pdf/png）
不再二次压缩。`docs/` 全量目录约 390 个文件时，一次打包约 1 分钟；
`--zip-only` 可再省掉一半写入时间。

默认输出到仓库同级目录 `release/`，产物是：

```text
release/
  TargetDesign-workbench_2026-10-27/
    MANIFEST.md
    PACKAGE_CONTENTS.md
    code/
    submission/
  TargetDesign-workbench_2026-10-27.zip
```

脚本只读工作区，不修改任何源码；重复执行会重建同名目录与 zip。

## 收录内容

`code/` 收录当前工作树中的程序本体：

- 根目录入口与依赖清单：`README.md`、`README.zh-CN.md`、`main.py`、`unified_gui.py`、
  `designer_workbench.py`、`run_tests.py`、`requirements*.txt`（含
  `requirements-test.txt`，两份 README 都让收件人 `pip install -r` 它）、
  `pyproject.toml`、`Dockerfile`、`docker-compose.yml`、`LICENSE`、`CITATION.cff` 等。
- 代码目录：`basic/`、`shared/`、`webapp/`、`tools/`、`tests/`、`native/`、
  `requirements/`、`sample_data/`、
  `Target_xbp_Target/`、`Target_xbp_Y_zbp_Target/`、`docs/`。
- 示例：`example/engine_benchmark_small/`、`example/batch/`。
- `shared/output/` 是随包发布的源码包（`__init__.py`、`candidate_export.py`、
  `output_columns.py`、`xlsx_utils.py`），不是运行产物。
- `.gitignore` 与 `.github/workflows/container.yml`、`portability.yml`；
  `tests/test_constraints.py` 和 `tests/test_container_workflow.py` 会读取它们。
- Windows 启动器 `TargetDesign-workbench.exe` 与 `native/bin/` 下的预编译引擎。
- `docs/` 下的工程记录随包发布：`refactor_plan.md`、`PHASE3_ACCEPTANCE.md`、
  `PHASE5_ADVANCED_MODES.md`、`UPGRADE_REPORT.md`、`OFFTARGET_HARDENING_*.md`、
  `SEED_PLAN_ANALYSIS.md`、`ALLEGRO_REFERENCE_ANALYSIS.md`、
  `EXPRESSIVENESS_MATRIX.md`、`NATIVE_INDEXED_BENCHMARK.md`、`BULGE_FIXTURE.md`。
  它们是开发过程材料，写进 `.gitignore` 只表示「不进公开仓库」，不表示内部保密；
  交付包与容器都照常收录，同样受整包脱敏扫描约束。
- 未提交的新文件同样会被收录，例如 `shared/scoring/deepcrispr_convert.py`；
  `MANIFEST.md` 会逐条列出构建时的 `git status`，便于核对"待发布"状态。

`submission/` 收录 `SUBMISSION_SHORT_v1` 这一版投稿件：

- `SUBMISSION_SHORT_v1.docx` / `.md`
- `SUPPLEMENTARY_v1.md` / `.pdf`
- `figures/`：正文图与 graphical abstract 的 PDF/PNG

文件清单与版本定义复用 `tools/build_release_stage.py` 的 `submission_files()`
和 `SUBMISSION_FIGURES_SHORT`，两处不会漂移。

## 排除内容

- 第三方 vendored 源码：整个 `external_tools/`，包括上游 crispAI 源码目录和它的
  许可证文件，以及 `external_tools/DeepCas12a*/` 权重。`docs/CRISPAI.md` 已声明本
  项目只提供适配器、不分发上游代码，发布包与之保持一致；收件人按该文档从上游仓库
  自行获取 `crispAI_score/`。包里保留的是本项目自己的
  `shared/scoring/crispai_runtime.py`、`tools/score_crispai.py` 和
  `tools/build_crispai_env.sh`。
  需要反过来把上游源码随包交给收件人时，用 `--include-vendored` 构建另一个变体：
  整个 `external_tools/`（含 `LICENSE`）复制进 `code/external_tools/`，
  `PACKAGE_CONTENTS.md` 与 `MANIFEST.md` 会写明本包采用了哪一口径，请求该口径却
  没有可复制的 vendored 文件时脚本直接退出。默认口径不变，仍是排除。
- 模型权重：`models/`，以及 `.pth`、`.pt`、
  `.h5`、`.npz`、`.ckpt`、`.tar.gz` 等权重格式。
- 大体积数据与中间结果：除 `example/engine_benchmark_small/` 和 `example/batch/`
  之外的 `example/` 内容。
- 运行产物：`logs/`、`output/`、`out/`、`backup/`、`jobs/`、`webapp/jobs/`、
  `__pycache__/`、`*.pyc`。注意 `shared/output/` 是源码，不在此列。
- 构建树：`native/build*/`（CMake 配置与编译中间产物，含 `build/`、`build-windows/`、`build-x86_64/`）。
- 本机专用文件：`docs/SSH_ACCESS.md`、`tools/release_scan_denylist.local.txt`。
  排除清单本身是公开信息，只写文件名，不含主机名、IP 或账号。
- 内部材料：`docs/submission/`、`docs/figures/`、`docs/qa/`、`docs/handoff/`、
  `docs/archive/`、`docs/PAPER_*`、`docs/FIGURE_TABLE_PLAN.md`、
  `docs/NAR_FORMAT_CHECKLIST.md` 等。
- `.git/`、虚拟环境、`.codex*`。

## 校验

1. 清单脱敏：`MANIFEST.md` 记录 git HEAD、分支、未提交改动列表、inventory
   digest 与每个文件的大小和 SHA256；repository/output 两行只写
   `<redacted build-machine path>`。
2. 关键文件必检：`shared/output/` 四个模块、`.gitignore`、两个 workflow、
   `shared/scoring/deepcrispr_convert.py`、`webapp/services/models.py`、
   `requirements-test.txt`、任一个 native 引擎（`offtarget-engine` 或
   `offtarget-engine.exe`）、`SUBMISSION_SHORT_v1.docx`、`SUPPLEMENTARY_v1.pdf`
   和第一张正文图；缺任何一项直接失败。`TargetDesign-workbench.exe` 只在源文件
   存在时必检。
3. 入口导入冒烟：在复制后的 `code/` 中实际导入 `schema`、
   `designer_workbench` 和 `webapp.app`，避免再发出缺 `shared/output/` 的包。
   子进程带 `PYTHONDONTWRITEBYTECODE=1`，否则这一步会往已交付的 `code/` 里写下
   `__pycache__/*.pyc`，使目录内容多于 `MANIFEST.md` 的清单（zip 不受影响）。
4. 整包脱敏扫描：对目录（或 `--zip-only` 解出的临时目录）运行
   `build_release_stage.scan()`；站点身份类命中直接拒发，其余仅报告。
   缺少未跟踪的 `tools/release_scan_denylist.local.txt` 时降级为只跑仓库内
   通用规则，并打印 warning，不再中止。
5. 执行位保真：`native/bin/offtarget-engine`、`native/bin/offtarget-engine-tests`
   与 `tools/*.sh` 在目录和 zip 中都保持 0755。这三个名字同时写进
   `EXECUTABLE_PATHS`，因为 Windows 打包机上既读不到 POSIX 权限位、这些二进制
   也不在 git 索引里，白名单是唯一可靠的途径。
6. `unzip -t` / `Expand-Archive` 可验证 zip 完整性。
7. 发布说明脱敏：`python tools/check_release_notes.py <notes.md>` 用同一组
   通用规则加本地 denylist 检查拟发布的 release notes / tag message。命中
   `BLOCKING_LEAK_LABELS`（主机名、内网路径、home/UNC/环境变量路径）时 exit 1
   拒发；`drive letter`、agent 品牌、技能名等 report-only 标签只列出，与整包
   扫描口径一致。文件读不到时打印 `cannot read <name>` 后 exit 1，不抛 traceback。
8. 换行归一化：`_normalize_lf()` 把每个非压缩格式的字节流里的 CRLF 与孤立 CR 折成
   LF，SHA256 按归一化后的字节计算。这样包内字节与公开仓库的 blob 一致，尤其是
   `.gitattributes` 用 `-text` 声明按字节交付的 `example/` 与 `tests/data/`；
   Windows 工作树的 CRLF 不再随包发布。docx/pdf/png/gz 等容器格式不受影响。
   归一化会改变 `example/engine_benchmark_small/guides.tsv` 这类按字节交付的
   fixture，所以生成方 `tools/benchmark_all_engines.py` 的 `csv.DictWriter` 必须
   显式 `lineterminator="\n"`，`fixture.json` 的写入也必须带 `newline=""`；否则
   重新生成的字节（csv 默认 CRLF）与 `fixture.json`、`docs/seed_plan_sweep.json`
   记录的 `guides_sha256` 对不上，`tests/test_seed_plan_sweep.py` 会立刻失败。

9. 版本 DOI 一致性：`python tools/check_release_metadata.py` 除比对
   version / title / authors / ORCID 外，还拒绝未决的 DOI 占位注释、非 Zenodo
   形式的 `doi`，以及在本地已打 `v<version>` tag 时仍指向概念 DOI 的情况；
   详见「发布顺序：预留 DOI」。
10. 包内容锚点：`MANIFEST.md` 的 `- inventory digest:` 行是对两份清单的全部
    `section<TAB>path<TAB>size<TAB>sha256` 行排序后再取 SHA256，只由交付字节决定，
    与打包机是否在 git 工作树里无关。zip 旁边同时写 `<zip>.sha256`
    （`sha256sum` 格式，在 zip 所在目录 `sha256sum -c <name>.zip.sha256` 即可校验
    传输是否完整；gate 拒发或中途失败时不会留下过期的 sidecar）。复核用
    `python code/tools/check_bundle_inventory.py <包目录 | 包 zip | MANIFEST.md>`：
    它按清单逐项比对磁盘上的大小与 SHA256，并重算 digest；digest 与表格不一致，
    或有文件缺失/被改动，都 exit 1。构建时若 `git HEAD` 为 `unknown`
    （打包机不在 git 工作树内），`MANIFEST.md` 会显式写明该包没有 commit 锚点，
    此时 inventory digest 是唯一的内容锚点。**正式对外发布请始终在 git 工作树中
    构建**，让 `git HEAD` 记下真实 commit；digest 与 sidecar 只回答“这个包是否
    与构建时一致”，不能替代版本锚点。
11. `tests/test_check_release_notes.py`、`tests/test_release_metadata.py` 与
    `tests/test_release_bundle.py` 覆盖以上第 2、5、7、8、9、10 条的判定分支。

## 发布顺序：预留 DOI

一个版本只发布一次、只回填一次 DOI。Zenodo 的 draft 可以先预留版本 DOI，所以
不必「先发布再补」，被 tag 的那份快照本身就是正确的：

1. 升版本号：`pyproject.toml`、`CITATION.cff`、`.zenodo.json` 三处一致，
   `python tools/check_release_metadata.py` 通过。
2. 在 Zenodo 上为该 draft **预留 DOI**（Reserve DOI），记下分配到的版本 DOI。
3. 把该 DOI 写进 `CITATION.cff` 的 `doi` 字段，并把 `date-released` 改成实际
   发布日。`CITATION.cff` 里不留任何「待回填」式注释。
4. 提交这一处改动，然后打 tag `v<version>` 并推送。
5. 用 `python tools/check_release_notes.py <notes.md>` 检查拟发布的 release
   notes / tag message，通过后再创建 GitHub Release。
6. Zenodo 的 GitHub 集成随 tag 归档该版本；预留的 DOI 即正式生效。

`check_release_metadata.py` 的 DOI 检查覆盖第 3 步的两类失误：注释里残留
`replace with` / `TBD` / `待补` 一类的未决占位，以及 `doi` 不是 Zenodo 形式。
此外它还会在**本地存在 `v<version>` 这个 tag** 时拒绝 `doi` 仍等于概念 DOI
（`10.5281/zenodo.23231712`）——即「已发布却忘了回填」。在不含 `.git` 的目录
（交付包、`--zip-only` 的临时目录）里这一半无法判定，脚本会安静跳过，不误报。

概念 DOI 本身是合法的长期引用入口，两份 README 的 Citation 段只指概念 DOI，
不写具体版本号，因此发布后无需回改 README。

## 稿件准入规则（印章）

两个打包入口（`build_release_bundle.py` 与 `build_release_stage.py`）在复制
任何文件之前都会运行 `tools/manuscript_lineage.py check`。校验不通过就直接
退出，不会生成包。

规则要求：

- `docs/submission/manuscript_lineage.json` 存在且 schema 正确；
- 印章里记录的基线、当前稿 `.docx` / `.md`、补充材料的 SHA256 全部未变；
- `docs/` 下（`docs/archive/` 与 `branch_base/` 除外）有且仅有一个 `.docx`，
  即当前稿；任何旧稿必须先归档；
- 当前稿 `.docx` 不早于 `.md`，且 `.md` 正文块在 `.docx` 中的覆盖率不低于
  90%；
- 当前稿相对 r9 rev22 基线的正文保留率不低于 90%，并且至少新增一个块，
  防止误把别的文章当成修改分支。

正常改稿流程：

```powershell
python docs\submission\build_submission_docx.py --version short
python tools\manuscript_lineage.py seal --note "改了什么"
python tools\build_release_bundle.py
```

`seal` 会把新的哈希写进印章并追加一条修订记录；它自身也会先跑同样的结构
检查，所以线路不对的稿子连印章都盖不上。只想查看状态时用：

```powershell
python tools\manuscript_lineage.py status
```

## 与 `build_release_stage.py` 的区别

| 工具 | 用途 | 内容 |
| --- | --- | --- |
| `tools/build_release_stage.py` | 期刊投稿系统上传 | 手稿 + 补充数据 + 论文点名的证据文件 |
| `tools/build_release_bundle.py` | 交给导师/合作者查看 | 完整可运行代码（含未提交改动）+ 投稿件 |

投稿上传仍然使用 `build_release_stage.py`；日常交付、内部评审和给导师看进度
使用本工具。
