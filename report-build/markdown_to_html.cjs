const fs = require('node:fs');

(async () => {
  const { marked } = await import('file:///C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/marked/lib/marked.esm.js');
  const sourcePath = process.argv[2];
  if (!sourcePath) {
    throw new Error('report.md 路径必填');
  }
  const markdown = fs.readFileSync(sourcePath, 'utf8');
  process.stdout.write(marked.parse(markdown));
})().catch((error) => {
  process.stderr.write(error.stack + '\n');
  process.exitCode = 1;
});
