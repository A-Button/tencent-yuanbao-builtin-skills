import { readFile } from "node:fs/promises";
import { JSDOM, VirtualConsole } from "jsdom";
import { execFileSync } from "node:child_process";
const root = new URL("..", import.meta.url).pathname;
const html = await readFile(root + "assets/ui/index.html", "utf8");
// 用真实引擎产出 16 组数据
const out = execFileSync("node", [root + "scripts/engine.mjs", '{"operation":"get_card"}'], {encoding:"utf8"});
const DATA = JSON.parse(out).data;
const ctx = { theme:"light", displayMode:"inline", availableDisplayModes:["inline"], locale:"zh-CN", safeAreaInsets:{top:0,right:0,bottom:0,left:0} };

async function boot(label, mode) {
  const calls=[]; let win, host;
  const vc=new VirtualConsole(); const errs=[];
  vc.on("jsdomError",e=>errs.push(e.message)); vc.on("error",e=>errs.push(String(e)));
  const dom=new JSDOM(html,{runScripts:"dangerously",url:"https://app.local/assets/ui/index.html",pretendToBeVisual:true,virtualConsole:vc,
    beforeParse(w){ win=w;
      host={postMessage(m){
        if(m?.method==="ui/initialize"){ queueMicrotask(()=>w.dispatchEvent(new w.MessageEvent("message",{source:host,data:{jsonrpc:"2.0",id:m.id,result:{protocolVersion:"2026-01-26",hostInfo:{name:"h",version:"1"},hostCapabilities:{},hostContext:ctx}}}))); return; }
        if(m?.method==="tools/call"){
          calls.push(m.params.arguments);
          if(mode==="hang") return;                       // 宿主完全不响应
          if(mode==="firstOnly" && calls.length>1) return; // 首次成功，之后不响应（用户场景）
          queueMicrotask(()=>{
            const res = { jsonrpc:"2.0", id:m.id, result:{ content:[], structuredContent:{ phase:"result", data:DATA } } };
            w.dispatchEvent(new w.MessageEvent("message",{ source:host, data:res }));
          });
        }
      }};
      Object.defineProperty(w,"parent",{value:host,configurable:true});
      w.ResizeObserver=class{observe(){}unobserve(){}disconnect(){}};
      w.requestAnimationFrame=()=>0; w.cancelAnimationFrame=()=>{};
    }});
  await new Promise(r=>setTimeout(r,300));
  // 宿主首屏推送结果
  const d=win.document;
  console.log(`  ${label}`);
  const read=()=>({ title:d.querySelector(".title")?.textContent, score:d.querySelector(".scoreBox .value")?.textContent,
    insight:[...d.querySelectorAll(".insightTitle, .insight .title, #stage b")].map(e=>e.textContent).slice(0,2).join("|") });
  const q=(sel)=>d.querySelector(sel)?.textContent;
  console.log(`     首屏: 指数 ${q(".scoreBox .value")} | ${q(".title")}`);
  const click=(key)=>{ const b=[...d.querySelectorAll(".seg button")].find(x=>x.dataset.key===key); if(b) b.dispatchEvent(new win.MouseEvent("click",{bubbles:true})); };
  click("week"); await new Promise(r=>setTimeout(r,150));
  console.log(`     点"本周"后: 指数 ${q(".scoreBox .value")} | ${q(".title")}`);
  click("year"); await new Promise(r=>setTimeout(r,150));
  console.log(`     点"今年"后: 指数 ${q(".scoreBox .value")} | ${q(".title")}`);
  click("love"); await new Promise(r=>setTimeout(r,150));
  const insightText=[...d.querySelectorAll("#stage *")].map(e=>e.textContent).find(t=>t&&t.includes("感情"));
  console.log(`     切"感情"后: 解读含"感情"=${!!insightText} → ${insightText?insightText.slice(0,28):"无"}`);
  const lucky=[...d.querySelectorAll("#stage *")].map(e=>e.textContent).find(t=>t&&t.includes("幸运色"));
  console.log(`     幸运色行: ${lucky||"无"}`);
  const switchedLocally = calls.length <= 1 && errs.length === 0;
  console.log(`     宿主收到调用 ${calls.length} 次 | JS错误 ${errs.length} | 本地切换 ${switchedLocally ? "✓" : "✗"}`);
  if (mode !== "hang" && !switchedLocally) process.exitCode = 1;
  console.log();
  dom.window.close();
}
console.log("=== 本地切换验证（真实16组数据）===\n");
await boot("A. 宿主正常", "ok");
await boot("B. 宿主完全不响应", "hang");
await boot("C. 首次成功、之后不响应（你的场景）", "firstOnly");
