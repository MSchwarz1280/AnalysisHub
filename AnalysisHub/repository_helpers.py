# -*- coding: utf-8 -*-
"""
repository_helpers.py  —  AnalysisHub Backend
==============================================
Handles all manifest I/O, file-record management, status checks,
health reporting, revision tracking, and archive operations.

Compatible: IronPython 2.7 (ANSYS ACT / Workbench 2024 R2+)
No external dependencies beyond Python stdlib + .NET (System).

v7 additions
------------
* zip_extract_to(zip_path, dest_dir)  — extract a ZIP to a chosen directory
* update_local_extract(section, index, wbpj_path)  — save extraction path
* prune_stale_extract(section, index)  — remove stale local_extract_path
* get_open_target(record)  — resolve what to open for a given record
"""

import os
import json
import copy
import shutil
import traceback
from datetime import datetime

import System

# ────────────────────────────────────────────────────────────────────────────
#  Constants & schema
# ────────────────────────────────────────────────────────────────────────────

LOG_PATH = r"C:\Temp\AnalysisHub_debug.log"

SECTION_MAP = {
    "main_wb_database":         "MainWBDatabase",
    "supplemental_wb_database": "SupplementalWBDatabase",
    "customer_provided_data":   "CustomerProvidedData",
    "analysis_results":         "AnalysisResults",
    "analysis_reports":         "AnalysisReports",
}

ALL_SECTIONS = [
    "main_wb_database",
    "supplemental_wb_database",
    "customer_provided_data",
    "analysis_results",
    "analysis_reports",
]

SECTION_LABELS = {
    "main_wb_database":         "Main WB Database",
    "supplemental_wb_database": "Supplemental WB Database",
    "customer_provided_data":   "Customer Provided Data",
    "analysis_results":         "Analysis Results",
    "analysis_reports":         "Analysis Reports",
}

# Archive status strings
ARCH_STATUS_NONE     = "Ready"
ARCH_STATUS_OK       = u"Archived \u2714"
ARCH_STATUS_OUTDATED = u"Archived \u2718 \u2014 Source Changed"
ARCH_STATUS_MISSING  = "MISSING"

DEFAULT_MANIFEST = {
    "schema_version": 2,
    "project_info": {
        "title": "", "customer": "", "analyst": "",
        "status": "Active", "notes": "", "revision": "Rev 0",
        "created": "", "modified": "",
    },
    "revision_log": [],
    "sections": {
        "main_wb_database":         [],
        "supplemental_wb_database": [],
        "customer_provided_data":   [],
        "analysis_results":         [],
        "analysis_reports":         [],
    },
}

# ────────────────────────────────────────────────────────────────────────────
#  Logging
# ────────────────────────────────────────────────────────────────────────────

try:
    with open(LOG_PATH, "a") as _fh:
        _fh.write("[{0}] REPO_HELPERS >>> Module loaded / reloaded\n".format(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
except Exception:
    pass


def _safe_log(msg):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a") as fh:
            fh.write("[{0}] REPO_HELPERS >>> {1}\n".format(ts, msg))
    except Exception:
        pass


# ────────────────────────────────────────────────────────────────────────────
#  Base-directory / repo-root management
# ────────────────────────────────────────────────────────────────────────────

_BASE_DIR  = None
_REPO_ROOT = None


def set_base_directory(path):
    global _BASE_DIR, _REPO_ROOT
    new_path = os.path.abspath(path)
    if new_path != _BASE_DIR:
        _BASE_DIR  = new_path
        _REPO_ROOT = None
        _safe_log("set_base_directory -> " + _BASE_DIR)


def get_base_directory():
    if not _BASE_DIR:
        raise RuntimeError("AnalysisHub: set_base_directory() was never called.")
    return _BASE_DIR


def get_repo_root():
    global _REPO_ROOT
    if _REPO_ROOT is not None:
        return _REPO_ROOT

    base = get_base_directory()
    _safe_log("get_repo_root resolving from: " + base)

    if os.path.basename(base).lower() == "user_files":
        _REPO_ROOT = os.path.join(base, "AnalysisRepository")
        _safe_log("Resolved repo root (user_files direct): " + _REPO_ROOT)
        return _REPO_ROOT

    current = base
    for _ in range(10):
        if current.lower().endswith("_files"):
            _REPO_ROOT = os.path.join(current, "user_files", "AnalysisRepository")
            _safe_log("Resolved repo root (via _files walk): " + _REPO_ROOT)
            return _REPO_ROOT
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    sibling = os.path.join(base, os.path.basename(base) + "_files")
    if os.path.isdir(sibling):
        _REPO_ROOT = os.path.join(sibling, "user_files", "AnalysisRepository")
        _safe_log("Resolved repo root (via sibling _files): " + _REPO_ROOT)
        return _REPO_ROOT

    _REPO_ROOT = os.path.join(base, "AnalysisRepository")
    _safe_log("Resolved repo root (fallback): " + _REPO_ROOT)
    return _REPO_ROOT


def get_section_archive_dir(section):
    folder_name = SECTION_MAP.get(section, section)
    return os.path.join(get_repo_root(), folder_name)


# ────────────────────────────────────────────────────────────────────────────
#  Manifest I/O
# ────────────────────────────────────────────────────────────────────────────

def _manifest_path():
    return os.path.join(get_repo_root(), "repository_manifest.json")


def _ensure_repo_dirs():
    root = get_repo_root()
    try:
        System.IO.Directory.CreateDirectory(root)
    except Exception as exc:
        _safe_log("CreateDirectory failed: " + str(exc))
    mpath = _manifest_path()
    if not os.path.exists(mpath):
        blank = copy.deepcopy(DEFAULT_MANIFEST)
        blank["project_info"]["created"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _write_json(mpath, blank)
        _safe_log("Created new manifest at: " + mpath)


def _read_json(path):
    with open(path, "r") as fh:
        return json.load(fh)


def _write_json(path, data):
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)


def load_manifest():
    _ensure_repo_dirs()
    data = _read_json(_manifest_path())
    if "schema_version" not in data or data["schema_version"] < 2:
        data = _migrate_manifest_v1_to_v2(data)
        save_manifest(data)
    for sec in ALL_SECTIONS:
        data["sections"].setdefault(sec, [])
    return data


def save_manifest(data):
    data["project_info"]["modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_json(_manifest_path(), data)
    _safe_log("Manifest saved")


def _migrate_manifest_v1_to_v2(old):
    new = copy.deepcopy(DEFAULT_MANIFEST)
    for k in old.get("project_info", {}):
        if k in new["project_info"]:
            new["project_info"][k] = old["project_info"][k]
    new["sections"]["main_wb_database"] = old.get("sections", {}).get(
        "main_wb_database", [])
    new["schema_version"] = 2
    return new


# ────────────────────────────────────────────────────────────────────────────
#  Archive status
# ────────────────────────────────────────────────────────────────────────────

def get_archive_status(record):
    """
    Return archive status for a record.
    For .wbpj records uses full _files tree mtime for out-of-date detection.
    """
    src_path = record.get("source_path", "")

    if not src_path or not os.path.exists(src_path):
        return ARCH_STATUS_MISSING

    archive_path = record.get("archive_path", "")
    if not archive_path or not os.path.exists(archive_path):
        return ARCH_STATUS_NONE

    try:
        ext    = os.path.splitext(src_path)[1].lower()
        method = record.get("archive_method", "copy")
        if ext == ".wbpj" and method in ("copy_with_files", "zip", "wbpz"):
            current_mtime = get_wbpj_latest_mtime(src_path)
        else:
            current_mtime = os.path.getmtime(src_path)
        if abs(current_mtime - record.get("archive_src_mtime", 0)) > 2:
            return ARCH_STATUS_OUTDATED
    except Exception:
        return ARCH_STATUS_OUTDATED

    return ARCH_STATUS_OK


def get_folder_size(folder_path):
    total = 0
    try:
        for root, dirs, files in os.walk(folder_path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass
    except Exception:
        pass
    return total


def format_size(size_bytes):
    if size_bytes < 1024:
        return "{0} B".format(size_bytes)
    elif size_bytes < 1024 * 1024:
        return "{0:.1f} KB".format(size_bytes / 1024.0)
    elif size_bytes < 1024 * 1024 * 1024:
        return "{0:.1f} MB".format(size_bytes / (1024.0 * 1024))
    else:
        return "{0:.2f} GB".format(size_bytes / (1024.0 * 1024 * 1024))


def get_wbpj_files_size(wbpj_path):
    total = 0
    try:
        total += os.path.getsize(wbpj_path)
    except Exception:
        pass
    files_dir = os.path.splitext(wbpj_path)[0] + "_files"
    if os.path.isdir(files_dir):
        total += get_folder_size(files_dir)
    return total


def get_wbpj_latest_mtime(wbpj_path):
    """Max mtime across .wbpj file and entire _files folder tree."""
    latest = 0.0
    try:
        if os.path.exists(wbpj_path):
            latest = max(latest, os.path.getmtime(wbpj_path))
    except Exception:
        pass
    files_dir = os.path.splitext(wbpj_path)[0] + "_files"
    if os.path.isdir(files_dir):
        try:
            for root, dirs, files in os.walk(files_dir):
                for f in files:
                    try:
                        mtime = os.path.getmtime(os.path.join(root, f))
                        if mtime > latest:
                            latest = mtime
                    except Exception:
                        pass
        except Exception:
            pass
    return latest


# ────────────────────────────────────────────────────────────────────────────
#  Archive operations
# ────────────────────────────────────────────────────────────────────────────

def archive_regular_file(src_path, dest_dir):
    if not os.path.exists(src_path):
        raise IOError("Source file not found: " + src_path)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
    dest_path = os.path.join(dest_dir, os.path.basename(src_path))
    shutil.copy2(src_path, dest_path)
    _safe_log("Archived regular file: {0} -> {1}".format(src_path, dest_path))
    return dest_path


def copy_wbpj_with_files(wbpj_path, dest_dir):
    if not os.path.exists(wbpj_path):
        raise IOError("Source .wbpj not found: " + wbpj_path)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
    dest_wbpj = os.path.join(dest_dir, os.path.basename(wbpj_path))
    shutil.copy2(wbpj_path, dest_wbpj)
    _safe_log("Copied .wbpj: {0} -> {1}".format(wbpj_path, dest_wbpj))
    files_dir  = os.path.splitext(wbpj_path)[0] + "_files"
    if os.path.isdir(files_dir):
        dest_files = os.path.join(dest_dir, os.path.basename(files_dir))
        if os.path.exists(dest_files):
            shutil.rmtree(dest_files)
        shutil.copytree(files_dir, dest_files)
        _safe_log("Copied _files: {0} -> {1}".format(files_dir, dest_files))
    return dest_wbpj


_RESULT_FILE_EXTENSIONS = {
    ".rst", ".rth", ".rmg", ".rfl",
    ".dat", ".r001", ".esav", ".emat",
    ".db", ".out", ".err",
    ".DSP", ".full", ".sub",
    ".mntr", ".stat",
    ".cas", ".dat.gz",
    ".cff", ".res", ".trn",
}


def _is_result_file(rel_path):
    parts = rel_path.replace("/", "\\").split("\\")
    ext   = os.path.splitext(rel_path)[1].lower()
    if len(parts) >= 2:
        if parts[-2].upper() == "MECH" and ext in _RESULT_FILE_EXTENSIONS:
            return True
    return False


def zip_wbpj_with_files(wbpj_path, dest_dir, include_results=False,
                         progress_callback=None):
    """
    Create a ZIP archive of a .wbpj + _files folder.
    Returns the path of the created .zip file.
    """
    import zipfile

    if not os.path.exists(wbpj_path):
        raise IOError("Source .wbpj not found: " + wbpj_path)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    project_name = os.path.splitext(os.path.basename(wbpj_path))[0]
    zip_path     = os.path.join(dest_dir, project_name + ".zip")
    base_dir     = os.path.dirname(wbpj_path)
    files_dir    = os.path.join(base_dir, project_name + "_files")

    _safe_log("Creating ZIP: " + zip_path)
    _safe_log("include_results={0}".format(include_results))

    file_count = skip_count = 0

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED,
                         allowZip64=True) as zf:
        arcname = os.path.basename(wbpj_path)
        zf.write(wbpj_path, arcname)
        file_count += 1
        if progress_callback:
            progress_callback(arcname)

        if os.path.isdir(files_dir):
            for root, dirs, files in os.walk(files_dir):
                dirs.sort()
                files.sort()
                for fname in files:
                    full_path = os.path.join(root, fname)
                    arcname   = os.path.relpath(full_path, base_dir)
                    if not include_results and _is_result_file(arcname):
                        skip_count += 1
                        continue
                    try:
                        zf.write(full_path, arcname)
                        file_count += 1
                        if progress_callback:
                            progress_callback(fname)
                    except Exception as exc:
                        _safe_log("ZIP skip {0}: {1}".format(full_path, str(exc)))

    _safe_log("ZIP complete: {0} added, {1} skipped".format(file_count, skip_count))
    return zip_path


def zip_extract_to(zip_path, dest_dir, progress_callback=None):
    """
    Extract a .zip archive to dest_dir.
    Creates dest_dir if it does not exist.
    Returns the path to the extracted .wbpj file (if found), else dest_dir.
    """
    import zipfile

    if not os.path.exists(zip_path):
        raise IOError("ZIP not found: " + zip_path)

    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    _safe_log("Extracting ZIP: {0} -> {1}".format(zip_path, dest_dir))

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        for name in names:
            if progress_callback:
                progress_callback(os.path.basename(name))
            zf.extract(name, dest_dir)

    # Find the extracted .wbpj
    for name in names:
        if name.lower().endswith(".wbpj") and "/" not in name and "\\" not in name:
            wbpj_path = os.path.join(dest_dir, name)
            _safe_log("Extracted .wbpj: " + wbpj_path)
            return wbpj_path

    _safe_log("Extraction complete (no .wbpj found at root): " + dest_dir)
    return dest_dir


def update_archive_record(section, index, archive_path, method):
    """Write archive metadata into manifest. Handles full _files mtime for .wbpj."""
    data    = load_manifest()
    records = data["sections"].get(section, [])
    if index < 0 or index >= len(records):
        _safe_log("update_archive_record: index out of range")
        return False

    src_path = records[index].get("source_path", "")
    ext      = os.path.splitext(src_path)[1].lower() if src_path else ""

    try:
        if ext == ".wbpj" and method in ("copy_with_files", "zip", "wbpz"):
            src_mtime = get_wbpj_latest_mtime(src_path)
        elif os.path.exists(src_path):
            src_mtime = os.path.getmtime(src_path)
        else:
            src_mtime = 0
    except Exception:
        src_mtime = 0

    try:
        src_size = os.path.getsize(src_path) if os.path.exists(src_path) else 0
    except Exception:
        src_size = 0

    records[index]["archive_path"]      = archive_path
    records[index]["archive_date"]      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records[index]["archive_src_mtime"] = src_mtime
    records[index]["archive_src_size"]  = src_size
    records[index]["archive_method"]    = method

    save_manifest(data)
    _safe_log("Archive record updated [{0}][{1}]: {2}  (mtime={3})".format(
        section, index, archive_path, int(src_mtime)))
    return True


def update_local_extract(section, index, extracted_wbpj_path):
    """
    Save the local extraction path for a ZIP-archived .wbpj record.
    Also optionally updates source_path if the user designates the
    extracted copy as the new working version.
    """
    data    = load_manifest()
    records = data["sections"].get(section, [])
    if index < 0 or index >= len(records):
        _safe_log("update_local_extract: index out of range")
        return False
    records[index]["local_extract_path"] = extracted_wbpj_path
    records[index]["local_extract_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_manifest(data)
    _safe_log("Local extract path saved [{0}][{1}]: {2}".format(
        section, index, extracted_wbpj_path))
    return True


def update_source_path(section, index, new_source_path):
    """Update source_path — called when user designates extracted copy as working source."""
    data    = load_manifest()
    records = data["sections"].get(section, [])
    if index < 0 or index >= len(records):
        return False
    records[index]["source_path"] = new_source_path
    # Clear archive record — source has changed, archive is now stale
    for key in ["archive_path", "archive_date", "archive_src_mtime",
                "archive_src_size", "archive_method"]:
        records[index].pop(key, None)
    save_manifest(data)
    _safe_log("source_path updated [{0}][{1}]: {2}".format(
        section, index, new_source_path))
    return True


def prune_stale_fields(section, index):
    """
    Check source_path and local_extract_path on the current machine.
    Remove any that don't exist on disk (they belonged to another machine).
    Returns a dict of what was pruned.
    """
    data    = load_manifest()
    records = data["sections"].get(section, [])
    if index < 0 or index >= len(records):
        return {}

    record  = records[index]
    pruned  = {}
    changed = False

    src = record.get("source_path", "")
    if src and not os.path.exists(src):
        pruned["source_path"] = src
        records[index].pop("source_path", None)
        changed = True
        _safe_log("Pruned stale source_path [{0}][{1}]: {2}".format(
            section, index, src))

    ext_path = record.get("local_extract_path", "")
    if ext_path and not os.path.exists(ext_path):
        pruned["local_extract_path"] = ext_path
        records[index].pop("local_extract_path", None)
        records[index].pop("local_extract_date", None)
        changed = True
        _safe_log("Pruned stale local_extract_path [{0}][{1}]: {2}".format(
            section, index, ext_path))

    if changed:
        save_manifest(data)

    return pruned


def get_open_target(record):
    """
    Analyse a record and return a dict describing how it should be opened.

    Returns:
    {
        "mode":         "source" | "archive_zip" | "archive_direct" | "extract_first" | "none"
        "source_path":  str or ""   — original reference path (if accessible)
        "archive_path": str or ""   — archive copy path (if exists)
        "extract_path": str or ""   — local extracted .wbpj path (if exists)
        "has_source":   bool
        "has_archive":  bool
        "has_extract":  bool
        "method":       archive method string
        "is_zip":       bool
    }
    """
    src      = record.get("source_path", "")
    arch     = record.get("archive_path", "")
    ext_path = record.get("local_extract_path", "")
    method   = record.get("archive_method", "")
    is_zip   = (method == "zip")

    has_source  = bool(src)  and os.path.exists(src)
    has_archive = bool(arch) and os.path.exists(arch)
    has_extract = bool(ext_path) and os.path.exists(ext_path)

    if is_zip and has_archive:
        if has_extract:
            mode = "archive_zip"      # show "open existing / re-extract / different location"
        else:
            mode = "extract_first"    # prompt for extraction location
    elif has_archive and not is_zip:
        if has_source:
            mode = "archive_direct"   # show "open source / open archive copy" choice
        else:
            mode = "archive_direct"   # only archive available — open it directly
    elif has_source:
        mode = "source"               # no archive — open source directly
    else:
        mode = "none"                 # nothing accessible

    return {
        "mode":         mode,
        "source_path":  src,
        "archive_path": arch,
        "extract_path": ext_path,
        "has_source":   has_source,
        "has_archive":  has_archive,
        "has_extract":  has_extract,
        "method":       method,
        "is_zip":       is_zip,
    }


def clear_archive_record(section, index):
    data    = load_manifest()
    records = data["sections"].get(section, [])
    if index < 0 or index >= len(records):
        return False
    for key in ["archive_path", "archive_date", "archive_src_mtime",
                "archive_src_size", "archive_method",
                "local_extract_path", "local_extract_date"]:
        records[index].pop(key, None)
    save_manifest(data)
    _safe_log("Archive record cleared [{0}][{1}]".format(section, index))
    return True


# ────────────────────────────────────────────────────────────────────────────
#  File-record helpers
# ────────────────────────────────────────────────────────────────────────────

def _enrich_record(record):
    r    = dict(record)
    path = r.get("source_path", "")

    if not path or not os.path.exists(path):
        # Check if an archive copy exists to determine status
        arch = r.get("archive_path", "")
        if arch and os.path.exists(arch):
            r["status"] = ARCH_STATUS_OK   # source gone but archive present
        else:
            r["status"] = ARCH_STATUS_MISSING
        r["size_mb"]  = u"\u2014"
        r["modified"] = u"\u2014"
    else:
        r["status"] = get_archive_status(record)
        try:
            r["size_mb"] = "{0:.2f}".format(
                os.path.getsize(path) / (1024.0 * 1024.0))
        except Exception:
            r["size_mb"] = u"\u2014"
        try:
            r["modified"] = datetime.fromtimestamp(
                os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
        except Exception:
            r["modified"] = u"\u2014"

    return r


def get_section_records(section):
    data = load_manifest()
    raw  = data["sections"].get(section, [])
    return [_enrich_record(r) for r in raw]


def get_all_records():
    return {sec: get_section_records(sec) for sec in ALL_SECTIONS}


def add_file_record(section, path, label=None, notes=""):
    if section not in SECTION_MAP:
        raise ValueError("Unknown section: " + section)
    data = load_manifest()
    existing = [r.get("source_path", "") for r in data["sections"].get(section, [])]
    if path in existing:
        _safe_log("Duplicate skip: " + path)
        return None
    record = {
        "label":       label or os.path.basename(path),
        "source_path": path,
        "date_added":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "category":    section,
        "notes":       notes,
    }
    data["sections"][section].append(record)
    save_manifest(data)
    _safe_log("Added: {0} -> {1}".format(section, path))
    return record


def remove_file_record(section, index):
    data    = load_manifest()
    records = data["sections"].get(section, [])
    if 0 <= index < len(records):
        removed = records.pop(index)
        data["sections"][section] = records
        save_manifest(data)
        _safe_log("Removed [{0}][{1}]: {2}".format(
            section, index, removed.get("label", "")))
        return removed
    _safe_log("Remove failed: index out of range")
    return None


def update_file_notes(section, index, notes):
    data    = load_manifest()
    records = data["sections"].get(section, [])
    if 0 <= index < len(records):
        records[index]["notes"] = notes
        save_manifest(data)
        return True
    return False


def relink_file_record(section, index, new_path):
    data    = load_manifest()
    records = data["sections"].get(section, [])
    if 0 <= index < len(records):
        old_path  = records[index].get("source_path", "")
        old_label = records[index].get("label", "")
        if old_label == os.path.basename(old_path):
            records[index]["label"] = os.path.basename(new_path)
        records[index]["source_path"] = new_path
        for key in ["archive_path", "archive_date", "archive_src_mtime",
                    "archive_src_size", "archive_method",
                    "local_extract_path", "local_extract_date"]:
            records[index].pop(key, None)
        save_manifest(data)
        _safe_log("Relinked [{0}][{1}]: {2} -> {3}".format(
            section, index, old_path, new_path))
        return True
    _safe_log("Relink failed: index out of range")
    return False


def rename_file_record(section, index, new_label):
    data    = load_manifest()
    records = data["sections"].get(section, [])
    if 0 <= index < len(records):
        records[index]["label"] = new_label
        save_manifest(data)
        return True
    return False


# ────────────────────────────────────────────────────────────────────────────
#  Project info / revision
# ────────────────────────────────────────────────────────────────────────────

def get_project_info():
    return load_manifest().get("project_info", {})


def save_project_info(info_dict):
    data = load_manifest()
    data["project_info"].update(info_dict)
    save_manifest(data)


def add_revision_entry(revision, note=""):
    data  = load_manifest()
    entry = {
        "revision": revision,
        "date":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note":     note,
    }
    data.setdefault("revision_log", []).append(entry)
    data["project_info"]["revision"] = revision
    save_manifest(data)
    _safe_log("Revision added: " + revision)


def get_revision_log():
    return load_manifest().get("revision_log", [])


# ────────────────────────────────────────────────────────────────────────────
#  Health check / statistics
# ────────────────────────────────────────────────────────────────────────────

def run_health_check():
    result = {
        "total": 0, "ready": 0, "missing": 0,
        "archived_ok": 0, "archived_old": 0,
        "missing_list": [], "sections": {},
    }
    data = load_manifest()
    for sec in ALL_SECTIONS:
        records     = data["sections"].get(sec, [])
        sec_total   = len(records)
        sec_missing = 0
        for r in records:
            status = get_archive_status(r)
            if status == ARCH_STATUS_MISSING:
                # Only count as missing if no archive copy either
                arch = r.get("archive_path", "")
                if not arch or not os.path.exists(arch):
                    sec_missing += 1
                    result["missing_list"].append({
                        "label":   r.get("label", "Unnamed"),
                        "path":    r.get("source_path", ""),
                        "section": SECTION_LABELS.get(sec, sec),
                    })
                else:
                    result["archived_ok"] += 1
            elif status == ARCH_STATUS_OK:
                result["archived_ok"] += 1
            elif status == ARCH_STATUS_OUTDATED:
                result["archived_old"] += 1

        result["sections"][sec] = {"total": sec_total, "missing": sec_missing}
        result["total"]   += sec_total
        result["missing"] += sec_missing
        result["ready"]   += (sec_total - sec_missing)

    _safe_log("Health check: {0} total, {1} missing, {2} archived OK, "
              "{3} archived outdated".format(
                  result["total"], result["missing"],
                  result["archived_ok"], result["archived_old"]))
    return result


def get_summary_stats():
    hc = run_health_check()
    return hc["total"], hc["missing"]


# ────────────────────────────────────────────────────────────────────────────
#  Archive candidate builder
# ────────────────────────────────────────────────────────────────────────────

def get_archive_candidates(open_project_path=None):
    open_norm = (os.path.normcase(os.path.abspath(open_project_path))
                 if open_project_path else None)

    data       = load_manifest()
    candidates = []

    for sec in ALL_SECTIONS:
        records = data["sections"].get(sec, [])
        for i, r in enumerate(records):
            src = r.get("source_path", "")
            if not src:
                continue
            if open_norm:
                try:
                    if os.path.normcase(os.path.abspath(src)) == open_norm:
                        continue
                except Exception:
                    pass

            ext     = os.path.splitext(src)[1].lower()
            is_wbpj = (ext == ".wbpj")

            src_size = 0
            try:
                if os.path.exists(src):
                    src_size = os.path.getsize(src)
            except Exception:
                pass

            wbpj_total = get_wbpj_files_size(src) if is_wbpj else 0

            candidates.append({
                "section":               sec,
                "section_label":         SECTION_LABELS.get(sec, sec),
                "index":                 i,
                "label":                 r.get("label", os.path.basename(src)),
                "source_path":           src,
                "ext":                   ext,
                "is_wbpj":               is_wbpj,
                "archive_status":        get_archive_status(r),
                "source_size_bytes":     src_size,
                "source_size_str":       format_size(src_size),
                "wbpj_total_size_bytes": wbpj_total,
                "wbpj_total_size_str":   format_size(wbpj_total),
                "archive_path":          r.get("archive_path", ""),
                "archive_date":          r.get("archive_date", ""),
                "archive_method":        r.get("archive_method", ""),
            })

    return candidates


# ────────────────────────────────────────────────────────────────────────────
#  WBPZ batch script (kept for future Guided ARCHIVE use)
# ────────────────────────────────────────────────────────────────────────────

def generate_wbpz_script(wbpj_path, dest_dir,
                         include_results=False,
                         include_external=True,
                         archive_notes="Archived via AnalysisHub"):
    import re
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
    project_name = os.path.splitext(os.path.basename(wbpj_path))[0]
    safe_name    = re.sub(r"[^A-Za-z0-9_]", "_", project_name)
    script_path  = r"C:\Temp\AnalysisHub_archive_{0}.py".format(safe_name)
    marker_path  = r"C:\Temp\AnalysisHub_archive_{0}.done".format(safe_name)
    wbpz_path    = os.path.join(dest_dir, project_name + ".wbpz")

    lines = [
        "import os",
        "wbpj_path   = r\"{0}\"".format(wbpj_path),
        "wbpz_path   = r\"{0}\"".format(wbpz_path),
        "marker_path = r\"{0}\"".format(marker_path),
        "if not os.path.exists(r\"{0}\"): os.makedirs(r\"{0}\")".format(dest_dir),
        "Open(FilePath=wbpj_path)",
        "Archive(FilePath=wbpz_path, IncludeResultsFiles={0}, "
        "IncludeExternalFiles={1}, ArchiveNotes=r\"{2}\")".format(
            "True" if include_results else "False",
            "True" if include_external else "False",
            archive_notes),
        "open(marker_path, 'w').write('done')",
    ]
    with open(script_path, "w") as fh:
        fh.write("\n".join(lines))
    _safe_log("Generated ARCHIVE script: " + script_path)
    return script_path, wbpz_path, marker_path


def cleanup_archive_script(script_path):
    for path in [script_path, script_path.replace(".py", ".done")]:
        try:
            if os.path.exists(path):
                os.remove(path)
                _safe_log("Removed temp file: " + path)
        except Exception as exc:
            _safe_log("Could not remove: " + str(exc))
