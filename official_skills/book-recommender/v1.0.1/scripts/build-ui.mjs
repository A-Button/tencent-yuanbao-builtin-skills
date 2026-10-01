// 把 ui_bridge_entry.js 打成 IIFE，替换 workspace.template 里的占位符，产出单文件 workspace.html。
// 单文件是硬要求：Host 通过 GET /app/resource 整份取走 HTML 塞进 iframe，页面没有同源
// 服务器可以再去取任何外部资源，CSP 也会拦掉 CDN。第三方库同样必须内联进来。
import { build } from "esbuild";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const temporary = await mkdtemp(join(tmpdir(), "book-recommender-ui-"));
const bridgePath = join(temporary, "bridge.js");

try {
  await build({
    entryPoints: [join(appRoot, "scripts", "ui_bridge_entry.js")],
    outfile: bridgePath,
    bundle: true,
    format: "iife",
    platform: "browser",
    target: ["es2022"],
    minify: true,
    legalComments: "none",
  });

  const [template, bridge] = await Promise.all([
    readFile(join(appRoot, "assets", "ui", "workspace.template"), "utf8"),
    readFile(bridgePath, "utf8"),
  ]);

  // 用函数形式做替换：bridge 里的 $& $1 等序列在字符串形式下会被当成替换模式。
  // </script 必须转义，否则 bundle 里的字面量会提前闭合 <script> 标签。
  const html = template.replace(
    "/*__MCP_BRIDGE__*/",
    () => bridge.replaceAll("</script", "<\\/script"),
  );

  if (html.includes("/*__MCP_BRIDGE__*/")) {
    throw new Error("UI build placeholder was not replaced");
  }

  await writeFile(join(appRoot, "assets", "ui", "workspace.html"), html, "utf8");
  console.log("Built assets/ui/workspace.html");
} finally {
  await rm(temporary, { recursive: true, force: true });
}
