"""
Hunyuan3D-2GP — Tencent / fork deepbeepmeep
https://github.com/deepbeepmeep/Hunyuan3D-2GP

Melhor qualidade PBR. ~20–60 s em A10G. Roda com 6–24 GB VRAM via offloading.
Dois estágios: shape (geometria) → texture (PBR maps: albedo, normal, roughness, metallic).
Saída: bytes do arquivo .glb com texturas embutidas.
"""

import io
from pathlib import Path
from typing import Optional

from PIL import Image

MODEL_CACHE_SHAPE = "/models/hunyuan/shape"
MODEL_CACHE_TEX   = "/models/hunyuan/texture"
MODEL_ID_SHAPE    = "tencent/Hunyuan3D-2"
MODEL_ID_TEX      = "tencent/Hunyuan3D-2"  # mesmo repo, pesos separados

_shape_pipeline = None
_tex_pipeline   = None


def _load_pipelines():
    global _shape_pipeline, _tex_pipeline  # noqa: WPS420
    if _shape_pipeline and _tex_pipeline:
        return _shape_pipeline, _tex_pipeline

    from huggingface_hub import snapshot_download
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
    from hy3dgen.texgen import Hunyuan3DPaintPipeline

    if not Path(f"{MODEL_CACHE_SHAPE}/config.json").exists():
        print("Baixando Hunyuan3D (shape)...")
        snapshot_download(MODEL_ID_SHAPE, local_dir=MODEL_CACHE_SHAPE)
        import modal
        modal.Volume.from_name("dive-3d-gen-models").commit()

    if not Path(f"{MODEL_CACHE_TEX}/hunyuan3d-paint-v2-0/config.json").exists():
        print("Baixando Hunyuan3D (texture)...")
        snapshot_download(MODEL_ID_TEX, local_dir=MODEL_CACHE_TEX)
        import modal
        modal.Volume.from_name("dive-3d-gen-models").commit()

    # profile=4 mantém pico abaixo de 6 GB (offloading agressivo para CPU)
    # Em A10G (24 GB) podemos usar profile=1 para máxima velocidade
    _shape_pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        MODEL_CACHE_SHAPE,
        use_safetensors=True,
        device="cuda",
        offload_pipe=False,   # A10G tem VRAM suficiente
    )
    _tex_pipeline = Hunyuan3DPaintPipeline.from_pretrained(
        MODEL_CACHE_TEX,
        device="cuda",
    )
    print("Hunyuan3D carregado.")
    return _shape_pipeline, _tex_pipeline


def _quality_to_steps(quality: str) -> int:
    return {"fast": 20, "balanced": 35, "high": 50}.get(quality, 35)


def generate(
    prompt: Optional[str],
    image: Optional[Image.Image],
    quality: str = "balanced",
) -> bytes:
    shape_pipe, tex_pipe = _load_pipelines()
    steps = _quality_to_steps(quality)

    # Estágio 1 — geometria
    if image is not None:
        mesh = shape_pipe(
            image=image,
            num_inference_steps=steps,
            guidance_scale=7.5,
            octree_resolution=256,
        )[0]
    else:
        mesh = shape_pipe(
            prompt=prompt,
            num_inference_steps=steps,
            guidance_scale=7.5,
            octree_resolution=256,
        )[0]

    # Estágio 2 — texturas PBR
    mesh = tex_pipe(
        mesh=mesh,
        image=image,      # None se só texto
        num_inference_steps=steps,
        guidance_scale=7.5,
    )[0]

    buf = io.BytesIO()
    mesh.export(buf, file_type="glb")
    return buf.getvalue()
