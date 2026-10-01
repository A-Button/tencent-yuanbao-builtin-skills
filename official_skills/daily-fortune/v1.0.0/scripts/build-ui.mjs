import { build } from "esbuild";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const temporary = await mkdtemp(join(tmpdir(), "daily-fortune-ui-"));
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
    readFile(join(appRoot, "assets", "ui", "index.template"), "utf8"),
    readFile(bridgePath, "utf8"),
  ]);

  // 函数形式替换：$& / $1 在字符串形式下会被当成替换模式；</script 必须转义，否则提前闭合标签。
  const html = template.replace(
    "/*__MCP_BRIDGE__*/",
    () => bridge.replaceAll("</script", "<\\/script"),
  );

  if (html.includes("/*__MCP_BRIDGE__*/")) {
    throw new Error("UI build placeholder was not replaced");
  }

  await writeFile(join(appRoot, "assets", "ui", "index.html"), html, "utf8");
  console.log("Built assets/ui/index.html");
} finally {
  await rm(temporary, { recursive: true, force: true });
}
