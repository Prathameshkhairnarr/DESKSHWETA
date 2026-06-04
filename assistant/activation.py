"""
Activation system for Shweta AI Desktop Assistant.
User enters activation password → keys decrypt → app runs.
State saved so user only needs to activate once.
"""

import base64
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# State file — saves activated status
APPDATA = Path(os.environ.get("APPDATA", str(Path.home())))
STATE_DIR = APPDATA / "Shweta"
STATE_DIR.mkdir(parents=True, exist_ok=True)
ACTIVATION_STATE = STATE_DIR / "activation.json"

# Bundle file — look in app dir and script dir
def _find_bundle() -> Optional[Path]:
    """Find activation_bundle.json in app directory."""
    candidates = [
        Path(sys.executable).parent / "activation_bundle.json",  # PyInstaller dist
        Path(__file__).parent.parent / "activation_bundle.json",  # Dev mode
        Path(".") / "activation_bundle.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _decrypt_keys(password: str, encrypted_data: str) -> Optional[Dict]:
    """Decrypt the keys bundle with given password."""
    try:
        from cryptography.fernet import Fernet, InvalidToken
        key_bytes = hashlib.sha256(password.encode()).digest()
        key_b64 = base64.urlsafe_b64encode(key_bytes)
        f = Fernet(key_b64)
        decrypted = f.decrypt(base64.b64decode(encrypted_data))
        return json.loads(decrypted)
    except Exception:
        return None


def _verify_password(password: str, check_hash: str) -> bool:
    """Verify password matches the stored check hash."""
    expected = hashlib.sha256(("verify_" + password).encode()).hexdigest()[:16]
    return expected == check_hash


def is_activated() -> bool:
    """Check if app is already activated on this machine."""
    try:
        if ACTIVATION_STATE.exists():
            state = json.loads(ACTIVATION_STATE.read_text())
            return state.get("activated", False)
    except Exception:
        pass
    return False


def get_saved_keys() -> Optional[Dict]:
    """Get decrypted keys saved from last activation."""
    try:
        if ACTIVATION_STATE.exists():
            state = json.loads(ACTIVATION_STATE.read_text())
            if state.get("keys"):
                return state["keys"]
    except Exception:
        pass
    return None


def save_activation(keys: Dict) -> None:
    """Save activation state and keys locally (never sends anywhere)."""
    state = {"activated": True, "keys": keys}
    ACTIVATION_STATE.write_text(json.dumps(state, indent=2))


def activate(password: str) -> tuple[bool, str]:
    """
    Try to activate with given password.
    Returns (success: bool, message: str)
    """
    bundle_path = _find_bundle()
    if not bundle_path:
        return False, "Activation bundle not found. Re-install the app."

    try:
        bundle = json.loads(bundle_path.read_text())
    except Exception:
        return False, "Activation file corrupted. Re-install the app."

    # Verify password
    check = bundle.get("check", "")
    if not _verify_password(password, check):
        return False, "Wrong password. Check with the person who gave you this app."

    # Decrypt keys
    keys = _decrypt_keys(password, bundle["data"])
    if not keys:
        return False, "Decryption failed. Try again or contact support."

    # Save locally
    save_activation(keys)
    return True, "Activated! Shweta ready hai!"


def inject_keys_to_env(keys: Dict) -> None:
    """Inject decrypted keys into os.environ so app uses them."""
    for k, v in keys.items():
        if v:
            os.environ[k] = v
    logger.info("[Activation] Keys injected into environment.")


def setup_activation() -> bool:
    """
    Full activation flow. Returns True if app can proceed.
    Called at startup before anything else.
    """
    # If no bundle file exists — dev mode, skip activation
    if not _find_bundle():
        logger.info("[Activation] No bundle found — running in dev mode (use .env)")
        return True

    # Already activated — load saved keys
    if is_activated():
        keys = get_saved_keys()
        if keys:
            inject_keys_to_env(keys)
            logger.info("[Activation] Previously activated — keys loaded.")
            return True

    # Need to activate — show PyQt5 dialog
    return _show_activation_dialog()


def _show_activation_dialog() -> bool:
    """Show activation password dialog. Returns True if activated."""
    try:
        from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QFont

        app = QApplication.instance() or QApplication(sys.argv)

        dialog = QDialog()
        dialog.setWindowTitle("Shweta AI — Activation")
        dialog.setFixedSize(400, 220)
        dialog.setStyleSheet("""
            QDialog { background: #0a0f1a; }
            QLabel { color: #00d4ff; }
            QLineEdit {
                background: #1a2540; color: white; border: 1px solid #00d4ff;
                border-radius: 6px; padding: 8px; font-size: 14px;
            }
            QPushButton {
                background: #00d4ff; color: #0a0f1a; border-radius: 6px;
                padding: 10px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background: #33ddff; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 25, 30, 25)

        title = QLabel("🤖  Shweta AI — Enter Activation Password")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("Contact the app provider for your password.")
        subtitle.setStyleSheet("color: #778899; font-size: 11px;")
        subtitle.setAlignment(Qt.AlignCenter)

        password_input = QLineEdit()
        password_input.setEchoMode(QLineEdit.Password)
        password_input.setPlaceholderText("Enter activation password...")

        activate_btn = QPushButton("Activate Shweta")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(password_input)
        layout.addWidget(activate_btn)

        result = {"activated": False}

        def on_activate():
            pwd = password_input.text().strip()
            if not pwd:
                QMessageBox.warning(dialog, "Error", "Please enter the activation password.")
                return
            success, msg = activate(pwd)
            if success:
                keys = get_saved_keys()
                if keys:
                    inject_keys_to_env(keys)
                result["activated"] = True
                QMessageBox.information(dialog, "Activated!", f"✅ {msg}\n\nShweta will start now!")
                dialog.accept()
            else:
                QMessageBox.warning(dialog, "Activation Failed", f"❌ {msg}")
                password_input.clear()
                password_input.setFocus()

        activate_btn.clicked.connect(on_activate)
        password_input.returnPressed.connect(on_activate)

        dialog.exec_()
        return result["activated"]

    except Exception as e:
        logger.error(f"[Activation] Dialog failed: {e}")
        return False


def reset_activation() -> None:
    """Reset activation (for testing or re-activation)."""
    try:
        if ACTIVATION_STATE.exists():
            ACTIVATION_STATE.unlink()
        logger.info("[Activation] Reset done.")
    except Exception:
        pass
