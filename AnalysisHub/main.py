# -*- coding: utf-8 -*-
"""
main.py  —  AnalysisHub ACT Extension  (Entry Point)
=====================================================
IronPython 2.7 / ANSYS Workbench 2024 R2+

v7 — Smart Open / ZIP Extract workflow
---------------------------------------
* Context-aware open: source vs archive vs extract
* ZipExtractDialog: choose extraction location (beside ZIP or custom)
* ZipOpenDialog: open existing extract / re-extract / different location
* OpenChoiceDialog: open source vs open archive copy (non-ZIP archived files)
* Stale path pruning: local_extract_path and source_path cleaned on open
* Designate extracted copy as working source
* Archive toolbar button + status-dropdown trigger
* Sort, right-click menu, relink, tab drawing, bold headers
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
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a") as fh:
            fh.write("[{0}] MAIN >>> {1}\n".format(ts, msg))
        print("[{0}] MAIN >>> {1}".format(ts, msg))
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
    try:
        p = Project.GetProjectFile()
        if p and p.strip():
            return p.strip()
    except Exception:
        pass
    return None


def _get_runwb2_path():
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
    for candidate in [
        r"C:\Program Files\ANSYS Inc\v242\Framework\bin\Win64\RunWB2.exe",
        r"C:\Program Files\ANSYS Inc\v251\Framework\bin\Win64\RunWB2.exe",
    ]:
        if os.path.exists(candidate):
            return candidate
    return None


# ────────────────────────────────────────────────────────────────────────────
#  Smart file opener  (low-level — opens a single known path)
# ────────────────────────────────────────────────────────────────────────────

def _smart_open_file(path):
    if not path or not os.path.exists(path):
        _log("Open failed - not found: " + str(path))
        return False
    ext = os.path.splitext(path)[1].lower()
    _log("Opening: {0}  (ext={1})".format(path, ext))
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
_CLR_ARCHIVED_OK = Drawing.Color.FromArgb(0,   102, 204)
_CLR_ARCHIVED_OLD= Drawing.Color.FromArgb(200, 100,   0)
_CLR_GREEN_DIM   = Drawing.Color.FromArgb(0,   128,   0)
_CLR_WARN_BG     = Drawing.Color.FromArgb(255, 244, 206)

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
        lbl.Text = "Notes / Description:"
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

        self.Controls.Add(_make_btn("OK",     260, 185, 90, 32, primary=True,
                                    handler=self._ok))
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
        self.result_rev  = ""
        self.result_note = ""
        self.Text          = "Add Revision Entry"
        self.Width         = 460
        self.Height        = 240
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox   = False
        self.MaximizeBox   = False
        self.BackColor     = Drawing.Color.White
        self.Font          = _FONT_NORMAL

        lbl_rev = WinForms.Label()
        lbl_rev.Text = "Revision label (e.g. Rev A, v1.2):"
        lbl_rev.Location = Drawing.Point(12, 14)
        lbl_rev.AutoSize = True
        self.Controls.Add(lbl_rev)

        self._tb_rev = WinForms.TextBox()
        self._tb_rev.Location = Drawing.Point(12, 36)
        self._tb_rev.Size     = Drawing.Size(420, 28)
        self._tb_rev.Text     = current_rev
        self.Controls.Add(self._tb_rev)

        lbl_note = WinForms.Label()
        lbl_note.Text = "Change note:"
        lbl_note.Location = Drawing.Point(12, 74)
        lbl_note.AutoSize = True
        self.Controls.Add(lbl_note)

        self._tb_note = WinForms.TextBox()
        self._tb_note.Multiline = True
        self._tb_note.Location  = Drawing.Point(12, 96)
        self._tb_note.Size      = Drawing.Size(420, 68)
        self.Controls.Add(self._tb_note)

        self.Controls.Add(_make_btn("Save",   240, 172, 90, 32, primary=True,
                                    handler=self._ok))
        self.Controls.Add(_make_btn("Cancel", 340, 172, 90, 32,
                                    handler=self._cancel))

    def _ok(self, s, e):
        self.result_rev  = self._tb_rev.Text.strip()
        self.result_note = self._tb_note.Text.strip()
        if not self.result_rev:
            WinForms.MessageBox.Show("Please enter a revision label.", "Validation")
            return
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()

    def _cancel(self, s, e):
        self.DialogResult = WinForms.DialogResult.Cancel
        self.Close()


# ────────────────────────────────────────────────────────────────────────────
#  Health-check dialog
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

        total    = health["total"]
        missing  = health["missing"]
        ready    = health["ready"]
        arch_ok  = health.get("archived_ok", 0)
        arch_old = health.get("archived_old", 0)
        colour   = _CLR_MISSING if missing > 0 else _CLR_READY
        icon     = u"\u2718 ISSUES FOUND" if missing > 0 else u"\u2714 ALL FILES OK"

        lbl_icon = WinForms.Label()
        lbl_icon.Text      = icon
        lbl_icon.Font      = Drawing.Font("Segoe UI", 13, Drawing.FontStyle.Bold)
        lbl_icon.ForeColor = colour
        lbl_icon.Location  = Drawing.Point(16, 14)
        lbl_icon.AutoSize  = True
        self.Controls.Add(lbl_icon)

        lbl_sum = WinForms.Label()
        lbl_sum.Text = ("Total: {0}   Ready: {1}   Missing: {2}   "
                        "Archived OK: {3}   Outdated: {4}".format(
                            total, ready, missing, arch_ok, arch_old))
        lbl_sum.Location = Drawing.Point(16, 46)
        lbl_sum.AutoSize = True
        self.Controls.Add(lbl_sum)

        if missing > 0:
            lbl_hint = WinForms.Label()
            lbl_hint.Text = u"Select a missing file and click \u27A1 Relink."
            lbl_hint.Font      = _FONT_SMALL
            lbl_hint.ForeColor = Drawing.Color.Gray
            lbl_hint.Location  = Drawing.Point(16, 66)
            lbl_hint.AutoSize  = True
            self.Controls.Add(lbl_hint)

        self._lv = WinForms.ListView()
        self._lv.View         = WinForms.View.Details
        self._lv.FullRowSelect = True
        self._lv.GridLines     = True
        self._lv.Location      = Drawing.Point(16, 86)
        self._lv.Size          = Drawing.Size(690, 340)
        self._lv.Font          = _FONT_NORMAL
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

        self._btn_relink = _make_btn(u"\u27A1  Relink Selected\u2026",
                                      16, 440, 160, 32,
                                      handler=self._on_relink)
        self._btn_relink.Enabled = (missing > 0)
        self.Controls.Add(self._btn_relink)
        self._lv.SelectedIndexChanged += self._on_sel_changed

        self.Controls.Add(_make_btn("Close", 620, 440, 100, 32, primary=True,
                                    handler=lambda s, e: self.Close()))

    def _on_sel_changed(self, s, e):
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
                    "Could not locate this record.\nClose and Refresh, then try again.",
                    "Relink Error")
                return
            dlg = WinForms.OpenFileDialog()
            dlg.Title    = u"Relink: locate \"{0}\"".format(old_name)
            dlg.Filter   = "All Files (*.*)|*.*"
            dlg.FileName = old_name
            if dlg.ShowDialog() != WinForms.DialogResult.OK:
                return
            repo.relink_file_record(section, index, dlg.FileName)
            selected.SubItems[2].Text = dlg.FileName
            selected.SubItems[1].Text = os.path.basename(dlg.FileName)
            selected.ForeColor        = _CLR_READY
            still = sum(1 for i in range(self._lv.Items.Count)
                        if self._lv.Items[i].ForeColor == _CLR_MISSING)
            if still == 0:
                WinForms.MessageBox.Show(
                    u"\u2714 All missing files relinked.\nClose then Refresh.",
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
#  Archive progress dialog
# ────────────────────────────────────────────────────────────────────────────

class ArchiveProgressDialog(WinForms.Form):
    """Marquee progress dialog for copy/zip/extract operations."""

    def __init__(self, label_text, process=None):
        self._process = process
        self._success = False
        self._elapsed = 0

        self.Text          = "Working..."
        self.Width         = 520
        self.Height        = 160
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
        self._lbl_status.Text      = "Working..."
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
        bar.Location = Drawing.Point(16, 88)
        bar.Size     = Drawing.Size(480, 22)
        self.Controls.Add(bar)

        self._timer = WinForms.Timer()
        self._timer.Interval = 500
        self._timer.Tick    += self._on_tick
        self._timer.Start()

    def set_status(self, msg):
        self._lbl_status.Text = msg
        WinForms.Application.DoEvents()

    def finish_success(self):
        self._timer.Stop()
        self._success = True
        self._lbl_status.Text = u"\u2714 Done."
        WinForms.Application.DoEvents()
        System.Threading.Thread.Sleep(300)
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()

    def _on_tick(self, s, e):
        try:
            self._elapsed += 0.5
            self._lbl_time.Text = "Elapsed: {0:.0f}s".format(self._elapsed)
            if self._process is not None and self._process.HasExited:
                self._timer.Stop()
                self._success = (self._process.ExitCode == 0)
                self._lbl_status.Text = (u"\u2714 Complete." if self._success
                                         else u"\u26A0 Completed with warnings.")
                WinForms.Application.DoEvents()
                System.Threading.Thread.Sleep(600)
                self.DialogResult = WinForms.DialogResult.OK
                self.Close()
        except Exception as exc:
            self._timer.Stop()
            _log("ArchiveProgressDialog tick error: " + str(exc))
            self.Close()

    @property
    def succeeded(self):
        return self._success


# ────────────────────────────────────────────────────────────────────────────
#  Open Choice dialog  (source vs archive for non-ZIP archived files)
# ────────────────────────────────────────────────────────────────────────────

class OpenChoiceDialog(WinForms.Form):
    """
    Shown when a file has both a source reference and a non-ZIP archive copy.
    User chooses which to open.
    """

    def __init__(self, record):
        self.open_path = ""

        src  = record.get("source_path", "")
        arch = record.get("archive_path", "")
        label = record.get("label", "File")

        self.Text          = u"Open: {0}".format(label)
        self.Width         = 640
        self.Height        = 300
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox   = False
        self.MaximizeBox   = False
        self.BackColor     = Drawing.Color.White
        self.Font          = _FONT_NORMAL

        lbl_hdr = WinForms.Label()
        lbl_hdr.Text = ("This file has both a source reference and an "
                        "archive copy. Which would you like to open?")
        lbl_hdr.Location = Drawing.Point(16, 14)
        lbl_hdr.Size     = Drawing.Size(594, 34)
        self.Controls.Add(lbl_hdr)

        # Source option
        self._rb_src = WinForms.RadioButton()
        self._rb_src.Text     = "Open source file  (current working version)"
        self._rb_src.Location = Drawing.Point(16, 58)
        self._rb_src.Size     = Drawing.Size(580, 20)
        self._rb_src.Checked  = True
        self.Controls.Add(self._rb_src)

        lbl_src_path = WinForms.Label()
        lbl_src_path.Text      = "   " + src
        lbl_src_path.Font      = _FONT_SMALL
        lbl_src_path.ForeColor = Drawing.Color.FromArgb(60, 60, 60)
        lbl_src_path.Location  = Drawing.Point(28, 80)
        lbl_src_path.Size      = Drawing.Size(580, 16)
        self.Controls.Add(lbl_src_path)

        try:
            src_mod = datetime.datetime.fromtimestamp(
                os.path.getmtime(src)).strftime("%Y-%m-%d %H:%M")
            src_sz  = "{0:.2f} MB".format(
                os.path.getsize(src) / (1024.0 * 1024))
        except Exception:
            src_mod = ""
            src_sz  = ""

        lbl_src_info = WinForms.Label()
        lbl_src_info.Text      = u"   Modified: {0}   Size: {1}".format(
            src_mod, src_sz)
        lbl_src_info.Font      = _FONT_SMALL
        lbl_src_info.ForeColor = Drawing.Color.Gray
        lbl_src_info.Location  = Drawing.Point(28, 96)
        lbl_src_info.Size      = Drawing.Size(580, 16)
        self.Controls.Add(lbl_src_info)

        # Separator
        sep = WinForms.Label()
        sep.BorderStyle = WinForms.BorderStyle.Fixed3D
        sep.Location    = Drawing.Point(16, 122)
        sep.Size        = Drawing.Size(594, 2)
        self.Controls.Add(sep)

        # Archive option
        self._rb_arch = WinForms.RadioButton()
        self._rb_arch.Text     = "Open archive copy  (snapshot saved to repository)"
        self._rb_arch.Location = Drawing.Point(16, 132)
        self._rb_arch.Size     = Drawing.Size(580, 20)
        self.Controls.Add(self._rb_arch)

        lbl_arch_path = WinForms.Label()
        lbl_arch_path.Text      = "   " + arch
        lbl_arch_path.Font      = _FONT_SMALL
        lbl_arch_path.ForeColor = Drawing.Color.FromArgb(60, 60, 60)
        lbl_arch_path.Location  = Drawing.Point(28, 154)
        lbl_arch_path.Size      = Drawing.Size(580, 16)
        self.Controls.Add(lbl_arch_path)

        arch_date = record.get("archive_date", "")
        lbl_arch_info = WinForms.Label()
        lbl_arch_info.Text      = u"   Archived: {0}".format(arch_date)
        lbl_arch_info.Font      = _FONT_SMALL
        lbl_arch_info.ForeColor = Drawing.Color.Gray
        lbl_arch_info.Location  = Drawing.Point(28, 170)
        lbl_arch_info.Size      = Drawing.Size(580, 16)
        self.Controls.Add(lbl_arch_info)

        self._src  = src
        self._arch = arch

        self.Controls.Add(_make_btn("Open Selected", 340, 230, 140, 34,
                                    primary=True, handler=self._open))
        self.Controls.Add(_make_btn("Cancel", 488, 230, 90, 34,
                                    handler=lambda s, e: self.Close()))

    def _open(self, s, e):
        self.open_path = self._src if self._rb_src.Checked else self._arch
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()


# ────────────────────────────────────────────────────────────────────────────
#  ZIP extract dialog  (first-time extraction location chooser)
# ────────────────────────────────────────────────────────────────────────────

class ZipExtractDialog(WinForms.Form):
    """
    Shown on first open of a ZIP-archived .wbpj.
    User chooses to extract beside the ZIP or to a custom location.
    """

    def __init__(self, zip_path, label):
        self.chosen_dest   = ""   # chosen extraction directory
        self._zip_path     = zip_path
        self._label        = label

        project_name    = os.path.splitext(os.path.basename(zip_path))[0]
        zip_dir         = os.path.dirname(zip_path)
        self._beside    = os.path.join(zip_dir, project_name)
        self._custom    = ""

        self.Text          = u"Extract Archive: {0}".format(label)
        self.Width         = 660
        self.Height        = 310
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox   = False
        self.MaximizeBox   = False
        self.BackColor     = Drawing.Color.White
        self.Font          = _FONT_NORMAL

        lbl_hdr = WinForms.Label()
        lbl_hdr.Text = ("This file is stored as a ZIP archive. "
                        "Choose where to extract it before opening.")
        lbl_hdr.Location = Drawing.Point(16, 14)
        lbl_hdr.Size     = Drawing.Size(614, 30)
        self.Controls.Add(lbl_hdr)

        # Option A — beside ZIP
        self._rb_beside = WinForms.RadioButton()
        self._rb_beside.Text     = "Extract beside ZIP  (inside repository folder)"
        self._rb_beside.Location = Drawing.Point(16, 54)
        self._rb_beside.Size     = Drawing.Size(500, 20)
        self._rb_beside.Checked  = True
        self._rb_beside.CheckedChanged += self._on_rb_changed
        self.Controls.Add(self._rb_beside)

        self._lbl_beside = WinForms.Label()
        self._lbl_beside.Text      = "   " + self._beside
        self._lbl_beside.Font      = _FONT_SMALL
        self._lbl_beside.ForeColor = Drawing.Color.Gray
        self._lbl_beside.Location  = Drawing.Point(28, 76)
        self._lbl_beside.Size      = Drawing.Size(610, 16)
        self.Controls.Add(self._lbl_beside)

        # Option B — custom location
        self._rb_custom = WinForms.RadioButton()
        self._rb_custom.Text     = "Extract to another location"
        self._rb_custom.Location = Drawing.Point(16, 104)
        self._rb_custom.Size     = Drawing.Size(300, 20)
        self._rb_custom.CheckedChanged += self._on_rb_changed
        self.Controls.Add(self._rb_custom)

        self._tb_custom = WinForms.TextBox()
        self._tb_custom.Location = Drawing.Point(28, 128)
        self._tb_custom.Size     = Drawing.Size(480, 24)
        self._tb_custom.Enabled  = False
        self.Controls.Add(self._tb_custom)

        self._btn_browse = _make_btn("Browse...", 516, 127, 90, 26,
                                      handler=self._browse)
        self._btn_browse.Enabled = False
        self.Controls.Add(self._btn_browse)

        self._lbl_dest = WinForms.Label()
        self._lbl_dest.Text      = ""
        self._lbl_dest.Font      = _FONT_SMALL
        self._lbl_dest.ForeColor = Drawing.Color.Gray
        self._lbl_dest.Location  = Drawing.Point(28, 156)
        self._lbl_dest.Size      = Drawing.Size(610, 16)
        self.Controls.Add(self._lbl_dest)

        # Size warning
        try:
            zip_size = os.path.getsize(zip_path)
            if zip_size > SIZE_WARN_BYTES:
                lbl_warn = WinForms.Label()
                lbl_warn.Text = (u"\u26A0 This archive is {0} — extraction "
                                 u"may take several minutes.".format(
                                     repo.format_size(zip_size)))
                lbl_warn.Font      = _FONT_SMALL
                lbl_warn.ForeColor = _CLR_ARCHIVED_OLD
                lbl_warn.Location  = Drawing.Point(16, 180)
                lbl_warn.Size      = Drawing.Size(614, 16)
                self.Controls.Add(lbl_warn)
        except Exception:
            pass

        self.Controls.Add(_make_btn("Extract and Open", 340, 238, 160, 34,
                                    primary=True, handler=self._extract))
        self.Controls.Add(_make_btn("Cancel", 508, 238, 90, 34,
                                    handler=lambda s, e: self.Close()))

    def _on_rb_changed(self, s, e):
        custom = self._rb_custom.Checked
        self._tb_custom.Enabled  = custom
        self._btn_browse.Enabled = custom
        self._lbl_dest.Text = ""

    def _browse(self, s, e):
        dlg = WinForms.FolderBrowserDialog()
        dlg.Description = "Choose extraction folder"
        if dlg.ShowDialog() == WinForms.DialogResult.OK:
            project_name    = os.path.splitext(
                os.path.basename(self._zip_path))[0]
            self._custom    = os.path.join(dlg.SelectedPath, project_name)
            self._tb_custom.Text = dlg.SelectedPath
            self._lbl_dest.Text = u"Will extract to: " + self._custom

    def _extract(self, s, e):
        if self._rb_beside.Checked:
            self.chosen_dest = self._beside
        else:
            if not self._custom:
                WinForms.MessageBox.Show(
                    "Please browse to choose an extraction folder.",
                    "No Folder Selected")
                return
            self.chosen_dest = self._custom
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()


# ────────────────────────────────────────────────────────────────────────────
#  ZIP open dialog  (subsequent opens of already-extracted ZIP)
# ────────────────────────────────────────────────────────────────────────────

class ZipOpenDialog(WinForms.Form):
    """
    Shown when a ZIP-archived .wbpj has already been extracted.
    User chooses: open existing / re-extract / different location.
    """

    OPEN_EXISTING  = "existing"
    RE_EXTRACT     = "re_extract"
    OTHER_LOCATION = "other"

    def __init__(self, zip_path, extract_path, label):
        self.action       = ""
        self._zip_path    = zip_path
        self._extract     = extract_path
        self._label       = label

        self.Text          = u"Open: {0}".format(label)
        self.Width         = 660
        self.Height        = 280
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox   = False
        self.MaximizeBox   = False
        self.BackColor     = Drawing.Color.White
        self.Font          = _FONT_NORMAL

        lbl_hdr = WinForms.Label()
        lbl_hdr.Text = ("This archive was previously extracted. "
                        "What would you like to do?")
        lbl_hdr.Location = Drawing.Point(16, 14)
        lbl_hdr.Size     = Drawing.Size(614, 20)
        self.Controls.Add(lbl_hdr)

        # Option 1 — open existing
        self._rb_open = WinForms.RadioButton()
        self._rb_open.Text     = "Open existing extracted copy"
        self._rb_open.Location = Drawing.Point(16, 46)
        self._rb_open.Size     = Drawing.Size(400, 20)
        self._rb_open.Checked  = True
        self.Controls.Add(self._rb_open)

        lbl_ext = WinForms.Label()
        lbl_ext.Text      = "   " + extract_path
        lbl_ext.Font      = _FONT_SMALL
        lbl_ext.ForeColor = Drawing.Color.Gray
        lbl_ext.Location  = Drawing.Point(28, 68)
        lbl_ext.Size      = Drawing.Size(610, 16)
        self.Controls.Add(lbl_ext)

        sep1 = WinForms.Label()
        sep1.BorderStyle = WinForms.BorderStyle.Fixed3D
        sep1.Location    = Drawing.Point(16, 92)
        sep1.Size        = Drawing.Size(614, 2)
        self.Controls.Add(sep1)

        # Option 2 — re-extract
        self._rb_re = WinForms.RadioButton()
        self._rb_re.Text     = (u"Re-extract from ZIP  "
                                u"(overwrites existing — use if ZIP was updated)")
        self._rb_re.Location = Drawing.Point(16, 102)
        self._rb_re.Size     = Drawing.Size(580, 20)
        self.Controls.Add(self._rb_re)

        lbl_zip = WinForms.Label()
        lbl_zip.Text      = "   " + zip_path
        lbl_zip.Font      = _FONT_SMALL
        lbl_zip.ForeColor = Drawing.Color.Gray
        lbl_zip.Location  = Drawing.Point(28, 124)
        lbl_zip.Size      = Drawing.Size(610, 16)
        self.Controls.Add(lbl_zip)

        sep2 = WinForms.Label()
        sep2.BorderStyle = WinForms.BorderStyle.Fixed3D
        sep2.Location    = Drawing.Point(16, 148)
        sep2.Size        = Drawing.Size(614, 2)
        self.Controls.Add(sep2)

        # Option 3 — different location
        self._rb_other = WinForms.RadioButton()
        self._rb_other.Text     = "Extract to a different location"
        self._rb_other.Location = Drawing.Point(16, 158)
        self._rb_other.Size     = Drawing.Size(400, 20)
        self.Controls.Add(self._rb_other)

        self.Controls.Add(_make_btn("Open / Extract", 390, 212, 150, 34,
                                    primary=True, handler=self._ok))
        self.Controls.Add(_make_btn("Cancel", 548, 212, 90, 34,
                                    handler=lambda s, e: self.Close()))

    def _ok(self, s, e):
        if self._rb_open.Checked:
            self.action = self.OPEN_EXISTING
        elif self._rb_re.Checked:
            self.action = self.RE_EXTRACT
        else:
            self.action = self.OTHER_LOCATION
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()


# ────────────────────────────────────────────────────────────────────────────
#  Archive dialog
# ────────────────────────────────────────────────────────────────────────────

class ArchiveDialog(WinForms.Form):
    """Checklist dialog for selecting files to archive."""

    WBPJ_ZIP            = "zip"
    WBPJ_COPY_WITH_FILES = "copy_with_files"
    WBPJ_SKIP           = "skip"

    def __init__(self, candidates, open_project_path=None):
        self._candidates       = candidates
        self._open_proj        = open_project_path
        self._archived_results = []
        self._has_wbpj         = any(c["is_wbpj"] for c in candidates)

        self.Text          = u"Archive Repository Files"
        self.Width         = 900
        self.Height        = 560 if self._has_wbpj else 460
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox   = False
        self.MaximizeBox   = True
        self.BackColor     = Drawing.Color.White
        self.Font          = _FONT_NORMAL

        self._build_ui()
        self._populate_list()

    def _build_ui(self):
        y = 12

        lbl_hdr = WinForms.Label()
        lbl_hdr.Text = ("Select files to archive into the project repository. "
                        "Files already archived show their current status.")
        lbl_hdr.Location = Drawing.Point(16, y)
        lbl_hdr.Size     = Drawing.Size(860, 18)
        lbl_hdr.Font     = _FONT_SMALL
        lbl_hdr.ForeColor = Drawing.Color.Gray
        self.Controls.Add(lbl_hdr)
        y += 28

        self.Controls.Add(_make_btn("Check All",   16, y, 100, 26,
                                    handler=self._check_all))
        self.Controls.Add(_make_btn("Uncheck All", 124, y, 110, 26,
                                    handler=self._uncheck_all))
        y += 36

        lv_height = 220
        self._lv = WinForms.ListView()
        self._lv.View         = WinForms.View.Details
        self._lv.CheckBoxes    = True
        self._lv.FullRowSelect = True
        self._lv.GridLines     = True
        self._lv.Location      = Drawing.Point(16, y)
        self._lv.Size          = Drawing.Size(858, lv_height)
        self._lv.Font          = _FONT_NORMAL
        self._lv.HeaderStyle   = WinForms.ColumnHeaderStyle.Nonclickable

        for name, w in [("Section", 150), ("File Name", 220),
                        ("Source Location", 240), ("Size", 80),
                        ("Archive Status", 150)]:
            self._lv.Columns.Add(name, w)

        self.Controls.Add(self._lv)
        y += lv_height + 10

        if self._has_wbpj:
            self._wbpj_panel = self._build_wbpj_panel(y)
            self.Controls.Add(self._wbpj_panel)
            y += self._wbpj_panel.Height + 10
        else:
            self._wbpj_panel = None

        btn_y = y + 4
        self.Controls.Add(_make_btn(u"\U0001F4E6  Archive Checked Files",
                                    16, btn_y, 210, 36,
                                    primary=True, handler=self._on_archive))
        self.Controls.Add(_make_btn("Cancel", 234, btn_y, 100, 36,
                                    handler=lambda s, e: self._cancel()))
        self.Height = btn_y + 80

    def _build_wbpj_panel(self, top_y):
        panel = WinForms.GroupBox()
        panel.Text     = "Workbench Project (.wbpj) Archive Method"
        panel.Location = Drawing.Point(16, top_y)
        panel.Size     = Drawing.Size(858, 96)
        panel.Font     = _FONT_NORMAL

        self._rb_zip = WinForms.RadioButton()
        self._rb_zip.Text    = u"Compress to ZIP  (recommended \u2014 works with any project)"
        self._rb_zip.Location = Drawing.Point(12, 20)
        self._rb_zip.Size    = Drawing.Size(560, 20)
        self._rb_zip.Checked = True
        panel.Controls.Add(self._rb_zip)

        lbl_rec = WinForms.Label()
        lbl_rec.Text      = u"\u2714 Recommended"
        lbl_rec.ForeColor = _CLR_GREEN_DIM
        lbl_rec.Font      = _FONT_BOLD
        lbl_rec.Location  = Drawing.Point(580, 22)
        lbl_rec.AutoSize  = True
        panel.Controls.Add(lbl_rec)

        self._chk_results = WinForms.CheckBox()
        self._chk_results.Text     = "Include result files (.rst, .db, etc.)"
        self._chk_results.Location = Drawing.Point(34, 44)
        self._chk_results.Size     = Drawing.Size(280, 20)
        self._chk_results.Checked  = False
        panel.Controls.Add(self._chk_results)

        self._rb_copy = WinForms.RadioButton()
        self._rb_copy.Text     = "Copy .wbpj + _files folder  (no compression, largest)"
        self._rb_copy.Location = Drawing.Point(12, 70)
        self._rb_copy.Size     = Drawing.Size(500, 20)
        panel.Controls.Add(self._rb_copy)

        return panel

    def _populate_list(self):
        self._lv.Items.Clear()
        for c in self._candidates:
            item   = WinForms.ListViewItem(c["section_label"])
            status = c["archive_status"]

            if status == repo.ARCH_STATUS_MISSING:
                item.ForeColor = _CLR_MISSING
            elif status == repo.ARCH_STATUS_OK:
                item.ForeColor = _CLR_ARCHIVED_OK
            elif status == repo.ARCH_STATUS_OUTDATED:
                item.ForeColor = _CLR_ARCHIVED_OLD

            item.SubItems.Add(c["label"])
            item.SubItems.Add(c["source_path"])

            if c["is_wbpj"]:
                sz_bytes = c["wbpj_total_size_bytes"]
                sz_str   = c["wbpj_total_size_str"]
            else:
                sz_bytes = c["source_size_bytes"]
                sz_str   = c["source_size_str"]

            if sz_bytes > SIZE_WARN_BYTES:
                sz_str += u"  \u26A0"

            item.SubItems.Add(sz_str)
            item.SubItems.Add(status)
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
        if self._rb_copy.Checked:
            return self.WBPJ_COPY_WITH_FILES
        return self.WBPJ_SKIP

    def _cancel(self):
        self.DialogResult = WinForms.DialogResult.Cancel
        self.Close()

    def _on_archive(self, s, e):
        checked = [self._candidates[i]
                   for i in range(self._lv.Items.Count)
                   if self._lv.Items[i].Checked]

        if not checked:
            WinForms.MessageBox.Show(
                "No files are checked. Select at least one file to archive.",
                "Nothing Selected")
            return

        wbpj_method = self._get_wbpj_method()

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

        successes = []
        failures  = []

        for c in checked:
            section  = c["section"]
            index    = c["index"]
            src      = c["source_path"]
            dest_dir = repo.get_section_archive_dir(section)
            label    = c["label"]

            try:
                if c["is_wbpj"]:
                    if wbpj_method == self.WBPJ_ZIP:
                        prog = ArchiveProgressDialog(
                            u"Compressing: {0}".format(label))
                        prog.Show()
                        WinForms.Application.DoEvents()

                        def _zip_cb(fname):
                            prog.set_status(u"Adding: {0}".format(fname))

                        dest_path = repo.zip_wbpj_with_files(
                            src, dest_dir,
                            include_results=self._chk_results.Checked,
                            progress_callback=_zip_cb)
                        prog.finish_success()
                        method = "zip"

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
                        continue

                else:
                    prog = ArchiveProgressDialog(
                        u"Copying: {0}  ({1})".format(
                            label,
                            repo.format_size(c.get("source_size_bytes", 0))))
                    prog.Show()
                    prog.set_status(u"Copying to archive folder...")
                    WinForms.Application.DoEvents()
                    dest_path = repo.archive_regular_file(src, dest_dir)
                    prog.finish_success()
                    method = "copy"

                repo.update_archive_record(section, index, dest_path, method)
                successes.append(label)
                _log("Archived: {0} -> {1}".format(label, dest_path))

            except Exception as exc:
                failures.append("{0}: {1}".format(label, str(exc)))
                _log("Archive failed [{0}]: {1}".format(label, str(exc)))

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
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()


# ────────────────────────────────────────────────────────────────────────────
#  Project-info panel
# ────────────────────────────────────────────────────────────────────────────

class ProjectInfoPanel(WinForms.Panel):
    def __init__(self, form_ref):
        self._form          = form_ref
        self._expanded      = True
        self._suppress_evt  = False
        self.BackColor      = Drawing.Color.FromArgb(245, 248, 252)
        self.BorderStyle    = WinForms.BorderStyle.FixedSingle
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        lbl = WinForms.Label()
        lbl.Text = "Project Information"
        lbl.Font = _FONT_BOLD
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
            lbl2.Text = caption + ":"
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
        lbl_s.Text = "Status:"
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
        lbl_r.Text = "Revision:"
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
        if self._suppress_evt:
            return
        try:
            selected = str(self._cb_status.SelectedItem or "")
            if selected != "Archived":
                return
            self._save(None, None)
            res = WinForms.MessageBox.Show(
                u"You have set this project to \u2018Archived\u2019 status.\n\n"
                u"Would you like to copy reference files into the project "
                u"repository archive folders now?",
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
                                    110, toolbar_h, handler=self._refresh_all))
        x += 118
        self.Controls.Add(_make_btn(u"\u25B6  Open", x, toolbar_y,
                                    100, toolbar_h, handler=self._on_open))
        x += 108
        self.Controls.Add(_make_btn(u"\u2716  Remove", x, toolbar_y,
                                    110, toolbar_h, handler=self._on_remove))
        x += 118
        self.Controls.Add(_make_btn(u"\u270E  Notes", x, toolbar_y,
                                    100, toolbar_h, handler=self._on_notes))
        x += 108
        self.Controls.Add(_make_btn(u"\u2764  Health Check", x, toolbar_y,
                                    140, toolbar_h,
                                    handler=self._on_health_check))
        x += 148
        self.Controls.Add(_make_btn(u"\U0001F4E6  Archive Files", x, toolbar_y,
                                    150, toolbar_h, handler=self._on_archive))

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
            bg   = _CLR_ANSYS_BLUE if is_active else Drawing.Color.FromArgb(240, 240, 240)
            fg   = Drawing.Color.White if is_active else Drawing.Color.FromArgb(100, 100, 100)
            font = _FONT_BOLD if is_active else _FONT_NORMAL
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
                u"Loaded \u2014 {0} file(s), {1} missing".format(total, missing))
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
                item.Font      = _FONT_BOLD
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
            missing  = (status == repo.ARCH_STATUS_MISSING)
            outdated = (status == repo.ARCH_STATUS_OUTDATED)

            menu = WinForms.ContextMenuStrip()

            item_open = menu.Items.Add(u"\u25B6  Open")
            item_open.Enabled = not (missing and not record.get("archive_path", ""))
            item_open.Click  += lambda s2, e2: self._on_open(None, None)

            item_notes = menu.Items.Add(u"\u270E  Edit Notes")
            item_notes.Click += lambda s2, e2: self._on_notes(None, None)

            menu.Items.Add(WinForms.ToolStripSeparator())

            item_relink = menu.Items.Add(u"\u27A1  Relink Missing File\u2026")
            item_relink.Enabled = missing
            _idx = idx
            _sec = sec
            item_relink.Click += lambda s2, e2: self._on_relink(_sec, _idx)

            item_rearch = menu.Items.Add(u"\u27F3  Re-archive (update copy)")
            item_rearch.Enabled = outdated
            item_rearch.Click  += lambda s2, e2: self._on_rearchive(_sec, _idx)

            menu.Items.Add(WinForms.ToolStripSeparator())

            item_remove = menu.Items.Add(u"\u2716  Remove from Repository")
            item_remove.Click += lambda s2, e2: self._on_remove(None, None)

            menu.Show(lv, Drawing.Point(e.X, e.Y))
        except Exception as exc:
            _log("Context menu error: " + str(exc))

    # ── Smart open  (context-aware) ───────────────────────────────────────

    def _on_open(self, sender, e):
        try:
            sel = self._selected_records()
            if not sel:
                WinForms.MessageBox.Show("Select a file first.", "Open")
                return
            idx, record = sel[0]
            self._open_record(self._cur_section, idx, record)
        except Exception as exc:
            _log("Open error: " + str(exc))
            WinForms.MessageBox.Show("Open failed:\n" + str(exc), "Error")

    def _open_record(self, section, index, record):
        """
        Context-aware open logic.

        1. Prune stale source_path / local_extract_path on this machine.
        2. Determine mode via repo.get_open_target().
        3. Route to appropriate dialog or direct open.
        """
        # Step 1 — prune stale paths (silent, updates manifest if needed)
        repo.prune_stale_fields(section, index)
        # Reload the record after potential pruning
        data    = repo.load_manifest()
        records = data["sections"].get(section, [])
        if index < 0 or index >= len(records):
            return
        record = records[index]

        target = repo.get_open_target(record)
        mode   = target["mode"]
        _log("Open mode: {0}  label={1}".format(mode, record.get("label", "")))

        if mode == "none":
            WinForms.MessageBox.Show(
                "No accessible file found.\n\n"
                "The source reference path does not exist on this machine\n"
                "and no archive copy is available.",
                "Cannot Open")
            return

        elif mode == "source":
            # No archive — open source directly
            _smart_open_file(target["source_path"])

        elif mode == "archive_direct":
            # Non-ZIP archive — offer choice if source also available
            if target["has_source"]:
                dlg = OpenChoiceDialog(record)
                if dlg.ShowDialog() == WinForms.DialogResult.OK and dlg.open_path:
                    _smart_open_file(dlg.open_path)
            else:
                # Only archive available — open it directly
                _smart_open_file(target["archive_path"])

        elif mode == "extract_first":
            # ZIP archive, not yet extracted on this machine
            self._extract_and_open(section, index, record,
                                   target["archive_path"])

        elif mode == "archive_zip":
            # ZIP archive, previously extracted
            dlg = ZipOpenDialog(
                target["archive_path"],
                target["extract_path"],
                record.get("label", ""))

            if dlg.ShowDialog() != WinForms.DialogResult.OK:
                return

            if dlg.action == ZipOpenDialog.OPEN_EXISTING:
                _smart_open_file(target["extract_path"])

            elif dlg.action == ZipOpenDialog.RE_EXTRACT:
                # Re-extract to same directory
                extract_dir = os.path.dirname(target["extract_path"])
                self._do_extract(section, index, target["archive_path"],
                                 extract_dir)

            elif dlg.action == ZipOpenDialog.OTHER_LOCATION:
                self._extract_and_open(section, index, record,
                                       target["archive_path"])

    def _extract_and_open(self, section, index, record, zip_path):
        """Show ZipExtractDialog, extract, open, save path, offer to set as source."""
        dlg = ZipExtractDialog(zip_path, record.get("label", ""))
        if dlg.ShowDialog() != WinForms.DialogResult.OK:
            return
        self._do_extract(section, index, zip_path, dlg.chosen_dest)

    def _do_extract(self, section, index, zip_path, dest_dir):
        """Extract the ZIP, open the .wbpj, save local_extract_path, offer source update."""
        prog = ArchiveProgressDialog(
            u"Extracting: {0}".format(os.path.basename(zip_path)))
        prog.Show()
        WinForms.Application.DoEvents()

        try:
            def _cb(fname):
                prog.set_status(u"Extracting: {0}".format(fname))

            extracted_wbpj = repo.zip_extract_to(zip_path, dest_dir,
                                                  progress_callback=_cb)
            prog.finish_success()
        except Exception as exc:
            prog.finish_success()
            _log("Extraction error: " + str(exc))
            WinForms.MessageBox.Show(
                "Extraction failed:\n" + str(exc), "Extract Error")
            return

        # Save local_extract_path
        if extracted_wbpj and extracted_wbpj.lower().endswith(".wbpj"):
            repo.update_local_extract(section, index, extracted_wbpj)
            _log("Saved local_extract_path: " + extracted_wbpj)

            # Open it
            _smart_open_file(extracted_wbpj)

            # Offer to designate as working source
            res = WinForms.MessageBox.Show(
                u"The archive was extracted to:\n{0}\n\n"
                u"Would you like to set this extracted copy as your working "
                u"source for future re-archiving?\n\n"
                u"Yes  \u2014 Future re-archives will compress this copy.\n"
                u"No   \u2014  Keep original source reference (if it exists).".format(
                    extracted_wbpj),
                u"Set as Working Source?",
                WinForms.MessageBoxButtons.YesNo,
                WinForms.MessageBoxIcon.Question)

            if res == WinForms.DialogResult.Yes:
                repo.update_source_path(section, index, extracted_wbpj)
                _log("source_path updated to extracted copy: " + extracted_wbpj)

            self._refresh_all(None, None)
        else:
            prog.finish_success()
            # No .wbpj found — just open the dest_dir in Explorer
            try:
                os.startfile(dest_dir)
            except Exception:
                WinForms.MessageBox.Show(
                    u"Extraction complete but no .wbpj found at root.\n"
                    u"Extracted to: " + dest_dir,
                    "Extraction Complete")

    def _on_double_click(self, sender, e):
        self._on_open(sender, e)

    # ── Archive launcher ──────────────────────────────────────────────────

    def launch_archive_dialog(self):
        try:
            open_proj  = _get_open_project_path()
            candidates = repo.get_archive_candidates(open_proj)
            if not candidates:
                WinForms.MessageBox.Show(
                    "No eligible files found to archive.\n\n"
                    "Add files to the repository first.\n\n"
                    "Note: the currently open project is automatically excluded.",
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

    # ── Re-archive single outdated file ───────────────────────────────────

    def _on_rearchive(self, section, index):
        try:
            records = self._section_data.get(section, [])
            if index < 0 or index >= len(records):
                return
            record = records[index]
            src    = record.get("source_path", "")
            label  = record.get("label", "")
            method = record.get("archive_method", "copy")

            if not src or not os.path.exists(src):
                WinForms.MessageBox.Show(
                    "Source file not found. Use Relink to locate it first.",
                    "Re-archive Error")
                return

            dest_dir = repo.get_section_archive_dir(section)

            if method == "zip":
                prog = ArchiveProgressDialog(
                    u"Re-compressing: {0}".format(label))
                prog.Show()
                WinForms.Application.DoEvents()

                def _cb(fname):
                    prog.set_status(u"Adding: {0}".format(fname))

                dest_path = repo.zip_wbpj_with_files(
                    src, dest_dir, progress_callback=_cb)
                prog.finish_success()
                repo.update_archive_record(section, index, dest_path, "zip")

            elif method == "copy_with_files":
                prog = ArchiveProgressDialog(
                    u"Re-copying: {0}".format(label))
                prog.Show()
                prog.set_status(u"Copying .wbpj + _files folder...")
                WinForms.Application.DoEvents()
                dest_path = repo.copy_wbpj_with_files(src, dest_dir)
                prog.finish_success()
                repo.update_archive_record(section, index, dest_path,
                                           "copy_with_files")
            else:
                prog = ArchiveProgressDialog(u"Re-copying: {0}".format(label))
                prog.Show()
                prog.set_status(u"Copying file...")
                WinForms.Application.DoEvents()
                dest_path = repo.archive_regular_file(src, dest_dir)
                prog.finish_success()
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
            repo.relink_file_record(section, index, dlg.FileName)
            self._refresh_all(None, None)
            self._set_status(u"Relinked: {0}".format(
                os.path.basename(dlg.FileName)))
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
                repo.update_file_notes(self._cur_section, idx, dlg.result_notes)
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
            return ["Unfulfilled", "Repository is empty - add files to get started"]
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
