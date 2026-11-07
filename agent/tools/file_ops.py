"""
Bulk file operations tool — rename, organize, dedupe, search by content.
All destructive operations support dry_run=True preview first.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path
from typing import List

from agent.types import RiskLevel, ToolResult
from agent.tools.registry import tool

logger = logging.getLogger(__name__)

_SAFE_ROOTS = [
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path.home() / "Pictures",
    Path.home() / "Music",
    Path.home() / "Videos",
]


def _assert_safe(path: Path) -> None:
    """Raise if path is outside safe roots (without explicit override)."""
    resolved = path.resolve()
    for root in _SAFE_ROOTS:
        try:
            resolved.relative_to(root.resolve())
            return
        except ValueError:
            pass
    raise PermissionError(
        f"Path '{path}' allowed roots se bahar hai. Pehle confirm karo."
    )


@tool(
    "bulk_rename",
    "Folder ke files rename karna pattern se (dry_run=True se pehle preview)",
    risk_level=RiskLevel.MEDIUM,
    timeout=30,
    needs_confirmation=False,
    category="files",
    param_descriptions={
        "folder": "Folder path jahan files hain",
        "pattern": "Rename pattern — {name}, {ext}, {n} (counter), {date} placeholders",
        "file_filter": "File filter e.g. '*.pdf' (default: all files)",
        "dry_run": "True = sirf preview dikhao, kuch change mat karo",
    },
)
def bulk_rename(folder: str, pattern: str, file_filter: str = "*", dry_run: bool = True) -> ToolResult:
    """Rename all files in a folder matching file_filter using a pattern template."""
    folder_path = Path(folder).expanduser()
    if not folder_path.exists():
        return ToolResult.err(f"Folder nahi mila: {folder}")
    _assert_safe(folder_path)

    files = sorted(folder_path.glob(file_filter))
    if not files:
        return ToolResult.ok(message=f"Koi file nahi mili '{file_filter}' filter se.")

    renames: List[dict] = []
    counter = 1
    from datetime import datetime
    today = datetime.now().strftime("%Y%m%d")

    for f in files:
        if not f.is_file():
            continue
        new_name = (
            pattern
            .replace("{name}", f.stem)
            .replace("{ext}", f.suffix.lstrip("."))
            .replace("{n}", str(counter).zfill(3))
            .replace("{date}", today)
        )
        if not new_name.endswith(f.suffix):
            new_name += f.suffix
        new_path = f.parent / new_name
        renames.append({"old": f.name, "new": new_name, "conflict": new_path.exists()})
        counter += 1

    conflicts = [r for r in renames if r["conflict"]]
    preview = "\n".join(f"  {r['old']} → {r['new']}" + (" ⚠️ CONFLICT" if r["conflict"] else "") for r in renames)

    if dry_run:
        return ToolResult.ok(
            message=f"Preview (kuch change nahi kiya):\n{preview}",
            data={"renames": renames, "total": len(renames), "conflicts": len(conflicts), "dry_run": True},
        )

    if conflicts:
        return ToolResult.confirm(
            message=f"{len(conflicts)} name conflicts hain. Confirm karein?",
            data={"renames": renames},
        )

    done = 0
    errors = []
    for r, f in zip(renames, [x for x in files if x.is_file()]):
        try:
            f.rename(f.parent / r["new"])
            done += 1
        except Exception as e:
            errors.append(f"{r['old']}: {e}")

    msg = f"{done}/{len(renames)} files rename kiye."
    if errors:
        msg += "\nErrors: " + "; ".join(errors)
    return ToolResult.ok(message=msg, data={"done": done, "errors": errors})


@tool(
    "organize_files",
    "Folder organize karna — files ko type/extension ke folders mein sort karna",
    risk_level=RiskLevel.MEDIUM,
    timeout=60,
    category="files",
    param_descriptions={
        "folder": "Folder path jisko organize karna hai",
        "dry_run": "True = sirf preview, kuch move mat karo (default True)",
    },
)
def organize_files(folder: str, dry_run: bool = True) -> ToolResult:
    """Sort files into sub-folders by extension type."""
    folder_path = Path(folder).expanduser()
    if not folder_path.exists():
        return ToolResult.err(f"Folder nahi mila: {folder}")
    _assert_safe(folder_path)

    ext_map = {
        "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic"},
        "Videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"},
        "Audio":  {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"},
        "Documents": {".pdf", ".doc", ".docx", ".txt", ".odt", ".rtf", ".md"},
        "Spreadsheets": {".xls", ".xlsx", ".csv", ".ods"},
        "Presentations": {".ppt", ".pptx", ".odp"},
        "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
        "Code": {".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c",
                 ".go", ".rs", ".sh", ".ps1", ".json", ".yaml", ".yml", ".toml"},
        "Executables": {".exe", ".msi", ".bat", ".cmd"},
    }
    ext_to_folder = {ext: cat for cat, exts in ext_map.items() for ext in exts}

    moves: List[dict] = []
    for f in folder_path.iterdir():
        if not f.is_file():
            continue
        cat = ext_to_folder.get(f.suffix.lower(), "Others")
        dest = folder_path / cat / f.name
        moves.append({"file": f.name, "to": cat, "dest": str(dest)})

    if not moves:
        return ToolResult.ok(message="Koi file nahi mili organize karne ke liye.")

    preview = "\n".join(f"  {m['file']} → {m['to']}/" for m in moves)
    if dry_run:
        return ToolResult.ok(
            message=f"Preview ({len(moves)} files):\n{preview}",
            data={"moves": moves, "dry_run": True},
        )

    done = 0
    errors = []
    for m, f in zip(moves, [folder_path / m["file"] for m in moves]):
        try:
            dest_dir = folder_path / m["to"]
            dest_dir.mkdir(exist_ok=True)
            shutil.move(str(f), str(dest_dir / f.name))
            done += 1
        except Exception as e:
            errors.append(f"{m['file']}: {e}")

    msg = f"{done}/{len(moves)} files organize kiye."
    if errors:
        msg += "\nErrors: " + "; ".join(errors)
    return ToolResult.ok(message=msg, data={"done": done, "errors": errors})


@tool(
    "search_files_by_content",
    "Files ke andar text dhundna (grep-style)",
    risk_level=RiskLevel.LOW,
    timeout=60,
    category="files",
    param_descriptions={
        "folder": "Folder jahan search karna hai",
        "query": "Text ya regex pattern jo dhundna hai",
        "file_filter": "File pattern jaise '*.txt' ya '*.py'",
        "max_results": "Maximum results return karne hain",
    },
)
def search_files_by_content(
    folder: str, query: str, file_filter: str = "*.*", max_results: int = 20
) -> ToolResult:
    """Search file contents for a text pattern."""
    folder_path = Path(folder).expanduser()
    if not folder_path.exists():
        return ToolResult.err(f"Folder nahi mila: {folder}")

    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error:
        pattern = re.compile(re.escape(query), re.IGNORECASE)

    matches: List[dict] = []
    checked = 0
    for f in folder_path.rglob(file_filter):
        if not f.is_file():
            continue
        if f.stat().st_size > 10 * 1024 * 1024:  # skip >10MB
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
            checked += 1
            for lineno, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    matches.append({
                        "file": str(f.relative_to(folder_path)),
                        "line": lineno,
                        "text": line.strip()[:120],
                    })
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break
        except Exception:
            pass

    if not matches:
        return ToolResult.ok(
            message=f"'{query}' koi bhi file mein nahi mila ({checked} files check kiye).",
            data={"query": query, "checked": checked, "results": []},
        )

    summary = "\n".join(
        f"  {m['file']}:{m['line']} → {m['text']}" for m in matches[:10]
    )
    if len(matches) > 10:
        summary += f"\n  ... aur {len(matches) - 10} matches"

    return ToolResult.ok(
        message=f"'{query}' mila:\n{summary}",
        data={"query": query, "checked": checked, "results": matches},
    )


@tool(
    "make_zip",
    "Files ya folder ko zip archive mein compress karna",
    risk_level=RiskLevel.MEDIUM,
    timeout=120,
    category="files",
    param_descriptions={
        "source": "File ya folder path",
        "output": "Output zip file path (optional)",
    },
)
def make_zip(source: str, output: str = "") -> ToolResult:
    """Compress a file or folder into a zip archive."""
    src = Path(source).expanduser()
    if not src.exists():
        return ToolResult.err(f"Source nahi mila: {source}")
    _assert_safe(src)

    if not output:
        output = str(src) + ".zip"
    out_path = Path(output)

    try:
        import zipfile
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if src.is_dir():
                for f in src.rglob("*"):
                    if f.is_file():
                        zf.write(f, f.relative_to(src.parent))
            else:
                zf.write(src, src.name)

        size_mb = out_path.stat().st_size / (1024 * 1024)
        return ToolResult.ok(
            message=f"Zip ban gaya: {out_path.name} ({size_mb:.1f} MB)",
            artifacts=[str(out_path)],
        )
    except Exception as exc:
        return ToolResult.err(f"Zip nahi ban paya: {exc}")
