# -*- coding: utf-8 -*-
"""
repository_helpers.py  —  AnalysisHub Backend
==============================================
Handles all manifest I/O, file-record management, status checks,
health reporting, revision tracking, and archive operations.

Compatible: IronPython 2.7 (ANSYS ACT / Workbench 2024 R2+)
No external dependencies beyond Python stdlib + .NET (System).

Archive additions
-----------------
* get_archive_status(record)        — returns archive state string
* get_folder_size(path)             — recursive folder size in bytes
* archive_regular_file(...)         — copy a non-.wbpj file into archive folder
* copy_wbpj_with_files(...)         — copy .wbpj + _files folder
* generate_wbpz_script(...)         — write the RunWB2 batch Python script
* update_archive_record(...)        — write archive metadata back to manifest
* get_open_project_path()           — return currently open .wbpj path
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

# Archive status strings — used in the main ListView Status column
ARCH_STATUS_NONE      = "Ready"                      # no archive copy
ARCH_STATUS_OK        = u"Archived \u2714"           # archive up to date
ARCH_STATUS_OUTDATED  = u"Archived \u2718 \u2014 Source Changed"  # source changed
ARCH_STATUS_MISSING   = "MISSING"                    # source file not found

DEFAULT_MANIFEST = {
    "schema_version": 2,
    "project_info": {
        "title":    "",
        "customer": "",
        "analyst":  "",
        "status":   "Active",
        "notes":    "",
        "revision": "Rev 0",
        "created":  "",
        "modified": "",
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
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = "[{0}] REPO_HELPERS >>> {1}\n".format(ts, msg)
        with open(LOG_PATH, "a") as fh:
            fh.write(line)
    except Exception:
        pass


# ────────────────────────────────────────────────────────────────────────────
#  Base-directory management  (cached to avoid log spam)
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
        raise RuntimeError(
            "AnalysisHub: set_base_directory() was never called.")
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
    """
    Return the archive destination folder for a section.
    Layout: <repo_root>/<SectionFolderName>/
    e.g.   .../AnalysisRepository/MainWBDatabase/
    """
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
        blank["project_info"]["created"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S")
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
    # Ensure new sections exist in older manifests
    for sec in ALL_SECTIONS:
        data["sections"].setdefault(sec, [])
    return data


def save_manifest(data):
    data["project_info"]["modified"] = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S")
    _write_json(_manifest_path(), data)
    _safe_log("Manifest saved")


def _migrate_manifest_v1_to_v2(old):
    new = copy.deepcopy(DEFAULT_MANIFEST)
    for k in old.get("project_info", {}):
        if k in new["project_info"]:
            new["project_info"][k] = old["project_info"][k]
    old_records = old.get("sections", {}).get("main_wb_database", [])
    new["sections"]["main_wb_database"] = old_records
    new["schema_version"] = 2
    return new


# ────────────────────────────────────────────────────────────────────────────
#  Archive status helpers
# ────────────────────────────────────────────────────────────────────────────

def get_archive_status(record):
    """
    Return the archive status string for a record.
    Checks whether source file exists, whether an archive copy exists,
    and whether the source has changed since archiving.

    Returns one of:
        ARCH_STATUS_MISSING   — source file not found
        ARCH_STATUS_NONE      — no archive copy (Ready)
        ARCH_STATUS_OK        — archived and up to date
        ARCH_STATUS_OUTDATED  — archived but source has changed
    """
    src_path = record.get("source_path", "")

    if not src_path or not os.path.exists(src_path):
        return ARCH_STATUS_MISSING

    archive_path = record.get("archive_path", "")
    if not archive_path or not os.path.exists(archive_path):
        return ARCH_STATUS_NONE

    # Compare source modification time against recorded archive timestamp
    try:
        current_mtime = os.path.getmtime(src_path)
        archived_mtime = record.get("archive_src_mtime", 0)
        # Allow 2-second tolerance for filesystem timestamp rounding
        if abs(current_mtime - archived_mtime) > 2:
            return ARCH_STATUS_OUTDATED
    except Exception:
        return ARCH_STATUS_OUTDATED

    return ARCH_STATUS_OK


def get_folder_size(folder_path):
    """Return total size of a folder and all its contents in bytes."""
    total = 0
    try:
        for root, dirs, files in os.walk(folder_path):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    total += os.path.getsize(fp)
                except Exception:
                    pass
    except Exception:
        pass
    return total


def format_size(size_bytes):
    """Format bytes as a human-readable string."""
    if size_bytes < 1024:
        return "{0} B".format(size_bytes)
    elif size_bytes < 1024 * 1024:
        return "{0:.1f} KB".format(size_bytes / 1024.0)
    elif size_bytes < 1024 * 1024 * 1024:
        return "{0:.1f} MB".format(size_bytes / (1024.0 * 1024))
    else:
        return "{0:.2f} GB".format(size_bytes / (1024.0 * 1024 * 1024))


def get_wbpj_files_size(wbpj_path):
    """
    Return the estimated archive size for a .wbpj file.
    This is the size of the associated _files folder if it exists,
    plus the .wbpj file itself.
    """
    total = 0
    try:
        total += os.path.getsize(wbpj_path)
    except Exception:
        pass

    base      = os.path.splitext(wbpj_path)[0]
    files_dir = base + "_files"
    if os.path.isdir(files_dir):
        total += get_folder_size(files_dir)

    return total


def get_open_project_path():
    """
    Return the full path of the currently open .wbpj, or None.
    Called from main.py context where Project is available.
    This function is a stub — the actual call is made in main.py
    and passed in where needed.
    """
    return None   # overridden by main.py


# ────────────────────────────────────────────────────────────────────────────
#  Archive operations
# ────────────────────────────────────────────────────────────────────────────

def archive_regular_file(src_path, dest_dir):
    """
    Copy a regular (non-.wbpj) file into dest_dir.
    Returns the destination path on success, raises on failure.
    """
    if not os.path.exists(src_path):
        raise IOError("Source file not found: " + src_path)

    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    filename = os.path.basename(src_path)
    dest_path = os.path.join(dest_dir, filename)
    shutil.copy2(src_path, dest_path)
    _safe_log("Archived regular file: {0} -> {1}".format(src_path, dest_path))
    return dest_path


def copy_wbpj_with_files(wbpj_path, dest_dir):
    """
    Copy a .wbpj file AND its associated _files folder into dest_dir.
    The relative structure is preserved so references remain intact.
    Returns the destination .wbpj path on success, raises on failure.
    """
    if not os.path.exists(wbpj_path):
        raise IOError("Source .wbpj not found: " + wbpj_path)

    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    filename   = os.path.basename(wbpj_path)
    dest_wbpj  = os.path.join(dest_dir, filename)
    shutil.copy2(wbpj_path, dest_wbpj)
    _safe_log("Copied .wbpj: {0} -> {1}".format(wbpj_path, dest_wbpj))

    # Copy _files folder if it exists
    base      = os.path.splitext(wbpj_path)[0]
    files_dir = base + "_files"
    if os.path.isdir(files_dir):
        dest_files = os.path.join(dest_dir,
                                  os.path.basename(files_dir))
        if os.path.exists(dest_files):
            shutil.rmtree(dest_files)
        shutil.copytree(files_dir, dest_files)
        _safe_log("Copied _files folder: {0} -> {1}".format(
            files_dir, dest_files))

    return dest_wbpj


def generate_wbpz_script(wbpj_path, dest_dir,
                         include_results=False,
                         include_external=True,
                         archive_notes="Archived via AnalysisHub"):
    """
    Write a temporary RunWB2 batch Python script that opens the specified
    .wbpj and produces a .wbpz archive in dest_dir.

    Returns (script_path, expected_wbpz_path).
    """
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    project_name = os.path.splitext(os.path.basename(wbpj_path))[0]
    wbpz_path    = os.path.join(dest_dir, project_name + ".wbpz")

    # Write script to temp location alongside the manifest
    script_path  = os.path.join(get_repo_root(),
                                "_archive_temp_{0}.py".format(project_name))

    # Completion marker — written at the very end of the script.
    # main.py checks for this file to distinguish "script ran but failed"
    # from "RunWB2 crashed before the script ran at all".
    marker_path = script_path.replace(".py", ".done")

    script_lines = [
        "# AnalysisHub --- auto-generated ARCHIVE script",
        "# Generated: {0}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "# DO NOT EDIT - regenerated each time",
        "import os",
        "",
        "wbpj_path   = r\"{0}\"".format(wbpj_path),
        "dest_dir    = r\"{0}\"".format(dest_dir),
        "wbpz_path   = r\"{0}\"".format(wbpz_path),
        "marker_path = r\"{0}\"".format(marker_path),
        "",
        "print('[AnalysisHub] Ensuring dest_dir exists...')",
        "if not os.path.exists(dest_dir):",
        "    os.makedirs(dest_dir)",
        "",
        "print('[AnalysisHub] Opening: ' + wbpj_path)",
        "Open(FilePath=wbpj_path)",
        "print('[AnalysisHub] Project opened successfully')",
        "",
        "print('[AnalysisHub] Starting ARCHIVE to: ' + wbpz_path)",
        "Archive(",
        "    FilePath=wbpz_path,",
        "    IncludeResultsFiles={0},".format(
            "True" if include_results else "False"),
        "    IncludeExternalFiles={0},".format(
            "True" if include_external else "False"),
        "    ArchiveNotes=r\"{0}\"".format(archive_notes),
        ")",
        "print('[AnalysisHub] ARCHIVE complete: ' + wbpz_path)",
        "",
        "# Write completion marker so caller knows script ran to end",
        "with open(marker_path, 'w') as _mf:",
        "    _mf.write('done')",
        "print('[AnalysisHub] Marker written: ' + marker_path)",
    ]

    with open(script_path, "w") as fh:
        fh.write("\n".join(script_lines))

    _safe_log("Generated ARCHIVE script: " + script_path)
    _safe_log("Expected .wbpz output:    " + wbpz_path)
    _safe_log("Completion marker path:   " + marker_path)
    return script_path, wbpz_path, marker_path


def cleanup_archive_script(script_path):
    """Remove a temporary archive script and its completion marker after use."""
    for path in [script_path, script_path.replace(".py", ".done")]:
        try:
            if os.path.exists(path):
                os.remove(path)
                _safe_log("Removed temp file: " + path)
        except Exception as exc:
            _safe_log("Could not remove temp file: " + str(exc))


def update_archive_record(section, index, archive_path, method):
    """
    Write archive metadata into the manifest record at [section][index].

    method: "wbpz" | "copy_with_files" | "copy"
    """
    data    = load_manifest()
    records = data["sections"].get(section, [])
    if index < 0 or index >= len(records):
        _safe_log("update_archive_record: index out of range")
        return False

    src_path = records[index].get("source_path", "")
    try:
        src_mtime = os.path.getmtime(src_path) if os.path.exists(src_path) else 0
        src_size  = os.path.getsize(src_path)  if os.path.exists(src_path) else 0
    except Exception:
        src_mtime = 0
        src_size  = 0

    records[index]["archive_path"]      = archive_path
    records[index]["archive_date"]      = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S")
    records[index]["archive_src_mtime"] = src_mtime
    records[index]["archive_src_size"]  = src_size
    records[index]["archive_method"]    = method

    save_manifest(data)
    _safe_log("Archive record updated [{0}][{1}]: {2}".format(
        section, index, archive_path))
    return True


def clear_archive_record(section, index):
    """Remove archive metadata from a record (used when archive copy is deleted)."""
    data    = load_manifest()
    records = data["sections"].get(section, [])
    if index < 0 or index >= len(records):
        return False
    for key in ["archive_path", "archive_date",
                "archive_src_mtime", "archive_src_size", "archive_method"]:
        records[index].pop(key, None)
    save_manifest(data)
    _safe_log("Archive record cleared [{0}][{1}]".format(section, index))
    return True


# ────────────────────────────────────────────────────────────────────────────
#  File-record helpers
# ────────────────────────────────────────────────────────────────────────────

def _enrich_record(record):
    """
    Add live status, size, modified date, and archive status to a record.
    Returns a NEW dict (does not mutate the stored record).
    """
    r    = dict(record)
    path = r.get("source_path", "")

    if not path or not os.path.exists(path):
        r["status"]   = ARCH_STATUS_MISSING
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
    data           = load_manifest()
    existing_paths = [r.get("source_path", "")
                      for r in data["sections"].get(section, [])]
    if path in existing_paths:
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
        _safe_log("Removed [{0}] index {1}: {2}".format(
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
    """Update the stored file path for a record after the user relocates it."""
    data    = load_manifest()
    records = data["sections"].get(section, [])
    if 0 <= index < len(records):
        old_path  = records[index].get("source_path", "")
        old_label = records[index].get("label", "")
        old_name  = os.path.basename(old_path)
        new_name  = os.path.basename(new_path)

        records[index]["source_path"] = new_path
        if old_label == old_name:
            records[index]["label"] = new_name

        # Clear stale archive metadata — the source has moved
        for key in ["archive_path", "archive_date",
                    "archive_src_mtime", "archive_src_size", "archive_method"]:
            records[index].pop(key, None)

        save_manifest(data)
        _safe_log("Relinked [{0}] index {1}: {2} -> {3}".format(
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
#  Project info
# ────────────────────────────────────────────────────────────────────────────

def get_project_info():
    return load_manifest().get("project_info", {})


def save_project_info(info_dict):
    data = load_manifest()
    data["project_info"].update(info_dict)
    save_manifest(data)


# ────────────────────────────────────────────────────────────────────────────
#  Revision log
# ────────────────────────────────────────────────────────────────────────────

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
        "total":        0,
        "ready":        0,
        "missing":      0,
        "archived_ok":  0,
        "archived_old": 0,
        "missing_list": [],
        "sections":     {},
    }
    data = load_manifest()
    for sec in ALL_SECTIONS:
        records     = data["sections"].get(sec, [])
        sec_total   = len(records)
        sec_missing = 0
        for r in records:
            status = get_archive_status(r)
            if status == ARCH_STATUS_MISSING:
                sec_missing += 1
                result["missing_list"].append({
                    "label":   r.get("label", "Unnamed"),
                    "path":    r.get("source_path", ""),
                    "section": SECTION_LABELS.get(sec, sec),
                })
            elif status == ARCH_STATUS_OK:
                result["archived_ok"] += 1
            elif status == ARCH_STATUS_OUTDATED:
                result["archived_old"] += 1

        result["sections"][sec] = {
            "total":   sec_total,
            "missing": sec_missing,
        }
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
    """
    Return a list of dicts describing every tracked file that is eligible
    for archiving (i.e. not the currently open project).

    Each dict contains:
        section, section_label, index, label, source_path, ext,
        is_wbpj, archive_status, source_size_bytes, source_size_str,
        wbpj_total_size_bytes, wbpj_total_size_str,
        archive_path, archive_date, archive_method
    """
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

            # Skip the currently open project
            if open_norm:
                try:
                    if os.path.normcase(os.path.abspath(src)) == open_norm:
                        _safe_log("Skipping open project from archive candidates: "
                                  + src)
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

            wbpj_total = 0
            if is_wbpj:
                wbpj_total = get_wbpj_files_size(src)

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
