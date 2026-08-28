"""
Dive 3D Gen — Modal server
Expõe uma API FastAPI serverless com GPU A10G (24 GB VRAM).
Suporta 3 modelos: sf3d | trellis | hunyuan
"""

import base64
import io
from pathlib import Path
from typing import Optional

import modal

# ---------------------------------------------------------------------------
# Modal app
# ---------------------------------------------------------------------------

app = modal.App("dive-3d-gen")

model_volume  = modal.Volume.from_name("dive-3d-gen-models", create_if_missing=True)
api_keys_store = modal.Dict.from_name("dive-3d-gen-api-keys", create_if_missing=True)

# ---------------------------------------------------------------------------
# Container images
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
        "einops", "omegaconf", "jaxtyping", "rembg[gpu]", "open_clip_torch",
    )
    .run_commands(
        "git clone --depth=1 https://github.com/Stability-AI/stable-fast-3d.git /sf3d",
        "pip install -r /sf3d/requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121 || true",
    )
    .add_local_dir("models", remote_path="/root/models")
)

trellis_image = (
    modal.Image.from_registry(_cuda_base, add_python="3.10")
    .pip_install("huggingface_hub", "Pillow", "trimesh[easy]", "numpy")
    .add_local_dir("models", remote_path="/root/models")
)

hunyuan_image = (
    modal.Image.from_registry(_cuda_base, add_python="3.10")
    .apt_install("git", "libgl1", "libglib2.0-0")
    .pip_install(
        "torch==2.4.0", "torchvision==0.19.0",
        extra_index_url="https://download.pytorch.org/whl/cu121",
    )
    .pip_install(
        "huggingface_hub", "Pillow", "numpy", "trimesh[easy]",
        "einops", "diffusers>=0.30.0", "accelerate", "transformers",
        "omegaconf", "pytorch-lightning", "tqdm",
    )
    .run_commands(
        "git clone --depth=1 https://github.com/deepbeepmeep/Hunyuan3D-2GP.git /hunyuan",
        "cd /hunyuan && pip install -e . --no-deps || true",
    )
    .add_local_dir("models", remote_path="/root/models")
)

web_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi", "python-multipart", "Pillow")
)

# ---------------------------------------------------------------------------
# GPU functions
# ---------------------------------------------------------------------------

@app.function(gpu="A10G", image=sf3d_image, volumes={"/models": model_volume}, timeout=120)
def run_sf3d(image_bytes: bytes, quality: str = "balanced") -> bytes:
    import sys
    sys.path.insert(0, "/sf3d")
    from PIL import Image
    from models.sf3d import generate as sf3d_generate
    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    return sf3d_generate(pil_image, quality=quality)


@app.function(gpu="A10G", image=trellis_image, volumes={"/models": model_volume}, timeout=300)
def run_trellis(prompt: Optional[str], image_bytes: Optional[bytes], quality: str = "balanced") -> bytes:
    raise NotImplementedError("TRELLIS fase 2. Use sf3d ou hunyuan.")


@app.function(gpu="A10G", image=hunyuan_image, volumes={"/models": model_volume}, timeout=600)
def run_hunyuan(prompt: Optional[str], image_bytes: Optional[bytes], quality: str = "balanced") -> bytes:
    import sys
    sys.path.insert(0, "/hunyuan")
    from PIL import Image
    from models.hunyuan import generate as hunyuan_generate
    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB") if image_bytes else None
    return hunyuan_generate(prompt=prompt, image=pil_image, quality=quality)


# ---------------------------------------------------------------------------
# Web API — FastAPI importado APENAS aqui (web_image tem fastapi, gpu images não)
# ---------------------------------------------------------------------------

@app.function(image=web_image, secrets=[modal.Secret.from_name("dive-3d-gen-secrets")])
@modal.asgi_app(label="dive-3d-gen")
def serve():
    from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware

    web_app = FastAPI(title="Dive 3D Gen API", version="0.1.0")
    web_app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    MODELS = {"sf3d": run_sf3d, "trellis": run_trellis, "hunyuan": run_hunyuan}
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
        if not _validate_key(x_api_key):
            raise HTTPException(status_code=403, detail="API key inválida.")
        if model not in MODELS:
            raise HTTPException(status_code=400, detail=f"Modelo desconhecido: {model}.")
        if not MODEL_SUPPORTS_TEXT[model] and not image:
            raise HTTPException(status_code=400, detail=f"'{model}' requer imagem.")
        if not prompt and not image:
            raise HTTPException(status_code=400, detail="Envie prompt ou imagem.")

        image_bytes = await image.read() if image else None

        try:
            entry = api_keys_store[x_api_key]
            entry["requests"] = entry.get("requests", 0) + 1
            api_keys_store[x_api_key] = entry
        except Exception:
            pass

        fn = MODELS[model]
        if model == "sf3d":
            call = fn.spawn(image_bytes=image_bytes, quality=quality)
        else:
            call = fn.spawn(prompt=prompt, image_bytes=image_bytes, quality=quality)

        return {"job_id": call.object_id, "status": "queued", "model": model}

    @web_app.get("/status/{job_id}")
    async def status(job_id: str, x_api_key: str = Header(..., alias="X-API-Key")):
        if not _validate_key(x_api_key):
            raise HTTPException(status_code=403, detail="API key inválida.")
        try:
            call = modal.functions.FunctionCall.from_id(job_id)
            glb_bytes: bytes = call.get(timeout=0)
            return {"status": "done", "glb_base64": base64.b64encode(glb_bytes).decode()}
        except modal.exception.TimeoutError:
            return {"status": "running"}
        except modal.exception.RemoteError as exc:
            return {"status": "error", "detail": str(exc)}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    return web_app
