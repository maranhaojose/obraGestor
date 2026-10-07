"""Núcleo do Controle de Obra: regras, banco (PostgreSQL em produção / SQLite local) e autenticação."""
import csv, datetime, hashlib, hmac, io, json, os, sqlite3, time

URL = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL') or ''
PROD = bool(os.environ.get('VERCEL'))
PASSWORD = os.environ.get('APP_PASSWORD', '')
SECRET = (os.environ.get('APP_SECRET') or PASSWORD).encode()
DB = os.environ.get('OBRA_DB') or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'obra.db')
CATS = ['Materiais', 'Mão de obra', 'Hidráulica', 'Elétrica', 'Estrutura', 'Equipamentos', 'Serviços', 'Outros']
CK = "check(comportamento in ('recorrente','pontual'))"
LITE = [
 "create table if not exists obra(id integer primary key check(id=1), nome text not null default '', orcamento real not null default 0, meta real, inicio text, fim text, status text not null default '', meta_alem integer not null default 0, atualizado text default current_timestamp)",
 "create table if not exists categorias(id integer primary key autoincrement, nome text not null unique collate nocase, ativo integer not null default 1, criado text default current_timestamp)",
 f"create table if not exists itens(id integer primary key autoincrement, nome text not null unique collate nocase, categoria_id integer references categorias(id), comportamento text {CK}, unidade text, ativo integer not null default 1, criado text default current_timestamp)",
 "create table if not exists gastos(id integer primary key autoincrement, item_id integer not null references itens(id), data text, quantidade real not null check(quantidade>0), valor_unitario real not null check(valor_unitario>=0), valor_total real not null, observacao text, origem text not null default 'manual', criado text default current_timestamp, atualizado text default current_timestamp)",
]
PG = [
 "create table if not exists obra(id integer primary key check(id=1), nome text not null default '', orcamento double precision not null default 0, meta double precision, inicio text, fim text, status text not null default '', meta_alem integer not null default 0, atualizado timestamptz default now())",
 "create table if not exists categorias(id serial primary key, nome text not null, ativo integer not null default 1, criado timestamptz default now())",
 "create unique index if not exists ux_categorias_nome on categorias(lower(nome))",
 f"create table if not exists itens(id serial primary key, nome text not null, categoria_id integer references categorias(id), comportamento text {CK}, unidade text, ativo integer not null default 1, criado timestamptz default now())",
 "create unique index if not exists ux_itens_nome on itens(lower(nome))",
 "create table if not exists gastos(id serial primary key, item_id integer not null references itens(id), data text, quantidade double precision not null check(quantidade>0), valor_unitario double precision not null check(valor_unitario>=0), valor_total double precision not null, observacao text, origem text not null default 'manual', criado timestamptz default now(), atualizado timestamptz default now())",
]
IDX = ["create index if not exists ix_gastos_item on gastos(item_id)", "create index if not exists ix_gastos_data on gastos(data)"]

class Erro(Exception):
    def __init__(s, m, code=400): super().__init__(m); s.code = code

class Conn:
    def __init__(s):
        s.pg = bool(URL)
        if s.pg:
            import psycopg
            from psycopg.rows import dict_row
            s.c = psycopg.connect(URL, prepare_threshold=None, row_factory=dict_row, connect_timeout=10)
        else:
            os.makedirs(os.path.dirname(DB), exist_ok=True)
            s.c = sqlite3.connect(DB); s.c.row_factory = sqlite3.Row; s.c.execute('pragma foreign_keys=on')
    def __enter__(s): return s
    def __exit__(s, t, v, tb):
        try: s.c.rollback() if t else s.c.commit()
        finally: s.c.close()
    def q(s, sql, a=()):
        return s.c.execute(sql.replace('?', '%s'), tuple(a) or None) if s.pg else s.c.execute(sql, a)
    def rows(s, sql, a=()): return [dict(x) for x in s.q(sql, a).fetchall()]
    def one(s, sql, a=()):
        x = s.q(sql, a).fetchone(); return dict(x) if x else None
    def ins(s, sql, a=()):
        return s.q(sql + ' returning id', a).fetchone()['id'] if s.pg else s.q(sql, a).lastrowid

_ready = False
def init():
    global _ready
    if _ready: return
    with Conn() as c:
        for st in (PG if c.pg else LITE) + IDX: c.q(st)
        if c.q('insert into obra(id) values(1) on conflict do nothing').rowcount == 1:
            for n in CATS: c.q('insert into categorias(nome) values(?)', (n,))
    _ready = True

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
    t = r[0] if r else ''; rid = int(r[1]) if len(r) > 1 and r[1].isdigit() else None
    if t == 'state' and m == 'GET':
        return {'obra': c.one('select * from obra'), 'categorias': c.rows('select * from categorias order by id'),
                'itens': c.rows('select * from itens order by nome'), 'gastos': c.rows('select * from gastos order by id')}
    if t == 'obra' and m == 'PUT':
        n = nome(b.get('nome')); orc = num(b.get('orcamento'), 'Orçamento', True)
        meta = b.get('meta'); meta = None if meta in (None, '') else num(meta, 'Meta', True)
        alem = 1 if b.get('meta_alem') else 0
        if meta and meta > orc and not alem: raise Erro('A meta excede o orçamento. Marque a opção para permitir.')
        i, f = dt(b.get('inicio')), dt(b.get('fim'))
        if i and f and f < i: raise Erro('A previsão de conclusão é anterior ao início.')
        c.q('update obra set nome=?,orcamento=?,meta=?,inicio=?,fim=?,status=?,meta_alem=?,atualizado=current_timestamp where id=1',
            (n, orc, meta, i, f, str(b.get('status') or ''), alem))
        return {'ok': 1}
    if t == 'categorias':
        if m == 'POST': return {'id': c.ins('insert into categorias(nome) values(?)', (nome(b.get('nome')),))}
        if m == 'PUT' and rid:
            if 'nome' in b: c.q('update categorias set nome=? where id=?', (nome(b['nome']), rid))
            if 'ativo' in b: c.q('update categorias set ativo=? where id=?', (1 if b['ativo'] else 0, rid))
            return {'ok': 1}
    if t == 'itens':
        if m == 'POST':
            cp = b.get('comportamento') or None
            if cp not in (None, 'recorrente', 'pontual'): raise Erro('Comportamento inválido.')
            return {'id': c.ins('insert into itens(nome,categoria_id,comportamento,unidade) values(?,?,?,?)',
                    (nome(b.get('nome')), b.get('categoria_id') or None, cp, b.get('unidade') or None))}
        if m == 'PUT' and rid:
            for k in ('categoria_id', 'comportamento', 'unidade', 'ativo'):
                if k not in b: continue
                v = (1 if b[k] else 0) if k == 'ativo' else (b[k] or None)
                if k == 'comportamento' and v not in (None, 'recorrente', 'pontual'): raise Erro('Comportamento inválido.')
                c.q(f'update itens set {k}=? where id=?', (v, rid))
            return {'ok': 1}
    if t == 'gastos':
        if m == 'DELETE' and rid:
            c.q('delete from gastos where id=?', (rid,)); return {'ok': 1}
        if m in ('POST', 'PUT'):
            old = c.one('select origem from gastos where id=?', (rid,)) if m == 'PUT' else None
            if m == 'PUT' and not old: raise Erro('Gasto não encontrado.', 404)
            q = num(b.get('quantidade'), 'Quantidade', True); v = num(b.get('valor_unitario'), 'Valor unitário')
            d = dt(b.get('data'), old is None or old['origem'] == 'manual')
            try: iid = int(b.get('item_id'))
            except (TypeError, ValueError): raise Erro('Item inválido.')
            if not c.one('select 1 as x from itens where id=?', (iid,)): raise Erro('Item inválido.')
            a = (iid, d, q, v, round(q * v, 2), str(b.get('observacao') or '')[:300])
            if m == 'POST':
                return {'id': c.ins('insert into gastos(item_id,data,quantidade,valor_unitario,valor_total,observacao) values(?,?,?,?,?,?)', a)}
            c.q('update gastos set item_id=?,data=?,quantidade=?,valor_unitario=?,valor_total=?,observacao=?,atualizado=current_timestamp where id=?', a + (rid,))
            return {'ok': 1}
    if t == 'import' and m == 'POST':
        arq = str(b.get('arquivo') or 'csv')[:80]
        ex = {(x['item_id'], x['d'], x['q'], x['v'], x['o']) for x in c.rows("select item_id, coalesce(data,'') as d, quantidade as q, valor_unitario as v, coalesce(observacao,'') as o from gastos where substr(origem,1,4)='csv:'")}
        ok = dup = 0; erros = []
        for n, l in enumerate(b.get('linhas') or [], 1):
            try:
                q = num(l.get('quantidade'), 'Quantidade', True); v = num(l.get('valor_unitario'), 'Valor unitário')
                d = dt(l.get('data')); nm = nome(l.get('item')); cat = None
                if l.get('categoria'):
                    cn = nome(l['categoria']); x = c.one('select id from categorias where lower(nome)=lower(?)', (cn,))
                    cat = x['id'] if x else c.ins('insert into categorias(nome) values(?)', (cn,))
                it = c.one('select id from itens where lower(nome)=lower(?)', (nm,))
                if it: iid = it['id']
                else:
                    cp = str(l.get('comportamento') or '').strip().lower()
                    iid = c.ins('insert into itens(nome,categoria_id,comportamento,unidade) values(?,?,?,?)',
                                (nm, cat, cp if cp in ('recorrente', 'pontual') else None, l.get('unidade') or None))
                obs = str(l.get('observacao') or '')[:300]
                if (iid, d or '', q, v, obs) in ex: dup += 1; continue
                c.q('insert into gastos(item_id,data,quantidade,valor_unitario,valor_total,observacao,origem) values(?,?,?,?,?,?,?)',
                    (iid, d, q, v, round(q * v, 2), obs, 'csv:' + arq)); ok += 1
            except Erro as e: erros.append(f'Linha {l.get("linha", n)}: {e}')
        return {'importados': ok, 'duplicadas': dup, 'erros': erros}
    if t == 'export' and m == 'GET':
        o = io.StringIO(); w = csv.writer(o, delimiter=';')
        w.writerow(['data', 'item', 'categoria', 'comportamento', 'quantidade', 'unidade', 'valor_unitario', 'valor_total', 'observacao'])
        for x in c.rows('select g.data,i.nome as n,k.nome as k,i.comportamento,g.quantidade,i.unidade,g.valor_unitario,g.valor_total,g.observacao from gastos g join itens i on i.id=g.item_id left join categorias k on k.id=i.categoria_id order by g.data,g.id'):
            w.writerow(['' if v is None else v for v in x.values()])
        return o.getvalue().encode('utf-8-sig')
    if t == 'reset' and m == 'POST':
        if c.pg: c.q('truncate gastos,itens,categorias restart identity cascade')
        else:
            for s in ('delete from gastos', 'delete from itens', 'delete from categorias', 'delete from sqlite_sequence'): c.q(s)
        c.q("update obra set nome='',orcamento=0,meta=null,inicio=null,fim=null,status='',meta_alem=0")
        for n in CATS: c.q('insert into categorias(nome) values(?)', (n,))
        return {'ok': 1}
    raise Erro('Rota não encontrada.', 404)

# ---- autenticação (cookie assinado) ----
def _tok():
    e = str(int(time.time()) + 7 * 86400)
    return e + '.' + hmac.new(SECRET, e.encode(), hashlib.sha256).hexdigest()
def _authed(cookie):
    for p in (cookie or '').split(';'):
        k, _, v = p.strip().partition('=')
        if k == 'obra_sess':
            e, _, s = v.partition('.')
            return e.isdigit() and int(e) > time.time() and hmac.compare_digest(s, hmac.new(SECRET, e.encode(), hashlib.sha256).hexdigest())
    return False

def handle(method, path, cookie, ctype, raw):
    """Retorna (status, headers, corpo em bytes). Usado pelo servidor local e pela função da Vercel."""
    def js(code, obj, extra=None):
        h = {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'}; h.update(extra or {})
        return code, h, json.dumps(obj, ensure_ascii=False, default=str).encode()
    p = path.split('?')[0]
    if p.startswith('/api/index'): p = '/api' + p[len('/api/index'):]
    r = [x for x in p[5:].split('/') if x]; t = r[0] if r else ''
    try:
        if PROD and not PASSWORD: return js(503, {'erro': 'Defina a variável APP_PASSWORD nas configurações do projeto na Vercel.'})
        if PROD and not URL: return js(503, {'erro': 'Banco não configurado. Conecte um Postgres ao projeto (variável DATABASE_URL).'})
        if method != 'GET' and 'application/json' not in (ctype or ''): return js(415, {'erro': 'Content-Type inválido.'})
        ok = (not PASSWORD) or _authed(cookie)
        if t == 'session' and method == 'GET': return js(200, {'protegido': bool(PASSWORD), 'auth': ok})
        flags = '; Path=/; HttpOnly; SameSite=Lax' + ('; Secure' if PROD else '')
        if t == 'logout' and method == 'POST': return js(200, {'ok': 1}, {'Set-Cookie': 'obra_sess=; Max-Age=0' + flags})
        b = json.loads(raw or b'{}') if method != 'GET' else {}
        if t == 'login' and method == 'POST':
            if PASSWORD and hmac.compare_digest(str(b.get('senha', '')).encode(), PASSWORD.encode()):
                return js(200, {'ok': 1}, {'Set-Cookie': f'obra_sess={_tok()}; Max-Age=604800' + flags})
            time.sleep(1); return js(401, {'erro': 'Senha incorreta.'})
        if not ok: return js(401, {'erro': 'Não autenticado.'})
        init()
        with Conn() as c: out = api(c, method, r, b)
        if isinstance(out, bytes):
            return 200, {'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': 'attachment; filename="gastos.csv"', 'Cache-Control': 'no-store'}, out
        return js(200, out)
    except Erro as e: return js(e.code, {'erro': str(e)})
    except json.JSONDecodeError: return js(400, {'erro': 'JSON inválido.'})
    except Exception as e:
        if type(e).__name__ == 'IntegrityError': return js(409, {'erro': 'Registro duplicado ou referência inválida.'})
        return js(500, {'erro': 'Erro interno: ' + str(e)})
