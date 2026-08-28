"""
Dive 3D Gen — Modal server
Expõe uma API FastAPI serverless com GPU A10G (24 GB VRAM).
Suporta 3 modelos: sf3d | trellis | hunyuan
"""

import base64
import io
import os
from typing import Optional

import modal
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Modal app
# ---------------------------------------------------------------------------

app = modal.App("dive-3d-gen")

# Volume persistente: pesos dos modelos (evita re-download a cada cold start)
model_volume = modal.Volume.from_name("dive-3d-gen-models", create_if_missing=True)

# Dict persistente: API keys  {token: {name, created_at, requests}}
api_keys_store = modal.Dict.from_name("dive-3d-gen-api-keys", create_if_missing=True)

# ---------------------------------------------------------------------------
# Container images (uma por modelo para isolamento de dependências)
# ---------------------------------------------------------------------------

_cuda_base = "nvidia/cuda:12.1.0-devel-ubuntu22.04"

sf3d_image = (
    modal.Image.from_registry(_cuda_base, add_python="3.10")
    .apt_install("git", "libgl1", "libglib2.0-0")
    .pip_install(
        "torch==2.2.0", "torchvision==0.17.0",
        extra_index_url="https://download.pytorch.org/whl/cu121",
    )
    .pip_install(
        "huggingface_hub", "Pillow", "numpy", "trimesh[easy]",
        "einops", "omegaconf", "jaxtyping", "rembg[gpu]",
    )
    .run_commands(
        "pip install git+https://github.com/Stability-AI/stable-fast-3d.git"
    )
)

trellis_image = (
    modal.Image.from_registry(_cuda_base, add_python="3.10")
    .apt_install("git", "libgl1", "libglib2.0-0", "libsparsehash-dev")
    .pip_install(
        "torch==2.4.0", "torchvision==0.19.0",
        extra_index_url="https://download.pytorch.org/whl/cu121",
    )
    .pip_install(
        "huggingface_hub", "Pillow", "numpy", "trimesh[easy]",
        "einops", "easydict", "imageio", "tqdm", "scipy",
        "xformers==0.0.27.post2",
    )
    .run_commands(
        # flash-attn wheel para cu121 + torch 2.4
        "pip install flash-attn --no-build-isolation",
        # spconv (voxelização esparsa necessária para TRELLIS)
        "pip install spconv-cu120",
        # TRELLIS
        "pip install git+https://github.com/microsoft/TRELLIS.git",
    )
)

hunyuan_image = (
    modal.Image.from_registry(_cuda_base, add_python="3.10")
    .apt_install("git", "libgl1", "libglib2.0-0")
    .pip_install(
        "torch==2.2.0", "torchvision==0.17.0",
        extra_index_url="https://download.pytorch.org/whl/cu121",
    )
    .pip_install(
        "huggingface_hub", "Pillow", "numpy", "trimesh[easy]",
        "einops", "diffusers==0.27.0", "accelerate", "transformers",
        "omegaconf", "pytorch-lightning",
    )
    .run_commands(
        "pip install git+https://github.com/deepbeepmeep/Hunyuan3D-2GP.git"
    )
)

web_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi", "python-multipart", "Pillow")
)

# ---------------------------------------------------------------------------
# GPU functions (cada modelo roda em sua própria imagem isolada)
# ---------------------------------------------------------------------------

@app.function(
    gpu="A10G",
    image=sf3d_image,
    volumes={"/models": model_volume},
    timeout=120,
    memory=16384,
)
def run_sf3d(image_bytes: bytes, quality: str = "balanced") -> bytes:
    """Stable Fast 3D: ~0.5 s/geração, entrada apenas imagem."""
    import torch
    from PIL import Image
    from models.sf3d import generate as sf3d_generate  # noqa: WPS433

    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    return sf3d_generate(pil_image, quality=quality)


@app.function(
    gpu="A10G",
    image=trellis_image,
    volumes={"/models": model_volume},
    timeout=300,
    memory=20480,
)
def run_trellis(
    prompt: Optional[str],
    image_bytes: Optional[bytes],
    quality: str = "balanced",
) -> bytes:
    """TRELLIS: ~60–90 s, suporta texto e imagem."""
    from PIL import Image
    from models.trellis import generate as trellis_generate  # noqa: WPS433

    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB") if image_bytes else None
    return trellis_generate(prompt=prompt, image=pil_image, quality=quality)


@app.function(
    gpu="A10G",
    image=hunyuan_image,
    volumes={"/models": model_volume},
    timeout=300,
    memory=24576,
)
def run_hunyuan(
    prompt: Optional[str],
    image_bytes: Optional[bytes],
    quality: str = "balanced",
) -> bytes:
    """Hunyuan3D-2GP: ~20–60 s, melhor qualidade PBR."""
    from PIL import Image
    from models.hunyuan import generate as hunyuan_generate  # noqa: WPS433

    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB") if image_bytes else None
    return hunyuan_generate(prompt=prompt, image=pil_image, quality=quality)


# ---------------------------------------------------------------------------
# Web API (FastAPI sem GPU — barato, sempre ativo)
# ---------------------------------------------------------------------------

web_app = FastAPI(
    title="Dive 3D Gen API",
    version="0.1.0",
    description="Gera assets 3D (GLB) a partir de texto ou imagem usando SF3D, TRELLIS e Hunyuan3D.",
)

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MODELS = {
    "sf3d": run_sf3d,
    "trellis": run_trellis,
    "hunyuan": run_hunyuan,
}

MODEL_SUPPORTS_TEXT = {"sf3d": False, "trellis": True, "hunyuan": True}


def _validate_key(key: str) -> bool:
    try:
        return key in api_keys_store
    except Exception:
        return False


@web_app.get("/health")
async def health():
    return {"status": "ok", "models": list(MODELS.keys())}


@web_app.post("/generate")
async def generate(
    model: str = Form("sf3d"),
    prompt: Optional[str] = Form(None),
    quality: str = Form("balanced"),
    image: Optional[UploadFile] = File(None),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """
    Enfileira uma geração 3D.
    Retorna `job_id` — use GET /status/{job_id} para obter o resultado.
    """
    if not _validate_key(x_api_key):
        raise HTTPException(status_code=403, detail="API key inválida.")

    if model not in MODELS:
        raise HTTPException(status_code=400, detail=f"Modelo desconhecido: {model}. Use: {list(MODELS)}")

    if not MODEL_SUPPORTS_TEXT[model] and not image:
        raise HTTPException(status_code=400, detail=f"O modelo '{model}' requer uma imagem.")

    if not prompt and not image:
        raise HTTPException(status_code=400, detail="Envie prompt (texto) ou image (arquivo).")

    image_bytes = await image.read() if image else None

    # Atualiza contador da key
    try:
        entry = api_keys_store[x_api_key]
        entry["requests"] = entry.get("requests", 0) + 1
        api_keys_store[x_api_key] = entry
    except Exception:
        pass

    # Dispara o job GPU de forma assíncrona
    fn = MODELS[model]
    if model == "sf3d":
        call = fn.spawn(image_bytes=image_bytes, quality=quality)
    else:
        call = fn.spawn(prompt=prompt, image_bytes=image_bytes, quality=quality)

    return {"job_id": call.object_id, "status": "queued", "model": model}


@web_app.get("/status/{job_id}")
async def status(
    job_id: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """
    Verifica o status de um job.
    - `queued` / `running` → ainda processando
    - `done` → campo `glb_base64` disponível (string base64 do arquivo .glb)
    - `error` → campo `detail` com a mensagem de erro
    """
    if not _validate_key(x_api_key):
        raise HTTPException(status_code=403, detail="API key inválida.")

    try:
        call = modal.functions.FunctionCall.from_id(job_id)
        glb_bytes: bytes = call.get(timeout=0)
        return {
            "status": "done",
            "glb_base64": base64.b64encode(glb_bytes).decode(),
        }
    except modal.exception.TimeoutError:
        return {"status": "running"}
    except modal.exception.RemoteError as exc:
        return {"status": "error", "detail": str(exc)}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


# ---------------------------------------------------------------------------
# Serve
# ---------------------------------------------------------------------------

@app.function(
    image=web_image,
    secrets=[modal.Secret.from_name("dive-3d-gen-secrets")],
)
@modal.asgi_app(label="dive-3d-gen")
def serve():
    return web_app
