"""Commandes d'administration du serveur ges-ped (à lancer sur le serveur, jamais par les utilisateurs).

  python3 manage.py init                      crée / met à jour la base
  python3 manage.py create-admin [identifiant] crée le premier administrateur (mot de passe temporaire affiché une fois)
  python3 manage.py reset-password identifiant  nouveau mot de passe temporaire
  python3 manage.py users                      liste des comptes
  python3 manage.py check                      diagnostic (base, comptes, version)
"""
import sys,os
from database import connect,init,uid,now,password_hash,temporary_password,DEFAULT_DB,is_pg
import server
def main(argv):
    if not argv or argv[0] in ['-h','--help','help']:print(__doc__);return 0
    cmd=argv[0];init(server.DB);db=connect(server.DB)
    try:
        if cmd=='init':print('Base prête.');return 0
        if cmd=='create-admin':
            name=(argv[1] if len(argv)>1 else 'admin').lower()
            if db.execute('SELECT 1 FROM users WHERE lower(name)=?',(name,)).fetchone():print(f'Le compte « {name} » existe déjà. Utilisez reset-password.');return 1
            tmp=temporary_password()
            db.execute('INSERT INTO users(id,name,password,role,must_change,full_name,created) VALUES(?,?,?,?,1,?,?)',(uid(),name,password_hash(tmp),'Administrateur','Administrateur ges-ped',now()));db.commit()
            print(f'Compte administrateur créé.\n  Identifiant : {name}\n  Mot de passe temporaire : {tmp}\n  (à changer à la première connexion)');return 0
        if cmd=='reset-password':
            name=argv[1].lower();row=db.execute('SELECT id FROM users WHERE lower(name)=?',(name,)).fetchone()
            if not row:print('Compte introuvable.');return 1
            tmp=temporary_password();db.execute('UPDATE users SET password=?,must_change=1,active=1 WHERE id=?',(password_hash(tmp),row['id']));db.execute('DELETE FROM sessions WHERE user_id=?',(row['id'],));db.commit()
            print(f'Nouveau mot de passe temporaire pour {name} : {tmp}');return 0
        if cmd=='users':
            for r in db.execute('SELECT name,role,active,must_change,last_login FROM users ORDER BY name'):
                print(f"{r['name']:<24} {r['role']:<22} {'actif' if r['active'] else 'inactif':<8} {'1re connexion à faire' if r['must_change'] else ''} {r['last_login'] or ''}")
            return 0
        if cmd=='check':
            v=db.execute('SELECT MAX(version) FROM migrations').fetchone()[0];n=db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            print(f'ges-ped {server.VERSION} {server.EDITION} · base {"PostgreSQL" if is_pg(server.DB) else "SQLite"} · schéma v{v} · {n} compte(s) · adresse publique : {server.PUBLIC_URL or "(non définie)"}');return 0
        print(__doc__);return 1
    finally:db.close()
if __name__=='__main__':sys.exit(main(sys.argv[1:]))
