"""
client_map.py — Import and persist client data from Microvix CSV export.

Formato esperado ("Relatório clientes/fornecedores" do Microvix):
  Encoding  : UTF-8 com BOM (utf-8-sig)
  Delimitador: ponto-e-vírgula (;)
  Colunas   : Cod;Nome/Razão Social;Nome Fantasia;CPF/CNPJ;CEP;End.;Nº;Compl.;Bairro;
              Cidade;UF;País;Tel.;Cel.;Email;Cliente Desde;Último Prod.;
              Tipo de Cliente;Data de Nascimento
"""
import csv
import io
import json
import os
import unicodedata
from datetime import datetime

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FILE = os.path.join(_BASE, "data", "client_map.json")
_META_FILE = os.path.join(_BASE, "data", "client_meta.json")

_SKIP_NAMES = {
    "CONSUMIDOR FINAL", "REDECARD ADM DE CARTOES",
    "CLIENTE USADO PARA DEMONSTRACAO", "TESTE SP",
}


def _norm_key(s: str) -> str:
    s = s.strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _title_case(s: str) -> str:
    if not s:
        return s
    if not s.isupper() and not s.islower():
        return s
    return s.title()


def _parse_month(date_str: str) -> int | None:
    """Extrai mês (1–12) de uma string de data. Retorna None se inválida."""
    if not date_str:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).month
        except ValueError:
            continue
    return None


def _parse_date_str(date_str: str) -> str:
    """Normaliza string de data para DD/MM/YYYY. Retorna original se não reconhecida."""
    if not date_str:
        return ""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return date_str.strip()


def load_clients() -> dict:
    """Carrega o mapa de clientes do disco.
    Retorna {codigo_str: {nome, fone, email, cidade, uf, aniversario, cliente_desde}}."""
    if os.path.exists(_FILE):
        with open(_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_client_meta() -> dict:
    """Carrega metadados da última importação de clientes.
    Retorna {imported_at, total, newest_client_date} ou {}."""
    if os.path.exists(_META_FILE):
        try:
            with open(_META_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_clients(cmap: dict) -> None:
    os.makedirs(os.path.dirname(_FILE), exist_ok=True)
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(cmap, f, ensure_ascii=False, indent=2)


def import_from_api_data(clients: dict) -> dict:
    """Persiste clientes vindos de LinxClientes (via MicrovixAPI.get_clients_api()).

    Salva client_map.json + client_meta.json com source='api'.
    Retorna o próprio dict recebido.
    """
    save_clients(clients)

    _dates = []
    for v in clients.values():
        _ds = v.get("cliente_desde", "")
        if _ds:
            try:
                _dates.append(datetime.strptime(_ds, "%d/%m/%Y"))
            except ValueError:
                continue

    newest_date_str = max(_dates).strftime("%d/%m/%Y") if _dates else ""

    meta = {
        "imported_at":        datetime.now().strftime("%d/%m/%Y %H:%M"),
        "total":              len(clients),
        "newest_client_date": newest_date_str,
        "source":             "api",
    }
    os.makedirs(os.path.dirname(_META_FILE), exist_ok=True)
    with open(_META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return clients


def import_from_csv(file_bytes: bytes) -> dict:
    """Parseia o CSV de clientes exportado do Microvix e persiste localmente.
    Também salva metadados em client_meta.json.
    Retorna {codigo_str: {nome, fone, email, cidade, uf, aniversario, cliente_desde}}."""
    for enc in ("utf-8-sig", "utf-8", "windows-1252"):
        try:
            text = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = file_bytes.decode("latin-1", errors="replace")

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    fieldnames = reader.fieldnames or []
    col = {_norm_key(c): c for c in fieldnames}

    cod_col       = col.get("cod", list(col.values())[0] if col else "")
    nome_col      = col.get("nome/razao social", col.get("nome/razao", ""))
    cel_col       = col.get("cel.", "")
    tel_col       = col.get("tel.", "")
    email_col     = col.get("email", "")
    cidade_col    = col.get("cidade", "")
    uf_col        = col.get("uf", "")
    tipo_col      = col.get("tipo de cliente", "")
    nasc_col      = col.get("data de nascimento", "")
    desde_col     = col.get("cliente desde", "")

    clients: dict = {}
    for row in reader:
        codigo = row.get(cod_col, "").strip()
        if not codigo or not codigo.isdigit():
            continue

        tipo = row.get(tipo_col, "C").strip().upper() if tipo_col else "C"
        if tipo not in ("C", ""):
            continue  # pula fornecedores (F)

        nome = row.get(nome_col, "").strip() if nome_col else ""
        if not nome or len(nome) < 3:
            continue
        nome_upper = unicodedata.normalize("NFD", nome.upper())
        nome_upper = "".join(c for c in nome_upper if unicodedata.category(c) != "Mn")
        if nome_upper in _SKIP_NAMES:
            continue

        fone   = (row.get(cel_col, "").strip() if cel_col else "") or \
                 (row.get(tel_col, "").strip() if tel_col else "")
        email  = row.get(email_col, "").strip() if email_col else ""
        cidade = row.get(cidade_col, "").strip() if cidade_col else ""
        uf     = row.get(uf_col, "").strip().upper() if uf_col else ""

        # Mês de nascimento (1–12 ou None)
        nasc_str   = row.get(nasc_col, "").strip() if nasc_col else ""
        aniversario = _parse_month(nasc_str)

        # Data de cadastro normalizada
        desde_raw    = row.get(desde_col, "").strip() if desde_col else ""
        cliente_desde = _parse_date_str(desde_raw)

        clients[codigo] = {
            "nome":          _title_case(nome),
            "fone":          fone,
            "email":         email,
            "cidade":        _title_case(cidade),
            "uf":            uf,
            "aniversario":   aniversario,
            "nascimento":    _parse_date_str(nasc_str),
            "cliente_desde": cliente_desde,
        }

    # Calcula data do cliente mais recente cadastrado
    _dates = []
    for v in clients.values():
        _ds = v.get("cliente_desde", "")
        if _ds:
            for _fmt in ("%d/%m/%Y",):
                try:
                    _dates.append(datetime.strptime(_ds, _fmt))
                    break
                except ValueError:
                    continue

    newest_date_str = max(_dates).strftime("%d/%m/%Y") if _dates else ""

    # Persiste clientes e metadados
    save_clients(clients)

    meta = {
        "imported_at":       datetime.now().strftime("%d/%m/%Y %H:%M"),
        "total":             len(clients),
        "newest_client_date": newest_date_str,
    }
    os.makedirs(os.path.dirname(_META_FILE), exist_ok=True)
    with open(_META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return clients
