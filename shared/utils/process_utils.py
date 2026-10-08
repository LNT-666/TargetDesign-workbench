#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import threading
import sys
import os
import json
import re
from tkinter import messagebox

from utils.log_utils import parse_progress_line


def run_subprocess(gui, cmd, description, on_finish=None, progress_callback=None):
    """在后台线程中运行子进程，并实时输出日志"""
    def target():
        retcode = -1
        try:
            gui.log(f"--- Start {description} ---")
            gui.log("Command: " + " ".join(cmd))
            gui.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                encoding='utf-8'
            )
            while True:
                line = gui.process.stdout.readline()
                if not line:
                    break
                gui.log(line.rstrip())
                if progress_callback:
                    try:
                        gui.run_on_ui(progress_callback, line)
                    except Exception:
                        progress_callback(line)
            gui.process.wait()
            retcode = gui.process.returncode
            if retcode == 0:
                gui.log(f"--- {description} complete (return code 0) ---")
            else:
                gui.log(f"--- {description} failed (return code {retcode}) ---")
        except Exception as e:
            gui.log(f"Error: {e}")
            retcode = -1
        finally:
            gui.process = None
            try:
                gui.run_on_ui(gui.enable_buttons)
            except Exception:
                pass
            if on_finish:
                try:
                    gui.run_on_ui(on_finish, retcode)
                except Exception:
                    on_finish(retcode)

    gui.disable_buttons()
    threading.Thread(target=target, daemon=True).start()


def run_download(gui):
    species = gui.entry_download_species.get().strip()
    if not species:
        messagebox.showerror("Missing parameters", "Enter a species name")
        return
    output_dir = gui.entry_download_output.get().strip()
    if not output_dir:
        messagebox.showerror("Missing parameters", "Choose a download output directory")
        return
    source = gui.combo_datasource.get()
    os.makedirs(output_dir, exist_ok=True)

    gui.progress_frame.grid()
    gui.progress_var.set(0)
    gui.progress_label.set("Preparing download...")

    cmd = [
        sys.executable, "download_data.py",
        "--species", species,
        "--output", output_dir,
        "--source", source
    ]

    def progress_callback(line):
        parsed = parse_progress_line(line)
        if parsed is not None:
            percent, label = parsed
            gui.progress_var.set(percent)
            gui.progress_label.set(f"{label} {percent}%")

    def on_finish(returncode):
        gui.root.after(0, _hide_progress, gui)
        if returncode == 0:
            info_path = os.path.join(output_dir, "download_info.json")
            if os.path.exists(info_path):
                try:
                    with open(info_path, 'r') as f:
                        info = json.load(f)
                    genome_fasta = info.get("genome_fasta")
                    gtf_file = info.get("gtf")
                    if genome_fasta and os.path.exists(genome_fasta):
                        gui.entry_genome.delete(0, tk.END)
                        gui.entry_genome.insert(0, genome_fasta)
                    if gtf_file and os.path.exists(gtf_file):
                        gui.entry_gtf.delete(0, tk.END)
                        gui.entry_gtf.insert(0, gtf_file)
                    gui.log("Download complete; genome and GTF paths filled in automatically")
                except Exception as e:
                    gui.log(f"Failed to read download info: {e}")
            else:
                gui.log("Download info file not found; specify the genome and GTF paths manually")
        else:
            messagebox.showerror(
                "Download failed",
                "Failed to download the genome and annotation; see the log for details.\n"
                "This may be a network problem or a stalled download. You can try:\n"
                "1. Check the network connection\n"
                "2. If the download was already started manually, running the script again may resume it.\n"
                "3. Or switch to the Ensembl data source."
            )

    run_subprocess(gui, cmd, "Download genome and annotation", on_finish, progress_callback)


def _hide_progress(gui):
    gui.progress_frame.grid_remove()
    gui.progress_var.set(0)
    gui.progress_label.set("")


def run_extract(gui):
    # 复用原GUI中的验证方法和提取逻辑，但这里为了简洁，直接调用gui中的方法
    # 但最好将验证和提取逻辑移到这里，但为了保持现有代码，我们直接调用gui的现有方法
    # 由于逻辑复杂，暂时保留原有实现，但可以逐步迁移
    # 这里仅作示例，实际可调用 gui._run_extract() 等
    # 但为了模块化，建议将整个run_extract逻辑移到本函数
    # 由于时间关系，我们保留gui中的run_extract逻辑，但通过调用gui的方法实现
    # 更合理的方式：在gui中定义 run_extract，然后在这里调用gui.run_extract()
    # 但我们已将按钮绑定到 run_extract_btn，而run_extract_btn调用 run_extract(gui)
    # 所以这里直接定义 run_extract 函数。
    # 但为了代码完整，我们重新实现一遍，但实际可复制原gui中run_extract的代码。
    # 为节省篇幅，此处简化：调用gui的原有方法（需将原有方法改为接受gui参数）
    # 这里我们直接调用 gui._run_extract_internal()，但需要先定义。
    # 更简单的做法：将run_extract_btn绑定到gui的一个方法，由gui内部处理。
    # 因此，我们不再需要process_utils中的run_extract，只需在gui中保留原有逻辑。
    # 但为了模块化，我们可以将run_extract的逻辑移到本文件，但会涉及大量gui属性访问。
    # 综合考虑，我们保持gui中的run_extract等不变，只将子进程执行和下载移出。
    # 所以这里不实现run_extract，而是由gui自己处理。
    # 我们删除此函数，由gui直接调用本地方法。
    pass


# 在gui中保留 run_extract_btn 直接调用 self.run_extract()，而 run_extract 仍然在gui中。
# 同样 run_blast, run_analyze 也留在gui中。
# 这样只需将下载和子进程基础函数移出来即可。

# 下面保持空函数以占位
def run_extract(gui):
    pass

def run_blast(gui):
    pass

def run_analyze(gui):
    pass
