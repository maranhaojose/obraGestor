#!/usr/bin/env python3
"""Controle de Obra - servidor local (apenas biblioteca padrao do Python 3.8+).
Uso: python3 server.py [porta]   ->  http://localhost:8000
Banco: SQLite em data/obra.db (criado automaticamente, zerado)."""
import csv, datetime, io, json, os, sqlite3, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
DB, PUB = os.path.join(BASE, 'data', 'obra.db'), os.path.join(BASE, 'public')
CATS = ['Materiais', 'Mão de obra', 'Hidráulica', 'Elétrica', 'Estrutura', 'Equipamentos', 'Serviços', 'Outros']
SCHEMA = '''
create table if not exists obra(id integer primary key check(id=1), nome text not null default '',
  orcamento real not null default 0, meta real, inicio text, fim text, status text not null default '',
  meta_alem integer not null default 0, atualizado text default current_timestamp);
create table if not exists categorias(id integer primary key autoincrement, nome text not null unique collate nocase,
  ativo integer not null default 1, criado text default current_timestamp);
create table if not exists itens(id integer primary key autoincrement, nome text not null unique collate nocase,
  categoria_id integer references categorias(id), comportamento text check(comportamento in ('recorrente','pontual')),
  unidade text, ativo integer not null default 1, criado text default current_timestamp);
create table if not exists gastos(id integer primary key autoincrement, item_id integer not null references itens(id),
  data text, quantidade real not null check(quantidade>0), valor_unitario real not null check(valor_unitario>=0),
  valor_total real not null, observacao text, origem text not null default 'manual',
  criado text default current_timestamp, atualizado text default current_timestamp);
create index if not exists ix_gastos_item on gastos(item_id);
create index if not exists ix_gastos_data on gastos(data);
'''

class Erro(Exception):
    def __init__(s, m, code=400): super().__init__(m); s.code = code

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute('pragma foreign_keys=on'); return c

def init():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    with db() as c:
        c.executescript(SCHEMA)
        if not c.execute('select 1 from obra').fetchone():
            c.execute('insert into obra(id) values(1)')
            c.executemany('insert into categorias(nome) values(?)', [(n,) for n in CATS])

def nome(v):
    v = ' '.join(str(v or '').split())
    if not v: raise Erro('Nome obrigatório.')
    return v[:120]

def num(v, campo, pos=False):
    try: x = float(v)
    except (TypeError, ValueError): raise Erro(f'{campo} inválido.')
    if x != x or x in (float('inf'), float('-inf')) or x < 0 or (pos and x == 0):
        raise Erro(f'{campo} deve ser ' + ('maior que zero.' if pos else 'zero ou maior.'))
    return x

def dt(v, obrig=False):
    if not v:
        if obrig: raise Erro('Informe a data do gasto.')
        return None
    try: datetime.date.fromisoformat(str(v))
    except ValueError: raise Erro('Data inválida.')
    return str(v)

def api(c, m, r, b):
    t = r[0]; rid = int(r[1]) if len(r) > 1 and r[1].isdigit() else None
    if t == 'state' and m == 'GET':
        q = lambda s: [dict(x) for x in c.execute(s)]
        return {'obra': dict(c.execute('select * from obra').fetchone()), 'categorias': q('select * from categorias order by id'),
                'itens': q('select * from itens order by nome'), 'gastos': q('select * from gastos order by id')}
    if t == 'obra' and m == 'PUT':
        n = nome(b.get('nome')); orc = num(b.get('orcamento'), 'Orçamento', True)
        meta = b.get('meta'); meta = None if meta in (None, '') else num(meta, 'Meta', True)
        alem = 1 if b.get('meta_alem') else 0
        if meta and meta > orc and not alem: raise Erro('A meta excede o orçamento. Marque a opção para permitir.')
        i, f = dt(b.get('inicio')), dt(b.get('fim'))
        if i and f and f < i: raise Erro('A previsão de conclusão é anterior ao início.')
        c.execute('update obra set nome=?,orcamento=?,meta=?,inicio=?,fim=?,status=?,meta_alem=?,atualizado=current_timestamp where id=1',
                  (n, orc, meta, i, f, str(b.get('status') or ''), alem))
        return {'ok': 1}
    if t == 'categorias':
        if m == 'POST': return {'id': c.execute('insert into categorias(nome) values(?)', (nome(b.get('nome')),)).lastrowid}
        if m == 'PUT' and rid:
            if 'nome' in b: c.execute('update categorias set nome=? where id=?', (nome(b['nome']), rid))
            if 'ativo' in b: c.execute('update categorias set ativo=? where id=?', (1 if b['ativo'] else 0, rid))
            return {'ok': 1}
    if t == 'itens':
        if m == 'POST':
            cp = b.get('comportamento') or None
            if cp not in (None, 'recorrente', 'pontual'): raise Erro('Comportamento inválido.')
            return {'id': c.execute('insert into itens(nome,categoria_id,comportamento,unidade) values(?,?,?,?)',
                    (nome(b.get('nome')), b.get('categoria_id') or None, cp, b.get('unidade') or None)).lastrowid}
        if m == 'PUT' and rid:
            for k in ('categoria_id', 'comportamento', 'unidade', 'ativo'):
                if k not in b: continue
                v = (1 if b[k] else 0) if k == 'ativo' else (b[k] or None)
                if k == 'comportamento' and v not in (None, 'recorrente', 'pontual'): raise Erro('Comportamento inválido.')
                c.execute(f'update itens set {k}=? where id=?', (v, rid))
            return {'ok': 1}
    if t == 'gastos':
        if m == 'DELETE' and rid:
            c.execute('delete from gastos where id=?', (rid,)); return {'ok': 1}
        if m in ('POST', 'PUT'):
            old = c.execute('select origem from gastos where id=?', (rid,)).fetchone() if m == 'PUT' else None
            if m == 'PUT' and not old: raise Erro('Gasto não encontrado.', 404)
            q = num(b.get('quantidade'), 'Quantidade', True); v = num(b.get('valor_unitario'), 'Valor unitário')
            d = dt(b.get('data'), old is None or old['origem'] == 'manual')
            if not c.execute('select 1 from itens where id=?', (b.get('item_id'),)).fetchone(): raise Erro('Item inválido.')
            a = (b['item_id'], d, q, v, round(q * v, 2), str(b.get('observacao') or '')[:300])
            if m == 'POST':
                return {'id': c.execute('insert into gastos(item_id,data,quantidade,valor_unitario,valor_total,observacao) values(?,?,?,?,?,?)', a).lastrowid}
            c.execute('update gastos set item_id=?,data=?,quantidade=?,valor_unitario=?,valor_total=?,observacao=?,atualizado=current_timestamp where id=?', a + (rid,))
            return {'ok': 1}
    if t == 'import' and m == 'POST':
        arq = str(b.get('arquivo') or 'csv')[:80]
        ex = {tuple(x) for x in c.execute("select item_id,coalesce(data,''),quantidade,valor_unitario,coalesce(observacao,'') from gastos where origem like 'csv:%'")}
        ok = dup = 0; erros = []
        for n, l in enumerate(b.get('linhas') or [], 1):
            try:
                q = num(l.get('quantidade'), 'Quantidade', True); v = num(l.get('valor_unitario'), 'Valor unitário')
                d = dt(l.get('data')); nm = nome(l.get('item')); cat = None
                if l.get('categoria'):
                    cn = nome(l['categoria']); x = c.execute('select id from categorias where nome=?', (cn,)).fetchone()
                    cat = x['id'] if x else c.execute('insert into categorias(nome) values(?)', (cn,)).lastrowid
                it = c.execute('select id from itens where nome=?', (nm,)).fetchone()
                if it: iid = it['id']
                else:
                    cp = str(l.get('comportamento') or '').strip().lower()
                    iid = c.execute('insert into itens(nome,categoria_id,comportamento,unidade) values(?,?,?,?)',
                                    (nm, cat, cp if cp in ('recorrente', 'pontual') else None, l.get('unidade') or None)).lastrowid
                obs = str(l.get('observacao') or '')[:300]
                if (iid, d or '', q, v, obs) in ex: dup += 1; continue
                c.execute('insert into gastos(item_id,data,quantidade,valor_unitario,valor_total,observacao,origem) values(?,?,?,?,?,?,?)',
                          (iid, d, q, v, round(q * v, 2), obs, 'csv:' + arq)); ok += 1
            except Erro as e: erros.append(f'Linha {l.get("linha", n)}: {e}')
        return {'importados': ok, 'duplicadas': dup, 'erros': erros}
    if t == 'export' and m == 'GET':
        o = io.StringIO(); w = csv.writer(o, delimiter=';')
        w.writerow(['data', 'item', 'categoria', 'comportamento', 'quantidade', 'unidade', 'valor_unitario', 'valor_total', 'observacao'])
        for x in c.execute('select g.data,i.nome,k.nome,i.comportamento,g.quantidade,i.unidade,g.valor_unitario,g.valor_total,g.observacao from gastos g join itens i on i.id=g.item_id left join categorias k on k.id=i.categoria_id order by g.data,g.id'):
            w.writerow(['' if v is None else v for v in x])
        return o.getvalue().encode('utf-8-sig')
    if t == 'reset' and m == 'POST':
        for s in ('delete from gastos', 'delete from itens', 'delete from categorias', 'delete from sqlite_sequence',
                  "update obra set nome='',orcamento=0,meta=null,inicio=null,fim=null,status='',meta_alem=0"): c.execute(s)
        c.executemany('insert into categorias(nome) values(?)', [(n,) for n in CATS]); return {'ok': 1}
    raise Erro('Rota não encontrada.', 404)

class H(SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=PUB, **k)
    def log_message(s, *a): pass
    def out(s, code, body, ctype='application/json', extra=None):
        b = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        s.send_response(code); s.send_header('Content-Type', ctype + '; charset=utf-8'); s.send_header('Content-Length', str(len(b)))
        s.send_header('Cache-Control', 'no-store')
        for k, v in (extra or {}).items(): s.send_header(k, v)
        s.end_headers(); s.wfile.write(b)
    def route(s, m):
        p = urlparse(s.path).path
        if not p.startswith('/api/'): return False
        try:
            raw = s.rfile.read(int(s.headers.get('Content-Length') or 0)); b = json.loads(raw or b'{}')
            with db() as c: r = api(c, m, p[5:].strip('/').split('/'), b)
            if isinstance(r, bytes): s.out(200, r, 'text/csv', {'Content-Disposition': 'attachment; filename="gastos.csv"'})
            else: s.out(200, r)
        except Erro as e: s.out(e.code, {'erro': str(e)})
        except sqlite3.IntegrityError: s.out(409, {'erro': 'Registro duplicado ou referência inválida.'})
        except Exception as e: s.out(500, {'erro': 'Erro interno: ' + str(e)})
        return True
    def do_GET(s): s.route('GET') or super().do_GET()
    def do_POST(s): s.route('POST')
    def do_PUT(s): s.route('PUT')
    def do_DELETE(s): s.route('DELETE')

if __name__ == '__main__':
    init(); port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f'Controle de Obra em http://localhost:{port}  (Ctrl+C para sair)')
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
