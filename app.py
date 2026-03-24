import base64, hashlib, io, re, sys, os
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

# 🔹 CÉREBRO FINANCEIRO: LÊ QUALQUER TIPO DE DINHEIRO (2889.90 ou 2.889,90) 🔹
def limpar_moeda(v_str):
    if not v_str: return 0.0
    v_str = str(v_str).strip()
    v_str = re.sub(r'[^\d\.,]', '', v_str) # Remove tudo que não for número, ponto ou vírgula
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
            if len(parts[-1]) == 2:
                return float(v_str)
            else:
                return float(v_str.replace('.', ''))
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
            if not session.get("perfil"):
                return redirect(url_for("login"))
            if role == "admin" and session.get("perfil") != "admin":
                flash("Acesso restrito ao administrador.", "erro")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator

def parse_vencimento(v):
    if not v: return "9999-12-31"
    try:
        if "-" in v and len(v.split("-")[0]) == 4:
            return v  
        if "/" in v:
            p = v.split("/")
            return f"{p[2]}-{p[1]}-{p[0]}"
    except:
        pass
    return "9999-12-31"

@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("perfil"):
        if session["perfil"] == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("dashboard"))
        
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

# ─── ROTAS DO CLIENTE E EQUIPE ───────────────────────────────────────────────

@app.route("/dashboard")
@login_required()
def dashboard():
    if session["perfil"] == "admin": 
        return redirect(url_for("admin_dashboard"))
    
    if session["perfil"] == "leitor":
        nfs = db.listar_todas_nfs()
        titulos = db.listar_todos_titulos()
        for n in nfs:
            n["numero_nf"] = f"{n['numero_nf']} - {n.get('cliente', '')}"
        for t in titulos:
            t["numero_titulo"] = f"{t['numero_titulo']} - {t.get('cliente', '')}"
    else:
        nfs = db.listar_nfs(session["usuario"]["id"])
        titulos = db.listar_titulos(session["usuario"]["id"])

    hoje = datetime.now().strftime("%Y-%m-%d")
    titulos_abertos  = [t for t in titulos if t["status"] == "aberto"]
    titulos_vencidos = [t for t in titulos_abertos if parse_vencimento(t.get("vencimento")) < hoje]

    for nf in nfs:
        nf["eventos"] = db.listar_eventos_rastreio(nf["id"])
        nf["tem_rastreio"] = len(nf["eventos"]) > 0
        nf["valor"] = formatar_moeda(nf.get("valor"))

    for t in titulos:
        t["valor"] = formatar_moeda(t.get("valor"))

    return render_template("dashboard.html", nfs=nfs, titulos_abertos=titulos_abertos, titulos_vencidos=titulos_vencidos)

@app.route("/financeiro")
@login_required()
def financeiro():
    if session["perfil"] == "admin": 
        return redirect(url_for("admin_dashboard"))
    
    if session["perfil"] == "leitor":
        titulos = db.listar_todos_titulos()
        for t in titulos:
            t["numero_titulo"] = f"{t['numero_titulo']} - {t.get('cliente', '')}"
    else:
        titulos = db.listar_titulos(session["usuario"]["id"])

    hoje = datetime.now().strftime("%Y-%m-%d")
    hoje_date = date.today()
    
    em_aberto_val = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "aberto")
    quitado_val   = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "pago")
    
    em_aberto = formatar_moeda(em_aberto_val)
    quitado = formatar_moeda(quitado_val)

    for t in titulos:
        iso = parse_vencimento(t.get("vencimento"))
        t["data_ordem"] = iso
        if iso != "9999-12-31":
            try:
                venc_date = date.fromisoformat(iso)
                t["dias_vencimento"] = (venc_date - hoje_date).days
                t["status_visual"] = "vencido" if t["status"] == "aberto" and iso < hoje else t["status"]
            except:
                t["status_visual"] = t["status"]
                t["dias_vencimento"] = None
        else:
            t["status_visual"] = t["status"]
            t["dias_vencimento"] = None
            
        t["valor"] = formatar_moeda(t.get("valor"))

    titulos.sort(key=lambda x: x["data_ordem"])
    
    return render_template("financeiro.html", titulos=titulos, em_aberto=em_aberto, quitado=quitado)

@app.route("/solicitar-pagamento/<int:titulo_id>", methods=["POST"])
@login_required()
def solicitar_pagamento(titulo_id):
    flash("Solicitação recebida com sucesso! Em breve entraremos em contato.", "sucesso")
    return redirect(url_for("financeiro"))

@app.route("/entrega/<int:nf_id>")
@login_required()
def entrega(nf_id):
    if session["perfil"] == "admin": 
        return redirect(url_for("admin_dashboard"))
    
    if session["perfil"] == "leitor":
        nfs = db.listar_todas_nfs()
        titulos_nf = [t for t in db.listar_todos_titulos() if t.get("nf_id") == nf_id]
        for t in titulos_nf:
            t["numero_titulo"] = f"{t['numero_titulo']} - {t.get('cliente', '')}"
    else:
        nfs = db.listar_nfs(session["usuario"]["id"])
        titulos_nf = [t for t in db.listar_titulos(session["usuario"]["id"]) if t.get("nf_id") == nf_id]

    nf = next((n for n in nfs if n["id"] == nf_id), None)
    if not nf:
        flash("Nota fiscal não encontrada.", "erro")
        return redirect(url_for("dashboard"))

    nf["eventos"] = db.listar_eventos_rastreio(nf_id)
    nf["pdf"] = db.get_pdf_nf(nf_id)
    nf["valor"] = formatar_moeda(nf.get("valor"))
    
    for t in titulos_nf:
        t["data_ordem"] = parse_vencimento(t.get("vencimento"))
        t["valor"] = formatar_moeda(t.get("valor"))
        
    titulos_nf.sort(key=lambda x: x["data_ordem"])
    
    return render_template("entrega.html", nf=nf, titulos=titulos_nf)

@app.route("/trocar-senha", methods=["GET", "POST"])
@login_required()
def trocar_senha():
    if session["perfil"] != "cliente": return redirect(url_for("dashboard"))
    cliente = session["usuario"]
    if request.method == "POST":
        atual, nova, conf = request.form.get("senha_atual", ""), request.form.get("senha_nova", ""), request.form.get("confirmar", "")
        dados = db.buscar_cliente_cnpj(cliente["cnpj"])
        if hash_senha(atual) != dados["senha_hash"]: flash("Senha atual incorreta.", "erro")
        elif nova != conf: flash("As senhas não coincidem.", "erro")
        elif len(nova) < 4: flash("A nova senha deve ter no mínimo 4 caracteres.", "erro")
        else:
            db.atualizar_senha(cliente["id"], hash_senha(nova))
            flash("Senha alterada com sucesso!", "sucesso")
            return redirect(url_for("dashboard"))
    return render_template("trocar_senha.html", cliente=cliente)

@app.route("/download/nf/<int:nf_id>")
@login_required()
def download_nf(nf_id):
    if session["perfil"] == "cliente":
        nfs = db.listar_nfs(session["usuario"]["id"])
        if not any(n["id"] == nf_id for n in nfs): return "Não autorizado", 403
    dados = db.get_pdf_nf(nf_id)
    if not dados or not dados.get("pdf_base64"): return "PDF não disponível", 404
    return send_file(io.BytesIO(base64.b64decode(dados["pdf_base64"])), mimetype="application/pdf", as_attachment=True, download_name=dados.get("nome_arquivo") or f"NF_{nf_id}.pdf")

@app.route("/download/boleto/<int:titulo_id>")
@login_required()
def download_boleto(titulo_id):
    if session["perfil"] == "cliente":
        titulos = db.listar_titulos(session["usuario"]["id"])
        if not any(t["id"] == titulo_id for t in titulos): return "Não autorizado", 403
    dados = db.get_pdf_titulo(titulo_id)
    if not dados or not dados.get("boleto_base64"): return "PDF não disponível", 404
    return send_file(io.BytesIO(base64.b64decode(dados["boleto_base64"])), mimetype="application/pdf", as_attachment=True, download_name=dados.get("nome_arquivo") or f"Boleto_{titulo_id}.pdf")

# ─── ROTAS DA ADMINISTRAÇÃO ──────────────────────────────────────────────────

@app.route("/admin")
@login_required("admin")
def admin_dashboard():
    nfs = db.listar_todas_nfs()
    titulos = db.listar_todos_titulos()
    clientes = db.listar_clientes()
    
    em_aberto_val = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "aberto")
    em_aberto = formatar_moeda(em_aberto_val)
    
    titulos_abertos = len([t for t in titulos if t["status"] == "aberto"])
    return render_template("admin/dashboard.html", total_clientes=len(clientes), total_nfs=len(nfs), titulos_abertos=titulos_abertos, em_aberto=em_aberto)

@app.route("/admin/upload", methods=["GET", "POST"])
@login_required("admin")
def admin_upload():
    if request.method == "POST":
        try:
            tipo = request.form.get("tipo")
            cliente_id = int(request.form.get("cliente_id", 0))
            arquivo = request.files.get("arquivo")
            pdf_b64 = base64.b64encode(arquivo.read()).decode() if arquivo and arquivo.filename else ""
            nome_arq_nf = arquivo.filename if arquivo and arquivo.filename else ""
            
            if tipo == "nf":
                numero_nf = request.form.get("numero_nf", "")
                valor = limpar_moeda(request.form.get("valor", "0"))
                
                nf_id = db.inserir_nf(
                    cliente_id, numero_nf, valor, 
                    request.form.get("data_emissao", ""), 
                    pdf_b64, nome_arq_nf, 
                    request.form.get("codigo_rastreio", ""), 
                    request.form.get("transportadora", ""), 
                    "ativo", 
                    request.form.get("observacao", ""), 
                    request.form.get("representada", "")
                )
                
                boletos_salvos = 0
                for i in range(50):
                    num_dup = request.form.get(f"dup_num_{i}")
                    if not num_dup or str(num_dup).strip() == "":
                        continue
                        
                    val_dup = limpar_moeda(request.form.get(f"dup_val_{i}", "0"))
                    p_pdf = request.files.get(f"pdf_boleto_{i}")
                    
                    b64_boleto = ""
                    nome_arq_boleto = ""
                    
                    # Permite salvar mesmo sem o ficheiro do boleto (Boleto Opcional)
                    if p_pdf and p_pdf.filename:
                        b64_boleto = base64.b64encode(p_pdf.read()).decode()
                        nome_arq_boleto = p_pdf.filename
                            
                    db.inserir_titulo(
                        cliente_id, num_dup, val_dup, 
                        request.form.get(f"dup_venc_{i}", ""), 
                        b64_boleto, nome_arq_boleto, nf_id
                    )
                    boletos_salvos += 1
                        
                flash(f"NF {numero_nf} salva com {boletos_salvos} parcelas/boletos!", "sucesso")
                return redirect(url_for("admin_nfs"))
                
            elif tipo == "boleto":
                valor = limpar_moeda(request.form.get("valor", "0"))
                n_id = request.form.get("nf_id")
                n_id_val = int(n_id) if n_id and str(n_id).strip() != "" else None
                
                db.inserir_titulo(
                    cliente_id, request.form.get("numero_titulo", ""), valor, 
                    request.form.get("vencimento", ""), pdf_b64, nome_arq_nf, n_id_val
                )
                flash("Boleto individual salvo com sucesso!", "sucesso")
                return redirect(url_for("admin_titulos"))
            else:
                flash("Selecione se é uma Nota Fiscal ou um Boleto.", "erro")
                
        except Exception as e:
            print(">>> ERRO NO SISTEMA DE UPLOAD: ", str(e), file=sys.stderr, flush=True)
            flash(f"Falha ao salvar. Verifique os dados. Erro: {str(e)}", "erro")
            
        return redirect(url_for("admin_upload"))
        
    return render_template("admin/upload.html", clientes=db.listar_clientes(), tipo_ativo=request.args.get("tipo", "nf"))

@app.route("/admin/clientes", methods=["GET", "POST"])
@login_required("admin")
def admin_clientes():
    if request.method == "POST":
        acao = request.form.get("acao")
        if acao == "cadastrar":
            db.criar_cliente(request.form["nome"], request.form["cnpj"], request.form.get("email"), request.form.get("whatsapp"), hash_senha(request.form["senha"]))
        elif acao == "inativar":
            db.toggle_cliente_ativo(int(request.form["cliente_id"]))
        return redirect(url_for("admin_clientes"))
    return render_template("admin/clientes.html", clientes=db.listar_clientes())

@app.route("/admin/clientes/editar/<int:cid>", methods=["POST"])
@login_required("admin")
def admin_clientes_editar(cid):
    ns = request.form.get("nova_senha")
    db.atualizar_cliente(cid, request.form["nome"], request.form["cnpj"], request.form["email"], request.form["whatsapp"], hash_senha(ns) if ns else None)
    return redirect(url_for("admin_clientes"))

@app.route("/admin/nfs", methods=["GET", "POST"])
@login_required("admin")
def admin_nfs():
    nfs = db.listar_todas_nfs()
    
    if request.method == "POST":
        db.atualizar_status_nf(int(request.form["nf_id"]), request.form.get("status",""), request.form.get("observacao",""))
        flash("NF atualizada!", "sucesso")
        return redirect(url_for("admin_nfs"))
        
    for n in nfs:
        n["valor"] = formatar_moeda(n.get("valor"))
        
    return render_template("admin/nfs.html", nfs=nfs)

@app.route("/admin/nfs/deletar/<int:nf_id>", methods=["POST"])
@login_required("admin")
def admin_deletar_nf(nf_id):
    try:
        db.deletar_nf(nf_id)
        flash("Nota Fiscal apagada com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro ao apagar NF: {str(e)}", "erro")
    return redirect(url_for("admin_nfs"))

@app.route("/admin/titulos", methods=["GET", "POST"])
@login_required("admin")
def admin_titulos():
    if request.method == "POST":
        db.marcar_titulo_pago(int(request.form["titulo_id"]))
        flash("Marcado como pago!", "sucesso")
        return redirect(url_for("admin_titulos"))
        
    titulos = db.listar_todos_titulos()
    
    em_aberto_val = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "aberto")
    recebido_val = sum(float(t["valor"] or 0) for t in titulos if t["status"] == "pago")
    
    em_aberto = formatar_moeda(em_aberto_val)
    recebido = formatar_moeda(recebido_val)
    
    for t in titulos:
        t["valor"] = formatar_moeda(t.get("valor"))
        
    return render_template("admin/titulos.html", titulos=titulos, em_aberto=em_aberto, recebido=recebido)

@app.route("/admin/rastreio")
@login_required("admin")
def admin_rastreio():
    nfs = db.listar_todas_nfs()
    for n in nfs: n["eventos"] = db.listar_eventos_rastreio(n["id"])
    return render_template("admin/rastreio.html", nfs=nfs)

@app.route("/admin/rastreio/adicionar", methods=["POST"])
@login_required("admin")
def admin_rastreio_adicionar():
    nf_id = request.form.get("nf_id")
    data = request.form.get("data", datetime.now().strftime("%d/%m/%Y %H:%M"))
    status = request.form.get("status")
    observacao = request.form.get("observacao", "")
    
    try:
        try:
            db.inserir_evento_rastreio(int(nf_id), data, status, observacao)
        except AttributeError:
            db.adicionar_evento_rastreio(int(nf_id), data, status, observacao)
        flash("Evento de rastreio adicionado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro ao adicionar evento: {str(e)}", "erro")
        
    return redirect(url_for("admin_rastreio"))

@app.route("/admin/extrair-xml", methods=["POST"])
@login_required("admin")
def extrair_xml():
    f = request.files.get("xml")
    if not f: return jsonify({"sucesso": False})
    
    dados = extrair_dados_xml(f.read())
    
    # Se a extração for um sucesso, aplica a formatação de dinheiro
    if isinstance(dados, dict) and dados.get("sucesso"):
        if "valor" in dados:
            dados["valor"] = formatar_moeda(dados["valor"])
            
        # Pega tanto a chave duplicatas quanto boletos, dependendo de como o extrator retorna
        lista_parcelas = dados.get("duplicatas", []) or dados.get("boletos", [])
        for p in lista_parcelas:
            if "valor" in p:
                p["valor"] = formatar_moeda(p["valor"])
                
    return jsonify(dados)

# ─── PORTA SECRETA (WEBHOOK PARA O MAKE.COM) ─────────────────────────────────
@app.route("/api/webhook/receber-nota", methods=["POST"])
def webhook_receber_nota():
    # 1. Verifica a senha de segurança (para evitar envios falsos)
    senha_enviada = request.form.get("token") or request.headers.get("Authorization")
    senha_correta = os.environ.get("WEBHOOK_SECRET", "lima-notas-2026") # Senha padrão caso não tenha no painel
    
    if senha_enviada != senha_correta:
        return jsonify({"erro": "Acesso negado. Senha incorreta."}), 403

    # 2. Recebe os ficheiros enviados pelo Make.com
    arquivo_pdf = request.files.get("pdf")
    arquivo_xml = request.files.get("xml")

    if not arquivo_pdf or not arquivo_xml:
        return jsonify({"erro": "É obrigatório enviar o PDF e o XML."}), 400

    # 3. Extrai toda a inteligência do XML
    conteudo_xml = arquivo_xml.read()
    dados_xml = extrair_dados_xml(conteudo_xml)
    
    if not isinstance(dados_xml, dict) or not dados_xml.get("sucesso"):
        return jsonify({"erro": "Falha ao ler os dados do XML."}), 400

    # 4. Procura de quem é a nota fiscal (pelo CNPJ)
    cnpj_cliente = dados_xml.get("cnpj")
    if not cnpj_cliente:
        return jsonify({"erro": "CNPJ não encontrado no XML."}), 400

    # Limpa a formatação do CNPJ para procurar no banco de dados
    cnpj_limpo = re.sub(r'\D', '', cnpj_cliente)
    clientes = db.listar_clientes()
    cliente_destino = next((c for c in clientes if re.sub(r'\D', '', c.get("cnpj", "")) == cnpj_limpo), None)

    if not cliente_destino:
        return jsonify({"erro": f"Nenhum cliente cadastrado com o CNPJ {cnpj_cliente}"}), 404

    # 5. Salva a Nota Fiscal no Banco de Dados
    arquivo_pdf.seek(0)
    pdf_b64 = base64.b64encode(arquivo_pdf.read()).decode()
    
    nf_id = db.inserir_nf(
        cliente_id=cliente_destino["id"],
        numero_nf=dados_xml.get("numero_nf"),
        valor=limpar_moeda(dados_xml.get("valor")), 
        data_emissao=dados_xml.get("data_emissao"),
        pdf_base64=pdf_b64,
        nome_arquivo=arquivo_pdf.filename or f"NF_{dados_xml.get('numero_nf')}.pdf",
        codigo_rastreio="",
        transportadora=dados_xml.get("transportadora"),
        status="ativo",
        observacao="📥 Recebido via Automação de E-mail (Make)",
        representada=dados_xml.get("representada")
    )

    # 6. Salva os Boletos (apenas com os dados de cobrança, sem PDF anexado)
    boletos_salvos = 0
    lista_parcelas = dados_xml.get("duplicatas", []) or dados_xml.get("boletos", [])
    
    for dup in lista_parcelas:
        db.inserir_titulo(
            cliente_id=cliente_destino["id"],
            numero_titulo=dup.get("numero"),
            valor=limpar_moeda(dup.get("valor")),
            vencimento=dup.get("vencimento"),
            boleto_base64="", # Fica em branco intencionalmente
            nome_arquivo="",
            nf_id=nf_id
        )
        boletos_salvos += 1

    return jsonify({
        "sucesso": True, 
        "mensagem": f"NF {dados_xml.get('numero_nf')} e {boletos_salvos} parcelas cadastradas automaticamente para o cliente {cliente_destino['nome']}!"
    }), 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)
