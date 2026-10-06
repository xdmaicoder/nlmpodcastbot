"""Independent test runner for Antigravity podcast & infographic pipeline.

Runs without the Telegram Bot to test MCP tool execution, prompt adherence,
and dual audio & infographic generation end-to-end.
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

from config import OUTPUTS_DIR
from services.antigravity_runner import run_antigravity_podcast_pipeline

# Configure detailed logging
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger("test_runner")


async def main() -> None:
    test_title = f"测试播客_独立运行_{time.strftime('%H%M%S')}"
    # Use a real informative article or url
    test_sources = ["https://example.com"]

    logger.info("=== 启动独立测试 ===")
    logger.info("测试标题: %s", test_title)
    logger.info("测试素材: %s", test_sources)
    logger.info("输出目录: %s", OUTPUTS_DIR.resolve())

    async def on_progress(status: str) -> None:
        logger.info(">>> [进度心跳更新]: %s", status)

    start_time = time.time()
    try:
        results = await run_antigravity_podcast_pipeline(
            title=test_title,
            sources=test_sources,
            output_dir=OUTPUTS_DIR,
            progress_callback=on_progress,
        )
        elapsed = time.time() - start_time
        audio_file = results["audio"]
        info_file = results.get("infographic")

        logger.info("=== 测试成功 ===")
        logger.info("生成耗时: %.1f 秒", elapsed)
        logger.info("音频文件路径: %s", audio_file)
        logger.info("音频文件大小: %d 字节", audio_file.stat().st_size)
        if info_file and info_file.exists():
            logger.info("信息图文件路径: %s", info_file)
            logger.info("信息图文件大小: %d 字节", info_file.stat().st_size)
        else:
            logger.warning("未检测到信息图文件输出")
    except Exception as e:
        elapsed = time.time() - start_time
        logger.exception("=== 测试执行失败 (耗时 %.1f 秒) ===", elapsed)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
