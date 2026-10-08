#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import argparse
import sys
import os
import subprocess
import threading
import webbrowser
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared"))

from data.annotation_utils import (
    ensure_plain_fasta, is_gzip_file, load_gene_list, open_annotation_text,
    plain_fasta_is_current,
)
from design.library_preflight import LEGACY_ENGINE_CHOICES
from design.system_presets import get_preset
from utils.process_utils import run_subprocess
from utils import system_memory
from data.local_extract import get_region_sequence
from utils.log_utils import (
    LogWriter, install_excepthook, open_log_dir, parse_progress_line,
)
import scoring.model_registry as model_registry
import scoring.deep_models as deep_models
import gui.gui_common as gui_common

# 切换到脚本所在目录（根目录）
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 子 GUI 脚本路径（相对于根目录）
GUI_SCRIPTS = {
    "basic": os.path.join("basic", "gui.py"),
    "Target_xbp_Target": os.path.join("Target_xbp_Target", "gui.py"),
    "Target_xbp_Y_zbp_Target": os.path.join("Target_xbp_Y_zbp_Target", "gui.py"),
}
LIBRARY_SCRIPT = os.path.join("shared", "design", "library_pipeline.py")
INDEX_BUILD_SCRIPT = os.path.join("tools", "build_genome_index.py")


class MainApp(gui_common.CommonGUIMixin):
    def __init__(self, root, as_panel=False, motif_launcher=None):
        self.root = root
        self.motif_launcher = motif_launcher
        if not as_panel:
            self.root.title("TargetDesign-workbench")
            self.root.geometry("1000x800")
            self.root.resizable(True, True)
        self.init_common(root, workspace_dir=os.path.dirname(os.path.abspath(__file__)))

        self.process = None
        self.gene_cache = {}
        self.target_options = []
        self.mask_options = []
        self._gtf_cache = {}
        self._genome_cache = {}
        self.model_vars = {}
        self.model_status_labels = {}
        self.model_buttons = {}
        self.model_progress = {}
        self.model_progress_vars = {}
        self.model_downloading = set()

        # 初始化进度条变量
        self.progress_var = tk.IntVar()
        self.progress_label = tk.StringVar()

        # Genome database 自动构建开关
        self.build_blastdb_var = tk.BooleanVar(value=True)
        # 屏蔽与目标相同开关
        self.mask_same_as_target_var = tk.BooleanVar(value=True)

        self.log_writer = LogWriter("main")
        install_excepthook(self.log_writer)
        self.create_widgets()
        if not as_panel:
            workspace_mapping = self._workspace_mapping()
            self.setup_workspace_menu(workspace_mapping)
            self.apply_workspace(workspace_mapping)
        self.log(f"Log file: {self.log_writer.path}")
        if not as_panel:
            self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- 辅助函数 ----------
    def _get_prepared_gtf(self, raw_gtf):
        """添加 UTR（若没有）并返回处理后的 GTF 路径"""
        if not raw_gtf or not os.path.exists(raw_gtf):
            return None
        if raw_gtf in self._gtf_cache:
            cached = self._gtf_cache[raw_gtf]
            if plain_fasta_is_current(cached, raw_gtf):
                return cached
            self.log(f"Prepared annotation is stale or missing, re-generating: {cached}")
            del self._gtf_cache[raw_gtf]

        output_dir = self.entry_output.get().strip() or os.path.dirname(raw_gtf) or os.getcwd()
        os.makedirs(output_dir, exist_ok=True)

        is_gz = is_gzip_file(raw_gtf)

        base = os.path.basename(raw_gtf)
        while True:
            lowered = base.lower()
            for suffix in ('.gz', '.gff', '.gff3', '.gtf'):
                if lowered.endswith(suffix):
                    base = base[:-len(suffix)]
                    break
            else:
                break

        if '_with_utrs' in base and not is_gz:
            self._gtf_cache[raw_gtf] = raw_gtf
            return raw_gtf

        has_utr = False
        try:
            with open_annotation_text(raw_gtf) as f:
                for _ in range(100):
                    line = f.readline()
                    if not line:
                        break
                    if line.startswith('#'):
                        continue
                    cols = line.split('\t')
                    if len(cols) >= 3 and cols[2] in ('five_prime_UTR', 'three_prime_UTR', "5'UTR", "3'UTR"):
                        has_utr = True
                        break
        except Exception:
            pass

        if has_utr and not is_gz:
            self.log("Annotation file already contains UTR, no need to add")
            self._gtf_cache[raw_gtf] = raw_gtf
            return raw_gtf

        utr_path = os.path.join(output_dir, f"{base}_with_utrs.gff3")
        # 与 genome 副本同一套新鲜度规则：源注释更新后不再复用旧产物
        if not plain_fasta_is_current(utr_path, raw_gtf):
            if os.path.exists(utr_path):
                self.log(f"UTR file is stale, re-generating: {utr_path}")
            self.log(f"Adding UTR (file: {raw_gtf}) ...")
            cmd = [sys.executable, os.path.join("shared", "data", "add_utrs_to_gff.py"), raw_gtf]
            with open(utr_path, 'w', encoding='utf-8') as f:
                # 子进程 stdout 也必须写 UTF-8，否则 Windows 上非 ASCII 注释会变成 GBK 字节
                proc = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE,
                                      text=True, encoding='utf-8',
                                      env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            if proc.returncode != 0:
                self.log(f"Failed to add UTR: {proc.stderr}")
                if os.path.exists(utr_path):
                    os.remove(utr_path)
                return None
            self.log(f"UTR added: {utr_path}")
        else:
            self.log(f"Using existing UTR file: {utr_path}")

        self._gtf_cache[raw_gtf] = utr_path
        return utr_path

    def _get_prepared_genome(self):
        """返回可直接读取的纯文本基因组 FASTA 路径（gz 输入会就近解压并缓存）。

        缓存命中也会按 C4 复查新鲜度：源文件更新（或副本被删/改名）后自动重新解压；
        失败返回 None。
        """
        raw_genome = self.entry_genome.get().strip()
        if not raw_genome or not os.path.exists(raw_genome):
            return None

        cached = self._genome_cache.get(raw_genome)
        if cached and plain_fasta_is_current(cached, raw_genome):
            return cached
        if cached:
            self.log(f"Plain genome FASTA is stale or missing, re-preparing: {cached}")
            self._genome_cache.pop(raw_genome, None)

        fallback_dir = None
        entry_output = getattr(self, "entry_output", None)
        if entry_output is not None:
            fallback_dir = entry_output.get().strip() or None

        prepared = ensure_plain_fasta(
            raw_genome, log_func=self.log, fallback_dir=fallback_dir
        )
        if not prepared:
            self._genome_cache.pop(raw_genome, None)
            return None
        self._genome_cache[raw_genome] = prepared
        return prepared

    def _write_fasta(self, content, filename):
        outdir = self.entry_output.get().strip()
        if not outdir:
            messagebox.showerror("Error", "Please set output directory first")
            return None
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, filename)
        with open(path, 'w') as f:
            f.write(content)
        self.log(f"FASTA written to: {path}")
        return path

    def _extract_sequences(self, identifier, region_type, region_num, id_type, gtf_path):
        """
        提取序列，返回列表 [(header, formatted_seq), ...]
        其中 formatted_seq 为每行60个字符格式化后的序列字符串
        """
        genome = self._get_prepared_genome()
        if not genome or not os.path.exists(genome):
            raise FileNotFoundError("Genome FASTA file not specified or not found")
        if not gtf_path or not os.path.exists(gtf_path):
            raise FileNotFoundError("GTF file not specified or not found")

        ids = [x.strip() for x in identifier.split(',') if x.strip()] if ',' in identifier else [identifier]
        results = []
        for gid in ids:
            header, seq = get_region_sequence(
                genome, gtf_path, gid,
                region_type, region_num,
                id_type=id_type
            )
            formatted_seq = "\n".join([seq[i:i+60] for i in range(0, len(seq), 60)])
            results.append((header, formatted_seq))
        return results

    # ---------- 下载功能 ----------
    def run_download(self):
        species = self.combo_species.get().strip()
        if not species:
            messagebox.showerror("Error", "Please select organism")
            return
        output_dir = self.entry_download_output.get().strip()
        if not output_dir:
            messagebox.showerror("Error", "Please select download output directory")
            return
        os.makedirs(output_dir, exist_ok=True)

        self.progress_frame.grid()
        self.progress_var.set(0)
        self.progress_label.set("Preparing download...")

        cmd = [
            sys.executable, os.path.join("shared", "data", "download_data.py"),
            "--species", species,
            "--output", output_dir
        ]

        def progress_callback(line):
            parsed = parse_progress_line(line)
            if parsed is not None:
                percent, label = parsed
                self.progress_var.set(percent)
                self.progress_label.set(f"{label} {percent}%")

        def on_finish(returncode):
            self.root.after(0, self._hide_progress)
            if returncode == 0:
                info_path = os.path.join(output_dir, "download_info.json")
                if os.path.exists(info_path):
                    try:
                        import json
                        with open(info_path, 'r') as f:
                            info = json.load(f)
                        genome_fasta = info.get("genome_fasta")
                        gtf_file = info.get("gtf")
                        if genome_fasta and os.path.exists(genome_fasta):
                            self.entry_genome.delete(0, tk.END)
                            self.entry_genome.insert(0, genome_fasta)
                        if gtf_file and os.path.exists(gtf_file):
                            self.entry_gtf.delete(0, tk.END)
                            self.entry_gtf.insert(0, gtf_file)
                        self.log("Download complete; Genome and GTF paths filled in automatically.")
                    except Exception as e:
                        self.log(f"Failed to read download info: {e}")
                else:
                    self.log("Download info file not found; specify Genome and GTF paths manually.")
            else:
                messagebox.showerror("Download failed", "Download failed, see log for details.")

        run_subprocess(self, cmd, "Download Genome and annotation", on_finish, progress_callback)

    def _hide_progress(self):
        self.progress_bar.stop()
        self.progress_bar.configure(mode="indeterminate")
        self.progress_var.set(0)
        self.progress_frame.grid_remove()
        self.progress_label.set("")
    def build_blastdb(self, genome_fasta, output_dir):
        """使用 makeblastdb 构建 Genome database，返回数据库前缀路径"""
        if not genome_fasta or not os.path.exists(genome_fasta):
            raise ValueError("Genome file not found")
        if not output_dir:
            raise ValueError("Output directory not specified")
        os.makedirs(output_dir, exist_ok=True)
        db_prefix = os.path.join(output_dir, "genome_blastdb")
        if os.path.exists(db_prefix + ".nin") and os.path.exists(db_prefix + ".nsq"):
            self.log(f"Genome database already exists, skipping build: {db_prefix}")
            return db_prefix
        self.log(f"Building Genome database: {db_prefix} ...")
        cmd = ["makeblastdb", "-in", genome_fasta, "-dbtype", "nucl", "-out", db_prefix]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.log(f"Genome database built successfully: {db_prefix}")
            return db_prefix
        except subprocess.CalledProcessError as e:
            self.log(f"Genome database build failed: {e.stderr}")
            raise RuntimeError("makeblastdb failed, check Genome file format")
        except FileNotFoundError:
            self.log("Error: makeblastdb not found, install NCBI BLAST+")
            raise RuntimeError("makeblastdb not installed")

    def prepare_data(self):
        raw_genome = self.entry_genome.get().strip()
        raw_gtf = self.entry_gtf.get().strip()
        output_dir = self.entry_output.get().strip()
        if not output_dir:
            messagebox.showerror("Error", "Please specify output directory")
            return
        os.makedirs(output_dir, exist_ok=True)

        if not raw_genome or not os.path.exists(raw_genome) or not raw_gtf or not os.path.exists(raw_gtf):
            species = self.combo_species.get().strip()
            if not species:
                messagebox.showerror("Error", "Please select organism for download")
                return
            self.log("Downloading Genome and annotation...")
            try:
                self.run_download()
                messagebox.showinfo("Info", "Use Download Genome and annotation first, or specify existing files.")
                return
            except Exception as e:
                messagebox.showerror("Download error", str(e))
                return

        genome = self._get_prepared_genome()
        if not genome:
            messagebox.showerror("Error", "Genome FASTA could not be prepared, see log")
            return

        gtf_processed = self._get_prepared_gtf(raw_gtf)
        if not gtf_processed:
            messagebox.showerror("Error", "GTF preprocessing failed")
            return

        target_id = self.entry_target_id.get().strip()
        if not target_id:
            messagebox.showerror("Error", "Please specify Search scope")
            return
        try:
            target_fasta_path = self._extract_target_fasta(gtf_processed, output_dir)
        except Exception as e:
            messagebox.showerror("Search scope extraction failed", str(e))
            return

        # ---------- 处理屏蔽序列 ----------
        try:
            mask_fasta_path = self._extract_mask_fasta(
                gtf_processed, output_dir, target_id, target_fasta_path
            )
        except Exception as e:
            messagebox.showerror("Mask gene extraction failed", str(e))
            return

        # ----- 构建 Genome database -----
        db_path = self.entry_blastdb.get().strip()
        if not db_path and self.build_blastdb_var.get():
            try:
                db_path = self.build_blastdb(genome, output_dir)
                self.entry_blastdb.delete(0, tk.END)
                self.entry_blastdb.insert(0, db_path)
            except Exception as e:
                self.log(f"Genome database build failed: {e}")
                messagebox.showwarning("Genome database build warning", f"Could not build Genome database: {e}\nSub-tools may need a manually specified database.")
        else:
            self.log(f"Using existing Genome database: {db_path if db_path else '(none)'}")

        self.prepared_params = {
            "genome": genome,
            "gtf": gtf_processed,
            "target_fasta": target_fasta_path,
            "mask_fasta": mask_fasta_path,
            "output_dir": output_dir,
            "blastdb": self.entry_blastdb.get().strip(),
        }
        if hasattr(self, "entry_library_genome"):
            if not self.entry_library_genome.get().strip():
                self.entry_library_genome.insert(0, genome)
            if not self.entry_library_output.get().strip():
                self.entry_library_output.insert(0, output_dir)
            if db_path and not self.entry_library_blastdb.get().strip():
                self.entry_library_blastdb.insert(0, db_path)
        self._save_workspace_fields()
        self.log("Data preparation complete! You can now launch sub-tools (parameters auto-filled).")

    def _extract_target_fasta(self, gtf_processed, output_dir):
        target_id = self.entry_target_id.get().strip()
        if not target_id:
            raise ValueError("Please specify Search scope")
        target_region = self.combo_target_region.get()
        target_num = self.entry_target_num.get().strip() if target_region in ["Specific exon", "Specific intron"] else None
        target_id_type = self.combo_target_id_type.get()
        target_fasta_parts = self._extract_sequences(
            target_id, target_region, target_num, target_id_type, gtf_processed
        )
        if not target_fasta_parts:
            raise ValueError("No sequences extracted")
        if len(target_fasta_parts) == 1:
            header = target_fasta_parts[0][0]
            base_name = header.lstrip('>').replace(' ', '_').replace('/', '_')
            target_filename = f"{base_name}.fa"
        else:
            target_filename = "target_sequences.fa"
        content = "\n".join([f"{h}\n{s}" for h, s in target_fasta_parts])
        target_fasta_path = self._write_fasta(content, target_filename)
        if not target_fasta_path:
            raise ValueError("Failed to write Target FASTA")
        return target_fasta_path

    def _extract_mask_fasta(self, gtf_processed, output_dir, target_id, target_fasta_path):
        mask_id = self.entry_mask_id.get().strip()
        if self.skip_mask_var.get():
            self.log("Skip mask option is enabled, no Mask gene FASTA will be generated")
            mask_id = ""
        elif self.mask_same_as_target_var.get():
            mask_id = target_id
            self.log("Mask gene is the same as Target, using Target sequence as Mask gene sequence")
        if not mask_id:
            self.log("No Mask gene identifier provided, no Mask gene FASTA generated")
            return None
        if mask_id == target_id and target_fasta_path:
            self.log("Reusing Target sequence file as Mask gene sequence")
            return target_fasta_path
        mask_region = self.combo_mask_region.get()
        mask_num = self.entry_mask_num.get().strip() if mask_region in ["Specific exon", "Specific intron"] else None
        mask_id_type = self.combo_mask_id_type.get()
        mask_fasta_parts = self._extract_sequences(
            mask_id, mask_region, mask_num, mask_id_type, gtf_processed
        )
        if not mask_fasta_parts:
            raise ValueError("No Mask gene sequences extracted")
        if len(mask_fasta_parts) == 1:
            header = mask_fasta_parts[0][0]
            base_name = header.lstrip('>').replace(' ', '_').replace('/', '_')
            mask_filename = f"{base_name}.fa"
        else:
            mask_filename = "mask_sequences.fa"
        content = "\n".join([f"{h}\n{s}" for h, s in mask_fasta_parts])
        mask_fasta_path = self._write_fasta(content, mask_filename)
        if not mask_fasta_path:
            raise ValueError("Failed to write Mask FASTA")
        return mask_fasta_path

    def extract_target_sequences(self):
        raw_genome = self.entry_genome.get().strip()
        raw_gtf = self.entry_gtf.get().strip()
        output_dir = self.entry_output.get().strip()
        if not output_dir:
            messagebox.showerror("Error", "Please specify output directory")
            return
        if not raw_genome or not os.path.exists(raw_genome) or not raw_gtf or not os.path.exists(raw_gtf):
            messagebox.showerror(
                "Error",
                "Please specify Genome FASTA and GTF/GFF3 files in Data preparation first",
            )
            return
        genome = self._get_prepared_genome()
        if not genome:
            messagebox.showerror("Error", "Genome FASTA could not be prepared, see log")
            return
        gtf_processed = self._get_prepared_gtf(raw_gtf)
        if not gtf_processed:
            messagebox.showerror("Error", "GTF preprocessing failed")
            return
        try:
            target_fasta_path = self._extract_target_fasta(gtf_processed, output_dir)
        except Exception as e:
            messagebox.showerror("Search scope extraction failed", str(e))
            return
        params = dict(getattr(self, "prepared_params", {}) or {})
        params.update({
            "genome": genome,
            "gtf": gtf_processed,
            "target_fasta": target_fasta_path,
            "output_dir": output_dir,
        })
        # When the mask mirrors the search scope (default "Mask gene same as
        # Target") and skip mask is off, reuse the extracted search-scope FASTA
        # so the Designer is pre-filled without a separate mask extraction.
        skip_mask = getattr(self, "skip_mask_var", None)
        mirror_mask = getattr(self, "mask_same_as_target_var", None)
        if not (skip_mask and skip_mask.get()) and mirror_mask and mirror_mask.get():
            params["mask_fasta"] = target_fasta_path
        self.prepared_params = params
        self.log("Target FASTA written: %s" % target_fasta_path)
        messagebox.showinfo(
            "Target extraction complete",
            "Target FASTA written to:\n%s" % target_fasta_path,
        )

    def extract_mask_sequences(self):
        raw_genome = self.entry_genome.get().strip()
        raw_gtf = self.entry_gtf.get().strip()
        output_dir = self.entry_output.get().strip()
        if not output_dir:
            messagebox.showerror("Error", "Please specify output directory")
            return
        if not raw_genome or not os.path.exists(raw_genome) or not raw_gtf or not os.path.exists(raw_gtf):
            messagebox.showerror(
                "Error",
                "Please specify Genome FASTA and GTF/GFF3 files in Data preparation first",
            )
            return
        genome = self._get_prepared_genome()
        if not genome:
            messagebox.showerror("Error", "Genome FASTA could not be prepared, see log")
            return
        gtf_processed = self._get_prepared_gtf(raw_gtf)
        if not gtf_processed:
            messagebox.showerror("Error", "GTF preprocessing failed")
            return
        target_id = self.entry_target_id.get().strip()
        params = dict(getattr(self, "prepared_params", {}) or {})
        target_fasta_path = params.get("target_fasta")
        if self.mask_same_as_target_var.get() and not target_fasta_path:
            if not target_id:
                messagebox.showerror("Error", "Please specify Search scope first")
                return
            try:
                target_fasta_path = self._extract_target_fasta(gtf_processed, output_dir)
            except Exception as e:
                messagebox.showerror("Search scope extraction failed", str(e))
                return
            params.update({
                "genome": genome,
                "gtf": gtf_processed,
                "target_fasta": target_fasta_path,
                "output_dir": output_dir,
            })
        try:
            mask_fasta_path = self._extract_mask_fasta(
                gtf_processed, output_dir, target_id, target_fasta_path
            )
        except Exception as e:
            messagebox.showerror("Mask gene extraction failed", str(e))
            return
        params["mask_fasta"] = mask_fasta_path
        self.prepared_params = params
        if mask_fasta_path:
            self.log("Mask FASTA written: %s" % mask_fasta_path)
            messagebox.showinfo(
                "Mask extraction complete",
                "Mask FASTA written to:\n%s" % mask_fasta_path,
            )
        else:
            self.log("No Mask gene FASTA generated")

    # ---------- Workspace ----------
    def _workspace_mapping(self):
        return {
            "entry_download_output": "download_output",
            "entry_genome": "genome",
            "entry_gtf": "annotation",
            "entry_output": "output_dir",
            "entry_blastdb": "blastdb",
            "entry_library_bed": "library_bed",
            "entry_library_genome": "library_genome",
            "entry_library_output": "library_output",
            "entry_library_index": "index_path",
            "entry_library_blastdb": "library_blastdb",
            "combo_library_search": "engine",
            "combo_library_on_target": "on_target_model",
            "combo_library_off_target": "off_target_model",
        }

    def collect_workspace(self, mapping):
        collected = super().collect_workspace(mapping)
        mode = self._memory_mode_key()
        collected["max_memory_mode"] = mode
        if mode == "custom":
            try:
                collected["max_memory_mb"] = int(
                    self.entry_library_memory.get().strip())
            except ValueError:
                collected["max_memory_mb"] = None
        elif mode == "unlimited":
            collected["max_memory_mb"] = 0
        else:
            collected["max_memory_mb"] = None
        return collected

    def apply_workspace(self, mapping):
        super().apply_workspace(mapping)
        combo = getattr(self, "combo_library_memory_mode", None)
        if combo is None:
            return
        mode = str(
            self.workspace.get("max_memory_mode") or "auto"
        ).strip().lower()
        label = {
            "custom": "Custom",
            "unlimited": "Unlimited",
        }.get(mode, "Auto (50% RAM)")
        combo.set(label)
        if mode == "custom":
            value = self.workspace.get("max_memory_mb")
            if value not in (None, ""):
                self.entry_library_memory.configure(state="normal")
                self.entry_library_memory.delete(0, tk.END)
                self.entry_library_memory.insert(0, str(value))
        self._on_memory_mode_changed()

    # ---------- 启动子工具 ----------
    def launch_gui(self, script_rel_path, name):
        if getattr(self, "motif_launcher", None):
            self.motif_launcher(name)
            return
        script_path = os.path.join(os.path.dirname(__file__), script_rel_path)
        if not os.path.isfile(script_path):
            messagebox.showerror("Error", f"Cannot find {script_path}")
            return

        cmd = [sys.executable, script_path]
        if self.skip_mask_var.get():
            cmd.extend(["--skip_mask"])
        if hasattr(self, 'prepared_params'):
            params = self.prepared_params
            cmd.extend([
                "--genome", params["genome"],
                "--gtf", params["gtf"],
                "--target_fasta", params["target_fasta"],
                "--output_dir", params["output_dir"],
            ])
            if params["mask_fasta"]:
                cmd.extend(["--mask_fasta", params["mask_fasta"]])
            if params["blastdb"]:
                cmd.extend(["--blastdb", params["blastdb"]])
            self.log(f"Launching {name} with common parameters")
        else:
            self.log(f"Launching {name} (no parameters, please enter manually)")

        try:
            if sys.platform == "win32":
                creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                subprocess.Popen(cmd, creationflags=creationflags,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
            self.log(f"Launched {name}")
        except Exception as e:
            messagebox.showerror("Launch error", f"Could not launch {name}: {e}")

    # ---------- Model download management ----------
    def create_library_tab(self, notebook):
        tab = ttk.Frame(notebook, padding="10")
        notebook.add(tab, text="Library")
        tab.columnconfigure(1, weight=1)
        r = 0

        ttk.Label(tab, text="BED regions file:").grid(
            row=r, column=0, sticky=tk.W, pady=2)
        self.entry_library_bed = ttk.Entry(tab, width=55)
        self.entry_library_bed.grid(
            row=r, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        ttk.Button(tab, text="Browse", command=lambda: self.browse_file(
            self.entry_library_bed)).grid(row=r, column=2, padx=5)
        r += 1

        ttk.Label(tab, text="Genome FASTA:").grid(
            row=r, column=0, sticky=tk.W, pady=2)
        self.entry_library_genome = ttk.Entry(tab, width=55)
        self.entry_library_genome.grid(
            row=r, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        ttk.Button(tab, text="Browse", command=lambda: self.browse_file(
            self.entry_library_genome)).grid(row=r, column=2, padx=5)
        r += 1

        ttk.Label(tab, text="Output directory:").grid(
            row=r, column=0, sticky=tk.W, pady=2)
        self.entry_library_output = ttk.Entry(tab, width=55)
        self.entry_library_output.grid(
            row=r, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        ttk.Button(tab, text="Browse", command=lambda: self.browse_directory(
            self.entry_library_output)).grid(row=r, column=2, padx=5)
        r += 1

        settings = ttk.LabelFrame(tab, text="Design and search", padding="5")
        settings.grid(row=r, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        settings.columnconfigure(1, weight=1)
        sr = 0
        ttk.Label(settings, text="System preset:").grid(
            row=sr, column=0, sticky=tk.W, pady=2)
        self.combo_library_preset = ttk.Combobox(
            settings, values=["cas9", "cas12a", "cas12b", "cas13",
                              "tnpb", "custom"],
            state="readonly", width=18)
        self.combo_library_preset.set("cas9")
        self.combo_library_preset.grid(
            row=sr, column=1, sticky=tk.W, padx=5, pady=2)
        sr += 1

        ttk.Label(settings, text="Spacer length:").grid(
            row=sr, column=0, sticky=tk.W, pady=2)
        self.entry_library_spacer = ttk.Entry(settings, width=10)
        self.entry_library_spacer.insert(0, "20")
        self.entry_library_spacer.grid(
            row=sr, column=1, sticky=tk.W, padx=5, pady=2)
        sr += 1

        ttk.Label(settings, text="PAM motif:").grid(
            row=sr, column=0, sticky=tk.W, pady=2)
        self.entry_library_pam = ttk.Entry(settings, width=10)
        self.entry_library_pam.insert(0, "NGG")
        self.entry_library_pam.grid(
            row=sr, column=1, sticky=tk.W, padx=5, pady=2)
        sr += 1

        ttk.Label(settings, text="PAM side:").grid(
            row=sr, column=0, sticky=tk.W, pady=2)
        self.combo_library_pam_side = ttk.Combobox(
            settings, values=["3prime", "5prime"], state="readonly", width=18)
        self.combo_library_pam_side.set("3prime")
        self.combo_library_pam_side.grid(
            row=sr, column=1, sticky=tk.W, padx=5, pady=2)
        sr += 1

        ttk.Label(settings, text="Search engine:").grid(
            row=sr, column=0, sticky=tk.W, pady=2)
        self.combo_library_search = ttk.Combobox(
            settings, values=LEGACY_ENGINE_CHOICES,
            state="readonly", width=18)
        self.combo_library_search.set("exact")
        self.combo_library_search.grid(
            row=sr, column=1, sticky=tk.W, padx=5, pady=2)
        sr += 1

        ttk.Label(settings, text="Memory limit:").grid(
            row=sr, column=0, sticky=tk.W, pady=2)
        self.combo_library_memory_mode = ttk.Combobox(
            settings,
            values=["Auto (50% RAM)", "Custom", "Unlimited"],
            state="readonly",
            width=18,
        )
        self.combo_library_memory_mode.set("Auto (50% RAM)")
        self.combo_library_memory_mode.grid(
            row=sr, column=1, sticky=tk.W, padx=5, pady=2)
        self.combo_library_memory_mode.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._on_memory_mode_changed(),
        )
        sr += 1

        ttk.Label(settings, text="Custom MiB:").grid(
            row=sr, column=0, sticky=tk.W, pady=2)
        self.entry_library_memory = ttk.Entry(settings, width=12)
        self.entry_library_memory.insert(0, "32768")
        self.entry_library_memory.grid(
            row=sr, column=1, sticky=tk.W, padx=5, pady=2)
        self.entry_library_memory.bind(
            "<KeyRelease>",
            lambda _event: self._refresh_memory_resolution(),
        )
        self.memory_resolved_var = tk.StringVar(value="Resolved: detecting...")
        ttk.Label(
            settings,
            textvariable=self.memory_resolved_var,
        ).grid(row=sr, column=2, columnspan=2, sticky=tk.W, padx=5, pady=2)
        sr += 1

        ttk.Label(settings, text="Genome index prefix (optional):").grid(
            row=sr, column=0, sticky=tk.W, pady=2)
        self.entry_library_index = ttk.Entry(settings, width=45)
        self.entry_library_index.grid(
            row=sr, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        ttk.Button(settings, text="Browse",
                   command=self.browse_library_index).grid(
            row=sr, column=2, padx=5)
        ttk.Button(settings, text="Build index",
                   command=self.build_library_index).grid(
            row=sr, column=3, padx=5)
        sr += 1

        ttk.Label(settings, text="Max mismatches:").grid(
            row=sr, column=0, sticky=tk.W, pady=2)
        self.entry_library_max_mismatch = ttk.Entry(settings, width=10)
        self.entry_library_max_mismatch.insert(0, "4")
        self.entry_library_max_mismatch.grid(
            row=sr, column=1, sticky=tk.W, padx=5, pady=2)
        sr += 1

        ttk.Label(settings, text="On-target model:").grid(
            row=sr, column=0, sticky=tk.W, pady=2)
        self.combo_library_on_target = ttk.Combobox(
            settings,
            values=[
                "cropsr", "rules", "deepcas12a", "deepcpf1",
                "rna_rules", "tiger", "omega", "teep",
            ],
            state="readonly", width=18)
        self.combo_library_on_target.set("cropsr")
        self.combo_library_on_target.grid(
            row=sr, column=1, sticky=tk.W, padx=5, pady=2)
        sr += 1

        ttk.Label(settings, text="Off-target model:").grid(
            row=sr, column=0, sticky=tk.W, pady=2)
        self.combo_library_off_target = ttk.Combobox(
            settings,
            values=[
                "cfd", "pfs", "identity", "crispr_m",
                "deepcrispr", "tiger",
            ],
            state="readonly", width=18)
        self.combo_library_off_target.set("cfd")
        self.combo_library_off_target.grid(
            row=sr, column=1, sticky=tk.W, padx=5, pady=2)
        sr += 1

        ttk.Label(settings, text="BLAST db prefix (optional):").grid(
            row=sr, column=0, sticky=tk.W, pady=2)
        self.entry_library_blastdb = ttk.Entry(settings, width=45)
        self.entry_library_blastdb.grid(
            row=sr, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        ttk.Button(settings, text="Browse", command=self.browse_library_blastdb).grid(
            row=sr, column=2, padx=5)
        sr += 1

        self._on_memory_mode_changed()

        self.btn_run_library = ttk.Button(
            tab, text="Run one-click library", command=self.run_library_pipeline)
        self.btn_run_library.grid(
            row=r + 1, column=0, columnspan=3, pady=10)

    def browse_library_blastdb(self):
        path = filedialog.askopenfilename(
            title="Select genome database file",
            filetypes=[("Genome database files", "*.nin *.nsq *.nhr *.nal *.nog"),
                       ("All files", "*.*")])
        if not path:
            return
        base, ext = os.path.splitext(path)
        self.entry_library_blastdb.delete(0, tk.END)
        self.entry_library_blastdb.insert(
            0, base if ext in (".nin", ".nsq", ".nhr", ".nal", ".nog") else path)

    def browse_library_index(self):
        path = filedialog.askopenfilename(
            title="Select genome index file",
            filetypes=[("Genome index", "*.ggi *.json"),
                       ("All files", "*.*")])
        if not path:
            return
        base, ext = os.path.splitext(path)
        self.entry_library_index.delete(0, tk.END)
        self.entry_library_index.insert(
            0, base if ext in (".ggi", ".json") else path)

    def _memory_mode_key(self):
        label = self.combo_library_memory_mode.get()
        if label == "Custom":
            return "custom"
        if label == "Unlimited":
            return "unlimited"
        return "auto"

    def _memory_snapshot(self):
        host = (
            os.environ.get("PROGRAMFILE_REMOTE_HOST")
            or os.environ.get("PROGRAMFILE_SSH_HOST")
            or ""
        ).strip()
        if host:
            return system_memory.resolve_remote_memory(host)
        return system_memory.memory_snapshot()

    def _on_memory_mode_changed(self):
        mode = self._memory_mode_key()
        entry = getattr(self, "entry_library_memory", None)
        if entry is not None:
            entry.configure(state="normal" if mode == "custom" else "disabled")
            if mode == "custom" and not entry.get().strip():
                try:
                    entry.insert(0, str(self._resolved_memory_limit()))
                except ValueError:
                    entry.insert(0, "32768")
        self._refresh_memory_resolution()

    def _refresh_memory_resolution(self):
        label = getattr(self, "memory_resolved_var", None)
        if label is None:
            return
        try:
            limit = self._resolved_memory_limit()
        except ValueError as exc:
            label.set("Resolved: %s" % exc)
            return
        mode = self._memory_mode_key()
        if mode == "unlimited":
            label.set("Resolved: Unlimited")
            return
        if mode == "custom":
            label.set("Resolved: %s (custom)" %
                      system_memory.format_memory_mb(limit))
            return
        snapshot = self._memory_snapshot()
        label.set(
            "Resolved: %s (%s total, %s available)"
            % (
                system_memory.format_memory_mb(limit),
                system_memory.format_memory_mb(snapshot["total_mb"]),
                system_memory.format_memory_mb(snapshot["available_mb"]),
            )
        )

    def _resolved_memory_limit(self):
        mode = self._memory_mode_key()
        if mode == "unlimited":
            return 0
        if mode == "custom":
            raw = self.entry_library_memory.get().strip()
            try:
                value = int(raw)
            except ValueError:
                raise ValueError("custom MiB must be an integer")
            if value < 512:
                raise ValueError("custom MiB must be at least 512")
            return value
        snapshot = self._memory_snapshot()
        value = system_memory.resolve_auto_limit_mb(
            snapshot["total_mb"], snapshot["available_mb"])
        if value <= 0:
            raise ValueError(
                "cannot detect memory on the execution host; "
                "use Custom or Unlimited")
        return value

    def _log_memory_limit(self, limit):
        mode = self._memory_mode_key()
        if mode == "auto":
            snapshot = self._memory_snapshot()
            self.log(
                "Memory limit: auto, resolved=%d MiB "
                "(50%% total, 75%% available guard; total=%d MiB, "
                "available=%d MiB)"
                % (limit, snapshot["total_mb"], snapshot["available_mb"]))
        elif mode == "custom":
            self.log("Memory limit: custom, resolved=%d MiB" % limit)
        else:
            self.log("Memory limit: unlimited")

    def build_library_index(self):
        genome = self.entry_library_genome.get().strip()
        output = self.entry_library_output.get().strip()
        if not genome or not os.path.isfile(genome):
            messagebox.showerror("Error", "Please select a valid Genome FASTA")
            return
        if not output:
            messagebox.showerror("Error", "Please specify output directory")
            return
        try:
            memory_limit = self._resolved_memory_limit()
        except ValueError as exc:
            messagebox.showerror("Error", str(exc))
            return
        self._log_memory_limit(memory_limit)
        os.makedirs(output, exist_ok=True)
        index_dir = os.path.join(output, "genome_index")
        base = os.path.splitext(os.path.basename(genome))[0]
        prefix = os.path.join(index_dir, base)
        self.entry_library_index.delete(0, tk.END)
        self.entry_library_index.insert(0, prefix)

        cmd = [
            sys.executable, INDEX_BUILD_SCRIPT, genome,
            "--output-dir", index_dir,
            "--max-memory-mb", str(memory_limit),
        ]

        def progress_callback(line):
            parsed = parse_progress_line(line)
            if parsed is not None:
                percent, label = parsed
                self.progress_var.set(percent)
                self.progress_label.set(f"{label} {percent}%")

        def on_finish(returncode):
            self.root.after(0, self._hide_progress)
            if returncode == 0:
                self.root.after(0, lambda: messagebox.showinfo(
                    "Index ready",
                    "Genome index written to %s.ggi" % prefix))

        self.progress_frame.grid()
        self.progress_var.set(0)
        self.progress_label.set("Building genome index...")
        run_subprocess(self, cmd, "Build genome index",
                       on_finish, progress_callback)

    def run_library_pipeline(self):
        bed = self.entry_library_bed.get().strip()
        genome = self.entry_library_genome.get().strip()
        output = self.entry_library_output.get().strip()
        if not bed or not os.path.isfile(bed):
            messagebox.showerror("Error", "Please select a valid BED file")
            return
        if not genome or not os.path.isfile(genome):
            messagebox.showerror("Error", "Please select a valid Genome FASTA")
            return
        if not output:
            messagebox.showerror("Error", "Please specify output directory")
            return
        try:
            memory_limit = self._resolved_memory_limit()
        except ValueError as exc:
            messagebox.showerror("Error", str(exc))
            return
        self._log_memory_limit(memory_limit)
        os.makedirs(output, exist_ok=True)

        spacer = self.entry_library_spacer.get().strip() or "20"
        pam = self.entry_library_pam.get().strip() or "NGG"
        preset = get_preset(self.combo_library_preset.get())
        cmd = [
            sys.executable, LIBRARY_SCRIPT,
            bed, genome, output,
            "--mode", "preset",
            "--preset", self.combo_library_preset.get(),
            "--spacer-len", spacer,
            "--pam", pam,
            "--pam-side", self.combo_library_pam_side.get(),
            "--engine", self.combo_library_search.get(),
            "--max-mismatch", self.entry_library_max_mismatch.get().strip() or "4",
            "--on-target-model", self.combo_library_on_target.get(),
            "--off-target-model", self.combo_library_off_target.get(),
            "--max-memory-mb", str(memory_limit),
        ]
        if preset.get("pam_required"):
            cmd.append("--require-pam")
        index_prefix = self.entry_library_index.get().strip()
        if index_prefix:
            cmd.extend(["--index-path", index_prefix])
        db_prefix = self.entry_library_blastdb.get().strip()
        if db_prefix:
            cmd.extend(["--blastdb", db_prefix])

        self.progress_frame.grid()
        self.progress_var.set(0)
        self.progress_label.set("Preparing library...")

        def progress_callback(line):
            parsed = parse_progress_line(line)
            if parsed is not None:
                percent, label = parsed
                self.progress_var.set(percent)
                self.progress_label.set(f"{label} {percent}%")

        def on_finish(returncode):
            self.root.after(0, self._hide_progress)
            if returncode == 0:
                self.root.after(0, lambda: messagebox.showinfo(
                    "Library complete",
                    "Library files written to %s" % output))

        run_subprocess(self, cmd, "Guide library pipeline",
                       on_finish, progress_callback)

    def disable_buttons(self):
        for attr in ("btn_prepare", "btn_start_basic", "btn_start_xbp",
                     "btn_start_yzbp", "btn_run_library"):
            button = getattr(self, attr, None)
            if button is not None:
                button.config(state=tk.DISABLED)

    def enable_buttons(self):
        for attr in ("btn_prepare", "btn_start_basic", "btn_start_xbp",
                     "btn_start_yzbp", "btn_run_library"):
            button = getattr(self, attr, None)
            if button is not None:
                button.config(state=tk.NORMAL)

    def create_models_tab(self, notebook):
        tab = ttk.Frame(notebook, padding="10")
        notebook.add(tab, text="Models")

        ttk.Label(tab, text="Local model downloads", font=('Arial', 11, 'bold'))\
            .pack(anchor=tk.W, pady=(0, 8))

        # Group registered models by their effector protein and render each
        # group as a collapsible section (collapsed by default).
        for protein, keys in model_registry.models_by_protein().items():
            self._create_model_group(tab, protein, keys)

        bottom = ttk.Frame(tab)
        bottom.pack(anchor=tk.W, pady=10)
        ttk.Button(bottom, text="Refresh status", command=self.refresh_models)\
            .pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom, text="Open models folder", command=self.open_models_dir)\
            .pack(side=tk.LEFT, padx=5)

        self.refresh_models()
        notebook.bind("<<NotebookTabChanged>>", lambda event: self.refresh_models())

    def _create_model_group(self, parent, protein, keys):
        """Create a click-to-toggle protein section, collapsed by default."""
        label = model_registry.PROTEIN_LABELS.get(protein, protein)
        summary = "%s (%d)" % (label, len(keys))

        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(6, 0))
        content = ttk.Frame(parent)
        content.columnconfigure(1, weight=1)
        content.columnconfigure(3, weight=1)

        state = {"open": False}

        def toggle():
            state["open"] = not state["open"]
            if state["open"]:
                content.pack(fill=tk.X)
            else:
                content.pack_forget()
            toggle_btn.config(
                text=("[-] " if state["open"] else "[+] ") + summary)

        toggle_btn = ttk.Button(header, text="[+] " + summary, command=toggle)
        toggle_btn.pack(side=tk.LEFT)

        self._fill_model_group(content, keys)
        content.pack_forget()  # start collapsed

    def _fill_model_group(self, parent, keys):
        """Populate the expanded body of a protein section."""
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, columnspan=4, sticky=(tk.W, tk.E))
        for col, text in enumerate(
                ["Model", "Status", "Local file / URL", "Action"]):
            ttk.Label(header, text=text, font=('Arial', 9, 'bold'))\
                .grid(row=0, column=col, sticky=tk.W, padx=5)

        row = 1
        for key in keys:
            row = self._add_model_row(
                parent, key, model_registry.MODELS[key], row)

    def _add_model_row(self, parent, key, info, row):
        """Add one model's status/progress row; return the next grid row."""
        status_var = tk.StringVar(value="Checking...")
        self.model_vars[key] = status_var

        ttk.Label(parent, text=info["name"], width=16)\
            .grid(row=row, column=0, sticky=tk.W, padx=5, pady=3)
        status_label = ttk.Label(
            parent, textvariable=status_var, width=20, anchor=tk.W)
        status_label.grid(row=row, column=1, sticky=tk.W, padx=5, pady=3)
        self.model_status_labels[key] = status_label
        path = model_registry.get_model_path(key)
        display = path if path else info["url"]
        ttk.Label(parent, text=display, foreground="gray")\
            .grid(row=row, column=2, sticky=tk.W, padx=5, pady=3)
        ttk.Label(parent, text=info["description"], foreground="gray",
                  wraplength=420)\
            .grid(row=row, column=3, columnspan=4, sticky=tk.W, padx=5, pady=3)
        row += 1

        actions = ttk.Frame(parent)
        actions.grid(row=row, column=0, columnspan=4, sticky=tk.W,
                     padx=20, pady=(0, 6))
        if model_registry.is_downloadable(info):
            progress_var = tk.DoubleVar(value=0)
            progressbar = ttk.Progressbar(actions, variable=progress_var,
                                          maximum=100, length=220)
            progressbar.pack(side=tk.LEFT, padx=4)
            self.model_progress_vars[key] = progress_var
            self.model_progress[key] = progressbar
            btn_download = ttk.Button(actions, text="Download",
                                      command=lambda k=key: self.download_model_gui(k))
            btn_download.pack(side=tk.LEFT, padx=4)
            btn_delete = ttk.Button(actions, text="Delete",
                                    command=lambda k=key: self.delete_model_gui(k))
            btn_delete.pack(side=tk.LEFT, padx=4)
            self.model_buttons[key] = {"download": btn_download, "delete": btn_delete}
        else:
            btn_open = ttk.Button(actions, text="Open website",
                                  command=lambda k=key: webbrowser.open(model_registry.MODELS[k]["url"]))
            btn_open.pack(side=tk.LEFT, padx=4)
            self.model_buttons[key] = {"download": btn_open, "delete": None}
        return row + 1

    def refresh_models(self):
        style = ttk.Style()
        style.configure("Ready.TLabel", foreground="#1a7f37")
        style.configure("Downloading.TLabel", foreground="#b26a00")
        style.configure("Error.TLabel", foreground="#b42318")
        style.configure("ModelStatus.TLabel", foreground="#555555")

        statuses = model_registry.get_all_statuses()
        for key, var in self.model_vars.items():
            status = statuses[key]
            if key == "crispr_m" and status == "ready":
                status = ("ready_loaded" if deep_models.crispr_m_status(load=False) == "ready"
                          else "ready_unavailable")
            if key == "deepcrispr" and status == "ready":
                status = ("ready" if deep_models.DeepCrisprPredictor.available()
                          else "ready_runtime_missing")
            if key == "deepcas12a" and status == "ready":
                status = ("ready" if deep_models.DeepCas12aPredictor.available()
                          else "ready_runtime_missing")
            if key in self.model_downloading:
                text = "Downloading..."
                label_style = "Downloading.TLabel"
            else:
                text = {
                    "ready": "✓ Ready",
                    "ready_loaded": "Ready (scoring)",
                    "ready_unavailable": "Ready (not loadable)",
                    "ready_runtime_missing": "Downloaded (runtime missing)",
                    "dependency_missing": "Downloaded (runtime missing)",
                    "needs_conversion": "Downloaded (needs conversion)",
                    "not_downloaded": "Not downloaded",
                    "size_mismatch": "⚠ Size mismatch",
                    "web_api": "Online API",
                }.get(status, status)
                if status in ("ready", "ready_loaded"):
                    label_style = "Ready.TLabel"
                elif status in ("ready_unavailable", "ready_runtime_missing",
                                "dependency_missing", "needs_conversion"):
                    label_style = "Error.TLabel"
                elif status == "size_mismatch":
                    label_style = "Error.TLabel"
                else:
                    label_style = "ModelStatus.TLabel"
            var.set(text)
            label = self.model_status_labels.get(key)
            if label:
                label.configure(style=label_style)

            buttons = self.model_buttons.get(key, {})
            download_btn = buttons.get("download")
            delete_btn = buttons.get("delete")
            if download_btn:
                is_file = model_registry.MODELS[key].get("type") == "file"
                if is_file:
                    if key in self.model_downloading:
                        download_btn.config(state=tk.DISABLED, text="Download")
                    elif status in ("ready", "ready_loaded", "ready_unavailable",
                                    "ready_runtime_missing", "dependency_missing"):
                        download_btn.config(state=tk.DISABLED, text="Downloaded")
                    else:
                        download_btn.config(state=tk.NORMAL, text="Download")
            if delete_btn:
                has_file = model_registry.get_model_path(key) and os.path.isfile(model_registry.get_model_path(key))
                delete_btn.config(state=tk.NORMAL if has_file and key not in self.model_downloading else tk.DISABLED)
            if key in self.model_progress_vars:
                progress_var = self.model_progress_vars[key]
                progressbar = self.model_progress.get(key)
                if key not in self.model_downloading:
                    if progressbar:
                        progressbar.stop()
                        progressbar.config(mode="determinate")
                    progress_var.set(
                        100.0 if status in (
                            "ready", "ready_loaded", "ready_unavailable",
                            "ready_runtime_missing", "dependency_missing") else 0.0)

    def download_model_gui(self, key):
        if key in self.model_downloading:
            return
        self.model_downloading.add(key)
        self.refresh_models()
        self.log(f"Downloading model: {key}")
        self.model_vars[key].set("Connecting...")
        if key in self.model_progress_vars:
            self.model_progress_vars[key].set(0)
        progressbar = self.model_progress.get(key)
        if progressbar:
            progressbar.config(mode="indeterminate")
            progressbar.start(10)

        def progress_callback(downloaded, total):
            percent = int(downloaded / max(total, 1) * 100)
            mb_done = downloaded / 1048576.0
            mb_total = total / 1048576.0
            text = f"Downloading {mb_done:.1f}/{mb_total:.1f} MB ({percent}%)"
            self.run_on_ui(self._set_model_progress, key, percent, text)

        def status_callback(status, downloaded, total):
            if status == "connecting":
                text = "Connecting..."
            elif status == "downloading":
                text = ""
                return
            elif status == "retrying":
                mb_done = downloaded / 1048576.0
                text = f"Retrying... {mb_done:.1f} MB downloaded"
            elif status == "curl":
                text = "Switching to curl fallback..."
            elif status == "mirror":
                text = "Trying GitHub mirror..."
            elif status == "done":
                text = "Downloaded"
            else:
                text = "Downloading..."
            self.run_on_ui(
                lambda k=key, text=text: self.model_vars[k].set(text))
            if key in self.model_progress_vars:
                if status == "done":
                    self.run_on_ui(self._finish_model_progress, key)
                elif status == "connecting":
                    bar = self.model_progress.get(key)
                    if bar:
                        self.run_on_ui(
                            lambda b=bar: (
                                b.config(mode="indeterminate"), b.start(10)))

        def worker():
            try:
                path = model_registry.download_model(
                    key,
                    progress_callback=progress_callback,
                    status_callback=status_callback)
                self.run_on_ui(
                    self.log, f"Model downloaded: {key} -> {path}")
            except Exception as e:
                self.run_on_ui(
                    self.log, f"Model download failed ({key}): {e}")
                self.run_on_ui(
                    messagebox.showerror, "Download failed",
                    f"Failed to download {key}: {e}")
            finally:
                self.model_downloading.discard(key)
                self.run_on_ui(self.refresh_models)

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(500, self._poll_model_progress, key)

    def _poll_model_progress(self, key):
        if key not in self.model_downloading:
            return
        info = model_registry.MODELS.get(key, {})
        if not model_registry.is_downloadable(info):
            return
        if info.get("type") == "savedmodel_dir":
            size, expected = model_registry.dir_download_progress(key)
        else:
            path = model_registry.get_model_path(key)
            part = path + ".part" if path else ""
            expected = info.get("expected_bytes")
            if not part or not expected:
                return
            size = os.path.getsize(part) if os.path.isfile(part) else 0
        if size > 0:
            percent = min(100, int(size / max(expected, 1) * 100))
            bar = self.model_progress.get(key)
            if bar:
                bar.stop()
                bar.config(mode="determinate")
            if key in self.model_progress_vars:
                self.model_progress_vars[key].set(percent)
            mb_done = size / 1048576.0
            mb_total = expected / 1048576.0
            self.model_vars[key].set(
                "Downloading %.1f/%.1f MB (%d%%)" % (mb_done, mb_total, percent))
        self.root.after(500, self._poll_model_progress, key)

    def _finish_model_progress(self, key):
        bar = self.model_progress.get(key)
        if bar:
            bar.stop()
            bar.config(mode="determinate")
        if key in self.model_progress_vars:
            self.model_progress_vars[key].set(100)

    def _set_model_progress(self, key, percent, text):
        self.model_vars[key].set(text)
        bar = self.model_progress.get(key)
        if bar:
            bar.stop()
            bar.config(mode="determinate")
        if key in self.model_progress_vars:
            self.model_progress_vars[key].set(percent)

    def delete_model_gui(self, key):
        if not messagebox.askyesno("Delete model", f"Delete local model {key}?"):
            return
        model_registry.delete_model(key)
        self.log(f"Deleted local model: {key}")
        self.refresh_models()

    def open_models_dir(self):
        os.makedirs(model_registry.models_dir(), exist_ok=True)
        if sys.platform == "win32":
            os.startfile(model_registry.models_dir())
        else:
            subprocess.Popen(["xdg-open", model_registry.models_dir()])

    # ---------- 界面构建 ----------
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        header = ttk.Frame(main_frame)
        header.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 4))
        ttk.Label(header, text="Workspace:").pack(side=tk.LEFT)
        ttk.Button(header, text="Load", command=self._load_workspace_fields) \
            .pack(side=tk.LEFT, padx=4)
        ttk.Button(header, text="Save", command=self._save_workspace_fields) \
            .pack(side=tk.LEFT, padx=4)

        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)

        # --- Data preparation ---
        tab0 = ttk.Frame(notebook, padding="10")
        notebook.add(tab0, text="Data preparation")
        tab0.columnconfigure(1, weight=1)
        r = 0

        ttk.Label(tab0, text="Organism (for download):").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.combo_species = ttk.Combobox(tab0, values=["human", "yeast", "mouse", "zebrafish", "fly", "worm"], state="readonly", width=20)
        self.combo_species.set("human")
        self.combo_species.grid(row=r, column=1, sticky=tk.W, padx=5, pady=2)
        r += 1
        ttk.Label(tab0, text="Supported: human, yeast, mouse, zebrafish, fly, worm", font=('Arial',8), foreground='gray')\
            .grid(row=r, column=0, columnspan=3, sticky=tk.W, padx=20, pady=(0,5))
        r += 1

        ttk.Label(tab0, text="Download output directory:").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.entry_download_output = ttk.Entry(tab0, width=50)
        self.entry_download_output.grid(row=r, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        ttk.Button(tab0, text="Browse", command=lambda: self.browse_directory(self.entry_download_output))\
            .grid(row=r, column=2, padx=5, pady=2)
        r += 1

        ttk.Button(tab0, text="Download Genome and annotation", command=self.run_download)\
            .grid(row=r, column=0, columnspan=3, pady=10)
        r += 1
        ttk.Label(tab0, text="After download, Genome FASTA and GTF paths are filled in below",
                  font=('Arial',8), foreground='gray')\
            .grid(row=r, column=0, columnspan=3, sticky=tk.W, padx=20, pady=(0,5))
        r += 2

        ttk.Separator(tab0, orient='horizontal').grid(row=r, column=0, columnspan=3, sticky=tk.EW, pady=5)
        r += 1

        ttk.Label(tab0, text="Genome file (FASTA):").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.entry_genome = ttk.Entry(tab0, width=50)
        self.entry_genome.grid(row=r, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        ttk.Button(tab0, text="Browse", command=lambda: self.browse_file(self.entry_genome))\
            .grid(row=r, column=2, padx=5, pady=2)
        r += 1

        ttk.Label(tab0, text="Annotation file (GTF/GFF3):").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.entry_gtf = ttk.Entry(tab0, width=50)
        self.entry_gtf.grid(row=r, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        ttk.Button(tab0, text="Browse", command=lambda: self.browse_file(self.entry_gtf))\
            .grid(row=r, column=2, padx=5, pady=2)
        r += 1

        ttk.Label(tab0, text="Existing Genome database path (optional):").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.entry_blastdb = ttk.Entry(tab0, width=50)
        self.entry_blastdb.grid(row=r, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        ttk.Button(tab0, text="Browse", command=self.browse_blastdb).grid(row=r, column=2, padx=5, pady=2)
        r += 1

        ttk.Checkbutton(tab0, text="Build Genome database automatically (from Genome FASTA)",
                        variable=self.build_blastdb_var).grid(row=r, column=1, sticky=tk.W, padx=5, pady=2)
        r += 1

        # --- Search scope ---
        tab1 = ttk.Frame(notebook, padding="10")
        notebook.add(tab1, text="Search scope")
        tab1.columnconfigure(1, weight=1)
        r = 0

        ttk.Label(tab1, text="Search scope (Gene Symbol / ENSEMBL ID / coordinates):").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.entry_target_id = ttk.Entry(tab1, width=50)
        self.entry_target_id.grid(row=r, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        # 绑定事件：当目标 ID 改变且屏蔽相同勾选时，同步更新屏蔽 ID
        self.entry_target_id.bind('<KeyRelease>', self.on_target_id_changed)
        r += 1

        id_frame = ttk.Frame(tab1)
        id_frame.grid(row=r, column=0, columnspan=3, sticky=tk.W, pady=5)
        ttk.Label(id_frame, text="Identifier type:").pack(side=tk.LEFT, padx=5)
        self.combo_target_id_type = ttk.Combobox(id_frame, values=["gene_name", "ID", "gene_id", "locus_tag"],
                                                 state="readonly", width=12)
        self.combo_target_id_type.set("gene_name")
        self.combo_target_id_type.pack(side=tk.LEFT, padx=5)
        self.combo_target_id_type.bind('<<ComboboxSelected>>', lambda e: self.load_target_list())
        self.btn_load_target = ttk.Button(id_frame, text="Load search list", command=self.load_target_list)
        self.btn_load_target.pack(side=tk.LEFT, padx=5)
        r += 1

        combo_frame = ttk.Frame(tab1)
        combo_frame.grid(row=r, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        self.combo_target_list = ttk.Combobox(combo_frame, width=30, state="normal")
        self.combo_target_list.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_search_target = ttk.Button(combo_frame, text="Search", width=8,
                   command=lambda: self.filter_combobox_by_input(self.combo_target_list, self.target_options))
        self.btn_search_target.pack(side=tk.LEFT, padx=(5,0))
        self.combo_target_list.bind('<<ComboboxSelected>>', lambda e: self.on_gene_selected(e, self.entry_target_id))
        self.combo_target_list.bind('<KeyRelease>', self.filter_combobox)
        self.combo_target_list.bind('<Return>', lambda e: self.filter_combobox_by_input(self.combo_target_list, self.target_options))
        r += 1

        ttk.Label(tab1, text="Search region:").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.combo_target_region = ttk.Combobox(tab1,
                                                values=["Coding region", "Exonic sequence", "Specific exon", "Introns", "Specific intron", "5' UTR", "3' UTR"],
                                                state="readonly", width=15)
        self.combo_target_region.set("Coding region")
        self.combo_target_region.grid(row=r, column=1, sticky=tk.W, padx=5, pady=2)
        self.combo_target_region.bind("<<ComboboxSelected>>", self.on_target_region_change)
        r += 1

        ttk.Label(tab1, text="Region number (Specific exon/intron only):").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.entry_target_num = ttk.Entry(tab1, width=10)
        self.entry_target_num.grid(row=r, column=1, sticky=tk.W, padx=5, pady=2)
        self.entry_target_num.config(state=tk.DISABLED)
        r += 1

        ttk.Button(tab1, text="Extract Target FASTA", command=self.extract_target_sequences)\
            .grid(row=r, column=0, columnspan=3, pady=10)
        r += 1

        ttk.Separator(tab1, orient='horizontal').grid(row=r, column=0, columnspan=3, sticky=tk.EW, pady=5)
        r += 1

        ttk.Label(tab1, text="Output directory:").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.entry_output = ttk.Entry(tab1, width=50)
        self.entry_output.grid(row=r, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        ttk.Button(tab1, text="Browse", command=lambda: self.browse_directory(self.entry_output))\
            .grid(row=r, column=2, padx=5, pady=2)
        r += 1

        # --- Mask gene ---
        tab2 = ttk.Frame(notebook, padding="10")
        notebook.add(tab2, text="Mask gene")
        tab2.columnconfigure(1, weight=1)
        r = 0

        # 新增复选框：屏蔽与目标相同
        self.mask_same_as_target_var = tk.BooleanVar(value=True)
        self.skip_mask_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tab2, text="Skip mask (do not set)", variable=self.skip_mask_var,
                        command=self.toggle_skip_mask).grid(row=r, column=0, columnspan=3, sticky=tk.W, pady=5)
        r += 1
        self.chk_mask_same = ttk.Checkbutton(tab2, text="Mask gene same as Target", variable=self.mask_same_as_target_var,
                                             command=self.toggle_mask_same)
        self.chk_mask_same.grid(row=r, column=0, columnspan=3, sticky=tk.W, pady=5)
        r += 1

        ttk.Label(tab2, text="Mask gene identifier (optional, leave blank to skip):").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.entry_mask_id = ttk.Entry(tab2, width=50)
        self.entry_mask_id.grid(row=r, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        # 初始时如果勾选，则禁用该输入框
        if self.mask_same_as_target_var.get():
            self.entry_mask_id.config(state=tk.DISABLED)
        r += 1

        id_frame2 = ttk.Frame(tab2)
        id_frame2.grid(row=r, column=0, columnspan=3, sticky=tk.W, pady=5)
        ttk.Label(id_frame2, text="Identifier type:").pack(side=tk.LEFT, padx=5)
        self.combo_mask_id_type = ttk.Combobox(id_frame2, values=["gene_name", "ID", "gene_id", "locus_tag"],
                                               state="readonly", width=12)
        self.combo_mask_id_type.set("gene_name")
        self.combo_mask_id_type.pack(side=tk.LEFT, padx=5)
        self.combo_mask_id_type.bind('<<ComboboxSelected>>', lambda e: self.load_mask_list())
        self.btn_load_mask = ttk.Button(id_frame2, text="Load gene list", command=self.load_mask_list)
        self.btn_load_mask.pack(side=tk.LEFT, padx=5)
        r += 1

        combo_frame2 = ttk.Frame(tab2)
        combo_frame2.grid(row=r, column=1, padx=5, pady=2, sticky=(tk.W, tk.E))
        self.combo_mask_list = ttk.Combobox(combo_frame2, width=30, state="normal")
        self.combo_mask_list.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_search_mask = ttk.Button(combo_frame2, text="Search", width=8,
                   command=lambda: self.filter_combobox_by_input(self.combo_mask_list, self.mask_options))
        self.btn_search_mask.pack(side=tk.LEFT, padx=(5,0))
        self.combo_mask_list.bind('<<ComboboxSelected>>', lambda e: self.on_gene_selected(e, self.entry_mask_id))
        self.combo_mask_list.bind('<KeyRelease>', self.filter_combobox)
        self.combo_mask_list.bind('<Return>', lambda e: self.filter_combobox_by_input(self.combo_mask_list, self.mask_options))
        r += 1

        ttk.Label(tab2, text="Mask gene region:").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.combo_mask_region = ttk.Combobox(tab2,
                                              values=["Coding region", "Exonic sequence", "Specific exon", "Introns", "Specific intron", "5' UTR", "3' UTR"],
                                              state="readonly", width=15)
        self.combo_mask_region.set("Coding region")
        self.combo_mask_region.grid(row=r, column=1, sticky=tk.W, padx=5, pady=2)
        self.combo_mask_region.bind("<<ComboboxSelected>>", self.on_mask_region_change)
        r += 1

        ttk.Label(tab2, text="Region number (Specific exon/intron only):").grid(row=r, column=0, sticky=tk.W, pady=2)
        self.entry_mask_num = ttk.Entry(tab2, width=10)
        self.entry_mask_num.grid(row=r, column=1, sticky=tk.W, padx=5, pady=2)
        self.entry_mask_num.config(state=tk.DISABLED)
        r += 1

        ttk.Button(tab2, text="Extract Mask FASTA", command=self.extract_mask_sequences)\
            .grid(row=r, column=0, columnspan=3, pady=10)
        r += 1

        # Library tab is now available inside each motif GUI and through
        # the web/CLI entry points; uncomment to restore the BED tab here.
        # self.create_library_tab(notebook)

        # --- Model downloads ---
        self.create_models_tab(notebook)

        # 进度条
        self.progress_frame = ttk.Frame(main_frame)
        self.progress_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)
        self.progress_frame.columnconfigure(0, weight=1)
        self.progress_frame.grid_remove()
        self.progress_bar = ttk.Progressbar(self.progress_frame, variable=self.progress_var, maximum=100, length=400)
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E))
        ttk.Label(self.progress_frame, textvariable=self.progress_label).grid(row=0, column=1, padx=5)

        # 日志
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="5")
        log_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(log_frame, width=80, height=12, state='normal', wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.grid(row=1, column=0, sticky=tk.W, pady=(3, 0))
        ttk.Button(log_btn_frame, text="Clear log", command=self.clear_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(log_btn_frame, text="Open log", command=self.open_log).pack(side=tk.LEFT, padx=5)

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)

    # ---------- 辅助方法 ----------
    def browse_file(self, entry):
        path = filedialog.askopenfilename()
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def browse_directory(self, entry):
        path = filedialog.askdirectory()
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def browse_blastdb(self):
        path = filedialog.askopenfilename(title="Select Genome database file",
                                          filetypes=[("Genome database files", "*.nin *.nsq *.nhr *.nal *.nog"), ("All files", "*.*")])
        if path:
            base, ext = os.path.splitext(path)
            if ext in ['.nin', '.nsq', '.nhr', '.nal', '.nog']:
                self.entry_blastdb.delete(0, tk.END)
                self.entry_blastdb.insert(0, base)
            else:
                self.entry_blastdb.delete(0, tk.END)
                self.entry_blastdb.insert(0, path)

    def log(self, msg):
        if hasattr(self, "log_writer"):
            self.log_writer.write(msg)
        root = getattr(self, "root", None)
        if root is not None:
            try:
                self.run_on_ui(self._log_now, str(msg))
                return
            except Exception:
                pass
        self._log_now(str(msg))

    def _log_now(self, msg):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def open_log(self):
        open_log_dir()

    def on_close(self):
        if hasattr(self, "log_writer"):
            self.log_writer.write("Closing main window")
            self.log_writer.close()
        self.root.destroy()

    # ---------- 基因列表加载与搜索 ----------
    def load_target_list(self):
        raw_gtf = self.entry_gtf.get().strip()
        if not raw_gtf:
            messagebox.showerror("Error", "Please specify a GTF/GFF3 file in Data preparation first")
            return
        self.btn_load_target.config(state=tk.DISABLED)
        self.log("Loading search list...")
        threading.Thread(target=self._load_list, args=(raw_gtf, self.combo_target_id_type.get(), "target"), daemon=True).start()

    def load_mask_list(self):
        raw_gtf = self.entry_gtf.get().strip()
        if not raw_gtf:
            messagebox.showerror("Error", "Please specify a GTF/GFF3 file in Data preparation first")
            return
        self.btn_load_mask.config(state=tk.DISABLED)
        self.log("Loading Mask gene list...")
        threading.Thread(target=self._load_list, args=(raw_gtf, self.combo_mask_id_type.get(), "mask"), daemon=True).start()

    def _load_list(self, raw_gtf, id_type, which):
        try:
            processed = self._get_prepared_gtf(raw_gtf)
            if not processed:
                self.run_on_ui(self.log, "GTF preprocessing failed")
                return
            values = load_gene_list(
                processed, id_type, None, self.gene_cache, self.log)
            self.run_on_ui(self._update_list, values, which)
        except Exception as exc:
            self.run_on_ui(
                self.log, f"Failed to load {which} list: {exc}")
        finally:
            if which == "target":
                self.run_on_ui(
                    lambda: self.btn_load_target.config(state=tk.NORMAL))
            else:
                self.run_on_ui(
                    lambda: self.btn_load_mask.config(state=tk.NORMAL))

    def _update_list(self, values, which):
        if which == "target":
            self.target_options = values
            self.combo_target_list['values'] = values
            self.btn_load_target.config(state=tk.NORMAL)
            self.log("Search list loaded")
        else:
            self.mask_options = values
            self.combo_mask_list['values'] = values
            self.btn_load_mask.config(state=tk.NORMAL)
            self.log("Mask gene list loaded")

    def filter_combobox_by_input(self, combobox, full_list):
        current = combobox.get().strip()
        if not current:
            combobox['values'] = full_list
            return
        lower = current.lower()
        filtered = [item for item in full_list if lower in item.lower() or item.lower().startswith(lower)]
        filtered.sort(key=lambda x: (not x.lower().startswith(lower), x))
        combobox['values'] = filtered

    def filter_combobox(self, event):
        widget = event.widget
        if widget == self.combo_target_list:
            full = self.target_options
        elif widget == self.combo_mask_list:
            full = self.mask_options
        else:
            return
        if not full:
            return
        current = widget.get().strip()
        if not current:
            widget['values'] = full
            return
        lower = current.lower()
        filtered = [item for item in full if lower in item.lower() or item.lower().startswith(lower)]
        filtered.sort(key=lambda x: (not x.lower().startswith(lower), x))
        widget['values'] = filtered

    def on_gene_selected(self, event, target_entry):
        selected = event.widget.get()
        if selected:
            target_entry.delete(0, tk.END)
            target_entry.insert(0, selected)

    def on_target_region_change(self, event):
        region = self.combo_target_region.get()
        if region in ["Specific exon", "Specific intron"]:
            self.entry_target_num.config(state=tk.NORMAL)
        else:
            self.entry_target_num.config(state=tk.DISABLED)
            self.entry_target_num.delete(0, tk.END)

    def on_mask_region_change(self, event):
        region = self.combo_mask_region.get()
        if region in ["Specific exon", "Specific intron"]:
            self.entry_mask_num.config(state=tk.NORMAL)
        else:
            self.entry_mask_num.config(state=tk.DISABLED)
            self.entry_mask_num.delete(0, tk.END)

    def toggle_skip_mask(self):
        skip = self.skip_mask_var.get()
        state = tk.DISABLED if skip else tk.NORMAL
        for widget in (self.entry_mask_id, self.combo_mask_id_type, self.btn_load_mask,
                       self.combo_mask_list, self.btn_search_mask, self.combo_mask_region,
                       self.entry_mask_num, self.chk_mask_same):
            widget.config(state=state)
        if skip:
            self.log("Skip mask enabled; Mask gene FASTA will not be generated")
        else:
            self.toggle_mask_same()
            self.on_mask_region_change(None)

    # ---------- 新增：屏蔽相同相关方法 ----------
    def toggle_mask_same(self):
        """当屏蔽相同复选框状态改变时，同步更新屏蔽 ID 输入框"""
        if self.mask_same_as_target_var.get():
            # 从目标 ID 获取并填入屏蔽 ID
            target_id = self.entry_target_id.get().strip()
            self.entry_mask_id.delete(0, tk.END)
            self.entry_mask_id.insert(0, target_id)
            self.entry_mask_id.config(state=tk.DISABLED)
        else:
            self.entry_mask_id.config(state=tk.NORMAL)
            # 可选：清空或保留当前内容，为了不干扰用户，保留

    def on_target_id_changed(self, event):
        """当目标 ID 改变时，如果屏蔽相同勾选，则同步更新屏蔽 ID"""
        if self.mask_same_as_target_var.get():
            target_id = self.entry_target_id.get().strip()
            self.entry_mask_id.delete(0, tk.END)
            self.entry_mask_id.insert(0, target_id)


if __name__ == "__main__":
    import unified_gui
    unified_gui.main()
