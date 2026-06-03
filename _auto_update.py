"""
_auto_update.py — Verifica atualizacoes das bibliotecas do Pepper.
Executado todo dia as 02:00 pelo Agendador de Tarefas do Windows.

29/05/2026 (builder) — MUDANCA DE SEGURANCA (supply chain):
  Antes este script INSTALAVA automaticamente, via pip, a versao mais nova do
  PyPI. Instalar releases novas sem revisao e um risco de cadeia de suprimento
  (um pacote comprometido entraria sozinho na maquina da loja). Agora o script
  e NOTIFY-ONLY: apenas DETECTA e REGISTRA as atualizacoes disponiveis para
  REVISAO/INSTALACAO MANUAL. Nada e instalado automaticamente.

Comportamento (notify-only):
  1. Le requirements.txt e extrai versoes atuais.
  2. Consulta o PyPI para cada pacote e verifica se ha versao mais nova.
  3. Registra as pendentes em data/update_log.json (o app mostra na sidebar).
  4. NAO instala, NAO altera requirements.txt. A instalacao e decisao humana:
       venv\\Scripts\\python -m pip install <pacote>==<versao>
     e depois validar o app e atualizar requirements.txt manualmente.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from urllib import request as _req

ROOT = os.path.dirname(os.path.abspath(__file__))
REQ  = os.path.join(ROOT, "requirements.txt")
LOG  = os.path.join(ROOT, "data", "update_log.json")

# SEGURANCA: instalacao automatica DESLIGADA (anti supply-chain).
# Mantido como interruptor caso um humano decida reativar conscientemente.
AUTO_INSTALL = False

# Pacotes que NUNCA devem ser atualizados sem revisao manual.
# Versoes major costumam quebrar APIs (ex: pandas 2->3, streamlit 1->2).
SAFE_MINOR_ONLY = {"pandas", "numpy", "streamlit", "plotly"}


def _log(entries: list):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    try:
        with open(LOG, encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        history = []
    history = (entries + history)[:60]   # ultimas 60 entradas
    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _parse_req() -> dict:
    """Retorna {pacote: versao_atual} para linhas com == fixo."""
    pkgs = {}
    with open(REQ, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([A-Za-z0-9_\-]+)==([^\s#]+)", line)
            if m:
                pkgs[m.group(1).lower()] = m.group(2)
    return pkgs


def _latest_version(pkg: str) -> str | None:
    """Consulta o PyPI e retorna a ultima versao estavel do pacote."""
    try:
        url = f"https://pypi.org/pypi/{pkg}/json"
        with _req.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        return data["info"]["version"]
    except Exception:
        return None


def _is_safe_update(pkg: str, current: str, latest: str) -> bool:
    """Para pacotes sensiveis, so atualiza dentro do mesmo major/minor."""
    def parts(v):
        return [int(x) for x in re.findall(r"\d+", v)]
    cur = parts(current); lat = parts(latest)
    if pkg in SAFE_MINOR_ONLY:
        # major deve ser igual; minor pode subir
        return len(cur) >= 1 and len(lat) >= 1 and cur[0] == lat[0]
    return True   # outros pacotes: atualiza livremente


def _pip_install(pkg: str, version: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", f"{pkg}=={version}", "--quiet"],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def run():
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"[{now_str}] Verificando atualizacoes (notify-only)...")

    pkgs = _parse_req()
    if not pkgs:
        _log([{"data": now_str, "status": "sem_pacotes", "msg": "Nenhum pacote fixo encontrado"}])
        return

    pendentes = []
    erros     = []

    for pkg, current in pkgs.items():
        latest = _latest_version(pkg)
        if latest is None:
            erros.append(pkg)
            continue
        if latest == current:
            continue
        # Ha versao mais nova — REGISTRA como pendente (nao instala).
        pendentes.append({
            "pacote": pkg, "atual": current, "disponivel": latest,
            "tipo": "segura" if _is_safe_update(pkg, current, latest) else "major",
            "motivo": "revisar e instalar manualmente (auto-install desativado por seguranca)",
        })
        print(f"  PENDENTE {pkg} {current} -> {latest}")

    # SEGURANCA: nada e instalado automaticamente; requirements.txt nao e alterado.
    if AUTO_INSTALL:
        print("  AVISO: AUTO_INSTALL=True — instalacao automatica reativada manualmente.")

    entry = {
        "data": now_str,
        "status": "ok" if not erros else "parcial",
        "modo": "notify-only",
        "atualizados": [],                 # nunca instala sozinho
        "ignorados_major": pendentes,      # compat. com o widget da sidebar
        "erros": erros,
        "verificados": len(pkgs),
    }
    _log([entry])

    if pendentes:
        print(f"  {len(pendentes)} atualizacao(oes) pendente(s) para revisao manual.")
    elif not erros:
        print("  Tudo atualizado. Nenhuma novidade.")
    print("Concluido.")


def run_email_queue():
    """Drena a fila de e-mails agendados (chamado pelo job das 02h)."""
    try:
        sys.path.insert(0, ROOT)
        from modules.email_queue import process_queue, queue_size
        n = queue_size()
        if n == 0:
            print("[email] Fila vazia.")
            return
        print(f"[email] Processando {n} e-mail(s) agendados...")
        result = process_queue()
        print(f"[email] Enviados: {result['enviados']} | Falhas: {result['falhas']}")
        for e in result["erros"][:5]:
            print(f"  ERRO: {e}")
    except Exception as ex:
        print(f"[email] ERRO ao processar fila: {ex}")


if __name__ == "__main__":
    run()
    run_email_queue()
