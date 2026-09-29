"""Bases de test : SQLite (par défaut) ou PostgreSQL si GESPED_TEST_PG est défini (ex. postgresql://u:p@127.0.0.1)."""
import os,tempfile,pathlib,shutil,uuid,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from database import init
PG=os.environ.get('GESPED_TEST_PG')
class TestDatabases:
    def __init__(self):
        self.tmp=tempfile.TemporaryDirectory();self.created=[]
        if PG:
            import psycopg
            self.admin=psycopg.connect(PG.rstrip('/')+'/postgres',autocommit=True)
            self.base='gesped_base_'+uuid.uuid4().hex[:10];self.admin.execute(f'CREATE DATABASE {self.base}');self.created.append(self.base)
            init(self.url(self.base))
        else:
            self.base=pathlib.Path(self.tmp.name)/'base.sqlite';init(self.base)
    def url(self,name):return PG.rstrip('/')+'/'+name
    def fresh(self):
        if PG:
            name='gesped_t_'+uuid.uuid4().hex[:12];self.admin.execute(f'CREATE DATABASE {name} TEMPLATE {self.base}');self.created.append(name);return self.url(name)
        path=pathlib.Path(self.tmp.name)/(uuid.uuid4().hex+'.sqlite');shutil.copy2(self.base,path);return path
    def drop(self,target):
        if PG:
            name=str(target).rsplit('/',1)[1];self.admin.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')
            if name in self.created:self.created.remove(name)
    def cleanup(self):
        if PG:
            for name in list(self.created):self.admin.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')
            self.admin.close()
        self.tmp.cleanup()
