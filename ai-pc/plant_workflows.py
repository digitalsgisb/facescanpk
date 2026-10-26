"""Plant shift settings, bulk review acknowledgements and persisted daily clock-outs."""
import hashlib
import json
import re
import threading
import uuid
from datetime import datetime,timedelta,timezone

KL=timezone(timedelta(hours=8))
PENDING_REVIEW="""json_extract(v.result,'$.action')='REVIEW'
 AND NOT EXISTS(SELECT 1 FROM audit a WHERE a.entity_id=v.id AND a.action='scan_reviewed')"""
SIGNATURE="json_array(s.time_in,s.time_out,s.flags)"
ATTENTION_SESSION=f"""((json_array_length(s.flags)>0 AND NOT EXISTS(
 SELECT 1 FROM review_acknowledgements r WHERE r.entity_id=s.id AND r.signature={SIGNATURE})) OR
 (s.time_out IS NULL AND julianday(s.time_in)<julianday(?) AND NOT EXISTS(
 SELECT 1 FROM review_acknowledgements r WHERE r.entity_id=s.id AND r.signature={SIGNATURE} AND r.stale=1)))"""


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def migrate(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS plant_preferences(base TEXT PRIMARY KEY,config TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS board_layouts(base TEXT PRIMARY KEY,config TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS review_acknowledgements(entity_id TEXT PRIMARY KEY,
      signature TEXT NOT NULL,stale INTEGER NOT NULL,actor TEXT NOT NULL,recorded_at TEXT NOT NULL,reason TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS automatic_clockout(id INTEGER PRIMARY KEY CHECK(id=1),
      enabled INTEGER NOT NULL,clock_time TEXT NOT NULL,activated_at TEXT NOT NULL,actor TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS automatic_clockout_runs(run_date TEXT PRIMARY KEY,clock_time TEXT NOT NULL,
      closed INTEGER NOT NULL,completed_at TEXT NOT NULL,backup TEXT);
    ''')


def preferences(db,base):
    row=db.execute('SELECT config FROM plant_preferences WHERE base=?',(base,)).fetchone()
    return json.loads(row['config']) if row else {}


def review_enabled(db,base):
    global_config=preferences(db,'')
    return global_config.get('review_enabled',True) and preferences(db,base).get('review_enabled',True)


def schedule_settings(db,base,defaults):
    local=preferences(db,base)
    return {**defaults,**{k:v for k,v in local.items() if k in ('team_schedules','team_overtime','rotation','schedule_groups')}}


def schedule(db,sid,base=''):
    row=db.execute('SELECT * FROM schedules WHERE id=?',(sid,)).fetchone()
    if not row:return None
    return {**dict(row),**preferences(db,base).get('schedules',{}).get(sid,{})}


def scope(assigned,requested,Problem):
    if requested is None:return assigned
    if not isinstance(requested,str) or (requested and not re.fullmatch(r'[A-Z0-9][A-Z0-9 &_.-]{0,79}',requested)):
        raise Problem('Choose a plant.')
    if assigned and requested!=assigned:raise Problem('This account manages its own plant only.',403)
    return requested


def board_layout(db,base):
    row=db.execute('SELECT config FROM board_layouts WHERE base=?',(base,)).fetchone()
    config=json.loads(row['config']) if row else {}
    return {'layout':config,'version':hashlib.sha256(encoded(config).encode()).hexdigest()}


def save_board_layout(store,db,base,data,actor,Problem):
    old=board_layout(db,base)
    if data.get('version')!=old['version']:raise Problem('Layout changed on another display. Cancel to load the latest layout.',409)
    config=data.get('layout')
    allowed={'enabled','columns','gap','cardWidth','cardHeight','photoSize','fontSize','sort','groups','order','cards','cardOrder'}
    if not isinstance(config,dict) or set(config)-allowed:raise Problem('Invalid board layout.')
    if type(config.get('enabled')) is not bool:raise Problem('Choose whether the custom grid is enabled.')
    for key,low,high in [('columns',1,12),('gap',0,32),('cardWidth',120,360),('cardHeight',52,160),('photoSize',24,100),('fontSize',10,24)]:
        if type(config.get(key)) is not int or not low<=config[key]<=high:raise Problem('Invalid layout size: '+key)
    if config['photoSize']>config['cardHeight']-12 or config['fontSize']>(config['cardHeight']-12)//3:raise Problem('Photo or text exceeds card height.')
    if config.get('sort') not in ('saved','position','name','status','manual','team'):raise Problem('Invalid employee sort.')
    order=config.get('order');groups=config.get('groups')
    if not isinstance(order,list) or len(order)>300 or any(not isinstance(x,str) or len(x)>240 for x in order) or len(set(order))!=len(order):raise Problem('Invalid group order.')
    if not isinstance(groups,dict) or len(groups)>300:raise Problem('Invalid layout groups.')
    for name,group in groups.items():
        if not isinstance(name,str) or len(name)>240 or not isinstance(group,dict) or set(group)-{'span','height','hidden'}:raise Problem('Invalid layout group.')
        if type(group.get('span')) is not int or not 1<=group['span']<=config['columns'] or type(group.get('height')) is not int or not 0<=group['height']<=1600 or type(group.get('hidden')) is not bool:raise Problem('Invalid group size or visibility.')
    cards=config.get('cards',{});card_order=config.get('cardOrder',[])
    if not isinstance(cards,dict) or len(cards)>10000:raise Problem('Invalid individual card sizes.')
    for eid,size in cards.items():
        if not isinstance(eid,str) or len(eid)>80 or not isinstance(size,dict) or set(size)!={'width','height'}:raise Problem('Invalid employee card.')
        if type(size['width']) is not int or not 120<=size['width']<=480 or type(size['height']) is not int or not 52<=size['height']<=240:raise Problem('Invalid employee card size.')
    if not isinstance(card_order,list) or len(card_order)>10000 or any(not isinstance(eid,str) or len(eid)>80 for eid in card_order) or len(set(card_order))!=len(card_order):raise Problem('Invalid employee card order.')
    known={row['id'] for row in db.execute("SELECT id FROM employees WHERE ?='' OR base=?",(base,base))}
    prior=set(old['layout'].get('cards',{}))|set(old['layout'].get('cardOrder',[]))
    if (set(cards)|set(card_order))-known-prior:raise Problem('Card layout includes an unknown employee or an employee outside this plant.')
    db.execute('INSERT INTO board_layouts VALUES(?,?) ON CONFLICT(base) DO UPDATE SET config=excluded.config',(base,encoded(config)))
    store.audit(db,actor,'board_layout_updated',base or 'all-plants',old['layout'],config)
    return board_layout(db,base)


def controls(store,db,base):
    config=schedule_settings(db,base,store.settings(db))
    local=preferences(db,base)
    teams=['C','D','N'] if base=='SENDAYAN' else ['A','B','N']
    config={k:v for k,v in config.items() if k in ('team_schedules','team_overtime','rotation','schedule_groups')}
    for key in ('team_schedules','team_overtime'):config[key]={k:v for k,v in config.get(key,{}).items() if k in teams}
    config['schedule_groups']=local.get('schedule_groups',{})
    if config.get('rotation') and config['rotation'].get('teams',['A','B'])!=teams[:2]:config['rotation']=None
    return {'base':base,'settings':{**config,'review_enabled':review_enabled(db,base)},
            'schedules':[schedule(db,r['id'],base) for r in db.execute('SELECT id FROM schedules')],
            'teams':teams,'template_overrides':local.get('schedules',{})}


def save_controls(store,db,base,data,actor,validate_team,validate_scope,Problem,now):
    allowed={'team_schedules','team_overtime','rotation','schedule_groups','review_enabled','schedules'}
    if set(data)-allowed:raise Problem('Unknown plant setting.')
    if base and data.get('review_enabled') is True and not preferences(db,'').get('review_enabled',True):
        raise Problem('Developer has disabled review prompts for all plants.',409)
    old=preferences(db,base)
    after={**old,**data}
    team_config={k:after[k] for k in ('team_schedules','team_overtime','rotation') if k in after}
    validate_team(db,team_config)
    teams={'C','D','N'} if base=='SENDAYAN' else {'A','B','N'} if base=='PORT KLANG' else {'A','B','C','D','N'}
    configs=[team_config]
    groups=after.get('schedule_groups',{})
    if not isinstance(groups,dict) or len(groups)>200:raise Problem('Invalid shift groups.')
    for key,config in groups.items():
        validate_scope(key);validate_team(db,config);configs.append(config)
    for config in configs:
        for field in ('team_schedules','team_overtime'):
            if set(config.get(field,{}))-teams:raise Problem('Choose the teams for this plant.')
        rotation=config.get('rotation')
        if rotation:
            pair=rotation.get('teams',['C','D'] if base=='SENDAYAN' else ['A','B'])
            if pair not in (['A','B'],['C','D']) or not set(pair)<=teams:raise Problem('Choose a valid rotation pair.')
            rotation={**rotation,'teams':pair}
            config['rotation']=rotation
    if 'rotation' in team_config:after['rotation']=team_config['rotation']
    if 'review_enabled' in after and type(after['review_enabled']) is not bool:raise Problem('Review prompts must be on or off.')
    templates=after.get('schedules',{})
    if not isinstance(templates,dict) or len(templates)>50:raise Problem('Invalid shift times.')
    for sid,template in templates.items():
        if not db.execute('SELECT 1 FROM schedules WHERE id=?',(sid,)).fetchone() or not isinstance(template,dict) or set(template)-{'name','start','end','ot'}:
            raise Problem('Choose an existing shift template.')
        for key in ('start','end'):
            if not isinstance(template.get(key),str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',template[key]):raise Problem('Use a valid shift time.')
        if template['start']==template['end']:raise Problem('Shift start and end must differ.')
        if not isinstance(template.get('name'),str) or not 1<=len(template['name'].strip())<=120:raise Problem('Enter a shift name.')
        if template.get('ot') not in (0,1,False,True):raise Problem('Invalid overtime template.')
    db.execute('INSERT INTO plant_preferences VALUES(?,?) ON CONFLICT(base) DO UPDATE SET config=excluded.config',(base,encoded(after)))
    store.audit(db,actor,'plant_controls_updated',base or 'all-plants',old,after)
    return {'ok':True}


def attention_data(store,db,base='',employees=None):
    employees=store.employees(db) if employees is None else employees
    employees=[e for e in employees if not base or e.get('base')==base]
    cutoff=(datetime.now(KL)-timedelta(hours=store.settings(db)['max_open_hours'])).isoformat()
    attendance=[dict(r) for r in db.execute('''SELECT s.*,COALESCE(p.name,e.name) AS name,
      COALESCE(p.nickname,e.nickname) AS nickname,e.department,e.line,e.team,e.base
      FROM sessions s JOIN employees e ON e.id=s.employee_id LEFT JOIN employee_snapshots p ON p.session_id=s.id
      WHERE '''+ATTENTION_SESSION+" AND (?='' OR e.base=?) ORDER BY s.time_in,s.id",(cutoff,base,base))]
    scans=[dict(r) for r in db.execute('SELECT v.*,e.name,e.nickname,e.department,e.line,e.team,e.base FROM events v JOIN employees e ON e.id=v.employee_id WHERE '+PENDING_REVIEW+" AND (?='' OR e.base=?) ORDER BY v.occurred_at,v.id",(base,base))]
    enabled={base:review_enabled(db,base) for base in {e.get('base','') for e in employees}}
    if not review_enabled(db,base):attendance=[];scans=[]
    attendance=[r for r in attendance if enabled.get(r['base'],True)]
    scans=[r for r in scans if enabled.get(r['base'],True)]
    for r in attendance:r['stale_session']=not r['time_out'] and datetime.fromisoformat(r['time_in'])<datetime.fromisoformat(cutoff)
    hours=sorted((e for e in employees if e['active'] and not e['effective_schedule']),key=lambda e:((e['nickname'] or e['name']).casefold(),e['id']))
    return {'hours':hours,'attendance':attendance,'scans':scans}


def summary(store,db,base='',employees=None):
    data=attention_data(store,db,base,employees)
    counts={k:len(v) for k,v in data.items()}
    return {**counts,'total':sum(counts.values())}


def page(store,db,category,offset,limit,base=''):
    data=attention_data(store,db,base)
    counts={k:len(v) for k,v in data.items()}
    total=counts[category]
    offset=min(offset,max(0,((total-1)//limit)*limit))
    return {'items':data[category][offset:offset+limit],'offset':offset,'limit':limit,'total':total,'category':category,
            'summary':{**counts,'total':sum(counts.values())}}


def review_preview(store,db,data,assigned,Problem):
    base=scope(assigned,data.get('base'),Problem)
    category=data.get('category')
    if category not in ('attendance','scans'):raise Problem('Choose attendance or scans.')
    before=data.get('before','')
    if not isinstance(before,str):raise Problem('Choose a valid date.')
    if before:
        try:datetime.strptime(before,'%Y-%m-%d')
        except ValueError:raise Problem('Choose a valid date.')
    rows=attention_data(store,db,base)[category]
    if before:rows=[r for r in rows if (r['work_date'] if category=='attendance' else r['occurred_at'][:10])<=before]
    ids=data.get('ids')
    if ids is not None:
        if not isinstance(ids,list) or not 1<=len(ids)<=5000 or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):raise Problem('Choose valid unique review records.')
        selected=set(ids)
        if not selected<={r['id'] for r in rows}:raise Problem('Some records changed or are outside your plant. Refresh the list.',409)
        rows=[r for r in rows if r['id'] in selected]
    token=hashlib.sha256(encoded({'base':base,'category':category,'rows':rows}).encode()).hexdigest()
    return {'count':len(rows),'preview_token':token,'open_sessions':sum(not r['time_out'] for r in rows) if category=='attendance' else 0},rows


def review_apply(store,db,data,actor,assigned,Problem,now):
    rid=data.get('request_id','');reason=data.get('reason','')
    if not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z0-9-]{8,80}',rid):raise Problem('A request ID is required.')
    if not isinstance(reason,str) or not 5<=len(reason.strip())<=500:raise Problem('Enter a reason (5–500 characters).')
    fingerprint=hashlib.sha256(encoded({'data':data,'actor':actor,'assigned':assigned}).encode()).hexdigest()
    old=db.execute('SELECT * FROM administration_operations WHERE request_id=?',(rid,)).fetchone()
    if old:
        if old['fingerprint']!=fingerprint:raise Problem('Request ID already used.',409)
        return json.loads(old['result'])
    report,rows=review_preview(store,db,data,assigned,Problem)
    if data.get('preview_token')!=report['preview_token']:raise Problem('Records changed. Preview again.',409)
    for row in rows:
        if data['category']=='attendance':
            signature=db.execute('SELECT json_array(time_in,time_out,flags) FROM sessions WHERE id=?',(row['id'],)).fetchone()[0]
            db.execute('INSERT INTO review_acknowledgements VALUES(?,?,?,?,?,?) ON CONFLICT(entity_id) DO UPDATE SET signature=excluded.signature,stale=excluded.stale,actor=excluded.actor,recorded_at=excluded.recorded_at,reason=excluded.reason',
                       (row['id'],signature,int(bool(row['stale_session'])),actor,now,reason.strip()))
        store.audit(db,actor,'attendance_bulk_reviewed' if data['category']=='attendance' else 'scan_reviewed',row['id'],None,{'reason':reason.strip(),'bulk':True,'times_unchanged':True})
    result={'ok':True,'reviewed':len(rows),'open_sessions':report['open_sessions']}
    db.execute('INSERT INTO administration_operations VALUES(?,?,?)',(rid,fingerprint,encoded(result)))
    return result


def clockout_config(db):
    row=db.execute('SELECT * FROM automatic_clockout WHERE id=1').fetchone()
    last=db.execute('SELECT * FROM automatic_clockout_runs ORDER BY run_date DESC LIMIT 1').fetchone()
    return {'enabled':bool(row and row['enabled']),'clock_time':row['clock_time'] if row else '23:59',
            'timezone':'Asia/Kuala_Lumpur','last_run':dict(last) if last else None}


def save_clockout(store,db,data,actor,Problem,now):
    if set(data)-{'enabled','clock_time'}:raise Problem('Daily clock-out applies to all plants. Use only enabled and clock_time.')
    if type(data.get('enabled')) is not bool or not isinstance(data.get('clock_time'),str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',data['clock_time']):
        raise Problem('Choose on/off and a valid Malaysia time.')
    previous=db.execute('SELECT * FROM automatic_clockout WHERE id=1').fetchone()
    activated=previous['activated_at'] if previous and previous['enabled'] and data['enabled'] and previous['clock_time']==data['clock_time'] else now
    db.execute('INSERT INTO automatic_clockout VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled,clock_time=excluded.clock_time,activated_at=excluded.activated_at,actor=excluded.actor',
               (int(data['enabled']),data['clock_time'],activated,actor))
    store.audit(db,actor,'automatic_clockout_configured','all-plants',None,data)
    return {'ok':True}


def run_clockout(store,now=None):
    now=now or datetime.now(KL)
    now=now.astimezone(KL)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        config=db.execute('SELECT * FROM automatic_clockout WHERE id=1 AND enabled=1').fetchone()
        if not config:return None
        cutoff=datetime.fromisoformat(now.date().isoformat()+'T'+config['clock_time']+':00').replace(tzinfo=KL)
        if now<cutoff:cutoff-=timedelta(days=1)
        # Enabling/changing a schedule after today's cutoff starts tomorrow.
        if datetime.fromisoformat(config['activated_at'])>cutoff:return None
        run_date=cutoff.date().isoformat()
        if db.execute('SELECT 1 FROM automatic_clockout_runs WHERE run_date=?',(run_date,)).fetchone():return None
        rows=list(db.execute('SELECT * FROM sessions WHERE time_out IS NULL AND julianday(time_in)<=julianday(?)',(cutoff.isoformat(),)))
        backup=None
        if rows:
            backup=store.path.parent/'backups'/('before-scheduled-clockout-'+str(uuid.uuid4())+'.zip')
            store.backup(backup)
        for row in rows:
            before=dict(row)
            db.execute('UPDATE sessions SET time_out=? WHERE id=?',(cutoff.isoformat(),row['id']))
            event_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'daily-clockout:'+run_date+':'+row['id']))
            result={'event_id':event_id,'employee_id':row['employee_id'],'accepted':True,'action':'OUT',
                    'session_id':row['id'],'timestamp':cutoff.isoformat(),'work_date':row['work_date'],
                    'flags':[],'source':'scheduled_clockout','message':'Scheduled clock-out.'}
            fingerprint=hashlib.sha256(encoded(result).encode()).hexdigest()
            db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)',(event_id,row['employee_id'],'scheduled-clockout',cutoff.isoformat(),now.isoformat(),fingerprint,encoded(result)))
            store.audit(db,'scheduled-clockout','scheduled_clock_out',row['id'],before,{'time_out':cutoff.isoformat(),'configured_by':config['actor']})
        result={'closed':len(rows),'clock_time':config['clock_time'],'date':run_date,'backup':backup.name if backup else None}
        db.execute('INSERT INTO automatic_clockout_runs VALUES(?,?,?,?,?)',(run_date,config['clock_time'],len(rows),now.isoformat(),result['backup']))
        store.audit(db,'scheduled-clockout','scheduled_clockout_completed','all-plants',None,result)
    store.emit()
    return result


def start_clockout_worker(store):
    stop=threading.Event()
    def work():
        while not stop.is_set():
            try:run_clockout(store)
            except Exception as error:print('[SCHEDULED CLOCKOUT]',type(error).__name__,str(error),flush=True)
            stop.wait(15)
    worker=threading.Thread(target=work,daemon=True,name='scheduled-clockout')
    worker.start()
    return stop,worker
