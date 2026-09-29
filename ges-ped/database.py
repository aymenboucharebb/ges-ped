import sqlite3, json, uuid, datetime, pathlib, hashlib, secrets, os, re, functools
ROOT=pathlib.Path(__file__).resolve().parent
# ges-ped : PostgreSQL commun en mode serveur (GESPED_DATABASE_URL), SQLite pour le poste isolé et les essais.
DEFAULT_DB=os.environ.get('GESPED_DATABASE_URL') or ROOT/'data'/'ensf.sqlite'
def is_pg(target):return isinstance(target,str) and target.startswith(('postgresql://','postgres://'))
def uid(): return uuid.uuid4().hex
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
IntegrityErrors=(sqlite3.IntegrityError,)
try:
    import psycopg
    IntegrityErrors=IntegrityErrors+(psycopg.errors.IntegrityError,)
except ImportError:psycopg=None
class PGRow(dict):
    """Ligne accessible par nom de colonne ou par position, comme sqlite3.Row."""
    __slots__=('_v',)
    def __init__(self,cols,values):
        dict.__init__(self,zip(cols,values));self._v=values
    def __getitem__(self,k):return self._v[k] if isinstance(k,int) else dict.__getitem__(self,k)
def _factory(cursor):
    cols=[c.name for c in cursor.description] if cursor.description else []
    return lambda values:PGRow(cols,values)
@functools.lru_cache(maxsize=512)
def translate(sql):
    """Dialecte SQLite du code métier → PostgreSQL (requêtes paramétrées uniquement)."""
    q=sql
    ignore='INSERT OR IGNORE INTO' in q
    q=q.replace('INSERT OR IGNORE INTO','INSERT INTO')
    q=re.sub(r"json_extract\((\w+),'\$\.(\w+)'\)",r"(\1::jsonb->>'\2')",q)
    q=q.replace('record IS ?','record IS NOT DISTINCT FROM ?').replace('ORDER BY rowid','ORDER BY seq')
    q=re.sub(r'(?<![\w."])user(?![\w"])','"user"',q)
    q=q.replace('%','%%').replace('?','%s')
    if ignore:q+=' ON CONFLICT DO NOTHING'
    return q
class PG:
    """Connexion PostgreSQL avec la même interface que sqlite3 pour le code métier."""
    pg=True
    def __init__(self,url):
        if psycopg is None:raise RuntimeError('Le module psycopg est requis pour PostgreSQL.')
        self.c=psycopg.connect(url,row_factory=_factory,autocommit=False,connect_timeout=10);self.cache={}
    def execute(self,sql,args=()):
        if not sql.lstrip()[:6].upper()=='SELECT':self.cache.clear()
        return self.c.execute(translate(sql),tuple(args or ()))
    def commit(self):self.c.commit()
    def rollback(self):self.cache.clear();self.c.rollback()
    def close(self):self.c.close()
def connect(path=None):
    path=path or DEFAULT_DB
    if is_pg(path):return PG(path)
    db=sqlite3.connect(path,timeout=20)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db
def decode(row):
    if row is None: return None
    r=dict(row); r.pop('seq',None); r['data']=json.loads(r['data']); return r
def rows(db,year,kind=None):
    sql='SELECT * FROM records WHERE year=?'; args=[year]
    if kind: sql+=' AND kind=?'; args.append(kind)
    return [decode(r) for r in db.execute(sql+' ORDER BY rowid',args)]
def get(db,id):
    cache=getattr(db,'cache',None)
    if cache is not None and id in cache:return decode(cache[id])
    row=db.execute('SELECT * FROM records WHERE id=?',(id,)).fetchone()
    if cache is not None:cache[id]=row
    return decode(row)
def set_json(db,id,key,value):
    r=get(db,id);r['data'][key]=value
    db.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(r['data'],ensure_ascii=False),id))
def raw_insert(db,year,kind,data,id=None,active=1):
    id=id or uid()
    db.execute('INSERT INTO records(id,year,kind,data,active,revision) VALUES(?,?,?,?,?,1)',(id,year,kind,json.dumps(data,ensure_ascii=False),active))
    return id
def refs(db,id,kind,data):
    from schema import SCHEMA
    db.execute('DELETE FROM links WHERE source=?',(id,))
    for field in SCHEMA[kind]['fields']:
        if field['type']=='ref' and data.get(field['key']):
            db.execute('INSERT INTO links VALUES(?,?,?)',(id,data[field['key']],field['key']))
def audit(db,user,action,year,kind,id,before,after):
    db.execute('INSERT INTO audit(at,user,action,year,kind,record,before_data,after_data) VALUES(?,?,?,?,?,?,?,?)',(now(),user,action,year,kind,id,json.dumps(before,ensure_ascii=False),json.dumps(after,ensure_ascii=False)))
ITERATIONS=600000
def password_hash(p,salt=None,iterations=ITERATIONS):
    salt=salt or secrets.token_hex(16)
    return f'pbkdf2${iterations}${salt}$'+hashlib.pbkdf2_hmac('sha256',p.encode(),salt.encode(),iterations).hex()
def check_password(p,h):
    if not isinstance(p,str) or not h:return False
    if h.startswith('pbkdf2$'):
        _,it,salt,_=h.split('$');return secrets.compare_digest(password_hash(p,salt,int(it)),h)
    salt=h.split(':')[0]  # format des versions 1.0 / 1.1
    return secrets.compare_digest(salt+':'+hashlib.pbkdf2_hmac('sha256',p.encode(),salt.encode(),310000).hex(),h)
TEMP_ALPHABET_UP='ABCDEFGHJKLMNPQRSTUVWXYZ';TEMP_ALPHABET_LOW='abcdefghijkmnpqrstuvwxyz';TEMP_DIGITS='23456789'
def temporary_password():
    """8 caractères faciles à dicter (sans 0/O, 1/l/I), avec majuscules, minuscules et chiffres alternés."""
    return ''.join(secrets.choice(TEMP_ALPHABET_UP if i%4==0 else TEMP_ALPHABET_LOW if i%2==0 else TEMP_DIGITS) for i in range(8))
def username_base(first,last):
    import unicodedata
    clean=lambda v:re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower())
    f=clean(first);l=clean(last)
    return (f[:1]+'.'+l) if f and l else (l or f)
def suggest_username(db,first,last,exclude_id=None):
    base=username_base(first,last);require_ok=bool(base)
    if not require_ok:return ''
    taken={r['name'].lower() for r in db.execute('SELECT id,name FROM users').fetchall() if r['id']!=exclude_id}
    name=base;n=1
    while name in taken:n+=1;name=f'{base}{n}'
    return name
SQLITE_DDL='''
    CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY, applied TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS years(id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,closed INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,year TEXT NOT NULL REFERENCES years(id),kind TEXT NOT NULL,data TEXT NOT NULL CHECK(json_valid(data)),active INTEGER NOT NULL CHECK(active IN(0,1)),revision INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS by_year_kind ON records(year,kind);
    CREATE TABLE IF NOT EXISTS links(source TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,target TEXT NOT NULL REFERENCES records(id) ON DELETE RESTRICT,field TEXT NOT NULL,PRIMARY KEY(source,field));
    CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,department TEXT,active INTEGER NOT NULL DEFAULT 1,teacher TEXT);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at TEXT NOT NULL,user TEXT NOT NULL,action TEXT NOT NULL,year TEXT,kind TEXT,record TEXT,before_data TEXT,after_data TEXT);
    CREATE TABLE IF NOT EXISTS generated(slot TEXT NOT NULL REFERENCES records(id),session TEXT NOT NULL REFERENCES records(id),PRIMARY KEY(slot,session));
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,csrf TEXT NOT NULL,created REAL NOT NULL,until REAL NOT NULL,seen REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY,at TEXT NOT NULL,user_name TEXT NOT NULL,role TEXT,page TEXT,type TEXT NOT NULL,comment TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Nouveau');
    INSERT OR IGNORE INTO migrations VALUES(1,datetime('now'));
'''
PG_DDL=[
    'CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY, applied TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS years(id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,closed INTEGER NOT NULL DEFAULT 0)',
    'CREATE TABLE IF NOT EXISTS records(seq BIGSERIAL UNIQUE,id TEXT PRIMARY KEY,year TEXT NOT NULL REFERENCES years(id),kind TEXT NOT NULL,data TEXT NOT NULL CHECK((data::jsonb) IS NOT NULL),active INTEGER NOT NULL CHECK(active IN(0,1)),revision INTEGER NOT NULL)',
    'CREATE INDEX IF NOT EXISTS by_year_kind ON records(year,kind)',
    'CREATE TABLE IF NOT EXISTS links(source TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,target TEXT NOT NULL REFERENCES records(id) ON DELETE RESTRICT,field TEXT NOT NULL,PRIMARY KEY(source,field))',
    'CREATE INDEX IF NOT EXISTS links_target ON links(target)',
    'CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,department TEXT,active INTEGER NOT NULL DEFAULT 1,teacher TEXT)',
    'CREATE TABLE IF NOT EXISTS audit(id BIGSERIAL PRIMARY KEY,at TEXT NOT NULL,"user" TEXT NOT NULL,action TEXT NOT NULL,year TEXT,kind TEXT,record TEXT,before_data TEXT,after_data TEXT)',
    'CREATE INDEX IF NOT EXISTS audit_record ON audit(record)',
    'CREATE TABLE IF NOT EXISTS generated(slot TEXT NOT NULL REFERENCES records(id),session TEXT NOT NULL REFERENCES records(id),PRIMARY KEY(slot,session))',
    'CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,csrf TEXT NOT NULL,created DOUBLE PRECISION NOT NULL,until DOUBLE PRECISION NOT NULL,seen DOUBLE PRECISION NOT NULL)',
    "CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY,at TEXT NOT NULL,user_name TEXT NOT NULL,role TEXT,page TEXT,type TEXT NOT NULL,comment TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Nouveau')",
    "INSERT INTO migrations VALUES(1,'initial') ON CONFLICT DO NOTHING",
]
def init(path=None):
    path=path or DEFAULT_DB
    if is_pg(path):
        db=connect(path)
        db.c.execute('SELECT pg_advisory_xact_lock(424242)')  # plusieurs démarrages simultanés : une seule initialisation
        for stmt in PG_DDL:db.c.execute(stmt)
    else:
        pathlib.Path(path).parent.mkdir(parents=True,exist_ok=True)
        db=connect(path);db.executescript(SQLITE_DDL)
    if not db.execute('SELECT 1 FROM years').fetchone():
        seed(db)
        for v in (2,3,4):db.execute('INSERT OR IGNORE INTO migrations VALUES(?,?)',(v,now()))
    migrate(db,path)
    db.commit(); db.close()
SCHEMA_VERSION=4
def columns(db,table):
    if getattr(db,'pg',False):return [r[0] for r in db.execute('SELECT column_name FROM information_schema.columns WHERE table_name=?',(table,))]
    return [r[1] for r in db.execute(f'PRAGMA table_info({table})')]
def migrate(db,path=None):
    """Migrations incrémentales, sans perte : copie de sécurité de la base avant toute transformation."""
    version=db.execute('SELECT MAX(version) FROM migrations').fetchone()[0] or 1
    if version<2 and not getattr(db,'pg',False) and path is not None and pathlib.Path(path).exists():
        db.commit();folder=pathlib.Path(path).parent/'sauvegardes';folder.mkdir(parents=True,exist_ok=True)
        target=sqlite3.connect(folder/('avant-migration-v1.1-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite'))
        db.backup(target);target.close()
    cols=columns(db,'users')
    for col,decl in [('teacher','TEXT'),('must_change','INTEGER NOT NULL DEFAULT 0'),('full_name','TEXT'),('created','TEXT'),('last_login','TEXT')]:
        if col not in cols:db.execute(f'ALTER TABLE users ADD COLUMN {col} {decl}')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS users_teacher ON users(teacher) WHERE teacher IS NOT NULL')
    if version<2:
        migrate_records(db)
        db.execute('INSERT OR IGNORE INTO migrations VALUES(?,?)',(2,now()))
    if version<3:
        db.execute('INSERT OR IGNORE INTO migrations VALUES(?,?)',(3,now()))
    if version<4:
        # Semaine ENSF dimanche → jeudi : la date de référence d'un semestre devient le dimanche précédant l'ancien lundi.
        for r in db.execute("SELECT * FROM records WHERE kind='semester'").fetchall():
            d=json.loads(r['data'])
            if d.get('start'):
                day=datetime.date.fromisoformat(d['start'])
                if day.weekday()==0:
                    d['start']=(day-datetime.timedelta(days=1)).isoformat()
                    db.execute('UPDATE records SET data=?,revision=revision+1 WHERE id=?',(json.dumps(d,ensure_ascii=False),r['id']))
        db.execute('INSERT OR IGNORE INTO migrations VALUES(?,?)',(4,now()))
def norm(v):
    import unicodedata
    v=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    return ' '.join(v.replace('-',' ').split())
def migrate_records(db):
    """Passage au modèle v1.1 : langue portée par l'affectation, identité enseignant unique ENSF."""
    changed=[]
    names={r['id']:json.loads(r['data']).get('name') for r in db.execute("SELECT id,data FROM records WHERE kind='language'")}
    for r in db.execute("SELECT * FROM records WHERE kind='activity'").fetchall():
        d=json.loads(r['data'])
        if 'language' in d:
            lang=d.pop('language')
            if lang:d['note']=((d.get('note') or '')+' · ' if d.get('note') else '')+'Langue indiquée dans la version 1.0 (non contraignante) : '+str(names.get(lang,lang))
            changed.append((r['id'],'activity',d))
    persons={}
    for r in db.execute("SELECT * FROM records WHERE kind='teacher' ORDER BY rowid").fetchall():
        d=json.loads(r['data']);dirty=False
        if not d.get('person'):
            key=('code',norm(d.get('code'))) if d.get('code') else ('name',norm(d.get('last')),norm(d.get('first')))
            d['person']=persons.setdefault(key,uid());dirty=True
        for k,v in (('english_level','Non renseigné'),('english_ok','Non déclaré')):
            if not d.get(k):d[k]=v;dirty=True
        if dirty:changed.append((r['id'],'teacher',d))
    for id,kind,d in changed:
        db.execute('UPDATE records SET data=?,revision=revision+1 WHERE id=?',(json.dumps(d,ensure_ascii=False),id));refs(db,id,kind,d)
    if changed:audit(db,'Mise à jour v1.1','Migration',None,'migration','',None,{'fiches_adaptees':len(changed)})
    return len(changed)
def seed(db):
    year='2026-2027'; db.execute('INSERT INTO years(id,name) VALUES(?,?)',(year,'2026 / 2027'))
    cache={}
    def add(kind,key,data):
        if (kind,key) not in cache: cache[kind,key]=raw_insert(db,year,kind,data)
        return cache[kind,key]
    for name,code in [('Français','fr'),('Anglais','en'),('Arabe','ar')]: add('language',code,dict(name=name,code=code))
    for name in ['Professeur','Maître de conférences A','Maître de conférences B','Maître assistant A','Maître assistant B']: add('grade',name,dict(name=name))
    for name in ['Permanent','Vacataire']: add('status',name,dict(name=name))
    for name in ['Salle de cours','Laboratoire','Amphithéâtre','Salle informatique','Terrain']: add('roomtype',name,dict(name=name))
    for name,target,factor in [('Cours','Section',1),('TD','Groupe',2/3),('TP','Groupe',2/3),('PFE','Libre',None)]: add('activitytype',name,dict(name=name,target=target,factor=factor))
    add('rule','initial',dict(name='ENSF — référence 2026 / 2027',normal=96,half=48,annual=192,weeks=14,duration=1.5,outing=8,source='Décret 24-103 du 07/03/2024 ; répartition semestrielle interne ENSF',note='Demi-charge sur décision individuelle. Sorties : règle interne à formaliser. Aucun calcul automatique CDE / Incubateur.'))
    source=json.loads((ROOT/'references/source.json').read_text(encoding='utf-8'))
    for r in source['03_BASE_REGLEMENTAIRE'][1:]:
        if not r[0]: continue
        cycle=add('cycle',r[1],dict(name=r[1]))
        trackname='Formation de base' if r[1]=='Cycle 1' else 'Sciences forestières'
        track=add('track',trackname,dict(name=trackname,cycle=cycle))
        special=None
        if r[2]=='Spécialité': special=add('specialty',r[4],dict(name=r[4],track=track))
        complementary=r[2]=='Formation complémentaire'
        levelkey=(r[1],r[3],r[4] if special else ('Complémentaire' if complementary else ''))
        lname=('Formation complémentaire — rattachement à préciser' if complementary else r[1]+' · '+r[3]+(' · '+r[4] if special else ' · '+trackname))
        level=add('level',levelkey,dict(name=lname,track=track,specialty=special))
        sem=add('semester',(level,r[5]),dict(name=r[5],level=level,period=str(1 if r[5] in ['S1','S3','S5','Bloc complémentaire 1','Bloc complémentaire 3'] else 2),weeks=14,note='Rattachement pédagogique et période à confirmer.' if complementary else 'Date de début à renseigner.'))
        ut=add('uetype',r[6],dict(name=r[6]))
        ue=add('ue',(sem,r[6],r[7]),dict(name=r[6],code=r[7] or '',semester=sem,type=ut,note='Code UE absent de la source.' if not r[7] else ''))
        sub=add('subject',r[0],dict(name=r[8],code=r[0],ue=ue,coefficient=r[14],credits=r[15],source_volume=r[9],personal=r[13],source=f'{r[17]} — p. {r[19]}',note=r[23] or ''))
        for index,name in [(10,'Cours'),(11,'TD'),(12,'TP')]:
            if r[index]: add('activity',(r[0],name),dict(subject=sub,type=cache['activitytype',name],hours=r[index],category='Formation complémentaire' if complementary else 'Réglementaire'))
        if r[16] in ['Activité PFE','Travail individuel']:
            add('activity',(r[0],'PFE'),dict(subject=sub,type=cache['activitytype','PFE'],hours=r[9],category='PFE',note='Conversion en charge non définie.'))
        if not complementary:
            section=add('group',(level,'section'),dict(name='Section A',level=level,type='Section',size=None))
            n=4 if r[1]=='Cycle 1' else (2 if r[2]=='Tronc commun' else 1)
            for i in range(1,n+1): add('group',(level,i),dict(name=f'G{i}',level=level,parent=section,type='Groupe',size=None))
    for row in rows(db,year): refs(db,row['id'],row['kind'],row['data'])
    audit(db,'Installation','Initialisation',year,'reference','',None,{'lignes_source':156,'affectations':0})
