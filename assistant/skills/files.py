"""
File Management Skills for Shweta AI Desktop Assistant.
Create, delete, rename, move, copy files and folders.
"""

import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

# Common user directories
HOME = Path.home().resolve()
DESKTOP = (HOME / "Desktop").resolve()
DOCUMENTS = (HOME / "Documents").resolve()
DOWNLOADS = (HOME / "Downloads").resolve()


def _is_safe_path(path: Path) -> bool:
    """
    Check if the path is safe (inside user's HOME directory) to prevent directory traversal.
    """
    try:
        # Resolve path using abspath to handle relative components without requiring file existence
        abs_path = Path(os.path.abspath(path)).resolve()
        return abs_path == HOME or HOME in abs_path.parents
    except Exception:
        return False


def _resolve_path(filepath: str) -> Path:
    """
    Resolve a file path — supports relative paths from Desktop/Documents/Downloads.
    If no directory specified, assumes Desktop.
    """
    p = Path(filepath)

    # If absolute path, use as-is
    if p.is_absolute():
        return p

    # Check common locations
    for base in [DESKTOP, DOCUMENTS, DOWNLOADS, HOME, Path(".")]:
        full = base / filepath
        if full.exists():
            return full

    # Default: assume Desktop
    return DESKTOP / filepath


def create_file(filename: str, content: str = "") -> Dict[str, str]:
    """
    Create a new file.

    Args:
        filename: Name/path of file to create.
        content: Optional content to write.
    """
    try:
        filepath = DESKTOP / filename if not Path(filename).is_absolute() else Path(filename)
        if not _is_safe_path(filepath):
            return {"status": "error", "message": "Access Denied: Path home folder ke bahar hai."}
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        logger.info(f"Created file: {filepath}")
        return {"status": "success", "message": f"File bana diya: {filepath.name}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def create_folder(foldername: str) -> Dict[str, str]:
    """
    Create a new folder.

    Args:
        foldername: Name/path of folder to create.
    """
    try:
        folderpath = DESKTOP / foldername if not Path(foldername).is_absolute() else Path(foldername)
        if not _is_safe_path(folderpath):
            return {"status": "error", "message": "Access Denied: Path home folder ke bahar hai."}
        folderpath.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created folder: {folderpath}")
        return {"status": "success", "message": f"Folder bana diya: {folderpath.name}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def delete_file(filename: str) -> Dict[str, str]:
    """
    Delete a file or folder.

    Args:
        filename: Name/path of file to delete.
    """
    try:
        filepath = _resolve_path(filename)
        if not _is_safe_path(filepath):
            return {"status": "error", "message": "Access Denied: Path home folder ke bahar hai."}

        if not filepath.exists():
            return {"status": "error", "message": f"'{filename}' nahi mila."}

        if filepath.is_file():
            filepath.unlink()
            logger.info(f"Deleted file: {filepath}")
            return {"status": "success", "message": f"Delete kar diya: {filepath.name}"}
        elif filepath.is_dir():
            shutil.rmtree(filepath)
            logger.info(f"Deleted folder: {filepath}")
            return {"status": "success", "message": f"Folder delete kar diya: {filepath.name}"}

        return {"status": "error", "message": "Delete nahi ho paya."}
    except PermissionError:
        return {"status": "error", "message": f"Permission denied — '{filename}' delete nahi ho sakta."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def rename_file(old_name: str, new_name: str) -> Dict[str, str]:
    """
    Rename a file or folder.

    Args:
        old_name: Current name/path.
        new_name: New name (just filename, not full path).
    """
    try:
        old_path = _resolve_path(old_name)
        if not _is_safe_path(old_path):
            return {"status": "error", "message": "Access Denied: Path home folder ke bahar hai."}

        if not old_path.exists():
            return {"status": "error", "message": f"'{old_name}' nahi mila."}

        # New path in same directory
        new_path = old_path.parent / new_name
        if not _is_safe_path(new_path):
            return {"status": "error", "message": "Access Denied: New path home folder ke bahar hai."}

        old_path.rename(new_path)
        logger.info(f"Renamed: {old_path.name} → {new_path.name}")
        return {"status": "success", "message": f"Rename kar diya: {old_path.name} → {new_path.name}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def move_file(filename: str, destination: str) -> Dict[str, str]:
    """
    Move a file to another location.

    Args:
        filename: File to move.
        destination: Destination folder path.
    """
    try:
        src = _resolve_path(filename)
        if not _is_safe_path(src):
            return {"status": "error", "message": "Access Denied: Source path home folder ke bahar hai."}

        if not src.exists():
            return {"status": "error", "message": f"'{filename}' nahi mila."}

        dest = Path(destination)
        if not dest.is_absolute():
            # Try common folders
            folder_map = {
                "desktop": DESKTOP,
                "documents": DOCUMENTS,
                "downloads": DOWNLOADS,
            }
            dest = folder_map.get(destination.lower(), HOME / destination)

        if not _is_safe_path(dest):
            return {"status": "error", "message": "Access Denied: Destination path home folder ke bahar hai."}

        dest.mkdir(parents=True, exist_ok=True)
        new_path = dest / src.name
        shutil.move(str(src), str(new_path))
        logger.info(f"Moved: {src} → {new_path}")
        return {"status": "success", "message": f"Move kar diya: {src.name} → {dest.name}/"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def copy_file(filename: str, destination: str) -> Dict[str, str]:
    """
    Copy a file to another location.

    Args:
        filename: File to copy.
        destination: Destination folder path.
    """
    try:
        src = _resolve_path(filename)
        if not _is_safe_path(src):
            return {"status": "error", "message": "Access Denied: Source path home folder ke bahar hai."}

        if not src.exists():
            return {"status": "error", "message": f"'{filename}' nahi mila."}

        dest = Path(destination)
        if not dest.is_absolute():
            folder_map = {
                "desktop": DESKTOP,
                "documents": DOCUMENTS,
                "downloads": DOWNLOADS,
            }
            dest = folder_map.get(destination.lower(), HOME / destination)

        if not _is_safe_path(dest):
            return {"status": "error", "message": "Access Denied: Destination path home folder ke bahar hai."}

        dest.mkdir(parents=True, exist_ok=True)
        new_path = dest / src.name

        if src.is_file():
            shutil.copy2(str(src), str(new_path))
        else:
            shutil.copytree(str(src), str(new_path))

        logger.info(f"Copied: {src} → {new_path}")
        return {"status": "success", "message": f"Copy kar diya: {src.name} → {dest.name}/"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_files(folder: str = "") -> Dict[str, str]:
    """
    List files in a folder.

    Args:
        folder: Folder path (defaults to Desktop).
    """
    try:
        if not folder:
            target = DESKTOP
        else:
            target = _resolve_path(folder)
            if not target.is_dir():
                target = DESKTOP

        if not _is_safe_path(target):
            return {"status": "error", "message": "Access Denied: Path home folder ke bahar hai."}

        files = []
        for item in sorted(target.iterdir()):
            icon = "📁" if item.is_dir() else "📄"
            files.append(f"{icon} {item.name}")

        if not files:
            return {"status": "success", "message": f"{target.name} folder khaali hai."}

        file_list = "\n".join(files[:20])  # Max 20 items
        total = len(list(target.iterdir()))
        msg = f"{target.name} mein {total} items hain:\n{file_list}"
        if total > 20:
            msg += f"\n... aur {total - 20} aur"

        return {"status": "success", "message": msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def open_file(filename: str) -> Dict[str, str]:
    """
    Open a file with its default application.

    Args:
        filename: File to open.
    """
    try:
        filepath = _resolve_path(filename)
        if not _is_safe_path(filepath):
            return {"status": "error", "message": "Access Denied: Path home folder ke bahar hai."}

        if not filepath.exists():
            return {"status": "error", "message": f"'{filename}' nahi mila."}

        if platform.system() == "Windows":
            os.startfile(str(filepath))
        else:
            subprocess.Popen(["xdg-open", str(filepath)])

        return {"status": "success", "message": f"Open kar diya: {filepath.name}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def search_file(name: str, location: str = "") -> Dict[str, str]:
    """
    Search for a file or folder by name on the PC.
    Searches Desktop, Documents, Downloads, and all drives.

    Args:
        name: File or folder name to search (partial match works).
        location: Optional specific folder to search in.
    """
    try:
        import subprocess

        results = []

        # If location is provided, make sure it is safe
        if location:
            loc_path = Path(location)
            if not _is_safe_path(loc_path):
                return {"status": "error", "message": "Access Denied: Search location home folder ke bahar hai."}
            search_path = location
        else:
            search_path = str(HOME)

        # Use PowerShell for fast recursive search
        ps_cmd = f'Get-ChildItem -Path "{search_path}" -Recurse -Filter "*{name}*" -ErrorAction SilentlyContinue | Select-Object -First 10 -ExpandProperty FullName'
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=15
        )

        if result.stdout.strip():
            results = result.stdout.strip().split("\n")

        # If not found in home, try all drives
        if not results and not location:
            for drive in ["C:\\", "D:\\", "E:\\"]:
                if Path(drive).exists():
                    # Ignore System folders in search
                    ps_cmd = f'Get-ChildItem -Path "{drive}" -Recurse -Filter "*{name}*" -ErrorAction SilentlyContinue | Where-Object {{ $_.FullName -notmatch "Windows|Program Files|AppData" }} | Select-Object -First 5 -ExpandProperty FullName'
                    result = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", ps_cmd],
                        capture_output=True, text=True, timeout=20
                    )
                    if result.stdout.strip():
                        results.extend(result.stdout.strip().split("\n"))
                        break

        if results:
            # Clean results
            results = [r.strip() for r in results if r.strip()][:10]
            # Verify paths
            safe_results = []
            for r in results:
                r_path = Path(r)
                if r_path.drive.lower() == 'c:':
                    if _is_safe_path(r_path):
                        safe_results.append(r)
                else:
                    if not any(sys_dir in r.lower() for sys_dir in ["windows", "program files", "appdata", "$recycle.bin", "system volume information"]):
                        safe_results.append(r)

            if safe_results:
                msg = f"'{name}' mil gaya! {len(safe_results)} results:\n"
                for i, r in enumerate(safe_results, 1):
                    msg += f"  {i}. {r}\n"
                return {"status": "success", "message": msg, "paths": safe_results}
            else:
                return {"status": "error", "message": f"'{name}' nahi mila PC mein."}
        else:
            return {"status": "error", "message": f"'{name}' nahi mila PC mein."}

    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Search mein zyada time lag raha — try with specific folder."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def search_and_open(name: str) -> Dict[str, str]:
    """
    Search for a file/folder and open the first result.

    Args:
        name: File or folder name to find and open.
    """
    import os as _os

    result = search_file(name)
    if result["status"] == "success" and "paths" in result:
        first_path = result["paths"][0]
        try:
            # Re-verify path safety before opening
            r_path = Path(first_path)
            if r_path.drive.lower() == 'c:' and not _is_safe_path(r_path):
                return {"status": "error", "message": "Access Denied: Path open karne ki permission nahi hai."}
            if any(sys_dir in first_path.lower() for sys_dir in ["windows", "program files", "appdata", "$recycle.bin", "system volume information"]):
                return {"status": "error", "message": "Access Denied: System path open karne ki permission nahi hai."}

            if Path(first_path).is_dir():
                # Open folder in explorer
                _os.startfile(first_path)
            else:
                # Open file with default app
                _os.startfile(first_path)
            return {"status": "success", "message": f"Khol diya: {Path(first_path).name}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    else:
        return result
