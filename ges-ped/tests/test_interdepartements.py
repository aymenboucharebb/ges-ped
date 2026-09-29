"""Version 1.1 : enseignants ENSF interdépartementaux, vœux, confidentialité, taux d'anglais."""
import unittest,tempfile,pathlib,sys,shutil,json,datetime,sqlite3
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from database import *
from support import TestDatabases
from domain import *
ADMIN={'id':'admin','name':'Admin','role':'Administrateur'}
TODAY=datetime.date.today()
class InterDepartementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dbs=TestDatabases()
    @classmethod
    def tearDownClass(cls):cls.dbs.cleanup()
    def setUp(self):
        self.path=self.dbs.fresh();self.db=connect(self.path);self.y='2026-2027'
        d=self.db;y=self.y
        self.depA=self.add('department',name='Département A');self.depB=self.add('department',name='Département B')
        tracks=rows(d,y,'track')
        self.trackA=next(t for t in tracks if t['data']['name']=='Formation de base');self.trackB=next(t for t in tracks if t['data']['name']=='Sciences forestières')
        self.change(self.trackA,department=self.depA['id']);self.change(self.trackB,department=self.depB['id'])
        self.en=self.lang('en');self.fr=self.lang('fr')
        self.status=rows(d,y,'status')[0]['id']
        self.room=self.add('room',name='Amphi 1',capacity=200,type=rows(d,y,'roomtype')[0]['id'])
        self.room2=self.add('room',name='Amphi 2',capacity=200,type=rows(d,y,'roomtype')[0]['id'])
        for s in rows(d,y,'semester'):self.change(s,start='2026-09-27')
        for g in rows(d,y,'group'):
            if g['data']['type']=='Groupe':self.change(g,size=25)
    def tearDown(self):
        self.db.close();self.dbs.drop(self.path)
    def lang(self,code):return next(r for r in rows(self.db,self.y,'language') if r['data']['code']==code)
    def add(self,kind,user=ADMIN,**data):return save(self.db,user,self.y,kind,data)
    def change(self,r,user=ADMIN,**data):
        r=get(self.db,r['id']);return save(self.db,user,self.y,r['kind'],dict(r['data'],**data),r['id'],r['revision'])
    def activity(self,track,typ='Cours',period='1',skip=0):
        found=[a for a in rows(self.db,self.y,'activity') if a['data']['category']=='Réglementaire' and get(self.db,a['data']['type'])['data']['name']==typ
               and context(self.db,a).get('track')==track['id'] and get(self.db,context(self.db,a)['semester'])['data']['period']==period]
        return found[skip]
    def public(self,act,kind='Section',n=0):
        level=context(self.db,act)['level']
        return [g for g in rows(self.db,self.y,'group') if g['data']['level']==level and g['data']['type']==kind][n]
    def teacher(self,last,dept=None,**kw):
        return self.add('teacher',**dict(dict(last=last,first='Test',status=self.status,load='Normale',department=dept and dept['id']),**kw))
    def assign(self,act,teacher,hours,lang=None,group=None,user=ADMIN,**kw):
        return self.add('assignment',user=user,**dict(dict(activity=act['id'],teacher=teacher['id'],group=(group or self.public(act))['id'],hours=hours,language=(lang or self.fr)['id'],state='Validée'),**kw))
    def user(self,role,teacher=None,dept=None):
        return {'id':role,'name':role+'-test','role':role,'department':dept and dept['id'],'teacher':teacher and teacher['data']['person']}
    def campaign(self,period='1',**kw):
        return self.add('campaign',**dict(dict(name='Vœux S1',period=period,open=(TODAY-datetime.timedelta(days=1)).isoformat(),deadline=(TODAY+datetime.timedelta(days=10)).isoformat(),status='Ouverte'),**kw))
    def wish(self,camp,teacher,act,user,priority=1,lang=None,**kw):
        return self.add('wish',user=user,**dict(dict(campaign=camp['id'],teacher=teacher['id'],activity=act['id'],priority=priority,language=(lang or self.fr)['id'],state='En attente'),**kw))
    def load(self,teacher,period='1'):return next(l for l in summary(self.db,self.y)['loads'] if l['teacher']==teacher['id'] and l['period']==period)

    # 1. Un enseignant, deux départements, une seule fiche.
    def test_teacher_in_two_departments_single_profile(self):
        x=self.teacher('Dr X',self.depA);aA=self.activity(self.trackA);aB=self.activity(self.trackB)
        self.assertEqual(dept_of(self.db,aA),self.depA['id']);self.assertEqual(dept_of(self.db,aB),self.depB['id'])
        a1=self.assign(aA,x,10);a2=self.assign(aB,x,12)
        self.assertEqual(dept_of(self.db,a2),self.depB['id'],'Le département d’un enseignement est celui de la matière, pas celui de l’enseignant.')
        self.assertEqual(len(rows(self.db,self.y,'teacher')),1)
    def test_teacher_without_department_can_teach(self):
        x=self.teacher('Sans rattachement');self.assign(self.activity(self.trackA),x,5);self.assign(self.activity(self.trackB),x,5)
    def test_duplicate_teacher_forbidden(self):
        self.teacher('Dupont',self.depA)
        with self.assertRaisesRegex(Invalid,'une seule fiche|Une seule fiche'):self.teacher('DUPONT',self.depB)
        self.teacher('Martin',code='M1')
        with self.assertRaisesRegex(Invalid,'matricule'):self.teacher('Autre',code='m1')
        self.teacher('Homonyme',code='H1');self.teacher('Homonyme',code='H2')  # vrais homonymes, matricules distincts

    # 2. Charge globale interdépartementale.
    def test_global_load_across_departments(self):
        x=self.teacher('Dr X',self.depA);aA=self.activity(self.trackA);aB=self.activity(self.trackB)
        hA=min(aA['data']['hours'],50);hB=min(aB['data']['hours'],46)
        self.assign(aA,x,hA);self.assign(aB,x,hB)
        l=self.load(x)
        self.assertAlmostEqual(l['assigned'],hA+hB);self.assertAlmostEqual(l['depts'][self.depA['id']],hA);self.assertAlmostEqual(l['depts'][self.depB['id']],hB)
        self.assertEqual(l['target'],96);self.assertEqual(l['status'],'Sous-charge' if hA+hB<96 else 'Charge atteinte')
        ann=next(a for a in summary(self.db,self.y)['annual'] if a['teacher']==x['id']);self.assertEqual(ann['target'],192);self.assertAlmostEqual(ann['assigned'],hA+hB)
    def test_overload_detected_on_total(self):
        x=self.teacher('Dr Y',load='Personnalisée',target=20,decision='D-1')
        aA=self.activity(self.trackA);aB=self.activity(self.trackB)
        self.assign(aA,x,12);self.assertEqual(self.load(x)['status'],'Sous-charge')
        self.assign(aB,x,12)  # 12 h + 12 h : chaque département isolément reste sous 20 h, le total ENSF dépasse.
        l=self.load(x);self.assertEqual(l['status'],'Dépassement');self.assertAlmostEqual(l['gap'],4)
    def test_half_load_target(self):
        x=self.teacher('Demi',load='Demi-charge',decision='D2',decision_date='2026-09-01');self.assertEqual(self.load(x)['target'],48)

    # 3. Conflits d'emploi du temps entre départements.
    def test_cross_department_teacher_conflict(self):
        x=self.teacher('Dr X',self.depA);aA=self.assign(self.activity(self.trackA),x,6);aB=self.assign(self.activity(self.trackB),x,6)
        self.add('slot',assignment=aA['id'],room=self.room['id'],day='Lundi',start='08:00',duration=1.5,weeks='1,2')
        with self.assertRaisesRegex(Invalid,'Conflit.*enseignant.*autre département'):
            self.add('slot',assignment=aB['id'],room=self.room2['id'],day='Lundi',start='08:00',duration=1.5,weeks='1,2')
        self.add('slot',assignment=aB['id'],room=self.room2['id'],day='Lundi',start='11:00',duration=1.5,weeks='1,2')
    def test_cross_department_group_and_room_conflict(self):
        aA=self.activity(self.trackA);subjB=get(self.db,self.activity(self.trackA,skip=1)['data']['subject'])
        self.change(subjB,department=self.depB['id'])  # matière du même niveau confiée au département B
        aB=next(a for a in rows(self.db,self.y,'activity') if a['data']['subject']==subjB['id'] and get(self.db,a['data']['type'])['data']['name']=='Cours')
        self.assertEqual(dept_of(self.db,aB),self.depB['id'])
        x=self.teacher('X');y=self.teacher('Y')
        s1=self.assign(aA,x,6);s2=self.assign(aB,y,6)
        self.add('slot',assignment=s1['id'],room=self.room['id'],day='Mardi',start='08:00',duration=1.5,weeks='1')
        with self.assertRaisesRegex(Invalid,'section / groupe'):self.add('slot',assignment=s2['id'],room=self.room2['id'],day='Mardi',start='08:00',duration=1.5,weeks='1')
        z=self.teacher('Z');other=self.assign(self.activity(self.trackB,skip=2),z,6)
        with self.assertRaisesRegex(Invalid,'salle'):self.add('slot',assignment=other['id'],room=self.room['id'],day='Mardi',start='08:00',duration=1.5,weeks='1')

    # 4. Vœux dans deux départements, arbitrage par le chef du département de la matière.
    def test_wishes_in_two_departments(self):
        x=self.teacher('Dr X',self.depA);ux=self.user('Enseignant',x);camp=self.campaign()
        aA=self.activity(self.trackA);aB=self.activity(self.trackB,'TD') if any(get(self.db,a['data']['type'])['data']['name']=='TD' and context(self.db,a).get('track')==self.trackB['id'] for a in rows(self.db,self.y,'activity')) else self.activity(self.trackB)
        wA=self.wish(camp,x,aA,ux,1,self.en);wB=self.wish(camp,x,aB,ux,2)
        chefA=self.user('Chef de département',dept=self.depA);chefB=self.user('Chef de département',dept=self.depB)
        self.change(wA,chefA,state='Acceptée',decision_note='OK');w=get(self.db,wA['id'])['data']
        self.assertEqual((w['decided_by'],w['state']),('Chef de département-test','Acceptée'));self.assertTrue(w['decision_date'])
        with self.assertRaisesRegex(Invalid,'autre département'):self.change(wB,chefA,state='Refusée')
        self.change(wB,chefB,state='Refusée',decision_note='Déjà pourvu')
        with self.assertRaisesRegex(Invalid,'demande de l’enseignant'):self.change(get(self.db,wA['id']),chefA,priority=3)
        self.assertEqual(get(self.db,wB['id'])['data']['state'],'Refusée')  # vœu refusé historisé
    def test_wishes_not_limited_by_load_and_several_candidates(self):
        x=self.teacher('Dr X',load='Personnalisée',target=5,decision='D');y=self.teacher('Dr Y');camp=self.campaign()
        ux=self.user('Enseignant',x);uy=self.user('Enseignant',y)
        acts=[self.activity(self.trackA,skip=i) for i in range(4)]
        for i,a in enumerate(acts):self.wish(camp,x,a,ux,i+1)  # bien au-delà de 5 h
        self.wish(camp,y,acts[0],uy,1)  # deux candidats pour la même activité : aucun blocage
        with self.assertRaisesRegex(Invalid,'existe déjà'):self.wish(camp,x,acts[0],ux,2)
        self.assertEqual(len([w for w in rows(self.db,self.y,'wish') if w['data']['activity']==acts[0]['id']]),2)
    def test_wish_campaign_rules(self):
        x=self.teacher('Dr X');ux=self.user('Enseignant',x);a=self.activity(self.trackA)
        closed=self.campaign(status='Clôturée')
        with self.assertRaisesRegex(Invalid,'pas ouverte'):self.wish(closed,x,a,ux)
        late=self.campaign(deadline=(TODAY-datetime.timedelta(days=1)).isoformat(),open=(TODAY-datetime.timedelta(days=5)).isoformat())
        with self.assertRaisesRegex(Invalid,'Dépôt des vœux possible'):self.wish(late,x,a,ux)
        other_period=self.campaign(period='2')
        with self.assertRaisesRegex(Invalid,'semestre de la campagne'):self.wish(other_period,x,a,ux)
        deptB=self.campaign(department=self.depB['id'])
        with self.assertRaisesRegex(Invalid,'département de la campagne'):self.wish(deptB,x,a,ux)
    def test_teacher_wish_lifecycle(self):
        x=self.teacher('Dr X');ux=self.user('Enseignant',x);camp=self.campaign();a=self.activity(self.trackA)
        w=self.wish(camp,x,a,ux);w=self.change(w,ux,priority=2);self.assertTrue(w['data']['updated'])
        with self.assertRaisesRegex(Invalid,'chef du département'):self.change(w,ux,state='Acceptée')
        w=self.change(w,ux,state='Retirée');self.assertEqual(w['data']['state'],'Retirée')
        with self.assertRaisesRegex(Invalid,'retiré'):self.change(w,ADMIN,state='Acceptée')
        w2=self.wish(camp,x,a,ux)  # nouveau vœu possible après retrait
        self.change(w2,self.user('Chef de département',dept=self.depA),state='Acceptée')
        with self.assertRaisesRegex(Invalid,'déjà été traité'):self.change(w2,ux,note='modification tardive')
    def test_teacher_cannot_self_assign(self):
        x=self.teacher('Dr X');ux=self.user('Enseignant',x)
        with self.assertRaisesRegex(Invalid,'chef de département'):self.assign(self.activity(self.trackA),x,3,user=ux)

    # 5. Affectation par un chef d'un enseignant venant d'un autre département.
    def test_chef_assigns_teacher_from_other_department(self):
        chefA=self.user('Chef de département',dept=self.depA);y=self.teacher('Dr Y',self.depB);v=self.teacher('Vacataire',status=rows(self.db,self.y,'status')[-1]['id'])
        aA=self.activity(self.trackA);aB=self.activity(self.trackB)
        a=self.assign(aA,y,4,user=chefA);self.assign(aA,v,4,user=chefA,group=self.public(aA))
        with self.assertRaisesRegex(Invalid,'autre département'):self.assign(aB,y,4,user=chefA)
        b=self.assign(aB,y,4)
        with self.assertRaisesRegex(Invalid,'autre département'):self.change(b,chefA,hours=3)
        with self.assertRaisesRegex(Invalid,'autre département'):self.change(a,chefA,activity=aB['id'],group=self.public(aB)['id'])
        with self.assertRaisesRegex(Invalid,'direction'):self.change(aA,chefA,hours=99)  # programme : consultation
        with self.assertRaisesRegex(Invalid,'direction'):self.change(y,chefA,first='Modifié')
    def test_assignment_from_wish(self):
        x=self.teacher('Dr X');y=self.teacher('Dr Y');ux=self.user('Enseignant',x);camp=self.campaign();a=self.activity(self.trackA)
        chef=self.user('Chef de département',dept=self.depA);w=self.wish(camp,x,a,ux,1,self.en)
        with self.assertRaisesRegex(Invalid,'vœu accepté'):self.assign(a,x,3,self.en,user=chef,wish=w['id'])
        self.change(w,chef,state='Acceptée partiellement',decision_note='TD seulement')
        with self.assertRaisesRegex(Invalid,'même enseignant'):self.assign(a,y,3,self.en,user=chef,wish=w['id'])
        asg=self.assign(a,x,3,self.fr,user=chef,wish=w['id'])  # langue finalement retenue différente de la langue souhaitée
        self.assertEqual(asg['data']['wish'],w['id'])
        with self.assertRaisesRegex(Invalid,'affectation a été créée'):self.change(w,chef,state='Refusée')
        self.assign(a,y,3,self.fr,user=chef)  # affectation manuelle sans vœu

    # 6. Confidentialité entre enseignants (backend).
    def test_confidentiality_between_teachers(self):
        x=self.teacher('Dr X',self.depA);y=self.teacher('Dr Y',self.depA);ux=self.user('Enseignant',x);uy=self.user('Enseignant',y)
        camp=self.campaign();a=self.activity(self.trackA);b=self.activity(self.trackB)
        self.wish(camp,x,a,ux);wy=self.wish(camp,y,a,uy);ay=self.assign(b,y,4);ax=self.assign(a,x,4)
        self.add('slot',assignment=ay['id'],room=self.room['id'],day='Lundi',start='08:00',duration=1.5,weeks='1')
        seen=visible(self.db,self.y,ux);ids={r['id'] for r in seen}
        self.assertNotIn(y['id'],ids);self.assertNotIn(wy['id'],ids);self.assertNotIn(ay['id'],ids)
        self.assertFalse([r for r in seen if r['kind']=='slot'])
        self.assertIn(ax['id'],ids);self.assertIn(x['id'],ids)
        s=scoped_summary(self.db,self.y,ux,seen)
        self.assertEqual({l['teacher'] for l in s['loads']},{x['id']});self.assertEqual({l['teacher'] for l in s['annual']},{x['id']})
        self.assertFalse(s['busy']);self.assertFalse(s['coverage'])
        with self.assertRaisesRegex(Invalid,'propres vœux'):self.wish(camp,y,b,ux)
        with self.assertRaisesRegex(Invalid,'propres vœux'):self.change(wy,ux,priority=4)
        with self.assertRaisesRegex(Invalid,'propre profil'):self.change(y,ux,english_level='C2')
        self.change(x,ux,english_level='B2',english_ok='Oui')
        with self.assertRaisesRegex(Invalid,'seuls le niveau'):self.change(x,ux,load='Demi-charge',decision='1',decision_date='2026-01-01')
    def test_chef_scope_sees_global_loads_not_other_department_details(self):
        x=self.teacher('Dr X',self.depB);aB=self.assign(self.activity(self.trackB),x,10);aA=self.assign(self.activity(self.trackA),x,6)
        self.add('slot',assignment=aB['id'],room=self.room['id'],day='Lundi',start='08:00',duration=1.5,weeks='1')
        chefA=self.user('Chef de département',dept=self.depA);seen=visible(self.db,self.y,chefA);ids={r['id'] for r in seen}
        self.assertIn(aA['id'],ids);self.assertNotIn(aB['id'],ids);self.assertIn(x['id'],ids)
        s=scoped_summary(self.db,self.y,chefA,seen);l=next(l for l in s['loads'] if l['teacher']==x['id'] and l['period']=='1')
        self.assertAlmostEqual(l['assigned'],16);self.assertEqual(set(l['depts']),{self.depA['id'],self.depB['id']})
        b=next(b for b in s['busy'] if b['teacher']==x['id']);self.assertEqual(b['department'],self.depB['id']);self.assertNotIn('activity',b)

    # 7. Taux d'enseignement en anglais.
    def test_english_rate_from_assignments(self):
        e=summary(self.db,self.y)['english'];self.assertEqual((e['total'],e['english'],e['rate']),(5625,0,0))
        cours=self.activity(self.trackA);h=cours['data']['hours']
        x=self.teacher('X');y=self.teacher('Y')
        self.assign(cours,x,h/2,self.en);self.assign(cours,y,h/2,self.fr)  # activité partagée : moitié anglais
        st=summary(self.db,self.y)['activityStats'][cours['id']];self.assertAlmostEqual(st['english'],h/2);self.assertAlmostEqual(st['assigned'],h)
        td=self.activity(self.trackA,'TD');groups=[g for g in rows(self.db,self.y,'group') if g['data']['level']==context(self.db,td)['level'] and g['data']['type']=='Groupe']
        for i,g in enumerate(groups):self.assign(td,x,td['data']['hours'],self.en if i==0 else self.fr,group=g)
        s=summary(self.db,self.y);st=s['activityStats'][td['id']]
        self.assertAlmostEqual(st['english'],td['data']['hours']/len(groups))  # un groupe sur quatre en anglais, sans multiplier le volume
        self.assertAlmostEqual(st['assigned'],td['data']['hours'])
        e=s['english'];self.assertEqual(e['total'],5625)
        self.assertAlmostEqual(e['english'],h/2+td['data']['hours']/len(groups));self.assertAlmostEqual(e['rate'],e['english']/5625*100)
        dep=next(b for b in s['breakdown'] if b['kind']=='department' and b['id']==self.depA['id']);self.assertAlmostEqual(dep['english'],e['english'])
        self.assertTrue(any(b['kind']=='period' for b in s['breakdown']))
        ld=next(l for l in s['loads'] if l['teacher']==x['id'] and l['period']=='1');self.assertAlmostEqual(ld['english'],h/2+td['data']['hours'])
    def test_draft_assignments_excluded_from_english_rate(self):
        a=self.activity(self.trackA);self.assign(a,self.teacher('X'),a['data']['hours'],self.en,state='Brouillon')
        self.assertEqual(summary(self.db,self.y)['english']['english'],0)

    # 8. Migration sans perte depuis la version 1.0.
    def test_migration_from_v1(self):
        d=self.db;a=rows(d,self.y,'activity')[0]
        set_json(d,a['id'],'language',self.en['id'])
        t1=self.teacher('Ancien',code='A1');t1d=dict(t1['data']);t1d.pop('person')
        d.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(t1d),t1['id']))
        d.execute('DELETE FROM migrations WHERE version>=2');d.commit()
        migrate(d,self.path);d.commit()
        a2=get(d,a['id'])['data'];self.assertNotIn('language',a2);self.assertIn('Anglais',a2['note'])
        self.assertTrue(get(d,t1['id'])['data']['person'])
        if not getattr(d,'pg',False):self.assertTrue(list((self.path.parent/'sauvegardes').glob('avant-migration-v1.1-*.sqlite')))
        self.assertEqual(d.execute('SELECT MAX(version) FROM migrations').fetchone()[0],4)
        if not getattr(d,'pg',False):self.assertEqual(d.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_year_copy_keeps_person_not_wishes(self):
        x=self.teacher('Dr X');self.wish(self.campaign(),x,self.activity(self.trackA),self.user('Enseignant',x))
        year=duplicate_year(self.db,ADMIN,self.y,'2027 / 2028')
        self.assertEqual(rows(self.db,year,'teacher')[0]['data']['person'],x['data']['person'])
        self.assertFalse(rows(self.db,year,'wish'));self.assertFalse(rows(self.db,year,'campaign'))
if __name__=='__main__':unittest.main(verbosity=2)
