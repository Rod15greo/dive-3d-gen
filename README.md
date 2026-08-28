# Dive 3D Gen

Geração de assets 3D diretamente no Unity Editor via IA.  
Envie um texto ou imagem — receba um `.glb` pronto pra cena em segundos.

**Modelos suportados:**

| Modelo | Entrada | Velocidade | Qualidade |
|---|---|---|---|
| **SF3D** (Stability AI) | Imagem | ~0.5 s | Boa — PBR limpo |
| **TRELLIS** (Microsoft) | Imagem ou Texto | ~60–90 s | Ótima topologia |
| **Hunyuan3D-2GP** (Tencent) | Imagem ou Texto | ~20–60 s | Melhor PBR |

---

## Estrutura

```
dive-3d-gen/
├── server/
│   ├── main.py          ← Servidor Modal (FastAPI + GPU A10G)
│   ├── models/
│   │   ├── sf3d.py      ← Wrapper Stable Fast 3D
│   │   ├── trellis.py   ← Wrapper TRELLIS
│   │   └── hunyuan.py   ← Wrapper Hunyuan3D-2GP
│   └── requirements.txt
├── scripts/
│   └── manage_keys.py   ← CLI para criar/revogar API keys
└── unity-plugin/
    └── com.dive.3dgen/  ← Package UPM para Unity 6
        ├── Editor/      ← Janela do editor (Tools → Dive 3D Gen)
        └── Runtime/     ← Cliente HTTP + importador GLB
```

---

## 1. Deploy do servidor (Modal.com)

### Pré-requisitos
```bash
pip install modal
modal token new     # faz login na sua conta modal.com
```

### Criar o secret com a chave admin
```bash
modal secret create dive-3d-gen-secrets ADMIN_SECRET=sua_senha_aqui
```

### Deploy
```bash
cd server
modal deploy main.py
```

O Modal vai exibir a URL pública, ex:  
`https://rod15greo--dive-3d-gen-serve.modal.run`

### Criar API keys para os usuários
```bash
# Cria uma key para você
modal run scripts/manage_keys.py::create_key --name "Rodrigo"

# Lista todas as keys
modal run scripts/manage_keys.py::list_keys

# Revoga uma key
modal run scripts/manage_keys.py::revoke_key --key "abc123..."
```

---

## 2. Instalar o plugin no Unity 6

1. No Unity, vá em **Window → Package Manager**
2. Clique em **+** → **Add package from disk…**
3. Selecione `unity-plugin/com.dive.3dgen/package.json`
4. O GLTFast será instalado automaticamente como dependência

### Configurar
1. Vá em **Tools → Dive 3D Gen**
2. Cole a **Server URL** (a URL do Modal)
3. Cole a sua **API Key**

### Usar
1. Escolha o modelo e a qualidade
2. Digite um prompt **ou** arraste uma imagem de referência
3. Clique em **⚡ Gerar 3D**
4. O `.glb` é salvo em `Assets/Dive3DGen/Generated/`
5. Clique em **➕ Instanciar na cena**

---

## 3. API REST (para integração direta)

### Gerar um asset
```http
POST /generate
X-API-Key: sua-key-aqui
Content-Type: multipart/form-data

model=sf3d          # sf3d | trellis | hunyuan
quality=balanced    # fast | balanced | high
prompt=wooden barrel
image=<arquivo>     # opcional
```
Resposta:
```json
{ "job_id": "fc-abc123", "status": "queued", "model": "sf3d" }
```

### Verificar status / obter resultado
```http
GET /status/{job_id}
X-API-Key: sua-key-aqui
```
Resposta quando pronto:
```json
{
  "status": "done",
  "glb_base64": "R0lGODlh..."
}
```
Decodifique o base64 para obter o arquivo `.glb`.

---

## Custos estimados (Modal.com — A10G 24 GB VRAM)

| Modelo | Tempo | Custo/geração |
|---|---|---|
| SF3D | ~0.5 s | ~$0.0002 |
| TRELLIS | ~75 s | ~$0.023 |
| Hunyuan3D-2GP | ~40 s | ~$0.012 |

Modal oferece **$30 grátis/mês** → ~1.500 gerações SF3D sem pagar nada.  
Enquanto ninguém usa, o custo é **$0** (escala a zero).

---

## Licenças dos modelos

| Modelo | Licença | Restrições |
|---|---|---|
| SF3D | Stability AI Community License | Uso comercial com cadastro |
| TRELLIS | MIT | Livre |
| Hunyuan3D-2GP | Tencent License | Exclui EU/UK/Coreia do Sul |

---

*Projeto open source — Dive Smart Factory*
