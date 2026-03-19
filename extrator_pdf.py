"""
extrator_pdf.py — Extração de dados de PDF usando Gemini API (Google)
Gratuito: 1.500 requisições/dia sem cartão
"""

import base64
import json
import os
import re


def pdf_para_base64(arquivo_bytes: bytes) -> str:
    return base64.b64encode(arquivo_bytes).decode("utf-8")


def extrair_dados_nf(arquivo_bytes: bytes, nome_arquivo: str) -> dict:
    """
    Envia o PDF da NF para o Gemini e retorna os dados extraídos.
    Retorna dict com: numero_nf, valor, data_emissao, cnpj, nome, sucesso
    """
    api_key = os.getenv("GEMINI_API_KEY", "")

    if not api_key:
        return _campos_vazios_nf()

    try:
        import urllib.request
        import urllib.error

        pdf_b64 = base64.standard_b64encode(arquivo_bytes).decode("utf-8")

        prompt = """Você é um especialista em leitura de DANFE (Documento Auxiliar da Nota Fiscal Eletrônica) brasileira.

Analise este PDF de DANFE e extraia os seguintes dados em JSON puro, sem markdown, sem explicações:

{
  "numero_nf": "número que aparece após 'Nº' no canto superior direito (ex: 000161759)",
  "serie": "número de série que aparece após 'Série' (ex: 000)",
  "valor_total": valor numérico do campo 'V. TOTAL DA NOTA' (ex: 1512.85),
  "data_emissao": "data do campo 'DATA DA EMISSÃO' no formato DD/MM/AAAA",
  "cnpj_destinatario": "CNPJ do bloco DESTINATÁRIO/REMETENTE no formato 00.000.000/0001-00",
  "nome_destinatario": "NOME/RAZÃO SOCIAL do bloco DESTINATÁRIO/REMETENTE",
  "cnpj_emitente": "CNPJ/CPF do emitente (bloco superior esquerdo com nome da empresa emitente)",
  "nome_emitente": "nome da empresa emitente (bloco superior esquerdo, ex: S A S PLASTIC MATRIZ)",
  "transportadora": "NOME/RAZÃO SOCIAL da transportadora no bloco TRANSPORTADOR/VOLUMES TRANSPORTADOS"
}

Observações importantes:
- O número da NF fica no canto superior direito após 'Nº'
- O CNPJ do emitente fica no campo 'CNPJ/CPF' do lado direito do cabeçalho
- O valor total da nota fica na linha 'V. TOTAL DA NOTA' destacado
- Se algum campo não for encontrado, use null

Responda APENAS com o JSON, sem nenhum texto adicional."""

        payload = {
            "contents": [{
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "application/pdf",
                            "data": pdf_b64
                        }
                    },
                    {"text": prompt}
                ]
            }],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 1024,
                "responseMimeType": "application/json"
            }
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        req_data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        print(f"[extrator] Gemini resultado completo: {json.dumps(result)[:800]}")
        raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        print(f"[extrator] Gemini texto: {raw[:500]}")
        raw = re.sub(r"```json|```", "", raw).strip()
        dados = json.loads(raw)

        return {
            "numero_nf":     dados.get("numero_nf") or "",
            "valor":         float(dados.get("valor_total") or 0),
            "data_emissao":  dados.get("data_emissao") or "",
            "cnpj":          dados.get("cnpj_destinatario") or "",
            "nome":          dados.get("nome_destinatario") or "",
            "representada":  dados.get("nome_emitente") or "",
            "cnpj_emitente": dados.get("cnpj_emitente") or "",
            "transportadora":dados.get("transportadora") or "",
            "sucesso":       True,
        }

    except Exception as e:
        print(f"[extrator] Erro Gemini: {e}")
        return _campos_vazios_nf()


def extrair_dados_boleto(arquivo_bytes: bytes, nome_arquivo: str) -> dict:
    """
    Envia o PDF do boleto para o Gemini e retorna os dados extraídos.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")

    if not api_key:
        return _campos_vazios_boleto()

    try:
        import urllib.request

        pdf_b64 = base64.standard_b64encode(arquivo_bytes).decode("utf-8")

        prompt = """Você é um extrator de dados de boletos bancários brasileiros.
Analise este PDF e extraia os dados abaixo em formato JSON puro, sem markdown, sem explicações:

{
  "numero_titulo": "número do documento ou nosso número",
  "valor": 0.00,
  "vencimento": "DD/MM/AAAA",
  "cnpj_pagador": "CNPJ ou CPF do pagador",
  "nome_pagador": "nome do pagador",
  "linha_digitavel": "linha digitável do boleto"
}

Se algum campo não for encontrado, use null.
Responda APENAS com o JSON, sem nenhum texto adicional."""

        payload = {
            "contents": [{
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "application/pdf",
                            "data": pdf_b64
                        }
                    },
                    {"text": prompt}
                ]
            }],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 1024,
                "responseMimeType": "application/json"
            }
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        req_data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        print(f"[extrator] Gemini resultado completo: {json.dumps(result)[:800]}")
        raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        print(f"[extrator] Gemini texto: {raw[:500]}")
        raw = re.sub(r"```json|```", "", raw).strip()
        dados = json.loads(raw)

        return {
            "numero_titulo": dados.get("numero_titulo") or "",
            "valor":         float(dados.get("valor") or 0),
            "vencimento":    dados.get("vencimento") or "",
            "cnpj":          dados.get("cnpj_pagador") or "",
            "nome":          dados.get("nome_pagador") or "",
            "sucesso":       True,
        }

    except Exception as e:
        print(f"[extrator] Erro Gemini boleto: {e}")
        return _campos_vazios_boleto()


def _campos_vazios_nf() -> dict:
    return {
        "numero_nf": "", "valor": 0.0, "data_emissao": "",
        "cnpj": "", "nome": "", "representada": "",
        "cnpj_emitente": "", "sucesso": True,
    }


def _campos_vazios_boleto() -> dict:
    return {
        "numero_titulo": "", "valor": 0.0,
        "vencimento": "", "cnpj": "", "nome": "", "sucesso": True,
    }


def extrair_dados_xml(xml_bytes: bytes) -> dict:
    """
    Extrai dados da NF-e diretamente do XML.
    Preciso, instantâneo e sem custo de API.
    """
    try:
        import xml.etree.ElementTree as ET

        # Remove BOM se existir
        xml_str = xml_bytes.decode("utf-8-sig").strip()
        root = ET.fromstring(xml_str)

        # Namespace padrão NF-e
        ns = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

        def find(tag):
            el = root.find(f".//{{{ns['nfe']}}}{tag}")
            if el is None:
                el = root.find(f".//{tag}")
            return el.text.strip() if el is not None and el.text else ""

        # Número e série
        numero_nf = find("nNF")
        serie     = find("serie")

        # Valor total
        try:
            valor = float(find("vNF") or 0)
        except Exception:
            valor = 0.0

        # Data de emissão — converte AAAA-MM-DD para DD/MM/AAAA
        data_raw  = find("dhEmi") or find("dEmi")
        data_emissao = ""
        if data_raw:
            parte = data_raw[:10]  # pega só AAAA-MM-DD
            try:
                y, m, d = parte.split("-")
                data_emissao = f"{d}/{m}/{y}"
            except Exception:
                data_emissao = parte

        # Emitente (representada)
        nome_emitente  = find("emit/xNome") or find("xNome")
        cnpj_emitente  = find("emit/CNPJ")

        # Destinatário
        nome_dest  = find("dest/xNome")
        cnpj_dest  = find("dest/CNPJ")
        if not cnpj_dest:
            cnpj_dest = find("dest/CPF")

        # Formata CNPJ destinatário
        if cnpj_dest and len(cnpj_dest) == 14:
            c = cnpj_dest
            cnpj_dest = f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"

        # Transportadora
        transportadora = find("transporta/xNome")

        # Extrai duplicatas (parcelas/títulos)
        duplicatas = []
        for dup in root.findall(f".//{{{ns['nfe']}}}dup"):
            n_dup  = dup.find(f"{{{ns['nfe']}}}nDup")
            d_venc = dup.find(f"{{{ns['nfe']}}}dVenc")
            v_dup  = dup.find(f"{{{ns['nfe']}}}vDup")
            if d_venc is not None and v_dup is not None:
                # Converte data AAAA-MM-DD para DD/MM/AAAA
                try:
                    y, m, d = d_venc.text[:10].split("-")
                    venc_fmt = f"{d}/{m}/{y}"
                except Exception:
                    venc_fmt = d_venc.text
                duplicatas.append({
                    "numero": n_dup.text if n_dup is not None else "",
                    "vencimento": venc_fmt,
                    "valor": float(v_dup.text or 0),
                })

        print(f"[extrator XML] NF {numero_nf} | {nome_emitente} → {nome_dest} | R$ {valor} | {len(duplicatas)} parcela(s)")

        return {
            "numero_nf":     numero_nf,
            "serie":         serie,
            "valor":         valor,
            "data_emissao":  data_emissao,
            "cnpj":          cnpj_dest,
            "nome":          nome_dest,
            "representada":  nome_emitente,
            "cnpj_emitente": cnpj_emitente,
            "transportadora":transportadora,
            "duplicatas":    duplicatas,
            "sucesso":       True,
            "fonte":         "xml",
        }

    except Exception as e:
        print(f"[extrator XML] Erro: {e}")
        return {"sucesso": False, "erro": str(e)}
