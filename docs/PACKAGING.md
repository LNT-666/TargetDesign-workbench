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
```

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
  `designer_workbench.py`、`run_tests.py`、`requirements*.txt`、`pyproject.toml`、
  `Dockerfile`、`docker-compose.yml`、`LICENSE`、`CITATION.cff` 等。
- 代码目录：`basic/`、`shared/`、`webapp/`、`tools/`、`tests/`、`native/`、
  `requirements/`、`sample_data/`、`external_tools/crispAI-main/`、
  `Target_xbp_Target/`、`Target_xbp_Y_zbp_Target/`、`docs/`。
- 示例：`example/engine_benchmark_small/`、`example/batch/`。
- `shared/output/` 是随包发布的源码包（`__init__.py`、`candidate_export.py`、
  `output_columns.py`、`xlsx_utils.py`），不是运行产物。
- `.gitignore` 与 `.github/workflows/container.yml`、`portability.yml`；
  `tests/test_constraints.py` 和 `tests/test_container_workflow.py` 会读取它们。
- Windows 启动器 `TargetDesign-workbench.exe` 与 `native/bin/` 下的预编译引擎。
- 未提交的新文件同样会被收录，例如 `shared/scoring/deepcrispr_convert.py`；
  `MANIFEST.md` 会逐条列出构建时的 `git status`，便于核对"待发布"状态。

`submission/` 收录 `SUBMISSION_SHORT_v1` 这一版投稿件：

- `SUBMISSION_SHORT_v1.docx` / `.md`
- `SUPPLEMENTARY_v1.md` / `.pdf`
- `figures/`：正文图与 graphical abstract 的 PDF/PNG

文件清单与版本定义复用 `tools/build_release_stage.py` 的 `submission_files()`
和 `SUBMISSION_FIGURES_SHORT`，两处不会漂移。

## 排除内容

- 模型权重：`models/`、`external_tools/DeepCas12a*/`，以及 `.pth`、`.pt`、
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

1. 清单脱敏：`MANIFEST.md` 记录 git HEAD、分支、未提交改动列表与每个文件的
   大小和 SHA256；repository/output 两行只写 `<redacted build-machine path>`。
2. 关键文件必检：`shared/output/` 四个模块、`.gitignore`、两个 workflow、
   `shared/scoring/deepcrispr_convert.py`、`webapp/services/models.py`、任一个
   native 引擎（`offtarget-engine` 或 `offtarget-engine.exe`）、
   `SUBMISSION_SHORT_v1.docx`、`SUPPLEMENTARY_v1.pdf` 和第一张正文图；缺任何
   一项直接失败。`TargetDesign-workbench.exe` 只在源文件存在时必检。
3. 入口导入冒烟：在复制后的 `code/` 中实际导入 `schema`、
   `designer_workbench` 和 `webapp.app`，避免再发出缺 `shared/output/` 的包。
4. 整包脱敏扫描：对目录（或 `--zip-only` 解出的临时目录）运行
   `build_release_stage.scan()`；站点身份类命中直接拒发，其余仅报告。
   缺少未跟踪的 `tools/release_scan_denylist.local.txt` 时降级为只跑仓库内
   通用规则，并打印 warning，不再中止。
5. 执行位保真：`native/bin/offtarget-engine` 与 `tools/*.sh` 在目录和 zip 中都
   保持 0755。
6. `unzip -t` / `Expand-Archive` 可验证 zip 完整性。
7. 发布说明脱敏：`python tools/check_release_notes.py <notes.md>` 用同一组
   通用规则加本地 denylist 检查拟发布的 release notes / tag message。

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
