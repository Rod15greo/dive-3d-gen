"""
CLI para gerenciar API keys do Dive 3D Gen.

Uso (rode sempre com `modal run`):
  modal run scripts/manage_keys.py::create_key --name "Rodrigo"
  modal run scripts/manage_keys.py::list_keys
  modal run scripts/manage_keys.py::revoke_key --key "abc123..."
"""

import secrets
from datetime import datetime

import modal

app = modal.App("dive-3d-gen")
api_keys_store = modal.Dict.from_name("dive-3d-gen-api-keys", create_if_missing=True)


@app.local_entrypoint()
def create_key(name: str = "default"):
    """Cria uma nova API key e imprime na tela."""
    key = secrets.token_hex(24)  # 48 caracteres hex
    api_keys_store[key] = {
        "name": name,
        "created_at": datetime.utcnow().isoformat(),
        "requests": 0,
        "active": True,
    }
    print(f"\n✅ API Key criada para '{name}':")
    print(f"   {key}\n")
    print("Guarde com segurança — não será exibida novamente.")


@app.local_entrypoint()
def list_keys():
    """Lista todas as API keys ativas."""
    print("\n📋 API Keys cadastradas:\n")
    for key, meta in api_keys_store.items():
        status = "✅ ativa" if meta.get("active", True) else "❌ revogada"
        print(f"  {key[:8]}...  | {meta['name']:<20} | {meta['created_at'][:10]} | {meta['requests']} req | {status}")
    print()


@app.local_entrypoint()
def revoke_key(key: str):
    """Revoga uma API key (mantém no histórico mas bloqueia acesso)."""
    if key not in api_keys_store:
        print(f"❌ Key não encontrada: {key}")
        return
    entry = api_keys_store[key]
    entry["active"] = False
    api_keys_store[key] = entry
    print(f"✅ Key revogada: {key[:8]}... ({entry['name']})")


@app.local_entrypoint()
def delete_key(key: str):
    """Remove permanentemente uma API key."""
    if key not in api_keys_store:
        print(f"❌ Key não encontrada: {key}")
        return
    name = api_keys_store[key].get("name", "?")
    del api_keys_store[key]
    print(f"🗑  Key removida: {key[:8]}... ({name})")
