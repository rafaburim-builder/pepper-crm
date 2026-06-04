"""
_sync_now.py - Sobe arquivos de dados locais para o Supabase (via REST direto).
Execute: python _sync_now.py
"""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))

# Le credenciais
try:
    import tomllib
except ImportError:
    import tomli as tomllib

with open(os.path.join(ROOT, ".streamlit", "secrets.toml"), "rb") as f:
    secrets = tomllib.load(f)

URL    = secrets["supabase"]["url"].rstrip("/")
KEY    = secrets["supabase"]["key"]
BUCKET = secrets["supabase"]["bucket"]
LOJA   = secrets["app"]["loja_id"]

import urllib.request, urllib.error

def upload(filename, content_bytes):
    obj_path = f"{LOJA}/{filename}"
    api_url  = f"{URL}/storage/v1/object/{BUCKET}/{obj_path}"
    req = urllib.request.Request(
        api_url,
        data    = content_bytes,
        method  = "POST",
        headers = {
            "Authorization":  f"Bearer {KEY}",
            "apikey":         KEY,
            "Content-Type":   "application/json",
            "x-upsert":       "true",
        },
    )
    import ssl
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

FILES = [
    "users.json",
    "profiles.json",
    "stores.json",
    "redes.json",
    "remember.json",
]

print("Sincronizando com Supabase...")
ok = 0
for filename in FILES:
    path = os.path.join(ROOT, "data", filename)
    if not os.path.exists(path):
        print(f"  [SKIP] {filename} - nao encontrado localmente")
        continue
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    status, body = upload(filename, content)
    if status in (200, 201):
        print(f"  [OK]   {filename}")
        ok += 1
    else:
        print(f"  [ERRO] {filename} - HTTP {status}: {body[:120]}")

print(f"\nConcluido: {ok} arquivo(s) enviado(s).")
