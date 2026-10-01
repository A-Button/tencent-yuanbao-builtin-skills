#!/usr/bin/env python3
"""Validate data, offline resources and structure of the rebuilt MBTI page."""
from __future__ import annotations
import argparse,base64,json,re,sys,uuid
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from assessment_data import EXPECTED_TYPE_CODES,TRAITS
from webp_validation import decode_webp_size

class VerifyError(ValueError):pass
def report_image_size(src):
 if not isinstance(src,str):raise VerifyError('报告图片地址无效')
 if src.startswith('data:image/webp;base64,'):
  return decode_webp_size(base64.b64decode(src.split(',',1)[1],validate=True))
 if not src.startswith('data:image/png;base64,'):raise VerifyError('报告图片格式无效')
 content=base64.b64decode(src.split(',',1)[1],validate=True)
 if not content.startswith(b'\x89PNG\r\n\x1a\n'):raise VerifyError('PNG 文件头无效')
 try:
  from PIL import Image
  with Image.open(BytesIO(content)) as image:
   if image.format!='PNG':raise VerifyError('报告图片不是 PNG')
   size=image.size;image.verify()
  with Image.open(BytesIO(content)) as image:
   if image.format!='PNG' or image.size!=size:raise VerifyError('PNG 元数据不一致')
   image.load()
  return size
 except (OSError,SyntaxError) as error:raise VerifyError('PNG 无法完整解码') from error
class Document(HTMLParser):
 def __init__(self):super().__init__();self.ids=[];self.external=[];self.payload='';self.in_payload=False;self.ready=False;self.csp='';self.scripts=[];self.in_script=False;self.current_script=''
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id'in a:self.ids.append(a['id'])
  if tag=='main' and a.get('data-assessment-build')=='ready':self.ready=True
  if tag=='meta' and a.get('http-equiv')=='Content-Security-Policy':self.csp=a.get('content','')
  if tag=='script':self.in_script=True;self.current_script='';self.in_payload=a.get('id')=='assessment-data'
  for name in ('src','href'):
   if name in a and a[name] and not a[name].startswith(('data:','blob:','#')):self.external.append(a[name])
 def handle_data(self,data):
  if self.in_payload:self.payload+=data
  if self.in_script:self.current_script+=data
 def handle_endtag(self,tag):
  if tag=='script':
   if not self.in_payload:self.scripts.append(self.current_script)
   self.in_payload=False;self.in_script=False

def verify_document(text):
 if len(text.encode())>2_000_000:raise VerifyError('待交付页面异常过大')
 if '/*{{'in text:raise VerifyError('不能交付源模板')
 doc=Document();doc.feed(text)
 if doc.external:raise VerifyError('页面包含外部资源')
 if not doc.ready or len(doc.ids)!=len(set(doc.ids)):raise VerifyError('页面结构无效或ID重复')
 if not {'runtimeNotice','questionScreen','questions','resultScreen','reportCapture','report','copyDialog','assessment-data'}.issubset(doc.ids):raise VerifyError('页面缺少必要交互入口')
 if "connect-src 'none'" not in doc.csp:raise VerifyError('页面必须禁止网络连接')
 p=json.loads(doc.payload)
 version=p.get('version_id');n={'quick':20,'deep':50}.get(version)
 if n is None or p.get('item_count')!=n or p.get('assessment_version')!='mbti-redesign-1':raise VerifyError('页面版本或题数无效')
 if p.get('transfer_id')!={'quick':'mini_ipip_20_v1','deep':'ipip_50_v1'}[version]:raise VerifyError('复制结果版本无效')
 try:uuid.UUID(p.get('artifact_id',''))
 except (ValueError,TypeError,AttributeError) as error:raise VerifyError('页面缺少独立状态标识') from error
 items=p.get('items',[])
 if len(items)!=n or [i.get('id') for i in items]!=list(range(1,n+1)):raise VerifyError('题目不完整')
 counts={t:0 for t in TRAITS}
 for i in items:
  if i.get('trait') not in counts or not isinstance(i.get('reverse'),bool) or not isinstance(i.get('text'),str) or '你'not in i['text'] or '我'in i['text']:raise VerifyError('题目维度、计分键或文本无效')
  counts[i['trait']]+=1
 if set(counts.values())!={n//5}:raise VerifyError('维度题数不平衡')
 # Check against the actual bank, so a changed reverse key cannot pass by shape alone.
 bank=json.loads((Path(__file__).parent/('mini_ipip_items.json' if version=='quick' else 'ipip_big_five_50_items.json')).read_text())
 expected=[{'id':i['id'],'trait':i['trait'],'reverse':i['reverse'],'text':i['zh_cn_draft']} for i in bank['items']]
 if items!=expected or p.get('response_scale')!=bank['response_scale']['zh-CN']:raise VerifyError('题库内容或量尺与源文件不一致')
 from build_personality_assessment_html import validate_profiles
 validate_profiles(p.get('report_profiles'))
 mascots=p.get('yuanbao_mascots',{})
 if set(mascots)!=EXPECTED_TYPE_CODES:raise VerifyError('元宝角色不完整')
 for code,asset in mascots.items():
  try:width,height=report_image_size(asset['src'])
  except (ValueError,KeyError,TypeError) as error:raise VerifyError('元宝图片无效：'+code) from error
  if not 64<=width<=2048 or not 64<=height<=2048:raise VerifyError('元宝图片尺寸无效：'+code)
 illustrations=p.get('illustrations',{})
 if set(illustrations)!={'communication','decision','growth','reflection'}:raise VerifyError('报告插画不完整')
 for slot,asset in illustrations.items():
  try:width,height=report_image_size(asset['src'])
  except (ValueError,KeyError,TypeError) as error:raise VerifyError('报告插画无效：'+slot) from error
  if not 64<=width<=2048 or not 64<=height<=2048:raise VerifyError('报告插画尺寸无效：'+slot)
 core=(Path(__file__).parents[1]/'assets/personality-scoring-core.js').read_text()
 if core not in doc.scripts:raise VerifyError('计分与复制核心不一致')
 persistence=(Path(__file__).parents[1]/'assets/mbti-state.js').read_text()
 if persistence not in doc.scripts:raise VerifyError('状态恢复核心不一致')
 result_image=(Path(__file__).parents[1]/'assets/result-image.js').read_text()
 if result_image not in doc.scripts:raise VerifyError('结果图片组件不一致')
 app=doc.scripts[-1]
 if re.search(r'\b(localStorage|sessionStorage|indexedDB|fetch|XMLHttpRequest)\b',app):raise VerifyError('页面应用绕过状态核心或发起网络请求')
 if re.search(r'\b(sessionStorage|indexedDB|fetch|XMLHttpRequest)\b',persistence):raise VerifyError('状态核心包含其他存储或网络接口')
 return {'ok':True,'version':version,'items':n}
def verify(path):
 if path.suffix.lower()!='.html':raise VerifyError('只能交付已生成的.html文件')
 r=verify_document(path.read_text());r['path']=str(path.resolve());return r
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('path',type=Path);a=parser.parse_args()
 try:print(json.dumps(verify(a.path),ensure_ascii=False));return 0
 except (ValueError,KeyError,TypeError,OSError) as e:print(json.dumps({'ok':False,'error':'E_ASSESSMENT_DELIVERY','message':str(e)},ensure_ascii=False),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
