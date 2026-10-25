import { chmodSync, copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';

// Pin uv and its release checksum manifest together so a download mirror cannot replace the executable.
const UV_VERSION = '0.13.5';
const UV_RELEASE = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}`;
const UV_MANIFEST_SHA256 = 'a7084f69eaafe57648c90bf7be8cb091bfccd796977f6f5383085a182fb6d2e1';

const sha256Of = (value) => createHash('sha256').update(value).digest('hex');

const linuxLibc = () => {
  const runtime = process.report?.getReport?.()?.header?.glibcVersionRuntime;
  if (typeof runtime === 'string' && runtime.length > 0) return 'gnu';
  if (existsSync('/lib/ld-musl-aarch64.so.1') || existsSync('/lib/ld-musl-x86_64.so.1')) return 'musl';
  throw new Error('无法识别当前 Linux 的 libc 类型。');
};

const uvAssetName = () => {
  if (process.platform === 'win32') {
    if (process.arch === 'arm64') return 'uv-aarch64-pc-windows-msvc.zip';
    if (process.arch === 'x64') return 'uv-x86_64-pc-windows-msvc.zip';
    throw new Error(`uv 暂不支持当前 Windows 架构: ${process.arch}`);
  }
  if (process.platform === 'darwin') {
    if (process.arch === 'arm64') return 'uv-aarch64-apple-darwin.tar.gz';
    if (process.arch === 'x64') return 'uv-x86_64-apple-darwin.tar.gz';
    throw new Error(`uv 暂不支持当前 macOS 架构: ${process.arch}`);
  }
  if (process.platform === 'linux') {
    if (process.arch === 'arm64') return `uv-aarch64-unknown-linux-${linuxLibc()}.tar.gz`;
    if (process.arch === 'x64') return `uv-x86_64-unknown-linux-${linuxLibc()}.tar.gz`;
    throw new Error(`uv 暂不支持当前 Linux 架构: ${process.arch}`);
  }
  throw new Error(`uv 暂不支持当前系统: ${process.platform} ${process.arch}`);
};

const downloadUrls = (url) => [
  url,
  `https://gh-proxy.com/${url}`,
  `https://ghproxy.net/${url}`,
];

const fetchBuffer = async (url) => {
  const response = await fetch(url, { signal: AbortSignal.timeout(120_000) });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return Buffer.from(await response.arrayBuffer());
};

const fetchVerifiedManifest = async () => {
  const errors = [];
  for (const url of downloadUrls(`${UV_RELEASE}/sha256.sum`)) {
    try {
      const manifest = await fetchBuffer(url);
      if (sha256Of(manifest) !== UV_MANIFEST_SHA256) {
        throw new Error('uv 官方校验清单 SHA-256 不符');
      }
      return manifest.toString('utf8');
    } catch (error) {
      errors.push(`${url}: ${error.message}`);
    }
  }
  throw new Error(`无法取得并验证 uv ${UV_VERSION} 官方校验清单。\n${errors.join('\n')}`);
};

const findBin = (name, directory) => {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      const match = findBin(name, path);
      if (match) return match;
    } else if (entry.name === name) {
      return path;
    }
  }
  return null;
};

const extractArchive = (archivePath, targetDir) => {
  const result = spawnSync('tar', ['-xf', archivePath, '-C', targetDir], {
    encoding: 'utf8',
    windowsHide: true,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`解压 uv 安装包失败: ${result.stderr || result.stdout || `exit=${result.status}`}`);
  }
};

const downloadedUv = async (targetDir, binName, manifest) => {
  const assetName = uvAssetName();
  const manifestEntry = manifest.split(/\r?\n/).find((line) => line.trim().endsWith(assetName));
  const match = manifestEntry?.match(/^([a-f0-9]{64})\s+\*?(.+)$/i);
  if (!match || match[2].trim() !== assetName) {
    throw new Error(`uv ${UV_VERSION} 官方校验清单缺少 ${assetName}。`);
  }

  const expectedSha256 = match[1].toLowerCase();
  const archiveName = assetName;
  const archivePath = join(targetDir, archiveName);
  const errors = [];
  for (const url of downloadUrls(`${UV_RELEASE}/${archiveName}`)) {
    try {
      const archive = await fetchBuffer(url);
      if (sha256Of(archive) !== expectedSha256) {
        throw new Error('下载文件 SHA-256 与 uv 官方清单不符');
      }
      writeFileSync(archivePath, archive);
      const extractDir = join(targetDir, 'extract');
      mkdirSync(extractDir, { recursive: true });
      extractArchive(archivePath, extractDir);
      const extractedBin = findBin(binName, extractDir);
      if (!extractedBin) throw new Error(`解压结果中未找到 ${binName}`);
      return extractedBin;
    } catch (error) {
      errors.push(`${url}: ${error.message}`);
      rmSync(archivePath, { force: true });
      rmSync(join(targetDir, 'extract'), { recursive: true, force: true });
    }
  }
  throw new Error(`下载 uv ${UV_VERSION} 失败。\n${errors.join('\n')}`);
};

export async function ensureUv({ dir }) {
  const systemUv = spawnSync('uv', ['--version'], { encoding: 'utf8', windowsHide: true });
  if (!systemUv.error) {
    if (systemUv.status !== 0) throw new Error(`系统 uv 无法启动: ${systemUv.stderr || systemUv.stdout}`);
    return 'uv';
  }
  if (systemUv.error.code !== 'ENOENT') throw systemUv.error;

  const binName = process.platform === 'win32' ? 'uv.exe' : 'uv';
  const target = join(dir, binName);
  if (existsSync(target)) {
    const version = spawnSync(target, ['--version'], { encoding: 'utf8', windowsHide: true });
    if (version.error) throw version.error;
    if (version.status !== 0) throw new Error(`插件目录中的 uv 无法启动: ${version.stderr || version.stdout}`);
    return target;
  }

  mkdirSync(dir, { recursive: true });
  const tempDir = join(dir, '.uv-install');
  rmSync(tempDir, { recursive: true, force: true });
  mkdirSync(tempDir, { recursive: true });
  try {
    const manifest = await fetchVerifiedManifest();
    const extractedBin = await downloadedUv(tempDir, binName, manifest);
    copyFileSync(extractedBin, target);
    if (process.platform !== 'win32') chmodSync(target, 0o755);
    const version = spawnSync(target, ['--version'], { encoding: 'utf8', windowsHide: true });
    if (version.error) throw version.error;
    if (version.status !== 0) throw new Error(`下载的 uv 无法在本机启动: ${version.stderr || version.stdout}`);
    return target;
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
}
