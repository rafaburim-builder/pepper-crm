"""
api/sefaz.py — Cliente SEFAZ NFeDistribuicaoDFe
Consulta NF-e / CT-e via Certificado Digital A1 (.pfx)

Endpoint nacional:
  https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx

Autenticação: TLS mútuo com certificado ICP-Brasil (sem assinatura XML).
"""

from __future__ import annotations

import base64
import gzip
import io
import os
import re
import tempfile
import textwrap
import warnings
from typing import Optional
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as _xml_escape

import requests

# ── Namespaces SEFAZ ─────────────────────────────────────────────────────────
_NS_DIST   = "http://www.portalfiscal.inf.br/nfe"
_NS_DIST_W = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe"

# Timeout em segundos para chamadas ao SEFAZ
_TIMEOUT = 60


class SefazError(Exception):
    """Exceção para erros do cliente SEFAZ."""
    pass


class SefazClient:
    """
    Cliente para o serviço NFeDistribuicaoDFe da SEFAZ Nacional.

    Parâmetros
    ----------
    pfx_bytes   : bytes do arquivo .pfx (Certificado Digital A1)
    pfx_password: senha do certificado (str)
    cnpj        : CNPJ do contribuinte (somente dígitos, 14 chars)
    uf          : Código UF (ex: "35" para SP, "33" para RJ)
    ambiente    : 1=Produção, 2=Homologação (default: 1)
    """

    ENDPOINT_PROD = (
        "https://www1.nfe.fazenda.gov.br"
        "/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
    )
    ENDPOINT_HOM = (
        "https://hom1.nfe.fazenda.gov.br"
        "/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
    )

    def __init__(
        self,
        pfx_bytes: bytes,
        pfx_password: str,
        cnpj: str,
        uf: str,
        ambiente: int = 1,
    ):
        self.cnpj     = re.sub(r"\D", "", cnpj)
        self.uf       = str(uf).strip()
        self.ambiente = int(ambiente)
        self._pfx_bytes    = pfx_bytes
        self._pfx_password = pfx_password
        self._endpoint = self.ENDPOINT_PROD if ambiente == 1 else self.ENDPOINT_HOM

        # Extrai PEM uma vez só
        self._cert_pem, self._key_pem = self._pfx_to_pem(pfx_bytes, pfx_password)

    # ── Conversão PFX → PEM ──────────────────────────────────────────────────
    @staticmethod
    def _pfx_to_pem(pfx_bytes: bytes, password: str) -> tuple[bytes, bytes]:
        """Extrai certificado e chave privada do .pfx em formato PEM."""
        try:
            from cryptography.hazmat.primitives.serialization import (
                Encoding, PrivateFormat, NoEncryption, pkcs12,
            )
            from cryptography.hazmat.backends import default_backend
        except ImportError:
            raise SefazError(
                "Biblioteca 'cryptography' não instalada. "
                "Execute: pip install cryptography"
            )

        # Tenta múltiplos encodings — certificados brasileiros às vezes usam Latin-1.
        # IMPORTANTE: UTF-16LE é propositalmente excluído — gera bytes nulos que
        # causam pyo3_runtime.PanicException no backend Rust/OpenSSL (NulError),
        # que herda de BaseException e não é capturável por "except Exception".
        # Ordem: UTF-8 → Latin-1 → sem senha (último recurso)
        _candidates: list = []
        if isinstance(password, (str, bytes)):
            pw_str = password if isinstance(password, str) else password.decode("utf-8", errors="replace")
            if pw_str:
                _candidates.append(pw_str.encode("utf-8"))
                try:
                    _candidates.append(pw_str.encode("latin-1"))
                except (UnicodeEncodeError, Exception):
                    pass
            _candidates.append(None)   # sem senha (último recurso)
        else:
            _candidates = [None]

        key = cert = chain = None
        _last_exc: BaseException | None = None
        for _pw_attempt in _candidates:
            try:
                key, cert, chain = pkcs12.load_key_and_certificates(
                    pfx_bytes, _pw_attempt, default_backend()
                )
                if cert is not None:
                    break  # sucesso
            except BaseException as exc:
                # BaseException captura tanto Exception quanto pyo3 PanicException
                _last_exc = exc
                continue

        if cert is None:
            _detalhe = str(_last_exc) if _last_exc else "motivo desconhecido"
            # Dica específica: MAC fail = senha errada; outros = arquivo inválido
            if "password" in _detalhe.lower() or "mac" in _detalhe.lower() or "pkcs12" in _detalhe.lower():
                raise SefazError(
                    "Senha do certificado incorreta. "
                    "Verifique a senha exata do arquivo .pfx e tente novamente. "
                    f"(detalhe: {_detalhe})"
                )
            raise SefazError(
                f"Não foi possível abrir o certificado .pfx. "
                f"Detalhe: {_detalhe}"
            )
        if key is None:
            raise SefazError("Chave privada não encontrada no arquivo .pfx.")

        cert_pem = cert.public_bytes(Encoding.PEM)
        key_pem  = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        return cert_pem, key_pem

    # ── Arquivos temporários de certificado ──────────────────────────────────
    def _temp_cert_files(self) -> tuple[str, str]:
        """
        Salva cert/chave PEM em arquivos temporários.
        Retorna (cert_path, key_path) — o chamador é responsável por apagar.
        """
        cert_fd, cert_path = tempfile.mkstemp(suffix=".crt")
        key_fd,  key_path  = tempfile.mkstemp(suffix=".key")
        try:
            os.write(cert_fd, self._cert_pem)
            os.write(key_fd,  self._key_pem)
        finally:
            os.close(cert_fd)
            os.close(key_fd)
        return cert_path, key_path

    # ── Chamada SOAP ─────────────────────────────────────────────────────────
    def _post_soap(self, xml_body: str, versao_dados: str = "1.01") -> str:
        """
        Faz a requisição SOAP 1.2 ao SEFAZ com autenticação mútua TLS.
        Inclui o <soap12:Header> com <nfeCabecMsg> exigido pelo WSDL.
        Retorna o conteúdo da resposta como string.
        """
        # O NFeDistribuicaoDFe exige o Header nfeCabecMsg (cUF + versaoDados)
        # ATENÇÃO: NÃO usar textwrap.dedent com {xml_body} multi-linha —
        # o xml_body tem linhas em coluna 0, o que faz dedent remover 0 espaços
        # e resulta em "    <?xml..." (4 espaços antes da declaração XML),
        # que é XML inválido e causa HTTP 400 no SEFAZ.
        envelope = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<soap12:Envelope\n'
            '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
            '  xmlns:xsd="http://www.w3.org/2001/XMLSchema"\n'
            '  xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">\n'
            '  <soap12:Header>\n'
            '    <nfeCabecMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">\n'
            f'      <cUF>{self.uf}</cUF>\n'
            f'      <versaoDados>{versao_dados}</versaoDados>\n'
            '    </nfeCabecMsg>\n'
            '  </soap12:Header>\n'
            '  <soap12:Body>\n'
            f'{xml_body}\n'
            '  </soap12:Body>\n'
            '</soap12:Envelope>'
        )

        headers = {
            "Content-Type": 'application/soap+xml; charset=utf-8; action="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse"',
            "Accept":       "text/xml, application/soap+xml",
        }

        # Silencia warnings de certificado ICP-Brasil
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

        cert_path, key_path = self._temp_cert_files()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                # Usa Session para keep-alive e reuso de conexão TCP
                with requests.Session() as _sess:
                    _sess.verify  = False
                    _sess.cert    = (cert_path, key_path)
                    _sess.headers.update(headers)
                    resp = _sess.post(
                        self._endpoint,
                        data=envelope.encode("utf-8"),
                        timeout=_TIMEOUT,
                    )
        except requests.exceptions.SSLError as e:
            raise SefazError(f"Erro SSL ao conectar ao SEFAZ: {e}") from e
        except requests.exceptions.ConnectionError as e:
            raise SefazError(f"Erro de conexão com SEFAZ: {e}") from e
        except requests.exceptions.Timeout:
            raise SefazError("Timeout ao conectar ao SEFAZ (> 60s). Tente novamente.")
        finally:
            for p in (cert_path, key_path):
                try:
                    os.unlink(p)
                except Exception:
                    pass

        if resp.status_code != 200:
            raise SefazError(
                f"SEFAZ retornou HTTP {resp.status_code}: {resp.text[:500]}"
            )
        return resp.text

    # ── Builds XML ───────────────────────────────────────────────────────────
    def _build_dist_nsu(self, ultimo_nsu: str) -> str:
        """Monta o XML para distDFeInteresse por NSU."""
        # NSU sempre 15 dígitos (truncado por segurança se vier maior).
        nsu_clean = re.sub(r"\D", "", str(ultimo_nsu))[-15:].zfill(15)
        return (
            f'<nfeDistDFeInteresse xmlns="{_NS_DIST_W}">\n'
            f'  <nfeDadosMsg>\n'
            f'    <distDFeInteresse versao="1.01" xmlns="{_NS_DIST}">\n'
            f'      <tpAmb>{int(self.ambiente)}</tpAmb>\n'
            f'      <cUFAutor>{_xml_escape(str(self.uf))}</cUFAutor>\n'
            f'      <CNPJ>{_xml_escape(str(self.cnpj))}</CNPJ>\n'
            f'      <distNSU>\n'
            f'        <ultNSU>{nsu_clean}</ultNSU>\n'
            f'      </distNSU>\n'
            f'    </distDFeInteresse>\n'
            f'  </nfeDadosMsg>\n'
            f'</nfeDistDFeInteresse>'
        )

    def _build_cons_nfe(self, chave: str) -> str:
        """Monta o XML para consultar uma NF-e pela chave de acesso."""
        chave_clean = re.sub(r"\D", "", str(chave))
        return (
            f'<nfeDadosMsg xmlns="{_NS_DIST_W}">\n'
            f'  <distDFeInteresse versao="1.01" xmlns="{_NS_DIST}">\n'
            f'    <tpAmb>{int(self.ambiente)}</tpAmb>\n'
            f'    <cUFAutor>{_xml_escape(str(self.uf))}</cUFAutor>\n'
            f'    <CNPJ>{_xml_escape(str(self.cnpj))}</CNPJ>\n'
            f'    <consChNFe>\n'
            f'      <chNFe>{chave_clean}</chNFe>\n'
            f'    </consChNFe>\n'
            f'  </distDFeInteresse>\n'
            f'</nfeDadosMsg>'
        )

    # ── Decodifica docZip ─────────────────────────────────────────────────────
    @staticmethod
    def _decode_doczip(b64gz: str) -> str:
        """Decodifica um docZip (base64 + gzip) em XML string."""
        try:
            raw_gz  = base64.b64decode(b64gz)
            raw_xml = gzip.decompress(raw_gz)
            return raw_xml.decode("utf-8")
        except Exception as exc:
            raise SefazError(f"Erro ao decodificar docZip: {exc}") from exc

    # ── Parse da resposta SEFAZ ───────────────────────────────────────────────
    def _parse_response(self, soap_text: str) -> dict:
        """
        Interpreta a resposta SOAP e devolve dict com:
          - cStat : código de status
          - xMotivo : descrição do status
          - maxNSU : maior NSU recebido
          - ultNSU : último NSU processado
          - docs   : lista de dicts com {nsu, schema, xml}
        """
        result = {
            "cStat":   "",
            "xMotivo": "",
            "maxNSU":  "0",
            "ultNSU":  "0",
            "docs":    [],
        }

        try:
            root = ET.fromstring(soap_text)
        except ET.ParseError as exc:
            raise SefazError(f"Resposta SOAP inválida: {exc}") from exc

        # Encontra retDistDFeInteresse (ou retDistDFeInt — forma abreviada usada pelo SEFAZ)
        def _find_tag(node, local_name: str):
            for child in node.iter():
                tag = child.tag
                if "}" in tag:
                    tag = tag.split("}", 1)[1]
                if tag == local_name:
                    return child
            return None

        # O SEFAZ retorna "retDistDFeInt" (forma abreviada) em vez de "retDistDFeInteresse"
        ret = _find_tag(root, "retDistDFeInteresse") or _find_tag(root, "retDistDFeInt")
        if ret is None:
            # Verifica se há fault SOAP
            fault = _find_tag(root, "Fault")
            if fault:
                reason = _find_tag(fault, "Text") or _find_tag(fault, "faultstring")
                msg = reason.text if reason is not None else "Fault SOAP desconhecido"
                raise SefazError(f"Fault SOAP do SEFAZ: {msg}")
            raise SefazError("Resposta SEFAZ não contém 'retDistDFeInteresse'.")

        def _txt(tag: str) -> str:
            el = _find_tag(ret, tag)
            return el.text.strip() if el is not None and el.text else ""

        result["cStat"]   = _txt("cStat")
        result["xMotivo"] = _txt("xMotivo")
        result["maxNSU"]  = _txt("maxNSU") or "0"
        result["ultNSU"]  = _txt("ultNSU") or "0"

        # Códigos conhecidos — não levanta exceção aqui; deixa o chamador decidir.
        # 137 = documento(s) localizado(s)
        # 138 = nenhum documento localizado (normal, não é erro)
        # Outros códigos (rejeições, etc.) são repassados via cStat/xMotivo
        # Só levanta SefazError para erros de autenticação/sistema (5xx como cStat)
        cstat = result["cStat"]
        _rejeicao_grave = cstat.startswith("5") if cstat else False
        if _rejeicao_grave:
            raise SefazError(
                f"SEFAZ recusou a requisição — cStat={cstat}: {result['xMotivo']}"
            )

        # Extrai lotes de documentos
        for doc_zip in ret.iter():
            tag = doc_zip.tag
            if "}" in tag:
                tag = tag.split("}", 1)[1]
            if tag != "docZip":
                continue

            nsu    = doc_zip.get("NSU", "")
            schema = doc_zip.get("schema", "")
            b64gz  = doc_zip.text or ""
            if not b64gz.strip():
                continue

            try:
                xml_str = self._decode_doczip(b64gz.strip())
            except SefazError:
                xml_str = ""

            result["docs"].append({
                "nsu":    nsu,
                "schema": schema,
                "xml":    xml_str,
            })

        return result

    # ── Método público: distDFe por NSU ──────────────────────────────────────
    def dist_dfe(self, ultimo_nsu: str = "0") -> dict:
        """
        Consulta documentos fiscais a partir de um NSU.

        Retorna dict com chaves: cStat, xMotivo, maxNSU, ultNSU, docs.
        'docs' é lista de dicts {nsu, schema, xml}.
        """
        xml_body = self._build_dist_nsu(ultimo_nsu)
        soap_text = self._post_soap(xml_body)
        return self._parse_response(soap_text)

    # ── Método público: consulta por chave ───────────────────────────────────
    def cons_nfe(self, chave: str) -> dict:
        """
        Consulta uma NF-e específica pela chave de acesso (44 dígitos).

        Retorna dict com chaves: cStat, xMotivo, maxNSU, ultNSU, docs.
        """
        chave_clean = re.sub(r"\D", "", chave)
        if len(chave_clean) != 44:
            raise SefazError(f"Chave de acesso inválida: deve ter 44 dígitos (recebido {len(chave_clean)}).")
        xml_body  = self._build_cons_nfe(chave_clean)
        soap_text = self._post_soap(xml_body)
        return self._parse_response(soap_text)

    # ── Método público: busca incremental completa ────────────────────────────
    def buscar_notas(
        self,
        ultimo_nsu: str = "0",
        max_paginas: int = 10,
    ) -> tuple[list[dict], str]:
        """
        Realiza busca incremental por NSU, paginando até max_paginas vezes
        ou até não haver mais documentos.

        Retorna (lista_de_documentos_parseados, novo_ultimo_nsu).
        Cada documento parseado é um dict gerado por _parse_doc().
        """
        todos_docs: list[dict] = []
        nsu_atual = str(ultimo_nsu)

        for _ in range(max_paginas):
            resp = self.dist_dfe(nsu_atual)
            docs = resp.get("docs", [])
            max_nsu = resp.get("maxNSU", nsu_atual)

            for doc in docs:
                parsed = self._parse_doc(doc)
                if parsed:
                    todos_docs.append(parsed)

            # Se não veio nenhum doc ou NSU não avançou, para
            if not docs or max_nsu == nsu_atual:
                nsu_atual = max_nsu
                break

            nsu_atual = max_nsu

            # Se cStat=138, não há mais documentos
            if resp.get("cStat") == "138":
                break

        return todos_docs, nsu_atual

    # ── Parse de documento individual ────────────────────────────────────────
    def _parse_doc(self, doc: dict) -> Optional[dict]:
        """
        Transforma um doc {nsu, schema, xml} em um dict amigável.
        Suporta: procNFe (NF-e), resNFe (resumo), procCTe (CT-e), resCTe.
        Retorna None se não reconhecido.
        """
        schema = doc.get("schema", "")
        xml    = doc.get("xml", "")
        nsu    = doc.get("nsu", "")

        if not xml:
            return None

        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return None

        def _local(tag: str) -> str:
            return tag.split("}", 1)[1] if "}" in tag else tag

        def _t(node, tag_name: str) -> str:
            """Primeira ocorrência de uma tag local (qualquer profundidade)."""
            if node is None:
                return ""
            for child in node.iter():
                if _local(child.tag) == tag_name:
                    return child.text.strip() if child.text else ""
            return ""

        def _find(node, tag_name: str):
            """Primeiro elemento com tag local correspondente."""
            if node is None:
                return None
            for child in node.iter():
                if _local(child.tag) == tag_name:
                    return child
            return None

        result = {
            "nsu":          nsu,
            "schema":       schema,
            "tipo":         "NF-e",
            "chave":        "",
            "numero":       "",
            "serie":        "",
            "data_emissao": "",
            "emitente":     "",
            "cnpj_emit":    "",
            "destinatario": "",
            "cnpj_dest":    "",
            "valor":        0.0,
            "situacao":     "Autorizada",
            "xml_raw":      xml,
        }

        # ── procNFe / nfeProc (NF-e autorizada) ──────────────────────────────
        if "procNFe" in schema or "nfeProc" in schema:
            result["tipo"]         = "NF-e"
            result["chave"]        = _t(root, "chNFe") or _t(root, "Id")
            result["numero"]       = _t(root, "nNF")
            result["serie"]        = _t(root, "serie")
            result["data_emissao"] = _t(root, "dhEmi") or _t(root, "dEmi")
            # Busca dentro de <emit> e <dest> separadamente — evita pegar xNome do produto.
            _emit = _find(root, "emit")
            _dest = _find(root, "dest")
            result["emitente"]     = _t(_emit, "xNome")
            result["cnpj_emit"]    = _t(_emit, "CNPJ")
            result["destinatario"] = _t(_dest, "xNome")
            result["cnpj_dest"]    = _t(_dest, "CNPJ") or _t(_dest, "CPF")
            result["valor"]        = self._to_float(_t(root, "vNF"))
            result["situacao"]     = "Autorizada"

        # ── resNFe (resumo de NF-e) ───────────────────────────────────────────
        elif "resNFe" in schema:
            result["tipo"]         = "NF-e (Resumo)"
            result["chave"]        = _t(root, "chNFe")
            result["numero"]       = _t(root, "nNF")
            result["serie"]        = _t(root, "serie")
            result["data_emissao"] = _t(root, "dhEmi") or _t(root, "dEmi")
            result["emitente"]     = _t(root, "xNome")
            result["cnpj_emit"]    = _t(root, "CNPJ")
            result["valor"]        = self._to_float(_t(root, "vNF"))
            cst = _t(root, "cSitNFe") or _t(root, "CSitNFe")
            result["situacao"]     = self._sit_nfe(cst)

        # ── procCTe / cteProc (CT-e) ──────────────────────────────────────────
        elif "procCTe" in schema or "cteProc" in schema:
            result["tipo"]         = "CT-e"
            result["chave"]        = _t(root, "chCTe") or _t(root, "Id")
            result["numero"]       = _t(root, "nCT")
            result["serie"]        = _t(root, "serie")
            result["data_emissao"] = _t(root, "dhEmi") or _t(root, "dEmi")
            _emit = _find(root, "emit")
            _dest = _find(root, "dest")
            result["emitente"]     = _t(_emit, "xNome")
            result["cnpj_emit"]    = _t(_emit, "CNPJ")
            result["destinatario"] = _t(_dest, "xNome")
            result["cnpj_dest"]    = _t(_dest, "CNPJ") or _t(_dest, "CPF")
            result["valor"]        = self._to_float(_t(root, "vTPrest"))
            result["situacao"]     = "Autorizada"

        # ── resCTe (resumo CT-e) ──────────────────────────────────────────────
        elif "resCTe" in schema:
            result["tipo"]         = "CT-e (Resumo)"
            result["chave"]        = _t(root, "chCTe")
            result["numero"]       = _t(root, "nCT")
            result["serie"]        = _t(root, "serie")
            result["data_emissao"] = _t(root, "dhEmi") or _t(root, "dEmi")
            result["emitente"]     = _t(root, "xNome")
            result["cnpj_emit"]    = _t(root, "CNPJ")
            result["valor"]        = self._to_float(_t(root, "vTPrest"))
            cst = _t(root, "cSitCTe")
            result["situacao"]     = "Autorizada" if cst == "100" else f"Código {cst}"

        else:
            # Schema não reconhecido — devolve com dados genéricos
            result["tipo"]     = schema or "Desconhecido"
            result["situacao"] = "Desconhecido"

        # Formata chave (remove prefixo 'NFe' ou 'CTe')
        chave = result["chave"]
        if chave.startswith(("NFe", "CTe")):
            chave = chave[3:]
        result["chave"] = re.sub(r"\D", "", chave)

        return result

    @staticmethod
    def _to_float(s: str) -> float:
        try:
            return float(str(s).replace(",", ".")) if s else 0.0
        except ValueError:
            return 0.0

    @staticmethod
    def _sit_nfe(cod: str) -> str:
        _map = {
            "1":  "Autorizada",
            "2":  "Cancelada",
            "3":  "Denegada",
            "4":  "Inutilizada",
            "5":  "Autorizada",  # Uso confirmado
            "6":  "Autorizada",  # Ciência emissão
            "7":  "Autorizada",  # Confirmação operação
            "8":  "Autorizada",  # Operação não realizada
            "9":  "Desconhecida",
        }
        return _map.get(str(cod), f"Código {cod}" if cod else "Desconhecida")

    # ── Informações do certificado ────────────────────────────────────────────
    def cert_info(self) -> dict:
        """
        Retorna informações do certificado: subject, issuer, not_before, not_after.
        Reutiliza o PEM já extraído (que passou pela lógica de múltiplos encodings).
        """
        try:
            from cryptography.x509 import load_pem_x509_certificate
            from cryptography.hazmat.backends import default_backend

            cert = load_pem_x509_certificate(self._cert_pem, default_backend())

            subject = cert.subject.rfc4514_string()
            issuer  = cert.issuer.rfc4514_string()

            # not_valid_before_utc adicionado na cryptography 42 — fallback para versões antigas
            try:
                not_before = cert.not_valid_before_utc.strftime("%d/%m/%Y %H:%M")
                not_after  = cert.not_valid_after_utc.strftime("%d/%m/%Y %H:%M")
            except AttributeError:
                not_before = cert.not_valid_before.strftime("%d/%m/%Y %H:%M")  # type: ignore[attr-defined]
                not_after  = cert.not_valid_after.strftime("%d/%m/%Y %H:%M")   # type: ignore[attr-defined]

            return {
                "subject":    subject,
                "issuer":     issuer,
                "not_before": not_before,
                "not_after":  not_after,
                "serial":     str(cert.serial_number),
            }
        except Exception as exc:
            return {"error": str(exc)}
