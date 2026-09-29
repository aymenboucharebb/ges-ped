"""ges-ped — Gestion pédagogique ENSF. Serveur web (poste isolé ou serveur pilote derrière HTTPS)."""
import base64,datetime,hashlib,http.cookies,http.server,json,os,pathlib,re,secrets,sqlite3,threading,time,urllib.parse,webbrowser,sys,traceback
from database import *
from domain import *
from schema import SCHEMA,ROLES
import excel
DB=os.environ.get('ENSF_DB') or DEFAULT_DB;PREVIEWS={};FAILURES={};LOCK=threading.RLock()
STATIC=ROOT/'static';VERSION='1.2.0';EDITION=os.environ.get('GESPED_EDITION','PILOTE')
APP_NAME='ges-ped';APP_TITLE='ges-ped — Gestion pédagogique ENSF'
PUBLIC_URL=os.environ.get('GESPED_PUBLIC_URL','').rstrip('/')
HOSTS=[h.strip().lower() for h in os.environ.get('GESPED_HOSTS','').split(',') if h.strip()]
SECURE=os.environ.get('GESPED_SECURE_COOKIE','1' if PUBLIC_URL.startswith('https://') else '0')=='1'
TRUST_PROXY=os.environ.get('GESPED_TRUST_PROXY','0')=='1'
ALLOW_SETUP=os.environ.get('GESPED_ALLOW_SETUP','1')=='1'
IDLE=int(os.environ.get('GESPED_IDLE_MINUTES','120'))*60;ABSOLUTE=int(os.environ.get('GESPED_SESSION_HOURS','10'))*3600
COOKIE='__Host-gesped' if SECURE else 'gesped'
USERNAME_RE=re.compile(r'^[a-z0-9][a-z0-9._-]{1,39}$')
class AuthError(Invalid):status=401
class MustChange(Invalid):status=403
def token_hash(t):return hashlib.sha256(t.encode()).hexdigest()
def failed(key):
    now_=time.time();FAILURES[key]=[t for t in FAILURES.get(key,[]) if t>now_-900]+[now_]
def locked(key,limit):
    now_=time.time();recent=[t for t in FAILURES.get(key,[]) if t>now_-900];FAILURES[key]=recent
    return len(recent)>=limit
def open_session(db,user_id):
    token=secrets.token_urlsafe(32);t=time.time()
    db.execute('DELETE FROM sessions WHERE until<?',(t,))
    db.execute('INSERT INTO sessions(token,user_id,csrf,created,until,seen) VALUES(?,?,?,?,?,?)',(token_hash(token),user_id,secrets.token_urlsafe(32),t,t+IDLE,t))
    return token
def cookie(value,age):return f'{COOKIE}={value}; HttpOnly; SameSite=Strict; Path=/; Max-Age={age}'+('; Secure' if SECURE else '')
USER_COLUMNS='id,name,full_name,role,department,active,teacher,must_change,created,last_login'
def load_warning(db,a):
    """Alerte non bloquante : la charge est contrôlée sur le total ENSF de l'enseignant."""
    if a['data']['state']!='Validée':return None
    per=get(db,context(db,a)['semester'])['data']['period']
    l=next((x for x in summary(db,a['year'])['loads'] if x['teacher']==a['data']['teacher'] and x['period']==per),None)
    if l and l['gap'] is not None and l['gap']>.01:return f"Attention : charge ENSF globale de l’enseignant en période {per} = {l['assigned']+l['extra']:.2f} h Eq.C pour une cible de {l['target']:g} h (dépassement de {l['gap']:.2f} h, tous départements confondus)."
    return None
def label(db,r,seen=None):
    if not r:return '—'
    seen=seen or set()
    if r['id'] in seen:return '…'
    seen.add(r['id']);d=r['data'];k=r['kind']
    def l(id):return label(db,get(db,id),set(seen))
    if k=='teacher':return d['last']+' '+d['first']
    if k=='activity':return l(d['subject'])+' · '+l(d['type'])
    if k=='assignment':return l(d['activity'])+' · '+l(d['teacher'])+' · '+l(d['group'])
    if k=='session':return d['date']+' '+d['start']+' · '+l(d['assignment'])
    if k=='slot':return d['day']+' '+d['start']+' · '+l(d['assignment'])
    if k in ['semester','group']:return d['name']+' · '+l(d['level'])
    if k=='ue':return (d.get('code') or d['name'])+' · '+l(d['semester'])
    if k=='subject':return d['name']+' ['+(d.get('code') or '')+']'
    if k=='wish':return l(d['activity'])+' · '+l(d['teacher'])+' · choix '+format(d['priority'],'g')
    if k=='campaign':return d['name']
    return d.get('name','—')
def backup(db):
    return dict(format='ENSF-1',created=now(),years=[dict(r) for r in db.execute('SELECT * FROM years')],records=[{k:v for k,v in dict(r).items() if k!='seq'} for r in db.execute('SELECT * FROM records ORDER BY rowid')],generated=[dict(r) for r in db.execute('SELECT * FROM generated')],audit=[dict(r) for r in db.execute('SELECT * FROM audit')])
def restore(db,data,user):
    require(data.get('format')=='ENSF-1','Format de sauvegarde ENSF invalide.')
    require(isinstance(data.get('records'),list) and len(data['records'])<=100000,'Sauvegarde invalide ou trop volumineuse.')
    require(data.get('years'),'Aucune année dans la sauvegarde.')
    db.execute('DELETE FROM generated');db.execute('DELETE FROM links');db.execute('DELETE FROM records');db.execute('DELETE FROM years')
    for y in data['years']:db.execute('INSERT INTO years(id,name,closed) VALUES(?,?,?)',(y['id'],y['name'],int(bool(y['closed']))))
    for r in data['records']:
        require(r['kind'] in SCHEMA,'Type inconnu dans la sauvegarde.')
        d=json.loads(r['data']);require(isinstance(d,dict),'Fiche invalide.')
        raw_insert(db,r['year'],r['kind'],d,r['id'],int(bool(r['active'])))
        db.execute('UPDATE records SET revision=? WHERE id=?',(max(1,int(r['revision'])),r['id']))
    for r in db.execute('SELECT * FROM records').fetchall():
        rr=decode(r)
        for field in SCHEMA[rr['kind']]['fields']:
            v=rr['data'].get(field['key'])
            if field['required']:require(v not in [None,''],'Sauvegarde incomplète : '+field['label'])
            if v is not None and field['type']=='number':require(isinstance(v,(int,float)) and math.isfinite(v),'Nombre invalide dans la sauvegarde.')
            if field['type']=='ref' and v:
                t=get(db,v);require(t and t['year']==rr['year'] and t['kind']==field['ref'],'Référence incohérente dans la sauvegarde.')
        refs(db,rr['id'],rr['kind'],rr['data'])
    for g in data['generated']:
        require(get(db,g['slot'])['kind']=='slot' and get(db,g['session'])['kind']=='session','Lien de génération invalide.')
        db.execute('INSERT INTO generated VALUES(?,?)',(g['slot'],g['session']))
    # Réintégrer le journal sauvegardé sans effacer les événements locaux postérieurs.
    for a in data.get('audit',[]):
        if not db.execute('SELECT 1 FROM audit WHERE at=? AND user=? AND action=? AND record IS ?',(a['at'],a['user'],a['action'],a['record'])).fetchone():
            db.execute('INSERT INTO audit(at,user,action,year,kind,record,before_data,after_data) VALUES(?,?,?,?,?,?,?,?)',tuple(a[k] for k in ['at','user','action','year','kind','record','before_data','after_data']))
    migrate_records(db)
    audit(db,user['name'],'Restauration',None,'backup','',None,{'date_sauvegarde':data['created']})

class Handler(http.server.BaseHTTPRequestHandler):
    server_version='ges-ped'
    def log_message(self,*args):pass
    def reply(self,value,status=200,ctype='application/json; charset=utf-8',headers=None):
        raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode() if ctype.startswith('application/json') else value
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer');self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers()
        if not self.head_only:self.wfile.write(raw)
    def client_ip(self):
        if TRUST_PROXY and self.headers.get('X-Forwarded-For'):return self.headers['X-Forwarded-For'].split(',')[0].strip()
        return self.client_address[0]
    def session(self,db):
        jar=http.cookies.SimpleCookie()
        try:jar.load(self.headers.get('Cookie',''))
        except http.cookies.CookieError:pass
        token=jar.get(COOKIE);t=time.time()
        row=db.execute('SELECT * FROM sessions WHERE token=?',(token_hash(token.value),)).fetchone() if token else None
        if not row or row['until']<t or row['created']+ABSOLUTE<t:
            if row:db.execute('DELETE FROM sessions WHERE token=?',(row['token'],));db.commit()
            raise AuthError('Session expirée ou connexion nécessaire. Veuillez vous reconnecter.')
        session=dict(row)
        if t-session['seen']>60:db.execute('UPDATE sessions SET seen=?,until=? WHERE token=?',(t,t+IDLE,session['token']));db.commit()
        user=db.execute(f'SELECT {USER_COLUMNS} FROM users WHERE id=?',(session['user_id'],)).fetchone()
        if not user or not user['active']:
            db.execute('DELETE FROM sessions WHERE token=?',(session['token'],));db.commit();raise AuthError('Compte désactivé.')
        return dict(user),session
    head_only=False
    def do_GET(self):self.dispatch(False)
    def do_HEAD(self):self.head_only=True;self.dispatch(False)
    def do_POST(self):self.dispatch(True)
    def dispatch(self,post):
        with LOCK:
            db=connect(DB)
            try:
                host=self.headers.get('Host','');allowed=HOSTS or [f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}']
                require('*' in allowed or host.lower() in allowed,'Adresse du site non autorisée.')
                parsed=urllib.parse.urlparse(self.path);path=parsed.path;q={k:v[0] for k,v in urllib.parse.parse_qs(parsed.query).items()}
                payload={}
                if post:
                    require(self.headers.get('Origin') in [None,'http://'+host,'https://'+host],'Origine refusée.')
                    require(self.headers.get('Content-Type','').startswith('application/json'),'Requête JSON requise.')
                    size=int(self.headers.get('Content-Length','0'));require(0<size<=25_000_000,'Requête trop volumineuse.')
                    payload=json.loads(self.rfile.read(size));require(isinstance(payload,dict),'Requête invalide.')
                if path=='/api/status':return self.reply({'setup':ALLOW_SETUP and not db.execute('SELECT 1 FROM users').fetchone(),'app':APP_NAME,'title':APP_TITLE,'edition':EDITION,'version':VERSION})
                if path=='/healthz':db.execute('SELECT 1').fetchone();return self.reply({'ok':True})
                if path in ['/api/setup','/api/login'] and post:
                    name=str(payload.get('name','')).strip().lower();password=payload.get('password','');ip=self.client_ip()
                    require(not locked(('ip',ip),30) and not locked(('user',name),5),'Trop de tentatives de connexion. Réessayez dans 15 minutes.')
                    if path=='/api/setup':
                        require(ALLOW_SETUP and not db.execute('SELECT 1 FROM users').fetchone(),'Administrateur déjà créé.')
                        require(USERNAME_RE.match(name) and len(password)>=10,'Identifiant (minuscules, sans espace) et mot de passe de 10 caractères minimum.')
                        db.execute('INSERT INTO users(id,name,password,role,created) VALUES(?,?,?,?,?)',(uid(),name,password_hash(password),'Administrateur',now()));db.commit()
                    user=db.execute('SELECT * FROM users WHERE lower(name)=? AND active=1',(name,)).fetchone()
                    if not user or not check_password(password,user['password']):
                        failed(('ip',ip));failed(('user',name))
                        if locked(('user',name),5):audit(db,name,'Verrouillage après tentatives répétées',None,'user','',None,{'ip':ip});db.commit()
                        raise AuthError('Identifiant ou mot de passe incorrect.')
                    FAILURES.pop(('user',name),None)
                    token=open_session(db,user['id']);db.execute('UPDATE users SET last_login=? WHERE id=?',(now(),user['id']));db.commit()
                    return self.reply({'ok':True,'must_change':bool(user['must_change'])},headers={'Set-Cookie':cookie(token,ABSOLUTE)})
                if not path.startswith('/api/'):
                    target={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/favicon.svg':'favicon.svg'}.get(path)
                    if not target:return self.reply({'error':'Page introuvable'},404)
                    return self.reply((STATIC/target).read_bytes(),ctype={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml'}[pathlib.Path(target).suffix])
                user,session=self.session(db)
                if post:require(secrets.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']),'Session expirée. Rechargez la page.')
                if path=='/api/me':return self.reply(dict(user=user,csrf=session['csrf'],app=APP_NAME,edition=EDITION,version=VERSION))
                if path=='/api/password' and post:
                    stored=db.execute('SELECT password FROM users WHERE id=?',(user['id'],)).fetchone()[0]
                    require(check_password(payload.get('old',''),stored),'Mot de passe actuel incorrect.')
                    new=payload.get('new','');require(isinstance(new,str) and len(new)>=10,'Nouveau mot de passe : 10 caractères minimum.')
                    require(payload.get('confirm',new)==new,'La confirmation ne correspond pas au nouveau mot de passe.')
                    require(new!=payload.get('old'),'Le nouveau mot de passe doit être différent du mot de passe temporaire.')
                    require(new.lower() not in [user['name'].lower(),'motdepasse','password123','1234567890'],'Mot de passe trop simple.')
                    db.execute('UPDATE users SET password=?,must_change=0 WHERE id=?',(password_hash(new),user['id']))
                    db.execute('DELETE FROM sessions WHERE user_id=? AND token<>?',(user['id'],session['token']))
                    audit(db,user['name'],'Changement de mot de passe',None,'user',user['id'],None,None);db.commit();return self.reply({'ok':True})
                if path=='/api/logout' and post:
                    db.execute('DELETE FROM sessions WHERE token=?',(session['token'],));db.commit()
                    return self.reply({'ok':True},headers={'Set-Cookie':cookie('',0)})
                if user['must_change']:raise MustChange('Vous devez modifier votre mot de passe avant de continuer.')
                if path=='/api/feedback':
                    if post:
                        require(payload.get('type') in ['Bloquant','À corriger','Amélioration'],'Type de remarque inconnu.')
                        comment=str(payload.get('comment','')).strip();require(3<=len(comment)<=5000,'Décrivez le problème ou la remarque.')
                        db.execute('INSERT INTO feedback(id,at,user_name,role,page,type,comment) VALUES(?,?,?,?,?,?,?)',(uid(),now(),user['name'],user['role'],str(payload.get('page',''))[:200],payload['type'],comment));db.commit()
                        return self.reply({'ok':True})
                    require(user['role'] in STAFF,'Réservé à l’administration.')
                    return self.reply([dict(r) for r in db.execute('SELECT * FROM feedback ORDER BY at DESC')])
                if path=='/api/feedback-status' and post:
                    require(user['role'] in STAFF,'Réservé à l’administration.');require(payload.get('status') in ['Nouveau','En cours','Traité','Sans suite'],'Statut inconnu.')
                    db.execute('UPDATE feedback SET status=? WHERE id=?',(payload['status'],payload.get('id')));db.commit();return self.reply({'ok':True})
                if path=='/api/bootstrap':
                    years=[dict(r) for r in db.execute('SELECT * FROM years ORDER BY name DESC')];year=q.get('year',years[0]['id'])
                    require(any(y['id']==year for y in years),'Année introuvable.')
                    rr=visible(db,year,user);ids={r['id'] for r in rr}
                    for r in rr:r['label']=label(db,r);r['context']=context(db,r)
                    source=json.loads((ROOT/'references/source.json').read_text(encoding='utf-8'))
                    me=sorted(teacher_ids(db,year,user));depts={r['id']:r['data']['name'] for r in rows(db,year,'department')}
                    return self.reply(dict(user=user,me=me[0] if me else None,days=DAYS,timeslots=[[hhmm(a_),hhmm(b_)] for a_,b_ in slots_of(db,year)],version=VERSION,edition=EDITION,app=APP_NAME,public_url=PUBLIC_URL,today=datetime.date.today().isoformat(),departments=depts,csrf=session['csrf'],schema=SCHEMA,roles=ROLES,years=years,year=year,records=rr,summary=scoped_summary(db,year,user,rr),anomalies=source['05_ANOMALIES_SOURCES'][1:],sources=source['08_TEXTES_JURIDIQUES'][1:],generated=[dict(r) for r in db.execute('SELECT * FROM generated') if r['slot'] in ids]))
                if path=='/api/save' and post:
                    result=save(db,user,payload['year'],payload['kind'],payload['data'],payload.get('id'),payload.get('revision'),payload.get('active',1));db.commit()
                    result['warning']=load_warning(db,result) if result['kind']=='assignment' else None
                    return self.reply(result)
                if path=='/api/wish-batch' and post:
                    items=payload.get('items');require(isinstance(items,list) and 0<len(items)<=30,'Sélectionnez au moins une activité.')
                    saved=[save(db,user,payload['year'],'wish',dict(campaign=payload['campaign'],teacher=payload['teacher'],state='En attente',**{k:i.get(k) for k in ['activity','priority','language','note']})) for i in items]
                    db.commit();return self.reply({'count':len(saved)})
                if path=='/api/history':
                    r=get(db,q.get('id',''));require(r and any(x['id']==r['id'] for x in visible(db,r['year'],user)),'Historique non disponible.')
                    return self.reply([dict(x) for x in db.execute('SELECT at,user,action,before_data,after_data FROM audit WHERE record=? ORDER BY id',(r['id'],))])
                if path=='/api/delete' and post:
                    r=get(db,payload['id']);require(r,'Fiche introuvable.');writable(db,r['year']);permission(db,user,r['kind'],r,r,deleting=True)
                    require(r['kind']!='rule','Les versions de règles sont conservées.')
                    require(not db.execute('SELECT 1 FROM links WHERE target=?',(r['id'],)).fetchone(),'Fiche utilisée : désactivez-la au lieu de la supprimer.')
                    require(not db.execute("SELECT 1 FROM audit WHERE record<>? AND (before_data LIKE ? OR after_data LIKE ?)",(r['id'],'%'+r['id']+'%','%'+r['id']+'%')).fetchone(),'Cette fiche figure dans l’historique : désactivation uniquement.')
                    db.execute('DELETE FROM records WHERE id=?',(r['id'],));audit(db,user['name'],'Suppression non utilisée',r['year'],r['kind'],r['id'],r,None);db.commit();return self.reply({'ok':True})
                if path=='/api/generate' and post:
                    count=generate(db,user,payload['year']);db.commit();return self.reply({'count':count})
                if path=='/api/year' and post:
                    require(user['role']=='Administrateur','Action réservée à l’administrateur.')
                    if payload['action']=='duplicate':year=duplicate_year(db,user,payload['source'],payload['name'])
                    else:
                        require(payload['action']=='close','Action inconnue.');year=payload['year'];writable(db,year);db.execute('UPDATE years SET closed=1 WHERE id=?',(year,));audit(db,user['name'],'Clôture',year,'year',year,None,None)
                    db.commit();return self.reply({'year':year})
                if path=='/api/audit':
                    require(user['role'] in ['Administrateur','Direction / DAP','Consultation'],'Historique général réservé à la direction.')
                    return self.reply([dict(r) for r in db.execute('SELECT at,user,action,kind,record,before_data,after_data FROM audit WHERE year=? OR year IS NULL ORDER BY id DESC LIMIT 300',(q['year'],))])
                if path=='/api/username-suggest':
                    require(user['role']=='Administrateur','Action réservée à l’administrateur.')
                    return self.reply({'name':suggest_username(db,q.get('first',''),q.get('last',''),q.get('id'))})
                if path=='/api/users':
                    require(user['role']=='Administrateur','Action réservée à l’administrateur.')
                    temporary=None;created=None
                    if post:
                        d=payload;action=d.get('action') or ('update' if d.get('id') else 'create')
                        existing=db.execute('SELECT * FROM users WHERE id=?',(d['id'],)).fetchone() if d.get('id') else None
                        if action in ['update','reset']:require(existing,'Compte introuvable.')
                        if action=='reset':
                            temporary=temporary_password();db.execute('UPDATE users SET password=?,must_change=1 WHERE id=?',(password_hash(temporary),existing['id']))
                            db.execute('DELETE FROM sessions WHERE user_id=?',(existing['id'],));audit(db,user['name'],'Réinitialisation du mot de passe',None,'user',existing['id'],None,{'name':existing['name']});db.commit()
                            return self.reply(dict(user=dict(db.execute(f'SELECT {USER_COLUMNS} FROM users WHERE id=?',(existing['id'],)).fetchone()),temporary=temporary))
                        require(d.get('role') in ROLES,'Rôle invalide.')
                        if d['role']=='Chef de département':require(d.get('department') and get(db,d['department']) and get(db,d['department'])['kind']=='department','Département obligatoire pour un chef de département.')
                        else:d['department']=None
                        d['teacher']=d.get('teacher') or None
                        if d['role']=='Enseignant':require(d['teacher'],'Un compte enseignant doit être lié à une fiche enseignant ENSF.')
                        tfiche=None
                        if d['teacher']:
                            tfiche=db.execute("SELECT data FROM records WHERE kind='teacher' AND json_extract(data,'$.person')=? ORDER BY rowid DESC",(d['teacher'],)).fetchone()
                            require(tfiche,'Fiche enseignant introuvable.');tfiche=json.loads(tfiche['data'])
                            require(not db.execute('SELECT 1 FROM users WHERE teacher=? AND id<>?',(d['teacher'],d.get('id') or '')).fetchone(),'Cette fiche enseignant possède déjà un compte : un enseignant = un seul compte.')
                        name=str(d.get('name') or '').strip().lower()
                        if not name and tfiche:name=suggest_username(db,tfiche.get('first'),tfiche.get('last'),d.get('id'))
                        require(USERNAME_RE.match(name or ''),'Identifiant invalide : lettres minuscules, chiffres, point ou tiret (ex. n.laouar).')
                        require(not db.execute('SELECT 1 FROM users WHERE lower(name)=? AND id<>?',(name,d.get('id') or '')).fetchone(),f'L’identifiant « {name} » est déjà utilisé.')
                        full=str(d.get('full_name') or '').strip() or (f"{tfiche.get('first','')} {tfiche.get('last','')}".strip() if tfiche else None)
                        active=int(bool(d.get('active',1)))
                        if existing and existing['role']=='Administrateur' and (d['role']!='Administrateur' or not active):
                            require(db.execute("SELECT COUNT(*) FROM users WHERE role='Administrateur' AND active=1 AND id<>?",(existing['id'],)).fetchone()[0]>0,'Conservez au moins un administrateur actif.')
                        if existing:
                            db.execute('UPDATE users SET name=?,full_name=?,role=?,department=?,active=?,teacher=? WHERE id=?',(name,full,d['role'],d['department'],active,d['teacher'],existing['id']))
                            if not active or d['role']!=existing['role'] or d['department']!=existing['department']:db.execute('DELETE FROM sessions WHERE user_id=?',(existing['id'],))
                            id=existing['id']
                        else:
                            if d.get('password'):
                                require(len(d['password'])>=10,'Mot de passe : 10 caractères minimum.');secret=d['password'];must=int(bool(d.get('must_change',0)))
                            else:temporary=secret=temporary_password();must=1
                            id=uid();db.execute('INSERT INTO users(id,name,password,role,department,active,teacher,must_change,full_name,created) VALUES(?,?,?,?,?,?,?,?,?,?)',(id,name,password_hash(secret),d['role'],d['department'],active,d['teacher'],must,full,now()))
                        audit(db,user['name'],'Gestion compte',None,'user',id,None,{'name':name,'role':d['role']});db.commit()
                        created=dict(db.execute(f'SELECT {USER_COLUMNS} FROM users WHERE id=?',(id,)).fetchone())
                        return self.reply(dict(user=created,temporary=temporary,users=[dict(r) for r in db.execute(f'SELECT {USER_COLUMNS} FROM users ORDER BY name')]))
                    return self.reply([dict(r) for r in db.execute(f'SELECT {USER_COLUMNS} FROM users ORDER BY name')])
                if path=='/api/backup':
                    require(user['role']=='Administrateur','Sauvegarde réservée à l’administrateur.')
                    return self.reply(backup(db),headers={'Content-Disposition':'attachment; filename="ges-ped_sauvegarde_'+datetime.date.today().isoformat()+'.json"'})
                if path=='/api/restore-preview' and post:
                    require(user['role']=='Administrateur','Restauration réservée à l’administrateur.')
                    data=payload['backup'];db.execute('SAVEPOINT preview')
                    try:restore(db,data,user)
                    finally:db.execute('ROLLBACK TO preview');db.execute('RELEASE preview')
                    token=secrets.token_urlsafe(24);PREVIEWS[token]=dict(kind='restore',user=user['id'],data=data,until=time.time()+600)
                    return self.reply(dict(token=token,created=data['created'],years=len(data['years']),records=len(data['records'])))
                if path=='/api/restore' and post:
                    require(user['role']=='Administrateur','Action réservée à l’administrateur.');p=PREVIEWS.get(payload['token']);require(p and p['kind']=='restore' and p['user']==user['id'] and p['until']>time.time(),'Aperçu expiré.')
                    require(check_password(payload.get('password',''),db.execute('SELECT password FROM users WHERE id=?',(user['id'],)).fetchone()[0]),'Mot de passe incorrect.')
                    folder=pathlib.Path(os.environ.get('GESPED_DATA_DIR') or ROOT/'data')/'sauvegardes';folder.mkdir(parents=True,exist_ok=True)
                    (folder/('avant-restauration-'+str(time.time_ns())+'.json')).write_text(json.dumps(backup(db),ensure_ascii=False),encoding='utf-8')
                    restore(db,p['data'],user);db.commit();del PREVIEWS[payload['token']];return self.reply({'ok':True})
                if path=='/api/export':
                    kind=q['kind'];require(kind in SCHEMA,'Type inconnu.');fields=[f for f in SCHEMA[kind]['fields'] if not f.get('auto')];rr=visible(db,q['year'],user,rows(db,q['year'],kind))
                    headers=[f['label'] for f in fields]+['État']
                    values=[[label(db,get(db,r['data'].get(f['key']))) if f['type']=='ref' and r['data'].get(f['key']) else r['data'].get(f['key']) for f in fields]+['Actif' if r['active'] else 'Archivé'] for r in rr]
                    return self.reply(excel.export(headers,values),ctype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="ges-ped_{kind}.xlsx"'})
                if path=='/api/report-export' and post:
                    require(isinstance(payload['headers'],list) and len(payload['headers'])<=50 and len(payload['rows'])<=10000,'Rapport trop volumineux.')
                    return self.reply(excel.export(payload['headers'],payload['rows']),ctype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="ges-ped_rapport.xlsx"'})
                if path=='/api/import-preview' and post:
                    kind=payload['kind'];year=payload['year'];require(kind in ['teacher','room','department','cycle','track','specialty','level','semester','group','ue','subject','activity','language','grade','status','roomtype','uetype'],'Import non disponible pour ce module.')
                    writable(db,year);permission(db,user,kind)
                    table=excel.read(base64.b64decode(payload['content'],validate=True));require(len(table)>1,'Le classeur est vide.');headers=table[0];fields=[f for f in SCHEMA[kind]['fields'] if not f.get('auto')];items=[];errors=[]
                    for no,row in enumerate(table[1:],2):
                        d={}
                        try:
                            for f in fields:
                                if f['label'] not in headers:continue
                                ix=headers.index(f['label']);v=row[ix] if ix<len(row) else None
                                if f['type']=='ref' and v:
                                    matches=[r for r in rows(db,year,f['ref']) if r['id']==v or label(db,r)==v or r['data'].get('name')==v]
                                    require(len(matches)==1,f['label']+' : libellé absent ou ambigu, utilisez le libellé complet exporté.')
                                    v=matches[0]['id']
                                d[f['key']]=v
                            d=validate(db,year,kind,d)
                            natural=[f['key'] for f in fields if f['key'] in ['code','name','last','first']]
                            if natural:require(not any(all(r['data'].get(k)==d.get(k) for k in natural) for r in rows(db,year,kind)),'Une fiche identique existe déjà.')
                            require(d not in items,'Ligne en double dans le fichier.');items.append(d)
                        except (Invalid,ValueError) as e:errors.append({'row':no,'error':str(e)})
                    token=secrets.token_urlsafe(24);PREVIEWS[token]=dict(kind='import',user=user['id'],entity=kind,year=year,data=items,errors=errors,until=time.time()+600)
                    return self.reply(dict(token=token,rows=items,errors=errors))
                if path=='/api/import' and post:
                    p=PREVIEWS.get(payload['token']);require(p and p['kind']=='import' and p['user']==user['id'] and p['until']>time.time(),'Aperçu expiré.');require(not p['errors'],'Corrigez toutes les erreurs avant import.')
                    for d in p['data']:
                        natural=[f['key'] for f in SCHEMA[p['entity']]['fields'] if f['key'] in ['code','name','last','first']]
                        if natural:require(not any(all(r['data'].get(k)==d.get(k) for k in natural) for r in rows(db,p['year'],p['entity'])),'Une fiche a été créée depuis l’aperçu. Relancez l’import.')
                        save(db,user,p['year'],p['entity'],d)
                    db.commit();del PREVIEWS[payload['token']];return self.reply({'count':len(p['data'])})
                self.reply({'error':'Action introuvable'},404)
            except (Invalid,ValueError,KeyError,TypeError)+IntegrityErrors as e:
                db.rollback();self.reply({'error':str(e) if not isinstance(e,IntegrityErrors) else 'Opération refusée : donnée en double ou liée.'},getattr(e,'status',400))
            except Exception:
                db.rollback();traceback.print_exc();self.reply({'error':'Une erreur est survenue. Aucune modification de cette opération n’a été conservée.'},500)
            finally:db.close()

def run():
    init(DB);port=int(os.environ.get('PORT') or os.environ.get('GESPED_PORT') or os.environ.get('ENSF_PORT',8765))
    bind=os.environ.get('GESPED_BIND','0.0.0.0' if os.environ.get('PORT') else '127.0.0.1')
    try:server=http.server.ThreadingHTTPServer((bind,port),Handler)
    except OSError:
        print('Le port est déjà occupé. Vérifiez si ges-ped est déjà lancé.');return
    server.daemon_threads=True
    url=PUBLIC_URL or f'http://127.0.0.1:{port}'
    print(f'{APP_TITLE} {VERSION} {EDITION} — {url}',flush=True)
    if '--no-browser' not in sys.argv and not PUBLIC_URL:threading.Timer(.7,lambda:webbrowser.open(url)).start()
    server.serve_forever()
if __name__=='__main__':run()
