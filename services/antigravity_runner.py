"""Antigravity CLI runner service.

Manages subprocess execution of Antigravity CLI in headless mode, prompt composition,
status polling, and audio/infographic output detection.
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

from config import (
    ANTIGRAVITY_BIN,
    ANTIGRAVITY_MODEL,
    OUTPUTS_DIR,
    TASK_TIMEOUT_SECONDS,
    WORKSPACE_DIR,
)

logger = logging.getLogger(__name__)


def _build_title_generation_prompt(sources: list[str]) -> str:
    """Build a concise prompt for generating a title from sources.
    
    Args:
        sources: List of source URLs or file paths
        
    Returns:
        A prompt string for title generation
    """
    sources_summary = "\n".join(f"{i}. {s}" for i, s in enumerate(sources, 1))
    
    prompt = f"""你是一个内容标题生成专家。请根据以下素材列表，生成一个简洁、准确的中文标题（8-15个汉字）。

素材列表：
{sources_summary}

要求：
1. 只输出标题文本，不要任何其他内容
2. 长度：8-15个汉字
3. 准确提炼核心主题
4. 使用专业但易懂的表达

直接输出标题："""
    return prompt


async def generate_title_from_sources(
    sources: list[str],
    timeout: int = 60,
) -> Optional[str]:
    """Generate a title by analyzing the provided sources using Antigravity CLI.
    
    Args:
        sources: List of source URLs or file paths to analyze
        timeout: Maximum seconds to wait for title generation (default: 60)
        
    Returns:
        Generated title string, or None if generation fails
    """
    try:
        prompt = _build_title_generation_prompt(sources)
        cli_bin = shutil.which(ANTIGRAVITY_BIN) or shutil.which("agy") or "/opt/homebrew/bin/agy"
        
        if not Path(cli_bin).exists() and not shutil.which(str(cli_bin)):
            logger.warning("Antigravity CLI not found, cannot generate title")
            return None
        
        cmd = [
            str(cli_bin),
            "-p",
            prompt,
            "--model",
            ANTIGRAVITY_MODEL,
            "--dangerously-skip-permissions",
        ]
        
        logger.info("Starting title generation via Antigravity CLI")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(WORKSPACE_DIR.resolve()),
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Title generation timed out after %ds", timeout)
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            return None
        
        if process.returncode != 0:
            logger.warning(
                "Title generation failed with exit code %d: %s",
                process.returncode,
                stderr.decode("utf-8", errors="replace")[:200],
            )
            return None
        
        # Extract title from stdout
        output = stdout.decode("utf-8", errors="replace").strip()
        if not output:
            logger.warning("Title generation returned empty output")
            return None
        
        # Take only the first line and clean it
        title = output.split("\n")[0].strip()
        
        # Remove common prefix patterns
        for prefix in ["标题：", "标题:", "Title:", "Title：", "《", "】", "【"]:
            if title.startswith(prefix):
                title = title[len(prefix):].strip()
        for suffix in ["》", "】", "【"]:
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip()
        
        # Validate length (should be 8-15 Chinese characters or reasonable length)
        if len(title) < 5 or len(title) > 50:
            logger.warning("Generated title has unusual length (%d): %s", len(title), title)
            return None
        
        logger.info("Successfully generated title: %s", title)
        return title
        
    except Exception as e:
        logger.warning("Title generation encountered error: %s", e)
        return None


def build_pipeline_prompt(title: str, sources: list[str], output_dir: Path) -> str:
    """Build a structured, strict prompt instructing the Antigravity Agent.

    Uses exact tool names and parameter schemas from the Gemini Notebook MCP server.
    Instructs the agent to generate both a Chinese deep-dive podcast and a Chinese portrait standard infographic.
    """
    sources_bullets = []
    for i, s in enumerate(sources, 1):
        if s.startswith("http://") or s.startswith("https://"):
            sources_bullets.append(
                f'{i}. URL 来源: 调用 source_add(notebook_id=..., source_type="url", url="{s}", wait=True)'
            )
        else:
            sources_bullets.append(
                f'{i}. 本地文件来源: 调用 source_add(notebook_id=..., source_type="file", file_path="{s}", wait=True)'
            )
    sources_text = "\n".join(sources_bullets)

    ts = int(time.time())
    audio_filename = f"podcast_{ts}.m4a"
    infographic_filename = f"infographic_{ts}.png"
    chinese_podcast_focus = "请两位主持人全程使用中文（普通话）展开深入、风趣且自然的对话讨论。哪怕来源材料是英文，也请翻译并完全用中文进行总结和剖析。"
    chinese_infographic_focus = "专注于核心框架与关键要点提炼，文字精简精练，全中文呈现，排版清晰美观，避免过度密集的大段文本，确保中文文字清晰准确。"

    prompt = f"""你是一个专业的全自动知识内容制作 AI 助手。请直接调用已配置的 gemini-notebook-mcp 工具，严格按以下步骤依次完成中文双人播客与知识信息图（Infographic）的双重制作全流程：

【目标任务】为笔记本 "{title}" 在同一笔记本内同时制作：
1. 中文 Audio Overview（双人对话 Deep Dive 播客音频）；
2. 知识信息图（Infographic，格式要求：中文、纵向 Portrait、标准 Standard）；
并分别下载两份成品文件。

【语言与生成规格要求（核心）】
1. 播客音频：必须全程为【中文（普通话）】对话。两位主持人必须使用生动、自然、地道的中文进行深度剖析；若来源材料中包含外语内容，请全部翻译并用中文表达。
2. 信息图（Infographic）：必须指定语言为中文（language="zh"），版式方向为纵向（orientation="portrait"），详细程度为标准（detail_level="standard"）。专注于核心框架与关键点提炼，文字精简精练，避免大段密集文字以提升文字渲染准确度。

【严格执行步骤】
1. 步骤 1（创建笔记本并提取标题）：
   调用 notebook_create() 创建新笔记本（不指定 title 参数以让 NotebookLM 自动生成标题），提取并记录返回的 notebook_id 和 title。
   若 title 字段存在且不为空，请将其以 JSON 格式输出到标准输出：{{"title": "自动生成的标题文本"}}。

2. 步骤 2（批量挂载素材）：
   对以下 {len(sources)} 份素材，依次调用 source_add 添加到该 notebook_id：
{sources_text}

3. 步骤 3（触发两项生成任务）：
   (a) 触发中文双人播客合成：
       调用 studio_create(
           notebook_id=notebook_id,
           artifact_type="audio",
           confirm=True,
           audio_format="deep_dive",
           language="zh",
           focus_prompt="{chinese_podcast_focus}",
           custom_prompt="{chinese_podcast_focus}"
       )
   (b) 触发纵向标准知识信息图合成：
       调用 studio_create(
           notebook_id=notebook_id,
           artifact_type="infographic",
           confirm=True,
           orientation="portrait",
           detail_level="standard",
           language="zh",
           focus_prompt="{chinese_infographic_focus}"
       )
   【关键参数提示】
   - 必须携带 confirm=True 完成生成审批；
   - 若通过 CLI 调用，对应命令为：
     `nlm audio create <notebook_id> --language zh --focus "{chinese_podcast_focus}" --confirm`
     `nlm infographic create <notebook_id> --orientation portrait --detail standard --language zh --focus "{chinese_infographic_focus}" --confirm`

4. 步骤 4（轮询等待两项任务完成）：
   每隔 15~20 秒调用一次 studio_status(notebook_id=notebook_id)，检查生成状态。
   持续轮询直到音频（audio）和信息图（infographic）两个 artifact 的状态均变为 completed 或 ready。

5. 步骤 5（分别下载两份成品文件）：
   (a) 下载播客音频：
       调用 download_artifact(notebook_id=notebook_id, artifact_type="audio", output_path="{audio_filename}", wait=True)
       （或 CLI: `nlm download audio <notebook_id> -o {audio_filename}`）
   (b) 下载知识信息图：
       调用 download_artifact(notebook_id=notebook_id, artifact_type="infographic", output_path="{infographic_filename}", wait=True)
       （或 CLI: `nlm download infographic <notebook_id> -o {infographic_filename}`）
   两份文件均保存在输出目录：{output_dir.resolve()}。

请全自动连续执行上述所有步骤，不要在中间中断，完成所有步骤后输出生成结果总结。"""
    return prompt


def resolve_cli_command(prompt: str) -> list[str]:
    """Resolve the command arguments for running Antigravity CLI.

    Prefers `agy` or `antigravity` with non-interactive print mode (-p) and auto-approval.
    """
    cli_bin = shutil.which(ANTIGRAVITY_BIN) or shutil.which("agy") or "/opt/homebrew/bin/agy"

    if not Path(cli_bin).exists() and not shutil.which(str(cli_bin)):
        raise FileNotFoundError(
            f"Neither '{ANTIGRAVITY_BIN}' nor 'agy' executable was found on PATH. "
            "Please install the Antigravity CLI."
        )

    return [
        str(cli_bin),
        "-p",
        prompt,
        "--model",
        ANTIGRAVITY_MODEL,
        "--print-timeout",
        "35m",
        "--dangerously-skip-permissions",
    ]


async def run_antigravity_podcast_pipeline(
    title: str,
    sources: list[str],
    output_dir: Path,
    progress_callback: Optional[Callable[[str], Awaitable[None]]] = None,
) -> dict[str, Optional[Path]]:
    """Execute the end-to-end podcast & infographic generation pipeline via Antigravity CLI.

    Returns:
        dict with keys:
            "audio": Path to generated audio file (.m4a/.mp3)
            "infographic": Path to generated infographic file (.png/.jpg/.pdf) or None
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    start_time = time.time()

    prompt = build_pipeline_prompt(title=title, sources=sources, output_dir=output_dir)
    cmd = resolve_cli_command(prompt)

    logger.info("Starting Antigravity subprocess: %s", " ".join(cmd[:4]))

    if progress_callback:
        await progress_callback("🚀 正在启动 Antigravity 自动化子进程...")

    # Inherit and configure environment
    env = os.environ.copy()
    # Explicitly configure default download directory and language for notebooklm-mcp
    env["NOTEBOOKLM_DOWNLOAD_DIR"] = str(output_dir.resolve())
    env["NOTEBOOKLM_HL"] = "zh-CN"

    # Spawn subprocess
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(WORKSPACE_DIR.resolve()),
        env=env,
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    # Stream stdout/stderr line by line for logging
    async def read_stream(stream, lines_acc, is_err=False):
        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded:
                lines_acc.append(decoded)
                prefix = "[Antigravity STDERR]" if is_err else "[Antigravity STDOUT]"
                print(f"{prefix} {decoded}", file=sys.stderr if is_err else sys.stdout, flush=True)
                if is_err:
                    logger.warning("%s %s", prefix, decoded)
                else:
                    logger.info("%s %s", prefix, decoded)

    stdout_task = asyncio.create_task(read_stream(process.stdout, stdout_lines, False))
    stderr_task = asyncio.create_task(read_stream(process.stderr, stderr_lines, True))

    # Heartbeat updates for Telegram
    async def heartbeat():
        last_reported_text = ""
        while True:
            await asyncio.sleep(10)
            elapsed = time.time() - start_time
            elapsed_min = int(elapsed // 60)
            elapsed_sec = int(elapsed % 60)
            time_str = f"{elapsed_min}分{elapsed_sec}秒" if elapsed_min > 0 else f"{elapsed_sec}秒"

            if elapsed < 25:
                msg = "1/4 正在创建笔记本与挂载素材..."
            elif elapsed < 75:
                msg = "2/4 素材已就绪，已触发双人播客与知识信息图合成..."
            elif elapsed < 300:
                msg = f"3/4 云端深度合成播客与信息图中，请稍候（已耗时 {time_str}）..."
            else:
                msg = (
                    f"3/4 ⏳ 当前主题内容体量较大，NotebookLM 正在深度合成中"
                    f"（已耗时 {time_str}，全流程预计需要 8~18 分钟，请耐心等待）..."
                )

            if msg != last_reported_text and progress_callback:
                last_reported_text = msg
                try:
                    await progress_callback(msg)
                except Exception as e:
                    logger.debug("Progress callback error: %s", e)

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        await asyncio.wait_for(
            asyncio.gather(process.wait(), stdout_task, stderr_task),
            timeout=TASK_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error("Antigravity process timed out after %ds", TASK_TIMEOUT_SECONDS)
        try:
            process.kill()
            await process.wait()
        except Exception:
            pass
        raise TimeoutError(
            f"播客与信息图生成任务达到最大超时限制（超过 {TASK_TIMEOUT_SECONDS // 60} 分钟），请检查网络或稍后重试。"
        )
    finally:
        heartbeat_task.cancel()

    logger.info("Antigravity process finished with return code %d", process.returncode)

    if process.returncode != 0:
        tail_stdout = "\n".join(stdout_lines[-15:]) if stdout_lines else "None"
        tail_stderr = "\n".join(stderr_lines[-15:]) if stderr_lines else "None"
        raise RuntimeError(
            f"Antigravity 子进程异常退出 (退出码 {process.returncode})。\n"
            f"标准输出:\n{tail_stdout}\n"
            f"错误输出:\n{tail_stderr}"
        )

    # Check for newly created or modified audio & infographic files in output_dir
    candidate_dirs = [
        output_dir,
        WORKSPACE_DIR,
        Path.home() / "Downloads" / "gemini-notebook",
    ]

    new_audio_files = []
    new_infographic_files = []

    for c_dir in candidate_dirs:
        if c_dir.exists():
            # Check audio files
            for f in list(c_dir.glob("*.m4a")) + list(c_dir.glob("*.mp3")) + list(c_dir.glob("*.wav")):
                if f.stat().st_mtime >= start_time - 15:
                    if f.parent != output_dir:
                        target = output_dir / f.name
                        shutil.move(str(f), str(target))
                        new_audio_files.append(target)
                    else:
                        new_audio_files.append(f)

            # Check image/infographic files (.png, .jpg, .jpeg, .pdf)
            for f in (
                list(c_dir.glob("*.png"))
                + list(c_dir.glob("*.jpg"))
                + list(c_dir.glob("*.jpeg"))
                + list(c_dir.glob("*.pdf"))
            ):
                if f.stat().st_mtime >= start_time - 15:
                    if f.parent != output_dir:
                        target = output_dir / f.name
                        shutil.move(str(f), str(target))
                        new_infographic_files.append(target)
                    else:
                        new_infographic_files.append(f)

    if not new_audio_files:
        tail_stdout = "\n".join(stdout_lines[-20:]) if stdout_lines else "None"
        tail_stderr = "\n".join(stderr_lines[-20:]) if stderr_lines else "None"
        raise RuntimeError(
            f"播客生成未检测到音频输出文件。\n"
            f"进程退出码: {process.returncode}\n"
            f"标准输出:\n{tail_stdout}\n"
            f"错误输出:\n{tail_stderr}"
        )

    # Return the newest generated audio
    new_audio_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    audio_path = new_audio_files[0]
    logger.info("Found generated podcast audio: %s", audio_path)

    infographic_path = None
    if new_infographic_files:
        # Prioritize files containing 'infographic' in the filename, else latest image
        info_matched = [p for p in new_infographic_files if "infographic" in p.name.lower()]
        if info_matched:
            info_matched.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            infographic_path = info_matched[0]
        else:
            new_infographic_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            infographic_path = new_infographic_files[0]
        logger.info("Found generated infographic: %s", infographic_path)
    else:
        logger.warning("No infographic file detected in output candidates.")

    notebooklm_title: Optional[str] = None
    for line in stdout_lines:
        stripped = line.strip()
        if not stripped or stripped[0] not in "{[":
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("title"), str):
            candidate = parsed["title"].strip()
            if candidate:
                notebooklm_title = candidate
                break

    return {
        "audio": audio_path,
        "infographic": infographic_path,
        "title": notebooklm_title,
    }
