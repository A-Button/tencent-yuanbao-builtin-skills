// Set PLAYWRIGHT_MODULE and PLAYWRIGHT_BROWSERS_PATH to use a local WebKit installation.
const {webkit}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'..'),outputs=path.resolve(root,'../测试产物');
const source=fs.readFileSync(path.join(root,'assets/result-image.js'),'utf8');
const server=http.createServer((req,res)=>{
 res.setHeader('Content-Type','text/html; charset=utf-8');
 if(req.url==='/fixture.html'){res.end('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;min-height:4000px}#mount{width:calc(100% - 24px);margin:auto}img{width:2500px!important}</style><button id="trigger">展开</button><div id="mount"></div>');return;}
 try{const file=path.resolve(outputs,decodeURIComponent(req.url.split('?')[0].slice(1)));if(!file.startsWith(outputs+path.sep))throw Error();res.end(fs.readFileSync(file));}catch{res.writeHead(404);res.end();}
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}`;
 const browser=await webkit.launch({headless:true}),results=[];
 try{
  const context=await browser.newContext({viewport:{width:390,height:740},isMobile:true,hasTouch:true,reducedMotion:'reduce',deviceScaleFactor:1,userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'});
  await context.addInitScript(()=>{window.nativeShareCalls=0;Object.defineProperty(navigator,'share',{configurable:true,value:()=>{nativeShareCalls++;throw new Error('Native sharing unavailable');}});});
  const page=await context.newPage();page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/fixture.html');await page.addScriptTag({content:source});
  await page.evaluate(async()=>{
   const canvas=document.createElement('canvas');canvas.width=1080;canvas.height=4000;const c=canvas.getContext('2d');c.fillStyle='#142419';c.fillRect(0,0,1080,4000);window.poster=canvas.toDataURL('image/png');window.scrollTo(0,600);
   await ResultImage.show({container:document.getElementById('mount'),url:poster,trigger:document.getElementById('trigger')});
  });
  for(const size of [{width:390,height:740},{width:320,height:568},{width:844,height:390},{width:768,height:1024},{width:320,height:256}]){
   await page.setViewportSize(size);await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
   const box=await page.locator('[data-result-image] img').boundingBox();assert(box.x>=0&&box.x+box.width<=size.width+1);assert(box.height>box.width);
   assert.equal(await page.locator('dialog[open],[role=dialog]').count(),1);assert.equal(await page.evaluate(()=>getComputedStyle(document.body).position),'fixed');
   assert.equal(await page.evaluate(()=>nativeShareCalls),0);const footer=await page.locator('[data-result-image] footer').boundingBox();const close=await page.getByRole('button',{name:'关闭图片预览'}).boundingBox();assert(footer.y>=0&&footer.y+footer.height<=size.height+1);assert(close.y>=0&&close.y+close.height<=size.height+1);results.push({dialogLayout:size,ok:true});
  }
  assert(await page.locator('[data-result-image] .download').isHidden());
  assert(await page.locator('[data-result-image] img').evaluate(img=>{
   const event=new Event('contextmenu',{bubbles:true,cancelable:true,composed:true});return img.dispatchEvent(event)&&!event.defaultPrevented;
  }));
  await page.getByRole('button',{name:'关闭图片预览'}).click();assert.equal(await page.locator('[data-result-image]').count(),0);assert.equal(await page.evaluate(()=>scrollY),600);assert.equal(await page.evaluate(()=>document.getElementById('trigger').inert),false);
  await page.evaluate(async()=>{await ResultImage.show({container:document.getElementById('mount'),url:poster});await ResultImage.show({container:document.getElementById('mount'),url:poster});});
  assert.equal(await page.locator('[data-result-image]').count(),1);
  await page.evaluate(()=>ResultImage.clear(document.getElementById('mount')));
  assert.equal(await page.locator('[data-result-image]').count(),0);
  await page.evaluate(async()=>{
    try{await ResultImage.show({container:document.getElementById('mount'),url:'data:image/png;base64,invalid'});}catch{}
  });
  assert.match(await page.locator('[data-result-image] .status').textContent(),/失败/);
  await page.evaluate(()=>ResultImage.show({container:document.getElementById('mount'),url:poster}));
  assert(await page.locator('[data-result-image] img').isVisible());results.push({longPressNotBlocked:true,noNativeCalls:true,closeReuseRetry:true,scrollRestore:true});
  await page.setViewportSize({width:390,height:740});
  await page.goto(base+'/塔罗.html');
  for(let i=0;i<3;i++){const card=page.locator('.wheel-card:not(:disabled)').first();await card.waitFor();await card.press('Enter');await page.waitForFunction(n=>document.querySelectorAll('.slot.has-card').length>=n,i+1);}
  const entry=page.getByRole('button',{name:'分享结果图片',exact:true});await entry.click();await page.locator('[data-result-image] img').waitFor({state:'visible'});
  assert.equal(await page.locator('[role=dialog],dialog[open]').count(),1);assert.equal(decodeURI(page.url()),base+'/塔罗.html');assert.equal(await page.evaluate(()=>nativeShareCalls),0);
  await page.screenshot({path:path.join(outputs,'塔罗-手机分享弹窗.png')});
  const captions=await page.locator('.card-caption').allTextContents();
  const snapshot=await page.evaluate(()=>{
    const config=JSON.parse(document.getElementById('tarot-standalone-config').textContent),v=JSON.parse(localStorage.getItem('yuanbao:tarot:state:v1:'+config.artifactId));
    return{v:1,kind:'tarot-result',artifactId:config.artifactId,cards:v.used.map(i=>({id:v.deck[i][0],reversed:Boolean(v.deck[i][1])}))};
  });
  await page.reload();await entry.waitFor();assert.deepEqual(await page.locator('.card-caption').allTextContents(),captions);
  const recipient=await browser.newContext({viewport:{width:390,height:740},reducedMotion:'reduce'});const received=await recipient.newPage();
  await received.goto(base+'/塔罗.html');await received.locator('.wheel-card:not(:disabled)').first().waitFor();assert.equal(await received.locator('.slot.has-card').count(),0);
  const snapshotPage=await recipient.newPage();await snapshotPage.goto(base+'/塔罗.html#tarot-state='+Buffer.from(JSON.stringify(snapshot)).toString('base64url'));await snapshotPage.getByRole('button',{name:'分享结果图片',exact:true}).waitFor();assert.deepEqual(await snapshotPage.locator('.card-caption').allTextContents(),captions);
  await recipient.close();results.push({sameBrowserRestore:true,plainLinkStartsFresh:true,explicitSnapshotRestoresSameCards:true});
  await entry.click();await page.locator('[data-result-image] img').waitFor({state:'visible'});await page.getByRole('button',{name:'关闭图片预览'}).click();await page.getByRole('button',{name:'再抽一次',exact:true}).click();await page.locator('.wheel-card:not(:disabled)').first().waitFor();assert.equal(await page.locator('[data-result-image]').count(),0);results.push({tarotDialogFlow:true,resetClearsImage:true});
  await page.goto(base+'/星盘.html');await page.locator('#zodiac-save-image').click();await page.locator('[data-result-image] img').waitFor({state:'visible'});
  assert.equal(await page.evaluate(()=>nativeShareCalls),0);assert.equal(await page.locator('[role=dialog],dialog[open]').count(),1);assert.equal(decodeURI(page.url()),base+'/星盘.html');await page.screenshot({path:path.join(outputs,'星盘-手机分享弹窗.png')});
  await page.getByRole('button',{name:'关闭图片预览'}).click();await page.locator('#zodiac-save-image').click();await page.locator('[data-result-image] img').waitFor({state:'visible'});results.push({zodiacDialogFlow:true});
  for(const count of [20,50]){
   await page.goto(base+`/MBTI-${count}题.html`);
   const answers=await page.evaluate(()=>JSON.parse(document.querySelector('#assessment-data').textContent).items.map(i=>i.reverse?1:5));
   for(let i=1;i<=count;i++){await page.locator('#question-'+i+'.active').waitFor();await page.locator('#question-'+i+' .option[data-value="'+answers[i-1]+'"]').press('Enter');}
   await page.locator('#generatePoster').click();await page.locator('[data-result-image] img').waitFor({state:'visible'});
   assert.equal(await page.evaluate(()=>nativeShareCalls),0);assert.equal(await page.locator('[role=dialog],dialog[open]').count(),1);if(count===20)await page.screenshot({path:path.join(outputs,'MBTI-手机分享弹窗.png')});
   const src=await page.locator('[data-result-image] img').getAttribute('src');await page.getByRole('button',{name:'关闭图片预览'}).click();await page.locator('#generatePoster').click();await page.locator('[data-result-image] img').waitFor({state:'visible'});assert.equal(await page.locator('[data-result-image] img').getAttribute('src'),src);
   await page.getByRole('button',{name:'关闭图片预览'}).click();await page.locator('#reviewAnswers').click();await page.locator('.question.active .option[aria-checked="false"]').first().press('Enter');assert.equal(await page.locator('[data-result-image]').count(),0);
   results.push({mbtiQuestions:count,dialogFlow:true,reuseAndClear:true});
  }
  const desktop=await browser.newContext({viewport:{width:1280,height:800}});const dp=await desktop.newPage();await dp.goto(base+'/fixture.html');await dp.addScriptTag({content:source});await dp.evaluate(async()=>{const c=document.createElement('canvas');c.width=20;c.height=20;await ResultImage.show({container:document.getElementById('mount'),url:c.toDataURL('image/png'),name:'result.png'});});const pending=dp.waitForEvent('download');await dp.getByRole('button',{name:'下载图片'}).click();assert.equal((await pending).suggestedFilename(),'result.png');assert.equal(dp.url(),base+'/fixture.html');await dp.goto(base+'/塔罗.html#tarot-state='+Buffer.from(JSON.stringify(snapshot)).toString('base64url'));await dp.getByRole('button',{name:'分享结果图片',exact:true}).click();await dp.locator('[data-result-image] img').waitFor({state:'visible'});assert(await dp.getByRole('button',{name:'下载图片',exact:true}).isVisible());assert.match(await dp.locator('[data-result-image] .hint').textContent(),/右键/);await dp.screenshot({path:path.join(outputs,'塔罗-PC分享弹窗.png')});await dp.getByRole('button',{name:'关闭图片预览'}).click();await desktop.close();results.push({desktopDownload:true});
  assert.deepEqual(errors,[]);await context.close();
 }finally{await browser.close();server.close();}
 fs.writeFileSync(path.join(outputs,'图片弹窗回归.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
