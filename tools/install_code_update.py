"""Preview/apply a verified code-only AI PC update; preserve plant data/configuration."""
import argparse
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
import tempfile
import uuid
import zipfile

FILES={'attendance_export.py','test_attendance_export.py','server.py','attendance_maintenance.py','test_attendance_maintenance.py','employee_admin.py','testing_operations.py','plant_workflows.py','test_plant_workflows.py','manage.py','import_history.py',
       'test_server.py','test_manage.py','test_employee_admin.py','test_testing_operations.py',
       'requirements.txt','package.json','package-lock.json','index.html','vite.config.js',
       'Dockerfile','.dockerignore','README.md','EMPLOYEE-ADMIN.md','PLANT-ROLLOUT.md','REVIEW-SHIFTS.md','compose.new-plant.example.yaml','data/employees.example.json'}


def allowed(name):
    parts=PurePosixPath(name).parts
    return bool(parts) and '\\' not in name and not name.startswith('/') and '..' not in parts and ':' not in name and (name in FILES or (parts[0] in ('src','public','dist') and len(parts)>1))


def destination(root,name):
    if not allowed(name): raise ValueError('Update includes a forbidden data/configuration path: '+name)
    path=root.joinpath(*PurePosixPath(name).parts)
    if not path.resolve().is_relative_to(root.resolve()): raise ValueError('Update path escapes the target directory.')
    if path.is_symlink(): raise ValueError('Refusing to replace a symlink: '+name)
    return path


def replace(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    previous=path.stat() if path.exists() else None
    fd,temp=tempfile.mkstemp(prefix='.attendance-update-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(raw);out.flush();os.fsync(out.fileno())
        os.chmod(temp,stat.S_IMODE(previous.st_mode) if previous else 0o644)
        if previous and hasattr(os,'chown'):
            os.chown(temp,previous.st_uid,previous.st_gid)
        os.replace(temp,path)
    finally:
        Path(temp).unlink(missing_ok=True)


def install(archive,target,apply=False):
    root=Path(target).resolve()
    if not root.is_dir(): raise ValueError('Target must be an existing AI PC application directory.')
    with zipfile.ZipFile(archive) as z:
        if sum(i.file_size for i in z.infolist())>100_000_000: raise ValueError('Update is too large.')
        names=z.namelist()
        if len(names)!=len(set(names)): raise ValueError('Duplicate archive entries.')
        manifest=json.loads(z.read('update-manifest.json'))
        if manifest.get('format')!='sgi-code-update-v1' or not isinstance(manifest.get('files'),dict): raise ValueError('Invalid update manifest.')
        if set(names)!=set(manifest['files'])|{'update-manifest.json'}: raise ValueError('Unlisted archive contents.')
        payload={}
        for name,sha in manifest['files'].items():
            destination(root,name)
            raw=z.read(name)
            if hashlib.sha256(raw).hexdigest()!=sha: raise ValueError('Checksum mismatch: '+name)
            payload[name]=raw
    changed={name:raw for name,raw in payload.items() if not (name in ('.dockerignore','data/employees.example.json') and destination(root,name).exists()) and (not destination(root,name).is_file() or destination(root,name).read_bytes()!=raw)}
    report={'files_to_update':len(changed),'target':str(root),'applied':False}
    if not apply or not changed: return report
    backup=root/'runtime'/'backups'/('code-before-update-'+str(uuid.uuid4())+'.zip')
    if not backup.resolve().is_relative_to(root): raise ValueError('Backup directory escapes application target.')
    backup.parent.mkdir(parents=True,exist_ok=True)
    originals={name:destination(root,name).read_bytes() if destination(root,name).is_file() else None for name in changed}
    with zipfile.ZipFile(backup,'x',zipfile.ZIP_DEFLATED) as z:
        for name,raw in originals.items():
            if raw is not None: z.writestr(name,raw)
        z.writestr('code-backup-manifest.json',json.dumps({'new_files':[n for n,v in originals.items() if v is None]}))
    written=[]
    try:
        for name,raw in changed.items():
            replace(destination(root,name),raw);written.append(name)
    except Exception:
        for name in reversed(written):
            path=destination(root,name)
            if originals[name] is None: path.unlink(missing_ok=True)
            else: replace(path,originals[name])
        raise
    return {**report,'applied':True,'code_backup':str(backup)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--target',type=Path,required=True)
    parser.add_argument('--apply',action='store_true',help='Use only while the attendance service is stopped')
    args=parser.parse_args()
    try: print(json.dumps(install(args.archive,args.target,args.apply),indent=2))
    except (ValueError,OSError,KeyError,zipfile.BadZipFile) as error: raise SystemExit(str(error))


if __name__=='__main__': main()
