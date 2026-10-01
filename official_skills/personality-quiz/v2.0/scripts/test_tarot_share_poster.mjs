import assert from 'node:assert/strict';
import {renderSharePoster, wrapPosterText} from '../assets/tarot-studio-source/share-poster.js';
// Unit coverage for the export path. This does not substitute for browser rendering QA.
const draws=[],rotations=[];
let exported=0;
const ctx={measureText:t=>({width:[...t].length*18}),scale(){},fillRect(){},strokeRect(){},fillText(){},save(){},restore(){},translate(){},rotate:a=>rotations.push(a),drawImage:(image,...rect)=>draws.push({src:image.src,rect})};
globalThis.document={fonts:{load:async()=>[],ready:Promise.resolve()},createElement:()=>({getContext:()=>ctx,toDataURL:()=>{exported++;return 'data:image/png;base64,TEST';}})};
globalThis.Image=class{naturalWidth=400;naturalHeight=700;set src(value){this._src=value;queueMicrotask(()=>value==='bad'?this.onerror():this.onload());}get src(){return this._src;}async decode(){}};
const cards=[{title:'一',text:'这是一段解读。',reversed:false},{title:'二',text:'另一段解读。',reversed:true},{title:'三',text:'最后一段解读。',reversed:false}];
await renderSharePoster(cards,c=>c.title,c=>c.reversed?'逆位':'正位');
assert.deepEqual(draws.map(d=>d.src),['一','二','三']);
assert.deepEqual(rotations,[Math.PI]);
assert.equal(exported,1);
assert.ok(draws.every(d=>d.rect[2]>0&&d.rect[3]>0));
await assert.rejects(renderSharePoster(cards,c=>c.title==='二'?'bad':c.title,()=>''),/failed to load/);
assert.equal(exported,1,'failed image must not produce a partial poster');
assert.equal(wrapPosterText(ctx,'第一行\n第二行',54).join('|'),'第一行|第二行');
console.log(JSON.stringify({ok:true,threeImages:true,reversedRotation:true,missingImageRejects:true,textWrap:true}));
