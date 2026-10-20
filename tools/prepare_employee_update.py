"""Read the six-column HR workbook as data; prepare private per-plant imports."""
import argparse
import collections
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile
import xml.etree.ElementTree as ET

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
HEADERS=('Employee#','Name','Company','Base','Department','Job Type')
KEYS=('id','name','company','base','employment_department','job_type')


def extract(path):
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist())>50_000_000:
            raise ValueError('Workbook is too large.')
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            root=ET.fromstring(z.read('xl/sharedStrings.xml'))
            # Shared strings may contain rich text; read only text nodes.
            strings=[''.join(t.text or '' for t in si.findall('.//s:t',NS)) for si in root.findall('s:si',NS)]
        workbook=ET.fromstring(z.read('xl/workbook.xml'))
        sheets=workbook.findall('s:sheets/s:sheet',NS)
        if len(sheets)!=1:
            raise ValueError('Use a workbook containing one employee worksheet.')
        rid=sheets[0].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        rel=next((r for r in rels if r.get('Id')==rid),None)
        if rel is None or rel.get('TargetMode')=='External':
            raise ValueError('Employee worksheet must be inside the workbook.')
        target=rel.get('Target','')
        sheet=target.lstrip('/') if target.startswith('/') else str(PurePosixPath('xl')/target)
        if '..' in PurePosixPath(sheet).parts:
            raise ValueError('Invalid worksheet path.')
        root=ET.fromstring(z.read(sheet))
        rows=[]
        for row in root.findall('s:sheetData/s:row',NS):
            values={}
            for cell in row.findall('s:c',NS):
                col=re.sub(r'\d','',cell.get('r',''))
                if col not in ('A','B','C','D','E','F'): continue
                if cell.find('s:f',NS) is not None:
                    raise ValueError('Employee fields must be values, not formulas.')
                kind=cell.get('t');v=cell.find('s:v',NS)
                if kind=='s': value=strings[int(v.text)] if v is not None else ''
                elif kind=='inlineStr': value=''.join(t.text or '' for t in cell.findall('.//s:t',NS))
                else: value=v.text if v is not None else ''
                values[col]=(value or '').strip()
            if any(values.values()): rows.append([values.get(c,'') for c in 'ABCDEF'])
    if not rows or tuple(rows[0])!=HEADERS:
        raise ValueError('Expected headers: '+', '.join(HEADERS))
    employees=[dict(zip(KEYS,row)) for row in rows[1:]]
    ids=[r['id'] for r in employees]
    if not employees or len(ids)!=len(set(ids)) or any(not v for r in employees for v in r.values()):
        raise ValueError('Missing fields or duplicate employee IDs. Nothing was prepared.')
    for row in employees:
        if not re.fullmatch(r'[A-Za-z0-9-]{1,40}',row['id']): raise ValueError('Invalid employee ID.')
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9 &_.-]{0,79}',row['base']): raise ValueError('Invalid plant location.')
    return employees


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbook',type=Path)
    parser.add_argument('--output',type=Path,required=True,help='New private output directory')
    args=parser.parse_args()
    if args.output.exists(): raise SystemExit('Choose a new output directory; existing files will not be replaced.')
    employees=extract(args.workbook)
    args.output.mkdir(parents=True,mode=0o700)
    sha=hashlib.sha256(args.workbook.read_bytes()).hexdigest()
    groups={'ALL-PLANTS':employees}
    for base in sorted({e['base'] for e in employees}): groups[re.sub(r'[^A-Z0-9]+','-',base).strip('-')]=[e for e in employees if e['base']==base]
    checks=[]
    for label,rows in groups.items():
        name='employees-'+label+'.json'
        path=args.output/name
        path.write_text(json.dumps({'format':'sgi-employees-v1','source_sha256':sha,'employees':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        path.chmod(0o600)
        checks.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+name)
    (args.output/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n',encoding='utf-8')
    print(json.dumps({'employees':len(employees),'locations':dict(collections.Counter(r['base'] for r in employees)),'files':list(groups)},indent=2))


if __name__=='__main__': main()
