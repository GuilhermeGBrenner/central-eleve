"""
sheets_db.py — Google Sheets as database for Central Eleve.
Supports credentials.json (local) or GOOGLE_CREDENTIALS env var (Render).
"""
import gspread, hashlib, os, json
from datetime import datetime
from google.oauth2.service_account import Credentials

SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
CREDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials.json')
SPREADSHEET_NAME = 'Central Eleve - DB'

_client = None
_sheet = None

def get_client():
    global _client
    if _client is None:
        env_creds = os.environ.get('GOOGLE_CREDENTIALS')
        if env_creds:
            info = json.loads(env_creds)
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
        _client = gspread.authorize(creds)
    return _client

def get_sheet():
    global _sheet
    if _sheet is None:
        client = get_client()
        try:
            _sheet = client.open(SPREADSHEET_NAME)
        except gspread.SpreadsheetNotFound:
            print(f"\nERRO: Planilha '{SPREADSHEET_NAME}' nao encontrada!")
            print(f"Crie manualmente no Google Sheets e compartilhe com: ")
            print(f"  {Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES).service_account_email}")
            raise
        ensure_tabs(_sheet)
    return _sheet

def ensure_tabs(sh):
    """Create required tabs if they don't exist in the spreadsheet."""
    existing = [ws.title for ws in sh.worksheets()]
    if 'usuarios' not in existing:
        if 'Sheet1' in existing or 'Página1' in existing or 'Planilha1' in existing:
            ws = sh.sheet1
            ws.update_title('usuarios')
        else:
            ws = sh.add_worksheet('usuarios', rows=100, cols=10)
        if not ws.row_values(1):
            ws.append_row(['user_id','pin_hash','nome','receita','meta_gasto','patrimonio','cdi','tema','created_at'])
        print("  Tab 'usuarios' configurada")
    if 'transacoes' not in existing:
        ws2 = sh.add_worksheet('transacoes', rows=5000, cols=12)
        ws2.append_row(['id','user_id','data','item','categoria','tipo','situacao','valor','mes_ref','observacao','created_at'])
        print("  Tab 'transacoes' configurada")
    if 'categorias' not in existing:
        ws3 = sh.add_worksheet('categorias', rows=200, cols=5)
        ws3.append_row(['user_id','nome','tipo','cor'])
        print("  Tab 'categorias' configurada")
    return sh

def hash_pin(pin):
    return hashlib.sha256(str(pin).encode()).hexdigest()[:16]

def create_user(nome, pin, receita=0, meta_gasto=4500, patrimonio=0, cdi=14.5):
    sh = get_sheet()
    ws = sh.worksheet('usuarios')
    all_users = ws.get_all_records()
    user_id = f"u{len(all_users)+1}"
    ws.append_row([user_id, hash_pin(pin), nome, float(receita), float(meta_gasto),
                    float(patrimonio), float(cdi), 'dark', datetime.now().strftime('%Y-%m-%d %H:%M')])
    default_cats = [
        ('Salario','Entrada','#22c55e'),('Entrada','Entrada','#3b82f6'),
        ('Lazer','Saida','#f472b6'),('Mercado','Saida','#fb923c'),
        ('Uber/99','Saida','#a78bfa'),('Contas','Saida','#ef4444'),
        ('Assinatura','Saida','#06b6d4'),('Parcelamento','Saida','#eab308'),
        ('Imprevistos','Saida','#f87171'),('Educacao','Saida','#8b5cf6'),
    ]
    ws_cat = sh.worksheet('categorias')
    rows_to_add = [[user_id, n, t, c] for n, t, c in default_cats]
    ws_cat.append_rows(rows_to_add)
    return user_id

def auth_user(nome, pin):
    sh = get_sheet()
    ws = sh.worksheet('usuarios')
    users = ws.get_all_records()
    ph = hash_pin(pin)
    for u in users:
        if str(u.get('nome','')).strip().lower() == nome.strip().lower() and u.get('pin_hash','') == ph:
            return u
    return None

def user_exists(nome):
    sh = get_sheet()
    ws = sh.worksheet('usuarios')
    users = ws.get_all_records()
    for u in users:
        if str(u.get('nome','')).strip().lower() == nome.strip().lower():
            return True
    return False

def get_user(user_id):
    sh = get_sheet()
    ws = sh.worksheet('usuarios')
    users = ws.get_all_records()
    for u in users:
        if u.get('user_id','') == user_id:
            return u
    return None

def update_user_config(user_id, **kwargs):
    sh = get_sheet()
    ws = sh.worksheet('usuarios')
    users = ws.get_all_records()
    headers = ws.row_values(1)
    for i, u in enumerate(users):
        if u.get('user_id','') == user_id:
            row = i + 2
            for key, val in kwargs.items():
                if key in headers:
                    col = headers.index(key) + 1
                    ws.update_cell(row, col, val)
            return True
    return False

def get_categorias(user_id):
    sh = get_sheet()
    ws = sh.worksheet('categorias')
    all_cats = ws.get_all_records()
    return [c for c in all_cats if c.get('user_id','') == user_id]

def add_categoria(user_id, nome, tipo='Saida', cor='#6b7280'):
    sh = get_sheet()
    ws = sh.worksheet('categorias')
    ws.append_row([user_id, nome, tipo, cor])

def delete_categoria(user_id, nome):
    sh = get_sheet()
    ws = sh.worksheet('categorias')
    all_rows = ws.get_all_values()
    for i, row in enumerate(all_rows[1:], start=2):
        if row[0] == user_id and row[1] == nome:
            trans = get_transacoes_mes(user_id, None)
            if not any(t.get('categoria','') == nome for t in trans):
                ws.delete_rows(i)
                return True
    return False

def _next_id(ws):
    all_vals = ws.col_values(1)
    ids = [int(v) for v in all_vals[1:] if str(v).isdigit()]
    return max(ids) + 1 if ids else 1

def add_transacao(user_id, data, item, categoria, tipo, situacao, valor, mes_ref, obs=''):
    sh = get_sheet()
    ws = sh.worksheet('transacoes')
    tid = _next_id(ws)
    ws.append_row([tid, user_id, data, item, categoria, tipo, situacao, float(valor), mes_ref, obs,
                    datetime.now().strftime('%Y-%m-%d %H:%M')])
    return tid

def get_transacoes_mes(user_id, mes_ref):
    sh = get_sheet()
    ws = sh.worksheet('transacoes')
    all_trans = ws.get_all_records()
    result = [t for t in all_trans if t.get('user_id','') == user_id]
    if mes_ref:
        result = [t for t in result if t.get('mes_ref','') == mes_ref]
    cats = {c['nome']: c.get('cor','#6b7280') for c in get_categorias(user_id)}
    for t in result:
        t['cat_cor'] = cats.get(t.get('categoria',''), '#6b7280')
        try:
            t['valor'] = float(t['valor'])
        except:
            t['valor'] = 0
    return sorted(result, key=lambda x: str(x.get('data', '')))

def get_meses_disponiveis(user_id):
    sh = get_sheet()
    ws = sh.worksheet('transacoes')
    all_trans = ws.get_all_records()
    meses = set()
    for t in all_trans:
        if t.get('user_id','') == user_id and t.get('mes_ref',''):
            meses.add(t['mes_ref'])
    return sorted(meses, reverse=True)

def update_transacao(tid, **kwargs):
    sh = get_sheet()
    ws = sh.worksheet('transacoes')
    all_rows = ws.get_all_values()
    headers = all_rows[0]
    for i, row in enumerate(all_rows[1:], start=2):
        if row[0] == str(tid):
            for key, val in kwargs.items():
                if key in headers:
                    col = headers.index(key) + 1
                    ws.update_cell(i, col, val)
            return True
    return False

def delete_transacao(tid):
    sh = get_sheet()
    ws = sh.worksheet('transacoes')
    all_rows = ws.get_all_values()
    for i, row in enumerate(all_rows[1:], start=2):
        if row[0] == str(tid):
            ws.delete_rows(i)
            return True
    return False

def toggle_situacao(tid):
    sh = get_sheet()
    ws = sh.worksheet('transacoes')
    all_rows = ws.get_all_values()
    headers = all_rows[0]
    sit_col = headers.index('situacao') + 1
    tipo_col = headers.index('tipo') + 1
    mes_col = headers.index('mes_ref')
    for i, row in enumerate(all_rows[1:], start=2):
        if row[0] == str(tid):
            old = row[sit_col - 1]
            tipo = row[tipo_col - 1]
            if tipo == 'Entrada':
                new = 'Recebido' if old == 'Pendente' else 'Pendente'
            else:
                new = 'Pago' if old == 'Pendente' else 'Pendente'
            ws.update_cell(i, sit_col, new)
            return row[mes_col]
    return None

def get_ultimas(user_id, limit=10):
    sh = get_sheet()
    ws = sh.worksheet('transacoes')
    all_trans = ws.get_all_records()
    user_trans = [t for t in all_trans if t.get('user_id','') == user_id]
    cats = {c['nome']: c.get('cor','#6b7280') for c in get_categorias(user_id)}
    for t in user_trans:
        t['cat_cor'] = cats.get(t.get('categoria',''), '#6b7280')
        try:
            t['valor'] = float(t['valor'])
        except:
            t['valor'] = 0
    return list(reversed(user_trans[-limit:]))

def resumo_mes(user_id, mes_ref):
    trans = get_transacoes_mes(user_id, mes_ref)
    cats = {c['nome']: c.get('cor','#6b7280') for c in get_categorias(user_id)}
    summary = {}
    for t in trans:
        key = (t.get('categoria',''), t.get('tipo',''))
        if key not in summary:
            summary[key] = {'nome': t.get('categoria',''), 'cor': cats.get(t.get('categoria',''), '#6b7280'),
                           'tipo': t.get('tipo',''), 'total': 0, 'qtd': 0}
        summary[key]['total'] += t['valor']
        summary[key]['qtd'] += 1
    return sorted(summary.values(), key=lambda x: x['total'], reverse=True)

def resumo_situacao(user_id, mes_ref):
    trans = get_transacoes_mes(user_id, mes_ref)
    sit = {}
    for t in trans:
        s = t.get('situacao','Pendente')
        if s not in sit:
            sit[s] = {'situacao': s, 'saidas': 0, 'entradas': 0}
        if t.get('tipo','') == 'Saida':
            sit[s]['saidas'] += t['valor']
        else:
            sit[s]['entradas'] += t['valor']
    return list(sit.values())

def historico_mensal(user_id):
    meses = sorted(get_meses_disponiveis(user_id))
    hist = []
    for m in meses:
        trans = get_transacoes_mes(user_id, m)
        ent = sum(t['valor'] for t in trans if t.get('tipo','') == 'Entrada')
        sai = sum(t['valor'] for t in trans if t.get('tipo','') in ('Saida','Saída'))
        hist.append({'mes': m, 'entrada': round(ent, 2), 'saida': round(sai, 2), 'economia': round(ent - sai, 2)})
    return hist
