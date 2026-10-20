"""Package reviewed AI PC code, per-plant employee updates and transfer instructions."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from install_code_update import FILES

BASE=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='New output folder')
    parser.add_argument('--employee-files',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise SystemExit('Choose a new output directory; existing files will not be replaced.')
    pc=BASE/'ai-pc'
    if not (pc/'dist/index.html').is_file(): raise SystemExit('Build the frontend first.')
    sources={name:pc/name for name in FILES if name!='compose.new-plant.example.yaml' and (pc/name).is_file()}
    for tree in ('src','public','dist'):
        sources.update({p.relative_to(pc).as_posix():p for p in sorted((pc/tree).rglob('*')) if p.is_file()})
    args.output.mkdir(parents=True,mode=0o700)
    archive=args.output/'AI-PC-Code-Update.zip'
    hashes={}
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for name,path in sorted(sources.items()):
            raw=path.read_bytes();z.writestr(name,raw);hashes[name]=hashlib.sha256(raw).hexdigest()
        z.writestr('compose.new-plant.example.yaml',(pc/'compose.yaml').read_bytes())
        hashes['compose.new-plant.example.yaml']=hashlib.sha256((pc/'compose.yaml').read_bytes()).hexdigest()
        z.writestr('update-manifest.json',json.dumps({'format':'sgi-code-update-v1','files':hashes},indent=2))
    shutil.copy2(BASE/'tools/install_code_update.py',args.output/'install_code_update.py')
    shutil.copy2(BASE/'tools/prepare_employee_update.py',args.output/'prepare_employee_update.py')
    shutil.copy2(pc/'PLANT-ROLLOUT.md',args.output/'START-HERE.md')
    private=args.output/'employee-files-PRIVATE'
    private.mkdir(mode=0o700)
    for p in args.employee_files.glob('employees-*.json'): shutil.copy2(p,private/p.name)
    paths=[p for p in args.output.rglob('*') if p.is_file()]
    (args.output/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(args.output).as_posix()+'\n' for p in sorted(paths)),encoding='utf-8')
    print(json.dumps({'output':str(args.output.resolve()),'code_files':len(hashes),'employee_files':len(list(private.glob('*.json')))},indent=2))


if __name__=='__main__': main()
