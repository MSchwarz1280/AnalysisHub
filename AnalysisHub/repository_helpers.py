# -*- coding: utf-8 -*-
"""
repository_helpers.py  —  AnalysisHub Backend
==============================================
Handles all manifest I/O, file-record management, status checks,
health reporting, and revision tracking for the Analysis Repository.

Compatible: IronPython 2.7 (ANSYS ACT / Workbench 2024 R2+)
No external dependencies beyond Python stdlib + .NET (System).
"""

import os
import json
import copy
import traceback
from datetime import datetime

# .NET is available inside ACT/IronPython environment
import System

# ────────────────────────────────────────────────────────────────────────────
#  Constants & schema
# ────────────────────────────────────────────────────────────────────────────

LOG_PATH = r"C:\Temp\AnalysisHub_debug.log"

# Section identifiers used in code  →  human-readable manifest keys
SECTION_MAP = {
    "main_wb_database":       "MainWBDatabase",
    "supplemental_wb_database": "SupplementalWBDatabase",
    "customer_provided_data":  "CustomerProvidedData",
    "analysis_results":  "AnalysisResults",
    "analysis_reports":  "AnalysisReports",
}

# All supported sections (order controls display order in the UI)
ALL_SECTIONS = ["main_wb_database", "supplemental_wb_database", "customer_provided_data", "analysis_results", "analysis_reports"]

SECTION_LABELS = {
    "main_wb_database":         "Main WB Database",
    "supplemental_wb_database": "Supplemental WB Database",
    "customer_provided_data":   "Customer Provided Data",
    "analysis_results":  "Analysis Results",
    "analysis_reports":  "AnalysisReports",
}

# Blank manifest skeleton — deep-copied on first use
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
    "revision_log": [],    # list of {"revision": str, "date": str, "note": str}
    "sections": {
        "main_wb_database":         [],
        "supplemental_wb_database": [],
        "customer_provided_data":   [],
        "analysis_results":   [],
        "analysis_reports":   [],
    },
}

# ────────────────────────────────────────────────────────────────────────────
#  Logging
# ────────────────────────────────────────────────────────────────────────────

# Append a startup marker each time this module loads (main.py already wrote
# the header, so we just add one line here).
try:
    with open(LOG_PATH, "a") as _fh:
        _fh.write("[{0}] REPO_HELPERS >>> Module loaded / reloaded\n".format(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
except Exception:
    pass


def _safe_log(msg):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = "[{0}] REPO_HELPERS >>> {1}\n".format(ts, msg)
        with open(LOG_PATH, "a") as fh:
            fh.write(line)
    except Exception:
        pass


# ────────────────────────────────────────────────────────────────────────────
#  Base-directory management
# ────────────────────────────────────────────────────────────────────────────

_BASE_DIR  = None   # set by main.py before any repo call
_REPO_ROOT = None   # cached result of get_repo_root() — reset when _BASE_DIR changes


def set_base_directory(path):
    """Called once per session after the project directory is known."""
    global _BASE_DIR, _REPO_ROOT
    new_path = os.path.abspath(path)
    if new_path != _BASE_DIR:          # only log + reset cache when it actually changes
        _BASE_DIR  = new_path
        _REPO_ROOT = None              # force re-resolution on next get_repo_root() call
        _safe_log("set_base_directory -> " + _BASE_DIR)


def get_base_directory():
    if not _BASE_DIR:
        raise RuntimeError(
            "AnalysisHub: set_base_directory() was never called.\n"
            "Open a saved project first, then launch the repository."
        )
    return _BASE_DIR


def get_repo_root():
    """
    Resolve and CACHE the repository root folder.
    Only re-resolves when set_base_directory() is called with a new path.
    Layout: <user_files>\\AnalysisRepository\\
    Since main.py now passes the already-correct user_files path directly
    (via Project.GetProjectFile()), resolution is straightforward.
    """
    global _REPO_ROOT
    if _REPO_ROOT is not None:
        return _REPO_ROOT              # return cached value — no log spam

    base = get_base_directory()
    _safe_log("get_repo_root resolving from: " + base)

    # main.py now always passes the user_files directory directly, so the
    # repo root is simply user_files\AnalysisRepository.
    # The walk-up logic below handles the legacy case where an ActiveDirectory
    # path (which points inside _files) might be passed instead.

    # Case 1: base already ends with "user_files" — direct path from GetProjectFile()
    if os.path.basename(base).lower() == "user_files":
        _REPO_ROOT = os.path.join(base, "AnalysisRepository")
        _safe_log("Resolved repo root (user_files direct): " + _REPO_ROOT)
        return _REPO_ROOT

    # Case 2: walk up to find a _files folder, then go into user_files
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

    # Case 3: check for a sibling _files folder
    basename = os.path.basename(base)
    sibling  = os.path.join(base, basename + "_files")
    if os.path.isdir(sibling):
        _REPO_ROOT = os.path.join(sibling, "user_files", "AnalysisRepository")
        _safe_log("Resolved repo root (via sibling _files): " + _REPO_ROOT)
        return _REPO_ROOT

    # Case 4: last resort — store directly under base
    _REPO_ROOT = os.path.join(base, "AnalysisRepository")
    _safe_log("Resolved repo root (fallback): " + _REPO_ROOT)
    return _REPO_ROOT


# ────────────────────────────────────────────────────────────────────────────
#  Manifest I/O
# ────────────────────────────────────────────────────────────────────────────

def _manifest_path():
    return os.path.join(get_repo_root(), "repository_manifest.json")


def _ensure_repo_dirs():
    """Create the repository folder and a blank manifest if absent."""
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
    # Migrate v1 manifests that lack multi-section support
    if "schema_version" not in data or data["schema_version"] < 2:
        data = _migrate_manifest_v1_to_v2(data)
        save_manifest(data)
        _safe_log("Manifest migrated from v1 to v2")
    return data


def save_manifest(data):
    data["project_info"]["modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_json(_manifest_path(), data)
    _safe_log("Manifest saved")


def _migrate_manifest_v1_to_v2(old):
    """Upgrade an old single-section manifest to the v2 multi-section schema."""
    new = copy.deepcopy(DEFAULT_MANIFEST)
    # Copy project_info fields
    for k in old.get("project_info", {}):
        if k in new["project_info"]:
            new["project_info"][k] = old["project_info"][k]
    # Migrate old "main_wb_database" records
    old_records = old.get("sections", {}).get("main_wb_database", [])
    new["sections"]["main_wb_database"] = old_records
    new["schema_version"] = 2
    return new


# ────────────────────────────────────────────────────────────────────────────
#  File-record helpers
# ────────────────────────────────────────────────────────────────────────────

def _enrich_record(record):
    """
    Add live status, size, and modified date to a record dict.
    Returns a NEW dict (does not mutate the stored record).
    """
    r = dict(record)   # shallow copy
    path = r.get("source_path", "")
    if not path or not os.path.exists(path):
        r["status"]   = "MISSING"
        r["size_mb"]  = "—"
        r["modified"] = "—"
    else:
        r["status"] = "Ready"
        try:
            size_bytes = os.path.getsize(path)
            r["size_mb"] = "{0:.2f}".format(size_bytes / (1024.0 * 1024.0))
        except Exception:
            r["size_mb"] = "—"
        try:
            mtime = os.path.getmtime(path)
            r["modified"] = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except Exception:
            r["modified"] = "—"
    return r


def get_section_records(section):
    """
    Return enriched records for a section (live status computed on the fly).
    Each returned dict has: label, source_path, date_added, category,
    notes, status, size_mb, modified.
    """
    data = load_manifest()
    raw = data["sections"].get(section, [])
    return [_enrich_record(r) for r in raw]


def get_all_records():
    """Return enriched records for all sections, keyed by section id."""
    return {sec: get_section_records(sec) for sec in ALL_SECTIONS}


def add_file_record(section, path, label=None, notes=""):
    """
    Add a file reference to a section.
    Raises ValueError if the path is already tracked in that section.
    """
    if section not in SECTION_MAP:
        raise ValueError("Unknown section: " + section)

    data = load_manifest()
    existing_paths = [r.get("source_path", "") for r in data["sections"].get(section, [])]
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
    """Remove the record at the given index from a section."""
    data = load_manifest()
    records = data["sections"].get(section, [])
    if 0 <= index < len(records):
        removed = records.pop(index)
        data["sections"][section] = records
        save_manifest(data)
        _safe_log("Removed [{0}] index {1}: {2}".format(section, index, removed.get("label", "")))
        return removed
    _safe_log("Remove failed: index {0} out of range for section {1}".format(index, section))
    return None


def update_file_notes(section, index, notes):
    """Update the notes field for a specific record."""
    data = load_manifest()
    records = data["sections"].get(section, [])
    if 0 <= index < len(records):
        records[index]["notes"] = notes
        save_manifest(data)
        return True
    return False

def relink_file_record(section, index, new_path):
    """
    Update the stored file path for a record — used when a file has
    moved and the user browses to its new location via the Relink dialog.
    Also resets the label to the new filename if the label previously
    matched the old filename (i.e. was never manually renamed).
    """
    data = load_manifest()
    records = data["sections"].get(section, [])
    if 0 <= index < len(records):
        old_path  = records[index].get("source_path", "")
        old_label = records[index].get("label", "")
        old_name  = os.path.basename(old_path)
        new_name  = os.path.basename(new_path)

        records[index]["source_path"] = new_path

        # Auto-update the label only if it still matches the old filename
        # (meaning the user never gave it a custom name)
        if old_label == old_name:
            records[index]["label"] = new_name

        save_manifest(data)
        _safe_log("Relinked [{0}] index {1}: {2} -> {3}".format(
            section, index, old_path, new_path))
        return True
    _safe_log("Relink failed: index {0} out of range".format(index))
    return False

def rename_file_record(section, index, new_label):
    """Rename the label of a specific record."""
    data = load_manifest()
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
    data = load_manifest()
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
    """
    Inspect every tracked file and return a summary dict:
      {
        "total": int,
        "ready": int,
        "missing": int,
        "missing_list": [ {label, path, section}, ... ],
        "sections": { section_id: {"total": int, "missing": int} }
      }
    """
    result = {
        "total":        0,
        "ready":        0,
        "missing":      0,
        "missing_list": [],
        "sections":     {},
    }
    data = load_manifest()
    for sec in ALL_SECTIONS:
        records = data["sections"].get(sec, [])
        sec_total   = len(records)
        sec_missing = 0
        for r in records:
            path = r.get("source_path", "")
            if not path or not os.path.exists(path):
                sec_missing += 1
                result["missing_list"].append({
                    "label":   r.get("label", "Unnamed"),
                    "path":    path,
                    "section": SECTION_LABELS.get(sec, sec),
                })
        result["sections"][sec] = {
            "total":   sec_total,
            "missing": sec_missing,
        }
        result["total"]   += sec_total
        result["missing"] += sec_missing
        result["ready"]   += (sec_total - sec_missing)

    _safe_log("Health check: {0} total, {1} missing".format(result["total"], result["missing"]))
    return result


def get_summary_stats():
    """Quick stats tuple (total, missing) for updating task properties."""
    hc = run_health_check()
    return hc["total"], hc["missing"]
