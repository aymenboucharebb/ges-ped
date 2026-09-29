import unittest,tempfile,pathlib,threading,json,urllib.request,urllib.error,http.cookiejar,base64,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import server,excel
from database import init
from support import TestDatabases
class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dbs=TestDatabases();cls.old=server.DB;server.DB=cls.dbs.fresh()
        cls.http=server.http.server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start();cls.url='http://127.0.0.1:'+str(cls.http.server_port)
        cls.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        cls.csrf='';cls.send('setup',{'name':'admin-test','password':'test-password-123'})
        cls.state=cls.send('bootstrap')[1];cls.csrf=cls.state['csrf'];cls.year=cls.state['year']
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.thread.join();server.DB=cls.old;cls.dbs.cleanup()
    @classmethod
    def send(cls,path,data=None,csrf=True,client=None,extra=None):
        headers={'Content-Type':'application/json'}
        if csrf:headers['X-CSRF-Token']=cls.csrf
        headers.update(extra or {})
        req=urllib.request.Request(cls.url+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:
            r=(client or cls.client).open(req);body=r.read();return r.status,json.loads(body) if r.headers['Content-Type'].startswith('application/json') else body
        except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
    def test_auth_required(self):
        status,_=self.send('bootstrap',client=urllib.request.build_opener());self.assertEqual(status,401)
    def test_csrf_required(self):
        status,_=self.send('save',{'year':self.year,'kind':'department','data':{'name':'No CSRF'}},csrf=False);self.assertEqual(status,400)
    def test_cross_origin_rejected(self):
        status,_=self.send('save',{'year':self.year,'kind':'department','data':{'name':'Cross origin'}},extra={'Origin':'https://example.org'});self.assertEqual(status,400)
    def test_setup_only_once(self):
        self.assertEqual(self.send('setup',{'name':'other','password':'test-password-123'})[0],400)
    def test_create_update_and_audit(self):
        status,r=self.send('save',{'year':self.year,'kind':'department','data':{'name':'Département HTTP'}});self.assertEqual(status,200)
        status,_=self.send('save',{'year':self.year,'kind':'department','id':r['id'],'revision':r['revision'],'data':{'name':'Département modifié'}});self.assertEqual(status,200)
        status,entries=self.send('audit?year='+self.year);self.assertEqual(status,200);self.assertTrue(any(e['action']=='Modification' for e in entries))
    def test_excel_export(self):
        status,content=self.send('export?year='+self.year+'&kind=subject');self.assertEqual(status,200);self.assertEqual(len(excel.read(content)),157)
    def test_excel_import_preview_commit(self):
        content=base64.b64encode(excel.export(['Libellé'],[['Grade HTTP']])).decode()
        status,p=self.send('import-preview',{'year':self.year,'kind':'grade','content':content});self.assertEqual(status,200);self.assertFalse(p['errors'])
        status,result=self.send('import',{'token':p['token']});self.assertEqual(status,200);self.assertEqual(result['count'],1)
        self.assertEqual(self.send('import',{'token':p['token']})[0],400)
    def test_bad_import_cannot_commit(self):
        content=base64.b64encode(excel.export(['Libellé','Code ISO (en, fr, ar...)'],[['Invalid','en']])).decode()
        status,p=self.send('import-preview',{'year':self.year,'kind':'language','content':content});self.assertEqual(status,200);self.assertTrue(p['errors'])
        self.assertEqual(self.send('import',{'token':p['token']})[0],400)
    def test_backup_and_preview_no_mutation(self):
        status,b=self.send('backup');self.assertEqual(status,200);status,p=self.send('restore-preview',{'backup':b});self.assertEqual(status,200);self.assertEqual(p['records'],len(b['records']))
        self.assertEqual(self.send('restore',{'token':p['token'],'password':'wrong'})[0],400)
    def test_user_consultation_write_denied(self):
        status,_=self.send('users',{'name':'reader-http','password':'reader-password','role':'Consultation','active':1});self.assertEqual(status,200)
        reader=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.assertEqual(self.send('login',{'name':'reader-http','password':'reader-password'},client=reader)[0],200)
        state=self.send('bootstrap',client=reader)[1]
        self.assertEqual(self.send('save',{'year':self.year,'kind':'department','data':{'name':'Forbidden'}},client=reader,extra={'X-CSRF-Token':state['csrf']})[0],400)
        self.assertEqual(self.send('backup',client=reader)[0],400)
    def test_no_last_admin_removal(self):
        users=self.send('users')[1];admin=next(u for u in users if u['name']=='admin-test')
        status,_=self.send('users',dict(admin,active=0));self.assertEqual(status,400)
    def login_as(self,name,password):
        c=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.assertEqual(self.send('login',{'name':name,'password':password},client=c)[0],200)
        st=self.send('bootstrap',client=c)[1];return c,st
    def test_teacher_confidentiality_http(self):
        import datetime
        st=self.state;rec=lambda k:[r for r in st['records'] if r['kind']==k]
        status=rec('status')[0]['id'];fr=next(r for r in rec('language') if r['data']['code']=='fr')['id']
        mk=lambda last:self.send('save',{'year':self.year,'kind':'teacher','data':{'last':last,'first':'Http','status':status,'load':'Normale'}})[1]
        t1=mk('Confidentiel');t2=mk('Collegue')
        for name,t in [('ens-un',t1),('ens-deux',t2)]:
            self.assertEqual(self.send('users',{'name':name,'password':'password-123456','role':'Enseignant','teacher':t['data']['person'],'active':1})[0],200)
        self.assertEqual(self.send('users',{'name':'doublon','password':'password-123456','role':'Enseignant','teacher':t1['data']['person'],'active':1})[0],400)
        today=datetime.date.today()
        camp=self.send('save',{'year':self.year,'kind':'campaign','data':{'name':'HTTP','period':'1','open':today.isoformat(),'deadline':(today+datetime.timedelta(days=3)).isoformat(),'status':'Ouverte'}})[1]
        acts=[a for a in rec('activity') if a['data']['category']=='Réglementaire' and next(s for s in rec('semester') if s['id']==a['context']['semester'])['data']['period']=='1'][:3]
        group=next(g for g in rec('group') if g['data']['level']==acts[0]['context']['level'] and g['data']['type']=='Section')
        cours=next(a for a in acts if next(t for t in rec('activitytype') if t['id']==a['data']['type'])['data']['name']=='Cours')
        asg=self.send('save',{'year':self.year,'kind':'assignment','data':{'activity':cours['id'],'teacher':t2['id'],'group':group['id'],'hours':2,'language':fr,'state':'Validée'}})
        self.assertEqual(asg[0],200,asg)
        c1,s1=self.login_as('ens-un','password-123456');c2,s2=self.login_as('ens-deux','password-123456')
        self.assertEqual(s1['me'],t1['id'])
        ok=self.send('wish-batch',{'year':self.year,'campaign':camp['id'],'teacher':t2['id'],'items':[{'activity':acts[0]['id'],'priority':1,'language':fr}]},client=c2,extra={'X-CSRF-Token':s2['csrf']})
        self.assertEqual(ok[0],200,ok)
        s1=self.send('bootstrap',client=c1)[1];ids={r['id'] for r in s1['records']}
        self.assertNotIn(t2['id'],ids);self.assertFalse([r for r in s1['records'] if r['kind'] in ['wish','assignment']])
        self.assertFalse([l for l in s1['summary']['loads'] if l['teacher']!=t1['id']])
        exp=self.send('export?year='+self.year+'&kind=assignment',client=c1)[1];self.assertEqual(len(excel.read(exp)),1)
        exp=self.send('export?year='+self.year+'&kind=teacher',client=c1)[1];self.assertEqual(len(excel.read(exp)),2)
        s2=self.send('bootstrap',client=c2)[1];wish=next(r for r in s2['records'] if r['kind']=='wish')
        self.assertEqual(self.send('history?id='+wish['id'],client=c1)[0],400)
        self.assertEqual(self.send('history?id='+wish['id'],client=c2)[0],200)
        self.assertEqual(self.send('audit?year='+self.year,client=c1)[0],400)
        h={'X-CSRF-Token':s1['csrf']}
        self.assertEqual(self.send('save',{'year':self.year,'kind':'wish','id':wish['id'],'revision':wish['revision'],'data':dict(wish['data'],priority=5)},client=c1,extra=h)[0],400)
        self.assertEqual(self.send('wish-batch',{'year':self.year,'campaign':camp['id'],'teacher':t2['id'],'items':[{'activity':acts[1]['id'],'priority':1,'language':fr}]},client=c1,extra=h)[0],400)
        self.assertEqual(self.send('save',{'year':self.year,'kind':'assignment','data':{'activity':cours['id'],'teacher':t1['id'],'group':group['id'],'hours':1,'language':fr,'state':'Validée'}},client=c1,extra=h)[0],400)
        self.assertEqual(self.send('users',client=c1)[0],400)
        self.assertEqual(self.send('password',{'old':'password-123456','new':'nouveau-mot-de-passe'},client=c1,extra=h)[0],200)
if __name__=='__main__':unittest.main(verbosity=2)
