# -*- coding: utf-8 -*-
"""
main.py  —  AnalysisHub ACT Extension  (Entry Point)
=====================================================
IronPython 2.7 / ANSYS Workbench 2024 R2+

Cumulative changes in this version
-----------------------------------
* Archive feature:
  - Status dropdown "Archived" triggers archive workflow
  - ArchiveDialog: checklist of all eligible files with sizes,
    Check All / Uncheck All, .wbpj options panel, 1 GB warnings
  - Regular files: copied via shutil.copy2
  - .wbpj files: archived via RunWB2 batch process (Open->Archive->exit)
    OR copied with _files folder — user chooses
  - Progress dialog shown while RunWB2 batch runs
  - Manifest updated with archive_path, archive_date, archive_src_mtime
  - Main list Status column shows: Ready / Archived ✔ / Archived ✘ / MISSING
  - Toolbar "Archive Files" button — accessible at any time
  - Open-project .wbpj excluded from archive candidates automatically
* Health Check dialog with inline Relink
* Column sort per tab
* Right-click context menu with Relink
* Active tab blue/bold drawing, tab padding
* Bold column headers, HeaderStyle.Clickable
"""

import os
import sys
import datetime
import traceback

import System
import clr

clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")

import System.Windows.Forms as WinForms
import System.Drawing        as Drawing

try:
    _EXT_DIR = os.path.join(ExtAPI.Extension.InstallDir, "AnalysisHub")
    if _EXT_DIR not in sys.path:
        sys.path.insert(0, _EXT_DIR)
except Exception:
    pass

import repository_helpers as repo

# ────────────────────────────────────────────────────────────────────────────
#  Logging
# ────────────────────────────────────────────────────────────────────────────

LOG_PATH = r"C:\Temp\AnalysisHub_debug.log"

try:
    with open(LOG_PATH, "w") as _fh:
        _fh.write("=" * 80 + "\n")
        _fh.write("  AnalysisHub  -  Module loaded: {0}\n".format(
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        _fh.write("=" * 80 + "\n")
except Exception:
    pass


def _log(msg):
    try:
        ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = "[{0}] MAIN >>> {1}\n".format(ts, msg)
        with open(LOG_PATH, "a") as fh:
            fh.write(line)
        print(line.rstrip())
    except Exception:
        pass


# ────────────────────────────────────────────────────────────────────────────
#  Project-directory resolution
# ────────────────────────────────────────────────────────────────────────────

def _resolve_project_dir(task=None):
    try:
        wbpj_path = Project.GetProjectFile()
        if wbpj_path and wbpj_path.strip():
            wbpj_path  = wbpj_path.strip()
            proj_dir   = wbpj_path[:wbpj_path.rfind("\\")]
            proj_name  = wbpj_path[wbpj_path.rfind("\\") + 1:-5]
            user_files = proj_dir + "\\" + proj_name + "_files\\user_files"
            _log("Resolved user_files: " + user_files)
            if os.path.exists(proj_dir):
                return user_files
    except Exception as exc:
        _log("Project.GetProjectFile() failed: " + str(exc))

    if task is not None:
        try:
            ad = task.ActiveDirectory
            if ad and os.path.isdir(ad):
                return ad
        except Exception:
            pass

    try:
        for tg in ExtAPI.DataModel.TaskGroups:
            if tg.Name == "AnalysisHubGroup":
                for t in tg.Tasks:
                    ad = t.ActiveDirectory
                    if ad and os.path.isdir(ad):
                        return ad
    except Exception:
        pass

    _log("WARNING: No saved project found.")
    return None


def _get_open_project_path():
    """Return the full path of the currently open .wbpj, or None."""
    try:
        p = Project.GetProjectFile()
        if p and p.strip():
            return p.strip()
    except Exception:
        pass
    return None


def _get_runwb2_path():
    """Locate RunWB2.exe for the current ANSYS installation."""
    try:
        install_root = (Ansys.Utilities.ApplicationConfiguration
                        .DefaultConfiguration.AwpRootEnvironmentVariableValue)
        platform     = (Ansys.Utilities.ApplicationConfiguration
                        .DefaultConfiguration.Platform)
        runwb2 = System.IO.Path.Combine(
            install_root, "Framework", "bin", platform, "runwb2.exe")
        if System.IO.File.Exists(runwb2):
            return runwb2
    except Exception as exc:
        _log("_get_runwb2_path error: " + str(exc))

    # Common fallback paths
    for candidate in [
        r"C:\Program Files\ANSYS Inc\v242\Framework\bin\Win64\RunWB2.exe",
        r"C:\Program Files\ANSYS Inc\v251\Framework\bin\Win64\RunWB2.exe",
    ]:
        if os.path.exists(candidate):
            return candidate
    return None


# ────────────────────────────────────────────────────────────────────────────
#  Smart file opener
# ────────────────────────────────────────────────────────────────────────────

def _smart_open_file(path):
    if not path or not os.path.exists(path):
        _log("Open failed - file does not exist: " + str(path))
        return False
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".wbpj", ".wbpz"):
            runwb2 = _get_runwb2_path()
            if runwb2:
                info = System.Diagnostics.ProcessStartInfo()
                info.FileName        = runwb2
                info.Arguments       = '-F "{0}"'.format(path)
                info.UseShellExecute = False
                System.Diagnostics.Process.Start(info)
                return True
        if ext in (".txt", ".py", ".log", ".csv", ".md",
                   ".xml", ".json", ".ini", ".bat"):
            npp = r"C:\Program Files\Notepad++\notepad++.exe"
            if os.path.exists(npp):
                System.Diagnostics.Process.Start(npp, '"{0}"'.format(path))
                return True
        os.startfile(path)
        return True
    except Exception as exc:
        _log("_smart_open_file error: " + str(exc))
        try:
            os.startfile(path)
            return True
        except Exception:
            pass
        return False


# ────────────────────────────────────────────────────────────────────────────
#  UI colours / fonts / column constants
# ────────────────────────────────────────────────────────────────────────────

_CLR_ANSYS_BLUE  = Drawing.Color.FromArgb(0,   120, 212)
_CLR_READY       = Drawing.Color.FromArgb(16,  124,  16)
_CLR_MISSING     = Drawing.Color.FromArgb(209,  52,  56)
_CLR_ARCHIVED_OK = Drawing.Color.FromArgb(0,   102, 204)   # blue
_CLR_ARCHIVED_OLD= Drawing.Color.FromArgb(200, 100,   0)   # orange
_CLR_ROW_ALT     = Drawing.Color.FromArgb(245, 247, 250)
_CLR_WARN_BG     = Drawing.Color.FromArgb(255, 244, 206)   # pale amber
_CLR_GREEN_DIM   = Drawing.Color.FromArgb(0,   128,   0)   # recommended badge

_FONT_NORMAL = Drawing.Font("Segoe UI",  9.5)
_FONT_BOLD   = Drawing.Font("Segoe UI",  9.5, Drawing.FontStyle.Bold)
_FONT_TITLE  = Drawing.Font("Segoe UI", 13,   Drawing.FontStyle.Bold)
_FONT_SMALL  = Drawing.Font("Segoe UI",  8.5)

COL_FILENAME  = 0
COL_STATUS    = 1
COL_SIZE      = 2
COL_MODIFIED  = 3
COL_DATEADDED = 4
COL_NOTES     = 5
COL_FULLPATH  = 6

SIZE_WARN_BYTES = 1024 * 1024 * 1024   # 1 GB


# ────────────────────────────────────────────────────────────────────────────
#  Button factory
# ────────────────────────────────────────────────────────────────────────────

def _make_btn(text, x, y, w=160, h=36, primary=False, handler=None):
    btn = WinForms.Button()
    btn.Text      = text
    btn.Location  = Drawing.Point(x, y)
    btn.Size      = Drawing.Size(w, h)
    btn.Font      = _FONT_NORMAL
    btn.FlatStyle = WinForms.FlatStyle.Flat
    if primary:
        btn.BackColor = _CLR_ANSYS_BLUE
        btn.ForeColor = Drawing.Color.White
        btn.FlatAppearance.BorderColor = _CLR_ANSYS_BLUE
    else:
        btn.BackColor = Drawing.Color.White
        btn.ForeColor = Drawing.Color.FromArgb(33, 37, 41)
        btn.FlatAppearance.BorderColor = Drawing.Color.FromArgb(180, 180, 180)
    if handler:
        btn.Click += handler
    return btn


# ────────────────────────────────────────────────────────────────────────────
#  Notes dialog
# ────────────────────────────────────────────────────────────────────────────

class NotesDialog(WinForms.Form):
    def __init__(self, current_notes=""):
        self.result_notes  = current_notes
        self.Text          = "File Notes"
        self.Width         = 480
        self.Height        = 260
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox   = False
        self.MaximizeBox   = False
        self.BackColor     = Drawing.Color.White
        self.Font          = _FONT_NORMAL

        lbl = WinForms.Label()
        lbl.Text     = "Notes / Description:"
        lbl.Location = Drawing.Point(12, 12)
        lbl.AutoSize = True
        self.Controls.Add(lbl)

        self._tb = WinForms.TextBox()
        self._tb.Multiline  = True
        self._tb.ScrollBars = WinForms.ScrollBars.Vertical
        self._tb.Location   = Drawing.Point(12, 36)
        self._tb.Size       = Drawing.Size(440, 140)
        self._tb.Text       = current_notes
        self.Controls.Add(self._tb)

        self.Controls.Add(_make_btn("OK",     260, 185, 90, 32,
                                    primary=True, handler=self._ok))
        self.Controls.Add(_make_btn("Cancel", 360, 185, 90, 32,
                                    handler=self._cancel))

    def _ok(self, s, e):
        self.result_notes = self._tb.Text
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()

    def _cancel(self, s, e):
        self.DialogResult = WinForms.DialogResult.Cancel
        self.Close()


# ────────────────────────────────────────────────────────────────────────────
#  Revision dialog
# ────────────────────────────────────────────────────────────────────────────

class RevisionDialog(WinForms.Form):
    def __init__(self, current_rev=""):
        self.result_rev    = ""
        self.result_note   = ""
        self.Text          = "Add Revision Entry"
        self.Width         = 460
        self.Height        = 240
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox   = False
        self.MaximizeBox   = False
        self.BackColor     = Drawing.Color.White
        self.Font          = _FONT_NORMAL

        lbl_rev = WinForms.Label()
        lbl_rev.Text     = "Revision label (e.g. Rev A, v1.2):"
        lbl_rev.Location = Drawing.Point(12, 14)
        lbl_rev.AutoSize = True
        self.Controls.Add(lbl_rev)

        self._tb_rev = WinForms.TextBox()
        self._tb_rev.Location = Drawing.Point(12, 36)
        self._tb_rev.Size     = Drawing.Size(420, 28)
        self._tb_rev.Text     = current_rev
        self.Controls.Add(self._tb_rev)

        lbl_note = WinForms.Label()
        lbl_note.Text     = "Change note:"
        lbl_note.Location = Drawing.Point(12, 74)
        lbl_note.AutoSize = True
        self.Controls.Add(lbl_note)

        self._tb_note = WinForms.TextBox()
        self._tb_note.Multiline = True
        self._tb_note.Location  = Drawing.Point(12, 96)
        self._tb_note.Size      = Drawing.Size(420, 68)
        self.Controls.Add(self._tb_note)

        self.Controls.Add(_make_btn("Save",   240, 172, 90, 32,
                                    primary=True, handler=self._ok))
        self.Controls.Add(_make_btn("Cancel", 340, 172, 90, 32,
                                    handler=self._cancel))

    def _ok(self, s, e):
        self.result_rev  = self._tb_rev.Text.strip()
        self.result_note = self._tb_note.Text.strip()
        if not self.result_rev:
            WinForms.MessageBox.Show("Please enter a revision label.",
                                     "Validation")
            return
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()

    def _cancel(self, s, e):
        self.DialogResult = WinForms.DialogResult.Cancel
        self.Close()


# ────────────────────────────────────────────────────────────────────────────
#  Health-check dialog  (with inline Relink)
# ────────────────────────────────────────────────────────────────────────────

class HealthCheckDialog(WinForms.Form):
    def __init__(self, health):
        self._health = health
        self.Text          = "Repository Health Check"
        self.Width         = 740
        self.Height        = 520
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox   = False
        self.MaximizeBox   = True
        self.BackColor     = Drawing.Color.White
        self.Font          = _FONT_NORMAL

        total   = health["total"]
        missing = health["missing"]
        ready   = health["ready"]
        arch_ok = health.get("archived_ok", 0)
        arch_old= health.get("archived_old", 0)
        colour  = _CLR_MISSING if missing > 0 else _CLR_READY
        icon    = (u"\u2718 ISSUES FOUND" if missing > 0
                   else u"\u2714 ALL FILES OK")

        lbl_icon = WinForms.Label()
        lbl_icon.Text      = icon
        lbl_icon.Font      = Drawing.Font("Segoe UI", 13, Drawing.FontStyle.Bold)
        lbl_icon.ForeColor = colour
        lbl_icon.Location  = Drawing.Point(16, 14)
        lbl_icon.AutoSize  = True
        self.Controls.Add(lbl_icon)

        lbl_sum = WinForms.Label()
        lbl_sum.Text = ("Total: {0}   Ready: {1}   Missing: {2}   "
                        "Archived OK: {3}   Archived Outdated: {4}".format(
                            total, ready, missing, arch_ok, arch_old))
        lbl_sum.Location = Drawing.Point(16, 46)
        lbl_sum.AutoSize = True
        self.Controls.Add(lbl_sum)

        if missing > 0:
            lbl_hint = WinForms.Label()
            lbl_hint.Text = (u"Select a missing file and click "
                             u"\u27A1 Relink to locate it.")
            lbl_hint.Font      = _FONT_SMALL
            lbl_hint.ForeColor = Drawing.Color.Gray
            lbl_hint.Location  = Drawing.Point(16, 66)
            lbl_hint.AutoSize  = True
            self.Controls.Add(lbl_hint)

        self._lv = WinForms.ListView()
        self._lv.View          = WinForms.View.Details
        self._lv.FullRowSelect  = True
        self._lv.GridLines      = True
        self._lv.Location       = Drawing.Point(16, 86)
        self._lv.Size           = Drawing.Size(690, 340)
        self._lv.Font           = _FONT_NORMAL
        self._lv.Columns.Add("Section",   160)
        self._lv.Columns.Add("File Name", 200)
        self._lv.Columns.Add("Path",      310)

        if missing == 0:
            item = self._lv.Items.Add(u"\u2014")
            item.SubItems.Add("No missing files detected.")
            item.SubItems.Add("")
        else:
            for m in health["missing_list"]:
                item = self._lv.Items.Add(m["section"])
                item.SubItems.Add(m["label"])
                item.SubItems.Add(m["path"])
                item.ForeColor = _CLR_MISSING

        self.Controls.Add(self._lv)

        self._btn_relink = _make_btn(
            u"\u27A1  Relink Selected\u2026",
            16, 440, 160, 32,
            handler=self._on_relink)
        self._btn_relink.Enabled = (missing > 0)
        self.Controls.Add(self._btn_relink)
        self._lv.SelectedIndexChanged += self._on_selection_changed

        self.Controls.Add(_make_btn("Close", 620, 440, 100, 32,
                                    primary=True,
                                    handler=lambda s, e: self.Close()))

    def _on_selection_changed(self, s, e):
        self._btn_relink.Enabled = (self._lv.SelectedItems.Count == 1)

    def _on_relink(self, s, e):
        try:
            if self._lv.SelectedItems.Count != 1:
                return
            selected = self._lv.SelectedItems[0]
            label    = selected.SubItems[1].Text
            old_path = selected.SubItems[2].Text
            old_name = os.path.basename(old_path) if old_path else label
            section, index = self._find_record(label, old_path)
            if section is None:
                WinForms.MessageBox.Show(
                    "Could not locate this record.\n"
                    "Close and Refresh, then try again.", "Relink Error")
                return
            dlg = WinForms.OpenFileDialog()
            dlg.Title    = u"Relink: locate \"{0}\"".format(old_name)
            dlg.Filter   = "All Files (*.*)|*.*"
            dlg.FileName = old_name
            if dlg.ShowDialog() != WinForms.DialogResult.OK:
                return
            new_path = dlg.FileName
            repo.relink_file_record(section, index, new_path)
            selected.SubItems[2].Text = new_path
            selected.SubItems[1].Text = os.path.basename(new_path)
            selected.ForeColor        = _CLR_READY
            still_missing = sum(
                1 for i in range(self._lv.Items.Count)
                if self._lv.Items[i].ForeColor == _CLR_MISSING)
            if still_missing == 0:
                WinForms.MessageBox.Show(
                    u"\u2714 All missing files relinked.\n\n"
                    "Click Close then Refresh to update the main list.",
                    "Relink Complete")
        except Exception as exc:
            _log("Health check relink error: " + str(exc))
            WinForms.MessageBox.Show("Relink failed:\n" + str(exc), "Error")

    def _find_record(self, label, old_path):
        try:
            data = repo.load_manifest()
            for sec in repo.ALL_SECTIONS:
                for i, r in enumerate(data["sections"].get(sec, [])):
                    if r.get("source_path", "") == old_path:
                        return sec, i
                    if not old_path and r.get("label", "") == label:
                        return sec, i
        except Exception as exc:
            _log("_find_record error: " + str(exc))
        return None, None


# ────────────────────────────────────────────────────────────────────────────
#  Archive Progress dialog
# ────────────────────────────────────────────────────────────────────────────

class ArchiveProgressDialog(WinForms.Form):
    """
    Modal progress dialog shown while RunWB2.exe runs in the background.
    Polls every 500ms. Captures stdout/stderr for diagnostics.
    Also used for regular file copy operations (no process, just label).
    """

    def __init__(self, label_text, process=None):
        self._process  = process
        self._success  = False
        self._elapsed  = 0   # seconds

        self.Text          = "Archiving..."
        self.Width         = 520
        self.Height        = 180
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox   = False
        self.MaximizeBox   = False
        self.ControlBox    = False
        self.BackColor     = Drawing.Color.White
        self.Font          = _FONT_NORMAL

        lbl = WinForms.Label()
        lbl.Text     = label_text
        lbl.Location = Drawing.Point(16, 16)
        lbl.Size     = Drawing.Size(480, 20)
        lbl.Font     = _FONT_BOLD
        self.Controls.Add(lbl)

        self._lbl_status = WinForms.Label()
        self._lbl_status.Text      = ("Opening project in batch mode..."
                                       if process else "Copying file...")
        self._lbl_status.ForeColor = Drawing.Color.FromArgb(80, 80, 80)
        self._lbl_status.Location  = Drawing.Point(16, 44)
        self._lbl_status.Size      = Drawing.Size(480, 20)
        self.Controls.Add(self._lbl_status)

        self._lbl_time = WinForms.Label()
        self._lbl_time.Text      = ""
        self._lbl_time.ForeColor = Drawing.Color.Gray
        self._lbl_time.Font      = _FONT_SMALL
        self._lbl_time.Location  = Drawing.Point(16, 64)
        self._lbl_time.Size      = Drawing.Size(480, 16)
        self.Controls.Add(self._lbl_time)

        bar = WinForms.ProgressBar()
        bar.Style    = WinForms.ProgressBarStyle.Marquee
        bar.Location = Drawing.Point(16, 90)
        bar.Size     = Drawing.Size(480, 22)
        self.Controls.Add(bar)

        self._lbl_hint = WinForms.Label()
        self._lbl_hint.Text      = ("ANSYS Workbench is running in the background. "
                                     "Do not close Workbench." if process else "")
        self._lbl_hint.ForeColor = Drawing.Color.Gray
        self._lbl_hint.Font      = _FONT_SMALL
        self._lbl_hint.Location  = Drawing.Point(16, 122)
        self._lbl_hint.Size      = Drawing.Size(480, 16)
        self.Controls.Add(self._lbl_hint)

        self._timer = WinForms.Timer()
        self._timer.Interval = 500
        self._timer.Tick    += self._on_tick
        self._timer.Start()

    def set_status(self, msg):
        """Update status label — call this for non-process (copy) operations."""
        self._lbl_status.Text = msg
        WinForms.Application.DoEvents()

    def finish_success(self):
        """Call after a copy operation completes successfully."""
        self._timer.Stop()
        self._success = True
        self._lbl_status.Text = u"\u2714 Done."
        WinForms.Application.DoEvents()
        System.Threading.Thread.Sleep(400)
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()

    def _on_tick(self, s, e):
        try:
            self._elapsed += 0.5
            self._lbl_time.Text = "Elapsed: {0:.0f}s".format(self._elapsed)

            if self._process is None:
                # No process — dialog is being driven externally
                return

            if self._process.HasExited:
                self._timer.Stop()
                exit_code = self._process.ExitCode
                self._success = (exit_code == 0)
                _log("RunWB2 exited. Code={0}  Elapsed={1:.0f}s".format(
                    exit_code, self._elapsed))
                status_text = (u"\u2714 ANSYS ARCHIVE complete."
                               if self._success
                               else u"\u26A0 Completed (exit code {0}) — "
                                    u"check log for details.".format(exit_code))
                self._lbl_status.Text = status_text
                WinForms.Application.DoEvents()
                System.Threading.Thread.Sleep(800)
                self.DialogResult = WinForms.DialogResult.OK
                self.Close()
            else:
                msgs = [
                    "Initializing ANSYS Workbench batch session...",
                    "Opening project file...",
                    "Running ANSYS ARCHIVE...",
                    "Packaging project files...",
                    "Writing .wbpz archive...",
                    "Finalizing archive...",
                ]
                idx = int(self._elapsed / 15) % len(msgs)
                self._lbl_status.Text = msgs[idx]
        except Exception as exc:
            self._timer.Stop()
            _log("ArchiveProgressDialog tick error: " + str(exc))
            self.Close()

    @property
    def succeeded(self):
        return self._success


# ────────────────────────────────────────────────────────────────────────────
#  Archive dialog
# ────────────────────────────────────────────────────────────────────────────

class ArchiveDialog(WinForms.Form):
    """
    Checklist dialog for selecting files to archive.

    Layout
    ------
    [Check All] [Uncheck All]
    [ListView — one row per eligible file with checkboxes]
    [.wbpj Options panel — shown only when .wbpj files are present]
    [Archive Checked Files]  [Cancel]
    """

    # wbpj method constants
    WBPJ_ZIP            = "zip"
    WBPJ_USE_WBPZ       = "wbpz"
    WBPJ_COPY_WITH_FILES = "copy_with_files"
    WBPJ_SKIP           = "skip"

    def __init__(self, candidates, open_project_path=None):
        self._candidates        = candidates   # list of dicts from repo helper
        self._open_proj         = open_project_path
        self._archived_results  = []           # filled after archive runs
        self._has_wbpj          = any(c["is_wbpj"] for c in candidates)

        self.Text          = u"Archive Repository Files"
        self.Width         = 900
        self.Height        = 640 if self._has_wbpj else 520
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox   = False
        self.MaximizeBox   = True
        self.BackColor     = Drawing.Color.White
        self.Font          = _FONT_NORMAL

        self._build_ui()
        self._populate_list()

    def _build_ui(self):
        y = 12

        # Header
        lbl_hdr = WinForms.Label()
        lbl_hdr.Text = (u"Select files to archive into the project repository. "
                        u"Files already archived show their current status.")
        lbl_hdr.Location = Drawing.Point(16, y)
        lbl_hdr.Size     = Drawing.Size(850, 18)
        lbl_hdr.Font     = _FONT_SMALL
        lbl_hdr.ForeColor = Drawing.Color.Gray
        self.Controls.Add(lbl_hdr)
        y += 28

        # Check All / Uncheck All
        self.Controls.Add(_make_btn("Check All",   16, y, 100, 26,
                                    handler=self._check_all))
        self.Controls.Add(_make_btn("Uncheck All", 124, y, 110, 26,
                                    handler=self._uncheck_all))
        y += 36

        # ListView
        lv_height = 240
        self._lv = WinForms.ListView()
        self._lv.View          = WinForms.View.Details
        self._lv.CheckBoxes     = True
        self._lv.FullRowSelect  = True
        self._lv.GridLines      = True
        self._lv.Location       = Drawing.Point(16, y)
        self._lv.Size           = Drawing.Size(854, lv_height)
        self._lv.Font           = _FONT_NORMAL
        self._lv.HeaderStyle    = WinForms.ColumnHeaderStyle.Nonclickable

        for name, w in [("Section", 150), ("File Name", 220),
                        ("Source Location", 240), ("Size", 80),
                        ("Archive Status", 130)]:
            self._lv.Columns.Add(name, w)

        self.Controls.Add(self._lv)
        y += lv_height + 10

        # .wbpj options panel
        if self._has_wbpj:
            self._wbpj_panel = self._build_wbpj_panel(y)
            self.Controls.Add(self._wbpj_panel)
            y += self._wbpj_panel.Height + 10
        else:
            self._wbpj_panel = None

        # Bottom buttons
        btn_y = y + 4
        self.Controls.Add(_make_btn(
            u"\U0001F4E6  Archive Checked Files",
            16, btn_y, 200, 36,
            primary=True, handler=self._on_archive))
        self.Controls.Add(_make_btn(
            "Cancel", 230, btn_y, 100, 36,
            handler=lambda s, e: self._cancel()))

        # Resize form to fit
        self.Height = btn_y + 80

    def _build_wbpj_panel(self, top_y):
        panel = WinForms.GroupBox()
        panel.Text     = "Workbench Project (.wbpj) Archive Method"
        panel.Location = Drawing.Point(16, top_y)
        panel.Size     = Drawing.Size(854, 152)
        panel.Font     = _FONT_NORMAL

        # ── Option 1: Compress to ZIP (recommended) ──
        self._rb_zip = WinForms.RadioButton()
        self._rb_zip.Text     = u"Compress to ZIP  (recommended \u2014 works with any project)"
        self._rb_zip.Location = Drawing.Point(12, 20)
        self._rb_zip.Size     = Drawing.Size(600, 20)
        self._rb_zip.Checked  = True
        panel.Controls.Add(self._rb_zip)

        lbl_zip_rec = WinForms.Label()
        lbl_zip_rec.Text      = u"\u2714 Recommended"
        lbl_zip_rec.ForeColor = _CLR_GREEN_DIM
        lbl_zip_rec.Font      = _FONT_BOLD
        lbl_zip_rec.Location  = Drawing.Point(620, 22)
        lbl_zip_rec.AutoSize  = True
        panel.Controls.Add(lbl_zip_rec)

        self._chk_results = WinForms.CheckBox()
        self._chk_results.Text     = "Include result files (.rst, .db, etc.)"
        self._chk_results.Location = Drawing.Point(34, 44)
        self._chk_results.Size     = Drawing.Size(260, 20)
        self._chk_results.Checked  = False
        panel.Controls.Add(self._chk_results)

        lbl_zip_note = WinForms.Label()
        lbl_zip_note.Text      = ("Output: ProjectName.zip in the archive folder. "
                                   "Open by extracting, then opening the .wbpj.")
        lbl_zip_note.Font      = _FONT_SMALL
        lbl_zip_note.ForeColor = Drawing.Color.Gray
        lbl_zip_note.Location  = Drawing.Point(34, 66)
        lbl_zip_note.Size      = Drawing.Size(800, 16)
        panel.Controls.Add(lbl_zip_note)

        # ── Option 2: Guided Manual ARCHIVE ──
        self._rb_wbpz = WinForms.RadioButton()
        self._rb_wbpz.Text     = (u"Guided Manual ANSYS ARCHIVE \u2192 .wbpz  "
                                   u"(requires manual steps)")
        self._rb_wbpz.Location = Drawing.Point(12, 90)
        self._rb_wbpz.Size     = Drawing.Size(600, 20)
        panel.Controls.Add(self._rb_wbpz)

        lbl_wbpz_note = WinForms.Label()
        lbl_wbpz_note.Text      = (u"\u26A0 Requires the project to be clean "
                                    u"(saved, no dialogs, no missing files).")
        lbl_wbpz_note.Font      = _FONT_SMALL
        lbl_wbpz_note.ForeColor = _CLR_ARCHIVED_OLD
        lbl_wbpz_note.Location  = Drawing.Point(34, 112)
        lbl_wbpz_note.Size      = Drawing.Size(800, 16)
        panel.Controls.Add(lbl_wbpz_note)

        # ── Option 3: Copy with _files ──
        self._rb_copy = WinForms.RadioButton()
        self._rb_copy.Text     = (u"Copy .wbpj + _files folder  "
                                   u"(largest, no compression)")
        self._rb_copy.Location = Drawing.Point(12, 132)
        self._rb_copy.Size     = Drawing.Size(600, 20)
        panel.Controls.Add(self._rb_copy)

        return panel

    def _populate_list(self):
        self._lv.Items.Clear()
        for c in self._candidates:
            item = WinForms.ListViewItem(c["section_label"])

            # Colour the row for context
            status = c["archive_status"]
            if status == repo.ARCH_STATUS_MISSING:
                item.ForeColor = _CLR_MISSING
            elif status == repo.ARCH_STATUS_OK:
                item.ForeColor = _CLR_ARCHIVED_OK
            elif status == repo.ARCH_STATUS_OUTDATED:
                item.ForeColor = _CLR_ARCHIVED_OLD

            item.SubItems.Add(c["label"])
            item.SubItems.Add(c["source_path"])

            # Size — for .wbpj show total (wbpj + _files), for others show file size
            if c["is_wbpj"]:
                size_str  = c["wbpj_total_size_str"]
                size_bytes = c["wbpj_total_size_bytes"]
            else:
                size_str  = c["source_size_str"]
                size_bytes = c["source_size_bytes"]

            # Warn if > 1 GB
            if size_bytes > SIZE_WARN_BYTES:
                size_str += u"  \u26A0"   # warning triangle

            item.SubItems.Add(size_str)
            item.SubItems.Add(status)

            # Default: check files not yet archived or out of date
            item.Checked = (status != repo.ARCH_STATUS_OK)

            self._lv.Items.Add(item)

    def _check_all(self, s, e):
        for i in range(self._lv.Items.Count):
            self._lv.Items[i].Checked = True

    def _uncheck_all(self, s, e):
        for i in range(self._lv.Items.Count):
            self._lv.Items[i].Checked = False

    def _get_wbpj_method(self):
        if self._wbpj_panel is None:
            return self.WBPJ_SKIP
        if self._rb_zip.Checked:
            return self.WBPJ_ZIP
        if self._rb_wbpz.Checked:
            return self.WBPJ_USE_WBPZ
        if self._rb_copy.Checked:
            return self.WBPJ_COPY_WITH_FILES
        return self.WBPJ_SKIP

    def _cancel(self):
        self.DialogResult = WinForms.DialogResult.Cancel
        self.Close()

    def _on_archive(self, s, e):
        """Run the archive operation for all checked items."""
        checked = [self._candidates[i]
                   for i in range(self._lv.Items.Count)
                   if self._lv.Items[i].Checked]

        if not checked:
            WinForms.MessageBox.Show(
                "No files are checked. Select at least one file to archive.",
                "Nothing Selected")
            return

        wbpj_method = self._get_wbpj_method()

        # Warn about large files before starting
        large = [c for c in checked
                 if (c["wbpj_total_size_bytes"] if c["is_wbpj"]
                     else c["source_size_bytes"]) > SIZE_WARN_BYTES]
        if large:
            names = "\n".join(u"  \u2022 " + c["label"] for c in large)
            res = WinForms.MessageBox.Show(
                u"The following files are larger than 1 GB:\n\n{0}\n\n"
                u"This may take several minutes. Continue?".format(names),
                u"Large File Warning",
                WinForms.MessageBoxButtons.YesNo,
                WinForms.MessageBoxIcon.Warning)
            if res != WinForms.DialogResult.Yes:
                return

        runwb2 = _get_runwb2_path() if wbpj_method == self.WBPJ_USE_WBPZ else None
        if wbpj_method == self.WBPJ_USE_WBPZ and not runwb2:
            WinForms.MessageBox.Show(
                "RunWB2.exe could not be located.\n"
                "Please use 'Copy .wbpj + _files folder' instead,\n"
                "or verify your ANSYS installation.",
                "RunWB2 Not Found",
                WinForms.MessageBoxButtons.OK,
                WinForms.MessageBoxIcon.Warning)
            return

        successes      = []
        failures       = []
        self._guided_items = []   # .wbpj items queued for guided manual ARCHIVE

        for c in checked:
            section  = c["section"]
            index    = c["index"]
            src      = c["source_path"]
            dest_dir = repo.get_section_archive_dir(section)
            label    = c["label"]

            try:
                if c["is_wbpj"]:
                    if wbpj_method == self.WBPJ_ZIP:
                        # ZIP compression — works with any project state
                        prog = ArchiveProgressDialog(
                            u"Compressing: {0}".format(label))
                        prog.Show()
                        WinForms.Application.DoEvents()

                        def _zip_progress(fname):
                            prog.set_status(u"Adding: {0}".format(fname))

                        dest_path = repo.zip_wbpj_with_files(
                            src, dest_dir,
                            include_results=self._chk_results.Checked,
                            progress_callback=_zip_progress)
                        prog.finish_success()
                        method = "zip"

                    elif wbpj_method == self.WBPJ_USE_WBPZ:
                        # Guided manual ARCHIVE — open a separate dialog
                        # Close this dialog first, then show guided steps
                        self._pending_guided = {"src": src, "dest_dir": dest_dir,
                                                 "label": label, "section": section,
                                                 "index": index}
                        self._guided_items.append(self._pending_guided)
                        continue   # handled after main loop via guided dialog

                    elif wbpj_method == self.WBPJ_COPY_WITH_FILES:
                        prog = ArchiveProgressDialog(
                            u"Copying: {0}".format(label))
                        prog.Show()
                        prog.set_status(u"Copying .wbpj + _files folder...")
                        WinForms.Application.DoEvents()
                        dest_path = repo.copy_wbpj_with_files(src, dest_dir)
                        prog.finish_success()
                        method = "copy_with_files"

                    else:
                        continue   # skip
                else:
                    # Show progress for regular file copy
                    size_mb = c.get("source_size_bytes", 0) / (1024.0 * 1024)
                    prog = ArchiveProgressDialog(
                        u"Copying: {0}  ({1:.1f} MB)".format(label, size_mb))
                    prog.Show()
                    prog.set_status(u"Copying file to archive folder...")
                    WinForms.Application.DoEvents()
                    dest_path = repo.archive_regular_file(src, dest_dir)
                    prog.finish_success()
                    method    = "copy"

                repo.update_archive_record(section, index, dest_path, method)
                successes.append(label)
                _log("Archived: " + label + " -> " + dest_path)

            except Exception as exc:
                failures.append("{0}: {1}".format(label, str(exc)))
                _log("Archive failed [{0}]: {1}".format(label, str(exc)))

        # Summary
        msg_parts = []
        if successes:
            msg_parts.append(
                u"\u2714 Archived successfully ({0}):\n{1}".format(
                    len(successes),
                    "\n".join(u"  \u2022 " + s for s in successes)))
        if failures:
            msg_parts.append(
                u"\u2718 Failed ({0}):\n{1}".format(
                    len(failures),
                    "\n".join(u"  \u2022 " + f for f in failures)))

        WinForms.MessageBox.Show(
            "\n\n".join(msg_parts) if msg_parts else "No files were processed.",
            "Archive Complete" if not failures else "Archive — Partial Success",
            WinForms.MessageBoxButtons.OK,
            WinForms.MessageBoxIcon.Information if not failures
            else WinForms.MessageBoxIcon.Warning)

        self._archived_results = successes

        # Launch guided ARCHIVE dialog for any .wbpj items that need it
        if self._guided_items:
            self.Hide()
            for item in self._guided_items:
                gdlg = GuidedArchiveDialog(
                    item["src"], item["dest_dir"], item["label"])
                gdlg.ShowDialog()
                if gdlg.archive_confirmed:
                    repo.update_archive_record(
                        item["section"], item["index"],
                        gdlg.confirmed_path, "wbpz")
                    successes.append(item["label"] + " (manual .wbpz)")
            self._archived_results = successes

        self.DialogResult = WinForms.DialogResult.OK
        self.Close()

    def _archive_via_wbpz(self, wbpj_path, dest_dir, runwb2,
                           include_results, include_external, label):
        """
        Generate a batch script and run RunWB2.exe -B -R to produce a .wbpz.
        Shows a progress dialog while the subprocess runs.
        Captures stdout/stderr and writes to log for diagnostics.
        Returns the path of the produced .wbpz file.
        """
        script_path, expected_wbpz, marker_path = repo.generate_wbpz_script(
            wbpj_path, dest_dir,
            include_results=include_results,
            include_external=include_external,
            archive_notes="Archived via AnalysisHub")

        _log("Launching RunWB2 batch for: " + wbpj_path)
        _log("Script:          " + script_path)
        _log("Expected .wbpz:  " + expected_wbpz)
        _log("Completion marker: " + marker_path)
        _log("RunWB2:          " + runwb2)

        info = System.Diagnostics.ProcessStartInfo()
        info.FileName               = runwb2
        info.Arguments              = u'-B -R "{0}"'.format(script_path)
        info.UseShellExecute        = False
        info.CreateNoWindow         = True
        info.RedirectStandardOutput = True
        info.RedirectStandardError  = True

        proc = System.Diagnostics.Process.Start(info)

        # Show progress dialog — blocks UI until process exits
        prog = ArchiveProgressDialog(
            u"ANSYS ARCHIVE: {0}".format(label), proc)
        prog.ShowDialog()

        # Capture and log process output for diagnostics
        try:
            stdout = proc.StandardOutput.ReadToEnd()
            stderr = proc.StandardError.ReadToEnd()
            if stdout.strip():
                _log("RunWB2 stdout:\n" + stdout.strip()[:1000])
            if stderr.strip():
                _log("RunWB2 stderr:\n" + stderr.strip()[:1000])
        except Exception as exc:
            _log("Could not read RunWB2 output: " + str(exc))

        exit_code = proc.ExitCode
        _log("RunWB2 exit code: " + str(exit_code))

        # Check completion marker — tells us if the script ran to end
        script_ran_to_end = os.path.exists(marker_path)
        _log("Script ran to completion: " + str(script_ran_to_end))

        repo.cleanup_archive_script(script_path)

        # List dest_dir contents for diagnostics
        try:
            contents = os.listdir(dest_dir) if os.path.isdir(dest_dir) else []
            _log("dest_dir contents: " + str(contents))
        except Exception:
            pass

        # Verify output exists
        if not os.path.exists(expected_wbpz):
            if not script_ran_to_end:
                reason = ("The ARCHIVE script did not run to completion.\n"
                          "RunWB2 likely failed to start, could not open the "
                          "project, or crashed before archiving.")
            else:
                reason = ("The script ran but the Archive() command did not "
                          "produce the expected .wbpz output.\n"
                          "The project may have unsaved changes or locked files.")
            raise IOError(
                u"ANSYS ARCHIVE did not produce the expected file.\n\n"
                u"Expected:\n  {0}\n\n"
                u"{1}\n\n"
                u"Check C:\\Temp\\AnalysisHub_debug.log for full details.\n"
                u"As a fallback, use \'Copy .wbpj + _files folder\' instead.".format(
                    expected_wbpz, reason))

        _log("wbpz verified at: " + expected_wbpz)
        return expected_wbpz


# ────────────────────────────────────────────────────────────────────────────
#  Project-info panel  (with Status change handler)
# ────────────────────────────────────────────────────────────────────────────



# ----------------------------------------------------------------------------
#  Guided Manual ARCHIVE dialog  (Proposal 1)
# ----------------------------------------------------------------------------

class GuidedArchiveDialog(WinForms.Form):
    """
    Step-by-step instructions for manually running ANSYS ARCHIVE on a
    referenced .wbpj file. The user follows the steps, saves the .wbpz
    to the displayed directory, then clicks Archive Complete.
    We then scan for the .wbpz and update the manifest.
    """

    def __init__(self, wbpj_path, dest_dir, label):
        self._wbpj_path        = wbpj_path
        self._dest_dir         = dest_dir
        self._label            = label
        self.archive_confirmed = False
        self.confirmed_path    = ''

        self.Text          = u'Guided ANSYS ARCHIVE: {0}'.format(label)
        self.Width         = 720
        self.Height        = 560
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox   = True
        self.MaximizeBox   = False
        self.BackColor     = Drawing.Color.White
        self.Font          = _FONT_NORMAL

        self._build_ui()

    def _build_ui(self):
        y = 16

        lbl_title = WinForms.Label()
        lbl_title.Text      = u'Guided ANSYS ARCHIVE Process'
        lbl_title.Font      = _FONT_TITLE
        lbl_title.ForeColor = _CLR_ANSYS_BLUE
        lbl_title.Location  = Drawing.Point(16, y)
        lbl_title.AutoSize  = True
        self.Controls.Add(lbl_title)
        y += 36

        lbl_sub = WinForms.Label()
        lbl_sub.Text      = ('This process requires manual steps inside '
                              'ANSYS Workbench. Follow the instructions below.')
        lbl_sub.Font      = _FONT_SMALL
        lbl_sub.ForeColor = Drawing.Color.Gray
        lbl_sub.Location  = Drawing.Point(16, y)
        lbl_sub.Size      = Drawing.Size(670, 18)
        self.Controls.Add(lbl_sub)
        y += 30

        # Warning box
        warn = WinForms.Panel()
        warn.BackColor   = Drawing.Color.FromArgb(255, 244, 206)
        warn.BorderStyle = WinForms.BorderStyle.FixedSingle
        warn.Location    = Drawing.Point(16, y)
        warn.Size        = Drawing.Size(670, 44)
        lbl_warn = WinForms.Label()
        lbl_warn.Text      = (u'\u26A0  Do NOT click \u201cArchive Complete\u201d '
                               u'until AFTER you have saved the .wbpz file. '
                               u'That button scans for the output file.')
        lbl_warn.Font      = _FONT_SMALL
        lbl_warn.ForeColor = Drawing.Color.FromArgb(120, 80, 0)
        lbl_warn.Location  = Drawing.Point(6, 6)
        lbl_warn.Size      = Drawing.Size(656, 30)
        warn.Controls.Add(lbl_warn)
        self.Controls.Add(warn)
        y += 54

        project_name  = os.path.splitext(os.path.basename(self._wbpj_path))[0]
        expected_wbpz = os.path.join(self._dest_dir, project_name + '.wbpz')
        self._expected_wbpz = expected_wbpz

        steps = [
            (u'1.', u'Click \u201cOpen Project\u201d below to launch the referenced database.'),
            (u'2.', u'Dismiss any warnings or dialogs (missing files, version migration, etc.). Save the project if prompted.'),
            (u'3.', u'In Workbench, go to:  File \u2192 Archive...'),
            (u'4.', u'Set the Save Location to:\n   {0}'.format(self._dest_dir)),
            (u'5.', u'Set the filename to:\n   {0}'.format(project_name + '.wbpz')),
            (u'6.', u'Choose your result file preference and click Archive.'),
            (u'7.', u'Return to this window and click \u201cArchive Complete \u2014 Update Repository\u201d.'),
        ]

        for num, text in steps:
            pnl = WinForms.Panel()
            pnl.Location = Drawing.Point(16, y)
            pnl.Size     = Drawing.Size(670, 50)
            lbl_num = WinForms.Label()
            lbl_num.Text      = num
            lbl_num.Font      = _FONT_BOLD
            lbl_num.ForeColor = _CLR_ANSYS_BLUE
            lbl_num.Location  = Drawing.Point(0, 4)
            lbl_num.Size      = Drawing.Size(24, 20)
            pnl.Controls.Add(lbl_num)
            lbl_txt = WinForms.Label()
            lbl_txt.Text     = text
            lbl_txt.Font     = _FONT_NORMAL
            lbl_txt.Location = Drawing.Point(28, 4)
            lbl_txt.Size     = Drawing.Size(640, 44)
            pnl.Controls.Add(lbl_txt)
            self.Controls.Add(pnl)
            y += 54

        y += 8

        lbl_exp = WinForms.Label()
        lbl_exp.Text     = 'Expected output location:'
        lbl_exp.Font     = _FONT_BOLD
        lbl_exp.Location = Drawing.Point(16, y)
        lbl_exp.AutoSize = True
        self.Controls.Add(lbl_exp)
        y += 22

        tb_path = WinForms.TextBox()
        tb_path.Text      = expected_wbpz
        tb_path.ReadOnly  = True
        tb_path.BackColor = Drawing.Color.FromArgb(240, 240, 240)
        tb_path.Font      = _FONT_SMALL
        tb_path.Location  = Drawing.Point(16, y)
        tb_path.Size      = Drawing.Size(560, 22)
        self.Controls.Add(tb_path)

        self.Controls.Add(_make_btn(u'Copy Path', 584, y - 1, 90, 24,
                                    handler=self._copy_path))
        y += 34

        self.Controls.Add(_make_btn(u'\u25B6  Open Project', 16, y,
                                    160, 36, primary=True,
                                    handler=self._open_project))

        self.Controls.Add(_make_btn(u'Open Archive Folder', 184, y,
                                    160, 36, handler=self._open_dest_dir))

        self._btn_complete = _make_btn(
            u'\u2714  Archive Complete \u2014 Update Repository',
            16, y + 44, 340, 36, handler=self._on_complete)
        self._btn_complete.ForeColor = _CLR_GREEN_DIM
        self._btn_complete.Font      = _FONT_BOLD
        self.Controls.Add(self._btn_complete)

        self.Controls.Add(_make_btn('Cancel / Skip', 364, y + 44,
                                    130, 36,
                                    handler=lambda s, e: self.Close()))

        self.Height = y + 130

    def _copy_path(self, s, e):
        try:
            WinForms.Clipboard.SetText(self._expected_wbpz)
        except Exception:
            pass

    def _open_project(self, s, e):
        try:
            _smart_open_file(self._wbpj_path)
        except Exception as exc:
            WinForms.MessageBox.Show('Could not open project:\n' + str(exc),
                                      'Open Error')

    def _open_dest_dir(self, s, e):
        try:
            if not os.path.exists(self._dest_dir):
                os.makedirs(self._dest_dir)
            os.startfile(self._dest_dir)
        except Exception as exc:
            WinForms.MessageBox.Show('Could not open folder:\n' + str(exc),
                                      'Error')

    def _on_complete(self, s, e):
        try:
            if os.path.exists(self._expected_wbpz):
                self.archive_confirmed = True
                self.confirmed_path    = self._expected_wbpz
                _log('Guided ARCHIVE confirmed: ' + self._expected_wbpz)
                WinForms.MessageBox.Show(
                    u'\u2714 Archive found and repository updated!\n\n'
                    u'{0}'.format(self._expected_wbpz),
                    'Archive Confirmed')
                self.DialogResult = WinForms.DialogResult.OK
                self.Close()
            else:
                dlg = WinForms.OpenFileDialog()
                dlg.Title            = 'Locate the .wbpz archive file'
                dlg.Filter           = 'Workbench Archive (*.wbpz)|*.wbpz|All Files (*.*)|*.*'
                dlg.InitialDirectory = self._dest_dir
                dlg.FileName         = os.path.basename(self._expected_wbpz)
                if dlg.ShowDialog() == WinForms.DialogResult.OK:
                    self.archive_confirmed = True
                    self.confirmed_path    = dlg.FileName
                    _log('Guided ARCHIVE confirmed (browsed): ' + dlg.FileName)
                    self.DialogResult = WinForms.DialogResult.OK
                    self.Close()
                else:
                    WinForms.MessageBox.Show(
                        u'The archive file was not found at:\n\n'
                        u'{0}\n\n'
                        u'Complete the ANSYS ARCHIVE process first, '
                        u'or browse to the file if saved elsewhere.'.format(
                            self._expected_wbpz),
                        u'File Not Found',
                        WinForms.MessageBoxButtons.OK,
                        WinForms.MessageBoxIcon.Warning)
        except Exception as exc:
            _log('GuidedArchiveDialog complete error: ' + str(exc))
            WinForms.MessageBox.Show('Error:\n' + str(exc), 'Error')
class ProjectInfoPanel(WinForms.Panel):
    def __init__(self, form_ref):
        self._form          = form_ref
        self._expanded      = True
        self._suppress_evt  = False   # prevents recursive status-change events
        self.BackColor      = Drawing.Color.FromArgb(245, 248, 252)
        self.BorderStyle    = WinForms.BorderStyle.FixedSingle
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        lbl = WinForms.Label()
        lbl.Text     = "Project Information"
        lbl.Font     = _FONT_BOLD
        lbl.Location = Drawing.Point(8, 7)
        lbl.AutoSize = True
        self.Controls.Add(lbl)

        btn_toggle = WinForms.Button()
        btn_toggle.Text      = u"\u25B2 Collapse"
        btn_toggle.Location  = Drawing.Point(200, 4)
        btn_toggle.Size      = Drawing.Size(90, 22)
        btn_toggle.Font      = _FONT_SMALL
        btn_toggle.FlatStyle = WinForms.FlatStyle.Flat
        btn_toggle.FlatAppearance.BorderColor = Drawing.Color.Silver
        btn_toggle.Click    += self._toggle
        self._btn_toggle     = btn_toggle
        self.Controls.Add(btn_toggle)

        self.Controls.Add(_make_btn("Save Info", 300, 4, 90, 22,
                                    primary=True, handler=self._save))

        self._fields_panel = WinForms.Panel()
        self._fields_panel.Location = Drawing.Point(0, 32)

        x0 = 8
        for caption, attr, col in [("Title",    "_tb_title",    0),
                                    ("Customer", "_tb_customer", 1),
                                    ("Analyst",  "_tb_analyst",  2)]:
            lbl2 = WinForms.Label()
            lbl2.Text     = caption + ":"
            lbl2.Location = Drawing.Point(x0 + col * 200, 6)
            lbl2.Size     = Drawing.Size(70, 20)
            self._fields_panel.Controls.Add(lbl2)
            tb = WinForms.TextBox()
            tb.Location = Drawing.Point(x0 + col * 200 + 72, 4)
            tb.Size     = Drawing.Size(118, 24)
            tb.Font     = _FONT_NORMAL
            setattr(self, attr, tb)
            self._fields_panel.Controls.Add(tb)

        lbl_s = WinForms.Label()
        lbl_s.Text     = "Status:"
        lbl_s.Location = Drawing.Point(x0 + 3 * 200, 6)
        lbl_s.Size     = Drawing.Size(50, 20)
        self._fields_panel.Controls.Add(lbl_s)

        self._cb_status = WinForms.ComboBox()
        self._cb_status.DropDownStyle = WinForms.ComboBoxStyle.DropDownList
        self._cb_status.Location = Drawing.Point(x0 + 3 * 200 + 54, 3)
        self._cb_status.Size     = Drawing.Size(130, 24)
        for s in ["Active", "In Review", "Complete", "On Hold", "Archived"]:
            self._cb_status.Items.Add(s)
        self._cb_status.SelectedIndexChanged += self._on_status_changed
        self._fields_panel.Controls.Add(self._cb_status)

        lbl_r = WinForms.Label()
        lbl_r.Text     = "Revision:"
        lbl_r.Location = Drawing.Point(x0, 36)
        lbl_r.Size     = Drawing.Size(70, 20)
        self._fields_panel.Controls.Add(lbl_r)

        self._tb_rev = WinForms.TextBox()
        self._tb_rev.Location = Drawing.Point(x0 + 72, 34)
        self._tb_rev.Size     = Drawing.Size(118, 24)
        self._fields_panel.Controls.Add(self._tb_rev)

        self._fields_panel.Controls.Add(
            _make_btn(u"\u2795 Log Revision", x0 + 200, 32, 140, 26,
                      handler=self._log_revision))

        self._fields_panel.Size = Drawing.Size(900, 66)
        self.Controls.Add(self._fields_panel)
        self.Size = Drawing.Size(1300, 106)

    def _load_values(self):
        try:
            self._suppress_evt = True
            info = repo.get_project_info()
            self._tb_title.Text    = info.get("title",    "")
            self._tb_customer.Text = info.get("customer", "")
            self._tb_analyst.Text  = info.get("analyst",  "")
            self._tb_rev.Text      = info.get("revision", "Rev 0")
            status = info.get("status", "Active")
            items  = [self._cb_status.Items[i]
                      for i in range(self._cb_status.Items.Count)]
            if status in items:
                self._cb_status.SelectedItem = status
            else:
                self._cb_status.SelectedIndex = 0
        except Exception as exc:
            _log("ProjectInfoPanel load error: " + str(exc))
        finally:
            self._suppress_evt = False

    def _save(self, s, e):
        try:
            repo.save_project_info({
                "title":    self._tb_title.Text,
                "customer": self._tb_customer.Text,
                "analyst":  self._tb_analyst.Text,
                "status":   str(self._cb_status.SelectedItem or "Active"),
                "revision": self._tb_rev.Text,
            })
            _log("Project info saved")
        except Exception as exc:
            _log("Save error: " + str(exc))
            WinForms.MessageBox.Show("Save failed:\n" + str(exc), "Error")

    def _on_status_changed(self, s, e):
        """
        Fires when the user changes the Status dropdown.
        If they select 'Archived', prompt to run the archive workflow.
        """
        if self._suppress_evt:
            return
        try:
            selected = str(self._cb_status.SelectedItem or "")
            if selected != "Archived":
                return   # other statuses — no action yet, reserved for future

            # Save the status first
            self._save(None, None)

            # Ask if they want to archive files now
            res = WinForms.MessageBox.Show(
                u"You have set this project to \u2018Archived\u2019 status.\n\n"
                u"Would you like to copy reference files into the project "
                u"repository archive folders now?\n\n"
                u"You can also run this later using the "
                u"\U0001F4E6 Archive Files toolbar button.",
                u"Archive Repository Files?",
                WinForms.MessageBoxButtons.YesNo,
                WinForms.MessageBoxIcon.Question)

            if res == WinForms.DialogResult.Yes:
                self._form.launch_archive_dialog()

        except Exception as exc:
            _log("Status change handler error: " + str(exc))

    def _log_revision(self, s, e):
        try:
            dlg = RevisionDialog(self._tb_rev.Text)
            if dlg.ShowDialog() == WinForms.DialogResult.OK:
                repo.add_revision_entry(dlg.result_rev, dlg.result_note)
                self._tb_rev.Text = dlg.result_rev
                self._save(None, None)
                WinForms.MessageBox.Show(
                    "Revision '{0}' logged.".format(dlg.result_rev),
                    "Revision Added")
        except Exception as exc:
            _log("Log revision error: " + str(exc))

    def _toggle(self, s, e):
        self._expanded = not self._expanded
        self._fields_panel.Visible = self._expanded
        if self._expanded:
            self.Size = Drawing.Size(1300, 106)
            self._btn_toggle.Text = u"\u25B2 Collapse"
        else:
            self.Size = Drawing.Size(1300, 36)
            self._btn_toggle.Text = u"\u25BC Expand"
        self._form.on_panel_resize()


# ────────────────────────────────────────────────────────────────────────────
#  Main Repository Form
# ────────────────────────────────────────────────────────────────────────────

class RepositoryForm(WinForms.Form):
    def __init__(self, task=None):
        self._task         = task
        self._section_data = {}
        self._sort_state   = {sec: {"col": COL_FILENAME, "asc": True}
                              for sec in repo.ALL_SECTIONS}
        self._cur_section  = repo.ALL_SECTIONS[0]

        self.Text          = "Analysis Repository Manager"
        self.Width         = 1360
        self.Height        = 900
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox   = True
        self.MaximizeBox   = True
        self.BackColor     = Drawing.Color.White
        self.Font          = _FONT_NORMAL
        self.MinimumSize   = Drawing.Size(900, 600)

        _log("RepositoryForm init start")
        self._build_ui()
        self._refresh_all(None, None)
        _log("RepositoryForm init complete")

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        lbl_h = WinForms.Label()
        lbl_h.Text      = "Analysis Repository"
        lbl_h.Font      = _FONT_TITLE
        lbl_h.ForeColor = _CLR_ANSYS_BLUE
        lbl_h.Location  = Drawing.Point(16, 10)
        lbl_h.AutoSize  = True
        self.Controls.Add(lbl_h)

        lbl_sub = WinForms.Label()
        lbl_sub.Text      = "Centralized file management for your ANSYS project"
        lbl_sub.Font      = _FONT_SMALL
        lbl_sub.ForeColor = Drawing.Color.Gray
        lbl_sub.Location  = Drawing.Point(18, 38)
        lbl_sub.AutoSize  = True
        self.Controls.Add(lbl_sub)

        toolbar_y = 62
        toolbar_h = 42
        x = 16

        self.Controls.Add(_make_btn(u"\u2795  Add File(s)...", x, toolbar_y,
                                    160, toolbar_h, primary=True,
                                    handler=self._on_add))
        x += 168
        self.Controls.Add(_make_btn(u"\u21BA  Refresh", x, toolbar_y,
                                    110, toolbar_h,
                                    handler=self._refresh_all))
        x += 118
        self.Controls.Add(_make_btn(u"\u25B6  Open", x, toolbar_y,
                                    100, toolbar_h,
                                    handler=self._on_open))
        x += 108
        self.Controls.Add(_make_btn(u"\u2716  Remove", x, toolbar_y,
                                    110, toolbar_h,
                                    handler=self._on_remove))
        x += 118
        self.Controls.Add(_make_btn(u"\u270E  Notes", x, toolbar_y,
                                    100, toolbar_h,
                                    handler=self._on_notes))
        x += 108
        self.Controls.Add(_make_btn(u"\u2764  Health Check", x, toolbar_y,
                                    140, toolbar_h,
                                    handler=self._on_health_check))
        x += 148
        self.Controls.Add(_make_btn(u"\U0001F4E6  Archive Files", x, toolbar_y,
                                    150, toolbar_h,
                                    handler=self._on_archive))

        sep = WinForms.Label()
        sep.BorderStyle = WinForms.BorderStyle.Fixed3D
        sep.Location    = Drawing.Point(16, toolbar_y + toolbar_h + 4)
        sep.Size        = Drawing.Size(1310, 2)
        self.Controls.Add(sep)

        self._info_panel = ProjectInfoPanel(self)
        self._info_panel.Location = Drawing.Point(16, toolbar_y + toolbar_h + 10)
        self.Controls.Add(self._info_panel)
        self._info_panel_bottom = (toolbar_y + toolbar_h + 10 +
                                   self._info_panel.Height + 4)

        self._tabs = WinForms.TabControl()
        self._tabs.Location  = Drawing.Point(16, self._info_panel_bottom)
        self._tabs.Anchor    = (WinForms.AnchorStyles.Top    |
                                WinForms.AnchorStyles.Bottom |
                                WinForms.AnchorStyles.Left   |
                                WinForms.AnchorStyles.Right)
        self._tabs.Font      = _FONT_NORMAL
        self._tabs.Padding   = Drawing.Point(12, 4)
        self._tabs.ItemSize  = Drawing.Size(0, 28)
        self._tabs.DrawMode  = WinForms.TabDrawMode.OwnerDrawFixed
        self._tabs.DrawItem += self._on_draw_tab
        self._tabs.SelectedIndexChanged += self._on_tab_changed

        self._listviews = {}
        for sec in repo.ALL_SECTIONS:
            tab = WinForms.TabPage()
            tab.Text      = repo.SECTION_LABELS[sec]
            tab.Padding   = WinForms.Padding(4)
            tab.BackColor = Drawing.Color.White

            lv = self._make_listview(sec)
            lv.Anchor   = (WinForms.AnchorStyles.Top    |
                           WinForms.AnchorStyles.Bottom |
                           WinForms.AnchorStyles.Left   |
                           WinForms.AnchorStyles.Right)
            lv.Location = Drawing.Point(0, 0)
            lv.Size     = Drawing.Size(tab.Width, tab.Height)

            tab.Controls.Add(lv)
            self._tabs.TabPages.Add(tab)
            self._listviews[sec] = lv

        self.Controls.Add(self._tabs)

        self._status_bar = WinForms.StatusStrip()
        self._status_lbl = WinForms.ToolStripStatusLabel()
        self._status_lbl.Text = "Ready"
        self._status_bar.Items.Add(self._status_lbl)
        self.Controls.Add(self._status_bar)

        self.Resize += self._on_form_resize
        self._do_layout()

    def _make_listview(self, section):
        lv = WinForms.ListView()
        lv.View          = WinForms.View.Details
        lv.FullRowSelect  = True
        lv.GridLines      = True
        lv.MultiSelect    = True
        lv.Font           = _FONT_BOLD
        lv.HeaderStyle    = WinForms.ColumnHeaderStyle.Clickable
        lv.Tag            = section

        for name, w in [("File Name",  380), ("Status",    90),
                        ("Size (MB)",   90), ("Modified", 150),
                        ("Date Added", 150), ("Notes",    250),
                        ("Full Path",  400)]:
            lv.Columns.Add(name, w)

        lv.ColumnClick  += self._on_column_click
        lv.DoubleClick  += self._on_double_click
        lv.MouseUp      += self._on_list_mouse_up
        return lv

    # ── Tab drawing ───────────────────────────────────────────────────────

    def _on_draw_tab(self, s, e):
        try:
            is_active = (e.Index == self._tabs.SelectedIndex)
            bg   = _CLR_ANSYS_BLUE if is_active else Drawing.Color.FromArgb(
                240, 240, 240)
            fg   = Drawing.Color.White if is_active else Drawing.Color.FromArgb(
                100, 100, 100)
            font = _FONT_BOLD if is_active else _FONT_BOLD
            e.Graphics.FillRectangle(Drawing.SolidBrush(bg), e.Bounds)
            fmt = Drawing.StringFormat()
            fmt.Alignment     = Drawing.StringAlignment.Center
            fmt.LineAlignment = Drawing.StringAlignment.Center
            e.Graphics.DrawString(
                self._tabs.TabPages[e.Index].Text, font,
                Drawing.SolidBrush(fg),
                Drawing.RectangleF(e.Bounds.X, e.Bounds.Y,
                                   e.Bounds.Width, e.Bounds.Height), fmt)
        except Exception as exc:
            _log("Tab draw error: " + str(exc))

    # ── Layout ────────────────────────────────────────────────────────────

    def on_panel_resize(self):
        self._info_panel_bottom = (self._info_panel.Top +
                                   self._info_panel.Height + 4)
        self._do_layout()

    def _on_form_resize(self, s, e):
        self._do_layout()

    def _do_layout(self):
        sb_h  = self._status_bar.Height
        top   = self._info_panel_bottom
        avail = self.ClientSize.Height - top - sb_h - 4
        if avail < 100:
            avail = 100
        self._tabs.Location = Drawing.Point(16, top)
        self._tabs.Size     = Drawing.Size(self.ClientSize.Width - 32, avail)

    def _on_tab_changed(self, s, e):
        idx = self._tabs.SelectedIndex
        if 0 <= idx < len(repo.ALL_SECTIONS):
            self._cur_section = repo.ALL_SECTIONS[idx]
        self._tabs.Invalidate()

    # ── Column sort ───────────────────────────────────────────────────────

    def _on_column_click(self, s, e):
        try:
            lv  = s
            sec = lv.Tag if lv.Tag else self._cur_section
            st  = self._sort_state[sec]
            if st["col"] == e.Column:
                st["asc"] = not st["asc"]
            else:
                st["col"] = e.Column
                st["asc"] = True
            self._sort_listview(sec)
        except Exception as exc:
            _log("Column click error: " + str(exc))

    def _sort_listview(self, section):
        records = self._section_data.get(section, [])
        if not records:
            return
        st  = self._sort_state[section]
        col = st["col"]
        asc = st["asc"]
        key_map = {
            COL_FILENAME:  "label",
            COL_STATUS:    "status",
            COL_SIZE:      "size_mb",
            COL_MODIFIED:  "modified",
            COL_DATEADDED: "date_added",
            COL_NOTES:     "notes",
            COL_FULLPATH:  "source_path",
        }
        key = key_map.get(col, "label")

        def sort_key(r):
            val = r.get(key, "") or ""
            if col == COL_SIZE:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return 0.0
            return val.lower()

        self._section_data[section] = sorted(
            records, key=sort_key, reverse=not asc)
        self._populate_listview(section, self._section_data[section])

    # ── Data / population ─────────────────────────────────────────────────

    def _refresh_all(self, sender, e):
        try:
            _log("Refresh all sections")
            for sec in repo.ALL_SECTIONS:
                records = repo.get_section_records(sec)
                self._section_data[sec] = records
                self._sort_listview(sec)
            total, missing = repo.get_summary_stats()
            self._set_status(
                u"Loaded \u2014 {0} file(s), {1} missing".format(
                    total, missing))
            self._update_tab_labels()
        except Exception as exc:
            _log("Refresh error: " + traceback.format_exc())
            self._set_status("Refresh error: " + str(exc))

    def _populate_listview(self, section, records):
        lv = self._listviews[section]
        sel_paths = set()
        for item in lv.SelectedItems:
            try:
                sel_paths.add(item.SubItems[COL_FULLPATH].Text)
            except Exception:
                pass

        lv.Items.Clear()
        for r in records:
            item   = lv.Items.Add(r.get("label", "Unnamed"))
            status = r.get("status", "?")
            item.SubItems.Add(status)
            item.SubItems.Add(r.get("size_mb",    u"\u2014"))
            item.SubItems.Add(r.get("modified",   u"\u2014"))
            item.SubItems.Add(r.get("date_added", ""))
            item.SubItems.Add(r.get("notes",      ""))
            path = r.get("source_path", "")
            item.SubItems.Add(path)

            if status == repo.ARCH_STATUS_MISSING:
                item.ForeColor = _CLR_MISSING
                item.Font      = _FONT_BOLD
            elif status == repo.ARCH_STATUS_OK:
                item.ForeColor = _CLR_ARCHIVED_OK
                item.Font      = _FONT_NORMAL
            elif status == repo.ARCH_STATUS_OUTDATED:
                item.ForeColor = _CLR_ARCHIVED_OLD
                item.Font      = _FONT_BOLD   # bold + orange = visual double indicator
            else:
                item.ForeColor = Drawing.Color.Black
                item.Font      = _FONT_NORMAL

            if path in sel_paths:
                item.Selected = True

    def _update_tab_labels(self):
        for i, sec in enumerate(repo.ALL_SECTIONS):
            records = self._section_data.get(sec, [])
            total   = len(records)
            missing = sum(1 for r in records
                          if r.get("status") == repo.ARCH_STATUS_MISSING)
            base    = repo.SECTION_LABELS[sec]
            if missing > 0:
                self._tabs.TabPages[i].Text = (
                    u"{0}  [{1}  \u2718{2}]".format(base, total, missing))
            else:
                self._tabs.TabPages[i].Text = (
                    u"{0}  [{1}]".format(base, total))

    def _set_status(self, msg):
        self._status_lbl.Text = msg

    # ── Selection helpers ─────────────────────────────────────────────────

    def _current_lv(self):
        return self._listviews.get(self._cur_section)

    def _selected_records(self):
        lv      = self._current_lv()
        records = self._section_data.get(self._cur_section, [])
        result  = []
        for item in lv.SelectedItems:
            idx = item.Index
            if 0 <= idx < len(records):
                result.append((idx, records[idx]))
        return result

    # ── Right-click context menu ──────────────────────────────────────────

    def _on_list_mouse_up(self, s, e):
        if e.Button != WinForms.MouseButtons.Right:
            return
        try:
            lv  = s
            sec = lv.Tag if lv.Tag else self._cur_section
            hit = lv.HitTest(e.X, e.Y)
            if hit.Item is None:
                return
            hit.Item.Selected = True
            lv.Select()

            records = self._section_data.get(sec, [])
            idx     = hit.Item.Index
            if idx < 0 or idx >= len(records):
                return
            record  = records[idx]
            status  = record.get("status", "")
            missing = (status == repo.ARCH_STATUS_MISSING)
            outdated= (status == repo.ARCH_STATUS_OUTDATED)

            menu = WinForms.ContextMenuStrip()

            item_open = menu.Items.Add(u"\u25B6  Open")
            item_open.Enabled = not missing
            item_open.Click  += lambda s2, e2: self._on_open(None, None)

            item_notes = menu.Items.Add(u"\u270E  Edit Notes")
            item_notes.Click += lambda s2, e2: self._on_notes(None, None)

            menu.Items.Add(WinForms.ToolStripSeparator())

            item_relink = menu.Items.Add(u"\u27A1  Relink Missing File\u2026")
            item_relink.Enabled = missing
            _idx = idx
            _sec = sec
            item_relink.Click += lambda s2, e2: self._on_relink(_sec, _idx)

            item_rearchive = menu.Items.Add(
                u"\u27F3  Re-archive (update copy)")
            item_rearchive.Enabled = outdated
            item_rearchive.Click  += lambda s2, e2: self._on_rearchive(
                _sec, _idx)

            menu.Items.Add(WinForms.ToolStripSeparator())

            item_remove = menu.Items.Add(u"\u2716  Remove from Repository")
            item_remove.Click += lambda s2, e2: self._on_remove(None, None)

            menu.Show(lv, Drawing.Point(e.X, e.Y))
        except Exception as exc:
            _log("Context menu error: " + str(exc))

    # ── Archive launcher (public — called by ProjectInfoPanel) ────────────

    def launch_archive_dialog(self):
        """Open the archive dialog. Called from status dropdown or toolbar."""
        try:
            open_proj  = _get_open_project_path()
            candidates = repo.get_archive_candidates(open_proj)

            if not candidates:
                WinForms.MessageBox.Show(
                    "No eligible files found to archive.\n\n"
                    "Add files to the repository first.\n\n"
                    "Note: the currently open project is automatically "
                    "excluded from archiving.",
                    "Nothing to Archive")
                return

            dlg = ArchiveDialog(candidates, open_proj)
            if dlg.ShowDialog() == WinForms.DialogResult.OK:
                self._refresh_all(None, None)
                archived = dlg._archived_results
                if archived:
                    self._set_status(
                        u"Archived {0} file(s): {1}".format(
                            len(archived),
                            ", ".join(archived[:3]) +
                            ("..." if len(archived) > 3 else "")))
        except Exception as exc:
            _log("launch_archive_dialog error: " + traceback.format_exc())
            WinForms.MessageBox.Show(
                "Archive dialog error:\n" + str(exc), "Error")

    # ── Re-archive single file ────────────────────────────────────────────

    def _on_rearchive(self, section, index):
        """Re-archive a single outdated file from the right-click menu."""
        try:
            records = self._section_data.get(section, [])
            if index < 0 or index >= len(records):
                return
            record = records[index]
            src    = record.get("source_path", "")
            label  = record.get("label", "")

            open_proj = _get_open_project_path()
            if (open_proj and os.path.normcase(os.path.abspath(src)) ==
                    os.path.normcase(os.path.abspath(open_proj))):
                WinForms.MessageBox.Show(
                    "Cannot archive the currently open project.",
                    "Not Allowed")
                return

            dest_dir = repo.get_section_archive_dir(section)
            ext      = os.path.splitext(src)[1].lower()

            if ext == ".wbpj":
                runwb2 = _get_runwb2_path()
                if runwb2:
                    res = WinForms.MessageBox.Show(
                        u"Re-archive '{0}' using ANSYS ARCHIVE (.wbpz)?".format(
                            label),
                        "Confirm Re-archive",
                        WinForms.MessageBoxButtons.YesNo)
                    if res != WinForms.DialogResult.Yes:
                        return
                    dlg = ArchiveDialog([repo.get_archive_candidates(
                        open_proj)[0]], open_proj)
                    script_path, expected_wbpz, marker_path = (
                        repo.generate_wbpz_script(src, dest_dir))
                    info = System.Diagnostics.ProcessStartInfo()
                    info.FileName               = runwb2
                    info.Arguments              = u'-B -R "{0}"'.format(
                        script_path)
                    info.UseShellExecute        = False
                    info.CreateNoWindow         = True
                    info.RedirectStandardOutput = True
                    info.RedirectStandardError  = True
                    proc = System.Diagnostics.Process.Start(info)
                    prog = ArchiveProgressDialog(
                        u"Re-archiving: {0}".format(label), proc)
                    prog.ShowDialog()
                    try:
                        stdout = proc.StandardOutput.ReadToEnd()
                        if stdout.strip():
                            _log("Re-archive RunWB2 output: " +
                                 stdout.strip()[:500])
                    except Exception:
                        pass
                    repo.cleanup_archive_script(script_path)
                    if os.path.exists(expected_wbpz):
                        repo.update_archive_record(section, index,
                                                   expected_wbpz, "wbpz")
                    else:
                        _log("Re-archive: .wbpz not found at " + expected_wbpz)
                        WinForms.MessageBox.Show(
                            "Re-archive did not produce the expected .wbpz.\n"
                            "Check the debug log for details.",
                            "Re-archive Warning")
                else:
                    dest_path = repo.copy_wbpj_with_files(src, dest_dir)
                    repo.update_archive_record(section, index,
                                               dest_path, "copy_with_files")
            else:
                dest_path = repo.archive_regular_file(src, dest_dir)
                repo.update_archive_record(section, index, dest_path, "copy")

            self._refresh_all(None, None)
            self._set_status(u"Re-archived: {0}".format(label))

        except Exception as exc:
            _log("Re-archive error: " + str(exc))
            WinForms.MessageBox.Show("Re-archive failed:\n" + str(exc), "Error")

    # ── Relink ────────────────────────────────────────────────────────────

    def _on_relink(self, section, index):
        try:
            records = self._section_data.get(section, [])
            if index < 0 or index >= len(records):
                return
            record   = records[index]
            old_path = record.get("source_path", "")
            old_name = os.path.basename(old_path) if old_path else ""

            dlg = WinForms.OpenFileDialog()
            dlg.Title    = u"Relink: locate \"{0}\"".format(old_name)
            dlg.Filter   = "All Files (*.*)|*.*"
            dlg.FileName = old_name
            if dlg.ShowDialog() != WinForms.DialogResult.OK:
                return

            new_path = dlg.FileName
            repo.relink_file_record(section, index, new_path)
            self._refresh_all(None, None)
            self._set_status(
                u"Relinked: {0}".format(os.path.basename(new_path)))
        except Exception as exc:
            _log("Relink error: " + str(exc))
            WinForms.MessageBox.Show("Relink failed:\n" + str(exc), "Error")

    # ── Toolbar handlers ──────────────────────────────────────────────────

    def _on_add(self, sender, e):
        try:
            dlg = WinForms.OpenFileDialog()
            dlg.Multiselect = True
            dlg.Title       = "Add File(s) to {0}".format(
                repo.SECTION_LABELS.get(self._cur_section, self._cur_section))
            dlg.Filter = ("All Files (*.*)|*.*|"
                          "Workbench Projects (*.wbpj;*.wbpz)|*.wbpj;*.wbpz|"
                          "Spreadsheets (*.xlsx;*.xls;*.xlsm)|*.xlsx;*.xls;*.xlsm|"
                          "PDF Files (*.pdf)|*.pdf|"
                          "Text / Data (*.txt;*.csv;*.json)|*.txt;*.csv;*.json")
            if dlg.ShowDialog() == WinForms.DialogResult.OK:
                added = skipped = 0
                for path in dlg.FileNames:
                    if repo.add_file_record(self._cur_section, path):
                        added += 1
                    else:
                        skipped += 1
                self._refresh_all(None, None)
                self._set_status(
                    u"Added {0} file(s). {1} duplicate(s) skipped.".format(
                        added, skipped))
        except Exception as exc:
            _log("Add error: " + traceback.format_exc())
            WinForms.MessageBox.Show("Add failed:\n" + str(exc), "Error")

    def _on_open(self, sender, e):
        try:
            sel = self._selected_records()
            if not sel:
                WinForms.MessageBox.Show("Select a file first.", "Open")
                return
            _, record = sel[0]
            path = record.get("source_path", "")
            if not _smart_open_file(path):
                WinForms.MessageBox.Show(
                    "Failed to open:\n" + path, "Open Error")
        except Exception as exc:
            _log("Open error: " + str(exc))

    def _on_double_click(self, sender, e):
        self._on_open(sender, e)

    def _on_remove(self, sender, e):
        try:
            sel = self._selected_records()
            if not sel:
                return
            names = "\n".join(r.get("label", "?") for _, r in sel)
            if WinForms.MessageBox.Show(
                    "Remove {0} file(s) from the repository?\n\n{1}".format(
                        len(sel), names),
                    "Confirm Remove",
                    WinForms.MessageBoxButtons.YesNo
                    ) != WinForms.DialogResult.Yes:
                return
            for idx, _ in sorted(sel, key=lambda t: t[0], reverse=True):
                repo.remove_file_record(self._cur_section, idx)
            self._refresh_all(None, None)
        except Exception as exc:
            _log("Remove error: " + traceback.format_exc())
            WinForms.MessageBox.Show("Remove failed:\n" + str(exc), "Error")

    def _on_notes(self, sender, e):
        try:
            sel = self._selected_records()
            if not sel:
                WinForms.MessageBox.Show("Select a file first.", "Notes")
                return
            idx, record = sel[0]
            dlg = NotesDialog(record.get("notes", ""))
            if dlg.ShowDialog() == WinForms.DialogResult.OK:
                repo.update_file_notes(self._cur_section, idx,
                                       dlg.result_notes)
                self._refresh_all(None, None)
        except Exception as exc:
            _log("Notes error: " + str(exc))

    def _on_health_check(self, sender, e):
        try:
            self._set_status("Running health check...")
            health = repo.run_health_check()
            HealthCheckDialog(health).ShowDialog()
            self._refresh_all(None, None)
            self._set_status("Health check complete.")
        except Exception as exc:
            _log("Health check error: " + str(exc))
            WinForms.MessageBox.Show(
                "Health check failed:\n" + str(exc), "Error")

    def _on_archive(self, sender, e):
        self.launch_archive_dialog()


# ────────────────────────────────────────────────────────────────────────────
#  Form launcher
# ────────────────────────────────────────────────────────────────────────────

def _launch_repository_form(task=None):
    try:
        _log("=== Launching Repository Form ===")
        user_files_dir = _resolve_project_dir(task)

        if not user_files_dir:
            WinForms.MessageBox.Show(
                "No saved Workbench project was found.\n\n"
                "Please save your project first:\n"
                u"    File  \u2192  Save As\u2026\n\n"
                "Then click the Analysis Repository button again.",
                u"Analysis Hub \u2014 Save Project First",
                WinForms.MessageBoxButtons.OK,
                WinForms.MessageBoxIcon.Information)
            return

        repo.set_base_directory(user_files_dir)
        RepositoryForm(task).ShowDialog()

    except Exception as exc:
        _log("_launch_repository_form error:\n" + traceback.format_exc())
        try:
            WinForms.MessageBox.Show(
                "Analysis Hub encountered an error:\n\n" + str(exc),
                "Analysis Hub Error",
                WinForms.MessageBoxButtons.OK,
                WinForms.MessageBoxIcon.Error)
        except Exception:
            pass


# ────────────────────────────────────────────────────────────────────────────
#  ACT callbacks
# ────────────────────────────────────────────────────────────────────────────

def init(ext):
    try:
        _log("Extension init: InstallDir = " + ext.InstallDir)
        ext_subdir = os.path.join(ext.InstallDir, "AnalysisHub")
        if ext_subdir not in sys.path:
            sys.path.insert(0, ext_subdir)
    except Exception as exc:
        _log("init error: " + str(exc))


def task_initialize(task):
    try:
        _log("task_initialize: " + task.Name)
        task.Properties["ProjectTitle"].Value  = ""
        task.Properties["Customer"].Value      = ""
        task.Properties["Analyst"].Value       = ""
        task.Properties["ProjectStatus"].Value = "Active"
        task.Properties["Revision"].Value      = "Rev 0"
        task.Properties["TotalFiles"].Value    = "0"
        task.Properties["MissingFiles"].Value  = "0"
        task.Properties["LastRefresh"].Value   = "Never"
    except Exception as exc:
        _log("task_initialize error: " + str(exc))


def task_edit(task):
    try:
        _log("task_edit called")
        _launch_repository_form(task)
        _sync_task_properties(task)
    except Exception as exc:
        _log("task_edit error: " + str(exc))


def task_update(task):
    try:
        _log("task_update called")
        user_files_dir = _resolve_project_dir(task)
        if user_files_dir:
            repo.set_base_directory(user_files_dir)
            _sync_task_properties(task)
    except Exception as exc:
        _log("task_update error: " + str(exc))


def task_refresh(task):
    try:
        _log("task_refresh called")
        task_update(task)
    except Exception as exc:
        _log("task_refresh error: " + str(exc))


def task_reset(task):
    _log("task_reset called")


def task_status(task):
    try:
        user_files_dir = _resolve_project_dir(task)
        if not user_files_dir:
            return ["Unfulfilled",
                    "No project directory found - please save the project"]
        repo.set_base_directory(user_files_dir)
        total, missing = repo.get_summary_stats()
        if total == 0:
            return ["Unfulfilled",
                    "Repository is empty - add files to get started"]
        elif missing > 0:
            return ["Refresh Required",
                    "{0} file(s) missing from repository".format(missing)]
        else:
            return ["UpToDate",
                    "Repository OK - {0} file(s) tracked".format(total)]
    except Exception as exc:
        _log("task_status error: " + str(exc))
        return ["UpToDate", "Repository"]


def task_report(task, report):
    try:
        _log("task_report called")
        total, missing = repo.get_summary_stats()
        info = repo.get_project_info()
        lines = [
            "Analysis Repository Report",
            "---------------------------",
            "Project:  " + info.get("title",    u"\u2014"),
            "Customer: " + info.get("customer", u"\u2014"),
            "Analyst:  " + info.get("analyst",  u"\u2014"),
            "Status:   " + info.get("status",   u"\u2014"),
            "Revision: " + info.get("revision", u"\u2014"),
            "",
            "Total files:   {0}".format(total),
            "Missing files: {0}".format(missing),
        ]
        report.AddLine("\n".join(lines))
    except Exception as exc:
        _log("task_report error: " + str(exc))


def task_delete(task):
    _log("task_delete called")


def context_refresh(task):
    try:
        _log("context_refresh called")
        user_files_dir = _resolve_project_dir(task)
        if user_files_dir:
            repo.set_base_directory(user_files_dir)
        _sync_task_properties(task)
        total, missing = repo.get_summary_stats()
        WinForms.MessageBox.Show(
            u"Repository refreshed.\nTotal: {0}   Missing: {1}".format(
                total, missing),
            u"Analysis Hub \u2014 Refresh")
    except Exception as exc:
        _log("context_refresh error: " + str(exc))


def context_health_check(task):
    try:
        _log("context_health_check called")
        user_files_dir = _resolve_project_dir(task)
        if user_files_dir:
            repo.set_base_directory(user_files_dir)
        HealthCheckDialog(repo.run_health_check()).ShowDialog()
    except Exception as exc:
        _log("context_health_check error: " + str(exc))


def toolbar_open_repository(task=None):
    try:
        _log("toolbar_open_repository called")
        _launch_repository_form(task)
    except Exception as exc:
        _log("toolbar_open_repository error: " + str(exc))


def _sync_task_properties(task):
    try:
        user_files_dir = _resolve_project_dir(task)
        if not user_files_dir:
            return
        repo.set_base_directory(user_files_dir)
        total, missing = repo.get_summary_stats()
        info = repo.get_project_info()

        task.Properties["TotalFiles"].Value   = str(total)
        task.Properties["MissingFiles"].Value = str(missing)
        task.Properties["LastRefresh"].Value  = datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M")

        for field, prop in [("title",    "ProjectTitle"),
                             ("customer", "Customer"),
                             ("analyst",  "Analyst"),
                             ("status",   "ProjectStatus"),
                             ("revision", "Revision")]:
            val = info.get(field, "")
            if val:
                try:
                    task.Properties[prop].Value = val
                except Exception:
                    pass
    except Exception as exc:
        _log("_sync_task_properties error: " + str(exc))
