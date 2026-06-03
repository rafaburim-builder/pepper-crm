"""
_migrate_to_cloud.py — Sobe todos os dados locais para o Supabase Storage.
Execute UMA ÚNICA VEZ para a migração inicial.

Uso:
  venv\\Scripts\\python.exe _migrate_to_cloud.py

Preencha as variáveis abaixo com os dados do seu projeto Supabase.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── PREENCHA AQUI ──────────────────────────────────────────────────────────
SUPABASE_URL    = ""   # https://xxxxx.supabase.co
SUPABASE_KEY    = ""   # anon public key
BUCKET          = "pepper-data"
LOJA_ID         = "porto_ferreira"
# ──────────────────────────────────────────────────────────────────────────

ROOT = os.path.dirname(os.path.abspath(__file__))

FILES = [
    "client_map.json", "product_map.json", "produto_map_meta.json",
    "familias.json", "loja_config.json", "qualidade_alertas.json",
    "fornecedor_lentes.json", "prescricoes.json", "funil.json",
    "email_queue.json", "lgpd_optout.json", "users.json",
]

def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERRO: Preencha SUPABASE_URL e SUPABASE_KEY no script.")
        sys.exit(1)

    try:
        from supabase import create_client
    except ImportError:
        print("ERRO: Execute: venv\\Scripts\\pip install supabase")
        sys.exit(1)

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    ok = err = 0
    for fname in FILES:
        path = os.path.join(ROOT, "data", fname)
        if not os.path.exists(path):
            print(f"  SKIP (não existe): {fname}")
            continue
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            obj_path = f"{LOJA_ID}/{fname}"
            sb.storage.from_(BUCKET).upload(
                obj_path,
                content.encode("utf-8"),
                {"upsert": "true", "content-type": "application/json"},
            )
            size = len(content)
            print(f"  OK: {fname} ({size:,} bytes)".replace(",", "."))
            ok += 1
        except Exception as e:
            print(f"  ERRO: {fname} — {e}")
            err += 1

    print(f"\nMigração concluída: {ok} OK | {err} erros")
    if err == 0:
        print("Todos os dados foram enviados para o Supabase.")
        print("Próximo passo: deploy no Streamlit Cloud.")

if __name__ == "__main__":
    main()
