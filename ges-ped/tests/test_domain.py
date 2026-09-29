import unittest,tempfile,pathlib,sys,shutil,json,datetime
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from database import *
from support import TestDatabases
from domain import *
import excel
ADMIN={'id':'test','name':'Test','role':'Administrateur'}
class DomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dbs=TestDatabases()
    @classmethod
    def tearDownClass(cls):cls.dbs.cleanup()
    def setUp(self):
        self.path=self.dbs.fresh();self.db=connect(self.path);self.y='2026-2027'
    def tearDown(self):
        self.db.close();self.dbs.drop(self.path)
    def add(self,kind,**data):return save(self.db,ADMIN,self.y,kind,data)
    def change(self,r,**data):return save(self.db,ADMIN,self.y,r['kind'],dict(r['data'],**data),r['id'],r['revision'])
    def fixture(self,hours=3):
        d=self.db;y=self.y
        act=next(r for r in rows(d,y,'activity') if get(d,r['data']['type'])['data']['name']=='Cours')
        en=next(r for r in rows(d,y,'language') if r['data']['code']=='en')
        ctx=context(d,act);sem=get(d,ctx['semester']);sem=self.change(sem,start='2026-09-27')
        group=next(r for r in rows(d,y,'group') if r['data']['level']==ctx['level'] and r['data']['type']=='Section');group=self.change(group,size=30)
        teacher=self.add('teacher',last='Test',first='Enseignant',status=rows(d,y,'status')[0]['id'],load='Normale')
        room=self.add('room',name='Salle test',capacity=35,type=rows(d,y,'roomtype')[0]['id'])
        a=self.add('assignment',activity=act['id'],teacher=teacher['id'],group=group['id'],hours=hours,language=en['id'],state='Validée')
        return act,sem,group,teacher,room,a
    def slot(self,a,room,**kw):return self.add('slot',**dict(dict(assignment=a['id'],room=room['id'],day='Lundi',start='08:00',duration=1.5,weeks='1,2'),**kw))
    def test_seed_no_real_assignments(self):
        self.assertEqual(len(rows(self.db,self.y,'subject')),156);self.assertEqual(len(rows(self.db,self.y,'activity')),283)
        for k in ['teacher','assignment','slot','session','room']:self.assertEqual(rows(self.db,self.y,k),[])
    def test_unknown_language_not_claimed_french(self):
        e=summary(self.db,self.y)['english'];self.assertEqual(e['total'],5625);self.assertEqual(e['english'],0);self.assertEqual(e['coverage'],0)
        self.assertFalse(any('language' in r['data'] for r in rows(self.db,self.y,'activity')))
    def test_english_not_multiplied_by_groups(self):
        act,*_=self.fixture(48);e=summary(self.db,self.y)['english'];self.assertEqual(e['english'],48);self.assertEqual(e['total'],5625)
    def test_multi_teacher_split_and_overflow(self):
        act,s,g,t,r,a=self.fixture(24);t2=self.add('teacher',last='Second',first='Prof',status=t['data']['status'],load='Normale')
        self.add('assignment',**dict(a['data'],teacher=t2['id'],hours=24))
        with self.assertRaisesRegex(Invalid,'Dépassement'):self.add('assignment',**dict(a['data'],hours=1))
    def test_cross_level_group_rejected(self):
        act,s,g,t,r,a=self.fixture();other=next(x for x in rows(self.db,self.y,'group') if x['data']['level']!=g['data']['level'])
        with self.assertRaisesRegex(Invalid,'niveau'):self.add('assignment',**dict(a['data'],group=other['id']))
    def test_half_load_requires_decision(self):
        with self.assertRaisesRegex(Invalid,'décision'):self.add('teacher',last='X',first='Y',status=rows(self.db,self.y,'status')[0]['id'],load='Demi-charge')
    def test_equivalence_and_three_loads(self):
        act,s,g,t,r,a=self.fixture();slot=self.slot(a,r);generate(self.db,ADMIN,self.y);ss=rows(self.db,self.y,'session')[0];self.change(ss,state='Réalisée',actual=1.5)
        load=next(x for x in summary(self.db,self.y)['loads'] if x['teacher']==t['id'] and x['period']=='1')
        self.assertEqual((load['assigned'],load['planned'],load['actual'],load['target']),(3,3,1.5,96))
        tp=next(x for x in rows(self.db,self.y,'activitytype') if x['data']['name']=='TP');self.assertAlmostEqual(tp['data']['factor']*21,14)
    def test_weeks(self):
        self.assertEqual(weeks('1-3,5,3',14),[1,2,3,5]);self.assertEqual(len(weeks('toutes',14)),14)
        for invalid in ['0','15','4-2','a','1,', '-1']:
            with self.assertRaises(Invalid):weeks(invalid,14)
    def test_room_capacity(self):
        act,s,g,t,r,a=self.fixture();r=self.change(r,capacity=20)
        with self.assertRaisesRegex(Invalid,'Capacité'):self.slot(a,r)
    def test_unknown_capacity_group(self):
        act,s,g,t,r,a=self.fixture();set_json(self.db,g['id'],'size',None)
        with self.assertRaisesRegex(Invalid,'effectif'):self.slot(a,r)
    def test_room_type(self):
        act,s,g,t,r,a=self.fixture();other=next(x for x in rows(self.db,self.y,'roomtype') if x['id']!=r['data']['type']);set_json(self.db,act['id'],'roomtype',other['id'])
        with self.assertRaisesRegex(Invalid,'Type de salle'):self.slot(a,r)
    def test_calendar_conflict(self):
        *_,r,a=self.fixture(6);self.slot(a,r)
        with self.assertRaisesRegex(Invalid,'Conflit'):self.slot(a,r,weeks='2,3')
    def test_ensf_week_and_slots(self):
        *_,r,a=self.fixture(12)
        with self.assertRaisesRegex(Invalid,'créneaux'):self.slot(a,r,start='08:30')
        with self.assertRaisesRegex(Invalid,'créneaux'):self.slot(a,r,start='11:00',duration=3)  # chevauche la pause
        with self.assertRaisesRegex(Invalid,'choix inconnu'):self.slot(a,r,day='Samedi')
        self.slot(a,r,start='08:00',duration=3,weeks='1');self.slot(a,r,day='Dimanche',start='13:30',weeks='1');self.slot(a,r,day='Jeudi',start='15:00',weeks='1')
        generate(self.db,ADMIN,self.y);self.assertEqual(sorted(x['data']['date'] for x in rows(self.db,self.y,'session')),['2026-09-27','2026-09-28','2026-10-01'])
        with self.assertRaisesRegex(Invalid,'dimanche'):self.change(get(self.db,context(self.db,a)['semester']),start='2026-09-28')
    def test_non_overlapping_weeks(self):
        *_,r,a=self.fixture(6);self.slot(a,r);self.slot(a,r,weeks='3,4')
    def test_planned_overflow(self):
        *_,r,a=self.fixture(3)
        with self.assertRaisesRegex(Invalid,'dépasse'):self.slot(a,r,weeks='1-3')
    def test_unavailability(self):
        act,s,g,t,r,a=self.fixture();self.add('unavailable',name='Réunion',teacher=t['id'],date='2026-09-28',start='08:00',end='10:00')
        with self.assertRaisesRegex(Invalid,'Indisponibilité'):self.slot(a,r)
    def test_unavailability_after_booking_rejected(self):
        act,s,g,t,r,a=self.fixture();self.slot(a,r)
        with self.assertRaisesRegex(Invalid,'séance'):self.add('unavailable',name='Réunion',teacher=t['id'],date='2026-09-28',start='08:00',end='10:00')
    def test_generate_idempotent(self):
        *_,r,a=self.fixture();self.slot(a,r);self.assertEqual(generate(self.db,ADMIN,self.y),2);self.assertEqual(generate(self.db,ADMIN,self.y),0)
        self.assertEqual(sorted(x['data']['date'] for x in rows(self.db,self.y,'session')),['2026-09-28','2026-10-05'])
    def test_makeup_link_and_actual(self):
        *_,r,a=self.fixture();self.slot(a,r);generate(self.db,ADMIN,self.y);s=rows(self.db,self.y,'session')[0];s=self.change(s,state='Annulée')
        self.add('session',assignment=a['id'],room=r['id'],date='2026-10-06',start='08:00',duration=1.5,state='Réalisée',actual=1.5,replaces=s['id'])
        p=summary(self.db,self.y)['progression'][0];self.assertEqual(p['actual'],1.5);self.assertEqual(p['makeups'],1.5);self.assertEqual(p['planned'],3)
    def test_invalid_realized_duration(self):
        *_,r,a=self.fixture()
        with self.assertRaisesRegex(Invalid,'entièrement'):self.add('session',assignment=a['id'],room=r['id'],date='2026-09-28',start='08:00',duration=1.5,state='Réalisée',actual=1)
    def test_partial_makeup_no_double_planned(self):
        *_,r,a=self.fixture();self.slot(a,r);generate(self.db,ADMIN,self.y);s=rows(self.db,self.y,'session')[0];s=self.change(s,state='Partiellement réalisée',actual=.5)
        self.add('session',assignment=a['id'],room=r['id'],date='2026-10-06',start='08:00',duration=1,state='Réalisée',actual=1,replaces=s['id'])
        p=summary(self.db,self.y)['progression'][0];self.assertEqual(p['actual'],1.5);self.assertEqual(p['planned'],3)
    def test_makeup_origin_cannot_double_realized(self):
        *_,r,a=self.fixture(48);self.slot(a,r);generate(self.db,ADMIN,self.y);s=rows(self.db,self.y,'session')[0];s=self.change(s,state='Annulée')
        self.add('session',assignment=a['id'],room=r['id'],date='2026-10-06',start='08:00',duration=1.5,state='Réalisée',actual=1.5,replaces=s['id'])
        with self.assertRaisesRegex(Invalid,'rattrapages'):self.change(s,state='Réalisée',actual=1.5)
    def test_semester_date_edit_before_scheduling(self):
        act,s,g,t,r,a=self.fixture();self.change(s,start='2026-10-04')
    def test_unchanged_numeric_string_allowed(self):
        act,s,g,t,r,a=self.fixture();slot=self.slot(a,r)
        self.change(a,hours='3',note='Observation ajoutée')
    def test_closed_year_immutable(self):
        self.db.execute('UPDATE years SET closed=1 WHERE id=?',(self.y,))
        with self.assertRaisesRegex(Invalid,'clôturée'):self.add('department',name='Nouveau')
    def test_year_copy_isolated_no_assignments(self):
        act,*_=self.fixture();year=duplicate_year(self.db,ADMIN,self.y,'2027 / 2028');self.assertFalse(rows(self.db,year,'assignment'));self.assertEqual(len(rows(self.db,year,'teacher')),1)
        r=rows(self.db,year,'subject')[0];save(self.db,ADMIN,year,'subject',dict(r['data'],name='Renommé'),r['id'],r['revision']);self.assertNotEqual(rows(self.db,self.y,'subject')[0]['data']['name'],'Renommé')
        self.assertFalse(any(s['data'].get('start') for s in rows(self.db,year,'semester')))
    def test_consultation_cannot_write(self):
        with self.assertRaisesRegex(Invalid,'consultation'):save(self.db,{'role':'Consultation'},self.y,'department',{'name':'X'})
    def test_department_scope(self):
        with self.assertRaises(Invalid):save(self.db,{'role':'Chef de département','department':'x'},self.y,'department',{'name':'X'})
    def test_optimistic_lock(self):
        d=self.add('department',name='A');self.change(d,name='B')
        with self.assertRaisesRegex(Invalid,'changé'):self.change(d,name='C')
    def test_used_program_immutable_volume(self):
        a,*_=self.fixture()
        with self.assertRaisesRegex(Invalid,'utilisée'):self.change(a,hours=20)
    def test_reference_rejects_other_year(self):
        year=duplicate_year(self.db,ADMIN,self.y,'2027');other=rows(self.db,year,'cycle')[0]
        with self.assertRaisesRegex(Invalid,'autre année'):self.add('track',name='X',cycle=other['id'])
    def test_numbers_reject_nan(self):
        with self.assertRaises(Invalid):self.add('room',name='X',capacity='NaN',type=rows(self.db,self.y,'roomtype')[0]['id'])
    def test_backup_restore(self):
        import server
        original=server.backup(self.db);self.add('department',name='Temp');server.restore(self.db,original,ADMIN)
        self.assertFalse(rows(self.db,self.y,'department'));self.assertEqual(len(rows(self.db,self.y,'subject')),156)
    def test_xlsx_roundtrip_strings_safe(self):
        content=excel.export(['Nom','Nombre'],[['=HYPERLINK("x")',1.5],['Forêt',2]])
        self.assertEqual(excel.read(content),[['Nom','Nombre'],['=HYPERLINK("x")','1.5'],['Forêt','2']])
    def test_group_ancestors_conflict(self):
        g=next(r for r in rows(self.db,self.y,'group') if r['data']['type']=='Groupe');self.assertTrue(group_conflict(self.db,g['id'],g['data']['parent']))
    def test_coverage_subgroups(self):
        g=next(r for r in rows(self.db,self.y,'group') if r['data']['type']=='Groupe')
        one=self.add('group',name='SG1',level=g['data']['level'],parent=g['id'],type='Sous-groupe',size=15)
        two=self.add('group',name='SG2',level=g['data']['level'],parent=g['id'],type='Sous-groupe',size=15)
        cov=summary(self.db,self.y)['coverage'];self.assertFalse(any(x['group']==g['id'] for x in cov));self.assertTrue(any(x['group']==one['id'] for x in cov));self.assertTrue(any(x['group']==two['id'] for x in cov))
    def test_rule_versions(self):
        old=rows(self.db,self.y,'rule')[0];new=self.add('rule',**dict(old['data'],name='Nouvelle règle',normal=90))
        self.assertEqual(get(self.db,old['id'])['active'],0);self.assertEqual(get(self.db,new['id'])['active'],1)
if __name__=='__main__':unittest.main(verbosity=2)
