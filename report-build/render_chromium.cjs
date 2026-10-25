const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

const [htmlPath, pdfPath] = process.argv.slice(2);
if (!htmlPath || !pdfPath) {
  throw new Error('HTML 和 PDF 路径必填');
}

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  });
  try {
    const page = await browser.newPage();
    await page.goto(pathToFileURL(path.resolve(htmlPath)).href, { waitUntil: 'networkidle' });
    await page.pdf({
      path: path.resolve(pdfPath),
      format: 'A4',
      printBackground: true,
      displayHeaderFooter: true,
      headerTemplate: '<div></div>',
      footerTemplate: '<div style="width:100%;font:7pt Arial,sans-serif;color:#768191;padding:0 19mm;"><span>懂球帝阅读助手开发报告</span><span style="float:right"><span class="pageNumber"></span></span></div>',
      margin: { top: '17mm', bottom: '15mm', left: '19mm', right: '19mm' },
    });
  } finally {
    await browser.close();
  }
})().catch((error) => {
  process.stderr.write(error.stack + '\n');
  process.exitCode = 1;
});
