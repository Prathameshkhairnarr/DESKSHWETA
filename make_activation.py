"""
Run this ONCE to generate encrypted keys bundle.
YOU run this on your machine — output goes into the app.
Keep your ACTIVATION_PASSWORD secret — share it with users separately.

Usage:
  python make_activation.py
"""

import base64
import hashlib
import json
import os
from pathlib import Path

# ============================================================
# CONFIGURE THESE:
# ============================================================
ACTIVATION_PASSWORD = "Shweta@2025"   # <--- CHANGE THIS to your secret password
                                        # Share this with your users via WhatsApp/DM

# Keys to embed (from your .env)
from dotenv import load_dotenv
load_dotenv()

KEYS_TO_EMBED = {
    "GEMINI_API_KEY":   os.getenv("GEMINI_API_KEY", ""),
    "GROQ_API_KEY":     os.getenv("GROQ_API_KEY", ""),
    "GITHUB_TOKEN":     os.getenv("GITHUB_TOKEN", ""),
    "ASSISTANT_NAME":   os.getenv("ASSISTANT_NAME", "Shweta"),
    "DEFAULT_CITY":     os.getenv("DEFAULT_CITY", "Pune"),
}
# ============================================================

def encrypt_keys(password: str, keys: dict) -> str:
    """Encrypt keys dict with password. Returns base64 string."""
    # Derive a 32-byte key from password using SHA-256
    key_bytes = hashlib.sha256(password.encode()).digest()
    key_b64 = base64.urlsafe_b64encode(key_bytes)
    
    from cryptography.fernet import Fernet
    f = Fernet(key_b64)
    
    data = json.dumps(keys).encode()
    encrypted = f.encrypt(data)
    return base64.b64encode(encrypted).decode()


if __name__ == "__main__":
    print("Generating encrypted keys bundle...")
    
    # Check keys are filled
    empty = [k for k, v in KEYS_TO_EMBED.items() if not v and k.endswith("KEY")]
    if empty:
        print(f"WARNING: These keys are empty: {empty}")
    
    encrypted = encrypt_keys(ACTIVATION_PASSWORD, KEYS_TO_EMBED)
    
    # Save to file
    output = {
        "v": "1",
        "data": encrypted,
        # Password hint hash (not the password itself — just for verification)
        "check": hashlib.sha256(("verify_" + ACTIVATION_PASSWORD).encode()).hexdigest()[:16]
    }
    
    out_path = Path("activation_bundle.json")
    out_path.write_text(json.dumps(output, indent=2))
    
    print(f"\n✅ Done! Created: activation_bundle.json")
    print(f"\n📋 Share with users:")
    print(f"   Activation Password: {ACTIVATION_PASSWORD}")
    print(f"\n⚠️  Keep this password private — share only via direct message!")
    print(f"\n📦 Include activation_bundle.json in your installer.")
    print(f"   Add to shweta.spec datas: ('activation_bundle.json', '.')")
