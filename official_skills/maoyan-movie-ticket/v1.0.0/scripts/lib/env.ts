/**
 * 统一 .env 加载模块
 *
 * 从本文件同目录读取 .env，注入 process.env（已存在的环境变量不覆盖）。
 * 作为唯一的环境加载入口，run.ts 和各 api 脚本通过 import 副作用触发加载。
 *
 * 用法：在脚本入口 `import './lib/env.js'`（或 `import '../lib/env.js'`）即可。
 */

import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { SCRIPTS_ROOT } from './scripts-root.js';

const envFile = path.join(SCRIPTS_ROOT, '.env');

if (existsSync(envFile)) {
  for (const line of readFileSync(envFile, 'utf8').split('\n')) {
    const m = line.match(/^([A-Z_]+)=(.*)$/);
    if (m && !process.env[m[1]]) {
      process.env[m[1]] = m[2].replace(/^["']|["']$/g, '');
    }
  }
}
