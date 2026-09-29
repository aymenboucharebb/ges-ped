"""ges-ped PILOTE : comptes web, première connexion, sessions, confidentialité API (test D), simultanéité (test E)."""
import unittest,pathlib,threading,json,urllib.request,urllib.error,http.cookiejar,sys,re,datetime,time,concurrent.futures
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import server,excel
from database import *
from domain import *
from support import TestDatabases
ADMIN={'id':'setup','name':'setup','role':'Administrateur'}
TODAY=datetime.date.today()
class Client:
    def __init__(self,url):
        self.url=url;self.jar=http.cookiejar.CookieJar();self.op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar));self.csrf=''
    def send(self,path,data=None,headers=None):
        h={'Content-Type':'application/json','X-CSRF-Token':self.csrf};h.update(headers or {})
        req=urllib.request.Request(self.url+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers=h)
        try:
            r=self.op.open(req,timeout=60);body=r.read()
            return r.status,(json.loads(body) if r.headers['Content-Type'].startswith('application/json') else body)
        except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
    def login(self,name,password):
        st,v=self.send('login',{'name':name,'password':password})
        if st==200 and not v.get('must_change'):self.csrf=self.send('me')[1]['csrf']
        return st,v
class PiloteWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dbs=TestDatabases()
    @classmethod
    def tearDownClass(cls):cls.dbs.cleanup()
    def setUp(self):
        self.old=server.DB;server.DB=self.dbs.fresh();server.FAILURES.clear()
        db=connect(server.DB);y=self.y='2026-2027'
        # Données de base : deux départements, deux enseignants, une campagne ouverte.
        dA=save(db,ADMIN,y,'department',{'name':'Département A'});dB=save(db,ADMIN,y,'department',{'name':'Département B'})
        for t in rows(db,y,'track'):save(db,ADMIN,y,'track',dict(t['data'],department=dA['id'] if t['data']['name']=='Formation de base' else dB['id']),t['id'],t['revision'])
        for s_ in rows(db,y,'semester'):save(db,ADMIN,y,'semester',dict(s_['data'],start='2026-09-27'),s_['id'],s_['revision'])
        for g in rows(db,y,'group'):save(db,ADMIN,y,'group',dict(g['data'],size=25),g['id'],g['revision'])
        st=rows(db,y,'status')[0]['id']
        self.t1=save(db,ADMIN,y,'teacher',{'last':'Laouar','first':'Nadhir','status':st,'load':'Normale','department':dA['id']})
        self.t2=save(db,ADMIN,y,'teacher',{'last':'Ben Salah','first':'Élodie','status':st,'load':'Normale'})
        self.room=save(db,ADMIN,y,'room',{'name':'Amphi','capacity':300,'type':rows(db,y,'roomtype')[0]['id']})
        self.room2=save(db,ADMIN,y,'room',{'name':'Salle 2','capacity':300,'type':rows(db,y,'roomtype')[0]['id']})
        self.camp=save(db,ADMIN,y,'campaign',{'name':'S1','period':'1','open':TODAY.isoformat(),'deadline':(TODAY+datetime.timedelta(days=5)).isoformat(),'status':'Ouverte'})
        per={s_['id']:s_['data']['period'] for s_ in rows(db,y,'semester')}
        cours=lambda dep:[a for a in rows(db,y,'activity') if a['data']['category']=='Réglementaire' and get(db,a['data']['type'])['data']['name']=='Cours' and per[context(db,a)['semester']]=='1' and context(db,a).get('department')==dep['id']]
        self.aA=cours(dA);self.aB=cours(dB);self.dA=dA;self.dB=dB
        self.fr=next(l for l in rows(db,y,'language') if l['data']['code']=='fr');self.en=next(l for l in rows(db,y,'language') if l['data']['code']=='en')
        self.sec=lambda a:next(g for g in rows(db,y,'group') if g['data']['level']==context(db,a)['level'] and g['data']['type']=='Section')
        db.execute("INSERT INTO users(id,name,password,role,created) VALUES('adm','admin',?,'Administrateur',?)",(password_hash('admin-password-1'),now()))
        db.commit();self.db=db
        self.http=server.http.server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);self.http.daemon_threads=True
        threading.Thread(target=self.http.serve_forever,daemon=True).start();self.url='http://127.0.0.1:'+str(self.http.server_port)
        self.admin=Client(self.url);self.assertEqual(self.admin.login('admin','admin-password-1')[0],200)
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.db.close();self.dbs.drop(server.DB);server.DB=self.old
    def account(self,**d):
        st,v=self.admin.send('users',d);self.assertEqual(st,200,v);return v
    def activate(self,name,temporary,new='nouveau-mot-de-passe-1'):
        c=Client(self.url);st,v=c.login(name,temporary);self.assertEqual(st,200);self.assertTrue(v['must_change'])
        c.csrf=c.send('me')[1]['csrf'];self.assertEqual(c.send('password',{'old':temporary,'new':new,'confirm':new})[0],200)
        c.csrf=c.send('me')[1]['csrf'];return c
    def pilot_accounts(self):
        chefA=self.account(role='Chef de département',department=self.dA['id'],full_name='Chef A',name='chef.a')
        chefB=self.account(role='Chef de département',department=self.dB['id'],full_name='Chef B',name='chef.b')
        e1=self.account(role='Enseignant',teacher=self.t1['data']['person']);e2=self.account(role='Enseignant',teacher=self.t2['data']['person'])
        return [self.activate(v['user']['name'],v['temporary']) for v in [chefA,chefB,e1,e2]]

    # Comptes : identifiant automatique, mot de passe temporaire unique, jamais réaffiché.
    def test_username_and_temporary_password(self):
        v=self.account(role='Enseignant',teacher=self.t1['data']['person'])
        self.assertEqual(v['user']['name'],'n.laouar');self.assertRegex(v['temporary'],r'^[A-HJ-NP-Z][2-9][a-km-z][2-9][A-HJ-NP-Z][2-9][a-km-z][2-9]$')
        self.assertEqual(self.admin.send('username-suggest?first=%C3%89lodie&last=Ben%20Salah')[1]['name'],'e.bensalah')
        self.assertEqual(self.admin.send('username-suggest?first=Nadhir&last=Laouar')[1]['name'],'n.laouar2')
        w=self.account(role='Consultation',full_name='Nadia Laouar',name='n.laouar')if False else None
        st,e=self.admin.send('users',{'role':'Consultation','name':'n.laouar'});self.assertEqual(st,400);self.assertIn('déjà utilisé',e['error'])
        v2=self.account(role='Enseignant',teacher=self.t2['data']['person'],name='e.bensalah');self.assertNotEqual(v['temporary'],v2['temporary'])
        users=self.admin.send('users')[1];self.assertFalse(any('password' in u or 'temporary' in u for u in users))
        stored=self.db.execute("SELECT password FROM users WHERE name='n.laouar'").fetchone()[0];self.assertNotIn(v['temporary'],stored);self.assertTrue(stored.startswith('pbkdf2$'))
        self.assertEqual(self.admin.send('users',{'role':'Consultation','name':'Nom Invalide'})[0],400)
        self.assertEqual(self.admin.send('users',{'role':'Enseignant','teacher':self.t1['data']['person']})[0],400)  # un seul compte par enseignant

    # Première connexion : changement obligatoire avant tout accès.
    def test_first_login_forces_password_change(self):
        v=self.account(role='Enseignant',teacher=self.t1['data']['person']);tmp=v['temporary']
        c=Client(self.url);st,r=c.login('n.laouar',tmp);self.assertTrue(r['must_change']);c.csrf=c.send('me')[1]['csrf']
        for path in ['bootstrap','feedback']:self.assertEqual(c.send(path)[0],403)
        self.assertEqual(c.send('save',{'year':self.y,'kind':'wish','data':{}})[0],403)
        self.assertEqual(c.send('password',{'old':'mauvais','new':'nouveau-mot-de-passe-1','confirm':'nouveau-mot-de-passe-1'})[0],400)
        self.assertEqual(c.send('password',{'old':tmp,'new':'nouveau-mot-de-passe-1','confirm':'autre-chose-123'})[0],400)
        self.assertEqual(c.send('password',{'old':tmp,'new':'court','confirm':'court'})[0],400)
        self.assertEqual(c.send('password',{'old':tmp,'new':'nouveau-mot-de-passe-1','confirm':'nouveau-mot-de-passe-1'})[0],200)
        self.assertEqual(c.send('bootstrap')[0],200)
        self.assertEqual(Client(self.url).login('n.laouar',tmp)[0],401)  # le mot de passe temporaire ne fonctionne plus
        st,r=self.admin.send('users',{'action':'reset','id':v['user']['id']});self.assertEqual(st,200)
        self.assertEqual(c.send('bootstrap')[0],401)  # sessions fermées par la réinitialisation
        self.assertTrue(Client(self.url).login('n.laouar',r['temporary'])[1]['must_change'])

    def test_lockout_after_repeated_failures(self):
        c=Client(self.url)
        for _ in range(5):self.assertEqual(c.login('admin','mauvais-mot-de-passe')[0],401)
        st,e=c.login('admin','admin-password-1');self.assertEqual(st,400);self.assertIn('Trop de tentatives',e['error'])
        self.assertEqual(Client(self.url).login('inconnu','x')[0],401)

    def test_session_expiry_logout_and_cookie_flags(self):
        c=Client(self.url);c.login('admin','admin-password-1');self.assertEqual(c.send('bootstrap')[0],200)
        cookie=next(iter(c.jar));self.assertTrue(cookie.has_nonstandard_attr('HttpOnly'))
        self.db.execute('UPDATE sessions SET until=0');self.db.commit()
        self.assertEqual(c.send('bootstrap')[0],401)
        c=Client(self.url);c.login('admin','admin-password-1');self.assertEqual(c.send('logout',{})[0],200);self.assertEqual(c.send('bootstrap')[0],401)
        stored=[r[0] for r in self.db.execute('SELECT token FROM sessions')];self.assertTrue(all(len(t)==64 for t in stored))  # jetons hachés
    def test_hosts_origin_and_secure_cookie(self):
        old=(server.HOSTS,server.SECURE,server.COOKIE)
        try:
            server.HOSTS=['pilote.ges-ped.exemple.dz'];c=Client(self.url)
            self.assertEqual(c.login('admin','admin-password-1')[0],400)  # hôte technique refusé
            st,v=c.send('login',{'name':'admin','password':'admin-password-1'},{'Host':'pilote.ges-ped.exemple.dz','Origin':'https://evil.example'});self.assertEqual(st,400)
            server.SECURE=True;server.COOKIE='__Host-gesped'
            req=urllib.request.Request(self.url+'/api/login',data=json.dumps({'name':'admin','password':'admin-password-1'}).encode(),headers={'Content-Type':'application/json','Host':'pilote.ges-ped.exemple.dz','Origin':'https://pilote.ges-ped.exemple.dz'})
            r=urllib.request.urlopen(req);sc=r.headers['Set-Cookie'];self.assertIn('__Host-gesped=',sc);self.assertIn('Secure',sc);self.assertIn('HttpOnly',sc);self.assertIn('SameSite=Strict',sc)
        finally:server.HOSTS,server.SECURE,server.COOKIE=old
    def test_setup_disabled_on_server(self):
        old=server.ALLOW_SETUP;server.ALLOW_SETUP=False
        try:self.assertFalse(Client(self.url).send('status')[1]['setup']);self.assertEqual(Client(self.url).send('setup',{'name':'x','password':'y'*12})[0],400)
        finally:server.ALLOW_SETUP=old
    def test_feedback(self):
        chefA,chefB,e1,e2=self.pilot_accounts()
        self.assertEqual(e1.send('feedback',{'page':'Mes vœux','type':'Bloquant','comment':'Bouton inactif'})[0],200)
        self.assertEqual(e1.send('feedback')[0],400)
        items=self.admin.send('feedback')[1];self.assertEqual(len(items),1);self.assertEqual(items[0]['user_name'],'n.laouar')
        self.assertEqual(self.admin.send('feedback-status',{'id':items[0]['id'],'status':'Traité'})[0],200)

    # TEST A / B / C / D : parcours des pilotes et tentatives de contournement de l'API.
    def test_pilot_scenarios_and_api_tampering(self):
        chefA,chefB,e1,e2=self.pilot_accounts();y=self.y
        s1=e1.send('bootstrap')[1];s2=e2.send('bootstrap')[1];me1=s1['me'];me2=s2['me']
        self.assertEqual({r['kind'] for r in s1['records'] if r['id']==me2},set())
        # C : l'enseignant n°2 formule des vœux dans les deux départements.
        st,v=e2.send('wish-batch',{'year':y,'campaign':self.camp['id'],'teacher':me2,'items':[{'activity':self.aA[0]['id'],'priority':1,'language':self.en['id']},{'activity':self.aB[0]['id'],'priority':2,'language':self.fr['id']}]});self.assertEqual(st,200,v)
        e1.send('wish-batch',{'year':y,'campaign':self.camp['id'],'teacher':me1,'items':[{'activity':self.aA[1]['id'],'priority':1,'language':self.fr['id']}]})
        # A : chaque chef traite les vœux de ses matières et crée l'affectation.
        wA=next(r for r in chefA.send('bootstrap')[1]['records'] if r['kind']=='wish' and r['data']['teacher']==me2)
        self.assertEqual(chefA.send('save',{'year':y,'kind':'wish','id':wA['id'],'revision':wA['revision'],'data':dict(wA['data'],state='Acceptée')})[0],200)
        st,aA=chefA.send('save',{'year':y,'kind':'assignment','data':{'activity':self.aA[0]['id'],'teacher':me2,'group':self.sec(self.aA[0])['id'],'hours':self.aA[0]['data']['hours'],'language':self.en['id'],'state':'Validée','wish':wA['id']}});self.assertEqual(st,200,aA)
        st,m=chefA.send('save',{'year':y,'kind':'assignment','data':{'activity':self.aA[2]['id'],'teacher':me1,'group':self.sec(self.aA[2])['id'],'hours':3,'language':self.fr['id'],'state':'Validée'}});self.assertEqual(st,200,m)  # manuelle sans vœu
        wB=next(r for r in chefB.send('bootstrap')[1]['records'] if r['kind']=='wish' and r['data']['teacher']==me2)
        self.assertEqual(chefA.send('save',{'year':y,'kind':'wish','id':wB['id'],'revision':wB['revision'],'data':dict(wB['data'],state='Refusée')})[0],400)  # autre département
        self.assertEqual(chefB.send('save',{'year':y,'kind':'wish','id':wB['id'],'revision':wB['revision'],'data':dict(wB['data'],state='Acceptée')})[0],200)
        st,aB=chefB.send('save',{'year':y,'kind':'assignment','data':{'activity':self.aB[0]['id'],'teacher':me2,'group':self.sec(self.aB[0])['id'],'hours':self.aB[0]['data']['hours'],'language':self.fr['id'],'state':'Validée'}});self.assertEqual(st,200,aB)
        self.assertEqual(chefA.send('save',{'year':y,'kind':'assignment','id':aB['id'],'revision':aB['revision'],'data':dict(aB['data'],hours=1)})[0],400)
        prog=next(r for r in chefA.send('bootstrap')[1]['records'] if r['id']==self.aA[0]['id'])
        self.assertEqual(chefA.send('save',{'year':y,'kind':'activity','id':prog['id'],'revision':prog['revision'],'data':dict(prog['data'],hours=1)})[0],400)
        # F : conflit interdépartemental au même créneau.
        self.assertEqual(chefA.send('save',{'year':y,'kind':'slot','data':{'assignment':aA['id'],'room':self.room['id'],'day':'Lundi','start':'09:30','duration':1.5,'weeks':'1-4'}})[0],200)
        st,e=chefB.send('save',{'year':y,'kind':'slot','data':{'assignment':aB['id'],'room':self.room2['id'],'day':'Lundi','start':'09:30','duration':1.5,'weeks':'2'}});self.assertEqual(st,400);self.assertIn('autre département',e['error'])
        self.assertEqual(chefB.send('save',{'year':y,'kind':'slot','data':{'assignment':aB['id'],'room':self.room2['id'],'day':'Mardi','start':'09:30','duration':1.5,'weeks':'1-4'}})[0],200)
        # C : charge unique et emploi du temps unique pour l'enseignant n°2.
        s2=e2.send('bootstrap')[1]
        loads=[l for l in s2['summary']['loads'] if l['period']=='1'];self.assertEqual(len(loads),1)
        self.assertAlmostEqual(loads[0]['assigned'],self.aA[0]['data']['hours']+self.aB[0]['data']['hours']);self.assertEqual(set(loads[0]['depts']),{self.dA['id'],self.dB['id']})
        self.assertEqual({r['context']['department'] for r in s2['records'] if r['kind']=='slot'},{self.dA['id'],self.dB['id']})
        # D : l'enseignant n°1 tente d'accéder aux données de l'enseignant n°2.
        s1=e1.send('bootstrap')[1];ids={r['id'] for r in s1['records']}
        self.assertFalse(ids&{me2,aA['id'],aB['id'],wA['id'],wB['id']});self.assertFalse([r for r in s1['records'] if r['kind']=='slot'])
        self.assertEqual([l['teacher'] for l in s1['summary']['loads']],[me1,me1]);self.assertFalse(s1['summary']['busy'])
        for kind in ['assignment','wish','slot','session','teacher']:
            content=e1.send(f'export?year={y}&kind={kind}')[1];table=excel.read(content)
            self.assertFalse(any('Ben Salah' in ' '.join(map(str,row)) for row in table),kind)
        for rid in [wA['id'],aA['id'],me2]:self.assertEqual(e1.send('history?id='+rid)[0],400)
        self.assertEqual(e1.send('wish-batch',{'year':y,'campaign':self.camp['id'],'teacher':me2,'items':[{'activity':self.aA[3]['id'],'priority':1,'language':self.fr['id']}]})[0],400)
        self.assertEqual(e1.send('save',{'year':y,'kind':'wish','data':{'campaign':self.camp['id'],'teacher':me2,'activity':self.aA[3]['id'],'priority':1,'language':self.fr['id'],'state':'En attente'}})[0],400)
        self.assertEqual(e1.send('save',{'year':y,'kind':'wish','id':wA['id'],'revision':get(self.db,wA['id'])['revision'],'data':dict(wA['data'],teacher=me1)})[0],400)
        self.assertEqual(e1.send('save',{'year':y,'kind':'teacher','id':me2,'revision':1,'data':{}})[0],400)
        self.assertEqual(e1.send('bootstrap?year=inconnue')[0],400)
        for path in ['users','audit?year='+y,'backup','feedback','username-suggest?first=a&last=b']:self.assertEqual(e1.send(path)[0],400,path)
        self.assertEqual(e1.send('users',{'action':'reset','id':'adm'})[0],400)
        # G : taux d'anglais.
        st=self.admin.send('bootstrap')[1]['summary'];en=st['english']
        self.assertAlmostEqual(en['english'],self.aA[0]['data']['hours']);self.assertEqual(en['total'],5625)
        dep=next(b for b in st['breakdown'] if b['kind']=='department' and b['id']==self.dA['id']);self.assertAlmostEqual(dep['english'],self.aA[0]['data']['hours'])
        depB=next(b for b in st['breakdown'] if b['kind']=='department' and b['id']==self.dB['id']);self.assertEqual(depB['english'],0)

    # TEST E : cinq utilisateurs simultanés sur la même base.
    def test_simultaneous_users(self):
        chefA,chefB,e1,e2=self.pilot_accounts();y=self.y
        me1=e1.send('bootstrap')[1]['me'];me2=e2.send('bootstrap')[1]['me'];secs={a['id']:self.sec(a)['id'] for a in self.aA[:6]+self.aB[:6]}
        def chef(c,acts,teacher):
            out=[]
            for a in acts[:6]:out.append(c.send('save',{'year':y,'kind':'assignment','data':{'activity':a['id'],'teacher':teacher,'group':secs[a['id']],'hours':1,'language':self.fr['id'],'state':'Validée'}})[0])
            return out
        def teacher(c,me,acts):return [c.send('wish-batch',{'year':y,'campaign':self.camp['id'],'teacher':me,'items':[{'activity':a['id'],'priority':i+1,'language':self.en['id']}]})[0] for i,a in enumerate(acts[6:10])]
        def admin():return [self.admin.send('bootstrap')[0] for _ in range(3)]
        with concurrent.futures.ThreadPoolExecutor(5) as ex:
            jobs=[ex.submit(chef,chefA,self.aA,me1),ex.submit(chef,chefB,self.aB,me2),ex.submit(teacher,e1,me1,self.aA),ex.submit(teacher,e2,me2,self.aB),ex.submit(admin)]
            results=[j.result() for j in jobs]
        self.assertTrue(all(code==200 for r in results for code in r),results)
        fresh=connect(server.DB)
        self.assertEqual(len(rows(fresh,y,'assignment')),12);self.assertEqual(len(rows(fresh,y,'wish')),8)
        l=[x for x in summary(fresh,y)['loads'] if x['period']=='1'];self.assertEqual({x['teacher']:x['assigned'] for x in l},{me1:6,me2:6})
        # Deux modifications concurrentes de la même fiche : la seconde est refusée, rien n'est écrasé.
        a=next(x for x in rows(fresh,y,'assignment') if x['data']['teacher']==me1);fresh.close()
        r1=chefA.send('save',{'year':y,'kind':'assignment','id':a['id'],'revision':a['revision'],'data':dict(a['data'],note='modif 1')})
        r2=chefA.send('save',{'year':y,'kind':'assignment','id':a['id'],'revision':a['revision'],'data':dict(a['data'],note='modif 2')})
        self.assertEqual(r1[0],200,r1);self.assertEqual(r2[0],400);self.assertIn('changé',r2[1]['error'])
if __name__=='__main__':unittest.main(verbosity=2)
