"""
extrator_pdf.py — Processamento 100% nativo focado no XML (Sem IA / Sem Custos)
"""

import base64
import re
import xml.etree.ElementTree as ET

def pdf_para_base64(arquivo_bytes: bytes) -> str:
    return base64.b64encode(arquivo_bytes).decode("utf-8")

def extrair_dados_xml(xml_bytes: bytes) -> dict:
    """Extrai dados da NF-e e Parcelas diretamente do XML localmente."""
    try:
        # Blindagem de Encoding (Tenta UTF-8, cai para ISO-8859-1 se for antigo)
        try:
            xml_str = xml_bytes.decode("utf-8-sig").strip()
        except UnicodeDecodeError:
            xml_str = xml_bytes.decode("iso-8859-1").strip()
            
        if not xml_str:
            return {"sucesso": False, "erro": "Arquivo vazio ou corrompido."}
            
        # Limpeza de declaração XML e Namespaces para evitar bugs de leitura
        xml_str = re.sub(r'<\?xml.*?\?>', '', xml_str)
        xml_str = re.sub(r'\sxmlns="[^"]+"', '', xml_str)

        root = ET.fromstring(xml_str)

        def find(tag):
            el = root.find(f".//{tag}")
            return el.text.strip() if el is not None and el.text else ""

        numero_nf = find("nNF")
        serie     = find("serie")

        try:
            valor = float(find("vNF") or 0)
        except Exception:
            valor = 0.0

        # Formata Data de Emissão
        data_raw  = find("dhEmi") or find("dEmi")
        data_emissao = ""
        if data_raw:
            parte = data_raw[:10]
            try:
                y, m, d = parte.split("-")
                data_emissao = f"{d}/{m}/{y}"
            except Exception:
                data_emissao = parte

        nome_emitente  = find("emit/xNome") or find("xNome")
        cnpj_emitente  = find("emit/CNPJ")

        nome_dest  = find("dest/xNome")
        cnpj_dest  = find("dest/CNPJ")
        if not cnpj_dest:
            cnpj_dest = find("dest/CPF")

        # Formata CNPJ Destinatário
        if cnpj_dest and len(cnpj_dest) == 14:
            c = cnpj_dest
            cnpj_dest = f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"

        transportadora = find("transporta/xNome")

        # Extração Exata das Parcelas/Duplicatas
        duplicatas = []
        for dup in root.findall(f".//dup"):
            n_dup  = dup.find(f"nDup")
            d_venc = dup.find(f"dVenc")
            v_dup  = dup.find(f"vDup")
            if d_venc is not None and v_dup is not None:
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

        print(f"[extrator XML] NF {numero_nf} | R$ {valor} | {len(duplicatas)} parcela(s)")

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
