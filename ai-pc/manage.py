"""Local terminal administration for an SSH/Docker installation. No password arguments."""
import argparse
import getpass
import secrets
import uuid
from pathlib import Path
from server import Store, Problem, digest, password_hash

BASE = Path(__file__).resolve().parent


def init_admin(store, password, confirmation):
    if password != confirmation:
        raise ValueError('The passwords did not match. Nothing was changed.')
    if not 12 <= len(password) <= 256:
        raise ValueError('Use an administrator password between 12 and 256 characters.')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM admin').fetchone():
            raise ValueError('Administrator already configured. Log in with the existing password; this command does not reset it.')
        salt = secrets.token_hex(16)
        db.execute('INSERT INTO admin VALUES(1,?,?)',(salt,password_hash(password,salt)))
        store.audit(db,'local-cli','admin_created','admin',None,{'configured':True})
    store.emit()


def create_kiosk(store, name):
    name = name.strip()
    if not name or len(name)>100:
        raise ValueError('Use a kiosk name between 1 and 100 characters.')
    token, device_id = secrets.token_urlsafe(32), str(uuid.uuid4())
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM admin').fetchone():
            raise ValueError('Create the administrator first using init-admin.')
        db.execute('INSERT INTO devices(id,name,token_hash,scope) VALUES(?,?,?,?)',(device_id,name,digest(token),'kiosk'))
        store.audit(db,'local-cli','device_created',device_id,None,{'name':name,'scope':'kiosk'})
    store.emit()
    return token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=str(BASE/'runtime/attendance.sqlite3'))
    commands = parser.add_subparsers(dest='command',required=True)
    commands.add_parser('init-admin',help='Create the first administrator using hidden password prompts')
    kiosk = commands.add_parser('create-kiosk',help='Create a kiosk connection; show its token once')
    kiosk.add_argument('--name',default='Port Klang Pi')
    backup = commands.add_parser('backup',help='Create a consistent database/photo backup')
    backup.add_argument('--output',required=True)
    args = parser.parse_args()
    try:
        store = Store(args.db)
        if args.command=='init-admin':
            init_admin(store,getpass.getpass('New administrator password (12+ characters): '),getpass.getpass('Confirm administrator password: '))
            print('Administrator created. Open the AI PC address from the Pi browser and sign in.')
        elif args.command=='create-kiosk':
            print('Kiosk token (copy privately into configure_kiosk.py; shown once):')
            print(create_kiosk(store,args.name))
        else:
            output=Path(args.output)
            if output.suffix.lower()!='.zip' or output.exists() or output.with_suffix('.sqlite3').exists():
                raise ValueError('Choose a new .zip output path; existing files will not be replaced.')
            store.backup(output)
            print('Private database/photo backup saved to '+str(output))
        return 0
    except (ValueError,Problem,OSError) as exc:
        print('Setup: '+str(exc))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
