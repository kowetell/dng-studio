from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import warnings
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
PROJECT_DIR = Path(os.getenv("IMAGE2DNG_PROJECT", BASE_DIR / "vendor" / "Image-to-Raw")).resolve()
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
MAX_PIXELS = int(os.getenv("MAX_PIXELS", "100000000"))
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}

Image.MAX_IMAGE_PIXELS = MAX_PIXELS
app = FastAPI(title="DNG Studio", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def get_converter_base() -> list[str] | None:
    """Find the image2dng CLI, preferring a directly installed entry point."""
    installed = shutil.which("image2dng")
    if installed:
        return [installed]

    uv = shutil.which("uv")
    if uv and (PROJECT_DIR / "pyproject.toml").exists():
        return [uv, "run", "--project", str(PROJECT_DIR), "image2dng"]
    return None


def engine_status() -> dict[str, Any]:
    command = get_converter_base()
    return {
        "available": command is not None,
        "engine": "image2dng / LinearRaw DNG" if command else None,
        "projectFound": (PROJECT_DIR / "pyproject.toml").exists(),
        "message": "Mesin konversi siap." if command else "Mesin image2dng belum dipasang. Ikuti README.md untuk memasangnya.",
    }


async def read_upload(upload: UploadFile) -> bytes:
    filename = upload.filename or "foto"
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Format belum didukung. Gunakan JPG/JPEG, PNG, WebP, BMP, TIFF, atau GIF statis.",
        )

    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="File kosong.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Ukuran file melebihi batas 100 MB.")
    return data


def inspect_image(data: bytes) -> tuple[int, int, str, str, bool]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            from io import BytesIO
            with Image.open(BytesIO(data)) as image:
                width, height = image.size
                fmt = (image.format or "unknown").upper()
                mode = image.mode
                animated = bool(getattr(image, "is_animated", False)) or int(getattr(image, "n_frames", 1)) > 1
                image.verify()
    except Image.DecompressionBombError as exc:
        raise HTTPException(status_code=413, detail="Foto terlalu besar untuk diproses dengan aman.") from exc
    except Image.DecompressionBombWarning as exc:
        raise HTTPException(status_code=413, detail="Foto terlalu besar untuk diproses dengan aman.") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="File tidak dapat dibaca sebagai gambar yang valid.") from exc

    if width < 1 or height < 1:
        raise HTTPException(status_code=400, detail="Dimensi gambar tidak valid.")
    if width * height > MAX_PIXELS:
        raise HTTPException(status_code=413, detail=f"Foto melebihi batas {MAX_PIXELS:,} piksel.")
    if animated:
        raise HTTPException(status_code=415, detail="Gambar animasi belum didukung. Ekspor satu frame sebagai PNG atau JPG terlebih dahulu.")
    return width, height, fmt, mode, animated


def normalized_input(original_path: Path, temp_dir: Path, extension: str, mode: str) -> Path:
    """Keep RGB PNG/TIFF sources intact where possible; normalize other formats without resizing."""
    if extension in {".png", ".tif", ".tiff"} and mode == "RGB":
        return original_path

    from PIL import Image as PILImage
    with PILImage.open(original_path) as source:
        # Deliberately do not resize, crop, or auto-rotate: keep stored raster geometry intact.
        rgba = source.convert("RGBA")
        background = PILImage.new("RGBA", rgba.size, (255, 255, 255, 255))
        flattened = PILImage.alpha_composite(background, rgba).convert("RGB")
        normalized = temp_dir / "normalized-input.png"
        flattened.save(normalized, format="PNG", optimize=False)
    return normalized


@app.get("/")
def homepage() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return engine_status()


@app.post("/api/inspect")
async def inspect(file: UploadFile = File(...)) -> dict[str, Any]:
    data = await read_upload(file)
    width, height, fmt, mode, animated = inspect_image(data)
    from math import gcd
    divisor = gcd(width, height)
    return {
        "name": file.filename or "foto",
        "width": width,
        "height": height,
        "ratio": f"{width // divisor}:{height // divisor}",
        "format": fmt,
        "mode": mode,
        "size": len(data),
        "animated": animated,
        "engine": engine_status(),
    }


@app.post("/api/convert")
async def convert(file: UploadFile = File(...)) -> FileResponse:
    original_name = Path(file.filename or "foto").name
    extension = Path(original_name).suffix.lower()
    data = await read_upload(file)
    width, height, _fmt, mode, _animated = inspect_image(data)

    base_command = get_converter_base()
    if base_command is None:
        raise HTTPException(
            status_code=503,
            detail="Mesin konversi belum tersedia. Jalankan setup.sh atau ikuti petunjuk README.md.",
        )

    temp_path = Path(tempfile.mkdtemp(prefix="dng-studio-"))
    try:
        source_path = temp_path / ("source" + extension)
        source_path.write_bytes(data)
        input_path = normalized_input(source_path, temp_path, extension, mode)
        safe_stem = Path(original_name).stem.strip().replace("/", "_").replace("\\", "_") or "foto"
        output_path = temp_path / f"{safe_stem}.dng"

        command = base_command + [
            str(input_path), str(output_path),
            "--input-space", "srgb",
            "--mode", "linearraw",
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=int(os.getenv("CONVERT_TIMEOUT_SECONDS", "240")),
                check=False,
                cwd=str(BASE_DIR),
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail="Konversi melebihi batas waktu. Coba foto yang lebih kecil.") from exc

        if result.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
            details = (result.stderr or result.stdout or "Mesin konversi tidak menghasilkan file.").strip()
            # Avoid returning an enormous compiler traceback to the browser.
            details = details[-1200:]
            raise HTTPException(status_code=500, detail=f"Konversi gagal. {details}")

        # Independently inspect the TIFF-based output rather than assuming the converter kept
        # the original geometry. Fail closed if the DNG cannot be read or dimensions changed.
        try:
            with Image.open(output_path) as generated:
                output_width, output_height = generated.size
        except Exception as exc:
            raise HTTPException(status_code=500, detail="File hasil dibuat, tetapi dimensinya tidak dapat diverifikasi sebagai TIFF/DNG.") from exc
        if (output_width, output_height) != (width, height):
            raise HTTPException(
                status_code=500,
                detail=(f"Dimensi hasil berbeda dari sumber: sumber {width}×{height}, "
                        f"hasil {output_width}×{output_height}. File tidak diberikan."),
            )

        # These dimensions have now been verified from the generated TIFF/DNG itself.
        from math import gcd
        divisor = gcd(output_width, output_height)
        headers = {
            "X-Image-Width": str(output_width),
            "X-Image-Height": str(output_height),
            "X-Image-Aspect-Ratio": f"{output_width // divisor}:{output_height // divisor}",
            "X-DNG-Mode": "synthetic-linearraw",
            "Cache-Control": "no-store",
        }
        return FileResponse(
            output_path,
            media_type="image/x-adobe-dng",
            filename=f"{safe_stem}.dng",
            headers=headers,
            background=BackgroundTask(shutil.rmtree, temp_path, ignore_errors=True),
        )
    except Exception:
        shutil.rmtree(temp_path, ignore_errors=True)
        raise
