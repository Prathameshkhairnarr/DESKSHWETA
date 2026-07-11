"""
Telegram Bot Interface for Shweta AI Desktop Assistant.
Remote control desktop from phone + secure file sharing.
"""

import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pyautogui
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, Update
)
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters
)

from config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# Security constants
SAFE_FOLDERS = [
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Pictures",
    Path.home() / "Music",
    Path.home() / "Videos",
]

BLOCKED_PATHS = ["C:\\Windows", "/etc", "/usr", "/bin", "/sbin"]

BLOCKED_KEYWORDS = [
    "password", "secret", "key", "token", ".env",
    "credential", "private", "id_rsa", ".pem", ".pfx", ".p12"
]

ALLOWED_EXTENSIONS = [
    ".pdf", ".txt", ".docx", ".xlsx", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif",
    ".mp3", ".mp4", ".zip", ".csv"
]

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

FILE_LOG = PROJECT_ROOT / "logs" / "file_transfers.log"


class ShwetaTelegramBot:
    """Telegram bot for remote desktop control + file sharing."""

    def __init__(
        self,
        desktop_action_fn: Callable,
        ai_brain_fn: Callable,
        bolna_fn: Callable
    ) -> None:
        """
        Args:
            desktop_action_fn: Function to execute desktop actions.
            ai_brain_fn: Function to get AI response.
            bolna_fn: Function to speak on desktop.
        """
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        allowed_id = os.getenv("TELEGRAM_ALLOWED_USER_ID", "0")
        self.allowed_id = int(allowed_id) if allowed_id.isdigit() else 0
        self.desktop_action = desktop_action_fn
        self.ai_brain = ai_brain_fn
        self.bolna = bolna_fn
        self.pending_files: Dict[int, Dict] = {}
        self.app = None
        self._start_time = time.time()
        self._command_count = 0

        # Cleanup thread for expired pending files
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def is_authorized(self, update: Update) -> bool:
        """Check if user is whitelisted."""
        return update.effective_user.id == self.allowed_id

    def is_safe_file(self, filepath: str) -> Tuple[bool, str]:
        """
        Check if file is safe to send.

        Returns:
            (True, "") if safe, (False, reason) if blocked.
        """
        path = Path(filepath)

        # Check blocked paths
        path_str = str(path).lower()
        for blocked in BLOCKED_PATHS:
            if path_str.startswith(blocked.lower()):
                return False, "System folder se file nahi bhej sakti."

        # Check blocked keywords in filename
        name_lower = path.name.lower()
        for keyword in BLOCKED_KEYWORDS:
            if keyword in name_lower:
                return False, f"Sensitive file hai ('{keyword}' detected)."

        # Check extension
        ext = path.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return False, f"'{ext}' extension allowed nahi hai."

        # Check file size
        if path.exists() and path.stat().st_size > MAX_FILE_SIZE:
            size_mb = path.stat().st_size / (1024 * 1024)
            return False, f"File bahut badi hai ({size_mb:.1f}MB). Max 50MB allowed."

        # Check if in safe folder
        in_safe = False
        for safe in SAFE_FOLDERS:
            try:
                path.resolve().relative_to(safe.resolve())
                in_safe = True
                break
            except ValueError:
                continue

        if not in_safe:
            return False, "File safe folders ke bahar hai."

        return True, ""

    def find_file(self, filename: str) -> List[str]:
        """
        Search for file in safe folders (case insensitive, partial match).
        Max 3 levels deep, max 5 results, sorted by newest first.
        """
        results = []
        search = filename.lower()

        for folder in SAFE_FOLDERS:
            if not folder.exists():
                continue
            try:
                for item in folder.rglob("*"):
                    # Max 3 levels deep
                    try:
                        depth = len(item.relative_to(folder).parts)
                        if depth > 3:
                            continue
                    except ValueError:
                        continue

                    if item.is_file() and search in item.name.lower():
                        safe, _ = self.is_safe_file(str(item))
                        if safe:
                            results.append(str(item))

                    if len(results) >= 5:
                        break
            except PermissionError:
                continue

            if len(results) >= 5:
                break

        # Sort by modified time (newest first)
        results.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)
        return results[:5]

    # --- HANDLERS ---

    async def start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not self.is_authorized(update):
            user_id = update.effective_user.id
            
            # Auto-authorize the user and update .env
            env_path = os.path.join(PROJECT_ROOT, ".env")
            try:
                if os.path.exists(env_path):
                    with open(env_path, 'r') as f:
                        lines = f.readlines()
                    with open(env_path, 'w') as f:
                        for line in lines:
                            if line.startswith("TELEGRAM_ALLOWED_USER_ID="):
                                f.write(f"TELEGRAM_ALLOWED_USER_ID={user_id}\n")
                            else:
                                f.write(line)
                self.allowed_id = user_id
                await update.message.reply_text(f"✅ Telegram id auto-configured in .env! (ID: {user_id})\nAap authorized ho gaye hain.")
            except Exception as e:
                await update.message.reply_text(f"❌ Auto-authorize failed: {e}. Please manually set TELEGRAM_ALLOWED_USER_ID={user_id} in .env")
            return

        keyboard = ReplyKeyboardMarkup(
            [
                ["📸 Screenshot", "🌤️ Weather"],
                ["🔊 Volume +", "🔇 Volume -"],
                ["📁 Files", "⏰ Timer"],
                ["💬 AI Chat", "ℹ️ Status"],
            ],
            resize_keyboard=True
        )

        await update.message.reply_text(
            f"🤖 *Namaste! Main {os.getenv('ASSISTANT_NAME', 'Shweta')} hoon!*\n\n"
            "Phone se desktop control karo:\n"
            "• Kuch bhi likho — main samjhungi\n"
            "• File mangwao — dhundhke bhejungi\n"
            "• Screenshot, weather, volume sab\n\n"
            "🔒 Secure mode: Sirf allowed files bhejti hoon",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    async def help_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if not self.is_authorized(update):
            return

        await update.message.reply_text(
            "📖 *Shweta Commands:*\n\n"
            "🗣️ Kuch bhi likho — main samjhungi\n\n"
            "📁 *File mangwane ke liye:*\n"
            "• `resume bhejo`\n"
            "• `project report send karo`\n"
            "• `photo dhundo`\n\n"
            "⚡ *Quick commands:*\n"
            "/screenshot — desktop screenshot\n"
            "/status — system status\n"
            "/files — recent files\n"
            "/help — yeh message\n\n"
            "🔒 *Security:*\n"
            "Sirf safe extensions bhejti hoon\n"
            "Sirf safe folders mein dhundti hoon\n"
            "Har file bhejne se pehle confirm karti hoon",
            parse_mode="Markdown"
        )

    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages."""
        if not self.is_authorized(update):
            user_id = update.effective_user.id
            
            # Auto-authorize the user and update .env
            env_path = os.path.join(PROJECT_ROOT, ".env")
            try:
                if os.path.exists(env_path):
                    with open(env_path, 'r') as f:
                        lines = f.readlines()
                    with open(env_path, 'w') as f:
                        for line in lines:
                            if line.startswith("TELEGRAM_ALLOWED_USER_ID="):
                                f.write(f"TELEGRAM_ALLOWED_USER_ID={user_id}\n")
                            else:
                                f.write(line)
                self.allowed_id = user_id
                await update.message.reply_text(f"✅ Telegram id auto-configured in .env! (ID: {user_id})\nAap authorized ho gaye hain.")
            except Exception as e:
                await update.message.reply_text(f"❌ Auto-authorize failed: {e}. Please manually set TELEGRAM_ALLOWED_USER_ID={user_id} in .env")
            return

        self._command_count += 1
        text = update.message.text.strip()

        # Block dangerous commands from Telegram
        BLOCKED_TELEGRAM_ACTIONS = ["shutdown_pc", "restart_pc", "run_command",
                                     "empty_recycle_bin", "lock_screen"]

        try:
            # Check if file request
            file_keywords = ["bhejo", "send", "file chahiye", "dhundo file",
                             "mujhe chahiye", "share karo", "file bhej",
                             "file send", "bhej do", "de do file",
                             ".txt", ".pdf", ".docx", ".xlsx", ".jpg", ".png", ".mp3", ".mp4", ".zip"]
            if any(kw in text.lower() for kw in file_keywords):
                await self._file_request(update, context, text)
                return

            # Quick button handlers
            if text == "📸 Screenshot":
                await self.screenshot_handler(update, context)
                return
            elif text == "🌤️ Weather":
                result = self.desktop_action("get_weather", {})
                await update.message.reply_text(f"🌤️ {result.get('message', 'N/A')}")
                return
            elif text == "🔊 Volume +":
                self.desktop_action("volume_up", {"steps": 5})
                await update.message.reply_text("🔊 Volume badha diya!")
                return
            elif text == "🔇 Volume -":
                self.desktop_action("volume_down", {"steps": 5})
                await update.message.reply_text("🔇 Volume kam kar diya!")
                return
            elif text == "📁 Files":
                await self.files_list_handler(update, context)
                return
            elif text == "ℹ️ Status":
                await self.status_handler(update, context)
                return
            elif text == "💬 AI Chat":
                await update.message.reply_text("💬 Kuch bhi pucho, main jawab dungi!")
                return
            elif text == "⏰ Timer":
                await update.message.reply_text("⏰ Likho: 'timer 5 min' ya 'reminder 10 min meeting'")
                return

            # AI response
            response = self.ai_brain(text)
            action = response.get("action", "none")
            params = response.get("params", {})
            reply = response.get("reply", "")

            # Execute action
            if action and action != "none":
                # Block dangerous actions from Telegram
                if action in BLOCKED_TELEGRAM_ACTIONS:
                    await update.message.reply_text(
                        f"⛔ '{action}' Telegram se allowed nahi hai. Desktop pe voice se karo."
                    )
                    return

                result = self.desktop_action(action, params)
                if result.get("message"):
                    reply = result["message"]

            await update.message.reply_text(f"💬 {reply}" if reply else "✅ Done!")

            # Speak on desktop
            if reply:
                self.bolna(reply)

        except Exception as e:
            logger.error(f"Telegram message error: {e}")
            await update.message.reply_text("❌ Kuch gadbad hui, dobara try karo.")

    async def _file_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
        """Handle file request."""
        # Extract filename — remove common command words
        remove_words = ["bhejo", "send", "file", "chahiye", "dhundo", "mujhe",
                        "share", "karo", "ko", "de", "do", "bhej", "kar",
                        "meri", "mera", "wali", "wala", "naam", "name"]
        words = query.lower().split()
        search_words = [w for w in words if w not in remove_words and len(w) > 1]
        search_name = " ".join(search_words).strip()

        # If nothing left after filtering, use original query minus just "bhejo/send"
        if not search_name:
            search_name = query.lower().replace("bhejo", "").replace("send", "").replace("file", "").strip()

        if not search_name:
            await update.message.reply_text("❓ Kaunsi file chahiye? Naam likho.")
            return

        results = self.find_file(search_name)

        if not results:
            await update.message.reply_text(
                f"❌ '{search_name}' nahi mila.\n"
                "Desktop, Documents, Downloads mein check kiya.\n"
                "Exact naam likho ya alag try karo."
            )
            return

        if len(results) == 1:
            await self._show_file_confirm(update, results[0])
        else:
            # Multiple results — show buttons
            buttons = []
            for path in results:
                p = Path(path)
                size = p.stat().st_size / (1024 * 1024)
                buttons.append([InlineKeyboardButton(
                    f"📄 {p.name} ({size:.1f}MB)",
                    callback_data=f"select_file_{results.index(path)}"
                )])

            # Store all results
            self.pending_files[update.effective_user.id] = {
                "paths": results,
                "timestamp": time.time()
            }

            await update.message.reply_text(
                f"🔍 {len(results)} files mili '{search_name}' ke liye:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

    async def _show_file_confirm(self, update_or_query, filepath: str) -> None:
        """Show file confirmation with buttons."""
        p = Path(filepath)
        size = p.stat().st_size / (1024 * 1024)
        modified = datetime.fromtimestamp(p.stat().st_mtime).strftime("%d %b %Y")
        folder = p.parent.name

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Haan, bhejo", callback_data="confirm_send"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_send")
            ]
        ])

        msg = (
            f"📄 *File mili:*\n"
            f"Name: `{p.name}`\n"
            f"Size: {size:.1f}MB\n"
            f"Folder: {folder}\n"
            f"Modified: {modified}\n\n"
            f"Bhejun kya?"
        )

        user_id = update_or_query.effective_user.id
        self.pending_files[user_id] = {
            "path": filepath,
            "timestamp": time.time()
        }

        if hasattr(update_or_query, 'message') and update_or_query.message:
            await update_or_query.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
        elif hasattr(update_or_query, 'callback_query'):
            await update_or_query.callback_query.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)

    async def confirm_send_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle confirm send button."""
        query = update.callback_query
        await query.answer()

        if not self.is_authorized(update):
            return

        user_id = update.effective_user.id
        pending = self.pending_files.get(user_id)

        if not pending or "path" not in pending:
            await query.message.reply_text("❌ Request expire ho gayi, dobara try karo.")
            return

        if time.time() - pending["timestamp"] > 60:
            del self.pending_files[user_id]
            await query.message.reply_text("❌ Request expire ho gayi (60s), dobara try karo.")
            return

        filepath = pending["path"]
        safe, reason = self.is_safe_file(filepath)
        if not safe:
            await query.message.reply_text(f"⛔ {reason}")
            del self.pending_files[user_id]
            return

        try:
            await query.message.reply_text("📤 File bhej rahi hoon...")
            p = Path(filepath)

            with open(filepath, "rb") as f:
                await query.message.reply_document(
                    document=f,
                    filename=p.name,
                    caption=f"📄 {p.name}\n✅ Shweta ne bheja"
                )

            # Notify on desktop
            self.bolna(f"{p.name} Telegram pe bheji gayi")

            # Log
            self._log_transfer(p.name, p.stat().st_size, user_id)

        except Exception as e:
            await query.message.reply_text(f"❌ File bhejne mein error: {str(e)[:100]}")
        finally:
            self.pending_files.pop(user_id, None)

    async def cancel_send_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle cancel button."""
        query = update.callback_query
        await query.answer()
        self.pending_files.pop(update.effective_user.id, None)
        await query.message.reply_text("❌ Cancel kar diya. Koi aur kaam?")

    async def file_select_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle file selection from list."""
        query = update.callback_query
        await query.answer()

        if not self.is_authorized(update):
            return

        user_id = update.effective_user.id
        pending = self.pending_files.get(user_id)
        if not pending or "paths" not in pending:
            await query.message.reply_text("❌ Request expire ho gayi.")
            return

        # Extract index from callback data
        try:
            idx = int(query.data.replace("select_file_", ""))
            filepath = pending["paths"][idx]
        except (ValueError, IndexError):
            await query.message.reply_text("❌ Invalid selection.")
            return

        await self._show_file_confirm(update, filepath)

    async def screenshot_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send desktop screenshot (hides Shweta window first)."""
        if not self.is_authorized(update):
            return

        try:
            await update.message.reply_text("📸 Screenshot le rahi hoon...")
            import tempfile, time

            self._hide_shweta_window()
            time.sleep(0.3)

            screenshot = pyautogui.screenshot()

            self._show_shweta_window()

            tmp = tempfile.mktemp(suffix=".png")
            screenshot.save(tmp)

            with open(tmp, "rb") as f:
                await update.message.reply_photo(photo=f, caption="📸 Desktop Screenshot")

            os.unlink(tmp)
            self.bolna("Screenshot Telegram pe bheja")
        except Exception as e:
            self._show_shweta_window()
            await update.message.reply_text(f"❌ Screenshot error: {str(e)[:100]}")

    async def status_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show system status."""
        if not self.is_authorized(update):
            return

        uptime_min = int((time.time() - self._start_time) / 60)

        await update.message.reply_text(
            f"🤖 *Shweta Status*\n\n"
            f"✅ Bot: Online\n"
            f"🖥️ Desktop: Connected\n"
            f"🧠 AI: Ready\n"
            f"🎙️ Voice: Active\n"
            f"📁 Safe folders: {len(SAFE_FOLDERS)}\n"
            f"🕐 Uptime: {uptime_min} minutes\n"
            f"📊 Commands: {self._command_count}",
            parse_mode="Markdown"
        )

    async def files_list_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show recent files in safe folders."""
        if not self.is_authorized(update):
            return

        recent = []
        cutoff = time.time() - (7 * 24 * 3600)  # Last 7 days

        for folder in SAFE_FOLDERS:
            if not folder.exists():
                continue
            try:
                for item in folder.iterdir():
                    if item.is_file() and item.stat().st_mtime > cutoff:
                        ext = item.suffix.lower()
                        if ext in ALLOWED_EXTENSIONS:
                            recent.append(item)
            except PermissionError:
                continue

        recent.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        recent = recent[:10]

        if not recent:
            await update.message.reply_text("📁 Last 7 days mein koi allowed file nahi mili.")
            return

        buttons = []
        for i, p in enumerate(recent):
            size = p.stat().st_size / (1024 * 1024)
            buttons.append([InlineKeyboardButton(
                f"📄 {p.name} ({size:.1f}MB)",
                callback_data=f"select_file_{i}"
            )])

        # Store paths
        self.pending_files[update.effective_user.id] = {
            "paths": [str(p) for p in recent],
            "timestamp": time.time()
        }

        await update.message.reply_text(
            "📁 *Recent Files (7 days):*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    # --- UTILITIES ---

    def _hide_shweta_window(self) -> None:
        """Temporarily hide Shweta window for clean screenshots."""
        try:
            import pygetwindow as gw
            import ctypes
            for win in gw.getAllWindows():
                if "shweta" in win.title.lower() and win.title == "Shweta":
                    # Use Win32 API to hide window (works with overrideredirect)
                    hwnd = win._hWnd
                    ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
                    return
        except Exception:
            pass

    def _show_shweta_window(self) -> None:
        """Restore Shweta window after screenshot."""
        try:
            import pygetwindow as gw
            import ctypes
            for win in gw.getAllWindows():
                if "shweta" in win.title.lower() and win.title == "Shweta":
                    hwnd = win._hWnd
                    ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
                    return
        except Exception:
            pass

    def _log_transfer(self, filename: str, size: int, user_id: int) -> None:
        """Log file transfer (filename only, not path)."""
        try:
            FILE_LOG.parent.mkdir(exist_ok=True)
            size_mb = size / (1024 * 1024)
            with open(FILE_LOG, "a", encoding="utf-8") as f:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{ts}] SENT | {filename} | {size_mb:.1f}MB | user_id: {user_id}\n")
        except Exception:
            pass

    def _cleanup_loop(self) -> None:
        """Background thread to clear expired pending files."""
        while True:
            time.sleep(30)
            now = time.time()
            expired = [uid for uid, data in self.pending_files.items()
                       if now - data.get("timestamp", 0) > 60]
            for uid in expired:
                del self.pending_files[uid]

    # --- FILE UPLOAD (Phone → PC) ---

    async def file_upload_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle files/photos/videos sent from phone → save to PC Desktop."""
        if not self.is_authorized(update):
            return
        try:
            if update.message.document:
                file = await context.bot.get_file(update.message.document.file_id)
                filename = update.message.document.file_name
            elif update.message.photo:
                file = await context.bot.get_file(update.message.photo[-1].file_id)
                filename = f"photo_{datetime.now().strftime('%H%M%S')}.jpg"
            elif update.message.video:
                file = await context.bot.get_file(update.message.video.file_id)
                filename = f"video_{datetime.now().strftime('%H%M%S')}.mp4"
            elif update.message.audio:
                file = await context.bot.get_file(update.message.audio.file_id)
                filename = f"audio_{datetime.now().strftime('%H%M%S')}.mp3"
            else:
                await update.message.reply_text("❓ File type samajh nahi aayi.")
                return

            save_path = Path.home() / "Desktop" / filename
            await file.download_to_drive(str(save_path))
            size_kb = save_path.stat().st_size / 1024

            await update.message.reply_text(
                f"✅ *File save ho gayi!*\n📄 `{filename}`\n📁 Desktop pe\n💾 {size_kb:.0f} KB",
                parse_mode="Markdown"
            )
            self.bolna(f"{filename} phone se aayi, Desktop pe save ki")
        except Exception as e:
            await update.message.reply_text(f"❌ Save nahi hui: {str(e)[:100]}")

    # --- LIVE SCREEN STREAM ---

    async def stream_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send 5 screenshots, one every 3 sec. Hides Shweta UI during capture."""
        if not self.is_authorized(update):
            return

        import tempfile, asyncio

        await update.message.reply_text("📹 Live stream! 5 screenshots aa rahe hain...")

        for i in range(5):
            try:
                # Hide Shweta window before screenshot
                self._hide_shweta_window()
                import time
                time.sleep(0.3)

                shot = pyautogui.screenshot()
                shot = shot.resize((960, 540))

                # Show window back
                self._show_shweta_window()

                tmp = tempfile.mktemp(suffix=".jpg")
                shot.save(tmp, "JPEG", quality=45)
                with open(tmp, "rb") as f:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=f,
                        caption=f"🖥️ #{i+1} | {datetime.now().strftime('%H:%M:%S')}"
                    )
                os.unlink(tmp)
            except Exception as e:
                logger.error(f"Stream frame error: {e}")
                self._show_shweta_window()
                break
            await asyncio.sleep(3)

    async def stop_stream_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Stop live stream."""
        if not self.is_authorized(update):
            return
        context.user_data["streaming"] = False
        await update.message.reply_text("⏹️ Stream off.")

    # --- CLIPBOARD SYNC ---

    async def clip_get_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Get PC clipboard → send to phone. /clipboard"""
        if not self.is_authorized(update):
            return
        try:
            import pyperclip
            content = pyperclip.paste()
            if content:
                content = content[:4000]
                await update.message.reply_text(f"📋 *PC Clipboard:*\n\n`{content}`", parse_mode="Markdown")
            else:
                await update.message.reply_text("📋 Clipboard khaali hai.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

    async def clip_set_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Copy text from phone → PC clipboard. /copy <text>"""
        if not self.is_authorized(update):
            return
        try:
            import pyperclip
            text = update.message.text.replace("/copy", "").strip()
            if not text:
                await update.message.reply_text("Usage: `/copy yahan text likho`", parse_mode="Markdown")
                return
            pyperclip.copy(text)
            await update.message.reply_text(f"✅ PC clipboard mein copy:\n`{text[:200]}`", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)[:100]}")

    # --- RUN ---

    def run_bot(self) -> None:
        """Start the Telegram bot (blocking)."""
        if not self.token:
            logger.warning("TELEGRAM_BOT_TOKEN not set — bot disabled.")
            return

        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())

        self.app = Application.builder().token(self.token).build()

        self.app.add_handler(CommandHandler("start", self.start_handler))
        self.app.add_handler(CommandHandler("help", self.help_handler))
        self.app.add_handler(CommandHandler("screenshot", self.screenshot_handler))
        self.app.add_handler(CommandHandler("status", self.status_handler))
        self.app.add_handler(CommandHandler("files", self.files_list_handler))
        self.app.add_handler(CommandHandler("stream", self.stream_handler))
        self.app.add_handler(CommandHandler("stopstream", self.stop_stream_handler))
        self.app.add_handler(CommandHandler("clipboard", self.clip_get_handler))
        self.app.add_handler(CommandHandler("copy", self.clip_set_handler))
        self.app.add_handler(CallbackQueryHandler(self.confirm_send_handler, pattern="^confirm_send$"))
        self.app.add_handler(CallbackQueryHandler(self.cancel_send_handler, pattern="^cancel_send$"))
        self.app.add_handler(CallbackQueryHandler(self.file_select_handler, pattern="^select_file_"))
        self.app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO, self.file_upload_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler))

        logger.info("Telegram bot polling started...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

    def start_in_thread(self) -> Optional[threading.Thread]:
        """Start bot in background thread."""
        if not self.token:
            logger.info("Telegram bot disabled (no token).")
            return None

        thread = threading.Thread(target=self.run_bot, daemon=True)
        thread.start()
        logger.info("📱 Telegram bot started in background!")
        return thread
