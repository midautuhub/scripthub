#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
translate_pdf2zh.py —— 用 PDFMathTranslate（pdf2zh）+ Ollama 本地模型翻译大型 PDF
                       教材，单文件，带 Rich 全屏分区式监控面板。

【功能】
  · 整本或指定页范围翻译，按页切片（默认 20 页/片）逐片调用 pdf2zh（-s ollama）
  · 每片完成即写入续跑清单（<stem>.manifest.json）：中断后重跑同一命令，
    已完成片自动跳过，失败片自动重试；全部片成功后才合并（--merge 默认开启）
    ※ 跳过的判定依据是 chunks/ 里仍存在该片的 -mono-sliced/-dual-sliced 产物，
      所以续跑要求 chunks/ 没被删：合并成功且未加 --keep-chunks 时它会删掉，
      此时清单虽仍标「已完成」，重跑会整本重译。长期要保住续跑能力就加
      --keep-chunks，或在合并前中断（chunks/ 尚在）。
    ※ 另一条硬限制（脚本既有行为）：产物文件名取自【当前翻译用的 PDF】——
      默认 --repair 会先生成 <stem>_repaired.pdf 再翻，产物因此叫
      <stem>_repaired-mono-sliced.pdf，而查找用的是原始 <stem>，两者对不上，
      于是默认配置下重跑【永远】重新翻译（日志提示「标记完成但产物已清理」）。
      实测：加 --no-repair 后同命令重跑能正常跳过。因此需要续跑时，两条一起用：
      --no-repair --keep-chunks（或在脚本修正文件名匹配前先按此规避）。
  · 前置自检：PDF 是否存在 / 页数 / 是否文字版 / 全书字数，Ollama 服务与
    指定模型是否就绪，pdf2zh 命令是否可执行
  · 前置清洗：重写 PDF 修掉非法 dict 键，规避 pymupdf 保存阶段崩溃
    （--no-repair 可跳过）
  · 合并分片为成品 PDF（garbage=4 + clean 清理重复与未引用对象），
    合并成功后默认删除分片目录（--keep-chunks 保留）
  · 失败与卡死可诊断：单片超时、pdf2zh 打完 100% 后静默收尾、按页进度前进
    计时判定「仍在推进」与「真卡死」
  · 面板（TTY 下默认启用）分五个区：PDF 文件信息 ｜ Ollama 运行状态
    （连接 / 端口 / 使用模型 / 显存占用）／ 处理阶段五步 ／ 总体进度条 ／
    带级别与时间戳的执行日志
  · 语言参数默认英译中，可用 --src-lang / --dst-lang 改；也接受 English /
    中文 / Chinese / zh-TW 这类写法，脚本归一成 pdf2zh 语言代码
  · 可选自定义翻译提示词（--prompt-file <文件>），默认不启用

【依赖】
  Python 3.12（3.13 有兼容风险）
  ollama    服务已启动，目标模型已 pull
  pdf2zh    pip install uv && uv tool install --python 3.12 pdf2zh
  PyMuPDF   统计字数 / 裁剪 / 合并 / 预处理
  rich      强依赖，缺失时直接报错并以退出码 4 结束（无降级实现）

  安装：
    pip install uv
    uv tool install --python 3.12 pdf2zh
    pip install pymupdf rich
    ollama pull Hy-MT2

【用法 · 完整样例】
  最简：整本翻译，模型用默认值
    python translate_pdf2zh.py "book.pdf"

  指定模型（不指定时：TTY 下交互选择已装模型）
    python translate_pdf2zh.py "book.pdf" --model Hy-MT2

  只自检不翻译：查 PDF 页数 / Ollama 服务与模型 / pdf2zh 是否可用
    python translate_pdf2zh.py "book.pdf" --model Hy-MT2 --dry-run

  只译前 5 页验质量，看版式与术语是否正常
    python translate_pdf2zh.py "book.pdf" --model Hy-MT2 --probe-only

  只译指定页范围（可多段，逗号分隔，越界部分自动裁掉）
    python translate_pdf2zh.py "book.pdf" --pages 1-50
    python translate_pdf2zh.py "book.pdf" --pages 1-5,20-30

  非交互环境 / 重定向输出到文件时手动关面板，用普通滚动日志
    python translate_pdf2zh.py "book.pdf" --model Hy-MT2 --plain > run.log 2>&1

  中断后续跑：原命令再跑一遍，已完成片跳过、失败片重试
    python translate_pdf2zh.py "book.pdf" --model Hy-MT2
    ※ 前提：chunks/ 还在（合并成功会默认删除），且产物文件名要能匹配上。
      默认 --repair 生成的 _repaired 文件名与查找名不一致，会导致重跑全部重译；
      需要续跑请用下面这条（实测可正常跳过）：
    python translate_pdf2zh.py "book.pdf" --model Hy-MT2 --no-repair --keep-chunks

  调参：分片页数 / 单片超时 / 模型常驻时长 / 输出目录 / 保留分片 / 失败即停
    python translate_pdf2zh.py "book.pdf" --model Hy-MT2 ^
        --pages-per-chunk 10 --timeout 1800 --keep-alive 10m ^
        --out-dir D:\\out --keep-chunks --stop-on-error

  指定源语言与目标语言（默认英译中）
    python translate_pdf2zh.py "book.pdf" --src-lang en --dst-lang zh

  语言也可以写全称或中文（脚本归一成代码；认不出的写法会报错退出）
    python translate_pdf2zh.py "book.pdf" --src-lang English --dst-lang 中文
    python translate_pdf2zh.py "book.pdf" --src-lang en --dst-lang zh-TW

  自定义翻译提示词（默认不启用）。文件用 UTF-8，可含占位符
  ${lang_in} / ${lang_out} / ${text}，由 pdf2zh 用上面指定的语言代码填充
    python translate_pdf2zh.py "book.pdf" --prompt-file my_prompt.txt
    python translate_pdf2zh.py "book.pdf" --prompt-file my_prompt.txt ^
        --src-lang en --dst-lang zh
    ※ 文件不存在、不是文件、内容为空（或只有空白）、非 UTF-8 都会直接报错退出。

  面板只在 TTY 下启用；重定向、管道、--plain 时自动退回普通滚动日志。

【参数】
  pdf                   PDF 文件路径（必填）
  --pages               只译指定页范围：1-50 / 1-5,20-30 / 单页 7
  --model               Ollama 模型名，不填则 TTY 下交互选择
  --plain               关闭面板，用普通滚动日志
  --merge / --no-merge  是否合并分片为成品（默认合并）
  --keep-chunks         合并后保留 chunks/ 分片目录（续跑跳过的前提之一，需配合 --no-repair）
  --ollama-host         Ollama 地址，默认 http://127.0.0.1:11434
  --hf-endpoint         下载 DocLayout-YOLO 布局模型的 HF 镜像
  --pages-per-chunk     每片页数，默认 20
  --threads             pdf2zh 并发线程，默认 1；并发过高易 OOM
  --timeout             单片超时秒数，默认 3600
  --keep-alive          ollama 模型常驻时长，默认 30m
  --src-lang / --dst-lang  源 / 目标语言，默认 en / zh（不传时照旧传入 en / zh）。
                        也接受 English、Chinese、中文、zh-TW、日文 等写法，脚本
                        归一成 pdf2zh 语言代码；认不出的写法报错退出。与
                        --prompt-file 同时使用时，提示词里的 ${lang_in} /
                        ${lang_out} 就是归一后的代码
  --prompt-file         自定义翻译提示词文件（UTF-8，非空）。可含 ${lang_in} /
                        ${lang_out} / ${text} 占位符。默认不启用，即用 pdf2zh
                        内置模板；文件不可用时直接报错退出
  --out-dir             输出目录，默认 PDF 同级的 output/
  --total-pages         页数无法自动获取时手工指定
  --ultrafast           跳过 pdf2zh 的精细排版修正，换取速度
  --no-skip-subset-fonts  恢复 pdf2zh 的字体子集化。默认跳过：子集化对超大
                        CJK 字体是超线性开销，且个别 PDF 会在此阶段永久挂死；
                        代价是产物 PDF 偏大
  --stop-on-error       任一分片失败即中止（退出码 2）
  --repair / --no-repair  是否执行 PDF 前置清洗（默认执行）。注意：启用后分片
                        产物名带 _repaired，与续跑查找名不一致，重跑会全部重译
  --dry-run             只做自检与分片规划，不翻译
  --probe-only          只译前 5 页

【退出码】
  0    成功
  1    前置检查或参数错误（文件不存在、页范围越界、模型未装、页面数取不到等）
  2    --stop-on-error 下遇到分片失败
  3    未捕获异常
  4    缺少 rich 依赖
  130   用户中断（Ctrl-C，重跑可续跑）

【产物】
  <out-dir>/<stem>-merged-mono.pdf   纯目标语言版
  <out-dir>/<stem>-merged-dual.pdf   双语对照版
  单分片场景直接拷出 <stem>[-pX-pY]-mono-sliced.pdf / -dual-sliced.pdf
  <out-dir>/<stem>.manifest.json     续跑清单（指定 --pages 时文件名带 scope）
  <out-dir>/translate_logs/          主日志与每片 pdf2zh 原始日志
  <out-dir>/chunks/                  分片中间产物（默认合并后删除）
"""

import argparse
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import textwrap
import threading
import time
from datetime import datetime
from pathlib import Path

# ============================== Rich 依赖检查（强依赖）==============================
try:
    from rich import box as rich_box
    from rich import box
    from rich.align import Align
    from rich.console import Console, Group
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel as RichPanel
    from rich.progress import BarColumn, Progress, TextColumn
    from rich.table import Table
    from rich.text import Text
    _RICH_IMPORT_ERROR = None
except Exception as _e:                                        # pragma: no cover
    _RICH_IMPORT_ERROR = _e


def require_rich():
    """缺 rich 时明确报错并退出（本脚本强依赖 rich）。"""
    if _RICH_IMPORT_ERROR is None:
        return
    sys.stderr.write(
        "\n[错误] 本脚本需要 rich，但导入失败：\n"
        f"        {type(_RICH_IMPORT_ERROR).__name__}: {_RICH_IMPORT_ERROR}\n\n"
        "请先安装：\n"
        "    pip install rich\n"
        "（若用 uv 工具装的 pdf2zh，可改用 pdf2zh 所在环境的 python 运行本脚本）\n\n"
    )
    sys.exit(4)



# ============================== 版本与默认配置 ==============================
BUILD = "2026-10-16.standalone.rich.dark.c"   # c: 阶段⑤完成后状态改「已完成」（含级别2分支）
CORE_BUILD = "2026-10-16.standalone.h"
DEFAULT_MODEL = "Hy-MT2"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"  # 下载 DocLayout-YOLO 布局模型的镜像
DEFAULT_PAGES_PER_CHUNK = 20                    # 每片页数
DEFAULT_THREADS = 1                             # pdf2zh 并发线程（并发过高易 OOM）
DEFAULT_TIMEOUT_PER_CHUNK = 3600                # 单请求超时（秒）
LOG_DIRNAME = "translate_logs"
CHUNKS_DIRNAME = "chunks"

_LOG_FH = None
_parse_logged = {}          # 进度诊断去重（每片打印一次 pdf2zh 原始行）

_PANEL = None               # 当前面板；非 None 时 log() 推给它的日志区
def set_log_sink(panel):
    global _PANEL
    _PANEL = panel


# ============================== 日志 ==============================
def log(msg, level="INFO"):
    """带时间戳打印，同时写入当前日志文件（若已初始化）。

    输出去向由 _PANEL 决定：面板在用时推给面板日志区（不破坏布局），
    否则直接 print（--plain / 非 TTY）。
    """
    global _LOG_FH
    stamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] [{level}] {msg}"
    if _PANEL is not None:
        try:
            _PANEL.log_line(line, level)
        except Exception:
            print(line, flush=True)
    else:
        print(line, flush=True)
    # 非面板模式（_PANEL is None）由上面 print；面板模式由 log_line 缓冲。
    if _LOG_FH:
        try:
            _LOG_FH.write(line + "\n")
            _LOG_FH.flush()
        except Exception:
            pass


def init_log_file(out_dir):
    global _LOG_FH
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"translate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    _LOG_FH = open(path, "a", encoding="utf-8")
    return path


# ============================== 页范围解析 ==============================
def parse_pages(spec):
    """解析页范围字符串，返回 [(start,end), ...] 排序去重。非法输入抛 ValueError。"""
    if not spec:
        return None
    ranges = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a < 1 or b < 1:
                raise ValueError(f"页码必须 >= 1：{part}")
            if a > b:
                a, b = b, a
            ranges.append((a, b))
            continue
        if re.fullmatch(r"\d+", part):
            n = int(part)
            if n < 1:
                raise ValueError(f"页码必须 >= 1：{part}")
            ranges.append((n, n))
            continue
        raise ValueError(f"无法解析页范围：{part!r}（示例：1-50 或 1-5,20-30）")
    if not ranges:
        return None
    ranges.sort()
    merged = [ranges[0]]
    for a, b in ranges[1:]:
        la, lb = merged[-1]
        if a <= lb + 1:
            merged[-1] = (la, max(lb, b))
        else:
            merged.append((a, b))
    return merged


def clamp_ranges(ranges, total):
    out = []
    for a, b in ranges:
        if a > total:
            continue
        out.append((a, min(b, total)))
    return out


def make_chunks(total_pages, per_chunk, ranges=None):
    """生成页码区间列表。ranges=None 时整本按 per_chunk 切。"""
    chunks = []
    spans = ranges if ranges else [(1, total_pages)]
    for (rs, re_) in spans:
        start = rs
        while start <= re_:
            end = min(start + per_chunk - 1, re_)
            chunks.append((start, end))
            start = end + 1
    return chunks


# ============================== 清单（续跑）==============================
def manifest_path(out_dir, src_stem):
    return out_dir / f"{src_stem}.manifest.json"


def load_manifest(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"done": [], "failed": []}


def save_manifest(path, data):
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"清单写入失败：{e}", "WARN")


# ============================== PDF 工具 ==============================
def _import_fitz():
    try:
        import pymupdf as fitz
        return fitz
    except Exception:
        try:
            import fitz
            return fitz
        except Exception as e:
            return None


def repair_pdf(src, dst):
    """清洗重写 PDF，修掉非法 dict 键（规避 pymupdf save 崩溃，官方 issue #1137）。

    递进策略（B8：保持逐级加重，不要改成单档）：
      1) garbage=4 + deflate + clean —— clean=True 会重写内容流，个别畸形 PDF
         可能报错，故下一档作为无 clean 的回退；
      2) garbage=4 + deflate + clean + linear；
      3) garbage=4 + deflate（不带 clean）—— clean 重写失败时的保底。
    三档都失败才报 False。
    """
    fitz = _import_fitz()
    if fitz is None:
        return False, "未安装 PyMuPDF"
    try:
        doc = fitz.open(str(src))
    except Exception as e:
        return False, f"打开失败：{e}"
    try:

        def _try_save(opts):
            """按 opts 保存；成功返回 (True, 描述)，失败返回 (False, 异常)。"""
            try:
                doc.save(str(dst), **opts)
                size_mb = Path(dst).stat().st_size / 1024 / 1024
                return True, f"清洗成功，输出 {size_mb:.1f} MB"
            except Exception as e:
                return False, e

        # 递进链，逐级加重（garbage=4 起步，承接契约 B7/B8）
        attempts = [
            dict(garbage=4, deflate=True, clean=True),
            dict(garbage=4, deflate=True, clean=True, linear=True),
            dict(garbage=4, deflate=True),
        ]
        last_err = None
        for opts in attempts:
            ok, res = _try_save(opts)
            if ok:
                return True, res
            last_err = res
        return False, f"所有清洗策略均失败：{last_err}"
    finally:
        doc.close()


def get_page_count(pdf_path):
    fitz = _import_fitz()
    if fitz is not None:
        try:
            with fitz.open(str(pdf_path)) as doc:
                return doc.page_count
        except Exception:
            pass
    for cmd in (["pdfinfo", str(pdf_path)],):
        if shutil.which(cmd[0]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
                m = re.search(r"Pages:\s+(\d+)", out)
                if m:
                    return int(m.group(1))
            except Exception:
                pass
    return None


def _extract_pages(src_pdf, dst_pdf, start, end, dual, fitz):
    """从整本 PDF 抽出 [start,end] 对应的页。
    mono: 源页 p -> 输出第 p 页
    dual: 源页 p -> 输出第 2*(p-1) 与 2*(p-1)+1 页（原文/译文交替）"""
    src = fitz.open(str(src_pdf))
    try:
        n = src.page_count
        out = fitz.open()
        for p in range(start, end + 1):
            idxs = [2 * (p - 1), 2 * (p - 1) + 1] if dual else [p - 1]
            for idx in idxs:
                if 0 <= idx < n:
                    out.insert_pdf(src, from_page=idx, to_page=idx)
        # garbage=4 + clean：insert_pdf 会把每片的字体/资源/ICC 对象全部带进成品，
        # garbage=3 不清重复/未引用对象，garbage=4 才做最大清理，clean=True 另重写
        # 内容流。实测 8 片合并：g3=21381 字节/127 对象；g4+clean=8694 字节/51 对象，
        # 体积 -59.3%（见 CONTRACT-2.md §2.2）。
        # 个别畸形 PDF clean=True 会报错，故保存失败时回退不带 clean 重试一次（B11）。
        try:
            out.save(str(dst_pdf), garbage=4, deflate=True, clean=True)
        except Exception:
            out.save(str(dst_pdf), garbage=4, deflate=True)
        out.close()
    finally:
        src.close()


def _find_chunk_outputs(chunk_dir, src_stem):
    """在分片目录里找【已裁剪】的产物。返回 (mono|None, dual|None)。"""
    chunk_dir = Path(chunk_dir)
    mono = chunk_dir / f"{src_stem}-mono-sliced.pdf"
    dual = chunk_dir / f"{src_stem}-dual-sliced.pdf"
    return (mono if mono.exists() else None, dual if dual.exists() else None)


def make_heartbeat_log(now, t0, start, end, seen_pages, pages_in_chunk, quiet,
                       chunk_log, progress_quiet=None):
    """心跳行：明确区分「输出静默」与「进度静默」，避免读日志的人误判成卡死。"""
    alive = (now - t0) / 60
    tail = _read_tail(chunk_log, 400).strip()
    extra = (f"｜pdf2zh 最后输出：{tail.splitlines()[-1][:90]}") if tail else ""
    pq = quiet if progress_quiet is None else progress_quiet
    if pq < quiet:
        state = f"页进度静默 {pq:.0f}s（输出静默 {quiet:.0f}s）"
    else:
        state = f"已静默 {quiet:.0f}s"
    return (f"  … 仍在处理 p{start}-{end}（已 {alive:.1f} 分钟，"
            f"页进度 {seen_pages}/{pages_in_chunk}，{state}）{extra}")


def _read_tail(path, n=1000):
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"（日志读取失败：{e}）"
    data = data.strip()
    if not data:
        return "（日志为空——子进程可能还没产生任何输出就卡住了）"
    return data[-n:]


def _parse_progress(line, pages_in_chunk, start=1, total_pages=None):
    """从 tqdm 输出行算【本片已完成页数】(0..pages_in_chunk)，算不出返回 None。

    ⚠ 第一道关：**必须确认这是 tqdm 行**，否则一概返回 None。

    为什么这一步不能省（真实踩过的坑）：
      pdf2zh 把普通日志和 tqdm 进度条混在同一个 stderr 管道里，
      日志行形如：
        [10/15/26 21:20:21] INFO  INFO:pdf2zh.high_level:use font: high_level.py:423
      其中【时间戳 10/15/26】会被 x/y 正则 `(\\d+)\\s*/\\s*(\\d+)` 抓成
      cur=10, tot=15，于是 round(10/15*20)=13 —— 面板一开机就显示
      「当前片 13/20」，而且 13 看起来还"像"个正常进度，极难怀疑到时间戳。
      （日志行往往比 tqdm 第一帧还早，所以它是**首值**。）

    tqdm 行的独有结构 = 百分比 + 竖线包住的进度柱 + x/y，三者同现：
        10%|██        | 2/20 [00:01<00:09]
    因此用「有 `%`」且「有 `|...|` 柱」来认证；日志行没有 `|...|`。

    语义判定（认证为 tqdm 行之后）：
      a) total == pages_in_chunk -> 本片相对计数，直接取 cur。
      b) total == 整本页数      -> cur 是绝对页号，本片进度 = cur-(start-1)。
    百分比仅作没有 x/y 时的兜底。
    """
    clamp = lambda v: max(0, min(pages_in_chunk, int(v)))

    # 0) 认证：不是 tqdm 行就直接放弃（挡住 pdf2zh 的日志行/时间戳）
    if "|" not in line:
        return None
    mp0 = re.search(r"(\d{1,3})\s*%", line)          # tqdm 必带百分比
    if not mp0:
        return None
    # 柱状条必须被竖线包住：  |xxx|
    if not re.search(r"\|[^|]*\|", line):
        return None

    # 1) 优先：x/y 计数 —— total 决定语义
    mc = re.search(r"(\d+)\s*/\s*(\d+)", line)
    if mc:
        try:
            cur, tot = int(mc.group(1)), int(mc.group(2))
        except ValueError:
            cur = tot = None
        if tot is not None and tot > 0:
            if tot == pages_in_chunk:
                return clamp(cur)                       # a) 本片相对计数
            if total_pages is not None and tot == total_pages:
                return clamp(cur - (start - 1))         # b) 整本/绝对页号
            if tot > pages_in_chunk:
                return clamp(cur - (start - 1))
            # tot < pages_in_chunk：无法可靠锚定，按比例保守换算
            return clamp(int(round(cur / tot * pages_in_chunk)))

    # 2) 兜底：百分比（已认证是 tqdm 行，但没有 x/y 结构）
    try:
        pct = int(mp0.group(1))
    except ValueError:
        return None
    if not (0 <= pct <= 100):
        return None
    if total_pages is not None and total_pages > pages_in_chunk:
        return clamp(int(round(pct / 100.0 * total_pages)) - (start - 1))
    return clamp(int(round(pct / 100.0 * pages_in_chunk)))


# ============================== 自检 ==============================
def check_pdf2zh():
    exe = shutil.which("pdf2zh")
    if not exe:
        log("找不到 pdf2zh 命令。请先安装：pip install uv && uv tool install --python 3.12 pdf2zh", "ERROR")
        log("安装后若仍找不到，说明 uv 工具目录不在 PATH，用 `uv tool dir` 找到并加入 PATH。", "ERROR")
        return None
    return exe


# ============================== 语言与提示词 ==============================
DEFAULT_SRC_LANG = "en"
DEFAULT_DST_LANG = "zh"
# pdf2zh 的 -li / -lo 只认语言代码，这里把常见写法（全称 / 大小写 / 中文名）
# 归一成官方代码。不认识的写法直接报错，不静默透传或退回默认值。
LANG_ALIASES = {
    "en": "en", "eng": "en", "english": "en", "英文": "en", "英语": "en",
    "zh": "zh", "zh-cn": "zh", "zh-hans": "zh", "chs": "zh",
    "chinese": "zh", "simplified chinese": "zh", "简体中文": "zh", "中文": "zh",
    "zh-tw": "zh-TW", "zh-hant": "zh-TW", "cht": "zh-TW",
    "traditional chinese": "zh-TW", "繁體中文": "zh-TW", "繁体中文": "zh-TW",
    "ja": "ja", "jp": "ja", "japanese": "ja", "日文": "ja", "日语": "ja",
    "ko": "ko", "kr": "ko", "korean": "ko", "韩文": "ko", "韩语": "ko",
    "fr": "fr", "fra": "fr", "french": "fr", "法文": "fr", "法语": "fr",
    "de": "de", "deu": "de", "german": "de", "德文": "de", "德语": "de",
    "es": "es", "spa": "es", "spanish": "es", "西班牙文": "es", "西班牙语": "es",
    "ru": "ru", "rus": "ru", "russian": "ru", "俄文": "ru", "俄语": "ru",
    "pt": "pt", "por": "pt", "portuguese": "pt", "葡萄牙文": "pt", "葡萄牙语": "pt",
    "it": "it", "ita": "it", "italian": "it", "意大利文": "it", "意大利语": "it",
    "ar": "ar", "ara": "ar", "arabic": "ar", "阿拉伯文": "ar", "阿拉伯语": "ar",
}


class LangError(ValueError):
    """语言参数无法识别。"""


class PromptFileError(ValueError):
    """--prompt-file 指向的文件不可用。"""


def normalize_lang(value, default):
    """把用户给的语言写法归一成 pdf2zh 语言代码。

    value 为 None / 空串 → 返回 default（不改变默认行为）；
    能识别（大小写、下划线/空格不敏感）→ 返回官方代码（如 zh-TW）；
    认不出 → 抛 LangError，由调用方报错退出，绝不静默替换成默认值。
    """
    if value is None:
        return default
    raw = str(value).strip()
    if not raw:
        return default
    key = raw.lower().replace("_", "-")
    hit = LANG_ALIASES.get(key)
    if hit:
        return hit
    hit = LANG_ALIASES.get(key.replace("-", " "))
    if hit:
        return hit
    # 区域写法（en-US / pt-BR）：主语言可识别且后缀是两字母或两位数字才退到主语言，
    # 其余（zh-XXx-YY、xx-YY）一律视为非法，不靠回退蒙对。
    if "-" in key:
        base, _, region = key.partition("-")
        if base in LANG_ALIASES and re.fullmatch(r"[a-z]{2}|\d{3}", region):
            return LANG_ALIASES[base]
    raise LangError(
        f"无法识别的语言：{raw}（请用代码，如 en / zh / zh-TW / ja / fr / de / ko；"
        f"也可用 English / 中文 / Chinese 这类常见写法）")


def resolve_prompt_file(path):
    """校验并解析自定义提示词文件路径。

    返回绝对路径 Path；未指定（None / 空串）返回 None。
    路径不存在、不是文件、内容为空 → 抛 PromptFileError。
    """
    if path is None:
        return None
    raw = str(path).strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    try:
        p = p.resolve()
    except OSError as e:
        raise PromptFileError(f"提示词文件路径无法解析：{raw}（{e}）")
    if not p.exists():
        raise PromptFileError(f"提示词文件不存在：{p}")
    if not p.is_file():
        raise PromptFileError(f"提示词路径不是文件：{p}")
    try:
        size = p.stat().st_size
    except OSError as e:
        raise PromptFileError(f"无法读取提示词文件：{p}（{e}）")
    if size == 0:
        raise PromptFileError(f"提示词文件为空：{p}")
    try:
        body = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise PromptFileError(f"提示词文件不是 UTF-8 编码：{p}（请另存为 UTF-8）")
    except OSError as e:
        raise PromptFileError(f"无法读取提示词文件：{p}（{e}）")
    if not body.strip():
        raise PromptFileError(f"提示词文件只有空白字符：{p}")
    return p


def check_ollama(host, model):
    import urllib.request
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        log(f"无法连接 ollama 服务 {host}：{e}", "ERROR")
        log("请在另一个窗口运行：ollama serve", "ERROR")
        return False, []
    names = [m.get("name", "") for m in data.get("models", [])]
    base = model.split(":")[0]
    hit = any(n == model or n.startswith(base + ":") for n in names)
    if not hit:
        log(f"模型 {model} 未安装。请运行：ollama pull {model}", "ERROR")
        return False, names
    log(f"ollama 服务正常，模型 {model} 已就绪")
    return True, names


def list_ollama_models(host):
    import urllib.request
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def choose_model_interactive(models, panel=None):
    """交互选择模型。

    ⚠ 必须在【清屏】后输入：面板用的是 alternate screen（全屏），
      输入前先交出屏幕（panel.suspend() 会退出全屏并清屏），
      输入完再 panel.resume() 重新接管，避免提示语和面板叠在一起。
    """
    def _ask(prompt):
        try:
            return input(prompt).strip()
        except EOFError:
            return ""

    if panel is not None:
        panel.suspend()
    try:
        if models:
            print("\n检测到以下已安装的 Ollama 模型：")
            for i, name in enumerate(models, 1):
                print(f"  [{i}] {name}")
            print("  [0] 手动输入其他模型名")
            raw = _ask("请选择模型编号（直接回车=取消）: ")
            if not raw:
                return None
            if raw == "0":
                return _ask("请输入模型名: ") or None
            if raw.isdigit() and 1 <= int(raw) <= len(models):
                return models[int(raw) - 1]
            return raw or None
        print("\n未能从 Ollama 获取已安装模型列表（服务未启动？）。")
        return _ask("请手动输入模型名: ") or None
    finally:
        if panel is not None:
            panel.resume()


# ============================== 子进程执行（pdf2zh）==============================
def run_pdf2zh(pdf2zh_exe, pdf_path, start, end, args, chunk_out_dir, panel=None):
    """调用 pdf2zh CLI 翻译指定页区间。

    返回 (ok, elapsed_sec, err_msg, pages_done, mono_path, dual_path)。

    ⚠ 要点
      1. pdf2zh 输出名只取决于【输入文件名】，所以每条分片必须独立输出目录。
      2. 进度是 tqdm 的 "\\r 刷新、不换行" 输出；用后台线程按【块】读，
         把 \\r 和 \\n 都当行界 —— 否则最后一行没换行会让读循环永久阻塞。
      3. pdf2zh 打完 100% 后还要做字体子集化 / 写 PDF，期间完全静默；
         此时打心跳、给诊断，绝不误判成卡死。
    """
    chunk_out_dir = Path(chunk_out_dir)
    chunk_out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        pdf2zh_exe, str(pdf_path),
        "-p", f"{start}-{end}",
        "-li", args.src_lang,
        "-lo", args.dst_lang,
        "-s", "ollama",
        "-t", str(args.threads),
        "-o", str(chunk_out_dir),
    ]
    if args.ultrafast:
        cmd.append("--ultrafast")
    if args.skip_subset_fonts:
        # 默认开启：绕开 pdf2zh 收尾阶段的字体子集化（慢 + 可能挂死）。
        # 日志里显式说明，避免用户以为输出了问题。
        cmd.append("--skip-subset-fonts")
    # 自定义提示词：仅在 --prompt-file 指定时追加，默认不传（行为与旧版一致）。
    # 语言占位符 ${lang_in} / ${lang_out} 由 pdf2zh 用上面的 -li / -lo 填充。
    if getattr(args, "prompt_file", None):
        cmd += ["--prompt", str(args.prompt_file)]

    chunk_log_dir = chunk_out_dir.parent / LOG_DIRNAME
    chunk_log_dir.mkdir(parents=True, exist_ok=True)
    chunk_log = chunk_log_dir / f"chunk_p{start}-{end}.log"

    t0 = time.time()
    log(f"  执行：{' '.join(cmd)}")
    if args.skip_subset_fonts:
        log("  （已启用 --skip-subset-fonts：跳过字体子集化，"
            "规避收尾阶段卡死；产物会大 ~13-16MB/册）")
    else:
        log("  （未跳过字体子集化：收尾会较慢，某些 PDF 可能挂死。"
            "如需跳过请去掉 --no-skip-subset-fonts）")
    log(f"  输出日志：{chunk_log}")

    pages_in_chunk = end - start + 1
    seen_pages = 0
    _parse_logged.clear()          # 每片只打印一次进度诊断

    carry = {"buf": ""}
    EOF = object()

    def _reader(stream, q):
        """按块读，\r 或 \n 都切行。跨平台：优先二进制 read1。"""
        get = None
        try:
            if hasattr(stream, "buffer"):
                get = lambda: stream.buffer.read1(4096)
        except Exception:
            get = None
        if get is None:
            def get():
                return stream.read(4096)
        try:
            while True:
                try:
                    chunk = get()
                except (OSError, ValueError, TypeError):
                    break
                if not chunk:
                    break
                if isinstance(chunk, (bytes, bytearray)):
                    chunk = chunk.decode("utf-8", errors="replace")
                buf = carry["buf"] + chunk
                parts = re.split(r"[\r\n]", buf)
                carry["buf"] = parts.pop()
                for pl in parts:
                    q.put(pl)
        except Exception:
            pass
        finally:
            if carry["buf"]:
                q.put(carry["buf"])
                carry["buf"] = ""
            q.put(EOF)

    line_q = queue.Queue()
    heartbeat_every = int(os.environ.get("TBS_HEARTBEAT_EVERY", "30"))
    # 静默告警阈值：默认 180s。
    #   为什么不能再是 60s：页耗时由模型与页密度决定，常见 10–20s/页；
    #   tqdm 只在【本页翻完】时才产生新的一帧，所以
    #   「60s 无新输出」在翻译中完全正常 —— 据 60s 报 WARN 是误报。
    quiet_warn_after = int(os.environ.get("TBS_QUIET_WARN_AFTER", "180"))
    last_beat = time.time()
    last_output = time.time()
    last_progress_at = time.time()   # 上一次【页进度前进】的时间（WARN 的真正锚点）

    try:
        with open(chunk_log, "w", encoding="utf-8", errors="replace") as fh:
            fh.write(f"# cmd: {' '.join(cmd)}\n")
            fh.write(f"# started: {datetime.now().isoformat()}\n\n")
            fh.flush()
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    env=os.environ.copy(), bufsize=0,
                )
            except Exception as e:
                return False, time.time() - t0, f"无法启动 pdf2zh：{e}", 0, None, None

            rd = threading.Thread(target=_reader, args=(proc.stdout, line_q), daemon=True)
            rd.start()

            deadline = time.time() + args.timeout
            eof_seen = False
            warned_quiet = False
            phase_warned = False        # 是否已给出"卡在哪一步"的诊断
            post_warned = False         # 是否已给出"收尾疑似卡死 + 绕行"提示
            quiet_start = time.time()   # 本轮静默的起点（用于算收尾阶段时长）
            post_warn_after = int(os.environ.get("TBS_POST_WARN_AFTER", "600"))
            try:
                while True:
                    if eof_seen and line_q.empty():
                        break
                    if time.time() > deadline:
                        proc.kill()
                        tail = _read_tail(chunk_log, 1200)
                        if seen_pages >= pages_in_chunk:
                            phase = "收尾阶段（写 PDF）"
                            if args.skip_subset_fonts:
                                hint = ("\n提示：页进度已满，超时在收尾阶段。本片已启用 "
                                        "--skip-subset-fonts，说明卡点在 pdf2zh 写 PDF 本身"
                                        "（上游 pymupdf bug #3891），不是字体子集化 —— "
                                        "这类 PDF 目前无解，建议用 --pages 跳过这几页。")
                            else:
                                hint = ("\n提示：页进度已满，超时在收尾阶段（字体子集化/写 PDF）。"
                                        "去掉 --no-skip-subset-fonts 可跳过字体子集化，"
                                        "多半能解决。")
                        else:
                            phase = "翻译中"
                            hint = ("\n提示：页进度未满，超时发生在翻译中 —— 检查 ollama"
                                    "（ollama ps）与显存占用。")
                        return False, time.time() - t0, (
                            f"超时（>{args.timeout}s，卡在{phase}）已终止。"
                            f"{hint}\n最后输出：\n{tail}"
                        ), seen_pages, None, None

                    try:
                        item = line_q.get(timeout=0.5)
                    except queue.Empty:
                        now = time.time()
                        quiet = now - last_output
                        # ── 关键修正 ──────────────────────────────────────
                        # 「静默」不等于「卡住」。tqdm 用 \r 原地刷新，而且
                        # 一页翻完才有新帧：长页耗时期间队列必然空，但 pid 活着
                        # 就说明 pdf2zh 仍在推进。因此：
                        #   · 若页进度在 quiet_warn_after 内前进过 -> 只做心跳，
                        #     绝不报 WARN（这是旧版误报的根因）；
                        #   · 只有「自上次进度前进以来」超过阈值才报 WARN。
                        progress_quiet = now - last_progress_at
                        if progress_quiet < quiet_warn_after:
                            # 进度仍新鲜：允许心跳，但禁止 WARN
                            if now - last_beat >= heartbeat_every:
                                last_beat = now
                                if proc.poll() is None:
                                    log(make_heartbeat_log(now, t0, start, end, seen_pages,
                                                           pages_in_chunk, quiet, chunk_log,
                                                           progress_quiet=progress_quiet))
                            continue
                        if now - last_beat >= heartbeat_every:
                            last_beat = now
                            alive = (now - t0) / 60
                            if proc.poll() is None:
                                tail = _read_tail(chunk_log, 400).strip()
                                extra = (f"｜pdf2zh 最后输出："
                                         f"{tail.splitlines()[-1][:90]}") if tail else ""
                                log(f"  … 仍在处理 p{start}-{end}（已 {alive:.1f} 分钟，"
                                    f"页进度 {seen_pages}/{pages_in_chunk}，"
                                    f"已静默 {quiet:.0f}s）{extra}")
                                if panel is not None:
                                    try:
                                        panel.set_heartbeat(
                                            f"仍在处理（{alive:.1f} 分钟，页进度 "
                                            f"{seen_pages}/{pages_in_chunk}）")
                                    except Exception:
                                        pass
                            else:
                                log(f"  … pdf2zh 已退出，正在收尾（已 {alive:.1f} 分钟）")
                        if progress_quiet >= quiet_warn_after and not warned_quiet \
                                and proc.poll() is None:
                            warned_quiet = True
                            tail = _read_tail(chunk_log, 400).strip()
                            last_line = tail.splitlines()[-1][:120] if tail else "（无输出）"
                            log(f"  p{start}-{end} 已 {progress_quiet:.0f}s 无页进度前进"
                                f"（输出静默 {quiet:.0f}s），pdf2zh 仍在运行。", "WARN")
                            log(f"    心跳说明：进程存活，只是 tqdm 长时间没吐出新的 x/y 帧。")
                            log(f"    pdf2zh 最后一行：{last_line}")
                            if seen_pages >= pages_in_chunk:
                                log("    → 判定：页进度已满 = 翻译完成，卡在【收尾阶段】。", "WARN")
                                log("      pdf2zh 100% 之后要做：安装补丁 → 双语装配 → "
                                    "字体子集化(subset_fonts) → 写 PDF。")
                                if args.skip_subset_fonts:
                                    log("      本片已启用 --skip-subset-fonts，"
                                        "所以卡点不在 subset_fonts，而在写 PDF 本身。")
                                    log("      · 几十秒~几分钟：正常偏慢，继续等。")
                                    log("      · 超过 10 分钟不动：命中上游 pymupdf bug"
                                        "（某些 PDF 写 PDF 时永久挂起）。")
                                    log("        这种 PDF 目前无解，建议用 --pages 跳过这几页，"
                                        "或换一份 PDF。")
                                else:
                                    log("      其中最慢/最易卡死的是 subset_fonts"
                                        "（纯 CPU、全程无输出）。")
                                    log("      · 几十秒~几分钟：正常，继续等。")
                                    log("      · 超过 10 分钟不动：多半是字体子集化触发上游卡死。")
                                    log("        绕行：去掉 --no-skip-subset-fonts 重跑"
                                        "（PDF 会大一些，但能跳过这个阶段）。")
                            else:
                                log("    → 判定：页进度未满，卡在【翻译中】。", "WARN")
                                log("      请另开窗口查 ollama：ollama ps（模型是否还在、"
                                    "是否被换出）；或看显卡占用/显存是否爆（OOM 会静默重试）。")
                            phase_warned = True
                        # 收尾阶段超长：给明确的"疑似卡死"升级提示 + 绕行方案
                        if phase_warned and seen_pages >= pages_in_chunk \
                                and proc.poll() is None \
                                and (now - quiet_start) >= post_warn_after \
                                and not post_warned:
                            post_warned = True
                            mins = (now - quiet_start) / 60
                            log(f"  p{start}-{end} 收尾阶段已持续 {mins:.1f} 分钟"
                                f"（翻译早已 100%，仍无输出）。", "WARN")
                            log("    这通常不是「慢」，而是 pdf2zh 在写 PDF 阶段卡死了"
                                "（上游 pymupdf 问题）。")
                            if args.skip_subset_fonts:
                                log("    注意：本片已在跳过字体子集化的情况下仍然卡住，"
                                    "说明卡点在 write() 而非 subset_fonts。")
                                log("    这种 PDF 目前无解（上游 bug），建议 Ctrl+C 中止后"
                                    "用 --pages 跳过这几页，或换一份 PDF。")
                            else:
                                log("    建议：Ctrl+C 中止，然后去掉 --no-skip-subset-fonts "
                                    "重跑（改为跳过字体子集化）：")
                                log("      python translate_pdf2zh.py \"你的.pdf\" "
                                    "--model 你的模型")
                        continue

                    if item is EOF:
                        eof_seen = True
                        continue

                    raw_line = item
                    fh.write(raw_line + "\n")
                    fh.flush()
                    last_output = time.time()
                    last_beat = last_output
                    quiet_start = last_output      # 有输出 -> 静默计时重新开始

                    # ---- 解析 tqdm 进度 ----
                    # pdf2zh/tqdm 的行形如：  " 10%|██  | 2/20 [00:01<00:09]"
                    # 坑：不同版本的 total 语义不同 —— 有的按【本片页数】(2/20)，
                    #     有的按【整本页数 + 绝对页号】(21/152)。只看百分比或
                    #     x/y 会把整本进度当成【本片】进度，导致本片首帧不是 0
                    #     （曾出现 10/20、13/20）。因此 _parse_progress 用 start
                    #     把绝对页号锚定到本片区间，使每片都从 0 开始。
                    if panel is not None:
                        rel = _parse_progress(raw_line, pages_in_chunk,
                                              start=start,
                                              total_pages=panel.total_pages)
                        # 诊断：每片首次解析出进度的那一行原文写进日志，
                        # 便于在真实环境下核对 pdf2zh 的 tqdm 语义（本片/整本）。
                        if rel is not None and not _parse_logged.get(id(panel)):
                            _parse_logged[id(panel)] = True
                            log(f"    [进度诊断] pdf2zh 原始行：{raw_line.strip()[:120]}")
                            log(f"    [进度诊断] 解析：本片 {pages_in_chunk} 页，"
                                f"start={start}，整本={panel.total_pages} -> 已完成 {rel} 页")
                        if rel is not None and rel > seen_pages:
                            seen_pages = rel
                            last_progress_at = time.time()   # 进度前进 -> WARN 计时重开
                            warned_quiet = False             # 允许下一轮静默重新告警
                            panel.advance_page(chunk_relative=rel)
            finally:
                if proc.poll() is None:
                    proc.kill()
                try:
                    proc.wait(timeout=15)
                except Exception:
                    pass
                try:
                    proc.stdout.close()
                except Exception:
                    pass
    except Exception as e:
        return False, time.time() - t0, f"无法写子进程日志：{e}", seen_pages, None, None

    elapsed = time.time() - t0
    if proc.returncode != 0:
        tail = _read_tail(chunk_log, 1200)
        return False, elapsed, f"退出码 {proc.returncode}。最后的输出：\n{tail}", seen_pages, None, None

    # ⚠ -p 只控制翻译哪些页，输出 PDF 仍是【整本】，必须裁出本片区间
    stem = Path(pdf_path).stem
    mono = chunk_out_dir / f"{stem}-mono.pdf"
    dual = chunk_out_dir / f"{stem}-dual.pdf"
    if not mono.exists() and not dual.exists():
        return False, elapsed, (
            f"pdf2zh 退出码 0 但未找到输出文件（预期 {mono.name} / {dual.name}）。"
        ), seen_pages, None, None

    fitz = _import_fitz()
    if fitz is None:
        return False, elapsed, "未安装 PyMuPDF，无法裁剪分片", seen_pages, None, None

    mono_p = dual_p = None
    try:
        if mono.exists():
            sliced = chunk_out_dir / f"{stem}-mono-sliced.pdf"
            _extract_pages(mono, sliced, start, end, dual=False, fitz=fitz)
            mono_p = sliced if sliced.exists() else None
        if dual.exists():
            sliced_d = chunk_out_dir / f"{stem}-dual-sliced.pdf"
            _extract_pages(dual, sliced_d, start, end, dual=True, fitz=fitz)
            dual_p = sliced_d if sliced_d.exists() else None
    except Exception as e:
        # 裁剪失败就别把【整本】原样留着 —— 否则 chunks/ 里出现一个
        # 名字看起来像分片、内容却是整本的文件，极容易被误判成"分片是全本"。
        for raw in (mono, dual):
            try:
                if raw.exists():
                    raw.unlink()
            except Exception:
                pass
        return False, elapsed, f"裁剪分片页区间失败：{e}", seen_pages, None, None

    # 裁完后立刻删掉 pdf2zh 的【整本】中间文件，只留切片。
    # 否则 chunks/pX-Y/ 里同时躺着「整本」和「切片」两份文件，
    # 极易被误认为"分片输出的是全本"，而且 N 片 × 整本很占磁盘。
    for raw in (mono, dual):
        try:
            if raw.exists():
                raw.unlink()
        except Exception as e:
            log(f"  （整本中间文件删除失败，可忽略：{raw.name} {e}）", "WARN")

    if mono_p is None and dual_p is None:
        return False, elapsed, "裁剪后无产物（页区间可能超出文档）。", seen_pages, None, None
    return True, elapsed, "", pages_in_chunk, mono_p, dual_p


def merge_chunks(mono_parts, dual_parts, order, out_dir, src_stem, args):
    """把各分片 PDF 按页序合并成完整文档；成功后清理分片目录。"""
    fitz = _import_fitz()
    if fitz is None:
        log("未安装 PyMuPDF，无法合并", "ERROR")
        return []

    n_chunks = len(order)

    def _merge(parts, suffix, label):
        missing = [i for i in range(1, n_chunks + 1) if i not in parts]
        if missing:
            log(f"{label}：缺少分片 {missing}，跳过合并。", "WARN")
            return None
        out_path = out_dir / f"{src_stem}-merged{suffix}.pdf"
        try:
            dst = fitz.open()
            for i in range(1, n_chunks + 1):
                src = fitz.open(str(parts[i]))
                dst.insert_pdf(src)
                src.close()
            n_pages = dst.page_count
            # garbage=4 + clean：这是合并成品，最关键。insert_pdf 把每片的字体/资源
            # /ICC 对象全部带进成品，garbage=3 不清重复/未引用对象，garbage=4 才做
            # 最大清理，clean=True 另重写内容流。实测 8 片合并：g3=21381 字节/127
            # 对象；g4+clean=8694 字节/51 对象，体积 -59.3%（见 CONTRACT-2.md §2.2）。
            # 个别畸形 PDF clean=True 会报错，故保存失败时回退不带 clean 重试（B11）。
            try:
                dst.save(str(out_path), garbage=4, deflate=True, clean=True)
            except Exception:
                dst.save(str(out_path), garbage=4, deflate=True)
            dst.close()
            log(f"  ✓ {label}：{n_chunks} 片 -> {n_pages} 页  {out_path}")
            return out_path
        except Exception as e:
            log(f"{label}：合并失败 {e}", "ERROR")
            return None

    merged = []
    m = _merge(mono_parts, "-mono", "纯中文版")
    if m:
        merged.append(m)
    d = _merge(dual_parts, "-dual", "双语对照版")
    if d:
        merged.append(d)

    if merged and not args.keep_chunks:
        chunks_root = out_dir / CHUNKS_DIRNAME
        try:
            shutil.rmtree(chunks_root)
            log(f"  已删除分片目录：{chunks_root}")
        except Exception as e:
            log(f"  分片目录删除失败（可手动删）：{e}", "WARN")
    return merged


def _page_tag(eff0):
    """把 clamp 后的区间对列表 [(s,e),...] 拼成文件名片段。

    [(5,10)]            -> "p5-p10"
    [(1,5),(20,30)]     -> "p1-p5-p20-p30"
    []（无 --pages 整本）-> ""
    """
    if not eff0:
        return ""
    return "-".join(f"p{s}-p{e}" for s, e in eff0)


def stage_single_chunk(mono_parts, dual_parts, eff0, out_dir, src_stem, args):
    """单片场景：不合并，直接把该片的 mono/dual 产物拷到 out_dir 根目录。

    文件名带页范围做前缀（无 --pages 时无 p 段）：
      <src_stem>-<page_tag>-mono-sliced.pdf / -dual-sliced.pdf
    拷贝成功后清理 chunks/（除非 keep_chunks）。拷贝失败则报错且保留 chunks。
    """
    page_tag = _page_tag(eff0)
    tag = f"-{page_tag}" if page_tag else ""

    def _copy(part, suffix, label):
        out_path = out_dir / f"{src_stem}{tag}{suffix}-sliced.pdf"
        try:
            shutil.copy2(str(part), str(out_path))
            log(f"  ✓ {label}：单片产物，已拷出 {out_path}")
            return out_path
        except Exception as e:
            log(f"{label}：单片产物拷贝失败 {e}", "ERROR")
            return None

    out_paths = []
    m = _copy(mono_parts[1], "-mono", "纯中文版") if 1 in mono_parts else None
    if m:
        out_paths.append(m)
    d = _copy(dual_parts[1], "-dual", "双语对照版") if 1 in dual_parts else None
    if d:
        out_paths.append(d)

    if out_paths and not args.keep_chunks:
        chunks_root = out_dir / CHUNKS_DIRNAME
        try:
            shutil.rmtree(chunks_root)
            log(f"  已删除分片目录：{chunks_root}")
        except Exception as e:
            log(f"  分片目录删除失败（可手动删）：{e}", "WARN")
    return out_paths




# ============================== 面板常量 ==============================
# 深色面板视觉规格（来自作者参考稿，冻结）。
BG = "#080D13"
PANEL_BG = "#0B121B"
WAIT_CARD_BG = "#0C141D"
BORDER = "#18364D"
BLUE = "#20B8FF"
BLUE_LIGHT = "#A9DFFF"
TEXT = "#D7E9F8"
MUTED = "#819BB2"
GREEN = "#00D994"
YELLOW = "#FFC857"
RED = "#FF647C"

_STAGE_FLOW = ["前置处理", "分片文件", "翻译内容", "合并内容", "输出 PDF"]

SECTION_TITLES = {
    "file": ("▤", "PDF 文件信息"),
    "ollama": ("♟", "Ollama 运行状态"),
    "stages": ("▰", "处理阶段"),
    "overall": ("◉", "总体进度"),
    "log": ("▤", "执行日志"),
}

LEVEL_STYLE = {
    "INFO": f"bold {GREEN}",
    "DEBUG": f"bold {BLUE}",
    "WARNING": f"bold {YELLOW}",
    "WARN": f"bold {YELLOW}",
    "OK": f"bold {GREEN}",
    "STEP": f"bold {BLUE_LIGHT}",
    "ERROR": f"bold {RED}",
}

# ============================== 布局固定区高度常量 ==============================
# DEFECT 6 修复：把各固定区高度提成模块级常量，render() 与
# _zone_log_visible_height() 共用同一组常量计算，账目不再脱节。
# 只有【内容不折行】的区用静态常量；top（顶栏）与 stages（阶段卡）随终端
# 宽度折行，高度由 _zone_fixed_heights() 动态实测（贴合内容，见 DEFECT 8）。
_H_HEADER = 3      # 标题条：单行标题 + 上下边框，固定
_H_FOOTER = 3      # 页脚条：单行提示 + 上下边框，固定
_H_PROGRESS = 3    # 总体进度：1 行进度条 + 上下边框，固定（贴合内容）
_MIN_LOG_LINES = 3   # 日志区最少可见 3 行内容（缺陷 10：小终端也不得让日志消失）
_LOG_BORDERS = 2     # 日志 Panel 上下边框共 2 行，随日志区一起占用屏幕高度
_TOP_MIN = 3         # 顶栏两面板的压缩下限（标题行 + 1 字段行 + 上下边框）
_STAGES_MIN = 3      # 阶段区压缩下限（标题行 + 卡片一整行 + 上下边框）


def _render_height(renderable, width=None):
    """实测一个 renderable 的最小内容高度（不加高度约束，让它收缩到内容）。

    返回渲染后的输出行数。用于顶栏/阶段区这类随宽度折行的内容自适应区。
    """
    from rich.console import Console as _Console
    import io
    c = _Console(force_terminal=True, width=width or 120, height=200, record=True,
                 file=io.StringIO())
    c.print(renderable)
    return len(c.export_text().rstrip("\n").splitlines())


def _fmt_num(n):
    if n is None:
        return "—"
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


# ============================== 深色监控面板（DarkDashboard）==============================
# 视觉规格来自作者参考稿 reference_dark_dashboard.py（保留视觉，删掉硬编码假数据）。
#   背景 #080D13 / 面板 #0B121B / 边框 #18364D / 主色 #20B8FF / 浅蓝 #A9DFFF
#   正文 #D7E9F8 / 次要 #819BB2 / 绿 #00D994 / 黄 #FFC857 / 红 #FF647C
# 布局六行：header(3) / top(16) / stages(9) / progress(4) / logs(剩余,最少8) / footer(3)。
# 阶段卡片带序号方块(1-5) + ➜ 箭头；状态：已完成(绿)/进行中(蓝)/等待中(灰)。
# GPU 显存：只显占用值（_fmt_bytes(size_vram)），不显总量、不画带分母进度条。
# ======================================================================


def _section_title(icon, title):
    """分区标题：图标 + 空格 + 文字，深蓝主色。"""
    result = Text()
    result.append(f"{icon}  ", style=f"bold {BLUE_LIGHT}")
    result.append(title, style=f"bold {BLUE}")
    return result


def _fmt_dur(secs):
    try:
        s = int(secs)
    except Exception:
        return "—"
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class DarkDashboard:
    """深色分区式监控面板（冻结契约替换旧 RichDashboard）。

    enabled=False 时所有方法退化为安全空操作，保证 --plain / 非 TTY 可跑且不 raise。
    """

    LOG_KEEP = 100               # 日志区上限（参考稿 LOG_LIMIT=100）

    def __init__(self, pdf_path, args, console=None, enabled=True):
        self.enabled = bool(enabled)
        self.args = args
        self.pdf_path = Path(pdf_path)
        self.console = console or Console()

        self.stage = 0
        self.finished = False      # 任务真正结束标志（CONTRACT-3：方案 A，rc==0 才置 True）
        self.t0 = time.time()

        # 前置信息
        self.pdf_info = {}
        self.preproc_state = "pending"     # pending|running|ok|fallback|skipped
        self.preproc_note = ""
        self.ollama = {}
        self.pdf_probing = False
        self.ollama_probing = False

        # 分段进度
        self.total_pages = 0
        self.scoped_total = 0
        self.per_chunk = getattr(args, "pages_per_chunk", DEFAULT_PAGES_PER_CHUNK)
        self.n_chunks = 0
        self.chunks = []
        self.chunk_states = {}
        self.cur_idx = 0
        self.cur_start = self.cur_end = 0
        self.cur_step = 0                  # 0 调 pdf2zh / 1 裁剪 / 2 记清单 / 3 完成
        self.cur_pages_done = 0
        self.cur_pages_total = 0
        self.cur_chunk_t0 = None
        self.cur_heartbeat = ""            # 最近一次心跳提示（片内静默期显示）

        # 总体进度
        self.done_chunks = 0
        self.done_pages = 0
        self.merged_ok = False
        self.merged_single = False
        self.merged_skipped = False
        self.scope_label = ""

        # 日志
        self._logs = []
        self._live = None
        self.fatal = False
        self._hold_footer = False   # hold_and_wait 置 True 后 footer 显示「按 Enter 关闭」

        # 缺陷 10：布局压缩级别（0 自然 / 1 紧凑 / 2 最小），由 _fixed_zone_heights()
        # 按屏幕高度预算决定；_zone_top / _zone_stages 据此渲染，保证账目与实测一致。
        self._top_level = 0
        self._stage_level = 0

    # ---------------- 生命周期 ----------------
    def start(self):
        if not self.enabled:
            return
        try:
            self.console.clear()
        except Exception:
            pass
        self._live = Live(
            self.render(), console=self.console,
            screen=True,                 # alternate screen = 真·全屏
            auto_refresh=False,
            refresh_per_second=4,
            transient=False,
        )
        self._live.start()

    def stop(self):
        if not self.enabled or self._live is None:
            return
        # 缺陷 14：把「刷新最后一帧」与「退出 Live」拆成两个独立 try。
        # 若 render() 抛异常，原先会连带跳过 self._live.stop() —— 备用屏
        # (alternate screen) 就不会退出，终端可能停在黑屏/残影上，而 _live
        # 又被置 None，后续 refresh/stop 全空操作、无法补救。退出必须无论如何都执行。
        try:
            self._live.update(self.render(), refresh=True)
        except Exception:
            pass
        try:
            self._live.stop()
        except Exception:
            pass
        self._live = None

    def refresh(self, force=False):
        if not self.enabled or self._live is None:
            return
        try:
            self._live.update(self.render(), refresh=True)
        except Exception:
            pass

    def draw(self, first=False):
        self.refresh(force=first)

    def close(self):
        self.stop()

    def hold_and_wait(self, rc, reason=""):
        """结束后停留在终端，等用户按 Enter 再退出（CONTRACT-2.md §1）。

        只在 panel 启用（enabled=True，即 TTY + 非 --plain）时起效；enabled=False
        时直接返回，既不阻塞也不调用 input()，保证管道/重定向/无人值守不挂死（B1）。

        行为：
          1) 按退出码在日志区追加一行提示（rc==0 正常 / rc==130 中断 / 其他失败）；
          2) footer 显示「按 Enter 关闭」，渲染最终画面；
          3) input() 阻塞等回车；EOFError/KeyboardInterrupt/任何异常都捕获后直接
             返回，绝不卡死（B3/B4）。
        """
        if not self.enabled:
            return
        if rc == 0:
            # CONTRACT-3：rc==0 成功才置 finished=True，且必须在 refresh(force=True)
            # 之前置位，否则最终画面刷不出绿色的「已完成」。
            self.finished = True
            msg = "已完成，可安全关闭窗口"
        elif rc == 130:
            msg = "已中断（可重跑续译），可安全关闭窗口"
        else:
            msg = f"任务未正常结束（退出码 {rc}），可安全关闭窗口"
        if reason:
            msg = f"{msg}（{reason}）"
        # 追加到日志区（复用 log_line，走面板缓冲 + refresh）
        self.log_line(f"[{datetime.now().strftime('%H:%M:%S')}] [STEP] {msg}", "STEP")
        # footer 显示「按 Enter 关闭」，渲染最终画面
        self._hold_footer = True
        drew_panel = False
        try:
            drew_panel = self._live is not None
            self.refresh(force=True)
        except Exception:
            pass
        # 缺陷 13：若没有 Live（未 start / 已被 stop），refresh 是空操作，
        # 屏幕上一片空白却要阻塞等回车 —— 用户面对全黑终端不知道该按什么。
        # 此时显式打印一行可见提示（而非默默空白等待）。
        if not drew_panel:
            try:
                self.console.print(msg)
                self.console.print("按 Enter 关闭 > ", end="")
            except Exception:
                pass
        # 用无参 input()（不输出 prompt）：footer 里已经写了「按 Enter 关闭」，
        # 若用 input("...") 传 prompt，该裸字符串会被直接写到终端，顶乱
        # alternate screen 上已经画好的面板布局（缺陷 12）。无参 input() 只阻塞
        # 等回车，不写任何字节；等待期间 Live 保持运行（auto_refresh=False，
        # 画面静态停在屏幕上），stop() 由 main() 的 finally 在 input() 返回之后
        # 才调用，保证按 Enter 之前画面一直接在 alt screen 上可见。
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        except Exception:
            pass

    def suspend(self):
        """临时让出屏幕（交互输入用）：退出 alternate screen、显示光标、清屏。"""
        if not self.enabled:
            return
        try:
            if self._live is not None:
                self._live.stop()
                self._live = None
        except Exception:
            pass
        try:
            self.console.show_cursor(True)
            self.console.clear()
        except Exception:
            pass

    def resume(self):
        """交互结束后清屏并重新接管屏幕。"""
        if not self.enabled:
            return
        try:
            self.console.clear()
        except Exception:
            pass
        self.start()

    # ---------------- 状态更新 ----------------
    def set_stage(self, s):
        # 单调递增：只前进，不回退
        self.stage = max(self.stage, int(s))
        self.refresh()

    def set_pdf_info(self, info):
        self.pdf_info = dict(info or {})
        self.pdf_probing = False
        self.refresh()

    def set_ollama(self, st):
        self.ollama = dict(st or {})
        self.ollama_probing = False
        self.refresh()

    def set_preproc(self, state, note=""):
        self.preproc_state = state
        self.preproc_note = note or ""
        self.refresh()

    def set_pdf_probing(self, flag=True):
        self.pdf_probing = bool(flag)
        self.refresh()

    def set_ollama_probing(self, flag=True):
        self.ollama_probing = bool(flag)
        self.refresh()

    def start_chunk(self, idx, start, end):
        self.cur_idx = idx
        self.cur_start, self.cur_end = start, end
        self.cur_step = 0
        self.cur_pages_done = 0
        self.cur_pages_total = end - start + 1
        self.cur_chunk_t0 = time.time()
        self.cur_heartbeat = ""
        self.chunk_states[idx] = "running"

    def advance_page(self, chunk_relative=None):
        if chunk_relative is not None:
            self.cur_pages_done = max(self.cur_pages_done,
                                      min(int(chunk_relative), self.cur_pages_total))
        if self.cur_pages_done > 0 and self.cur_step < 1:
            self.cur_step = 1
        self.refresh()

    def set_heartbeat(self, text):
        self.cur_heartbeat = text or ""
        self.refresh()

    def finish_chunk(self, idx, pages, state="done"):
        self.chunk_states[idx] = state
        self.done_chunks += 1
        if state in ("done", "skipped"):
            self.done_pages += pages
        self.cur_pages_done = 0
        self.cur_pages_total = 0
        self.cur_chunk_t0 = None
        self.cur_heartbeat = ""
        self.refresh()

    def log_line(self, text, level="INFO"):
        """追加一条日志。级别以【调用方传入的 level 为准】；正文里的 [XX] 仅当
        level 缺省 / 为 INFO 时才回退采用。LOG_KEEP 上限，超出丢最旧。"""
        stamp = datetime.now().strftime("%H:%M:%S")
        body = text
        m = re.match(r"^\[(\d{2}:\d{2}:\d{2})\]\s*\[([A-Z]+)\]\s*(.*)$", text, re.S)
        if m:
            stamp, body = m.group(1), m.group(3)
            if not level or level == "INFO":
                # 调用方没给明确级别时才退回正文里的级别
                level = m.group(2)
        self._logs.append((stamp, level, body))
        if len(self._logs) > self.LOG_KEEP:
            self._logs = self._logs[-self.LOG_KEEP:]
        if not self.enabled:
            # 非面板模式：日志已在 log() 里 print 过，这里只留缓冲
            return
        self.refresh()

    # ---------------- 小工具 ----------------
    @staticmethod
    def _kv(label, value, label_style=MUTED, value_style=TEXT):
        t = Text()
        t.append(f"{label:<8}", style=label_style)
        if isinstance(value, Text):
            t.append_text(value)
        else:
            t.append(str(value), style=value_style)
        return t

    # ---------------- 区域一：顶栏（PDF 文件信息 ‖ Ollama 运行状态）----------------
    def _zone_file_info(self, level=None, bottom_pad=0):
        lvl = self._top_level if level is None else level
        d = self.pdf_info or {}
        ov = "ellipsis" if lvl > 0 else "fold"
        details = Table.grid(expand=True, padding=(0, 1))
        details.add_column(width=17, style=MUTED, no_wrap=True)
        details.add_column(style=TEXT, ratio=1, overflow=ov, no_wrap=(lvl > 0))

        name = d.get("name") or self.pdf_path.name
        size = d.get("size_mb")
        size_txt = (f"{size:.1f} MB" if size is not None else
                    (f"{self.pdf_path.stat().st_size / 1048576:.1f} MB"
                     if self.pdf_path.exists() else "—"))
        pages = d.get("pages")
        pages_txt = (f"{_fmt_num(pages)} 页" if pages else
                     ("统计中…" if self.pdf_probing else "—"))
        chars = d.get("chars")
        chars_txt = (f"{_fmt_num(chars)} 字" if chars is not None else
                     ("全文统计中…" if self.pdf_probing else "—"))

        if d.get("text_pdf") is True:
            type_txt = f"文字版 PDF  ✓ {d.get('text_pdf_label', '')}".strip()
            type_style = GREEN
        elif d.get("text_pdf") is False:
            type_txt = f"扫描版 PDF（需 OCR） {d.get('text_pdf_label', '')}".strip()
            type_style = YELLOW
        else:
            type_txt = str(d.get("text_pdf_label") or
                           ("判定中…" if self.pdf_probing else "未知"))
            type_style = YELLOW

        ps = self.preproc_state
        if ps == "running":
            preproc_txt, preproc_style = "清洗中（修复非法 dict 键）…", YELLOW
        elif ps == "fallback":
            note = (self.preproc_note or "").strip()
            panel_note = note[:28] + ("…" if len(note) > 28 else "")
            preproc_txt, preproc_style = f"● 清洗失败，改用原 PDF {panel_note}".strip(), YELLOW
        elif ps == "skipped":
            note = (self.preproc_note or "").strip()
            panel_note = note[:28] + ("…" if len(note) > 28 else "")
            preproc_txt, preproc_style = f"● 已跳过 {panel_note}".strip(), MUTED
        elif ps == "ok":
            # DEFECT 4 修复：面板只放短文案（截到 28 字符），全量清洗参数进日志
            note = (self.preproc_note or "").strip()
            panel_note = note[:28] + ("…" if len(note) > 28 else "")
            preproc_txt, preproc_style = f"● 已清洗 {panel_note}".strip(), GREEN
        else:
            preproc_txt, preproc_style = "等待中", YELLOW

        # 缺陷 10 级别 2：极小终端每个面板只保留最核心的 1 个字段（文件名 /
        # 服务连接），使面板压缩到 3 行（标题行 + 1 字段 + 边框），不裁边框。
        if lvl >= 2:
            details.add_row("文件名", Text(name, style=f"bold {TEXT}", overflow=ov))
        else:
            details.add_row("文件名", Text(name, style=f"bold {TEXT}", overflow=ov))
            details.add_row("文件大小", Text(size_txt, overflow=ov))
            details.add_row("文件页数", Text(pages_txt, overflow=ov))
            details.add_row("文件字数", Text(chars_txt, overflow=ov))
            details.add_row("文件类型", Text(type_txt, style=type_style, overflow=ov))
            details.add_row("前置处理", Text(preproc_txt, style=preproc_style, overflow=ov))

        return RichPanel(
            details,
            title=_section_title("▤", "PDF 文件信息"),
            border_style=BORDER,
            box=box.ROUNDED,
            style=PANEL_BG,
            padding=((0 if lvl >= 1 else 1), 1 if lvl >= 1 else 2,
                     (0 if lvl >= 1 else 1) + bottom_pad, 1 if lvl >= 1 else 2),
            expand=True,
        )

    def _zone_ollama(self, level=None, bottom_pad=0):
        lvl = self._top_level if level is None else level
        o = self.ollama or {}
        ov = "ellipsis" if lvl > 0 else "fold"
        pad = ((0 if lvl >= 1 else 1), 1 if lvl >= 1 else 2,
               (0 if lvl >= 1 else 1) + bottom_pad, 1 if lvl >= 1 else 2)
        details = Table.grid(expand=True, padding=(0, 1))
        details.add_column(width=17, style=MUTED, no_wrap=True)
        details.add_column(style=TEXT, ratio=1, overflow=ov, no_wrap=(lvl > 0))

        if o.get("ok"):
            conn_txt, conn_style = "● 已连接", GREEN
        else:
            conn_txt, conn_style = (
                f"✗ 未连接 {str(o.get('err', ''))[:36]}".strip(), RED)

        port = o.get("port")
        addr_txt = f"{o.get('h', '—')}:{port}" if port else str(o.get("host", "—"))

        model = getattr(self.args, "model", None)
        if model:
            state = o.get("model_state", "未知")
            ready = bool(o.get("model_ready"))
            model_style = GREEN if ready else (YELLOW if o.get("ok") else RED)
            model_txt = f"{model} [{state}]"
        else:
            model_style = YELLOW
            model_txt = "（未指定，运行时交互选择）"

        if o.get("running"):
            vram = o.get("size_vram")
            v = Text()
            v.append(_fmt_bytes(vram), style=f"bold {GREEN}")
            v.append(" ●", style=GREEN)
            vram_txt = v
            extra_label, extra_txt = "已加载", ", ".join(o["running"])[:44]
        else:
            vram_txt = Text(
                "模型未加载（首次调用时进入显存）" if o.get("ok") else "—",
                style=MUTED)
            extra_label, extra_txt = "已装模型", f"{o.get('n_models', 0)} 个"

        if not o:
            conn_txt, conn_style = Text("探测中…", style=YELLOW), MUTED
            addr_txt, model_txt = "—", "—"
            vram_txt, extra_label, extra_txt = Text("—"), "已装模型", "—"

        # 缺陷 10 级别 2：极小终端只保留最核心的 1 个字段（连接状态 / 使用模型中
        # 取服务连接），使面板压缩到 3 行，不裁边框。
        if lvl >= 2:
            details.add_row("服务连接", Text(conn_txt, style=conn_style, overflow=ov) if isinstance(conn_txt, str) else conn_txt)
        else:
            if o:
                details.add_row("服务连接", Text(conn_txt, style=conn_style, overflow=ov))
                details.add_row("服务地址", Text(addr_txt, overflow=ov))
                details.add_row("使用模型", Text(model_txt, style=model_style, overflow=ov))
                details.add_row("显存占用", vram_txt)
                details.add_row(extra_label, Text(extra_txt, overflow=ov))
            else:
                details.add_row("服务连接", Text("探测中…", style=YELLOW))
                details.add_row("服务地址", "—")
                details.add_row("使用模型", "—")
                details.add_row("显存占用", "—")

        return RichPanel(
            details,
            title=_section_title("♟", "Ollama 运行状态"),
            border_style=BORDER,
            box=box.ROUNDED,
            style=PANEL_BG,
            padding=pad,
            expand=True,
        )

    def _zone_top(self):
        # DEFECT 7 修复：顶栏用 Table.grid(padding=(0,1)) 两列 ratio=1（同参考稿
        # make_top_row），两面板之间保留 1 列间隙，且顶边（╭）同处一行。
        # DEFECT 9 修复：两个面板内容行数不同导致底边差 1~2 行。这里做「探针渲染」——
        # 先渲染一次未加垫的 grid，按列位置（左列 ╰ 在第 0 列、右列 ╰ 在 >0 列）
        # 定位两面板各自的底边行号，算出真实行差；再把这个差值作为【面板内底部
        # padding】加到较矮一方的 Panel 内（border 内部），而不是用顶部 Padding
        # 把整块挪下去——这样顶边（╭）仍与另一面板齐平（缺陷 7），底边（╰）也
        # 与另一面板对齐（缺陷 9）。
        width = getattr(self.console, "width", None) or 120

        def _bottoms(l, r):
            import io
            row = Table.grid(expand=True, padding=(0, 1))
            row.add_column(ratio=1)
            row.add_column(ratio=1)
            row.add_row(l, r)
            c = Console(force_terminal=True, width=width, height=200,
                        record=True, file=io.StringIO())
            c.print(row)
            lines = c.export_text().splitlines()
            # 左面板底边 ╰ 在第 0 列；右面板底边 ╰ 在 >0 列。两面板等高时，同一行
            # 会出现两个 ╰（左在第 0 列、右在 >0 列），需逐个定位而非只取第一个。
            left_b = right_b = 0
            for i, ln in enumerate(lines):
                cnt = ln.count("╰")
                if cnt == 0:
                    continue
                first = ln.index("╰")
                if first == 0:
                    left_b = i
                if cnt >= 2:
                    right_b = i          # 同一行第二个 ╰ = 右面板底边
                elif first > 0:
                    right_b = i          # 右面板底边在另一行
            return left_b, right_b

        lb, rb = _bottoms(self._zone_file_info(), self._zone_ollama())
        left = self._zone_file_info(bottom_pad=max(0, rb - lb))
        right = self._zone_ollama(bottom_pad=max(0, lb - rb))

        row = Table.grid(expand=True, padding=(0, 1))
        row.add_column(ratio=1)
        row.add_column(ratio=1)
        row.add_row(left, right)
        return row

    def _screen_height(self):
        try:
            h = self.console.size.height
        except Exception:
            h = 50
        return h if h else 50

    def _fixed_zone_heights(self):
        """返回各固定区实际高度 (header, top, stages, progress, footer)。

        DEFECT 6 / 8：header/progress/footer 用模块常量；top（顶栏）/stages
        （阶段卡）按当前 console 宽度实测贴合内容。
        DEFECT 10：再做【总量约束】——若「固定区之和 + 日志最小值(3 行内容 + 2
        边框)」超过屏幕高，按优先级压缩：top（字段省略号截断/精简）→ stages
        （卡片压 padding / 压单行），header/progress/footer 保持 3 行不动。
        目标是任何尺寸下 sum(固定区) + 日志可见行 ≤ 屏幕高。压缩级别存进
        self._top_level / self._stage_level，render() 与 _zone_log_visible_height()
        共用同一来源，保证账目与实测一致（不像上轮只在大终端成立）。
        """
        width = getattr(self.console, "width", None) or 120
        h = self._screen_height()
        header = _H_HEADER
        progress = _H_PROGRESS
        footer = _H_FOOTER
        # 日志区最少占 3 行内容 + 2 行 Panel 边框
        min_log_total = _MIN_LOG_LINES + _LOG_BORDERS
        budget = h - header - progress - footer - min_log_total

        def measure():
            return (_render_height(self._zone_top(), width),
                    _render_height(self._zone_stages(), width))

        # 先试自然布局（级别 0）
        self._top_level = 0
        self._stage_level = 0
        top, stages = measure()
        if top + stages <= budget:
            return (header, top, stages, progress, footer)

        # 级别 1：顶栏字段省略号截断 + 卡片压 padding
        self._top_level = 1
        self._stage_level = 1
        top, stages = measure()
        if top + stages <= budget:
            return (header, top, stages, progress, footer)

        # 级别 2：顶栏精简到核心字段 + 阶段卡压成单行
        self._top_level = 2
        self._stage_level = 2
        top, stages = measure()
        # 即便到级别 2 仍装不下（极小终端），强制夹到下限，宁可从
        # top/stages 里裁，也不吞掉总体进度与日志两个必需区。
        top = max(_TOP_MIN, min(top, budget - _STAGES_MIN))
        stages = max(_STAGES_MIN, min(stages, budget - top))
        return (header, top, stages, progress, footer)

    # ---------------- 区域二：处理阶段（五张序号卡片 + ➜）----------------
    def _zone_stages(self):
        names = _STAGE_FLOW
        lvl = self._stage_level

        # 缺陷 10 级别 2：极小终端把五张卡片压成一行纯文本（序号 + 首字），
        # 去掉卡片边框，使阶段区天然收敛到 3 行（标题行 + 卡片整行 + 边框），
        # 满足「阶段区至少能显示卡片一整行」，且不再裁边框。
        if lvl >= 2:
            line = Text()
            for i, name in enumerate(names):
                idx = i + 1
                if self.finished or self.stage > idx:
                    num_style = f"bold {BG} on {GREEN}"
                elif self.stage == idx:
                    num_style = f"bold {BG} on {BLUE}"
                else:
                    num_style = f"bold #06111B on #8BA8C4"
                line.append(f" {idx} ", style=num_style)
                line.append(name[:1] + ("…" if len(name) > 1 else ""),
                            style=f"bold {TEXT}")
                if i < len(names) - 1:
                    line.append(" ➜ ", style=BLUE_LIGHT)
            return RichPanel(
                line,
                title=_section_title("▰", "处理阶段"),
                border_style=BORDER,
                box=box.ROUNDED,
                style=BG,
                padding=(0, 0),
            )

        # 缺陷 10：级别 1 收窄卡片 padding 并截短卡片文本。
        card_pad = (0, 0) if lvl >= 1 else (0, 1)
        flow = Table.grid(expand=True, padding=(0, 0))
        for i in range(len(names)):
            flow.add_column(ratio=5)
            if i < len(names) - 1:
                flow.add_column(ratio=1, width=3)

        cells = []
        for i, name in enumerate(names):
            idx = i + 1
            if self.finished or self.stage > idx:
                number_style = f"bold {BG} on {GREEN}"
                border = GREEN
                state = f"[{GREEN}]✓ 已完成[/{GREEN}]"
                card_style = "#06251F"
            elif self.stage == idx:
                number_style = f"bold {BG} on {BLUE}"
                border = BLUE
                if name == "翻译内容":
                    # DEFECT 3 修复：进行中态恢复片数（契约授权，非自行变更需求）
                    state = f"[{BLUE}]进行中 · {max(0, self.done_chunks)}/{self.n_chunks} 片[/{BLUE}]"
                else:
                    state = f"[{BLUE}]进行中[/{BLUE}]"
                card_style = "#071B2A"
            else:
                number_style = f"bold #06111B on #8BA8C4"
                border = "#334A60"
                state = f"[{MUTED}]等待中[/{MUTED}]"
                card_style = WAIT_CARD_BG

            # 截短名称，随压缩级别逐步收紧
            if lvl == 0:
                disp_name = name
                disp_state = Text.from_markup(state)
            else:  # lvl == 1
                disp_name = name[:2] + ("…" if len(name) > 2 else "")
                disp_state = Text.from_markup(state)

            body = Table.grid(expand=True, padding=(0, 1) if lvl == 0 else (0, 0))
            body.add_column(width=4, justify="center")
            body.add_column(ratio=1)
            body.add_row(
                Text(f" {idx} ", style=number_style, justify="center"),
                Group(
                    Text(disp_name, style=f"bold {TEXT}"),
                    disp_state,
                ),
            )
            cells.append(RichPanel(
                body,
                border_style=border,
                box=box.ROUNDED,
                style=card_style,
                padding=card_pad,
                expand=True,
            ))

        items = []
        for i, cell in enumerate(cells):
            items.append(cell)
            if i < len(cells) - 1:
                items.append(Align.center(Text("➜", style=BLUE_LIGHT)))
        flow.add_row(*items)

        return RichPanel(
            flow,
            title=_section_title("▰", "处理阶段"),
            border_style=BORDER,
            box=box.ROUNDED,
            style=BG,
            padding=(0, 0) if lvl >= 1 else (0, 1),
        )

    # ---------------- 区域三：总体进度 ----------------
    def _zone_overall(self):
        n_chunks = self.n_chunks or 0
        done = self.done_chunks
        if self.stage >= 5 and self.merged_ok:
            done = max(done, n_chunks)

        progress = Progress(
            BarColumn(
                bar_width=None,
                complete_style=BLUE,
                finished_style=GREEN,
                style="#1B2A39",
            ),
            TextColumn(f"[bold {BLUE_LIGHT}]{{task.percentage:>3.0f}}%"),
            TextColumn(f"[{MUTED}]({{task.completed:.0f}} / {{task.total:.0f}} 片)"),
            expand=True,
        )
        progress.add_task("总体进度", total=max(1, n_chunks), completed=done)

        return RichPanel(
            progress,
            title=_section_title("◉", "总体进度"),
            border_style=BORDER,
            box=box.ROUNDED,
            style=BG,
            padding=(0, 1),
        )

    # ---------------- 区域四：执行日志 ----------------
    def _zone_log_visible_height(self):
        """按 console 高度推算日志区可容纳的可见【内容】行数（不含 Panel 上下边框）。

        rich 的 Layout 对超出 minimum_size 的子区从上往下裁、截掉尾部——所以
        显示层必须自己截「尾部」（最新日志）。visible = 屏幕高 - 2（日志面板
        上下边框）- 各固定区高度（DEFECT 6：header/footer/progress 用模块常量，
        top/stages 实测贴合内容）。与 render() 的 Layout size 共用同一来源
        _fixed_zone_heights()。DEFECT 10：_fixed_zone_heights() 已做总量约束，
        保证 visible ≥ _MIN_LOG_LINES（任何尺寸日志区都不消失）。
        """
        h = self._screen_height()
        header, top, stages, progress, footer = self._fixed_zone_heights()
        fixed = header + top + stages + progress + footer
        visible = h - fixed - _LOG_BORDERS      # 减 2：日志 Panel 上下边框
        return max(_MIN_LOG_LINES, visible)

    def _zone_log(self):
        table = Table(
            box=None,
            show_header=False,
            expand=True,
            padding=(0, 0),
            pad_edge=False,
        )
        table.add_column(width=10, style=MUTED, no_wrap=True)
        table.add_column(width=9, no_wrap=True)
        table.add_column(ratio=1, style=TEXT, overflow="fold")

        max_lines = self._zone_log_visible_height()
        # DEFECT 6：提示行（截断时才出现）占 1 行，从可见行数里扣掉，保证
        # 「提示行 + 日志行」之和不超过日志区实际高度，账目自洽。
        shown = self._logs[-max_lines:]
        skipped = len(self._logs) - len(shown)
        if skipped > 0 and max_lines > 1:
            shown = shown[-(max_lines - 1):]
            skipped = len(self._logs) - len(shown)

        for stamp, level, body in shown:
            table.add_row(
                Text(f"[{stamp}]", style=MUTED),
                Text.from_markup(f"[{LEVEL_STYLE.get(level, TEXT)}]{level}[/]"),
                Text(body, style=TEXT, overflow="fold"),
            )

        if skipped > 0:
            # 被裁掉的最旧日志给一句提示（沿用旧版「显示最新 M 条」语义）
            note = Text(
                f"… 共 {len(self._logs)} 条，显示最新 {len(shown)} 条",
                style=MUTED,
            )
            content = Group(note, table)
        else:
            content = table

        sub = f"[{MUTED}]最近 {len(self._logs)} 条记录[/]"
        if skipped > 0:
            sub += f"[{MUTED}]（显示最新 {len(shown)} 条）[/]"

        return RichPanel(
            content,
            title=_section_title("▤", "执行日志"),
            subtitle=sub,
            border_style=BORDER,
            box=box.ROUNDED,
            style=BG,
            padding=(0, 1),
        )

    # ---------------- 组装 ----------------
    def render(self):
        # DEFECT 6 / 8 / 10：固定区高度统一取自 _fixed_zone_heights()（含总量
        # 约束），顶栏/阶段区贴合内容（或按需压缩）不留大块空白；logs 显式给
        # size=内容行+2 边框，使得「固定区 + 日志区」恰好等于屏幕高，任何尺寸
        # 下都不会把总体进度/日志区挤到屏幕外（rich Layout 截尾部）。
        header_h, top_h, stages_h, progress_h, footer_h = self._fixed_zone_heights()
        log_h = self._zone_log_visible_height() + _LOG_BORDERS

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=header_h),
            Layout(name="top", size=top_h),
            Layout(name="stages", size=stages_h),
            Layout(name="progress", size=progress_h),
            Layout(name="logs", size=log_h),
            Layout(name="footer", size=footer_h),
        )

        title = Text()
        title.append("🐍  ", style=BLUE)
        title.append("PDF 本地模型翻译工具", style=f"bold {TEXT}")
        title.append("   " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), style=MUTED)
        title.append("  │  ", style=MUTED)
        done = bool(self.stage >= 5 and self.merged_ok)
        title.append("● 已完成" if done else "● 运行中",
                     style=f"bold {GREEN}" if done else f"bold {BLUE}")

        layout["header"].update(
            RichPanel(title, box=box.SIMPLE, style=BG, padding=(0, 1))
        )
        layout["top"].update(self._zone_top())
        layout["stages"].update(self._zone_stages())
        layout["progress"].update(self._zone_overall())
        layout["logs"].update(self._zone_log())

        footer = Text()
        footer.append(" Ctrl+C ", style=f"bold {BLUE_LIGHT} on #122437")
        footer.append(" 中断任务   │   ", style=MUTED)
        if self._hold_footer:
            footer.append("按 Enter 关闭", style=f"bold {GREEN}")
        else:
            footer.append(
                "任务已完成" if done else "翻译过程中请勿关闭终端…",
                style=f"bold {GREEN}" if done else MUTED,
            )
        layout["footer"].update(RichPanel(footer, box=box.SIMPLE, style=BG, padding=(0, 1)))

        return layout


# ============================== 辅助：Ollama / PDF 探测 ==============================

def parse_host_port(host):
    """http://127.0.0.1:11434 -> (127.0.0.1, 11434)。解析不出端口返回 (host, None)。"""
    try:
        h = str(host).split("//", 1)[-1].strip("/")
        if h.startswith("["):                       # IPv6 字面量
            ip, _, rest = h.partition("]")
            if rest.startswith(":"):
                return ip.lstrip("["), int(rest[1:].split("/")[0])
            return ip.lstrip("["), None
        if ":" in h:
            host_only, _, port = h.rpartition(":")
            return host_only, int(port.split("/")[0])
        return h, None
    except Exception:
        return str(host), None


def _fmt_bytes(n):
    if n is None:
        return "—"
    try:
        n = float(n)
    except Exception:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} GB"


def _fmt_ctx(n):
    if not n:
        return "—"
    try:
        n = int(n)
    except Exception:
        return "—"
    return f"{n // 1024}K" if n >= 1024 else str(n)


def _norm_model(name):
    return str(name or "").strip().lower()


def fetch_ollama_status(host, model=None):
    """查 ollama：连接状态 / 端口 / 已装模型 / 目标模型就绪 / 运行中模型与显存占用。

    只读，绝不改任何配置。任何失败都以 ok=False + err 呈现，不抛异常。
    """
    import urllib.request
    out = {
        "ok": False, "err": "", "host": str(host), "h": "", "port": None,
        "models": [], "n_models": 0,
        "model_state": "未知", "model_ready": False,
        "running": [], "size_vram": None, "size_total": None,
        "context": None,
    }
    out["h"], out["port"] = parse_host_port(host)

    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        out["ok"] = True
    except Exception as e:
        out["err"] = f"{type(e).__name__}: {e}"
        out["model_state"] = "服务未连接"
        return out

    models = [m for m in data.get("models", []) if m.get("name")]
    out["models"] = [m.get("name") for m in models]
    out["n_models"] = len(models)

    if model:
        base = str(model).split(":")[0]
        hit = any(_norm_model(m.get("name")) == _norm_model(model)
                  or _norm_model(m.get("name")).startswith(_norm_model(base) + ":")
                  for m in models)
        out["model_ready"] = hit
        out["model_state"] = "已就绪" if hit else "未安装"
    else:
        out["model_state"] = "未指定"

    try:
        with urllib.request.urlopen(f"{host}/api/ps", timeout=5) as r:
            ps = json.loads(r.read().decode("utf-8"))
        ms = ps.get("models") or []
        out["running"] = [m.get("name", "") for m in ms]
        if ms:
            cur = ms[0]
            out["size_vram"] = cur.get("size_vram")
            out["size_total"] = cur.get("size")
            det = cur.get("details") or {}
            raw_ctx = (cur.get("model_info") or {}).get("general.context_length") \
                or det.get("context_length")
            out["context"] = raw_ctx
    except Exception:
        pass        # /api/ps 失败不影响 tags 的成功判定

    if model and out["model_ready"] and not out["running"]:
        out["model_state"] = "已就绪（未加载）"
    return out


def probe_pdf_info(pdf_path, panel=None):
    """全书统计：页数 / 总字数 / 是否文字版 / 平均每页字数。

    ⚠ 按需求做【全书逐页统计】（不是抽样），逐页回吐进度以免看起来卡死。
    不改动输入文件；只读。返回 dict，取不到的字段一律 None + 说明。
    """
    info = {
        "path": str(pdf_path), "name": Path(pdf_path).name,
        "size_mb": None, "pages": None, "chars": None, "chars_per_page": None,
        "text_pdf": None, "text_pdf_label": "未知", "err": "",
    }
    try:
        info["size_mb"] = Path(pdf_path).stat().st_size / 1024 / 1024
    except Exception as e:
        info["err"] = f"无法读取文件：{e}"
        return info

    fitz = _import_fitz()
    if fitz is None:
        info["err"] = "未安装 PyMuPDF，无法统计页数/字数/文字版（pip install pymupdf）"
        info["text_pdf_label"] = "无法判定（缺 PyMuPDF）"
        return info

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        info["err"] = f"打开失败：{type(e).__name__}: {e}"
        return info

    try:
        total = doc.page_count
        info["pages"] = total
        total_chars = 0
        text_pages = 0
        step = max(1, total // 20)          # 每 ~5% 回吐一次进度
        for i, page in enumerate(doc, 1):
            t = (page.get_text("text") or "").strip()
            n = len(t)
            total_chars += n
            if n >= 20:
                text_pages += 1
            if panel is not None and (i % step == 0 or i == total):
                log(f"  · 全书字数统计：{i}/{total} 页（累计 {_fmt_num(total_chars)} 字）",
                    "DEBUG")
    except Exception as e:
        info["err"] = f"读取内容失败：{type(e).__name__}: {e}"
        return info
    finally:
        try:
            doc.close()
        except Exception:
            pass

    info["chars"] = total_chars
    info["chars_per_page"] = round(total_chars / total, 1) if total else 0

    ratio = (text_pages / total) if total else 0
    if total_chars < 100:
        info["text_pdf"] = False
        info["text_pdf_label"] = "疑似扫描版（几乎无 text 层）"
    elif ratio >= 0.8:
        info["text_pdf"] = True
        info["text_pdf_label"] = "是（含可提取文字）"
    elif ratio >= 0.4:
        info["text_pdf"] = True
        info["text_pdf_label"] = f"部分（{ratio*100:.0f}% 页有文字）"
    else:
        info["text_pdf"] = False
        info["text_pdf_label"] = f"疑似扫描版（仅 {ratio*100:.0f}% 页有文字）"
    return info


# ============================== 主流程 ==============================
def run_translation(pdf_path, args, panel):
    """主流程：前置检查 → 清洗 → 分片 → 逐片调用 pdf2zh → 合并，
    全程把状态汇报给 DarkDashboard 的各个分区。"""
    out_dir = Path(args.out_dir) if args.out_dir else pdf_path.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = init_log_file(out_dir / LOG_DIRNAME)
    log(f"日志文件：{log_file}")

    # ---- 阶段：前置处理 ----
    panel.set_stage(1)

    # 语言参数归一（不传则用默认 en / zh，行为与旧版一致）。
    # 认不出的写法在此抛错，绝不静默透传给 pdf2zh 或退回默认值。
    try:
        src_lang = normalize_lang(getattr(args, "src_lang", None), DEFAULT_SRC_LANG)
        dst_lang = normalize_lang(getattr(args, "dst_lang", None), DEFAULT_DST_LANG)
    except LangError as e:
        log(f"语言参数错误：{e}", "ERROR")
        panel.fatal = True
        panel.set_preproc("skipped", "语言参数错误")
        raise
    args.src_lang, args.dst_lang = src_lang, dst_lang
    log(f"语言：{src_lang} → {dst_lang}")
    if src_lang == dst_lang:
        log("  提示：源语言与目标语言相同（如做同语言润色），确认无误可继续。", "WARN")

    # 自定义提示词文件（--prompt-file，默认不启用）
    try:
        args.prompt_file = resolve_prompt_file(getattr(args, "prompt_file", None))
    except PromptFileError as e:
        log(f"提示词文件错误：{e}", "ERROR")
        panel.fatal = True
        panel.set_preproc("skipped", "提示词文件不可用")
        raise
    if args.prompt_file:
        log(f"提示词文件：{args.prompt_file}（占位符 ${{lang_in}} → {src_lang}，"
            f"${{lang_out}} → {dst_lang}，${{text}} → 原文）")
    else:
        log("提示词：使用 pdf2zh 内置默认模板（未指定 --prompt-file）")

    if not pdf_path.exists():
        log(f"PDF 不存在：{pdf_path}", "ERROR")
        panel.fatal = True
        panel.set_preproc("skipped", "输入文件不存在")
        return 1

    size_mb = pdf_path.stat().st_size / 1024 / 1024
    log(f"输入文件：{pdf_path.name}（{size_mb:.1f} MB）", "STEP")
    panel.set_pdf_info({"name": pdf_path.name, "size_mb": size_mb})
    panel.set_preproc("running", "探测中") if False else None

    # 全书字数 / 文字版判定
    panel.set_pdf_probing(True)
    log("前置处理：全书统计字数与文字版判定（逐页扫描，勿关窗口）…", "STEP")
    info = probe_pdf_info(pdf_path, panel=panel)
    panel.set_pdf_info(info)
    log(f"  · 页数 {_fmt_num(info.get('pages'))}｜全书字数 {_fmt_num(info.get('chars'))}"
        f"｜文字版：{info.get('text_pdf_label')}")
    if info.get("err"):
        log(f"  · 探测告警：{info['err']}", "WARN")

    # Ollama 状态
    panel.set_ollama_probing(True)
    log("前置处理：查询 Ollama 服务状态（连接 / 端口 / 模型 / 显存）…", "STEP")
    st = fetch_ollama_status(args.ollama_host, args.model)
    panel.set_ollama(st)
    if st.get("ok"):
        log(f"  · Ollama 已连接 {st.get('host')}（端口 {st.get('port')}，"
            f"已装 {st.get('n_models')} 个模型）")
        if st.get("running"):
            log(f"  · 已加载 {', '.join(st['running'])}｜显存占用 {_fmt_bytes(st.get('size_vram'))}")
        else:
            log("  · 当前无模型常驻显存（首次调用时加载）")
    else:
        log(f"  · Ollama 未连接：{st.get('err')}", "WARN")
        log("    请在另一个窗口运行：ollama serve", "WARN")

    # pdf2zh 命令
    pdf2zh_exe = check_pdf2zh()
    if not pdf2zh_exe:
        panel.fatal = True
        panel.set_preproc("skipped", "未找到 pdf2zh")
        return 1
    log(f"  · pdf2zh: {pdf2zh_exe}")

    # 模型（缺失则交互选择；此处必须清屏）
    if not args.model:
        if args.dry_run:
            log("dry-run 模式必须用 --model 指定模型。", "ERROR")
            panel.fatal = True
            return 1
        installed = list_ollama_models(args.ollama_host)
        chosen = choose_model_interactive(installed, panel=panel)
        if not chosen:
            log("未选择模型，已取消。", "ERROR")
            panel.fatal = True
            return 1
        args.model = chosen
        st = fetch_ollama_status(args.ollama_host, args.model)
        panel.set_ollama(st)
    log(f"  · 模型：{args.model}")

    os.environ["OLLAMA_HOST"] = args.ollama_host
    os.environ["OLLAMA_MODEL"] = args.model
    os.environ["HF_ENDPOINT"] = args.hf_endpoint
    if args.keep_alive:
        os.environ["OLLAMA_KEEP_ALIVE"] = args.keep_alive

    ok_ol, _names = check_ollama(args.ollama_host, args.model)
    st = fetch_ollama_status(args.ollama_host, args.model)
    if ok_ol:
        st["ok"] = True
        st["model_ready"] = True
    panel.set_ollama(st)
    if not ok_ol and not args.dry_run:
        panel.fatal = True
        panel.set_preproc("skipped", "Ollama / 模型不可用")
        return 1

    # 页范围
    try:
        user_ranges = parse_pages(args.pages)
    except ValueError as e:
        log(str(e), "ERROR")
        panel.fatal = True
        return 1

    # 预处理（清洗非法 dict 键）
    work_pdf = pdf_path
    if args.repair:
        panel.set_preproc("running", "清洗 PDF（修复非法 dict 键）")
        log("前置处理：清洗 PDF（修复非法 dict 键，规避 pymupdf save 崩溃 #1137）…", "STEP")
        repaired = out_dir / f"{pdf_path.stem}_repaired.pdf"
        rok, rmsg = repair_pdf(pdf_path, repaired)
        if rok:
            log(f"  ✓ {rmsg}")
            work_pdf = repaired
            panel.set_preproc("ok", rmsg)
        else:
            log(f"  ✗ 清洗失败：{rmsg}", "WARN")
            log("  将直接用原始 PDF 继续（若报 invalid key in dict，说明此路不通）。", "WARN")
            panel.set_preproc("fallback", rmsg)
    else:
        log("已跳过 PDF 预处理（--no-repair）")
        panel.set_preproc("skipped", "由 --no-repair 指定")

    # ---- 阶段：分片文件 ----
    panel.set_stage(2)
    total = get_page_count(work_pdf) or get_page_count(pdf_path) or args.total_pages
    if total is None:
        log("无法自动获取页数（缺 PyMuPDF/pdfinfo）。请用 --total-pages 手工指定。", "ERROR")
        panel.fatal = True
        return 1
    log(f"总页数：{total}")
    panel.total_pages = total
    if not panel.pdf_info.get("pages"):
        panel.pdf_info["pages"] = total

    eff0 = []
    if user_ranges:
        eff0 = clamp_ranges(user_ranges, total)
        if not eff0:
            log(f"指定的页范围超出文档（总 {total} 页），无事可做。", "ERROR")
            panel.fatal = True
            return 1
        panel.scoped_total = sum(e - s + 1 for s, e in eff0)
        panel.scope_label = ",".join(f"{s}-{e}" for s, e in eff0)
    else:
        panel.scoped_total = total
    panel.refresh()

    if args.dry_run:
        if user_ranges:
            dry_chunks = make_chunks(total, args.pages_per_chunk, clamp_ranges(user_ranges, total))
            log(f"dry-run：指定页范围 -> {len(dry_chunks)} 个分片")
            for s, e in dry_chunks:
                log(f"    p{s}-{e}")
        log("dry-run：自检通过，未执行翻译。")
        return 0

    if args.probe_only:
        chunks = [(1, min(5, total))]
        log("probe-only：仅翻译前 5 页用于质量验证")
    else:
        effective = None
        if user_ranges:
            effective = clamp_ranges(user_ranges, total)
            dropped = [(a, b) for a, b in user_ranges if a > total]
            if dropped:
                log(f"警告：以下范围超出文档已忽略：{dropped}", "WARN")
            log(f"限定页范围：{effective}（共 {panel.scoped_total} 页）")
        chunks = make_chunks(total, args.pages_per_chunk, effective)
    log(f"共 {len(chunks)} 个分片，每片约 {args.pages_per_chunk} 页")

    panel.n_chunks = len(chunks)
    panel.chunks = list(chunks)
    for i in range(1, len(chunks) + 1):
        panel.chunk_states[i] = "pending"
    panel.refresh()

    # ---- 阶段：翻译内容 ----
    panel.set_stage(3)
    scope = args.pages.replace(" ", "") if args.pages else "all"
    stem_key = pdf_path.stem if scope == "all" else f"{pdf_path.stem}_scope-{scope}"
    mpath = manifest_path(out_dir, stem_key)
    manifest = load_manifest(mpath)
    done = set(manifest.get("done", []))
    log(f"续跑清单：{mpath.name}，已完成 {len(done)} 个分片")

    mono_parts, dual_parts = {}, {}
    order = {i: ch for i, ch in enumerate(chunks, 1)}
    chunks_root = out_dir / CHUNKS_DIRNAME
    chunks_root.mkdir(parents=True, exist_ok=True)

    t_all = time.time()
    for idx, (start, end) in enumerate(chunks, 1):
        tag = f"{start}-{end}"
        pages_in_chunk = end - start + 1
        chunk_dir = chunks_root / f"p{start}-{end}"
        panel.start_chunk(idx, start, end)
        panel.refresh()

        if tag in done:
            m, d = _find_chunk_outputs(chunk_dir, pdf_path.stem)
            if m or d:
                log(f"[{idx}/{len(chunks)}] 跳过（已完成）：p{tag}")
                if m:
                    mono_parts[idx] = m
                if d:
                    dual_parts[idx] = d
                panel.cur_step = 3
                panel.finish_chunk(idx, pages_in_chunk, "skipped")
                continue
            log(f"[{idx}/{len(chunks)}] p{tag} 标记完成但产物已清理，重新翻译", "WARN")
            done.discard(tag)

        log(f"[{idx}/{len(chunks)}] 翻译 p{tag} …", "STEP")
        panel.cur_step = 0
        panel.cur_pages_done = 0
        panel.refresh()

        try:
            ok, elapsed, err, _pd, mono_p, dual_p = run_pdf2zh(
                pdf2zh_exe, work_pdf, start, end, args, chunk_dir, panel=panel)
        except Exception as e:
            ok, elapsed, err = False, 0.0, f"内部异常：{type(e).__name__}: {e}"
            mono_p = dual_p = None

        panel.cur_step = 2
        panel.refresh()

        if ok:
            log(f"  ✓ p{tag} 完成，用时 {elapsed/60:.1f} 分钟", "OK")
            done.add(tag)
            manifest["done"] = sorted(done, key=lambda s: int(s.split("-")[0]))
            manifest["failed"] = [f for f in manifest.get("failed", []) if f != tag]
            if mono_p:
                mono_parts[idx] = mono_p
            if dual_p:
                dual_parts[idx] = dual_p
            panel.finish_chunk(idx, pages_in_chunk, "done")
        else:
            log(f"  ✗ p{tag} 失败：{err}", "ERROR")
            if tag not in manifest.get("failed", []):
                manifest.setdefault("failed", []).append(tag)
            panel.finish_chunk(idx, pages_in_chunk, "failed")
            if args.stop_on_error:
                save_manifest(mpath, manifest)
                log("已按 --stop-on-error 中止。", "ERROR")
                panel.fatal = True
                return 2
        save_manifest(mpath, manifest)
        panel.refresh()

    # ---- 阶段：合并内容 ----
    panel.cur_pages_done = 0
    panel.set_stage(4)
    merged = []
    panel.merged_skipped = bool(args.merge and manifest.get("failed"))
    if args.merge and not manifest.get("failed"):
        if len(order) == 1:
            merged = stage_single_chunk(mono_parts, dual_parts, eff0,
                                        out_dir, pdf_path.stem, args)
        else:
            merged = merge_chunks(mono_parts, dual_parts, order, out_dir,
                                  pdf_path.stem, args)
    elif args.merge:
        log("存在失败分片，暂不合并（修好后重跑即可自动重试失败片）。", "WARN")

    # ---- 阶段⑤：输出 PDF ----
    panel.merged_ok = bool(merged)
    panel.merged_single = (len(order) == 1)
    panel.set_stage(5)

    mins = (time.time() - t_all) / 60
    log(f"翻译结束，总用时 {mins:.1f} 分钟", "OK")
    log(f"成功 {len(done)} / {len(chunks)} 片")
    for f in merged:
        log(f"  产物：{f}", "OK")
    log(f"  输出目录：{out_dir}")
    if manifest.get("failed"):
        log(f"  失败分片：{manifest['failed']}（重跑本脚本会自动重试）", "ERROR")
    return 0


# ============================== CLI ==============================
def build_parser():
    p = argparse.ArgumentParser(
        description="PDF 双语翻译（单文件 · Rich 全屏分区式监控面板）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("pdf", help="PDF 文件路径")
    p.add_argument("--pages", default=None, help="只翻译指定页范围，如 1-50 或 1-5,20-30")
    p.add_argument("--model", default=None, help="Ollama 模型名（不填交互选择）")
    p.add_argument("--plain", action="store_true",
                   help="关闭面板，退回普通滚动日志")
    p.add_argument("--merge", dest="merge", action="store_true", default=True)
    p.add_argument("--no-merge", dest="merge", action="store_false")
    p.add_argument("--keep-chunks", action="store_true", help="合并后保留分片文件")
    p.add_argument("--ollama-host", default=DEFAULT_OLLAMA_HOST)
    p.add_argument("--hf-endpoint", default=DEFAULT_HF_ENDPOINT)
    p.add_argument("--pages-per-chunk", type=int, default=DEFAULT_PAGES_PER_CHUNK)
    p.add_argument("--threads", type=int, default=DEFAULT_THREADS,
                   help="pdf2zh 并发线程（默认 1，并发过高易 OOM）")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_PER_CHUNK,
                   help="单片超时秒数")
    p.add_argument("--keep-alive", default="30m", help="ollama 模型常驻时长")
    p.add_argument("--src-lang", default=None,
                   help=f"源语言，默认 {DEFAULT_SRC_LANG}；也接受 English / 英文 等写法，"
                        "脚本会归一成 pdf2zh 语言代码，认不出则报错")
    p.add_argument("--dst-lang", default=None,
                   help=f"目标语言，默认 {DEFAULT_DST_LANG}；也接受 Chinese / 中文 / "
                        "zh-TW 等写法，脚本会归一成 pdf2zh 语言代码，认不出则报错")
    p.add_argument("--prompt-file", default=None,
                   help="自定义翻译提示词文件（UTF-8，可含 ${lang_in} / ${lang_out} / "
                        "${text} 占位符）。默认不启用，用 pdf2zh 内置模板")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--total-pages", type=int, default=None)
    p.add_argument("--ultrafast", action="store_true")
    p.add_argument(
        "--no-skip-subset-fonts", dest="skip_subset_fonts",
        action="store_false", default=True,
        help="关闭「跳过字体子集化」。默认跳过。"
             "pdf2zh 的 subset_fonts 对超大 CJK 字体是超线性开销，"
             "且某些 PDF 会在此阶段永久挂死（pymupdf issue #3891）。"
             "代价：产物 PDF 会大 ~13-16MB/册。")
    p.add_argument("--stop-on-error", action="store_true")
    p.add_argument("--repair", dest="repair", action="store_true", default=True)
    p.add_argument("--no-repair", dest="repair", action="store_false")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--probe-only", action="store_true")
    return p


def main():
    require_rich()
    args = build_parser().parse_args()
    pdf_path = Path(args.pdf).expanduser().resolve()

    want_panel = (not args.plain) and sys.stdout.isatty()
    if args.plain:
        print("已按 --plain 使用普通日志模式。", file=sys.stderr)
    elif not sys.stdout.isatty():
        print("提示：非交互终端，已退回普通日志模式（面板需要 TTY）。", file=sys.stderr)

    if not want_panel:
        set_log_sink(None)
        panel = DarkDashboard(pdf_path, args, enabled=False)
        try:
            return run_translation(pdf_path, args, panel)
        except KeyboardInterrupt:
            log("用户中断。重新运行可续跑。", "WARN")
            return 130
        except (LangError, PromptFileError):
            # 参数错误：run_translation 已打出具体原因与位置（退出码 1）。
            return 1
        except Exception as e:
            import traceback
            log(f"未捕获异常：{type(e).__name__}: {e}", "ERROR")
            for ln in traceback.format_exc().splitlines()[-8:]:
                log("  " + ln, "ERROR")
            return 3

    console = Console()
    panel = DarkDashboard(pdf_path, args, console=console, enabled=True)
    set_log_sink(panel)
    panel.start()
    rc = 3  # 缺省失败码，兜底「run_translation 未赋值就异常」的未绑定情况
    try:
        rc = run_translation(pdf_path, args, panel)
    except KeyboardInterrupt:
        log("用户中断。重新运行可续跑。", "WARN")
        rc = 130
    except (LangError, PromptFileError):
        # 参数错误：run_translation 已打出具体原因，这里只定退出码（1）。
        rc = 1
    except Exception as e:
        import traceback
        log(f"未捕获异常：{type(e).__name__}: {e}", "ERROR")
        for ln in traceback.format_exc().splitlines()[-8:]:
            log("  " + ln, "ERROR")
        rc = 3
    finally:
        # 先用 rc_hold 中转，保证 finally 里 rc 一定已绑定（避免未绑定变量）。
        # 结束场景统一停留：hold_and_wait 后再 stop 关闭全屏（契约 §1.2）。
        rc_hold = rc
        panel.hold_and_wait(rc_hold)
        panel.stop()
    return rc_hold


if __name__ == "__main__":
    sys.exit(main())
