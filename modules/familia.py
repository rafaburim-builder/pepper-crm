"""
familia.py — Módulo de Família/Parentes.

Agrupa clientes que compartilham telefone ou e-mail em núcleos familiares.
Para cada família, define um único receptor de mensagens (evita spam de campanha).

Regra padrão de receptor:
  1. Se houver designação manual: usa ela.
  2. Caso contrário: homem mais velho (maior ano de nascimento invertido = mais velho).
  3. Se empate ou sem data: primeiro da lista por ordem alfabética.

Armazena em data/familias.json:
  {
    "fam_abc12": {
      "id": "fam_abc12",
      "tipo_vinculo":  "telefone" | "email",
      "valor_vinculo": "19999999999",
      "membros": ["cod_A", "cod_B", ...],
      "receptor_padrao": "cod_A",    # determinado pela regra
      "receptor_manual": "cod_B",    # sobrescreve o padrão se definido
      "criado_em": "DD/MM/AAAA",
      "observacao": ""
    }
  }
"""
import json
import os
import uuid
from datetime import date
from typing import Optional

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH = os.path.join(ROOT, "data", "familias.json")


def _load() -> dict:
    if not os.path.exists(_PATH):
        return {}
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _escolher_receptor_padrao(codigos: list, client_map: dict) -> str:
    """
    Aplica a regra de receptor padrão:
      Prioridade 1 → homem mais velho
      Prioridade 2 → qualquer pessoa mais velha
      Prioridade 3 → primeiro na ordem alfabética pelo nome
    """
    if not codigos:
        return ""
    if len(codigos) == 1:
        return codigos[0]

    candidatos = []
    for cod in codigos:
        info = client_map.get(str(cod), {})
        nome = info.get("nome", "") or ""
        nasc = info.get("nascimento", "") or ""
        # Extrai ano de nascimento
        ano_nasc = 0
        if nasc and "/" in nasc:
            partes = nasc.split("/")
            if len(partes) == 3:
                try:
                    ano_nasc = int(partes[2])
                except ValueError:
                    pass
        # Detecta gênero pelo nome (heurística simples — terminações masculinas)
        nome_lower = nome.lower().split()[0] if nome.lower().split() else ""
        is_male = (
            nome_lower.endswith("o") or nome_lower.endswith("os")
            or nome_lower in {"jose","joao","carlos","luis","luiz","antonio","francisco",
                               "pedro","paulo","marcos","rafael","julio","roberto",
                               "sergio","andre","wagner","diego","gabriel","lucas",
                               "matheus","samuel","douglas","rodrigo","fabio","mario",
                               "marcio","clesio","alan","ivan","alex","anderson"}
        )
        candidatos.append({
            "cod": cod, "nome": nome,
            "ano_nasc": ano_nasc,
            "is_male": is_male,
        })

    # Ordena: masculino + mais velho + nome
    candidatos.sort(key=lambda c: (
        0 if c["is_male"] else 1,       # masculino primeiro
        -c["ano_nasc"] if c["ano_nasc"] else 9999,  # mais velho (menor ano = mais velho)
        c["nome"],
    ))
    return candidatos[0]["cod"]


def get_receptor(codigo_cliente: str) -> str:
    """
    Retorna o receptor de mensagens do cliente.
    Se o cliente estiver numa família, retorna o receptor definido para ela.
    Caso contrário, retorna o próprio código do cliente.
    """
    familias = _load()
    for fam in familias.values():
        if str(codigo_cliente) in fam.get("membros", []):
            return fam.get("receptor_manual") or fam.get("receptor_padrao") or codigo_cliente
    return codigo_cliente


def is_receptor(codigo_cliente: str) -> bool:
    """True se este cliente é o receptor da sua família (ou não tem família)."""
    return get_receptor(str(codigo_cliente)) == str(codigo_cliente)


def get_familia_do_cliente(codigo: str) -> Optional[dict]:
    """Retorna a família do cliente ou None."""
    familias = _load()
    for fam in familias.values():
        if str(codigo) in fam.get("membros", []):
            return fam
    return None


def criar_ou_atualizar_familia(
    codigos: list,
    tipo_vinculo: str,      # "telefone" | "email"
    valor_vinculo: str,
    client_map: dict,
    receptor_manual: str = "",
    observacao: str = "",
) -> str:
    """
    Cria ou atualiza um núcleo familiar.
    Retorna o ID da família.
    """
    familias = _load()

    # Verifica se já existe família com este vínculo
    fam_id = None
    for fid, fam in familias.items():
        if fam.get("tipo_vinculo") == tipo_vinculo and fam.get("valor_vinculo") == valor_vinculo:
            fam_id = fid
            break

    receptor_padrao = _escolher_receptor_padrao(codigos, client_map)

    if fam_id:
        # Atualiza membros
        familias[fam_id]["membros"]         = list(set(codigos))
        familias[fam_id]["receptor_padrao"] = receptor_padrao
        if receptor_manual:
            familias[fam_id]["receptor_manual"] = receptor_manual
        if observacao:
            familias[fam_id]["observacao"] = observacao
    else:
        fam_id = "fam_" + uuid.uuid4().hex[:8]
        familias[fam_id] = {
            "id":             fam_id,
            "tipo_vinculo":   tipo_vinculo,
            "valor_vinculo":  valor_vinculo,
            "membros":        list(set(codigos)),
            "receptor_padrao": receptor_padrao,
            "receptor_manual": receptor_manual,
            "criado_em":      date.today().strftime("%d/%m/%Y"),
            "observacao":     observacao,
        }

    _save(familias)
    return fam_id


def definir_receptor_manual(fam_id: str, codigo_receptor: str) -> bool:
    """Define manualmente o receptor de uma família."""
    familias = _load()
    if fam_id not in familias:
        return False
    if codigo_receptor not in familias[fam_id].get("membros", []):
        return False
    familias[fam_id]["receptor_manual"] = codigo_receptor
    _save(familias)
    return True


def detectar_familias_da_base(client_map: dict, threshold: int = 2) -> int:
    """
    Varre o client_map e cria famílias para todos os grupos que compartilham
    telefone ou e-mail (>= threshold membros).
    Retorna o número de famílias criadas/atualizadas.
    """
    from modules.marketing import normalize_phone
    from collections import defaultdict

    por_fone  = defaultdict(list)
    por_email = defaultdict(list)

    for cod, info in client_map.items():
        fone = normalize_phone(info.get("fone", "") or "", "")
        if fone:
            por_fone[fone].append(cod)
        email = (info.get("email", "") or "").lower().strip()
        if email and "@" in email:
            por_email[email].append(cod)

    n = 0
    for fone, codigos in por_fone.items():
        if len(codigos) >= threshold:
            criar_ou_atualizar_familia(codigos, "telefone", fone, client_map)
            n += 1
    for email, codigos in por_email.items():
        if len(codigos) >= threshold:
            # Evita criar família para e-mails de loja / placeholder
            from modules.loja_config import is_telefone_bloqueado
            criar_ou_atualizar_familia(codigos, "email", email, client_map)
            n += 1
    return n


def listar_familias(client_map: dict) -> list:
    """Retorna lista de famílias enriquecida com nomes dos membros."""
    familias = _load()
    result = []
    for fam in familias.values():
        membros_info = []
        for cod in fam.get("membros", []):
            info = client_map.get(str(cod), {})
            receptor_atual = fam.get("receptor_manual") or fam.get("receptor_padrao")
            membros_info.append({
                "codigo":    cod,
                "nome":      info.get("nome", f"Cliente #{cod}"),
                "receptor":  cod == receptor_atual,
            })
        result.append({**fam, "membros_info": membros_info})
    return result
