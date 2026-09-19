# annotation_utils.py
"""注释 / 基因组 FASTA 的通用读取帮手。

本模块同时承载 gz / 文本读取的通用帮手（注释与 FASTA）。
"""
import re
import os
import gzip
import shutil

def parse_gff_attributes(attr_str):
    """兼容 GFF3 和 GTF 的属性解析"""
    attrs = {}
    if not attr_str or attr_str == ".":
        return attrs
    for item in re.split(r'[;\s]+', attr_str):
        if not item:
            continue
        if '=' in item:
            k, v = item.split('=', 1)
            attrs[k.strip()] = v.strip('"')
        elif ' ' in item:
            k, v = item.split(' ', 1)
            attrs[k.strip()] = v.strip('"')
    return attrs

GZIP_MAGIC = b"\x1f\x8b"


def is_gzip_file(path):
    """按文件头（magic bytes）判断是否为 gzip 文件；路径无效或不可读时返回 False。"""
    try:
        if not os.path.isfile(path):
            return False
        with open(path, 'rb') as f:
            return f.read(2) == GZIP_MAGIC
    except Exception:
        return False


def open_annotation_text(path, encoding="utf-8"):
    """打开注释文件（gzip 自动解压），返回文本句柄，交由调用方 with 管理。"""
    if is_gzip_file(path):
        return gzip.open(path, 'rt', encoding=encoding)
    return open(path, 'r', encoding=encoding)


# 解压产物需要带 pyfaidx / makeblastdb 认得的 FASTA 类扩展名（C3）
FASTA_EXTENSIONS = ('.fa', '.fna', '.fasta', '.fas', '.fsa')
_FASTA_UTF8_BOM = b'\xef\xbb\xbf'
_FASTA_CHUNK_SIZE = 1024 * 1024


def _plain_fasta_name(basename):
    """C3：去掉末尾一个 ".gz"（大小写不敏感）；无 FASTA 类扩展名时补 ".fna"。"""
    name = basename[:-3] if basename.lower().endswith('.gz') else basename
    if os.path.splitext(name)[1].lower() not in FASTA_EXTENSIONS:
        name += '.fna'
    return name


def _first_nonblank_byte(path):
    """流式读取 gz 内容，返回第一个非空字节（跳过 UTF-8 BOM 与空白）；空内容返回 None。"""
    with gzip.open(path, 'rb') as handle:
        while True:
            chunk = handle.read(_FASTA_CHUNK_SIZE)
            if not chunk:
                return None
            if chunk.startswith(_FASTA_UTF8_BOM):
                chunk = chunk[len(_FASTA_UTF8_BOM):]
            stripped = chunk.lstrip(b' \t\r\n\v\f')
            if stripped:
                return stripped[:1]


def _decompress_to_plain_fasta(source, target):
    """C5/C6/C7：流式解压 source 到 target（先写 <target>.part 再原子替换），失败不留半成品。"""
    if _first_nonblank_byte(source) != b'>':
        raise ValueError("decompressed content is not FASTA (first byte is not '>')")
    part = target + '.part'
    try:
        with gzip.open(source, 'rb') as src, open(part, 'wb') as dst:
            shutil.copyfileobj(src, dst, _FASTA_CHUNK_SIZE)
        os.replace(part, target)
    except BaseException:
        try:
            if os.path.exists(part):
                os.remove(part)
        except OSError:
            pass
        raise


def plain_fasta_is_current(target, source):
    """C4：判断 target 能否直接当作 source 的明文副本复用。

    条件：存在、是普通文件、非 gzip、大小 > 0，且 mtime(target) >= mtime(source)。
    """
    try:
        if not os.path.isfile(target) or os.path.getsize(target) <= 0:
            return False
        if is_gzip_file(target):
            return False
        return os.path.getmtime(target) >= os.path.getmtime(source)
    except OSError:
        return False


def ensure_plain_fasta(path, log_func=None, fallback_dir=None):
    """把（可能 gzip 压缩的）基因组 FASTA 准备成可直接 open(...) 读取的纯文本路径（C1-C10）。

    非 gz 输入原样返回；gz 输入解压到 <源目录>/<去掉 .gz 的基名>（C3），
    目标目录不可写时回退到 fallback_dir（C8）；失败记日志并返回 None。
    """
    if not is_gzip_file(path):
        return path

    target_name = _plain_fasta_name(os.path.basename(path))
    source_dir = os.path.dirname(os.path.abspath(path))
    directories = [source_dir]
    if fallback_dir:
        fallback_abs = os.path.abspath(fallback_dir)
        if fallback_abs != source_dir:
            directories.append(fallback_abs)

    failure = None
    for directory in directories:
        target = os.path.join(directory, target_name)
        if plain_fasta_is_current(target, path):
            if log_func:
                log_func(f"Using existing plain FASTA: {target}")
            return target
        try:
            _decompress_to_plain_fasta(path, target)
        except (gzip.BadGzipFile, EOFError, ValueError) as exc:
            # 源文件损坏 / 不是 FASTA：换目录也救不回来
            failure = exc
            break
        except Exception as exc:
            # C8：IO / 权限 / 磁盘等问题，换 fallback_dir 再试
            failure = exc
            continue
        if log_func:
            log_func(f"Decompressed genome FASTA: {target}")
        return target

    if log_func:
        log_func(f"Failed to prepare FASTA ({path}): {failure}")
    return None

def _load_gene_attributes(gff_path, log_func=None):
    """
    读取 GFF3 文件，提取每个基因的多个属性。
    返回一个列表，每个元素为 dict，包含 gene_name, ID, locus_tag, gene_id 等。
    """
    gene_attrs_list = []
    gene_types = ('gene', 'pseudogene', 'ncRNA_gene', 'rRNA_gene', 'tRNA_gene')
    try:
        with open_annotation_text(gff_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('\t')
                if len(parts) < 9:
                    continue
                feature = parts[2]
                if feature not in gene_types:
                    continue
                raw_attrs = parse_gff_attributes(parts[8])
                # 提取需要的属性
                gene_name = raw_attrs.get('gene_name') or raw_attrs.get('Name') or raw_attrs.get('gene')
                gene_id = raw_attrs.get('gene_id')
                id_attr = raw_attrs.get('ID')
                locus_tag = raw_attrs.get('locus_tag')
                # 至少有一个属性才记录
                if gene_name or gene_id or id_attr or locus_tag:
                    gene_attrs_list.append({
                        'gene_name': gene_name,
                        'gene_id': gene_id,
                        'ID': id_attr,
                        'locus_tag': locus_tag,
                    })
        return gene_attrs_list
    except Exception as e:
        if log_func:
            log_func(f"读取注释文件时发生异常: {e}")
        return []

def load_gene_list(gff_path, id_type, combo_list, gene_cache, log_func=None):
    """
    从注释文件中提取指定类型的基因标识符列表，使用缓存实现快速切换。
    参数:
        gff_path: 注释文件路径
        id_type: 要提取的属性类型，如 'gene_name', 'ID', 'locus_tag', 'gene_id'
        combo_list: 用于填充的下拉框对象（需要设置 values），可以为 None
        gene_cache: 缓存字典，结构为 {gff_path: {'attrs_list': [...]}}
        log_func: 日志函数
    返回:
        提取的标识符列表
    """
    if not os.path.exists(gff_path):
        if log_func:
            log_func(f"错误：注释文件不存在 - {gff_path}")
        return []

    # 检查缓存
    if gff_path not in gene_cache:
        if log_func:
            log_func(f"首次加载基因属性，解析文件: {gff_path}")
        attrs_list = _load_gene_attributes(gff_path, log_func)
        gene_cache[gff_path] = {'attrs_list': attrs_list}
    else:
        attrs_list = gene_cache[gff_path]['attrs_list']

    # 根据 id_type 提取对应的值
    values = []
    seen = set()
    for attrs in attrs_list:
        value = attrs.get(id_type)
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    values.sort()

    # 更新下拉框（仅当 combo_list 不为 None 时）
    if combo_list is not None:
        combo_list['values'] = values
        if values:
            combo_list.set(values[0])
        else:
            combo_list.set('')
    # 日志记录
    if log_func:
        log_func(f"已从缓存中提取 '{id_type}' 类型的基因列表，共 {len(values)} 个。")
    return values
