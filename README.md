# scripthub

by deepseek-v4-flash + Hermes Agent

这是一个存放由 AI Agent 生成脚本的仓库，只用于分享特定需求的脚本，如果你的需求正好和脚本功能对得上，欢迎当作参考使用🤗

---

## 目录结构

```
scripthub/
├── python/
│   └── translate_pdf2zh.py   # pdf2zh + Ollama 本地模型翻译大型 PDF
├── README.md
└── LICENSE
```

## python/translate_pdf2zh.py

用 [PDFMathTranslate (pdf2zh)](https://github.com/PDFMathTranslate/PDFMathTranslate) + Ollama 本地模型翻译大型 PDF 教材。单文件脚本，带 Rich 全屏分区式监控面板。

### 功能

- **整本或指定页范围翻译**：按页切片（默认 20 页/片）逐片调用 `pdf2zh -s ollama`
- **断点续跑**：每片完成即写入续跑清单 `<stem>.manifest.json`；中断后重跑同一命令，已完成片自动跳过，失败片自动重试；全部片成功后才合并（`--merge` 默认开启）
- **前置自检**：PDF 是否存在 / 页数 / 是否文字版 / 全书字数，Ollama 服务与指定模型是否就绪，`pdf2zh` 命令是否可执行
- **前置清洗**：重写 PDF 修掉非法 dict 键，规避 pymupdf 保存阶段崩溃（`--no-repair` 可跳过）
- **分片合并**：`garbage=4` + `clean` 清理重复与未引用对象，合并成功后默认删除分片目录（`--keep-chunks` 保留）
- **卡死可诊断**：单片超时、`pdf2zh` 打完 100% 后静默收尾、按页进度前进计时，判定「仍在推进」与「真卡死」
- **监控面板**（TTY 下默认启用）五个区：PDF 文件信息 ｜ Ollama 运行状态（连接 / 端口 / 模型 / 显存）｜ 处理阶段五步 ｜ 总体进度条 ｜ 带级别与时间戳的执行日志
- **语言参数**：默认英译中，`--src-lang` / `--dst-lang` 可改；也接受 `English` / `中文` / `Chinese` / `zh-TW` 这类写法，脚本归一成 pdf2zh 语言代码
- **自定义翻译提示词**：`--prompt-file <文件>`，默认不启用

### 依赖

| 依赖 | 说明 |
|---|---|
| Python 3.12 | 3.13 有兼容风险 |
| `ollama` | 服务已启动，目标模型已 pull |
| `pdf2zh` | `pip install uv && uv tool install --python 3.12 pdf2zh` |
| `PyMuPDF` | 统计字数 / 裁剪 / 合并 / 预处理 |
| `rich` | 强依赖，缺失时直接报错并以退出码 4 结束（无降级实现） |

### 安装

```bash
pip install uv
uv tool install --python 3.12 pdf2zh
pip install pymupdf rich
ollama pull Hy-MT2
```

### 用法

```bash
# 最简：整本翻译，模型用默认值
python translate_pdf2zh.py "book.pdf"

# 指定模型（不指定时：TTY 下交互选择已装模型）
python translate_pdf2zh.py "book.pdf" --model Hy-MT2

# 只自检不翻译：查 PDF 页数 / Ollama 服务与模型 / pdf2zh 是否可用
python translate_pdf2zh.py "book.pdf" --model Hy-MT2 --dry-run

# 只译前 5 页验质量，看版式与术语是否正常
python translate_pdf2zh.py "book.pdf" --model Hy-MT2 --probe-only

# 只译指定页范围（可多段，逗号分隔，越界部分自动裁掉）
python translate_pdf2zh.py "book.pdf" --pages 1-50
python translate_pdf2zh.py "book.pdf" --pages 1-5,20-30

# 非交互环境 / 重定向输出到文件时手动关面板，用普通滚动日志
python translate_pdf2zh.py "book.pdf" --model Hy-MT2 --plain > run.log 2>&1

# 调参：分片页数 / 单片超时 / 模型常驻时长 / 输出目录 / 保留分片 / 失败即停
python translate_pdf2zh.py "book.pdf" --model Hy-MT2 \
    --pages-per-chunk 10 --timeout 1800 --keep-alive 10m \
    --out-dir ./out --keep-chunks --stop-on-error

# 指定源语言与目标语言（默认英译中；也可写全称或中文）
python translate_pdf2zh.py "book.pdf" --src-lang English --dst-lang 中文

# 自定义翻译提示词（UTF-8，可含 ${lang_in} / ${lang_out} / ${text} 占位符）
python translate_pdf2zh.py "book.pdf" --prompt-file my_prompt.txt
```

### ⚠️ 续跑的两个坑

1. **`chunks/` 必须还在**。跳过判定依据是 `chunks/` 里仍存在该片的 `-mono-sliced` / `-dual-sliced` 产物。合并成功且未加 `--keep-chunks` 时会删掉分片目录，此时清单虽仍标「已完成」，重跑会整本重译。
2. **默认 `--repair` 会让重跑永远全量重译**。产物文件名取自「当前翻译用的 PDF」，而 `--repair` 先生成 `<stem>_repaired.pdf` 再翻，产物因此叫 `<stem>_repaired-mono-sliced.pdf`，查找用的却是原始 `<stem>`，两者对不上，日志会提示「标记完成但产物已清理」。

需要续跑时两条一起用（实测可正常跳过）：

```bash
python translate_pdf2zh.py "book.pdf" --model Hy-MT2 --no-repair --keep-chunks
```

## LICENSE

[MIT](LICENSE)
