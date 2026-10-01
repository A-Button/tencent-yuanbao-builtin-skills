/**
 * 统一的 scripts/ 根目录解析。
 *
 * 源码运行（tsx dev）时，本文件在 lib/ 下，上一级就是 scripts/；
 * 预编译到 dist/ 后，本文件在 dist/lib/ 下，需要上两级才到 scripts/。
 *
 * 所有原本用 __dirname + '..' 的地方，统一用 SCRIPTS_ROOT 替代。
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dir = path.dirname(fileURLToPath(import.meta.url));

export const SCRIPTS_ROOT = __dir.endsWith('/dist/lib') || __dir.endsWith('\\dist\\lib')
  ? path.resolve(__dir, '../..')
  : path.resolve(__dir, '..');
