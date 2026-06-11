# -*- coding: utf-8 -*-
"""
repository_helpers.py  —  AnalysisHub Backend
==============================================
Compatible: IronPython 2.7 (ANSYS ACT / Workbench 2024 R2+)

v8 changes
----------
* Relative archive_path storage — archive_path stored relative to repo root,
  resolved to absolute at runtime.  Backward-compatible with existing absolute
  paths in older manifests.
* Archive method tag in status strings: [ZIP] / [Copy]
* New status ARCH_STATUS_UNARCHIVED — "Unarchived — Archive when ready"
  shown when source_path was designated from an extraction but has no archive.
* copy_wbpj_with_files_delta — delta copy that only updates changed files,
  skipping unchanged files by mtime comparison. Optionally exclude results.
* copy_wbpj_with_files updated — now accepts include_results parameter.
* Orphaned archive files scan — scan section archive folders and find files
  not referenced by any manifest record.
* remove_file_record updated — returns archive_path so caller can offer
  deletion of the physical archive file.
* zip_extract_to — extracts flat into dest_dir (not into a subfolder).
* update_local_extract, update_source_path, prune_stale_fields,
  get_open_target — carried forward from v7.
"""

import os
import json
import copy
import shutil
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

# ── Archive status strings ───────────────────────────────────────────────────
# Method tags appended at runtime: [ZIP] or [Copy]
ARCH_STATUS_NONE       = "Ready"
ARCH_STATUS_OK         = u"Archived \u2714"
ARCH_STATUS_OUTDATED   = u"Archived \u2718 \u2014 Source Changed"
ARCH_STATUS_MISSING    = "MISSING"
ARCH_STATUS_UNARCHIVED = u"Unarchived \u2014 Archive when ready"

DEFAULT_MANIFEST = {
    "schema_version": 2,
    "project_info": {
        "title": "", "customer": "", "analyst": "",
        "status": "Active", "notes": "", "revision": "Rev 0",
        "created": "", "modified": "",
    },
    "revision_log": [],
    "sections": {sec: [] for sec in ALL_SECTIONS},
}

# ────────────────────────────────────────────────────────────────────────────
#  Logging
# ────────────────────────────────────────────────────────────────────────────

try:
    with open(LOG_PATH, "a") as _fh:
        _fh.write("[{0}] REPO_HELPERS >>> Module loaded\n".format(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
except Exception:
    pass


def _safe_log(msg):
    try:
        with open(LOG_PATH, "a") as fh:
            fh.write("[{0}] REPO_HELPERS >>> {1}\n".format(
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


# ────────────────────────────────────────────────────────────────────────────
#  Base-directory / repo-root  (cached)
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
        _safe_log("Resolved (user_files direct): " + _REPO_ROOT)
        return _REPO_ROOT
    current = base
    for _ in range(10):
        if current.lower().endswith("_files"):
            _REPO_ROOT = os.path.join(current, "user_files", "AnalysisRepository")
            _safe_log("Resolved (via _files walk): " + _REPO_ROOT)
            return _REPO_ROOT
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    sibling = os.path.join(base, os.path.basename(base) + "_files")
    if os.path.isdir(sibling):
        _REPO_ROOT = os.path.join(sibling, "user_files", "AnalysisRepository")
        _safe_log("Resolved (sibling _files): " + _REPO_ROOT)
        return _REPO_ROOT
    _REPO_ROOT = os.path.join(base, "AnalysisRepository")
    _safe_log("Resolved (fallback): " + _REPO_ROOT)
    return _REPO_ROOT


def get_section_archive_dir(section):
    return os.path.join(get_repo_root(), SECTION_MAP.get(section, section))


# ────────────────────────────────────────────────────────────────────────────
#  Relative path helpers  (core of the cross-machine fix)
# ────────────────────────────────────────────────────────────────────────────

def _to_relative_archive_path(abs_path):
    """
    Convert an absolute archive_path to a path relative to repo_root.
    e.g.  .../AnalysisRepository/SupplementalWBDatabase/foo.zip
          ->  SupplementalWBDatabase/foo.zip
    Only converts paths that are inside the repo root.
    """
    try:
        repo = get_repo_root()
        abs_norm  = os.path.normcase(os.path.abspath(abs_path))
        repo_norm = os.path.normcase(os.path.abspath(repo))
        if abs_norm.startswith(repo_norm + os.sep) or abs_norm == repo_norm:
            return os.path.relpath(abs_path, repo)
    except Exception:
        pass
    return abs_path   # return unchanged if outside repo or error


def _resolve_archive_path(stored_path):
    """
    Resolve a stored archive_path to an absolute path on this machine.
    Handles both:
      - Relative paths (new format): join with get_repo_root()
      - Absolute paths (old format): return as-is (backward compat)
    """
    if not stored_path:
        return ""
    if os.path.isabs(stored_path):
        return stored_path          # old absolute path — use as-is
    return os.path.join(get_repo_root(), stored_path)


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
        _safe_log("Created manifest: " + mpath)


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

def _method_tag(method):
    """Return a short display tag for the archive method."""
    if method == "zip":
        return " [ZIP]"
    elif method in ("copy_with_files", "copy"):
        return " [Copy]"
    return ""


def get_archive_status(record):
    """
    Return the archive status string for a record, including method tag.

    Status strings:
        "Ready"                              — no source, no archive
        "Unarchived — Archive when ready"    — has source (extracted), no archive
        "MISSING"                            — source gone, no archive
        "Archived ✔ [ZIP]"                  — archived and current
        "Archived ✔ [Copy]"
        "Archived ✘ — Source Changed [ZIP]" — archived but stale
        "Archived ✘ — Source Changed [Copy]"
    """
    src_path = record.get("source_path", "")
    method   = record.get("archive_method", "")
    tag      = _method_tag(method)

    # Resolve archive path (handles both relative and absolute)
    raw_arch = record.get("archive_path", "")
    arch_abs = _resolve_archive_path(raw_arch)
    has_arch = bool(arch_abs) and os.path.exists(arch_abs)

    src_exists = bool(src_path) and os.path.exists(src_path)

    if not src_exists and not has_arch:
        return ARCH_STATUS_MISSING

    if not src_exists and has_arch:
        # Source gone but archive exists — OK for recipient machines
        return ARCH_STATUS_OK + tag

    # Source exists
    if not has_arch:
        # Check if this was previously designated as working source
        if record.get("_was_extracted_source"):
            return ARCH_STATUS_UNARCHIVED
        return ARCH_STATUS_NONE

    # Both source and archive exist — check if in sync
    try:
        ext = os.path.splitext(src_path)[1].lower()
        if ext == ".wbpj" and method in ("copy_with_files", "zip", "wbpz"):
            current_mtime = get_wbpj_latest_mtime(src_path)
        else:
            current_mtime = os.path.getmtime(src_path)
        if abs(current_mtime - record.get("archive_src_mtime", 0)) > 2:
            return ARCH_STATUS_OUTDATED + tag
    except Exception:
        return ARCH_STATUS_OUTDATED + tag

    return ARCH_STATUS_OK + tag


# ────────────────────────────────────────────────────────────────────────────
#  Size / mtime helpers
# ────────────────────────────────────────────────────────────────────────────

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
    """Max mtime across .wbpj and entire _files tree."""
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
                        t = os.path.getmtime(os.path.join(root, f))
                        if t > latest:
                            latest = t
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
        raise IOError("Source not found: " + src_path)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
    dest_path = os.path.join(dest_dir, os.path.basename(src_path))
    shutil.copy2(src_path, dest_path)
    _safe_log("Archived file: {0} -> {1}".format(src_path, dest_path))
    return dest_path


_RESULT_FILE_EXTENSIONS = {
    ".rst", ".rth", ".rmg", ".rfl",
    ".dat", ".r001", ".esav", ".emat",
    ".db", ".out", ".err",
    ".DSP", ".full", ".sub",
    ".mntr", ".stat",
    ".cas", ".cff", ".res", ".trn",
}


def _is_result_file(rel_path):
    parts = rel_path.replace("/", "\\").split("\\")
    ext   = os.path.splitext(rel_path)[1].lower()
    if len(parts) >= 2 and parts[-2].upper() == "MECH":
        if ext in _RESULT_FILE_EXTENSIONS:
            return True
    return False


def copy_wbpj_with_files(wbpj_path, dest_dir, include_results=False,
                          progress_callback=None):
    """
    Copy a .wbpj and its _files folder into dest_dir (flat, no subfolder).
    Supports optional result file exclusion.
    Returns the destination .wbpj path.
    """
    if not os.path.exists(wbpj_path):
        raise IOError("Source .wbpj not found: " + wbpj_path)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    dest_wbpj = os.path.join(dest_dir, os.path.basename(wbpj_path))
    shutil.copy2(wbpj_path, dest_wbpj)
    _safe_log("Copied .wbpj: " + dest_wbpj)
    if progress_callback:
        progress_callback(os.path.basename(wbpj_path))

    base      = os.path.splitext(wbpj_path)[0]
    files_dir = base + "_files"
    if os.path.isdir(files_dir):
        dest_files = os.path.join(dest_dir, os.path.basename(files_dir))
        if not os.path.exists(dest_files):
            os.makedirs(dest_files)
        for root, dirs, files in os.walk(files_dir):
            dirs.sort()
            files.sort()
            rel_root = os.path.relpath(root, files_dir)
            dest_root = os.path.join(dest_files, rel_root)
            if not os.path.exists(dest_root):
                os.makedirs(dest_root)
            for fname in files:
                src_file  = os.path.join(root, fname)
                # Build rel_path for result-file check
                rel_path  = os.path.join(
                    os.path.basename(files_dir), rel_root, fname)
                if not include_results and _is_result_file(rel_path):
                    continue
                dest_file = os.path.join(dest_root, fname)
                shutil.copy2(src_file, dest_file)
                if progress_callback:
                    progress_callback(fname)
        _safe_log("Copied _files: " + dest_files)

    return dest_wbpj


def copy_wbpj_with_files_delta(wbpj_path, dest_dir, include_results=False,
                                progress_callback=None):
    """
    Delta copy — only copies files newer than existing destination copies.
    Uses mtime comparison with a 2-second tolerance.
    Falls back to full copy for files that don't exist in dest.
    Returns the destination .wbpj path.
    """
    if not os.path.exists(wbpj_path):
        raise IOError("Source .wbpj not found: " + wbpj_path)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    copied = skipped = 0

    # Copy .wbpj itself
    dest_wbpj = os.path.join(dest_dir, os.path.basename(wbpj_path))
    src_mtime = os.path.getmtime(wbpj_path)
    if (not os.path.exists(dest_wbpj) or
            abs(os.path.getmtime(dest_wbpj) - src_mtime) > 2):
        shutil.copy2(wbpj_path, dest_wbpj)
        copied += 1
    else:
        skipped += 1
    if progress_callback:
        progress_callback(os.path.basename(wbpj_path))

    base      = os.path.splitext(wbpj_path)[0]
    files_dir = base + "_files"
    if os.path.isdir(files_dir):
        dest_files = os.path.join(dest_dir, os.path.basename(files_dir))
        for root, dirs, files in os.walk(files_dir):
            dirs.sort()
            files.sort()
            rel_root  = os.path.relpath(root, files_dir)
            dest_root = os.path.join(dest_files, rel_root)
            if not os.path.exists(dest_root):
                os.makedirs(dest_root)
            for fname in files:
                src_file  = os.path.join(root, fname)
                rel_path  = os.path.join(
                    os.path.basename(files_dir), rel_root, fname)
                if not include_results and _is_result_file(rel_path):
                    continue
                dest_file  = os.path.join(dest_root, fname)
                src_mtime2 = os.path.getmtime(src_file)
                if (not os.path.exists(dest_file) or
                        abs(os.path.getmtime(dest_file) - src_mtime2) > 2):
                    shutil.copy2(src_file, dest_file)
                    copied += 1
                    if progress_callback:
                        progress_callback(fname)
                else:
                    skipped += 1

    _safe_log("Delta copy complete: {0} copied, {1} unchanged".format(
        copied, skipped))
    return dest_wbpj


def zip_wbpj_with_files(wbpj_path, dest_dir, include_results=False,
                         progress_callback=None):
    """
    Create a ZIP archive of a .wbpj + _files folder in dest_dir.
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

    # Count total files first so progress bar can be deterministic
    total_files = 1  # the .wbpj itself
    if os.path.isdir(files_dir):
        for root, dirs, files in os.walk(files_dir):
            for fname in files:
                full = os.path.join(root, fname)
                rel  = os.path.relpath(full, base_dir)
                if include_results or not _is_result_file(rel):
                    total_files += 1

    _safe_log("Creating ZIP: {0}  ({1} files, include_results={2})".format(
        zip_path, total_files, include_results))

    file_count = skip_count = 0

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED,
                         allowZip64=True) as zf:
        arcname = os.path.basename(wbpj_path)
        zf.write(wbpj_path, arcname)
        file_count += 1
        if progress_callback:
            progress_callback(arcname, file_count, total_files)

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
                            progress_callback(fname, file_count, total_files)
                    except Exception as exc:
                        _safe_log("ZIP skip {0}: {1}".format(full_path, str(exc)))

    _safe_log("ZIP complete: {0} added, {1} skipped".format(
        file_count, skip_count))
    return zip_path


def zip_extract_to(zip_path, dest_dir, progress_callback=None):
    """
    Extract a .zip archive FLAT into dest_dir (no subfolder created).
    The .wbpj and _files folder land directly inside dest_dir.
    Returns the path to the extracted .wbpj if found, else dest_dir.
    """
    import zipfile

    if not os.path.exists(zip_path):
        raise IOError("ZIP not found: " + zip_path)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    _safe_log("Extracting ZIP flat: {0} -> {1}".format(zip_path, dest_dir))

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        total = len(names)
        for i, name in enumerate(names):
            if progress_callback:
                progress_callback(os.path.basename(name), i + 1, total)
            zf.extract(name, dest_dir)

    # Find extracted .wbpj at root level of dest_dir
    for name in names:
        if name.lower().endswith(".wbpj") and "/" not in name and "\\" not in name:
            wbpj_path = os.path.join(dest_dir, name)
            _safe_log("Extracted .wbpj: " + wbpj_path)
            return wbpj_path

    _safe_log("Extraction complete — no root .wbpj found in: " + dest_dir)
    return dest_dir


# ────────────────────────────────────────────────────────────────────────────
#  Manifest record update helpers
# ────────────────────────────────────────────────────────────────────────────

def update_archive_record(section, index, archive_path, method):
    """
    Write archive metadata into manifest. Stores archive_path as relative.
    """
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

    # Store as RELATIVE path so it works on any machine
    rel_path = _to_relative_archive_path(archive_path)

    records[index]["archive_path"]      = rel_path
    records[index]["archive_date"]      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records[index]["archive_src_mtime"] = src_mtime
    records[index]["archive_src_size"]  = src_size
    records[index]["archive_method"]    = method
    # Clear _was_extracted_source flag if present
    records[index].pop("_was_extracted_source", None)

    save_manifest(data)
    _safe_log("Archive record updated [{0}][{1}]: {2} -> rel={3}".format(
        section, index, archive_path, rel_path))
    return True


def update_local_extract(section, index, extracted_wbpj_path):
    """Save local extraction path for a ZIP-archived record."""
    data    = load_manifest()
    records = data["sections"].get(section, [])
    if index < 0 or index >= len(records):
        return False
    records[index]["local_extract_path"] = extracted_wbpj_path
    records[index]["local_extract_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_manifest(data)
    _safe_log("Local extract saved [{0}][{1}]: {2}".format(
        section, index, extracted_wbpj_path))
    return True


def update_source_path(section, index, new_source_path):
    """
    Update source_path to the extracted copy.
    Clears archive record (source changed) and marks _was_extracted_source
    so get_archive_status shows ARCH_STATUS_UNARCHIVED instead of NONE.
    """
    data    = load_manifest()
    records = data["sections"].get(section, [])
    if index < 0 or index >= len(records):
        return False
    records[index]["source_path"]         = new_source_path
    records[index]["_was_extracted_source"] = True
    for key in ["archive_path", "archive_date", "archive_src_mtime",
                "archive_src_size", "archive_method"]:
        records[index].pop(key, None)
    save_manifest(data)
    _safe_log("source_path updated [{0}][{1}]: {2}".format(
        section, index, new_source_path))
    return True


def prune_stale_fields(section, index):
    """
    Remove source_path and local_extract_path if they don't exist on this machine.
    Returns dict of what was pruned.
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
        _safe_log("Pruned stale source_path [{0}][{1}]".format(section, index))

    ext_path = record.get("local_extract_path", "")
    if ext_path and not os.path.exists(ext_path):
        pruned["local_extract_path"] = ext_path
        records[index].pop("local_extract_path", None)
        records[index].pop("local_extract_date", None)
        changed = True
        _safe_log("Pruned stale local_extract_path [{0}][{1}]".format(
            section, index))

    if changed:
        save_manifest(data)
    return pruned


def get_open_target(record):
    """
    Analyse a record and return a dict describing how it should be opened.
    Resolves relative archive_path to absolute before checking existence.
    """
    src      = record.get("source_path", "")
    raw_arch = record.get("archive_path", "")
    arch     = _resolve_archive_path(raw_arch)
    ext_path = record.get("local_extract_path", "")
    method   = record.get("archive_method", "")
    is_zip   = (method == "zip")

    has_source  = bool(src)  and os.path.exists(src)
    has_archive = bool(arch) and os.path.exists(arch)
    has_extract = bool(ext_path) and os.path.exists(ext_path)

    if is_zip and has_archive:
        if has_extract or has_source:
            # archive_zip mode shows open options including source (if present)
            mode = "archive_zip"
        else:
            # No extraction yet, no source on this machine -- prompt to extract
            mode = "extract_first"
    elif has_archive and not is_zip:
        mode = "archive_direct"
    elif has_source:
        mode = "source"
    else:
        mode = "none"

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
                "local_extract_path", "local_extract_date",
                "_was_extracted_source"]:
        records[index].pop(key, None)
    save_manifest(data)
    _safe_log("Archive record cleared [{0}][{1}]".format(section, index))
    return True


# ────────────────────────────────────────────────────────────────────────────
#  File-record helpers
# ────────────────────────────────────────────────────────────────────────────

def _enrich_record(record):
    """
    Add live display fields to a manifest record.

    Priority rules
    --------------
    - size_mb and modified ALWAYS reflect the SOURCE file when it exists.
      The owner always sees current reference file info for version control.
    - When source is gone (recipient machine), size/modified show dashes.
    - status reflects archive state (see get_archive_status).
    - archive_path_abs, archive_date_disp, archive_method_disp
      are exposed for the UI status column and tooltips.
    """
    r    = dict(record)
    path = r.get("source_path", "")

    arch_abs = _resolve_archive_path(r.get("archive_path", ""))

    if not path or not os.path.exists(path):
        if arch_abs and os.path.exists(arch_abs):
            r["status"] = get_archive_status(record)
        else:
            r["status"] = ARCH_STATUS_MISSING
        r["size_mb"]  = u"\u2014"
        r["modified"] = u"\u2014"
    else:
        # Source exists -- show source file info (owner machine behaviour)
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

    # Expose archive metadata for UI
    r["archive_path_abs"]    = arch_abs
    r["archive_date_disp"]   = record.get("archive_date", "")
    r["archive_method_disp"] = record.get("archive_method", "")
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
    """
    Remove a manifest record.
    Returns the removed record dict (contains archive_path if archived)
    so the caller can offer to delete the physical archive file.
    """
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


def delete_archive_file(record):
    """
    Delete the physical archive file (and folder for copy_with_files).
    Called after the user confirms deletion following remove_file_record.
    Returns True if deleted successfully.
    """
    raw_arch = record.get("archive_path", "")
    arch_abs = _resolve_archive_path(raw_arch)
    method   = record.get("archive_method", "")

    if not arch_abs or not os.path.exists(arch_abs):
        _safe_log("delete_archive_file: nothing to delete at " + str(arch_abs))
        return False

    try:
        os.remove(arch_abs)
        _safe_log("Deleted archive file: " + arch_abs)

        # For copy_with_files, also delete the _files folder
        if method == "copy_with_files":
            base      = os.path.splitext(arch_abs)[0]
            files_dir = base + "_files"
            if os.path.isdir(files_dir):
                shutil.rmtree(files_dir)
                _safe_log("Deleted _files folder: " + files_dir)
        return True
    except Exception as exc:
        _safe_log("delete_archive_file error: " + str(exc))
        return False


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
                    "local_extract_path", "local_extract_date",
                    "_was_extracted_source"]:
            records[index].pop(key, None)
        save_manifest(data)
        _safe_log("Relinked [{0}][{1}]: {2} -> {3}".format(
            section, index, old_path, new_path))
        return True
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
#  Health check  (with orphaned archive file scan)
# ────────────────────────────────────────────────────────────────────────────

def scan_orphaned_archive_files():
    """
    Scan all section archive folders and find files that have no matching
    manifest record.  Returns a list of dicts:
      { "path": absolute_path, "section": section_id, "filename": str }
    """
    data     = load_manifest()
    orphans  = []

    for sec in ALL_SECTIONS:
        arch_dir = get_section_archive_dir(sec)
        if not os.path.isdir(arch_dir):
            continue

        # Collect all archive paths referenced by this section's records
        referenced = set()
        for r in data["sections"].get(sec, []):
            raw  = r.get("archive_path", "")
            abs_ = _resolve_archive_path(raw)
            if abs_:
                referenced.add(os.path.normcase(os.path.abspath(abs_)))
            # Also track _files folder for copy_with_files
            if r.get("archive_method") == "copy_with_files" and abs_:
                files_folder = os.path.splitext(abs_)[0] + "_files"
                referenced.add(os.path.normcase(os.path.abspath(files_folder)))

        # Walk the archive directory (one level only — no deep nesting)
        for entry in os.listdir(arch_dir):
            full = os.path.join(arch_dir, entry)
            norm = os.path.normcase(os.path.abspath(full))
            if norm not in referenced:
                orphans.append({
                    "path":     full,
                    "section":  sec,
                    "filename": entry,
                    "is_dir":   os.path.isdir(full),
                })

    _safe_log("Orphan scan: {0} orphaned items found".format(len(orphans)))
    return orphans


def run_health_check():
    """
    Full health check including orphaned archive file scan.
    """
    result = {
        "total":        0,
        "ready":        0,
        "missing":      0,
        "archived_ok":  0,
        "archived_old": 0,
        "missing_list": [],
        "orphaned":     [],
        "sections":     {},
    }
    data = load_manifest()
    for sec in ALL_SECTIONS:
        records     = data["sections"].get(sec, [])
        sec_total   = len(records)
        sec_missing = 0
        for r in records:
            status = get_archive_status(r)
            arch_abs = _resolve_archive_path(r.get("archive_path", ""))
            has_arch = bool(arch_abs) and os.path.exists(arch_abs)

            if status == ARCH_STATUS_MISSING and not has_arch:
                sec_missing += 1
                result["missing_list"].append({
                    "label":   r.get("label", "Unnamed"),
                    "path":    r.get("source_path", ""),
                    "section": SECTION_LABELS.get(sec, sec),
                })
            if ARCH_STATUS_OK in status:
                result["archived_ok"] += 1
            elif ARCH_STATUS_OUTDATED in status:
                result["archived_old"] += 1

        result["sections"][sec] = {"total": sec_total, "missing": sec_missing}
        result["total"]   += sec_total
        result["missing"] += sec_missing
        result["ready"]   += (sec_total - sec_missing)

    result["orphaned"] = scan_orphaned_archive_files()

    _safe_log("Health check: {0} total, {1} missing, "
              "{2} archived OK, {3} outdated, {4} orphans".format(
                  result["total"], result["missing"],
                  result["archived_ok"], result["archived_old"],
                  len(result["orphaned"])))
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
                "archive_path":          _resolve_archive_path(
                    r.get("archive_path", "")),
                "archive_date":          r.get("archive_date", ""),
                "archive_method":        r.get("archive_method", ""),
            })

    return candidates


# ────────────────────────────────────────────────────────────────────────────
#  WBPZ script (kept for Guided ARCHIVE future use)
# ────────────────────────────────────────────────────────────────────────────

def generate_wbpz_script(wbpj_path, dest_dir,
                         include_results=False, include_external=True,
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
        "wbpj_path=r\"{0}\"".format(wbpj_path),
        "wbpz_path=r\"{0}\"".format(wbpz_path),
        "marker=r\"{0}\"".format(marker_path),
        "if not os.path.exists(r\"{0}\"): os.makedirs(r\"{0}\")".format(dest_dir),
        "Open(FilePath=wbpj_path)",
        "Archive(FilePath=wbpz_path,IncludeResultsFiles={0},"
        "IncludeExternalFiles={1},ArchiveNotes=r\"{2}\")".format(
            "True" if include_results else "False",
            "True" if include_external else "False",
            archive_notes),
        "open(marker,'w').write('done')",
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
        except Exception:
            pass
