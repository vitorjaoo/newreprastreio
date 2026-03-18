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

        prompt = """Você é um extrator de dados de Notas Fiscais brasileiras (NF-e, NFS-e, CT-e).
Analise este PDF e extraia os dados abaixo em formato JSON puro, sem markdown, sem explicações:

{
  "numero_nf": "número da NF (ex: 000123)",
  "serie": "série da NF (ex: 001)",
  "valor_total": 0.00,
  "data_emissao": "DD/MM/AAAA",
  "cnpj_destinatario": "CNPJ do destinatário no formato 00.000.000/0001-00",
  "nome_destinatario": "razão social do destinatário",
  "cnpj_emitente": "CNPJ de quem emitiu a NF",
  "nome_emitente": "razão social de quem emitiu (representada/fornecedor)"
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
                "maxOutputTokens": 512
            }
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        dados = json.loads(raw)

        return {
            "numero_nf":    dados.get("numero_nf") or "",
            "valor":        float(dados.get("valor_total") or 0),
            "data_emissao": dados.get("data_emissao") or "",
            "cnpj":         dados.get("cnpj_destinatario") or "",
            "nome":         dados.get("nome_destinatario") or "",
            "representada": dados.get("nome_emitente") or "",
            "cnpj_emitente":dados.get("cnpj_emitente") or "",
            "sucesso":      True,
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
                "maxOutputTokens": 512
            }
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()
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
