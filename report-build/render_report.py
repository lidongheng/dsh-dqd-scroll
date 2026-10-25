import importlib.util;
import subprocess;
import sys;
from pathlib import Path;

from pypdf import PdfReader;

sys.stdout.reconfigure(encoding='utf-8');
sys.stderr.reconfigure(encoding='utf-8');

ROOT = Path(__file__).resolve().parent.parent;
BUILD_DIR = ROOT / 'report-build';
CORE_PATH = BUILD_DIR / 'render.py';
BUILDER_PATH = BUILD_DIR / 'build_report.py';
HTML_PATH = ROOT / 'report.html';
PDF_PATH = ROOT / 'report.pdf';
CHROMIUM_SCRIPT = BUILD_DIR / 'render_chromium.cjs';
NODE = Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe');
PYTHON = Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe');

spec = importlib.util.spec_from_file_location('huashu_render', CORE_PATH);
if spec is None or spec.loader is None:
    raise RuntimeError('无法加载 huashu-report 渲染器');
core = importlib.util.module_from_spec(spec);
spec.loader.exec_module(core);

core.REPORT_TITLE = '懂球帝阅读助手开发报告';
core.ANCHORS = [
    ('摘要', r'^\s*摘要\s*$'),
    ('第一幕', r'^\s*第一幕.*$'),
    ('第二幕', r'^\s*第二幕.*$'),
    ('第三幕', r'^\s*第三幕.*$'),
    ('工具箱', r'^\s*工具箱.*$'),
    ('参考资料', r'^\s*参考资料\s*$'),
];

def page_count(pdf_path: str) -> int:
    return len(PdfReader(pdf_path).pages);

def page_texts(pdf_path: str, count: int) -> dict[int, str]:
    pages = PdfReader(pdf_path).pages;
    return {index + 1: pages[index].extract_text() or '' for index in range(count)};

core.page_count = page_count;
core.page_texts = page_texts;

for round_no in range(1, 5):
    subprocess.run([str(PYTHON), str(BUILDER_PATH)], check=True);
    subprocess.run([str(NODE), str(CHROMIUM_SCRIPT), str(HTML_PATH), str(PDF_PATH)], check=True);
    found, page_total = core.locate(str(PDF_PATH), core.ANCHORS);
    missing = [key for key, _ in core.ANCHORS if key not in found];
    if missing:
        print(f'第 {round_no} 轮未定位到：{missing}');
    if not core.patch_toc(str(BUILDER_PATH), found):
        print(f'目录页码已收敛（{page_total} 页）');
        break;
    print(f'第 {round_no} 轮回填页码：{found}');
else:
    print('目录页码在四轮内未收敛');

core.selfcheck(str(PDF_PATH), str(HTML_PATH));
