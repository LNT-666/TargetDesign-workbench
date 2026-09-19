# 服务器部署与 GRCh38 全基因组构建

当前推荐优先使用 `native/bin/offtarget-engine` 构建和搜索索引；下面的
Python/`server_build_index.sh` 流程保留为 native 二进制不可用时的 fallback。

本机 17 GB 内存不够一次性构建全 GRCh38 索引，推荐把索引构建放到
Linux 服务器上完成。服务器建议配置：

- Linux，Python 3.10+
- 内存 64 GB+（全基因组构建峰值约 50–64 GB）
- 磁盘至少预留 40 GB
- 已有 GRCh38 FASTA；没有的话先上传，3.3 GB 文件建议走内网或共享盘

## 1. 上传代码（本机 PowerShell）

```powershell
cd D:\songji\programfile
scp -r shared tools requirements.txt user@server:/data/crispr_tool/
```

如果服务器已有 GRCh38，不要重复上传 `example\` 下的 3.3 GB FASTA。
只需要把共享模块、工具脚本和依赖清单传过去。

## 2. 服务器上构建（SSH）

```bash
ssh user@server
cd /data/crispr_tool
native/bin/offtarget-engine build-index \
  --genome /data/GRCh38.fna \
  --prefix /data/grch38_out/genome_index/GRCh38 \
  --k 12 --threads 16
```

如果 native 二进制不可用，再使用 Python fallback：

```bash
bash tools/server_build_index.sh /data/GRCh38.fna /data/grch38_out
```

脚本会自动创建 `.venv_server`、安装 numpy/biopython/pyfaidx，然后构建索引，
结果写到：

```text
/data/grch38_out/genome_index/GRCh38.ggi
/data/grch38_out/genome_index/GRCh38.json
```

构建日志里有 `INDEX_READY` 和 `REPORT_JSON` 两行，`GRCh38.json`
就是运行时间、内存峰值、位置数量等报告。

## 3. 顺手做一次真实搜索验证

把 guide 列表传到服务器，例如 `guides.tsv`：

```text
qid	guide_seq
demo	GCCTTGGCCTCCTAAAGTGC
```

```bash
bash tools/server_build_index.sh /data/GRCh38.fna /data/grch38_out guides.tsv
```

搜索输出在 `/data/grch38_out/search/top_offtargets.tsv`，
报告在 `/data/grch38_out/search/index_report.json`。

## 4. 长任务放后台

构建可能要几十分钟到数小时，建议用 nohup：

```bash
nohup bash tools/server_build_index.sh /data/GRCh38.fna /data/grch38_out \
  > /data/grch38_build.log 2>&1 &
tail -f /data/grch38_build.log
```

## 5. 取回结果（本机 PowerShell）

```powershell
scp -r user@server:/data/grch38_out D:\songji\programfile\example\grch38_server_result
```

之后本机 Library 流程可以直接复用：

```powershell
python shared\design\library_pipeline.py regions.tsv example\GRCh38.fna outdir `
  --engine indexed --index-path example\grch38_server_result\genome_index\GRCh38
```

## 其他选择

- 只有 Windows 服务器：直接跑 `python tools\build_genome_index.py`，但需要
  64 GB+ 内存，且 Python 依赖用 `pip install numpy biopython pyfaidx`。
- 没有现成服务器：租一台 64 GB 内存的云主机（阿里云、腾讯云、AWS 等），
  把 FASTA 放到数据盘再执行同一套命令。
- 内存仍然不够：用 `--contigs NC_000021.9` 等参数逐条染色体构建，
  或用后续的 FM-index/Rust 扩展后端降低峰值内存。
