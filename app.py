import base64, hashlib, io, re, sys
from functools import wraps
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
import db
from config import Config
from extrator_pdf import extrair_dados_xml

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# 🔹 FORMATADOR UNIVERSAL DE MOEDA PARA A TELA (Ex: 2.889,90) 🔹
def formatar_moeda(valor):
    try:
        if valor is None or str(valor).strip() == "":
            return "0,00"
        v = float(valor)
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00"

# 🔹 CÉREBRO FINANCEIRO: CONVERTE QUALQUER TEXTO PARA NÚMERO DE BANCO 🔹
def limpar_moeda(v_str):
    if not v_str: return 0.0
    v_str = str(v_str).strip()
    v_str = re.sub(r'[^\d\.,]', '', v_str)
    if not v_str: return 0.0
    try:
        if '.' in v_str and ',' in v_str:
            if v_str.rfind(',') > v_str.rfind('.'):
                return float(v_str.replace('.', '').replace(',', '.'))
            else:
                return float(v_str.replace(',', ''))
        elif ',' in v_str:
            return float(v_str.replace(',', '.'))
        elif '.' in v_str:
            parts = v_str.split('.')
            if len(parts[-1]) == 2: return float(v_str)
            else: return float(v_str.replace('.', ''))
        return float(v_str)
    except:
        return 0.0

@app.context_processor
def globals_template():
    return {
        "nome_escritorio": Config.NOME_ESCRITORIO,
        "cor_primaria": Config.COR_PRIMARIA,
        "cor_secundaria": Config.COR_SECUNDARIA,
        "now": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "formatar_moeda": formatar_moeda
    }

with app.app_context():
    db.criar_tabelas()

def hash_senha(s):
    return hashlib.sha256(s.encode()).hexdigest()

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("perfil"): return redirect(url_for("login"))
            if role == "admin" and session.get("perfil") != "admin":
                flash("Acesso restrito.", "erro")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorator
    return decorator

def parse_vencimento(v):
    if not v: return "9999-12-31"
    try:
        if "-" in v and len(v.split("-")[0]) == 4: return v  
        if "/" in v:
            p = v.split("/")
            return f"{p[2]}-{p[1]}-{p[0]}"
    except: pass
    return "9999-12-31"

@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("perfil"):
        return redirect(url_for("admin_dashboard" if session["perfil"] == "admin" else "dashboard"))
    if request.method == "POST":
        u, s = request.form.get("cnpj", "").strip(), request.form.get("senha", "").strip()
        if u.lower() == "admin" and s == Config.ADMIN_SENHA:
            session.update({"perfil": "admin", "usuario": {"nome": "Admin"}})
            return redirect(url_for("admin_dashboard"))
        if u.lower() == "equipe" and s == Config.EQUIPE_SENHA:
            session.update({"perfil": "leitor", "usuario": {"nome": "Equipe Interna", "id": 0}})
            return redirect(url_for("dashboard"))
        c = db.buscar_cliente_cnpj(u)
        if c and hash_senha(s) == c["senha_hash"] and c["ativo"]:
            session.update({"perfil": "cliente", "usuario": c})
            return redirect(url_for("dashboard"))
        flash("Credenciais inválidas.", "erro")
    return render_template("login.html")

@app.route("/sair")
def sair():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required()
def dashboard():
    if session["perfil"] == "admin": return redirect(url_for("admin_dashboard"))
    nfs = db.listar_todas_nfs() if session["perfil"] == "leitor" else db.listar_nfs(session["usuario"]["id"])
    titulos = db.listar_todos_titulos() if session["perfil"] == "leitor" else db.listar_titulos(session["usuario"]["id"])
    hoje = datetime.now().strftime("%Y-%m-%d")
    titulos_abertos = [t for t in titulos if t["status"] == "aberto"]
    titulos_vencidos = [t for t in titulos_abertos if parse_vencimento(t.get("vencimento")) < hoje]
    for nf in nfs:
        nf["eventos"] = db.listar_eventos_rastreio(nf["id"])
        nf["tem_rastreio"] = len(nf["eventos"]) > 0
        nf["valor"] = formatar_moeda(nf.get("valor"))
    return render_template("dashboard.html", nfs=nfs, titulos_abertos=titulos_abertos, titulos_vencidos=titulos_vencidos)

@app.route("/financeiro")
@login_required()
def financeiro():
    if session["perfil"] == "admin": return redirect(url_for("admin_dashboard"))
    titulos = db.listar_todos_titulos() if session["perfil"] == "leitor" else db.listar_titulos(session["usuario"]["id"])
    hoje = datetime.now().strftime("%Y-%m-%d")
    hoje_date = date.today()
    em_aberto_val = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "aberto")
    quitado_val = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "pago")
    for t in titulos:
        iso = parse_vencimento(t.get("vencimento"))
        t["data_ordem"] = iso
        if iso != "9999-12-31":
            try:
                venc_date = date.fromisoformat(iso)
                t["dias_vencimento"] = (venc_date - hoje_date).days
                t["status_visual"] = "vencido" if t["status"] == "aberto" and iso < hoje else t["status"]
            except: t["status_visual"] = t["status"]
        t["valor"] = formatar_moeda(t.get("valor"))
    titulos.sort(key=lambda x: x["data_ordem"])
    return render_template("financeiro.html", titulos=titulos, em_aberto=formatar_moeda(em_aberto_val), quitado=formatar_moeda(quitado_val))

@app.route("/admin/upload", methods=["GET", "POST"])
@login_required("admin")
def admin_upload():
    if request.method == "POST":
        try:
            tipo = request.form.get("tipo")
            arquivo = request.files.get("arquivo")
            if not arquivo or not arquivo.filename.lower().endswith(".pdf"):
                flash("Selecione um PDF válido.", "erro")
                return redirect(url_for("admin_upload"))
            pdf_b64 = base64.b64encode(arquivo.read()).decode()
            cliente_id = int(request.form.get("cliente_id", 0))
            if tipo == "nf":
                nf_id = db.inserir_nf(cliente_id, request.form.get("numero_nf"), limpar_moeda(request.form.get("valor")), request.form.get("data_emissao"), pdf_b64, arquivo.filename, request.form.get("codigo_rastreio"), request.form.get("transportadora"), "ativo", request.form.get("observacao"), request.form.get("representada"))
                for i in range(50):
                    num = request.form.get(f"dup_num_{i}")
                    if not num: continue
                    p_pdf = request.files.get(f"pdf_boleto_{i}")
                    if p_pdf:
                        db.inserir_titulo(cliente_id, num, limpar_moeda(request.form.get(f"dup_val_{i}")), request.form.get(f"dup_venc_{i}"), base64.b64encode(p_pdf.read()).decode(), p_pdf.filename, nf_id)
                flash("NF e Boletos salvos!", "sucesso")
            elif tipo == "boleto":
                db.inserir_titulo(cliente_id, request.form.get("numero_titulo"), limpar_moeda(request.form.get("valor")), request.form.get("vencimento"), pdf_b64, arquivo.filename, request.form.get("nf_id"))
                flash("Boleto salvo!", "sucesso")
        except Exception as e: flash(f"Erro: {str(e)}", "erro")
        return redirect(url_for("admin_upload"))
    return render_template("admin/upload.html", clientes=db.listar_clientes(), tipo_ativo=request.args.get("tipo", "nf"))

@app.route("/admin/extrair-xml", methods=["POST"])
@login_required("admin")
def extrair_xml():
    f = request.files.get("xml")
    if not f: return jsonify({"sucesso": False})
    dados = extrair_dados_xml(f.read())
    if isinstance(dados, dict) and dados.get("sucesso"):
        if "valor" in dados: dados["valor"] = formatar_moeda(dados["valor"])
        if "boletos" in dados:
            for b in dados["boletos"]:
                if "valor" in b: b["valor"] = formatar_moeda(b["valor"])
    return jsonify(dados)

# (Outras rotas administrativas omitidas para brevidade, manter conforme código anterior)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
