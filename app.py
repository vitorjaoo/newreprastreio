"""
app.py — Portal do Cliente (Flask)
"""
import base64
import hashlib
import io
import re
from functools import wraps
from datetime import datetime

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, send_file, jsonify)

import db
from config import Config
from extrator_pdf import extrair_dados_xml, pdf_para_base64

try:
    import resend
except ImportError:
    resend = None

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

if resend:
    resend.api_key = getattr(Config, 'RESEND_API_KEY', '')

@app.context_processor
def globals_template():
    return {
        "nome_escritorio": Config.NOME_ESCRITORIO,
        "cor_primaria":    Config.COR_PRIMARIA,
        "cor_secundaria":  Config.COR_SECUNDARIA,
        "ano_atual":       datetime.now().year,
    }

with app.app_context():
    db.criar_tabelas()

def hash_senha(s):
    return hashlib.sha256(s.encode()).hexdigest()

def login_cliente_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("perfil") != "cliente":
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def login_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("perfil") != "admin":
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# Decorador para permitir o acesso à Equipe (Leitor) ou ao Admin
def login_admin_ou_leitor_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("perfil") not in ["admin", "leitor"]:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def enviar_email_notificacao(email_destino, assunto, mensagem_html):
    if not resend or not email_destino or not getattr(resend, 'api_key', None):
        return False
    try:
        params = {
            "from": f"{Config.NOME_ESCRITORIO} <nao-responda@seudominio.com.br>",
            "to": [email_destino],
            "subject": assunto,
            "html": mensagem_html,
        }
        resend.Emails.send(params)
        return True
    except Exception as e:
        return False

# ─── AUTENTICAÇÃO ────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("perfil"):
        if session["perfil"] in ["admin", "leitor"]:
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("dashboard"))

    erro = None
    if request.method == "POST":
        cnpj  = request.form.get("cnpj", "").strip()
        senha = request.form.get("senha", "").strip()

        # Login do Admin
        if cnpj.lower() == "admin" and senha == Config.ADMIN_SENHA:
            session["perfil"]  = "admin"
            session["usuario"] = {"nome": "Administrador", "id": 0}
            return redirect(url_for("admin_dashboard"))
            
        # Login da Equipe (Visão Geral - Só Leitura)
        elif cnpj.lower() == "equipe" and senha == getattr(Config, "EQUIPE_SENHA", "equipe123"):
            session["perfil"]  = "leitor"
            session["usuario"] = {"nome": "Equipe Comercial", "id": 0}
            return redirect(url_for("admin_dashboard"))

        # Login do Cliente
        cliente = db.buscar_cliente_cnpj(cnpj)
        if not cliente:
            erro = "CNPJ não encontrado."
        elif hash_senha(senha) != cliente["senha_hash"]:
            erro = "Senha incorreta."
        elif not cliente["ativo"]:
            erro = "Acesso desativado. Entre em contato com o escritório."
        else:
            session["perfil"]  = "cliente"
            session["usuario"] = cliente
            return redirect(url_for("dashboard"))

    return render_template("login.html", erro=erro)

@app.route("/sair")
def sair():
    session.clear()
    return redirect(url_for("login"))


# ─── DOWNLOADS GERAIS (CLIENTE, ADMIN E EQUIPE) ──────────────────────────────
@app.route("/download/nf/<int:nf_id>")
def download_nf(nf_id):
    if not session.get("perfil"): 
        return redirect(url_for("login"))
    
    if session["perfil"] == "cliente":
        cliente = session["usuario"]
        nfs = db.listar_nfs(cliente["id"])
        if not any(n["id"] == nf_id for n in nfs): 
            return "Não autorizado", 403
            
    dados = db.get_pdf_nf(nf_id)
    if not dados or not dados.get("pdf_base64"): return "PDF não disponível", 404
    pdf_bytes = base64.b64decode(dados["pdf_base64"])
    return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=True, download_name=dados.get("nome_arquivo") or f"NF_{nf_id}.pdf")

@app.route("/download/boleto/<int:titulo_id>")
def download_boleto(titulo_id):
    if not session.get("perfil"): 
        return redirect(url_for("login"))
        
    if session["perfil"] == "cliente":
        cliente = session["usuario"]
        titulos = db.listar_titulos(cliente["id"])
        if not any(t["id"] == titulo_id for t in titulos): 
            return "Não autorizado", 403
            
    dados = db.get_pdf_titulo(titulo_id)
    if not dados or not dados.get("boleto_base64"): return "PDF não disponível", 404
    pdf_bytes = base64.b64decode(dados["boleto_base64"])
    return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=True, download_name=dados.get("nome_arquivo") or f"Boleto_{titulo_id}.pdf")


# ─── ROTAS DO CLIENTE ────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_cliente_required
def dashboard():
    cliente = session["usuario"]
    nfs     = db.listar_nfs(cliente["id"])
    titulos = db.listar_titulos(cliente["id"])

    hoje = datetime.now().strftime("%Y-%m-%d")
    titulos_abertos  = [t for t in titulos if t["status"] == "aberto"]
    titulos_vencidos = []
    for t in titulos_abertos:
        try:
            p = t["vencimento"].split("/")
            if f"{p[2]}-{p[1]}-{p[0]}" < hoje:
                titulos_vencidos.append(t)
        except Exception:
            pass

    for nf in nfs:
        nf["eventos"] = db.listar_eventos_rastreio(nf["id"])
        nf["tem_rastreio"] = len(nf["eventos"]) > 0

    return render_template("dashboard.html", cliente=cliente, nfs=nfs, 
                           titulos_abertos=titulos_abertos, titulos_vencidos=titulos_vencidos)

@app.route("/entrega/<int:nf_id>")
@login_cliente_required
def entrega(nf_id):
    cliente = session["usuario"]
    nfs     = db.listar_nfs(cliente["id"])
    nf      = next((n for n in nfs if n["id"] == nf_id), None)
    if not nf:
        flash("Nota fiscal não encontrada.", "erro")
        return redirect(url_for("dashboard"))

    nf["eventos"]    = db.listar_eventos_rastreio(nf_id)
    nf["pdf"]        = db.get_pdf_nf(nf_id)
    titulos_nf       = [t for t in db.listar_titulos(cliente["id"]) if t.get("nf_id") == nf_id]
    return render_template("entrega.html", cliente=cliente, nf=nf, titulos=titulos_nf)

@app.route("/financeiro")
@login_cliente_required
def financeiro():
    cliente = session["usuario"]
    titulos = db.listar_titulos(cliente["id"])
    hoje    = datetime.now().strftime("%Y-%m-%d")

    from datetime import date
    for t in titulos:
        try:
            p = t["vencimento"].split("/")
            iso = f"{p[2]}-{p[1]}-{p[0]}"
            venc_date = date.fromisoformat(iso)
            hoje_date = date.today()
            t["dias_vencimento"] = (venc_date - hoje_date).days
            t["status_visual"] = "vencido" if t["status"] == "aberto" and iso < hoje else t["status"]
        except Exception:
            t["status_visual"] = t["status"]
            t["dias_vencimento"] = None

    em_aberto = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "aberto")
    quitado   = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "pago")
    return render_template("financeiro.html", cliente=cliente, titulos=titulos, em_aberto=em_aberto, quitado=quitado)

@app.route("/trocar-senha", methods=["GET", "POST"])
@login_cliente_required
def trocar_senha():
    cliente = session["usuario"]
    if request.method == "POST":
        atual, nova, conf = request.form.get("senha_atual", ""), request.form.get("senha_nova", ""), request.form.get("confirmar", "")
        dados = db.buscar_cliente_cnpj(cliente["cnpj"])
        if hash_senha(atual) != dados["senha_hash"]: flash("Senha atual incorreta.", "erro")
        elif nova != conf: flash("As senhas não coincidem.", "erro")
        elif len(nova) < 4: flash("A nova senha deve ter pelo menos 4 caracteres.", "erro")
        else:
            db.atualizar_senha(cliente["id"], hash_senha(nova))
            flash("Senha alterada com sucesso!", "sucesso")
            return redirect(url_for("dashboard"))
    return render_template("trocar_senha.html", cliente=cliente)


# ─── ROTAS DO ADMIN E EQUIPA (VISÃO GERAL GLOBAL) ────────────────────────────
@app.route("/admin")
@login_admin_ou_leitor_required
def admin_dashboard():
    nfs, titulos, clientes = db.listar_todas_nfs(), db.listar_todos_titulos(), db.listar_clientes()
    em_aberto = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "aberto")
    return render_template("admin/dashboard.html", total_clientes=len(clientes), total_nfs=len(nfs), 
                           titulos_abertos=len([t for t in titulos if t["status"] == "aberto"]), em_aberto=em_aberto)

@app.route("/admin/rastreio")
@login_admin_ou_leitor_required
def admin_rastreio():
    nfs = db.listar_todas_nfs()
    for nf in nfs: nf["eventos"] = db.listar_eventos_rastreio(nf["id"])
    clientes = sorted(list({n["cliente"] for n in nfs}))
    return render_template("admin/rastreio.html", nfs=nfs, clientes=clientes, now_str=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route("/admin/clientes", methods=["GET", "POST"])
@login_admin_ou_leitor_required
def admin_clientes():
    if request.method == "POST":
        if session["perfil"] == "leitor":
            flash("Acesso Negado: Você está no modo Leitura.", "erro")
            return redirect(url_for("admin_clientes"))
            
        acao = request.form.get("acao")
        if acao == "cadastrar":
            try:
                db.criar_cliente(request.form["nome"], request.form["cnpj"], request.form.get("email",""), request.form.get("whatsapp",""), hash_senha(request.form["senha"]))
                flash(f"Cliente {request.form['nome']} cadastrado!", "sucesso")
            except Exception
