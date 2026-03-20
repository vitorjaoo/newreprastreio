"""
app.py — Portal do Cliente (Flask) com Resend e Edição de Clientes
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

# ─── FUNÇÃO DE ENVIO DE E-MAIL VIA RESEND ────────────────────────────────────
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
        print(f"[E-mail Resend] Enviado com sucesso para {email_destino}")
        return True
    except Exception as e:
        print(f"[E-mail Resend] Erro ao enviar para {email_destino}: {e}")
        return False
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("perfil"):
        if session["perfil"] == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("dashboard"))

    erro = None
    if request.method == "POST":
        cnpj  = request.form.get("cnpj", "").strip()
        senha = request.form.get("senha", "").strip()

        if cnpj.lower() == "admin" and senha == Config.ADMIN_SENHA:
            session["perfil"]  = "admin"
            session["usuario"] = {"nome": "Administrador", "id": 0}
            return redirect(url_for("admin_dashboard"))

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

@app.route("/download/nf/<int:nf_id>")
@login_cliente_required
def download_nf(nf_id):
    cliente = session["usuario"]
    nfs     = db.listar_nfs(cliente["id"])
    if not any(n["id"] == nf_id for n in nfs): return "Não autorizado", 403
    dados = db.get_pdf_nf(nf_id)
    if not dados or not dados.get("pdf_base64"): return "PDF não disponível", 404
    pdf_bytes = base64.b64decode(dados["pdf_base64"])
    return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=True, download_name=dados.get("nome_arquivo") or f"NF_{nf_id}.pdf")

@app.route("/download/boleto/<int:titulo_id>")
@login_cliente_required
def download_boleto(titulo_id):
    cliente = session["usuario"]
    titulos = db.listar_titulos(cliente["id"])
    if not any(t["id"] == titulo_id for t in titulos): return "Não autorizado", 403
    dados = db.get_pdf_titulo(titulo_id)
    if not dados or not dados.get("boleto_base64"): return "PDF não disponível", 404
    pdf_bytes = base64.b64decode(dados["boleto_base64"])
    return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=True, download_name=dados.get("nome_arquivo") or f"Boleto_{titulo_id}.pdf")

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

@app.route("/admin")
@login_admin_required
def admin_dashboard():
    nfs, titulos, clientes = db.listar_todas_nfs(), db.listar_todos_titulos(), db.listar_clientes()
    em_aberto = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "aberto")
    return render_template("admin/dashboard.html", total_clientes=len(clientes), total_nfs=len(nfs), 
                           titulos_abertos=len([t for t in titulos if t["status"] == "aberto"]), em_aberto=em_aberto)

@app.route("/admin/upload", methods=["GET", "POST"])
@login_admin_required
def admin_upload():
    clientes  = db.listar_clientes()
    tipo_ativo = request.args.get("tipo", "nf")

    if request.method == "POST":
        tipo, cliente_id = request.form.get("tipo"), int(request.form.get("cliente_id"))
        arquivo = request.files.get("arquivo")

        cliente_alvo = next((c for c in clientes if c["id"] == cliente_id), None)
        email_cliente = cliente_alvo["email"] if (cliente_alvo and "email" in cliente_alvo) else ""
        nome_cliente = cliente_alvo["nome"] if cliente_alvo else "Cliente"

        if not arquivo or arquivo.filename == "":
            flash("Selecione um arquivo PDF.", "erro")
            return redirect(url_for("admin_upload"))
        if not arquivo.filename.lower().endswith(".pdf"):
            flash("Arquivo inválido. Selecione um PDF.", "erro")
            return redirect(url_for("admin_upload"))

        pdf_b64 = base64.b64encode(arquivo.read()).decode()

        if tipo == "nf":
            numero_nf = request.form.get("numero_nf","")
            nf_id = db.inserir_nf(
                cliente_id=cliente_id, numero_nf=numero_nf, valor=float(request.form.get("valor") or 0),
                data_emissao=request.form.get("data_emissao",""), pdf_base64=pdf_b64, nome_arquivo=arquivo.filename,
                codigo_rastreio=request.form.get("codigo_rastreio",""), transportadora=request.form.get("transportadora",""),
                status=request.form.get("status","ativo"), observacao=request.form.get("observacao",""), representada=request.form.get("representada","")
            )
            
            boletos_salvos, i = 0, 0
            while True:
                num_dup = request.form.get(f"dup_num_{i}")
                if not num_dup: break
                
                venc_dup, val_dup, pdf_dup = request.form.get(f"dup_venc_{i}"), request.form.get(f"dup_val_{i}"), request.files.get(f"pdf_boleto_{i}")
                if pdf_dup and pdf_dup.filename:
                    db.inserir_titulo(
                        cliente_id=cliente_id, numero_titulo=num_dup, valor=float(val_dup or 0), vencimento=venc_dup,
                        boleto_base64=base64.b64encode(pdf_dup.read()).decode(), nome_arquivo=pdf_dup.filename, nf_id=nf_id
                    )
                    boletos_salvos += 1
                i += 1

            if boletos_salvos > 0: 
                flash(f"NF {numero_nf} e {boletos_salvos} boleto(s) salvos com sucesso!", "sucesso")
            else: 
                flash(f"NF {numero_nf} salva com sucesso!", "sucesso")

            if email_cliente:
                assunto = f"Nova Nota Fiscal - {Config.NOME_ESCRITORIO}"
                html = f"""
                <div style="font-family: Arial, sans-serif; color: #333; max-width: 600px;">
                    <h2 style="color: {Config.COR_PRIMARIA};">Olá, {nome_cliente}!</h2>
                    <p>Uma nova <strong>Nota Fiscal (Nº {numero_nf})</strong> foi disponibilizada no seu portal.</p>
                    <p>Acesse o sistema para verificar os valores, fazer o download dos boletos e acompanhar a entrega.</p>
                    <br>
                    <p>Atenciosamente,<br>Equipe {Config.NOME_ESCRITORIO}</p>
                </div>
                """
                enviar_email_notificacao(email_cliente, assunto, html)

        elif tipo == "boleto":
            nf_id, numero_titulo = request.form.get("nf_id"), request.form.get("numero_titulo","")
            db.inserir_titulo(
                cliente_id=cliente_id, numero_titulo=numero_titulo, valor=float(request.form.get("valor") or 0),
                vencimento=request.form.get("vencimento",""), boleto_base64=pdf_b64, nome_arquivo=arquivo.filename, nf_id=int(nf_id) if nf_id else None
            )
            flash(f"Boleto {numero_titulo} salvo!", "sucesso")

            if email_cliente:
                assunto = f"Novo Boleto Disponível - {Config.NOME_ESCRITORIO}"
                html = f"""
                <div style="font-family: Arial, sans-serif; color: #333; max-width: 600px;">
                    <h2 style="color: {Config.COR_PRIMARIA};">Olá, {nome_cliente}!</h2>
                    <p>Um novo <strong>Boleto / Título (Nº {numero_titulo})</strong> foi adicionado ao seu painel financeiro.</p>
                    <p>Acesse o portal para visualizar a data de vencimento e realizar o download para pagamento.</p>
                    <br>
                    <p>Atenciosamente,<br>Equipe {Config.NOME_ESCRITORIO}</p>
                </div>
                """
                enviar_email_notificacao(email_cliente, assunto, html)

        return redirect(url_for("admin_upload"))

    return render_template("admin/upload.html", clientes=clientes, tipo_ativo=tipo_ativo)

@app.route("/admin/nfs-do-cliente/<int:cliente_id>")
@login_admin_required
def admin_nfs_cliente(cliente_id):
    return jsonify([{"id": n["id"], "numero_nf": n["numero_nf"], "data_emissao": n["data_emissao"]} for n in db.listar_nfs(cliente_id)])

@app.route("/admin/rastreio")
@login_admin_required
def admin_rastreio():
    nfs = db.listar_todas_nfs()
    for nf in nfs: nf["eventos"] = db.listar_eventos_rastreio(nf["id"])
    clientes = sorted(list({n["cliente"] for n in nfs}))
    return render_template("admin/rastreio.html", nfs=nfs, clientes=clientes, now_str=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route("/admin/rastreio/adicionar", methods=["POST"])
@login_admin_required
def admin_rastreio_adicionar():
    nf_id, descricao, data_hora = int(request.form.get("nf_id")), request.form.get("descricao","").strip(), request.form.get("data_hora","").strip()
    if descricao:
        db.inserir_evento_rastreio(nf_id, descricao, data_hora)
        flash("Evento adicionado!", "sucesso")
    return redirect(url_for("admin_rastreio") + f"#nf-{nf_id}")

@app.route("/admin/rastreio/remover/<int:evento_id>", methods=["POST"])
@login_admin_required
def admin_rastreio_remover(evento_id):
    db.deletar_evento_rastreio(evento_id)
    return redirect(request.referrer or url_for("admin_rastreio"))

@app.route("/admin/clientes", methods=["GET", "POST"])
@login_admin_required
def admin_clientes():
    if request.method == "POST":
        acao = request.form.get("acao")
        if acao == "cadastrar":
            try:
                db.criar_cliente(request.form["nome"], request.form["cnpj"], request.form.get("email",""), request.form.get("whatsapp",""), hash_senha(request.form["senha"]))
                flash(f"Cliente {request.form['nome']} cadastrado!", "sucesso")
            except Exception: flash(f"Erro: CNPJ já cadastrado?", "erro")
        elif acao == "inativar":
            db.toggle_cliente_ativo(int(request.form["cliente_id"]))
            flash("Status atualizado.", "sucesso")
        return redirect(url_for("admin_clientes"))
    return render_template("admin/clientes.html", clientes=db.listar_clientes())


# ─── NOVA ROTA PARA EDITAR O CLIENTE ─────────────────────────────────────────
@app.route("/admin/clientes/editar/<int:cliente_id>", methods=["POST"])
@login_admin_required
def admin_clientes_editar(cliente_id):
    nome = request.form.get("nome", "").strip()
    cnpj = request.form.get("cnpj", "").strip()
    email = request.form.get("email", "").strip()
    whatsapp = request.form.get("whatsapp", "").strip()
    nova_senha = request.form.get("nova_senha", "").strip()
    
    senha_hasheada = hash_senha(nova_senha) if nova_senha else None
    
    try:
        db.atualizar_cliente(cliente_id, nome, cnpj, email, whatsapp, senha_hasheada)
        flash(f"Cliente {nome} atualizado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro ao atualizar cliente (CNPJ duplicado?): {str(e)}", "erro")
        
    return redirect(url_for("admin_clientes"))
# ─────────────────────────────────────────────────────────────────────────────


@app.route("/admin/nfs", methods=["GET", "POST"])
@login_admin_required
def admin_nfs():
    if request.method == "POST":
        db.atualizar_status_nf(int(request.form["nf_id"]), request.form.get("status",""), request.form.get("observacao",""))
        flash("NF atualizada!", "sucesso")
        return redirect(url_for("admin_nfs"))
    return render_template("admin/nfs.html", nfs=db.listar_todas_nfs())

@app.route("/admin/titulos", methods=["GET", "POST"])
@login_admin_required
def admin_titulos():
    if request.method == "POST":
        db.marcar_titulo_pago(int(request.form["titulo_id"]))
        flash("Marcado como pago!", "sucesso")
        return redirect(url_for("admin_titulos"))
    titulos = db.listar_todos_titulos()
    return render_template("admin/titulos.html", titulos=titulos, 
                           em_aberto=sum(float(t["valor"] or 0) for t in titulos if t["status"] == "aberto"), 
                           recebido=sum(float(t["valor"] or 0) for t in titulos if t["status"] == "pago"))

@app.route("/admin/extrair-xml", methods=["POST"])
@login_admin_required
def extrair_xml():
    try:
        arquivo = request.files.get("xml")
        if not arquivo or arquivo.filename == "": return jsonify({"sucesso": False, "erro": "Nenhum arquivo"})
        dados = extrair_dados_xml(arquivo.read())
        return jsonify(dados)
    except Exception as e:
        return jsonify({"sucesso": False, "erro": f"Erro interno: {str(e)}"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
