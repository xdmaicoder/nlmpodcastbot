"""Image and media converter service.

Provides multimodal vision text extraction from images to structured Markdown documents,
and saving text notes for NotebookLM ingestion.
"""

import asyncio
import base64
import logging
import mimetypes
import os
import shutil
import time
from pathlib import Path
from typing import Optional

import httpx

from config import (
    ANTIGRAVITY_BIN,
    ANTIGRAVITY_MODEL,
    DOWNLOADS_DIR,
    GEMINI_API_KEY,
    HTTP_PROXY,
    HTTPS_PROXY,
)

logger = logging.getLogger(__name__)

VISION_PROMPT = (
    "你是一个精准的多模态文字提取与整理助手。请完整提取这张图片中的所有文本内容，"
    "保持原文的完整性与事实准确性，并用规范的 Markdown 格式（保留标题层级、段落、引用和列表）输出。"
    "不要添加任何开头或结尾的寒暄评论，只输出正文内容。"
)


async def _extract_via_gemini_api(image_path: Path, api_key: str, model: str) -> Optional[str]:
    """Extract text from image using Gemini REST API with base64 inline data.

    Args:
        image_path: Path to the image file.
        api_key: Gemini API key.
        model: Model name.

    Returns:
        Extracted Markdown string, or None if extraction failed.
    """
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        mime_type = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"

    image_bytes = image_path.read_bytes()
    b64_data = base64.b64encode(image_bytes).decode("utf-8")

    api_model = model
    # Adapt model identifier for public Developer API if needed
    if api_model.startswith("gemini-3.8-"):
        api_model = "gemini-2.5-flash"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{api_model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": VISION_PROMPT},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data,
                        }
                    },
                ]
            }
        ]
    }

    proxy = HTTPS_PROXY or HTTP_PROXY or None
    async with httpx.AsyncClient(proxy=proxy, timeout=90.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "").strip()
    return None


async def _extract_via_antigravity_cli(image_path: Path) -> str:
    """Extract text from image using Antigravity CLI multimodal session.

    Args:
        image_path: Path to the image file.

    Returns:
        Extracted Markdown text.
    """
    cli_bin = shutil.which(ANTIGRAVITY_BIN) or shutil.which("agy") or "/opt/homebrew/bin/agy"

    if not Path(cli_bin).exists() and not shutil.which(str(cli_bin)):
        raise FileNotFoundError(
            f"Neither Antigravity CLI executable '{cli_bin}' nor 'agy' found on PATH."
        )

    prompt = (
        f"请使用 view_file 工具查看图片文件 {image_path.resolve()}。"
        f"{VISION_PROMPT}"
    )

    cmd = [
        str(cli_bin),
        "-p",
        prompt,
        "--model",
        ANTIGRAVITY_MODEL,
        "--dangerously-skip-permissions",
    ]

    logger.info("Calling Antigravity CLI for multimodal image extraction: %s", image_path.name)
    env = os.environ.copy()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(image_path.parent),
        env=env,
    )

    stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=180.0)
    stdout_str = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        logger.error("Antigravity CLI extraction failed (exit %d): %s", proc.returncode, stderr_str)
        raise RuntimeError(f"Antigravity CLI exited with code {proc.returncode}: {stderr_str or stdout_str}")

    if not stdout_str:
        raise RuntimeError("Antigravity CLI completed but returned empty output.")

    # Strip wrapping markdown fences if present
    cleaned = stdout_str
    if cleaned.startswith("```markdown\n") and cleaned.endswith("\n```"):
        cleaned = cleaned[len("```markdown\n"):-len("\n```")].strip()
    elif cleaned.startswith("```\n") and cleaned.endswith("\n```"):
        cleaned = cleaned[len("```\n"):-len("\n```")].strip()

    return cleaned


async def convert_image_to_markdown(input_image_path: Path) -> Path:
    """Extract text from an image using Multimodal Vision and save as structured Markdown.

    Replaces legacy raster PDF conversion so NotebookLM can ingest pure text stream.

    Args:
        input_image_path: Path to the input image file (PNG, JPG, WEBP, etc.).

    Returns:
        Path to the generated Markdown file ({image_stem}_extracted.md).
    """
    if not input_image_path.exists():
        raise FileNotFoundError(f"Input image does not exist: {input_image_path}")

    output_dir = input_image_path.parent if input_image_path.parent.name == "downloads" else DOWNLOADS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_md_path = output_dir / f"{input_image_path.stem}_extracted.md"

    logger.info("Converting image %s to Markdown %s via Multimodal Vision...", input_image_path, output_md_path)

    extracted_text: Optional[str] = None

    # Option 1: Direct Gemini REST API if GEMINI_API_KEY is configured
    if GEMINI_API_KEY:
        try:
            logger.info("Attempting extraction via Gemini API with GEMINI_API_KEY...")
            extracted_text = await _extract_via_gemini_api(input_image_path, GEMINI_API_KEY, ANTIGRAVITY_MODEL)
        except Exception as e:
            logger.warning("Direct Gemini API extraction failed (%s), falling back to Antigravity CLI", e)

    # Option 2: Antigravity CLI multimodal vision agent
    if not extracted_text:
        extracted_text = await _extract_via_antigravity_cli(input_image_path)

    output_md_path.write_text(extracted_text, encoding="utf-8")
    logger.info("Successfully extracted text from %s to %s (%d chars)", input_image_path, output_md_path, len(extracted_text))
    return output_md_path.resolve()


def save_text_note(text: str, output_dir: Path, prefix: str = "note") -> Path:
    """Save raw text notes to a UTF-8 encoded text file.

    Args:
        text: Text content to save.
        output_dir: Directory where the text file will be saved.
        prefix: Filename prefix.

    Returns:
        Path to the saved text file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{int(time.time() * 1000)}.txt"
    file_path = output_dir / filename
    file_path.write_text(text, encoding="utf-8")
    logger.info("Saved text note to: %s", file_path)
    return file_path
