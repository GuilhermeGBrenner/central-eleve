from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import json, os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'eleve-2026-secret-key')

import sheets_db as db

MESES_NOME = {'01':'Janeiro','02':'Fevereiro','03':'Março','04':'Abril','05':'Maio','06':'Junho',
              '07':'Julho','08':'Agosto','09':'Setembro','10':'Outubro','11':'Novembro','12':'Dezembro'}

def mes_label(mes_ref):
    if not mes_ref or '-' not in str(mes_ref): return str(mes_ref or '')
    parts = str(mes_ref).split('-')
    return f"{MESES_NOME.get(parts[1], parts[1])} {parts[0]}"

app.jinja_env.globals['mes_label'] = mes_label

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def current_user():
    if 'user_id' in session:
        return db.get_user(session['user_id'])
    return None

@app.context_processor
def inject_user():
    user = current_user()
    tema = user.get('tema', 'dark') if user else 'dark'
    return dict(current_user=user, tema=tema)

# ============ AUTH ============

@app.route('/login', methods=['GET','POST'])
def login():
    error = None
    if request.method == 'POST':
        nome = request.form.get('nome','').strip()
        pin = request.form.get('pin','').strip()
        if not nome or not pin:
            error = 'Preencha nome e PIN'
        else:
            user = db.auth_user(nome, pin)
            if user:
                session['user_id'] = user['user_id']
                return redirect(url_for('index'))
            error = 'Nome ou PIN incorreto'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/onboarding', methods=['GET','POST'])
def onboarding():
    if request.method == 'POST':
        step = request.form.get('step','1')
        if step == '1':
            nome = request.form.get('nome','').strip()
            pin = request.form.get('pin','').strip()
            if not nome or not pin or len(pin) < 4:
                return render_template('onboarding.html', step=1, error='Nome e PIN (4+ digitos) obrigatorios')
            if db.user_exists(nome):
                return render_template('onboarding.html', step=1, error='Nome ja cadastrado')
            session['onb_nome'] = nome
            session['onb_pin'] = pin
            return render_template('onboarding.html', step=2)
        elif step == '2':
            nome = session.pop('onb_nome', '')
            pin = session.pop('onb_pin', '')
            if not nome or not pin:
                return redirect(url_for('onboarding'))
            receita = float(request.form.get('receita','0').replace(',','.') or 0)
            meta = float(request.form.get('meta_gasto','4500').replace(',','.') or 4500)
            pat = float(request.form.get('patrimonio','0').replace(',','.') or 0)
            cdi = float(request.form.get('cdi','14.5').replace(',','.') or 14.5)
            user_id = db.create_user(nome, pin, receita, meta, pat, cdi)
            session['user_id'] = user_id
            return redirect(url_for('index'))
    return render_template('onboarding.html', step=1)

# ============ GASTOS ============

@app.route('/')
@login_required
def index():
    uid = session['user_id']
    meses = db.get_meses_disponiveis(uid)
    mes_atual = request.args.get('mes', meses[0] if meses else None)
    if not mes_atual:
        return render_template('index.html', meses=[], mes_atual=None, transacoes=[], resumo=[],
                               total_entrada=0, total_saida=0, economia=0, pct_economia=0, sit_resumo=[], cats=[], hist='[]')
    transacoes = db.get_transacoes_mes(uid, mes_atual)
    resumo = db.resumo_mes(uid, mes_atual)
    sit = db.resumo_situacao(uid, mes_atual)
    cats = db.get_categorias(uid)
    total_entrada = sum(t['valor'] for t in transacoes if t.get('tipo','') == 'Entrada')
    total_saida = sum(t['valor'] for t in transacoes if t.get('tipo','') in ('Saida','Saída'))
    economia = total_entrada - total_saida
    pct_economia = (economia / total_entrada * 100) if total_entrada > 0 else 0
    hist = db.historico_mensal(uid)
    hist_labeled = [{'mes': mes_label(h['mes']), **h} for h in hist]
    return render_template('index.html', meses=meses, mes_atual=mes_atual, transacoes=transacoes,
                           resumo=resumo, total_entrada=total_entrada, total_saida=total_saida,
                           economia=economia, pct_economia=pct_economia, sit_resumo=sit, cats=cats,
                           hist=json.dumps(hist_labeled))

@app.route('/cadastro', methods=['GET','POST'])
@login_required
def cadastro():
    uid = session['user_id']
    cats = db.get_categorias(uid)
    meses = db.get_meses_disponiveis(uid)
    if request.method == 'POST':
        mes_new = request.form.get('mes_ref_new','').strip()
        mes_ref = mes_new if mes_new else request.form.get('mes_ref','')
        db.add_transacao(uid, request.form['data'], request.form['item'],
                         request.form['categoria'], request.form['tipo'],
                         request.form['situacao'], float(request.form['valor'].replace(',','.')),
                         mes_ref, request.form.get('observacao',''))
        return redirect(url_for('index', mes=mes_ref))
    ultimas = db.get_ultimas(uid, 10)
    return render_template('cadastro.html', cats=cats, meses=meses, ultimas=ultimas)

@app.route('/editar/<int:tid>', methods=['GET','POST'])
@login_required
def editar(tid):
    uid = session['user_id']
    cats = db.get_categorias(uid)
    meses = db.get_meses_disponiveis(uid)
    if request.method == 'POST':
        mes_new = request.form.get('mes_ref_new','').strip()
        mes_ref = mes_new if mes_new else request.form.get('mes_ref','')
        db.update_transacao(tid, data=request.form['data'], item=request.form['item'],
                            categoria=request.form['categoria'], tipo=request.form['tipo'],
                            situacao=request.form['situacao'], valor=float(request.form['valor'].replace(',','.')),
                            mes_ref=mes_ref, observacao=request.form.get('observacao',''))
        return redirect(url_for('index', mes=mes_ref))
    all_trans = db.get_transacoes_mes(uid, None)
    trans = next((t for t in all_trans if str(t.get('id','')) == str(tid)), None)
    ultimas = db.get_ultimas(uid, 10)
    return render_template('cadastro.html', cats=cats, meses=meses, trans=trans, editing=True, ultimas=ultimas)

@app.route('/excluir/<int:tid>')
@login_required
def excluir(tid):
    db.delete_transacao(tid)
    return redirect(url_for('index'))

@app.route('/toggle/<int:tid>')
@login_required
def toggle(tid):
    mes = db.toggle_situacao(tid)
    return redirect(url_for('index', mes=mes))

@app.route('/novo_mes', methods=['POST'])
@login_required
def novo_mes():
    return redirect(url_for('index', mes=request.form['mes_ref']))

# ============ PATRIMONIO ============

@app.route('/patrimonio')
@login_required
def patrimonio():
    uid = session['user_id']
    user = current_user()
    hist = db.historico_mensal(uid)
    hist_labeled = [{'label': mes_label(h['mes']), **h} for h in hist]
    full = hist[:-1] if len(hist) > 1 else hist
    avg_ent = sum(h['entrada'] for h in full)/len(full) if full else 0
    avg_sai = sum(h['saida'] for h in full)/len(full) if full else 0
    avg_eco = avg_ent - avg_sai
    last = full[-1] if full else {'entrada':0,'saida':0,'economia':0}
    pat = float(user.get('patrimonio',0) or 0)
    cdi = float(user.get('cdi',14.5) or 14.5)
    meta = float(user.get('meta_gasto',4500) or 4500)
    meses = sorted(db.get_meses_disponiveis(uid))
    recent = meses[-6:] if len(meses) >= 6 else meses
    cats_all = db.get_categorias(uid)
    cat_trend = []
    for cat in cats_all:
        if cat.get('tipo','') not in ('Saida','Saída'): continue
        vals = []
        for m in recent:
            trans = db.get_transacoes_mes(uid, m)
            total = sum(t['valor'] for t in trans if t.get('categoria','') == cat['nome'] and t.get('tipo','') in ('Saida','Saída'))
            vals.append(round(total, 2))
        if any(v > 0 for v in vals):
            cat_trend.append({'nome': cat['nome'], 'cor': cat.get('cor','#6b7280'), 'valores': vals})
    return render_template('patrimonio.html', user=user, monthly=json.dumps(hist_labeled),
                           cat_trend=json.dumps(cat_trend), cat_trend_labels=json.dumps([mes_label(m) for m in recent]),
                           avg_entrada=avg_ent, avg_saida=avg_sai, avg_economia=avg_eco,
                           last_entrada=last['entrada'], last_saida=last.get('saida',0),
                           patrimonio=pat, cdi=cdi, meta_gasto=meta)

# ============ CONFIG ============

@app.route('/config', methods=['GET','POST'])
@login_required
def configuracoes():
    uid = session['user_id']
    if request.method == 'POST':
        updates = {}
        for k in ['receita','meta_gasto','patrimonio','cdi','tema']:
            v = request.form.get(k)
            if v is not None:
                updates[k] = v
        db.update_user_config(uid, **updates)
        return redirect(url_for('index'))
    user = current_user()
    return render_template('config.html', user=user)

@app.route('/toggle_tema')
@login_required
def toggle_tema():
    uid = session['user_id']
    user = current_user()
    new_tema = 'light' if user.get('tema','dark') == 'dark' else 'dark'
    db.update_user_config(uid, tema=new_tema)
    return redirect(request.referrer or url_for('index'))

@app.route('/categorias', methods=['GET','POST'])
@login_required
def categorias_view():
    uid = session['user_id']
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            db.add_categoria(uid, request.form['nome'], request.form['tipo'], request.form['cor'])
        elif action == 'delete':
            db.delete_categoria(uid, request.form['nome'])
    cats = db.get_categorias(uid)
    return render_template('categorias.html', cats=cats)

@app.route('/icon')
def icon():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">
    <rect width="192" height="192" rx="40" fill="#0a0b0e"/>
    <rect x="16" y="16" width="160" height="160" rx="32" fill="url(#g)"/>
    <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#6ee7b7"/><stop offset="100%" stop-color="#60a5fa"/></linearGradient></defs>
    <text x="96" y="118" text-anchor="middle" font-family="Arial,sans-serif" font-size="90" font-weight="700" fill="#fff">E</text>
    </svg>'''
    return svg, 200, {'Content-Type': 'image/svg+xml'}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('RENDER') is None
    print("[Central Eleve] Iniciando..." + (" (debug)" if debug else " (production)"))
    app.run(debug=debug, host='0.0.0.0', port=port)
