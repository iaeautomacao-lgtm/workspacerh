"""Acrescenta ao banco as colunas novas que `create_all` não cria em tabela existente.

`Base.metadata.create_all` cria tabelas que faltam, mas nunca altera uma que já
existe. Este utilitário compara o modelo com o banco e aplica os ALTER que faltam.
Funciona em SQLite e MySQL/MariaDB. Só adiciona coluna: nunca remove nem altera tipo.

Uso, a partir da raiz do projeto:
    python backend/migrate.py            # mostra o que falta
    python backend/migrate.py --aplicar  # aplica
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import inspect, text
from app.core.database import Base, engine
from app.models import domain, workflow, exam  # noqa: F401  (registra as tabelas)

def pending():
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    faltando = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue  # create_all resolve
        atuais = {c['name'] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in atuais:
                faltando.append((table, column))
    return faltando

def ddl(table, column):
    tipo = column.type.compile(dialect=engine.dialect)
    sql = f'ALTER TABLE {table.name} ADD COLUMN {column.name} {tipo}'
    if column.default is not None and getattr(column.default, 'is_scalar', False):
        valor = column.default.arg
        sql += f" DEFAULT {'1' if valor is True else '0' if valor is False else repr(valor)}"
    return sql

def ensure_admin():
    """Sem administrador ninguém gerencia as contas: promove a mais antiga."""
    from app.core.database import SessionLocal
    from app.models.workflow import Account
    with SessionLocal() as db:
        if db.query(Account).filter(Account.role == 'admin', Account.active == True).count():
            return
        primeira = db.query(Account).order_by(Account.id).first()
        if not primeira:
            return
        primeira.role = 'admin'
        primeira.active = True
        db.commit()
        print(f'  promovido a administrador: {primeira.email}')

def run(aplicar):
    Base.metadata.create_all(engine)
    faltando = pending()
    if faltando:
        for table, column in faltando:
            comando = ddl(table, column)
            print(('  aplicando: ' if aplicar else '  faltando : ') + comando)
            if aplicar:
                with engine.begin() as conn:
                    conn.execute(text(comando))
    else:
        print('  colunas em dia, nada a alterar')
    if aplicar:
        ensure_admin()
    elif faltando:
        print('\n  rode de novo com --aplicar para executar')
    return len(faltando)

if __name__ == '__main__':
    run('--aplicar' in sys.argv)
