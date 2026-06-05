"""
sync_queue.py — Fila de sincronização resiliente para Supabase.

Quando o Supabase fica temporariamente inacessível, as escritas ficam em
fila local (_sync_queue.json em /tmp/pepper-data/) e são enviadas
silenciosamente na próxima vez que a conexão for restaurada.

Princípios:
  • Silencioso  — nenhum erro ou aviso exibido ao usuário durante a falha
  • Não-bloqueante — flush acontece no início de cada render, custa milissegundos
                     se a fila estiver vazia (apenas lê um arquivo pequeno)
  • Deduplicado — novo write no mesmo arquivo substitui a entrada anterior
  • Persistente — sobrevive a page refreshes (arquivo em /tmp, não session state)
  • Autolimitado — máximo de 100 entradas; itens com >24h são descartados
  • Rate-limited — flush tentado no máximo 1× a cada 30 segundos para não
                   adicionar latência em toda renderização

Uso (automático via cloud_storage.save_json):
  Se o upload ao Supabase falhar, cloud_storage chama enqueue() automaticamente.
  O flush é executado em app.py no início de cada render.
"""

import json
import os
from datetime import datetime, timedelta

_QUEUE_FILE  = "_sync_queue.json"
_MAX_ITEMS   = 100          # limite máximo de entradas na fila
_MAX_AGE_H   = 24           # descarta itens com mais de 24 horas
_FLUSH_COOLDOWN_S = 30      # aguarda 30s entre tentativas de flush consecutivas


# ── Helpers de caminho ────────────────────────────────────────────────────────

def _q_path() -> str:
    """Caminho do arquivo de fila (em /tmp no cloud, em data/ localmente)."""
    try:
        from modules.data_dir import data_path
        return data_path(_QUEUE_FILE)
    except Exception:
        return os.path.join("/tmp", _QUEUE_FILE)


# ── Leitura / escrita da fila ─────────────────────────────────────────────────

def _load_queue() -> list:
    """Lê a fila do disco. Descarta entradas expiradas. Retorna [] em qualquer erro."""
    path = _q_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            q = json.load(f)
        if not isinstance(q, list):
            return []
        # Descarta itens mais velhos que _MAX_AGE_H
        cutoff = (datetime.now() - timedelta(hours=_MAX_AGE_H)).isoformat()
        return [item for item in q if isinstance(item, dict) and item.get("ts", "") >= cutoff]
    except Exception:
        return []


def _save_queue(q: list) -> None:
    """Grava a fila no disco. Silencioso em caso de erro."""
    try:
        path = _q_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(q, f, ensure_ascii=False)
    except Exception:
        pass


# ── API pública ───────────────────────────────────────────────────────────────

def enqueue(filename: str, data) -> None:
    """
    Adiciona um arquivo à fila de sync.
    Chamado automaticamente por cloud_storage.save_json() quando o Supabase
    não está acessível.
    """
    try:
        q = _load_queue()
        # Dedup: substitui entrada anterior do mesmo arquivo pelo dado mais recente
        q = [item for item in q if item.get("filename") != filename]
        q.append({
            "filename": filename,
            "data":     data,
            "ts":       datetime.now().isoformat(),
        })
        # Garante limite de tamanho (mantém os mais recentes)
        if len(q) > _MAX_ITEMS:
            q = q[-_MAX_ITEMS:]
        _save_queue(q)
    except Exception:
        pass  # nunca propaga exceção para não impactar o fluxo principal


def flush_queue() -> int:
    """
    Tenta enviar todos os itens pendentes ao Supabase.
    Retorna o número de itens enviados com sucesso.
    Completamente silencioso — nunca lança exceções.
    """
    sent = 0
    try:
        from modules.cloud_storage import _is_cloud, _get_supabase, _loja_prefix
        if not _is_cloud():
            return 0  # modo local: fila não é usada

        q = _load_queue()
        if not q:
            return 0  # fila vazia: retorna imediatamente

        sb, bucket = _get_supabase()
        prefix = _loja_prefix()

        remaining = []
        for item in q:
            fname = item.get("filename", "")
            idata = item.get("data")
            if not fname or idata is None:
                continue  # entrada malformada: descarta
            try:
                content = json.dumps(idata, ensure_ascii=False, indent=2).encode("utf-8")
                sb.storage.from_(bucket).upload(
                    prefix + fname,
                    content,
                    {"upsert": "true", "content-type": "application/json"},
                )
                sent += 1
            except Exception:
                remaining.append(item)  # ainda inacessível: mantém na fila

        _save_queue(remaining)
    except Exception:
        pass  # Supabase ainda down: próxima tentativa no próximo render

    return sent


def maybe_flush(session_state) -> int:
    """
    Versão rate-limited do flush: executa no máximo a cada _FLUSH_COOLDOWN_S segundos.
    Recebe st.session_state como parâmetro (evita import circular de streamlit aqui).
    Retorna itens enviados (0 na maioria dos renders — sem custo).
    """
    import time

    # Verifica cooldown
    _last = session_state.get("_sq_last_flush_ts", 0.0)
    _now  = time.time()
    if _now - _last < _FLUSH_COOLDOWN_S:
        return 0  # ainda dentro da janela de cooldown: pula

    # Verifica se há algo na fila antes de abrir conexão
    if queue_size() == 0:
        session_state["_sq_last_flush_ts"] = _now
        return 0  # fila vazia: atualiza timestamp e retorna

    # Há itens: tenta flush
    sent = flush_queue()
    session_state["_sq_last_flush_ts"] = _now
    return sent


def queue_size() -> int:
    """Retorna quantos arquivos estão pendentes de sync. Rápido (só lê um arquivo)."""
    try:
        return len(_load_queue())
    except Exception:
        return 0
