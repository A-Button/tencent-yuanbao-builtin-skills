/**
 * init 子命令 —— 环境准备（每次对话首次执行）
 *
 * 执行顺序：Node >= 18 → npm → npm install → tsc 编译 → .env 校验 → CLIGuard
 * 每一步失败立即返回 error code + message。
 */

import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { SCRIPTS_ROOT } from '../lib/scripts-root.js';

export interface InitResult {
  success: boolean;
  error?: string;
  message?: string;
  scripts_dir?: string;
  node?: string;
  [key: string]: unknown;
}

function checkNode(): InitResult | null {
  const major = parseInt(process.versions.node.split('.')[0], 10);
  if (major < 18) {
    return {
      success: false,
      error: 'NODE_VERSION_LOW',
      current: process.version,
      message: '当前 Node.js 版本过低，本助手需要 >= 18，请升级后重试',
    };
  }
  return null;
}

function checkNpm(): InitResult | null {
  try {
    execSync('npm --version', { stdio: 'pipe' });
  } catch {
    return {
      success: false,
      error: 'NPM_NOT_FOUND',
      message: '本助手需要 npm，请确认 Node.js 安装完整后重试',
    };
  }
  return null;
}

function checkInstall(): InitResult | null {
  if (fs.existsSync(path.join(SCRIPTS_ROOT, 'node_modules'))) return null;
  try {
    console.error('[init] 首次运行，安装依赖...');
    execSync('npm install --silent', { cwd: SCRIPTS_ROOT, stdio: 'pipe' });
    console.error('[init] 依赖安装完成');
  } catch {
    return {
      success: false,
      error: 'INSTALL_FAILED',
      message: '依赖安装失败，请确认已安装 Node.js 和 npm，且可访问内网 npm 源后重试',
    };
  }
  return null;
}

function checkBuild(): InitResult | null {
  const runJs = path.join(SCRIPTS_ROOT, 'dist', 'run.js');
  if (fs.existsSync(runJs)) return null;
  try {
    console.error('[init] 编译 TypeScript...');
    execSync('npx tsc', { cwd: SCRIPTS_ROOT, stdio: 'pipe' });
    console.error('[init] 编译完成');
  } catch {
    return {
      success: false,
      error: 'BUILD_FAILED',
      message: '脚本编译失败，请确认 TypeScript 依赖已安装后重试',
    };
  }
  return null;
}

function checkEnv(): InitResult | null {
  const envFile = path.join(SCRIPTS_ROOT, '.env');
  if (fs.existsSync(envFile)) return null;
  try {
    fs.writeFileSync(envFile, '# 调试环境变量：test|st|prod\nENV=prod\n', 'utf-8');
    console.error('[init] 已写入默认 scripts/.env（ENV=prod）');
  } catch {
    return {
      success: false,
      error: 'ENV_NOT_FOUND',
      message: '未找到 scripts/.env 且无法自动创建，请手动写入 ENV=prod',
    };
  }
  return null;
}

function loadCliGuard(): void {
  try {
    const require = createRequire(import.meta.url);
    require('@sec/cliguard');
    console.error('[init] CLIGuard 已加载');
  } catch (e) {
    console.error('[init] CLIGuard 加载失败（不影响业务，签名缺失由后端风控兜底）:',
      e instanceof Error ? e.message : e);
  }
}

export async function init(_args: Record<string, unknown>): Promise<InitResult> {
  const checks: Array<() => InitResult | null> = [checkNode, checkNpm, checkInstall, checkBuild, checkEnv];
  for (const check of checks) {
    const err = check();
    if (err) return err;
  }

  loadCliGuard();

  return {
    success: true,
    scripts_dir: SCRIPTS_ROOT,
    node: process.version,
  };
}
