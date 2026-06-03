"""
dateutils.py — utilitários PUROS de data no padrão brasileiro (DD/MM/AAAA).

Motivo de existir
-----------------
O app guarda datas como texto "DD/MM/AAAA" em vários lugares (funil.json,
client_map, retorno do Microvix). Isso já causou TRÊS bugs latentes da mesma
classe, todos por tratar essas datas de forma ingênua:

  * FUNIL-1   (modules/funil.py, resumo_funil): filtra período comparando as
              strings "DD/MM/AAAA" diretamente (`v["data"] >= dt_ini`). Comparar
              "DD/MM/AAAA" como texto NÃO é cronológico — "05/01/2026" < "10/12/2025"
              como string, embora seja depois no calendário.
  * POSVENDA-2 (modules/pos_venda.py, scan_from_retorno): `pd.to_datetime(...)`
              sem `dayfirst=True` interpreta "02/06/2026" como 6 de fevereiro
              quando o dia <= 12.

Este módulo centraliza a conversão correta, em STDLIB pura (sem pandas), para
que os fixes acima possam importar uma única implementação testada em vez de
re-derivar a lógica.

Importante: módulo PURO — sem I/O, sem rede, sem estado global. NÃO é importado
pelo app em produção; é uma peça pronta para ser ligada quando o app estiver
parado (tarefas FUNIL-1 / POSVENDA-2). Seguro de adicionar a qualquer momento.
"""

from __future__ import annotations

from datetime import date, datetime

# Textos que aparecem nos dados como "sem data" e devem virar None,
# nunca uma data espúria. (placeholders vistos nas auditorias noturnas)
_PLACEHOLDERS = {"", "-", "—", "--", "0", "00/00/0000", "0000-00-00", "none", "nan", "nat"}

# Pivot de século para anos de 2 dígitos: 00-69 -> 2000-2069, 70-99 -> 1970-1999.
_YY_PIVOT = 70


def parse_br_date(value) -> "date | None":
    """
    Converte um valor em datetime.date, ou None se não for uma data válida.

    Aceita (nessa ordem de tentativa), sempre com semântica DIA-PRIMEIRO:
      * objetos date/datetime (retorna a parte date)
      * "DD/MM/AAAA"  e  "DD/MM/AA"   (com '/' ou '-' como separador)
      * "AAAA-MM-DD"  (ISO — desambiguado por ter 4 dígitos no 1º campo)

    Placeholders ("", "-", "—", "00/00/0000"...) e lixo -> None.
    Nunca levanta exceção; entrada inválida sempre vira None.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    s = str(value).strip()
    if s == "" or s.lower() in _PLACEHOLDERS:
        return None

    # ISO "AAAA-MM-DD" (e variações com horário): 1º campo com 4 dígitos.
    iso_head = s.split("T")[0].split(" ")[0]
    if len(iso_head) >= 8 and iso_head[:4].isdigit() and ("-" in iso_head):
        parts = iso_head.split("-")
        if len(parts) == 3 and len(parts[0]) == 4:
            d = _build(parts[2], parts[1], parts[0])
            if d is not None:
                return d

    # DD/MM/AAAA ou DD-MM-AAAA (dia primeiro)
    sep = "/" if "/" in s else ("-" if "-" in s else None)
    if sep is None:
        return None
    parts = s.split(sep)
    if len(parts) != 3:
        return None
    dd, mm, yy = parts[0].strip(), parts[1].strip(), parts[2].strip()
    # ano de 2 dígitos -> aplica pivot
    if len(yy) == 2 and yy.isdigit():
        n = int(yy)
        yy = str((2000 + n) if n < _YY_PIVOT else (1900 + n))
    return _build(dd, mm, yy)


def _build(dd: str, mm: str, yyyy: str) -> "date | None":
    """Monta um date a partir de componentes texto; None se inválido."""
    if not (dd.isdigit() and mm.isdigit() and yyyy.isdigit()):
        return None
    try:
        return date(int(yyyy), int(mm), int(dd))
    except ValueError:
        return None


def to_iso(value) -> str:
    """
    Retorna "AAAA-MM-DD" (ordenável cronologicamente como texto) ou "" se inválida.

    É a peça-chave para o fix do FUNIL-1: comparar to_iso(a) >= to_iso(b) é
    cronologicamente correto, ao contrário de comparar "DD/MM/AAAA" como string.
    """
    d = parse_br_date(value)
    return d.isoformat() if d is not None else ""


def cmp_br(a, b) -> int:
    """
    Compara duas datas BR cronologicamente: -1 se a<b, 0 se iguais, 1 se a>b.
    Datas inválidas/None ordenam ANTES de qualquer data válida (e empatam entre si).
    """
    da, db = parse_br_date(a), parse_br_date(b)
    if da is None and db is None:
        return 0
    if da is None:
        return -1
    if db is None:
        return 1
    return (da > db) - (da < db)


def in_range(value, dt_ini="", dt_fim="") -> bool:
    """
    True se `value` cai no intervalo [dt_ini, dt_fim] (inclusivo), cronologicamente.
    Limites vazios = aberto daquele lado. Valor inválido -> False.

    É o predicado exato que resumo_funil() precisa para corrigir o FUNIL-1:
        visitas = [v for v in visitas if in_range(v.get("data"), dt_ini, dt_fim)]
    """
    d = parse_br_date(value)
    if d is None:
        return False
    if dt_ini:
        ini = parse_br_date(dt_ini)
        if ini is not None and d < ini:
            return False
    if dt_fim:
        fim = parse_br_date(dt_fim)
        if fim is not None and d > fim:
            return False
    return True


def days_between(a, b) -> "int | None":
    """Número de dias de `a` até `b` (b - a). None se qualquer data for inválida."""
    da, db = parse_br_date(a), parse_br_date(b)
    if da is None or db is None:
        return None
    return (db - da).days


def to_br(value) -> str:
    """Normaliza qualquer entrada de data para "DD/MM/AAAA" canônico, ou "" se inválida."""
    d = parse_br_date(value)
    return d.strftime("%d/%m/%Y") if d is not None else ""
