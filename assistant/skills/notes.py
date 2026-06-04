"""
Notes/Todo Skill — Save and recall voice notes.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from config import PROJECT_ROOT

logger = logging.getLogger(__name__)

NOTES_FILE = PROJECT_ROOT / "notes.json"


def _load_notes() -> List[Dict]:
    """Load notes from file."""
    if NOTES_FILE.exists():
        try:
            return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_notes(notes: List[Dict]) -> None:
    """Save notes to file."""
    NOTES_FILE.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")


def add_note(text: str) -> Dict[str, str]:
    """Add a new note."""
    try:
        notes = _load_notes()
        next_id = max([n["id"] for n in notes]) + 1 if notes else 1
        note = {
            "id": next_id,
            "text": text,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "done": False
        }
        notes.append(note)
        _save_notes(notes)
        return {"status": "success", "message": f"Note save kar diya: '{text}'"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_notes() -> Dict[str, str]:
    """List all notes."""
    try:
        notes = _load_notes()
        if not notes:
            return {"status": "success", "message": "Koi note nahi hai abhi."}

        lines = []
        for n in notes[-10:]:  # Last 10
            status = "✅" if n.get("done") else "📝"
            lines.append(f"{status} [{n['id']}] {n['text']} ({n['created']})")

        msg = f"{len(notes)} notes hain:\n" + "\n".join(lines)
        return {"status": "success", "message": msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def delete_note(target: str) -> Dict[str, str]:
    """Delete a note by ID or matching text query."""
    try:
        notes = _load_notes()
        original_len = len(notes)

        # Check if target is numeric (ID)
        is_numeric = False
        try:
            note_id = int(target)
            is_numeric = True
        except ValueError:
            pass

        if is_numeric:
            notes = [n for n in notes if n["id"] != note_id]
        elif str(target).lower().strip() in ["last", "last_note", "latest", "recent", "last note"]:
            if notes:
                notes.pop()
            else:
                return {"status": "error", "message": "Koyi note nahi mila."}
        else:
            query = str(target).lower().strip()
            notes = [n for n in notes if query not in n["text"].lower()]

        if len(notes) == original_len:
            return {"status": "error", "message": f"Koyi match hone wala note nahi mila: '{target}'."}

        _save_notes(notes)
        return {"status": "success", "message": f"Note delete kar diya hai."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def complete_note(target: str) -> Dict[str, str]:
    """Mark a note as done by ID or matching text query."""
    try:
        notes = _load_notes()
        is_numeric = False
        try:
            note_id = int(target)
            is_numeric = True
        except ValueError:
            pass

        found = False
        if is_numeric:
            for n in notes:
                if n["id"] == note_id:
                    n["done"] = True
                    found = True
                    break
        elif str(target).lower().strip() in ["last", "last_note", "latest", "recent", "last note"]:
            if notes:
                notes[-1]["done"] = True
                found = True
            else:
                return {"status": "error", "message": "Koyi note nahi mila."}
        else:
            query = str(target).lower().strip()
            for n in notes:
                if query in n["text"].lower():
                    n["done"] = True
                    found = True

        if not found:
            return {"status": "error", "message": f"Koyi match hone wala note nahi mila: '{target}'."}

        _save_notes(notes)
        return {"status": "success", "message": f"Note complete mark kar diya hai."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def clear_notes() -> Dict[str, str]:
    """Clear all notes."""
    try:
        _save_notes([])
        return {"status": "success", "message": "Saare notes delete kar diye."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
