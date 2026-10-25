import re
import subprocess
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKDOWN = ROOT / 'report.md'
MARKED_SCRIPT = ROOT / 'report-build' / 'markdown_to_html.cjs'
OUTPUT = ROOT / 'report.html'

def toc_row(key: str, title: str, page: int) -> str:
    return f'<div class="toc-row"><span>{escape(title)}</span><span>{page}</span></div>'

TOC_ROWS = [
    toc_row("摘要", "摘要", 2),
    toc_row("第一幕", "第一幕｜先拆开一个已经跑起来的项目", 4),
    toc_row("第二幕", "第二幕｜懂球帝没有 MCP：用自编脚本调用只读接口", 6),
    toc_row("第三幕", "第三幕｜把它变成 Python 初学者能维护的项目", 10),
    toc_row("工具箱", "工具箱｜启动编码前要能回答的问题", 14),
    toc_row("参考资料", "参考资料", 15),
]

def render() -> None:
    result = subprocess.run(
        ['C:\\Users\\Administrator\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\bin\\node.exe',
         str(MARKED_SCRIPT), str(MARKDOWN)],
        check=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
    )
    html_body = result.stdout
    blocks = re.split(r'(?=<h2>.*?</h2>)', html_body, flags=re.DOTALL)
    chapters = [block for block in blocks if re.match(r'<h2>', block)]
    if len(chapters) != len(TOC_ROWS):
        raise ValueError(f'章节目录数量不一致：正文 {len(chapters)}，目录 {len(TOC_ROWS)}')

    summary = chapters[0]
    toc_html = ''.join(TOC_ROWS)
    chapter_html = ''.join(
        '<table class="pagewrap"><thead><tr><td><div class="crumb">'
        + re.sub(r'<[^>]+>', '', chapter.split('</h2>', 1)[0])
        + ' | 懂球帝阅读助手开发报告</div></td></tr></thead><tbody><tr><td class="chapter">'
        + chapter
        + '</td></tr></tbody></table>'
        for chapter in chapters[1:]
    )
    document = f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>从“刷 B 站”到懂球帝 API 阅读助手</title>
<link rel="stylesheet" href="report.css">
<link rel="stylesheet" href="report-extra.css">
</head>
<body>
<section class="cover">
  <div class="cover-grid"></div>
  <p class="eyebrow">ENGINEERING FIELD GUIDE · 2026.10</p>
  <div class="cover-rule"></div>
  <h1>从“刷 B 站”到<br>懂球帝 API 阅读助手</h1>
  <p class="cover-subtitle">基于 dsh-bili-scroll 的 Python 后端与 DSH 插件开发方案</p>
  <p class="cover-thesis">从授权 APP 请求中核实接口，再由 DSH 插件调用自编 Python 脚本。</p>
  <div class="cover-meta"><span>方案研究</span><span>面向 JavaScript 前端转 Python 后端的开发者</span><span>2026-10-25</span></div>
  <div class="cover-foot"><span>事实、建议与待验证假设分开标注</span><span>01 / FIELD GUIDE</span></div>
</section>
<section class="abstract">{summary}</section>
<table class="pagewrap toc-page"><thead><tr><td><div class="crumb">目录 | 懂球帝阅读助手开发报告</div></td></tr></thead><tbody><tr><td>
<h2>目录</h2>{toc_html}
</td></tr></tbody></table>
{chapter_html}
</body>
</html>'''
    OUTPUT.write_text(document, encoding='utf-8')

if __name__ == '__main__':
    render()

