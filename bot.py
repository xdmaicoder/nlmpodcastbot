"""Telegram Bot entry point and message routing.

Handles incoming messages, whitelist verification, media preprocessing, batch staging,
and dual podcast audio & knowledge infographic delivery workflows.
"""

import html
import logging
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from config import (
    ALLOWED_USER_ID,
    BOT_TOKEN,
    DOWNLOADS_DIR,
    OUTPUTS_DIR,
    validate_config,
)
from services.antigravity_runner import run_antigravity_podcast_pipeline
from services.converter import convert_image_to_markdown, save_text_note

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("telegram_bot")

# In-memory staging store: user_id -> list of {"type": str, "value": str, "name": str}
user_staging: Dict[int, List[dict]] = defaultdict(list)
user_active_jobs: Dict[int, bool] = defaultdict(bool)

URL_REGEX = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.IGNORECASE)


async def silent_drop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Silently drop requests from unauthorized users (no reply sent)."""
    user_id = update.effective_user.id if update.effective_user else "unknown"
    logger.warning("Unauthorized access attempt dropped silently. user_id=%s", user_id)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    count = len(user_staging[update.effective_user.id])
    msg = (
        "👋 **欢迎使用 Telegram NotebookLM 播客与信息图生成 Bot！**\n\n"
        "你可以向我发送以下任意素材，我将为你暂存并统一合成【中文双人对话播客】与【知识信息图】：\n"
        "• 🔗 **文章链接**（直接发送 URL 即可）\n"
        "• 📝 **随手笔记**（发送纯文本，自动存为文本素材）\n"
        "• 🖼️ **图片/截图**（多模态 Vision 智能提取正文并转为结构化 Markdown）\n"
        "• 📄 **文档文件**（PDF、Word、TXT、MD 等）\n"
        "• 🎙️ **音频/语音**（MP3、M4A、WAV 或语音消息）\n\n"
        "**常用指令：**\n"
        f"• `/status` - 查看当前暂存素材列表 (当前暂存: {count} 份)\n"
        "• `/clear` - 清空当前暂存区\n"
        "• `/make [标题]` - 开始制作 (例: `/make 架构演进与前沿综述`)\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command: show currently staged materials."""
    user_id = update.effective_user.id
    items = user_staging[user_id]
    if not items:
        await update.message.reply_text(
            "📦 **当前暂存区为空**\n\n"
            "发送文章链接、笔记、图片或文档给我，准备好后输入 `/make [可选标题]` 即可开始合成播客。",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    type_icons = {
        "url": "🔗",
        "note": "📝",
        "image_markdown": "🖼️",
        "image_pdf": "🖼️",
        "doc": "📄",
        "audio": "🎙️",
    }

    lines = [f"📦 **当前暂存素材列表 (共 {len(items)} 份)：**\n"]
    for i, it in enumerate(items, 1):
        icon = type_icons.get(it["type"], "📎")
        name = html.escape(it["name"])
        lines.append(f"{i}. {icon} {name}")

    lines.append("\n👉 发送 `/make [标题]` 即可触发播客制作\n👉 发送 `/clear` 可清空暂存")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /clear command: reset staging buffer."""
    user_id = update.effective_user.id
    count = len(user_staging[user_id])
    user_staging[user_id].clear()
    await update.message.reply_text(f"🧹 已清空暂存区中的 {count} 份素材。")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages (URLs or notes)."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if not text:
        return

    urls = URL_REGEX.findall(text)
    if urls:
        # User sent URLs
        for url in urls:
            user_staging[user_id].append({
                "type": "url",
                "value": url,
                "name": url,
            })
        count = len(user_staging[user_id])
        await update.message.reply_text(
            f"🔗 已捕获 {len(urls)} 个链接并暂存！\n"
            f"当前暂存素材：共 {count} 份。\n"
            "发送 `/make [标题]` 开始生成播客，或继续发送更多素材。"
        )
    else:
        # Pure text note
        note_file = save_text_note(text, DOWNLOADS_DIR, prefix=f"user_{user_id}_note")
        summary_preview = (text[:30] + "...") if len(text) > 30 else text
        user_staging[user_id].append({
            "type": "note",
            "value": str(note_file.resolve()),
            "name": f"文本笔记: {summary_preview}",
        })
        count = len(user_staging[user_id])
        await update.message.reply_text(
            f"📝 随手笔记已落盘为文本素材！\n"
            f"当前暂存素材：共 {count} 份。\n"
            "发送 `/make [标题]` 开始生成播客，或继续发送更多素材。"
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming photo: download original and extract to Markdown via multimodal vision."""
    user_id = update.effective_user.id
    photos = update.message.photo
    if not photos:
        return

    status_msg = await update.message.reply_text("📥 正在接收图片并通过多模态 Vision 提取正文...")
    try:
        # Highest resolution photo is the last element
        highest_photo = photos[-1]
        photo_file = await highest_photo.get_file()

        img_filename = f"photo_{user_id}_{int(time.time() * 1000)}.jpg"
        img_path = DOWNLOADS_DIR / img_filename
        await photo_file.download_to_drive(str(img_path))

        # Convert to Markdown via multimodal vision
        md_path = await convert_image_to_markdown(img_path)

        user_staging[user_id].append({
            "type": "image_markdown",
            "value": str(md_path.resolve()),
            "name": f"图片提取Markdown ({md_path.name})",
        })
        count = len(user_staging[user_id])
        await status_msg.edit_text(
            f"🖼️ 图片内容已成功通过多模态解析为 Markdown 存入素材库！\n"
            f"当前暂存素材：共 {count} 份。\n"
            "发送 `/make [标题]` 开始生成播客，或继续发送更多素材。"
        )
    except Exception as e:
        logger.exception("Failed to process photo: %s", e)
        await status_msg.edit_text(f"❌ 图片多模态解析失败: {e}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming documents (.pdf, .docx, .txt, or uncompressed images)."""
    user_id = update.effective_user.id
    doc = update.message.document
    if not doc:
        return

    status_msg = await update.message.reply_text(f"📥 正在接收文档：{doc.file_name}...")
    try:
        tg_file = await doc.get_file()
        orig_name = doc.file_name or f"doc_{int(time.time())}"
        safe_name = f"{int(time.time() * 1000)}_{orig_name}"
        dest_path = DOWNLOADS_DIR / safe_name
        await tg_file.download_to_drive(str(dest_path))

        # If document is an uncompressed image (e.g. .png, .jpg, .webp), extract to Markdown
        suffix = dest_path.suffix.lower()
        if suffix in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
            md_path = await convert_image_to_markdown(dest_path)
            user_staging[user_id].append({
                "type": "image_markdown",
                "value": str(md_path.resolve()),
                "name": f"图片提取Markdown ({orig_name})",
            })
            item_name = f"{orig_name} (已解析为Markdown)"
        else:
            user_staging[user_id].append({
                "type": "doc",
                "value": str(dest_path.resolve()),
                "name": orig_name,
            })
            item_name = orig_name

        count = len(user_staging[user_id])
        await status_msg.edit_text(
            f"📄 文档【{item_name}】已成功存入素材库！\n"
            f"当前暂存素材：共 {count} 份。\n"
            "发送 `/make [标题]` 开始生成播客，或继续发送更多素材。"
        )
    except Exception as e:
        logger.exception("Failed to process document: %s", e)
        await status_msg.edit_text(f"❌ 文档接收失败: {e}")


async def handle_audio_or_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming audio files or voice notes."""
    user_id = update.effective_user.id
    status_msg = await update.message.reply_text("📥 正在接收音频素材...")
    try:
        if update.message.voice:
            voice = update.message.voice
            tg_file = await voice.get_file()
            filename = f"voice_{user_id}_{int(time.time() * 1000)}.ogg"
            dest_path = DOWNLOADS_DIR / filename
            await tg_file.download_to_drive(str(dest_path))
            disp_name = f"语音素材 ({voice.duration}秒)"
        elif update.message.audio:
            audio = update.message.audio
            tg_file = await audio.get_file()
            filename = f"audio_{user_id}_{int(time.time() * 1000)}_{audio.file_name or 'audio.mp3'}"
            dest_path = DOWNLOADS_DIR / filename
            await tg_file.download_to_drive(str(dest_path))
            disp_name = audio.file_name or "音频素材"
        else:
            await status_msg.edit_text("❌ 未识别的音频对象。")
            return

        user_staging[user_id].append({
            "type": "audio",
            "value": str(dest_path.resolve()),
            "name": disp_name,
        })
        count = len(user_staging[user_id])
        await status_msg.edit_text(
            f"🎙️ 【{disp_name}】已成功存入素材库！\n"
            f"当前暂存素材：共 {count} 份。\n"
            "发送 `/make [标题]` 开始生成播客，或继续发送更多素材。"
        )
    except Exception as e:
        logger.exception("Failed to process audio/voice: %s", e)
        await status_msg.edit_text(f"❌ 音频接收失败: {e}")


def cleanup_batch_files(sources: list[str]) -> None:
    """Safely delete local temporary files in workspace/downloads after successful delivery.

    Args:
        sources: List of source URLs or local file paths from the batch.
    """
    downloads_dir_resolved = DOWNLOADS_DIR.resolve()
    for s in sources:
        if s.startswith("http://") or s.startswith("https://"):
            continue
        try:
            path = Path(s).resolve()
            # Security guard: only delete files strictly inside DOWNLOADS_DIR
            if downloads_dir_resolved in path.parents and path.exists() and path.is_file():
                # If this was an extracted Markdown file or converted PDF, also remove original image if present
                if path.name.endswith("_extracted.md"):
                    orig_stem = path.name[:-len("_extracted.md")]
                    for ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
                        img_path = path.parent / f"{orig_stem}{ext}"
                        if img_path.exists() and img_path.is_file():
                            img_path.unlink(missing_ok=True)
                            logger.info("Cleaned up temporary source image: %s", img_path)
                elif path.suffix.lower() == ".pdf":
                    for ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
                        img_path = path.with_suffix(ext)
                        if img_path.exists() and img_path.is_file():
                            img_path.unlink(missing_ok=True)
                            logger.info("Cleaned up temporary source image: %s", img_path)

                path.unlink(missing_ok=True)
                logger.info("Cleaned up temporary source file: %s", path)
        except Exception as e:
            logger.warning("Error cleaning up source file %s: %s", s, e)


async def make_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /make [optional title]: trigger pipeline execution and return podcast audio."""
    user_id = update.effective_user.id

    if user_active_jobs.get(user_id, False):
        await update.message.reply_text("⚠️ 当前已有正在生成的播客任务，请耐心等待其完成。")
        return

    items = user_staging[user_id]
    if not items:
        await update.message.reply_text(
            "⚠️ 当前暂存区为空！\n请先发送文章链接、笔记文本、图片或文档后再执行 `/make`。",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Extract title or fallback to default timestamped title
    custom_title = " ".join(context.args).strip() if context.args else ""
    default_title = f"播客速递_{time.strftime('%Y%m%d_%H%M')}"
    podcast_title = custom_title if custom_title else default_title

    # Snapshot current materials without clearing staging yet (delayed release strategy)
    staged_items = list(items)
    user_active_jobs[user_id] = True

    status_msg = await update.message.reply_text(
        f"🚀 **开始制作播客与信息图：《{podcast_title}》**\n\n"
        f"• 素材总计: {len(staged_items)} 份\n"
        "• 状态: 正在唤起 Antigravity CLI 调度任务...",
        parse_mode=ParseMode.MARKDOWN,
    )

    last_text = ""

    async def progress_callback(status_text: str) -> None:
        nonlocal last_text
        if status_text != last_text:
            last_text = status_text
            try:
                await status_msg.edit_text(
                    f"🎙️ **《{podcast_title}》制作中**\n\n"
                    f"• 素材数量: {len(staged_items)} 份\n"
                    f"• 当前进度: {status_text}",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                logger.debug("Failed to edit progress message: %s", e)

    try:
        source_paths_or_urls = [it["value"] for it in staged_items]
        pipeline_result = await run_antigravity_podcast_pipeline(
            title=podcast_title,
            sources=source_paths_or_urls,
            output_dir=OUTPUTS_DIR,
            progress_callback=progress_callback,
        )
        audio_path = pipeline_result["audio"]
        infographic_path = pipeline_result.get("infographic")

        # File size check
        file_size_bytes = audio_path.stat().st_size
        file_size_mb = file_size_bytes / (1024 * 1024)
        MAX_BOT_API_SIZE = 50 * 1024 * 1024  # 50MB Telegram Bot API limit

        if file_size_bytes > MAX_BOT_API_SIZE:
            logger.warning("Generated audio size (%.1f MB) exceeds Telegram 50MB limit: %s", file_size_mb, audio_path)
            await status_msg.edit_text(
                f"⚠️ **音频生成成功，但文件大小（{file_size_mb:.1f}MB）超过了 Telegram 官方 Bot API 单文件 50MB 限制！**\n\n"
                f"• 播客标题：《{podcast_title}》\n"
                f"• 本地完整路径：`{audio_path.resolve()}`\n\n"
                "音频已完整保留在服务器本地，您可以直接在本地收听或提取该文件。",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Notify user before uploading generated media
        await status_msg.edit_text(
            f"📦 **播客与信息图合成完毕！正在上传推送至 Telegram，请稍候...**",
            parse_mode=ParseMode.MARKDOWN,
        )

        try:
            # 1. Deliver Infographic if present
            if infographic_path and infographic_path.exists():
                suffix = infographic_path.suffix.lower()
                caption_text = (
                    f"📊 **《{podcast_title}》知识信息图**\n\n"
                    f"• 版式方向：纵向（Portrait）\n"
                    f"• 详细程度：标准（Standard）\n"
                    f"• 语言：中文\n\n"
                    "可点击放大查看高清图解 🔍"
                )
                if suffix in [".png", ".jpg", ".jpeg", ".webp"]:
                    with open(infographic_path, "rb") as photo_file:
                        await update.message.reply_photo(
                            photo=photo_file,
                            caption=caption_text,
                            parse_mode=ParseMode.MARKDOWN,
                            read_timeout=300.0,
                            write_timeout=300.0,
                        )
                elif suffix == ".pdf":
                    with open(infographic_path, "rb") as doc_file:
                        await update.message.reply_document(
                            document=doc_file,
                            caption=caption_text,
                            parse_mode=ParseMode.MARKDOWN,
                            read_timeout=300.0,
                            write_timeout=300.0,
                        )
                else:
                    with open(infographic_path, "rb") as doc_file:
                        await update.message.reply_document(
                            document=doc_file,
                            caption=caption_text,
                            parse_mode=ParseMode.MARKDOWN,
                            read_timeout=300.0,
                            write_timeout=300.0,
                        )

            # 2. Deliver Podcast Audio
            with open(audio_path, "rb") as audio_file:
                await update.message.reply_audio(
                    audio=audio_file,
                    title=podcast_title,
                    performer="NotebookLM Podcast",
                    filename=audio_path.name,
                    caption=(
                        f"🎙️ **《{podcast_title}》双人深度播客**\n\n"
                        f"• 素材来源：共聚合 {len(staged_items)} 份材料\n"
                        f"• 音频大小：{file_size_mb:.1f} MB\n"
                        f"• 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        "随身收听愉快！🎧"
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                    read_timeout=300.0,
                    write_timeout=300.0,
                )

            try:
                await status_msg.delete()
            except Exception:
                pass

            # ONLY AFTER SUCCESSFUL TELEGRAM DELIVERY:
            # Safely clear the staged items that were processed in this batch
            for it in staged_items:
                if it in user_staging[user_id]:
                    user_staging[user_id].remove(it)
            logger.info("Successfully delivered audio and infographic to user %d; staging cleared for %d items.", user_id, len(staged_items))

            # Delete local temporary files in workspace/downloads
            cleanup_batch_files(source_paths_or_urls)

        except (TimedOut, NetworkError) as upload_err:
            logger.warning("Telegram media upload encountered timeout/network error: %s", upload_err)
            # Staging is preserved (not cleared)
            extra_info = f"\n• 信息图保存路径：`{infographic_path.resolve()}`" if (infographic_path and infographic_path.exists()) else ""
            await status_msg.edit_text(
                f"⚠️ **成品已成功生成，但向 Telegram 推送时超时或遭遇网络波动（音频约 {file_size_mb:.1f}MB）！**\n\n"
                f"• 播客标题：《{podcast_title}》\n"
                f"• 音频保存路径：`{audio_path.resolve()}`"
                f"{extra_info}\n\n"
                f"⚠️ 您刚才提交的 {len(staged_items)} 份素材已为您完整保留，您可以直接在本地查看，或排查网络后再次发送 `/make` 重试推送。",
                parse_mode=ParseMode.MARKDOWN,
            )

    except TimeoutError as te:
        logger.error("Make command timeout: %s", te)
        # user_staging is already intact (never cleared up-front)
        await status_msg.edit_text(
            f"⏱️ **制作超时**\n\n{te}\n\n"
            f"⚠️ 您刚才提交的 {len(staged_items)} 份素材已为您完整保留，无需重新上传，排查网络后直接回复 `/make` 即可重试。",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.exception("Make command failed: %s", e)
        # user_staging is already intact (never cleared up-front)
        await status_msg.edit_text(
            f"❌ **任务执行异常中断**\n\n`{str(e)[:400]}`\n\n"
            f"⚠️ 您刚才提交的 {len(staged_items)} 份素材已为您完整保留，无需重新上传，排查后直接回复 `/make` 即可重试。",
            parse_mode=ParseMode.MARKDOWN,
        )
    finally:
        user_active_jobs[user_id] = False


def main() -> None:
    """Run the bot application."""
    validate_config()
    logger.info("Initializing Telegram Bot with whitelist user_id=%d", ALLOWED_USER_ID)

    # Custom HTTPXRequest with increased timeouts for large media uploads and proxy connections
    request = HTTPXRequest(
        connect_timeout=60.0,
        read_timeout=300.0,
        write_timeout=300.0,
        pool_timeout=60.0,
    )

    app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()

    # User whitelist filter
    user_filter = filters.User(user_id=ALLOWED_USER_ID)

    # Authorized Command Handlers
    app.add_handler(CommandHandler("start", start_command, filters=user_filter))
    app.add_handler(CommandHandler("help", start_command, filters=user_filter))
    app.add_handler(CommandHandler("status", status_command, filters=user_filter))
    app.add_handler(CommandHandler("clear", clear_command, filters=user_filter))
    app.add_handler(CommandHandler("make", make_command, filters=user_filter))

    # Authorized Message Handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & user_filter, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO & user_filter, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL & user_filter, handle_document))
    app.add_handler(MessageHandler((filters.AUDIO | filters.VOICE) & user_filter, handle_audio_or_voice))

    # Unauthorized requests silent-drop fallback handler (all other users)
    app.add_handler(MessageHandler(~user_filter, silent_drop))

    logger.info("Bot starting polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
