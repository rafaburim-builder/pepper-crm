"""
Linx Microvix WebService client (POST/XML format) + mock data generator.
API endpoint: https://webapi.microvix.com.br/1.0/api/integracao
"""
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape as _xml_escape

import numpy as np
import pandas as pd
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# HTTPS: criptografa o token em trânsito (evita sniffing passivo na rede).
# 29/05/2026 (builder): migrado de http:// para https:// (testado: conecta OK).
_BASE_URL = "https://webapi.microvix.com.br/1.0/api/integracao"


# ── Brazilian decimal string to float ─────────────────────────────────────────
def _br_float(s) -> float:
    try:
        return float(str(s).replace(".", "").replace(",", "."))
    except Exception:
        return 0.0


# ── Fix malformed JSON from Microvix (unescaped backslashes) ──────────────────
_VALID_ESC = set('"\\bfnrtu/')

def _fix_json(text: str) -> str:
    buf = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            buf.append(text[i] if text[i + 1] in _VALID_ESC else "\\\\")
        else:
            buf.append(text[i])
        i += 1
    return "".join(buf)


# ── Mock product catalogue ─────────────────────────────────────────────────────
# LV = Armações de Grau  |  OC = Óculos Solar  |  ML = Armações Multi
# LE = Lentes            |  LC = Lentes de Contato  |  AC = Acessórios
_PRODUCTS = [
    # LV – Armações de Grau
    {"ref": "LV.IJ.001.3333", "desc": "Armação Injetada Preta",        "cat": "LV", "price": 149.90, "w": 9},
    {"ref": "LV.IJ.002.3333", "desc": "Armação Injetada Tartaruga",    "cat": "LV", "price": 189.90, "w": 8},
    {"ref": "LV.MT.001.3333", "desc": "Armação Metal Dourada",         "cat": "LV", "price": 229.90, "w": 7},
    {"ref": "LV.MT.002.3333", "desc": "Armação Metal Prata",           "cat": "LV", "price": 259.90, "w": 6},
    {"ref": "LV.AL.001.3333", "desc": "Armação Acetato Redonda",       "cat": "LV", "price": 299.90, "w": 5},
    {"ref": "LV.AL.002.3333", "desc": "Armação Acetato Hexagonal",     "cat": "LV", "price": 349.90, "w": 4},
    {"ref": "LV.AC.001.3333", "desc": "Armação Acetato Premium",       "cat": "LV", "price": 399.90, "w": 3},
    # OC – Óculos Solar
    {"ref": "OC.AL.001.3333", "desc": "Óculos Solar Acetato Preto",    "cat": "OC", "price": 249.90, "w": 8},
    {"ref": "OC.AL.002.3333", "desc": "Óculos Solar Gatinho",          "cat": "OC", "price": 289.90, "w": 7},
    {"ref": "OC.CL.001.3333", "desc": "Óculos Solar Clássico",        "cat": "OC", "price": 329.90, "w": 6},
    {"ref": "OC.MT.001.3333", "desc": "Óculos Solar Metal Dourado",    "cat": "OC", "price": 369.90, "w": 5},
    {"ref": "OC.MT.002.3333", "desc": "Óculos Solar Oversized",        "cat": "OC", "price": 429.90, "w": 4},
    # ML – Armações Multi (multilentes / progressivas)
    {"ref": "ML.001.3333",    "desc": "Armação Multilente Básica",     "cat": "ML", "price": 299.90, "w": 5},
    {"ref": "ML.002.3333",    "desc": "Armação Multilente Digital",    "cat": "ML", "price": 459.90, "w": 3},
    {"ref": "LV.MU.001.3333", "desc": "Armação Multi Premium",        "cat": "ML", "price": 649.90, "w": 2},
    # LE – Lentes (visão / varilux)
    {"ref": "LE.VI.001.3333", "desc": "Lente Visão Simples",          "cat": "LE", "price": 189.90, "w": 6},
    {"ref": "LE.VI.002.3333", "desc": "Lente Anti-Reflexo",           "cat": "LE", "price": 279.90, "w": 5},
    {"ref": "LE.VA.001.3333", "desc": "Lente Varilux Progressiva",    "cat": "LE", "price": 449.90, "w": 3},
    {"ref": "LE.VA.002.3333", "desc": "Lente Varilux Premium",        "cat": "LE", "price": 649.90, "w": 2},
    # LC – Lentes de Contato
    {"ref": "LE.CO.001.3333", "desc": "Lente de Contato Mensal",      "cat": "LC", "price":  79.90, "w": 7},
    {"ref": "LE.CO.002.3333", "desc": "Lente de Contato Descartável", "cat": "LC", "price":  49.90, "w": 6},
    {"ref": "LE.CT.001.3333", "desc": "Lente de Contato Colorida",    "cat": "LC", "price":  99.90, "w": 4},
    # AC – Acessórios e Brindes
    {"ref": "AC.001.3333",    "desc": "Estojo Chilli Beans",          "cat": "AC", "price":  39.90, "w": 8},
    {"ref": "AC.002.3333",    "desc": "Cordão Ajustável",             "cat": "AC", "price":  29.90, "w": 7},
    {"ref": "AC.003.3333",    "desc": "Flanela Microfibra",           "cat": "AC", "price":  19.90, "w": 6},
]


def _parse_dates(dt_ini: str, dt_fim: str):
    start = datetime.strptime(dt_ini, "%Y-%m-%d")
    end   = datetime.strptime(dt_fim, "%Y-%m-%d")
    return start, end, (end - start).days + 1


def mock_vendas(dt_ini: str, dt_fim: str, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start, end, _ = _parse_dates(dt_ini, dt_fim)
    weights = np.array([p["w"] for p in _PRODUCTS], dtype=float)
    weights /= weights.sum()

    rows = []
    cur = start
    while cur <= end:
        base = 12
        base += 5 if cur.weekday() >= 5 else 0
        base += 4 if cur.month in (11, 12, 7) else 0
        n = int(rng.poisson(base))
        for _ in range(n):
            p     = _PRODUCTS[rng.choice(len(_PRODUCTS), p=weights)]
            price = round(float(p["price"]) * rng.uniform(0.97, 1.03), 2)
            qty   = int(rng.choice([1, 2], p=[0.93, 0.07]))
            _vendedores = ["1", "2", "3", "4", "5"]
            rows.append({
                "data":           cur,
                "referencia":     p["ref"],
                "descricao":      p["desc"],
                "categoria":      p["cat"],
                "quantidade":     qty,
                "preco_original": float(p["price"]),   # preço de tabela (sem desconto)
                "vlr_unitario":   price,               # preço efetivo de venda
                "vlr_total":      round(price * qty, 2),
                "cod_vendedor":   _vendedores[rng.integers(0, len(_vendedores))],
                "num_documento":  str(len(rows) + 10001),
            })
        cur += timedelta(days=1)

    return pd.DataFrame(rows)


def mock_estoque(seed: int = 77) -> pd.DataFrame:
    """Mock current stock — one row per SKU with realistic low/medium levels."""
    rng = np.random.default_rng(seed)
    choices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15]
    probs   = [0.05, 0.09, 0.12, 0.14, 0.13, 0.11, 0.09, 0.08, 0.07, 0.06, 0.04, 0.02]
    rows = []
    for p in _PRODUCTS:
        qty = int(rng.choice(choices, p=probs))
        rows.append({
            "referencia": p["ref"],
            "descricao":  p["desc"],
            "categoria":  p["cat"],
            "quantidade": qty,
        })
    return pd.DataFrame(rows)


def mock_inventario(seed: int = 88) -> pd.DataFrame:
    """Mock inventário físico — fallback demo para LinxInventarios."""
    return mock_estoque(seed=seed)


def mock_compras(dt_ini: str, dt_fim: str, seed: int = 99) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start, end, days = _parse_dates(dt_ini, dt_fim)
    weights = np.array([p["w"] for p in _PRODUCTS], dtype=float)
    weights /= weights.sum()
    fornecedores = ["Chilli Beans SP", "Óticas Distribuição", "CB Centro de Distribuição"]
    statuses     = ["Entregue", "Entregue", "Confirmado", "Pendente"]

    rows = []
    n_orders = max(1, days // 7)
    for _ in range(n_orders):
        order_date = start + timedelta(days=int(rng.integers(0, max(1, days))))
        fornecedor = fornecedores[rng.integers(0, len(fornecedores))]
        status     = statuses[rng.integers(0, len(statuses))]
        for _ in range(int(rng.integers(3, 8))):
            p    = _PRODUCTS[rng.choice(len(_PRODUCTS), p=weights)]
            cost = round(float(p["price"]) * rng.uniform(0.45, 0.55), 2)
            qty  = int(rng.integers(2, 6))
            rows.append({
                "data":         order_date,
                "referencia":   p["ref"],
                "descricao":    p["desc"],
                "categoria":    p["cat"],
                "fornecedor":   fornecedor,
                "quantidade":   qty,
                "vlr_unitario": cost,
                "vlr_total":    round(cost * qty, 2),
                "status":       status,
            })

    return pd.DataFrame(rows).sort_values("data").reset_index(drop=True)


# ── Microvix API client ───────────────────────────────────────────────────────

class MicrovixAPIError(Exception):
    pass


class MicrovixAPI:
    def __init__(self, token: str, cnpj: str, nome_empresa: str, base_url: str = None):
        self.token        = token.strip()
        self.cnpj         = "".join(filter(str.isdigit, cnpj))
        self.nome_empresa = nome_empresa.strip()
        self.base_url     = (base_url or _BASE_URL).strip()
        self._s           = requests.Session()
        # verify=False: o endpoint do Microvix não valida contra a CA padrão
        # (verify=True falha com SSLError). HTTPS ainda criptografa o tráfego.
        # TODO(builder P1): investigar/pinar o certificado do Microvix p/ ligar verify=True.
        self._s.verify    = False

    # ── internals ──────────────────────────────────────────────────────────────

    def _xml(self, command: str, params_inner: str) -> str:
        # Escape credenciais p/ evitar XML inválido caso contenham &, <, >, etc.
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            "<LinxMicrovix>"
            '<Authentication user="linx_export" password="linx_export" />'
            "<ResponseFormat>json</ResponseFormat>"
            f"<Command><Name>{_xml_escape(command)}</Name>"
            "<Parameters>"
            f'<Parameter id="chave">{_xml_escape(self.token)}</Parameter>'
            f'<Parameter id="cnpjEmp">{_xml_escape(self.cnpj)}</Parameter>'
            f"{params_inner}"
            "</Parameters></Command>"
            "</LinxMicrovix>"
        )

    def _post(self, command: str, params_inner: str) -> List[dict]:
        body = self._xml(command, params_inner)
        try:
            r = self._s.post(
                self.base_url,
                data=body.encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8"},
                timeout=90,
            )
            r.raise_for_status()
        except requests.ConnectionError as e:
            raise MicrovixAPIError(
                f"Não foi possível conectar ao Microvix ({type(e).__name__}).\n"
                "Verifique sua conexão com a internet."
            )
        except requests.Timeout:
            raise MicrovixAPIError("A requisição ao Microvix demorou demais. Tente novamente.")
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            err_body = e.response.text[:200] if e.response is not None else ""
            if code == 401:
                raise MicrovixAPIError("Token ou credenciais inválidos (erro 401).")
            raise MicrovixAPIError(f"Erro HTTP {code} ao acessar o Microvix. Detalhe: {err_body}")
        except MicrovixAPIError:
            raise
        except Exception as e:
            raise MicrovixAPIError(f"Erro inesperado ao conectar: {type(e).__name__}: {e}")

        text = r.text.lstrip("﻿").lstrip()  # strip UTF-8 BOM + leading whitespace

        # XML error response (Microvix devolve XML quando há erro de parâmetro/permissão)
        if "<ResponseSuccess>False</ResponseSuccess>" in text:
            msg = re.search(r"<Message>([^<]+)</Message>", text)
            raise MicrovixAPIError(
                f"Microvix: {msg.group(1) if msg else 'Erro desconhecido'}"
            )

        # Microvix retorna JSON truncado p/ resultado vazio: '{ "ResponseData" : [ \n'
        # sem o fechamento ]}  — tratar como lista vazia
        _stripped = text.strip()
        if _stripped.startswith('{ "ResponseData" : [') and not _stripped.endswith('}'):
            return []

        try:
            data = json.loads(_fix_json(text))
        except json.JSONDecodeError as e:
            raise MicrovixAPIError(f"Resposta inválida do Microvix: {e}")

        # Defensive: o Microvix normalmente devolve {"ResponseData": [...]}, mas em
        # alguns casos retorna o array direto. Em ambos os cenários, devolve lista.
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            rd = data.get("ResponseData")
            return rd if isinstance(rd, list) else []
        return []

    @staticmethod
    def _to_iso(d: str) -> str:
        try:
            datetime.strptime(d, "%Y-%m-%d")
        except (ValueError, TypeError):
            raise MicrovixAPIError(
                f"Data inválida: '{d}'. Use o formato AAAA-MM-DD."
            )
        return d

    # ── public ─────────────────────────────────────────────────────────────────

    def test_connection(self) -> bool:
        try:
            today = datetime.today().strftime("%Y-%m-%d")
            params = (
                f'<Parameter id="data_inicial">{today}</Parameter>'
                f'<Parameter id="data_fim">{today}</Parameter>'
            )
            self._post("LinxMovimento", params)
            return True
        except MicrovixAPIError:
            raise
        except Exception:
            return False

    def get_sales(
        self,
        dt_ini: str,
        dt_fim: str,
        product_map: Optional[Dict[str, dict]] = None,
    ) -> pd.DataFrame:
        """
        dt_ini / dt_fim: "yyyy-mm-dd"
        product_map: dict from modules.product_map.load_map()
          - If provided and non-empty: only records whose cod_produto is in the map
            (and maps to LV/OC/ML) are returned.
          - If empty/None: all records are returned with categoria="?".
        Returns DataFrame: data, referencia, descricao, categoria,
                           quantidade, vlr_unitario, vlr_total

        IMPORTANTE: o LinxMovimento traz TODAS as movimentações. Esta função
        retorna VENDAS LÍQUIDAS, validado contra o relatório oficial do Microvix
        "Produtos/Serviços Vendidos" (bate ao centavo):
          venda líquida = vendas fiscais (op="S", documento≠0) − devoluções (op="DS")
        Garantia/troca: a reposição é registrada SEM documento fiscal (documento=0)
        e já fica de fora pelo filtro; por isso NÃO se subtrai o retorno em garantia
        (evita a venda duplicada sem dupla contagem). Compras, transferências e
        demais movimentações não-fiscais são ignoradas.
        """
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxMovimento", params)

        _map     = product_map or {}
        has_map  = bool(_map)
        rows: list = []

        for rec in records:
            if rec.get("cancelado") == "S" or rec.get("excluido") == "S":
                continue
            # ── Classifica o movimento (fórmula validada com o Microvix) ──────
            #   • VENDA fiscal (op="S", natureza VENDA, documento≠0) → soma (+)
            #   • DEVOLUÇÃO DE VENDAS (op="DS")                       → subtrai (−)
            #   • garantia / compras / transferências / não-fiscais  → ignora
            # A reposição de troca em garantia é registrada SEM documento (=0),
            # então o filtro documento≠0 já a exclui — não se subtrai o retorno.
            # Isso também remove as linhas simbólicas a R$0,01 sem documento.
            op  = str(rec.get("operacao", "")).strip().upper()
            nat = str(rec.get("natureza_operacao", "")).upper()
            has_doc  = str(rec.get("documento", "") or "").strip() not in ("", "0")
            is_venda = (op == "S") and ("VENDA" in nat) and has_doc
            is_devol = (op == "DS")  # devolução de venda (cliente devolveu)
            if not (is_venda or is_devol):
                continue

            qty   = _br_float(rec.get("quantidade", 0))
            price = _br_float(rec.get("preco_unitario", 0))
            if price <= 0 or qty <= 0:
                continue
            # Valor real da linha (já com desconto aplicado); fallback p/ preço×qtd.
            # SEM arredondar por linha — o Microvix soma o valor cheio e arredonda
            # só no total. Arredondar aqui introduzia diferença de centavos.
            line_total = _br_float(rec.get("valor_total", 0))
            if line_total <= 0:
                line_total = price * qty

            # Devolução entra como NEGATIVO: venda líquida = vendas − devoluções
            sign = -1 if is_devol else 1

            cod = str(rec.get("cod_produto", "")).strip()

            entry = _map.get(cod) if has_map else None
            if entry:
                ref = entry["referencia"]
                cat = entry["categoria"]
                # Preço original de tabela armazenado no mapa (importado via CSV)
                preco_orig = entry.get("preco_original") or None
                desc = entry.get("descricao", "")
            else:
                # Produto não catalogado: NÃO descarta — mantém na venda como "?"
                # (categoria "Sem catálogo") para o total bater com o Microvix.
                ref = str(rec.get("cod_barra", "")).strip() or cod
                cat = "?"
                preco_orig = None
                desc = ""

            # Fallback: preço de tabela na época da venda (preco_tabela_epoca),
            # senão usa o preço de venda efetivo. O campo 'preco_cheio' NÃO existe
            # no LinxMovimento desta API — confirmado via diagnóstico ao vivo.
            if preco_orig is None:
                _tabela = _br_float(rec.get("preco_tabela_epoca", 0))
                preco_orig = _tabela if _tabela > 0 else price

            rows.append({
                "data":           pd.to_datetime(
                                      rec.get("data_documento", ""),
                                      format="%d/%m/%Y %H:%M:%S",
                                      errors="coerce",
                                  ),
                "referencia":     ref,
                "descricao":      desc,
                "categoria":      cat,
                "quantidade":     sign * qty,
                "preco_original": preco_orig,  # preço de tabela para classificação na faixa
                "vlr_unitario":   price,       # preço efetivo de venda
                "vlr_total":      sign * line_total,  # sem arredondar (fidelidade)
                "cod_vendedor":   str(rec.get("cod_vendedor", "") or "").strip(),
                "num_documento":  str(rec.get("documento", "") or "").strip(),
            })

        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["data", "referencia", "descricao", "categoria",
                     "quantidade", "vlr_unitario", "vlr_total"]
        )

    def get_purchases(
        self,
        dt_ini: str,
        dt_fim: str,
        product_map: Optional[Dict[str, dict]] = None,
    ) -> pd.DataFrame:
        """
        dt_ini / dt_fim: "yyyy-mm-dd"
        product_map: same semantics as get_sales().
        Returns DataFrame: data, referencia, descricao, categoria,
                           fornecedor, quantidade, vlr_unitario, vlr_total, status
        """
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxPedidosCompra", params)

        _map    = product_map or {}
        has_map = bool(_map)
        rows: list = []

        for rec in records:
            if rec.get("cancelado") == "S":
                continue
            qty   = _br_float(rec.get("quantidade", 0))
            price = _br_float(rec.get("valor_unitario", 0))
            if price <= 0 or qty <= 0:
                continue

            cod = str(rec.get("cod_produto", "")).strip()

            if has_map:
                entry = _map.get(cod)
                if not entry:
                    continue
                ref = entry["referencia"]
                cat = entry["categoria"]
                desc = entry.get("descricao", "")
            else:
                ref = cod
                cat = "?"
                desc = ""

            rows.append({
                "data":         pd.to_datetime(
                                    rec.get("data_pedido", ""),
                                    format="%d/%m/%Y %H:%M:%S",
                                    errors="coerce",
                                ),
                "referencia":   ref,
                "descricao":    desc,
                "categoria":    cat,
                "fornecedor":   str(rec.get("codigo_fornecedor", "")),
                "quantidade":   qty,
                "vlr_unitario": price,
                "vlr_total":    round(price * qty, 2),
                "status":       rec.get("status_pedido", ""),
            })

        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["data", "referencia", "descricao", "categoria",
                     "fornecedor", "quantidade", "vlr_unitario", "vlr_total", "status"]
        )

    def get_stock_from_movements(
        self,
        dt_ini: str,
        product_map: Optional[Dict[str, dict]] = None,
    ) -> Dict[str, int]:
        """
        Calcula entradas de estoque (compras recebidas) a partir do LinxMovimento.
        Retorna dict {categoria: quantidade_total_entrada}.
        """
        info = self.get_purchase_movements(dt_ini, product_map)
        return {cat: v["total"] for cat, v in info.items()}

    def get_purchase_movements(
        self,
        dt_ini: str,
        product_map: Optional[Dict[str, dict]] = None,
    ) -> Dict[str, dict]:
        """
        Retorna informações detalhadas das compras recebidas desde dt_ini.

        Para cada categoria (LV/OC/ML) retorna:
          {
            "total":           int,   # unidades totais recebidas
            "ultima_compra":   date,  # data da compra mais recente
            "primeira_compra": date,  # data da compra mais antiga no período
            "n_compras":       int,   # número de eventos de compra
          }

        Usa operacao='E' + natureza='COMPRA' do LinxMovimento — funciona mesmo quando
        LinxPedidosCompra e LinxSaldoEstoque não estão habilitados na conta.
        """
        from datetime import date as _date
        dt_fim = str(_date.today())
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxMovimento", params)

        _map  = product_map or {}
        info: Dict[str, dict] = {}

        for rec in records:
            if rec.get("cancelado") == "S" or rec.get("excluido") == "S":
                continue
            op  = str(rec.get("operacao", "")).strip().upper()
            nat = str(rec.get("natureza_operacao", "")).upper()
            if op != "E" or "COMPRA" not in nat:
                continue
            qty = _br_float(rec.get("quantidade", 0))
            if qty <= 0:
                continue
            cod   = str(rec.get("cod_produto", "")).strip()
            entry = _map.get(cod)
            if not entry:
                continue
            cat = entry.get("categoria", "?")
            if cat not in ("LV", "OC", "ML"):
                continue
            dt = pd.to_datetime(
                rec.get("data_documento", ""),
                format="%d/%m/%Y %H:%M:%S", errors="coerce",
            )
            if cat not in info:
                info[cat] = {"total": 0, "ultima_compra": None,
                             "primeira_compra": None, "n_compras": 0}
            info[cat]["total"]     += int(qty)
            info[cat]["n_compras"] += 1
            if not pd.isna(dt):
                dt_d = dt.date()
                if info[cat]["ultima_compra"] is None or dt_d > info[cat]["ultima_compra"]:
                    info[cat]["ultima_compra"] = dt_d
                if info[cat]["primeira_compra"] is None or dt_d < info[cat]["primeira_compra"]:
                    info[cat]["primeira_compra"] = dt_d

        return info

    def get_stock(
        self,
        product_map: Optional[Dict[str, dict]] = None,
    ) -> pd.DataFrame:
        """
        Fetch current stock balance from Microvix (LinxSaldoEstoque).
        Endpoint: LinxSaldoEstoque — returns one record per SKU/location.
        Returns DataFrame: referencia, categoria, quantidade
        """
        records = self._post("LinxSaldoEstoque", "")

        _map    = product_map or {}
        has_map = bool(_map)
        rows: list = []

        for rec in records:
            qty = _br_float(rec.get("quantidade", 0))
            if qty < 0:
                continue  # negative stock records are adjustments, skip

            cod = str(rec.get("cod_produto", "")).strip()

            if has_map:
                entry = _map.get(cod)
                if not entry:
                    continue
                ref = entry["referencia"]
                cat = entry["categoria"]
            else:
                ref = cod
                cat = "?"

            rows.append({
                "referencia": ref,
                "categoria":  cat,
                "quantidade": qty,
            })

        if not rows:
            return pd.DataFrame(columns=["referencia", "categoria", "quantidade"])

        df = pd.DataFrame(rows)
        # Aggregate: sum quantities for same ref (multiple locations)
        return (
            df.groupby(["referencia", "categoria"], as_index=False)["quantidade"].sum()
        )

    def get_inventory(
        self,
        product_map=None,
    ) -> pd.DataFrame:
        """Busca último inventário físico do Microvix (LinxInventarios).
        Fallback alternativo ao LinxSaldoEstoque.
        Retorna DataFrame: referencia, categoria, quantidade
        """
        try:
            records = self._post("LinxInventarios", "")
        except MicrovixAPIError:
            return pd.DataFrame(columns=["referencia", "categoria", "quantidade"])

        _map = product_map or {}
        has_map = bool(_map)
        rows: list = []

        for rec in records:
            qty = _br_float(rec.get("quantidade", 0) or rec.get("qtd", 0) or rec.get("saldo", 0))
            if qty <= 0:
                continue
            cod = str(rec.get("cod_produto", "") or rec.get("codigo_produto", "")).strip()
            if has_map:
                entry = _map.get(cod)
                if not entry:
                    continue
                ref = entry["referencia"]
                cat = entry["categoria"]
            else:
                ref = cod
                cat = "?"
            rows.append({"referencia": ref, "categoria": cat, "quantidade": qty})

        if not rows:
            return pd.DataFrame(columns=["referencia", "categoria", "quantidade"])
        df = pd.DataFrame(rows)
        return df.groupby(["referencia", "categoria"], as_index=False)["quantidade"].sum()

    def get_retorno_raw(
        self,
        months: int = 36,
        product_map: Optional[Dict[str, dict]] = None,
    ) -> pd.DataFrame:
        """Busca histórico de compras dos últimos `months` meses no LinxMovimento.

        Retorna DataFrame com colunas:
            codigo_cliente, ultima_compra, categoria, vlr_ultima_compra
        Uma linha por (cliente, categoria) com a compra mais recente.
        """
        from datetime import date as _date
        dt_fim = _date.today()
        dt_ini = dt_fim - timedelta(days=months * 30)
        _map    = product_map or {}
        has_map = bool(_map)
        # best[key] = {"ultima_compra": dt, "vlr_ultima_compra": val,
        #              "frequencia": int, "valor_total": float}
        best: dict = {}
        cur_end = dt_fim
        while cur_end > dt_ini:
            cur_start = max(dt_ini, cur_end - timedelta(days=182))
            params = (
                '<Parameter id="data_inicial">' + cur_start.strftime("%Y-%m-%d") + '</Parameter>'
                '<Parameter id="data_fim">'     + cur_end.strftime("%Y-%m-%d")   + '</Parameter>'
            )
            try:
                records = self._post("LinxMovimento", params)
            except MicrovixAPIError:
                records = []
            for rec in records:
                if rec.get("cancelado") == "S" or rec.get("excluido") == "S":
                    continue
                qty   = _br_float(rec.get("quantidade", 0))
                price = _br_float(rec.get("preco_unitario", 0))
                if price <= 0 or qty <= 0:
                    continue
                cod_cli = str(rec.get("codigo_cliente", "")).strip()
                if not cod_cli or cod_cli == "0":
                    continue
                cod_prod = str(rec.get("cod_produto", "")).strip()
                if has_map:
                    entry = _map.get(cod_prod)
                    if not entry:
                        continue
                    cat = entry["categoria"]
                else:
                    cat = "?"
                dt = pd.to_datetime(
                    rec.get("data_documento", ""),
                    format="%d/%m/%Y %H:%M:%S", errors="coerce")
                if pd.isna(dt):
                    continue
                key = (cod_cli, cat)
                val = round(price * qty, 2)
                if key not in best:
                    best[key] = {
                        "ultima_compra":    dt,
                        "vlr_ultima_compra": val,
                        "frequencia":       0,
                        "valor_total":      0.0,
                    }
                if dt >= best[key]["ultima_compra"]:
                    best[key]["ultima_compra"]    = dt
                    best[key]["vlr_ultima_compra"] = val
                best[key]["frequencia"]  += 1
                best[key]["valor_total"]  = round(best[key]["valor_total"] + val, 2)
            cur_end = cur_start - timedelta(days=1)
        if not best:
            return pd.DataFrame(
                columns=["codigo_cliente", "ultima_compra", "categoria",
                         "vlr_ultima_compra", "frequencia", "valor_total"])
        rows = [
            {
                "codigo_cliente":    k[0],
                "categoria":         k[1],
                "ultima_compra":     v["ultima_compra"],
                "vlr_ultima_compra": v["vlr_ultima_compra"],
                "frequencia":        v["frequencia"],
                "valor_total":       v["valor_total"],
            }
            for k, v in best.items()
        ]
        return pd.DataFrame(rows)

    # ── Produtos ──────────────────────────────────────────────────────────────

    def get_products(self, timestamp: str = "") -> pd.DataFrame:
        """LinxProdutos — catálogo completo de produtos.

        timestamp (opcional): retorna apenas registros alterados após essa data/hora.
        Formato: 'YYYY-MM-DDTHH:MM:SS' ou deixe '' para buscar tudo.
        """
        params = f'<Parameter id="timestamp">{timestamp}</Parameter>' if timestamp else ""
        records = self._post("LinxProdutos", params)
        return pd.DataFrame(records) if records else pd.DataFrame()

    def get_products_from_sales(self, months: int = 18) -> pd.DataFrame:
        """Constrói catálogo de produtos a partir do histórico de vendas (LinxMovimento).

        Útil quando LinxProdutos não está habilitado no plano da API.
        Busca 'months' meses de vendas sem filtro de mapa e extrai pares
        únicos (cod_produto, referencia) com preço de tabela.

        A referência é resolvida buscando o primeiro campo não-numérico entre
        vários candidatos do registro — priorizando campos que iniciam com os
        prefixos conhecidos (LV./OC./ML./LE./LC./AC.) antes de cair em cod_barra.

        Retorna DataFrame com colunas: cod_produto, referencia, preco_venda.
        """
        from datetime import date, timedelta
        from modules.product_map import ref_to_category  # evita circular import
        dt_fim = str(date.today())
        dt_ini = str(date.today() - timedelta(days=months * 30))
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxMovimento", params)

        # Campos candidatos à referência, em ordem de prioridade
        _REF_FIELDS = [
            "referencia", "cod_referencia", "referencia_produto",
            "cod_produto_referencia", "cod_barra",
        ]
        # Regex para extrair código de referência Chilli Beans da descrição
        # Ex: "ARMAÇÃO LV.IJ.001 PRETO 52" → "LV.IJ.001"
        _REF_RE = re.compile(
            r'\b(LV\.[A-Z]{2}|OC\.[A-Z]{2}|ML[.\-]|LE\.[A-Z]{2}|LC[.\-]|AC[.\-])'
            r'[A-Z0-9.\-]{1,20}',
            re.IGNORECASE,
        )

        def _best_ref(rec: dict) -> str:
            """Retorna o primeiro campo que representa uma referência válida."""
            candidates = []
            for f in _REF_FIELDS:
                v = str(rec.get(f, "") or "").strip()
                if v:
                    candidates.append(v)
            # 1. Prefere candidato com prefixo reconhecido (LV./OC./ML./LE./LC./AC.)
            for v in candidates:
                if ref_to_category(v) is not None:
                    return v
            # 2. Tenta extrair referência do campo descricao (ex: "ARMAÇÃO LV.IJ.001")
            for df_field in ("descricao", "descricao_completa", "nome_produto", "descricao_produto"):
                descr = str(rec.get(df_field, "") or "").strip()
                if descr:
                    m = _REF_RE.search(descr)
                    if m:
                        candidate = m.group(0).upper().strip()
                        if ref_to_category(candidate) is not None:
                            return candidate
            # 3. Prefere candidato alfanumérico com ponto (ex: LV.IJ.001)
            for v in candidates:
                if "." in v and not v.replace(".", "").replace(",", "").isdigit():
                    return v
            # 4. Fallback: primeiro candidato não-vazio
            return candidates[0] if candidates else ""

        seen: dict = {}  # cod_produto → {referencia, preco_venda}
        for rec in records:
            if rec.get("cancelado") == "S" or rec.get("excluido") == "S":
                continue
            cod = str(rec.get("cod_produto", "")).strip()
            if not cod:
                continue
            ref = _best_ref(rec)
            if not ref:
                continue
            if cod not in seen:
                preco = _br_float(rec.get("preco_cheio", 0)) or _br_float(rec.get("preco_unitario", 0))
                seen[cod] = {"referencia": ref, "preco_venda": preco if preco > 0 else None}
        rows = [{"cod_produto": k, **v} for k, v in seen.items()]
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def get_product_details(self, timestamp: str = "") -> pd.DataFrame:
        """LinxProdutosDetalhes — detalhes completos (preços, NCM, grade, composição)."""
        params = f'<Parameter id="timestamp">{timestamp}</Parameter>' if timestamp else ""
        records = self._post("LinxProdutosDetalhes", params)
        return pd.DataFrame(records) if records else pd.DataFrame()

    def get_stock_by_deposit(self) -> pd.DataFrame:
        """LinxProdutosDetalhesDepositos — saldo de estoque por depósito/filial."""
        records = self._post("LinxProdutosDetalhesDepositos", "")
        return pd.DataFrame(records) if records else pd.DataFrame()

    def get_product_suppliers(self, timestamp: str = "") -> pd.DataFrame:
        """LinxProdutosFornec — produtos × fornecedores com preço de custo."""
        params = f'<Parameter id="timestamp">{timestamp}</Parameter>' if timestamp else ""
        records = self._post("LinxProdutosFornec", params)
        return pd.DataFrame(records) if records else pd.DataFrame()

    def get_product_images(self, timestamp: str = "") -> pd.DataFrame:
        """LinxProdutosImagensURL — URLs das imagens cadastradas por produto."""
        params = f'<Parameter id="timestamp">{timestamp}</Parameter>' if timestamp else ""
        records = self._post("LinxProdutosImagensURL", params)
        return pd.DataFrame(records) if records else pd.DataFrame()

    def get_product_optics_types(self, timestamp: str = "") -> pd.DataFrame:
        """LinxProdutosOpticosTipo — tipos de produtos óticos (monomodal, progressivo…)."""
        params = f'<Parameter id="timestamp">{timestamp}</Parameter>' if timestamp else ""
        records = self._post("LinxProdutosOpticosTipo", params)
        return pd.DataFrame(records) if records else pd.DataFrame()

    def get_product_serials(self, dt_ini: str = "", dt_fim: str = "") -> pd.DataFrame:
        """LinxProdutosSerial — seriais/IMEI cadastrados por produto."""
        params = ""
        if dt_ini and dt_fim:
            params = (
                f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
                f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
            )
        records = self._post("LinxProdutosSerial", params)
        return pd.DataFrame(records) if records else pd.DataFrame()

    # ── Clientes ──────────────────────────────────────────────────────────────

    def get_clients_api(self, timestamp: str = "") -> dict:
        """LinxClientes — importa cadastro completo de clientes direto da API.

        Retorna dict compatível com client_map:
        {codigo_str: {nome, fone, email, cidade, uf, aniversario, nascimento, cliente_desde}}
        """
        from modules.client_map import _parse_month, _parse_date_str, _title_case  # noqa

        params = f'<Parameter id="timestamp">{timestamp}</Parameter>' if timestamp else ""
        records = self._post("LinxClientes", params)

        clients: dict = {}
        for rec in records:
            codigo = str(rec.get("codigo_cliente", "")).strip()
            if not codigo or not codigo.isdigit():
                continue
            nome = str(
                rec.get("nome", "") or rec.get("razao_social", "") or rec.get("nome_cliente", "")
            ).strip()
            if not nome or len(nome) < 3:
                continue

            # Telefone — prefere celular
            ddd_cel = str(rec.get("ddd_celular", "") or rec.get("ddd_cel", "") or "").strip()
            cel     = str(rec.get("celular", "") or "").strip()
            ddd_tel = str(rec.get("ddd_telefone", "") or rec.get("ddd_tel", "") or "").strip()
            tel     = str(rec.get("telefone", "") or "").strip()

            fone = ""
            if cel:
                fone = (ddd_cel + cel) if ddd_cel and not cel.startswith(ddd_cel) else cel
            elif tel:
                fone = (ddd_tel + tel) if ddd_tel and not tel.startswith(ddd_tel) else tel

            nasc_raw  = str(rec.get("data_nascimento", "") or "").strip()
            desde_raw = str(
                rec.get("data_cadastro", "") or rec.get("cliente_desde", "") or ""
            ).strip()

            clients[codigo] = {
                "nome":          _title_case(nome),
                "fone":          fone,
                "email":         str(rec.get("email", "") or "").strip(),
                "cidade":        _title_case(str(rec.get("cidade", "") or "").strip()),
                "uf":            str(rec.get("uf", "") or "").strip().upper(),
                "aniversario":   _parse_month(nasc_raw),
                "nascimento":    _parse_date_str(nasc_raw),
                "cliente_desde": _parse_date_str(desde_raw),
            }

        return clients

    def get_client_delivery_addresses(self, timestamp: str = "") -> pd.DataFrame:
        """LinxClientesEnderecosEntrega — endereços de entrega por cliente."""
        params = f'<Parameter id="timestamp">{timestamp}</Parameter>' if timestamp else ""
        records = self._post("LinxClientesEnderecosEntrega", params)
        return pd.DataFrame(records) if records else pd.DataFrame()

    def get_client_classes(self) -> pd.DataFrame:
        """LinxClientesFornecClasses — classes/segmentação de clientes (VIP, regular…)."""
        records = self._post("LinxClientesFornecClasses", "")
        return pd.DataFrame(records) if records else pd.DataFrame()

    # ── Movimento / Vendas — detalhamento ────────────────────────────────────

    def get_sales_header(self, dt_ini: str, dt_fim: str) -> pd.DataFrame:
        """LinxMovimentoPrincipal — cabeçalho das vendas: vendedor, desconto, totais.

        Retorna DataFrame: num_documento, data, cod_vendedor, nome_vendedor,
                           codigo_cliente, vlr_total, desconto
        """
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxMovimentoPrincipal", params)
        rows: list = []
        for rec in records:
            if rec.get("cancelado") == "S" or rec.get("excluido") == "S":
                continue
            rows.append({
                "num_documento":  str(rec.get("num_documento", "") or rec.get("numero_documento", "") or ""),
                "data":           pd.to_datetime(
                                      rec.get("data_documento", ""),
                                      format="%d/%m/%Y %H:%M:%S", errors="coerce",
                                  ),
                "cod_vendedor":   str(rec.get("cod_vendedor", "") or ""),
                "nome_vendedor":  str(rec.get("nome_vendedor", "") or ""),
                "codigo_cliente": str(rec.get("codigo_cliente", "") or ""),
                "vlr_total":      _br_float(rec.get("vlr_total", 0)),
                "desconto":       _br_float(
                                      rec.get("vlr_desconto", 0) or rec.get("desconto", 0)
                                  ),
            })
        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["num_documento", "data", "cod_vendedor", "nome_vendedor",
                     "codigo_cliente", "vlr_total", "desconto"]
        )

    def get_gift_card_movements(self, dt_ini: str, dt_fim: str) -> pd.DataFrame:
        """LinxMovimentoGiftCard — emissões e utilizações de Gift Card."""
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxMovimentoGiftCard", params)
        return pd.DataFrame(records) if records else pd.DataFrame()

    def get_sales_referrals(self, dt_ini: str, dt_fim: str) -> pd.DataFrame:
        """LinxMovimentoIndicacoes — cliente indicador por venda."""
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxMovimentoIndicacoes", params)
        return pd.DataFrame(records) if records else pd.DataFrame()

    def get_consignment(self, dt_ini: str, dt_fim: str) -> pd.DataFrame:
        """LinxMovimentoRemessas — remessas (consignado/demonstração)."""
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxMovimentoRemessas", params)
        return pd.DataFrame(records) if records else pd.DataFrame()

    def get_consignment_items(self, dt_ini: str, dt_fim: str) -> pd.DataFrame:
        """LinxMovimentoRemessasItens — itens das remessas."""
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxMovimentoRemessasItens", params)
        return pd.DataFrame(records) if records else pd.DataFrame()

    def get_conjugated_sales(self, dt_ini: str, dt_fim: str) -> pd.DataFrame:
        """LinxMovimentoVendaConjugada — venda conjugada (armação + lente no mesmo NF)."""
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxMovimentoVendaConjugada", params)
        return pd.DataFrame(records) if records else pd.DataFrame()

    # ── Fiscal / NF-e ─────────────────────────────────────────────────────────

    def get_nfe(self, dt_ini: str, dt_fim: str) -> pd.DataFrame:
        """LinxNFe — notas fiscais emitidas no período.

        Retorna DataFrame: numero, serie, chave, data_emissao, vlr_total, situacao, cod_cliente
        """
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxNFe", params)
        rows: list = []
        for rec in records:
            rows.append({
                "numero":       str(rec.get("numero_nf", "") or rec.get("numero", "") or ""),
                "serie":        str(rec.get("serie", "") or ""),
                "chave":        str(rec.get("chave_nfe", "") or rec.get("chave", "") or ""),
                "data_emissao": pd.to_datetime(
                                    rec.get("data_emissao", "") or rec.get("data_documento", ""),
                                    format="%d/%m/%Y %H:%M:%S", errors="coerce",
                                ),
                "vlr_total":    _br_float(
                                    rec.get("vlr_total_nf", 0) or rec.get("vlr_total", 0)
                                ),
                "situacao":     str(rec.get("situacao", "") or ""),
                "cod_cliente":  str(rec.get("codigo_cliente", "") or ""),
            })
        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["numero", "serie", "chave", "data_emissao",
                     "vlr_total", "situacao", "cod_cliente"]
        )

    def get_nfe_events(self, dt_ini: str, dt_fim: str) -> pd.DataFrame:
        """LinxNFeEvento — eventos de NF-e (cancelamentos, correções, inutilizações)."""
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxNFeEvento", params)
        return pd.DataFrame(records) if records else pd.DataFrame()

    def get_nfse(self, dt_ini: str, dt_fim: str) -> pd.DataFrame:
        """LinxNfse — notas fiscais de serviços (lab de lentes, manutenção)."""
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxNfse", params)
        return pd.DataFrame(records) if records else pd.DataFrame()

    # ── Operacional / Gestão ──────────────────────────────────────────────────

    def get_store_params(self) -> dict:
        """LinxLojasParametros — parâmetros da loja (nome, CNPJ, DDD, endereço).

        Retorna o primeiro registro como dict, ou {} se vazio.
        """
        records = self._post("LinxLojasParametros", "")
        return dict(records[0]) if records else {}

    def get_series(self) -> pd.DataFrame:
        """LinxSeries — séries de documentos (NF-e, NFC-e)."""
        records = self._post("LinxSeries", "")
        return pd.DataFrame(records) if records else pd.DataFrame()

    def get_users(self) -> pd.DataFrame:
        """LinxUsuarios — usuários/vendedores cadastrados no sistema.

        Retorna DataFrame: cod_usuario, nome_usuario, login, ativo
        """
        records = self._post("LinxUsuarios", "")
        rows: list = []
        for rec in records:
            rows.append({
                "cod_usuario":  str(rec.get("cod_usuario", "") or ""),
                "nome_usuario": str(rec.get("nome_usuario", "") or ""),
                "login":        str(rec.get("login", "") or ""),
                "ativo":        rec.get("ativo", "S") == "S",
            })
        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["cod_usuario", "nome_usuario", "login", "ativo"]
        )

    def get_seller_daily_goals(self, dt_ini: str, dt_fim: str) -> pd.DataFrame:
        """LinxMetasVendedoresDia — metas diárias por vendedor.

        Retorna DataFrame: data, cod_vendedor, nome_vendedor, meta_dia, vlr_vendido
        """
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxMetasVendedoresDia", params)
        rows: list = []
        for rec in records:
            rows.append({
                "data":          pd.to_datetime(
                                     rec.get("data", ""),
                                     format="%d/%m/%Y", errors="coerce",
                                 ),
                "cod_vendedor":  str(rec.get("cod_vendedor", "") or ""),
                "nome_vendedor": str(rec.get("nome_vendedor", "") or ""),
                "meta_dia":      _br_float(rec.get("meta_dia", 0) or rec.get("meta", 0)),
                "vlr_vendido":   _br_float(
                                     rec.get("vlr_vendido", 0) or rec.get("valor_vendido", 0)
                                 ),
            })
        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["data", "cod_vendedor", "nome_vendedor", "meta_dia", "vlr_vendido"]
        )

    def get_consignment_operations(self) -> pd.DataFrame:
        """LinxRemessasOperacoes — tipos de operação de remessa."""
        records = self._post("LinxRemessasOperacoes", "")
        return pd.DataFrame(records) if records else pd.DataFrame()

    def get_service_orders(self, dt_ini: str, dt_fim: str) -> pd.DataFrame:
        """LinxValeOrdemServicoExterna — ordens de serviço externas (ex.: lab de lentes)."""
        params = (
            f'<Parameter id="data_inicial">{self._to_iso(dt_ini)}</Parameter>'
            f'<Parameter id="data_fim">{self._to_iso(dt_fim)}</Parameter>'
        )
        records = self._post("LinxValeOrdemServicoExterna", params)
        return pd.DataFrame(records) if records else pd.DataFrame()


# ── Retorno de Clientes ───────────────────────────────────────────────────────

def mock_sales_header(dt_ini: str, dt_fim: str, seed: int = 42) -> pd.DataFrame:
    """Mock cabeçalhos de venda com vendedores — para demo mode."""
    rng = np.random.default_rng(seed)
    start, end, _ = _parse_dates(dt_ini, dt_fim)
    vendedores = [
        ("1", "Ana Paula"),
        ("2", "Carlos Silva"),
        ("3", "Mariana Lima"),
        ("4", "Rafael Santos"),
        ("5", "Juliana Costa"),
    ]
    rows: list = []
    cur = start
    doc_num = 10001
    while cur <= end:
        n = int(rng.poisson(8 + (3 if cur.weekday() >= 5 else 0)))
        for _ in range(n):
            cod_v, nome_v = vendedores[rng.integers(0, len(vendedores))]
            vlr  = round(float(rng.uniform(150.0, 850.0)), 2)
            desc = round(vlr * float(rng.choice([0.0, 0.0, 0.0, 0.05, 0.10])), 2)
            rows.append({
                "num_documento":  str(doc_num),
                "data":           cur,
                "cod_vendedor":   cod_v,
                "nome_vendedor":  nome_v,
                "codigo_cliente": str(int(rng.integers(1000, 9999))),
                "vlr_total":      vlr,
                "desconto":       desc,
            })
            doc_num += 1
        cur += timedelta(days=1)
    return pd.DataFrame(rows)


def mock_seller_goals(dt_ini: str, dt_fim: str, seed: int = 11) -> pd.DataFrame:
    """Mock metas diárias de vendedores — para demo mode."""
    rng = np.random.default_rng(seed)
    start, end, _ = _parse_dates(dt_ini, dt_fim)
    vendedores = [
        ("1", "Ana Paula"),
        ("2", "Carlos Silva"),
        ("3", "Mariana Lima"),
        ("4", "Rafael Santos"),
        ("5", "Juliana Costa"),
    ]
    rows: list = []
    cur = start
    while cur <= end:
        if cur.weekday() < 6:  # seg–sáb
            for cod_v, nome_v in vendedores:
                meta = round(float(rng.uniform(800.0, 1600.0)), 2)
                ating = round(meta * float(rng.uniform(0.60, 1.25)), 2)
                rows.append({
                    "data":          cur,
                    "cod_vendedor":  cod_v,
                    "nome_vendedor": nome_v,
                    "meta_dia":      meta,
                    "vlr_vendido":   ating,
                })
        cur += timedelta(days=1)
    return pd.DataFrame(rows)


def mock_nfe(dt_ini: str, dt_fim: str, seed: int = 77) -> pd.DataFrame:
    """Mock notas fiscais emitidas — para demo mode."""
    rng = np.random.default_rng(seed)
    df_hdr = mock_sales_header(dt_ini, dt_fim, seed)
    if df_hdr.empty:
        return pd.DataFrame(
            columns=["numero", "serie", "chave", "data_emissao",
                     "vlr_total", "situacao", "cod_cliente"]
        )
    rows: list = []
    for i, (_, row) in enumerate(df_hdr.iterrows()):
        rows.append({
            "numero":       str(9000 + i),
            "serie":        "001",
            # Chave de acesso NF-e tem 44 dígitos; UF 35 (SP) + 42 dígitos aleatórios.
            # Gerada dígito a dígito para evitar estouro de int64 no numpy.
            "chave":        "35" + "".join(str(int(d)) for d in rng.integers(0, 10, size=42)),
            "data_emissao": row["data"],
            "vlr_total":    row["vlr_total"],
            "situacao":     "Cancelada" if rng.random() < 0.04 else "Autorizada",
            "cod_cliente":  row["codigo_cliente"],
        })
    return pd.DataFrame(rows)


def mock_retorno(client_map: dict, seed: int = 55) -> pd.DataFrame:
    rng   = np.random.default_rng(seed)
    today = datetime.today()
    # Inclui todas as categorias; lentes e acessórios têm ciclos mais curtos
    cats  = ["LV",   "OC",  "ML",  "LE",  "LC",  "AC"]
    cat_p = [0.35,   0.20,  0.12,  0.13,  0.10,  0.10]
    # Faixa de valor por categoria
    cat_value = {
        "LV": (149.0, 699.0), "OC": (249.0, 499.0), "ML": (299.0, 749.0),
        "LE": (189.0, 649.0), "LC": (49.0,  199.0),  "AC": (19.0,  89.0),
    }
    # Dias típicos desde a última compra por categoria (ciclos mais curtos para LC/AC)
    cat_days = {
        "LV": (120, 1290), "OC": (90, 1080), "ML": (180, 1440),
        "LE": (60,  730),  "LC": (30, 365),  "AC": (30, 730),
    }
    ids = [k for k in list(client_map.keys()) if k.isdigit()]
    rng.shuffle(ids)
    rows = []
    for cod in ids[:200]:
        n_cats = int(rng.integers(1, 4))
        chosen = list(rng.choice(cats, size=min(n_cats, len(cats)), replace=False, p=cat_p))
        for cat in chosen:
            d_min, d_max = cat_days[cat]
            days_ago = int(rng.integers(d_min, d_max))
            last_dt  = today - timedelta(days=days_ago)
            v_min, v_max = cat_value[cat]
            vlr_ult  = round(float(rng.uniform(v_min, v_max)), 2)
            freq     = int(rng.integers(1, 8))           # 1–7 compras no período
            total    = round(vlr_ult * rng.uniform(0.9, float(freq) * 1.1), 2)
            rows.append({
                "codigo_cliente":    cod,
                "ultima_compra":     last_dt,
                "categoria":         cat,
                "vlr_ultima_compra": vlr_ult,
                "frequencia":        freq,
                "valor_total":       total,
            })
    if not rows:
        return pd.DataFrame(columns=[
            "codigo_cliente", "ultima_compra", "categoria",
            "vlr_ultima_compra", "frequencia", "valor_total",
        ])
    return pd.DataFrame(rows)