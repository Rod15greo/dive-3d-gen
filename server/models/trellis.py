"""
TRELLIS — Microsoft Research
https://github.com/microsoft/TRELLIS

Geração de mesh a partir de texto ou imagem.
~60–90 s em A10G. Requer ~16 GB VRAM.
Saída: bytes do arquivo .glb
"""

import io
from pathlib import Path
from typing import Optional

import torch
from PIL import Image

MODEL_CACHE = "/models/trellis"
MODEL_ID = "JeffreyXiang/TRELLIS-image-large"

_pipeline = None


def _load_pipeline():
    global _pipeline  # noqa: WPS420
    if _pipeline is not None:
        return _pipeline

    from huggingface_hub import snapshot_download
    from trellis.pipelines import TrellisImageTo3DPipeline

    if not Path(f"{MODEL_CACHE}/pipeline.yaml").exists():
        print("Baixando TRELLIS...")
        snapshot_download(MODEL_ID, local_dir=MODEL_CACHE)
        import modal
        modal.Volume.from_name("dive-3d-gen-models").commit()

    _pipeline = TrellisImageTo3DPipeline.from_pretrained(MODEL_CACHE)
    _pipeline.cuda()
    print("TRELLIS carregado.")
    return _pipeline


def _quality_to_steps(quality: str) -> dict:
    """Mapeia quality para steps de sampling."""
    return {
        "fast":     {"sparse_structure_sampler_params": {"steps": 12}, "slat_sampler_params": {"steps": 12}},
        "balanced": {"sparse_structure_sampler_params": {"steps": 20}, "slat_sampler_params": {"steps": 20}},
        "high":     {"sparse_structure_sampler_params": {"steps": 50}, "slat_sampler_params": {"steps": 50}},
    }.get(quality, {"sparse_structure_sampler_params": {"steps": 20}, "slat_sampler_params": {"steps": 20}})


def generate(
    prompt: Optional[str],
    image: Optional[Image.Image],
    quality: str = "balanced",
) -> bytes:
    pipeline = _load_pipeline()
    params = _quality_to_steps(quality)

    if image is not None:
        outputs = pipeline.run(image, seed=42, **params)
    else:
        # TRELLIS text-to-3D: gera imagem de referência primeiro via pipeline interno
        outputs = pipeline.run_text(prompt, seed=42, **params)

    # Pega o primeiro mesh da lista de resultados
    mesh = outputs["mesh"][0]

    buf = io.BytesIO()
    # trimesh Trimesh ou Scene
    if hasattr(mesh, "export"):
        mesh.export(buf, file_type="glb")
    else:
        import trimesh
        scene = trimesh.Scene(mesh)
        scene.export(buf, file_type="glb")

    return buf.getvalue()
