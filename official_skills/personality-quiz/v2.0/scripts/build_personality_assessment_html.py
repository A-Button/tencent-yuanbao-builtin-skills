#!/usr/bin/env python3
"""Compile the new MBTI interface into the existing offline artifact contract."""
from __future__ import annotations
import argparse, base64, json, struct, uuid
from pathlib import Path
from assessment_data import (BuildError, EXPECTED_TYPE_CODES, load_bank, load_type_labels, validate_bank, safe_script_json, atomic_write)
ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'assets'
INSTRUMENTS={
 'quick':{'version_id':'quick','transfer_id':'mini_ipip_20_v1','id':'mini_ipip_20','bank':ROOT/'scripts/mini_ipip_items.json','expected_name':'Mini-IPIP-20','expected_version':'donnellan-2006','items':20,'items_per_trait':4,'duration':'约4分钟'},
 'deep':{'version_id':'deep','transfer_id':'ipip_50_v1','id':'ipip_big_five_50','bank':ROOT/'scripts/ipip_big_five_50_items.json','expected_name':'IPIP-50-Big-Five-Factor-Markers','expected_version':'goldberg-1992-ipip-50','items':50,'items_per_trait':10,'duration':'约8—10分钟'}
}
PROFILE_FIELDS=('summary','core','strengths','watch','communication','decision','work','team','relationship','growth','reflection')
def validate_profiles(catalog):
 if not isinstance(catalog,dict) or set(catalog.get('types',{}))!=EXPECTED_TYPE_CODES: raise BuildError('新版报告必须包含16型')
 for code,entry in catalog['types'].items():
  if set(entry)!=set(PROFILE_FIELDS): raise BuildError(f'报告字段缺失：{code}')
  for key,value in entry.items():
   if not isinstance(value,str) or not 12<=len(value)<=400 or '<' in value or '>' in value: raise BuildError(f'报告正文无效：{code}.{key}')
def svg_uri(name,color):
 text=(ASSETS/name).read_text().replace('currentColor',color)
 return 'data:image/svg+xml;base64,'+base64.b64encode(text.encode()).decode()
def payload_for(version):
 c=INSTRUMENTS[version];bank=load_bank(c['bank']);validate_bank(bank,c)
 labels=load_type_labels(ROOT/'scripts/mbti_type_labels.json')
 catalog=json.loads((ROOT/'scripts/mbti_report_profiles.json').read_text());validate_profiles(catalog)
 art_manifest=json.loads((ASSETS/'report-illustrations.json').read_text())
 def art_uri(filename):
  if not isinstance(filename,str): raise BuildError('报告插画文件名无效')
  source=ASSETS/filename
  p=source.resolve()
  if not p.is_relative_to(ASSETS.resolve()) or p.suffix.lower() not in ('.png','.webp') or source.is_symlink() or not p.is_file(): raise BuildError('报告插画路径或格式无效')
  mime='image/png' if p.suffix.lower()=='.png' else 'image/webp'
  return 'data:'+mime+';base64,'+base64.b64encode(p.read_bytes()).decode()
 mascot_art=art_manifest.get('mascots',{})
 type_files=mascot_art.get('type_files',{})
 if not isinstance(type_files,dict) or not set(type_files).issubset(EXPECTED_TYPE_CODES): raise BuildError('报告人物图映射无效')
 mascots={code:{'src':art_uri(type_files.get(code,mascot_art.get('default_file'))),'alt':''} for code in sorted(EXPECTED_TYPE_CODES)}
 slots=art_manifest.get('slots',{})
 if set(slots)!={'communication','decision','growth','reflection'}: raise BuildError('报告插画位置不完整')
 art={slot:{'src':art_uri(entry.get('file'))} for slot,entry in slots.items()}
 return {'schema_version':'1.0.0','assessment_version':'mbti-redesign-1','version_id':version,'transfer_id':c['transfer_id'],'item_count':c['items'],'items_per_trait':c['items_per_trait'],'duration':c['duration'],'response_scale':bank['response_scale']['zh-CN'],'type_labels':labels,'yuanbao_mascots':mascots,'report_profiles':catalog,'illustrations':art,'icons':{'check':svg_uri('check.svg','#ffffff'),'pinPink':svg_uri('pin.svg','#f287a0'),'pinGold':svg_uri('pin.svg','#edba38'),'pinBlue':svg_uri('pin.svg','#88aef0')},'items':[{'id':i['id'],'trait':i['trait'],'reverse':i['reverse'],'text':i['zh_cn_draft']} for i in bank['items']]}
def build_document(version):
 font=(ASSETS/'vendor/BarlowCondensed-ExtraBoldItalic.ttf').read_bytes()
 if len(font)<12 or font[:4]!=b'\x00\x01\x00\x00':raise BuildError('离线字体无效')
 for i in range(struct.unpack_from('>H',font,4)[0]):
  _,_,offset,length=struct.unpack_from('>4sIII',font,12+16*i)
  if offset+length>len(font):raise BuildError('离线字体不完整')
 data=payload_for(version)
 data['artifact_id']=str(uuid.uuid4())
 tokens={'/*{{ASSESSMENT_CSS}}*/':("@font-face{font-family:'MBTI Display';src:url(data:font/ttf;base64,"+base64.b64encode((ASSETS/'vendor/BarlowCondensed-ExtraBoldItalic.ttf').read_bytes()).decode()+") format('truetype');font-weight:800;font-style:italic;font-display:swap;}\n"+(ASSETS/'mbti-assessment.css').read_text()),'/*{{ASSESSMENT_PAYLOAD}}*/':safe_script_json(data),'/*{{SCORING_CORE}}*/':(ASSETS/'personality-scoring-core.js').read_text(),'/*{{REPORT_MODEL}}*/':(ASSETS/'mbti-report-model.js').read_text(),'/*{{RESULT_IMAGE}}*/':(ASSETS/'result-image.js').read_text(),'/*{{STATE_CORE}}*/':(ASSETS/'mbti-state.js').read_text(),'/*{{POSTER_VENDOR}}*/':(ASSETS/'vendor/html2canvas.min.js').read_text(),'/*{{ASSESSMENT_APP}}*/':(ASSETS/'mbti-assessment.js').read_text()}
 doc=(ASSETS/'personality-assessment-shell.template').read_text()
 for token,value in tokens.items():
  if doc.count(token)!=1:raise BuildError('模板占位符不唯一：'+token)
  doc=doc.replace(token,value)
 if len(doc.encode())>2_000_000:raise BuildError('产物超过离线HTML大小上限，请压缩插画')
 return doc

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--version',choices=INSTRUMENTS,default='deep');parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
 try:
  doc=build_document(args.version)
  from verify_personality_assessment_html import verify_document
  verify_document(doc)
  atomic_write(args.output,doc)
  print(json.dumps({'ok':True,'output':str(args.output),'version':args.version,'items':INSTRUMENTS[args.version]['items'],'offline':True},ensure_ascii=False));return 0
 except Exception as e:
  print(json.dumps({'ok':False,'error':'E_PERSONALITY_ASSESSMENT_HTML','message':str(e)},ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
