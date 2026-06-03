"""
test_uf_batch_roi.py — UF × LOTE-DE-IMPORTAÇÃO (15/05) e ranking de praças por
ROI de enriquecimento telefônico (builder, iteração 14).

Por que existe:
  A Iter 13 (GEO-1) mostrou que o WhatsApp — único canal de saída ativo — é, na
  prática, SP-only. A Iter 12 (DADOS-7) achou que 58% da base carrega um carimbo
  de importação (cliente_desde = 15/05/2026), e-mail-rico/telefone-pobre. Esta
  iteração CRUZA as duas lentes: por UF, quanto da praça é "lote 15/05" vs
  "nativo de PDV", e quantos clientes do lote estão SEM TELEFONE — para RANQUEAR
  as praças por ROI de enriquecimento de telefone (o investimento que destrava o
  WhatsApp num território hoje cego).

  Achados concretos (produção, 31/05/2026, client_map de 27/05 21:38, 1.825 cli):
    >>> ACHADO PRINCIPAL (UF-1): 24 das 27 UFs são "PURO-LOTE" — 100% dos
        clientes vieram do import de 15/05 e há ZERO clientes nativos de PDV;
        nelas o WhatsApp é ~0%. Só SP é mista (750 nativos + 307 do lote, 70% WA);
        RJ/MG/BA/DF têm 1-4 nativos (~misto, mas WA ~2-8%). Ou seja: fora de SP,
        a base inteira de cada praça é um lote sem telefone.

    >>> ROI de enriquecimento telefônico — clientes do lote 15/05 SEM telefone
        normalizável, por UF (cada um destrava 1 alcance de WhatsApp novo):
          SP 306 · MG 151 · BA 62 · RJ 60 · PR 51 · DF 47 · GO 44 · PA 41 ·
          SC 39 · MT 39 · PE 30 · RS 28 · RN 23 · CE 18 · ES 17 · PI 17 · ...
          TOTAL recuperável = 1.059 clientes.
        Leitura de ROI: enriquecer SÓ o lote de SP (306) é o passo mais barato
        (praça que já tem operação de WhatsApp), mas NÃO abre território novo.
        Para dar QUALQUER fila de WhatsApp aos captadores/vendedores fora de SP,
        é preciso enriquecer as praças puro-lote — e aí o ranking por volume
        (MG 151, BA 62, RJ 60, PR 51, DF 47, GO 44, PA 41) prioriza onde cada
        real de enriquecimento alcança mais clientes.

  Estes testes guardam o CONTRATO das funções puras (classificar lote vs nativo,
  pureza da praça, ROI por UF) sobre base SINTÉTICA, registrando o achado em
  forma versionada e protegendo contra regressão silenciosa caso o import passe a
  preservar o cliente_desde real (DADOS-7). Tarefas para o humano: UF-1 no
  relatório.

ESCOPO E SEGURANÇA:
  Só funções PURAS sobre base SINTÉTICA em memória + normalize_phone
  (modules.marketing). NÃO chama load/save/import sobre dados reais. Guard de
  mtime confirma que data/client_map.json de PRODUÇÃO não é tocado (27/05 21:38).
  Rodar com:  venv\\Scripts\\python.exe -m unittest discover -s tests
"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.marketing import normalize_phone          # noqa: E402

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLIENT_MAP = os.path.join(_BASE, "data", "client_map.json")

# Data do carimbo de importação detectado na Iter 12 (DADOS-7).
IMPORT_STAMP = datetime.date(2026, 5, 15)


# ---------------------------------------------------------------- helpers puros
def _parse(raw):
    """date a partir de 'DD/MM/AAAA', ou None se vazio/'-'/inválido."""
    s = (raw or "").strip()
    if not s or s == "-":
        return None
    try:
        return datetime.datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        return None


def is_batch_client(rec, stamp=IMPORT_STAMP):
    """True se o cliente_desde do registro é exatamente a data do carimbo."""
    return _parse((rec or {}).get("cliente_desde", "")) == stamp


def uf_batch_roi_report(cmap, stamp=IMPORT_STAMP, default_ddd=""):
    """Métrica PURA por UF — sem escrever nada.

    Para cada UF mede: total, quantos vieram do lote (cliente_desde == stamp),
    quantos são nativos (qualquer outra data / sem data), alcance WhatsApp
    (telefone normalizável) e quantos clientes DO LOTE estão sem telefone
    (= ROI de enriquecimento: cada um destrava 1 alcance de WhatsApp novo).

    Retorna dict:
      {
        "total": int,
        "batch_total": int,
        "roi_total": int,                 # soma de batch_sem_fone na base toda
        "por_uf": { uf: {total, batch, nativo, wa, batch_sem_fone,
                          pct_batch, pct_wa, puro_lote(bool)} },
        "roi_ranking": [ (uf, batch_sem_fone), ... ]  # desc por volume
      }
    """
    por_uf = {}
    batch_total = 0
    for v in cmap.values():
        v = v or {}
        uf = (v.get("uf") or "").strip().upper() or "(vazio)"
        d = por_uf.setdefault(
            uf, {"total": 0, "batch": 0, "nativo": 0, "wa": 0,
                 "batch_sem_fone": 0}
        )
        d["total"] += 1
        has_phone = bool(normalize_phone(v.get("fone", ""), default_ddd))
        if has_phone:
            d["wa"] += 1
        if is_batch_client(v, stamp):
            d["batch"] += 1
            batch_total += 1
            if not has_phone:
                d["batch_sem_fone"] += 1
        else:
            d["nativo"] += 1

    roi_total = 0
    for uf, d in por_uf.items():
        t = d["total"]
        d["pct_batch"] = (100.0 * d["batch"] / t) if t else 0.0
        d["pct_wa"] = (100.0 * d["wa"] / t) if t else 0.0
        # "puro-lote": só clientes do lote, nenhum nativo de PDV
        d["puro_lote"] = d["batch"] > 0 and d["nativo"] == 0
        roi_total += d["batch_sem_fone"]

    roi_ranking = sorted(
        ((uf, d["batch_sem_fone"]) for uf, d in por_uf.items()
         if d["batch_sem_fone"] > 0),
        key=lambda kv: -kv[1],
    )

    return {
        "total": len(cmap),
        "batch_total": batch_total,
        "roi_total": roi_total,
        "por_uf": por_uf,
        "roi_ranking": roi_ranking,
    }


# ----------------------------------------------------------------------- guard
class _ClientMapGuard(unittest.TestCase):
    """Garante que a base de clientes de produção nunca é tocada pela suíte."""

    @classmethod
    def setUpClass(cls):
        cls._mtime = (os.path.getmtime(_CLIENT_MAP)
                      if os.path.exists(_CLIENT_MAP) else None)

    @classmethod
    def tearDownClass(cls):
        now = (os.path.getmtime(_CLIENT_MAP)
               if os.path.exists(_CLIENT_MAP) else None)
        assert now == cls._mtime, (
            "client_map.json de PRODUÇÃO foi modificado pela suíte!"
        )


# ----------------------------------------------------------------------- testes
class TestIsBatchClient(unittest.TestCase):
    def test_carimbo_eh_lote(self):
        self.assertTrue(is_batch_client({"cliente_desde": "15/05/2026"}))

    def test_outra_data_eh_nativo(self):
        self.assertFalse(is_batch_client({"cliente_desde": "22/07/2007"}))

    def test_sem_data_eh_nativo(self):
        self.assertFalse(is_batch_client({"cliente_desde": ""}))
        self.assertFalse(is_batch_client({"cliente_desde": "-"}))
        self.assertFalse(is_batch_client({}))

    def test_stamp_parametrizavel(self):
        self.assertTrue(is_batch_client(
            {"cliente_desde": "01/01/2020"}, stamp=datetime.date(2020, 1, 1)))


class TestUfBatchRoi(_ClientMapGuard):
    def _base(self):
        # SP: 2 nativos (1 c/ fone, 1 c/ fone) + 2 do lote (1 s/ fone, 1 c/ fone)
        # MG: puro-lote, 2 do lote ambos sem fone
        # RJ: misto, 1 nativo c/ fone + 1 do lote sem fone
        return {
            "1": {"uf": "SP", "fone": "(11)91234-5678",
                  "cliente_desde": "10/01/2020"},
            "2": {"uf": "SP", "fone": "(11)3000-0000",
                  "cliente_desde": "05/06/2019"},
            "3": {"uf": "SP", "fone": "",
                  "cliente_desde": "15/05/2026"},
            "4": {"uf": "SP", "fone": "(11)98888-7777",
                  "cliente_desde": "15/05/2026"},
            "5": {"uf": "MG", "fone": "",
                  "cliente_desde": "15/05/2026"},
            "6": {"uf": "mg", "fone": "  ",
                  "cliente_desde": "15/05/2026"},
            "7": {"uf": "RJ", "fone": "(21)97777-6666",
                  "cliente_desde": "02/02/2018"},
            "8": {"uf": "RJ", "fone": "",
                  "cliente_desde": "15/05/2026"},
        }

    def test_totais(self):
        r = uf_batch_roi_report(self._base())
        self.assertEqual(r["total"], 8)
        self.assertEqual(r["batch_total"], 5)   # 3,4,5,6,8

    def test_uf_normalizado(self):
        r = uf_batch_roi_report(self._base())
        # "MG" e "mg" colapsam num só bucket
        self.assertIn("MG", r["por_uf"])
        self.assertNotIn("mg", r["por_uf"])
        self.assertEqual(r["por_uf"]["MG"]["total"], 2)

    def test_puro_lote_flag(self):
        r = uf_batch_roi_report(self._base())
        self.assertTrue(r["por_uf"]["MG"]["puro_lote"])   # só lote
        self.assertFalse(r["por_uf"]["SP"]["puro_lote"])  # tem nativos
        self.assertFalse(r["por_uf"]["RJ"]["puro_lote"])  # 1 nativo

    def test_batch_sem_fone_e_roi(self):
        r = uf_batch_roi_report(self._base())
        self.assertEqual(r["por_uf"]["SP"]["batch_sem_fone"], 1)  # só #3
        self.assertEqual(r["por_uf"]["MG"]["batch_sem_fone"], 2)  # #5,#6
        self.assertEqual(r["por_uf"]["RJ"]["batch_sem_fone"], 1)  # #8
        self.assertEqual(r["roi_total"], 4)

    def test_roi_ranking_ordenado_desc(self):
        r = uf_batch_roi_report(self._base())
        vals = [n for _, n in r["roi_ranking"]]
        self.assertEqual(vals, sorted(vals, reverse=True))
        self.assertEqual(r["roi_ranking"][0], ("MG", 2))  # maior ROI

    def test_wa_so_conta_telefone_normalizavel(self):
        r = uf_batch_roi_report(self._base())
        # SP tem 3 com fone (1,2,4); 3 sem (só #3)
        self.assertEqual(r["por_uf"]["SP"]["wa"], 3)
        self.assertEqual(r["por_uf"]["MG"]["wa"], 0)

    def test_base_vazia_nao_quebra(self):
        r = uf_batch_roi_report({})
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["batch_total"], 0)
        self.assertEqual(r["roi_total"], 0)
        self.assertEqual(r["roi_ranking"], [])

    def test_stamp_diferente_muda_classificacao(self):
        # Com stamp em outra data, ninguém é lote → roi zero, nada puro-lote
        r = uf_batch_roi_report(self._base(), stamp=datetime.date(1999, 1, 1))
        self.assertEqual(r["batch_total"], 0)
        self.assertEqual(r["roi_total"], 0)
        self.assertFalse(any(d["puro_lote"] for d in r["por_uf"].values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
