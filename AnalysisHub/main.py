# -*- coding: utf-8 -*-
"""
main.py  v1.0  -  AnalysisHub ACT Extension
============================================
IronPython 2.7 / ANSYS Workbench 2024 R2+

v1.0 changes (Group 1 + Group 2)
----------------------------------
* in_user_files: files inside user_files tree stored with relative path,
  shown as "Local ✔" -- no archiving needed, path survives project transfer.
* local_extract_path stored relative to repo root when inside repo.
* Option B: .wbpz records can link a source .wbpj for change detection.
  Status shows "⚠ Source Project Changed" if .wbpj is newer than .wbpz.
* Version stamp v1.0 in title bar and debug log.
* Help button in RepositoryForm toolbar + Workbench toolbar entry (XML).
  Opens AnalysisHub_Manual.pdf from <InstallDir>\Help\ folder.
* NotesDialog: filename in title bar, resizable, textarea anchors.
* Best-practice nudge when adding .wbpj to Supplemental WB Database tab.
* Status bar shows live file count on open.
* Right-click: Link Source Project / Clear Source Link for .wbpz records.
"""

import os
import sys
import datetime
import traceback
import shutil

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

LOG_PATH = r"C:\Temp\AnalysisHub_debug.log"

try:
    with open(LOG_PATH, "w") as _fh:
        _fh.write("=" * 80 + "\n")
        _fh.write("  AnalysisHub v1.0  -  {0}\n".format(
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        _fh.write("=" * 80 + "\n")
except Exception:
    pass


def _log(msg):
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a") as fh:
            fh.write("[{0}] MAIN >>> {1}\n".format(ts, msg))
        print("[{0}] {1}".format(ts, msg))
    except Exception:
        pass


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
        platform = (Ansys.Utilities.ApplicationConfiguration
                    .DefaultConfiguration.Platform)
        runwb2 = System.IO.Path.Combine(
            install_root, "Framework", "bin", platform, "runwb2.exe")
        if System.IO.File.Exists(runwb2):
            return runwb2
    except Exception:
        pass
    for c in [r"C:\Program Files\ANSYS Inc\v242\Framework\bin\Win64\RunWB2.exe",
              r"C:\Program Files\ANSYS Inc\v251\Framework\bin\Win64\RunWB2.exe"]:
        if os.path.exists(c):
            return c
    return None


def _smart_open_file(path):
    if not path or not os.path.exists(path):
        _log("Open failed - not found: " + str(path))
        return False
    ext = os.path.splitext(path)[1].lower()
    _log("Opening: {0}".format(path))
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


def open_help(task=None):
    """
    Open the AnalysisHub PDF manual from the extension's Help\ sub-folder.
    Called from:
      - The Help toolbar button inside RepositoryForm (WinForms handler).
      - The <onclick>open_help</onclick> entry in AnalysisHub.xml (ACT callback).
    """
    try:
        install_dir = ExtAPI.Extension.InstallDir
    except Exception:
        install_dir = os.path.dirname(os.path.abspath(__file__))

    help_file = System.IO.Path.Combine(install_dir, "Help", "AnalysisHub_Manual.pdf")
    _log("Opening help: " + help_file)

    if not System.IO.File.Exists(help_file):
        WinForms.MessageBox.Show(
            u"Help file not found:\n{0}\n\n"
            u"Please ensure AnalysisHub_Manual.pdf is present in the "
            u"Help\\ folder alongside the extension files.".format(help_file),
            u"AnalysisHub \u2014 Help",
            WinForms.MessageBoxButtons.OK,
            WinForms.MessageBoxIcon.Information)
        return

    try:
        System.Diagnostics.Process.Start(help_file)
    except Exception as exc:
        _log("open_help error: " + str(exc))
        WinForms.MessageBox.Show(
            u"Could not open help file:\n" + help_file,
            u"AnalysisHub \u2014 Help")


_CLR_ANSYS_BLUE  = Drawing.Color.FromArgb(0,   120, 212)
_CLR_READY       = Drawing.Color.FromArgb(16,  124,  16)
_CLR_MISSING     = Drawing.Color.FromArgb(209,  52,  56)
_CLR_ARCHIVED_OK = Drawing.Color.FromArgb(0,   102, 204)
_CLR_ARCHIVED_OLD= Drawing.Color.FromArgb(200, 100,   0)
_CLR_UNARCHIVED  = Drawing.Color.FromArgb(128,   0, 128)
_CLR_GREEN_DIM   = Drawing.Color.FromArgb(0,   128,   0)
_CLR_LOCAL       = Drawing.Color.FromArgb(0,   128,   0)   # green — Local ✔
_CLR_SRC_CHANGED = Drawing.Color.FromArgb(180,  80,   0)   # amber — ⚠ Source Changed

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

SIZE_WARN_BYTES = 1024 * 1024 * 1024


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


class NotesDialog(WinForms.Form):
    """
    Resizable notes editor.
    * Title bar shows "Notes — <filename>" when file_label is supplied.
    * Text area anchors to all four edges so it stretches with the window.
    * OK / Cancel stay pinned bottom-right at all sizes.
    """
    _BTN_W   = 90
    _BTN_H   = 32
    _BTN_GAP = 8
    _BTN_PAD = 12

    def __init__(self, current_notes="", file_label=""):
        self.result_notes = current_notes
        self.Text = (u"Notes \u2014 {0}".format(file_label)
                     if file_label else "File Notes")
        self.Width         = 500
        self.Height        = 300
        self.MinimumSize   = Drawing.Size(380, 220)
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox   = False
        self.MaximizeBox   = True
        self.BackColor     = Drawing.Color.White
        self.Font          = _FONT_NORMAL

        lbl = WinForms.Label()
        lbl.Text     = "Notes / Description:"
        lbl.Location = Drawing.Point(12, 12)
        lbl.AutoSize = True
        lbl.Anchor   = WinForms.AnchorStyles.Top | WinForms.AnchorStyles.Left
        self.Controls.Add(lbl)

        self._tb = WinForms.TextBox()
        self._tb.Multiline  = True
        self._tb.ScrollBars = WinForms.ScrollBars.Vertical
        self._tb.Location   = Drawing.Point(12, 36)
        self._tb.Text       = current_notes
        self._tb.Anchor     = (WinForms.AnchorStyles.Top    |
                               WinForms.AnchorStyles.Bottom |
                               WinForms.AnchorStyles.Left   |
                               WinForms.AnchorStyles.Right)
        self.Controls.Add(self._tb)

        self._btn_ok = _make_btn("OK", 0, 0, self._BTN_W, self._BTN_H,
                                 primary=True, handler=self._ok)
        self._btn_ok.Anchor = (WinForms.AnchorStyles.Bottom |
                               WinForms.AnchorStyles.Right)
        self.Controls.Add(self._btn_ok)

        self._btn_cn = _make_btn("Cancel", 0, 0, self._BTN_W, self._BTN_H,
                                 handler=self._cancel)
        self._btn_cn.Anchor = (WinForms.AnchorStyles.Bottom |
                               WinForms.AnchorStyles.Right)
        self.Controls.Add(self._btn_cn)

        self._layout()
        self.Resize += lambda s, e: self._layout()

    def _layout(self):
        try:
            cw = self.ClientSize.Width
            ch = self.ClientSize.Height
            p  = self._BTN_PAD
            btn_y    = ch - self._BTN_H - p
            cancel_x = cw - self._BTN_W - p
            ok_x     = cancel_x - self._BTN_W - self._BTN_GAP
            self._btn_ok.Location = Drawing.Point(ok_x,     btn_y)
            self._btn_cn.Location = Drawing.Point(cancel_x, btn_y)
            self._tb.Size = Drawing.Size(max(100, cw - 24),
                                         max(60,  btn_y - 44))
        except Exception:
            pass

    def _ok(self, s, e):
        self.result_notes = self._tb.Text
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()

    def _cancel(self, s, e):
        self.DialogResult = WinForms.DialogResult.Cancel
        self.Close()


class RevisionDialog(WinForms.Form):
    def __init__(self, current_rev=""):
        self.result_rev = self.result_note = ""
        self.Text          = "Add Revision Entry"
        self.Width         = 460
        self.Height        = 240
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox = self.MaximizeBox = False
        self.BackColor   = Drawing.Color.White
        self.Font        = _FONT_NORMAL
        lbl_rev = WinForms.Label()
        lbl_rev.Text = "Revision label:"
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


class ArchiveProgressDialog(WinForms.Form):
    """Determinate progress dialog parented to RepositoryForm."""

    def __init__(self, label_text, owner=None):
        self._success = False
        self.Text          = "Working..."
        self.Width         = 540
        self.Height        = 170
        self.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
        self.MinimizeBox = self.MaximizeBox = self.ControlBox = False
        self.BackColor   = Drawing.Color.White
        self.Font        = _FONT_NORMAL
        if owner is not None:
            self.StartPosition = WinForms.FormStartPosition.CenterParent
            self.Owner = owner
        else:
            self.StartPosition = WinForms.FormStartPosition.CenterScreen

        lbl = WinForms.Label()
        lbl.Text = label_text
        lbl.Location = Drawing.Point(16, 14)
        lbl.Size     = Drawing.Size(500, 20)
        lbl.Font     = _FONT_BOLD
        self.Controls.Add(lbl)

        self._lbl_file = WinForms.Label()
        self._lbl_file.ForeColor = Drawing.Color.FromArgb(60, 60, 60)
        self._lbl_file.Location  = Drawing.Point(16, 40)
        self._lbl_file.Size      = Drawing.Size(500, 18)
        self.Controls.Add(self._lbl_file)

        self._lbl_count = WinForms.Label()
        self._lbl_count.Font      = _FONT_SMALL
        self._lbl_count.ForeColor = Drawing.Color.Gray
        self._lbl_count.Location  = Drawing.Point(16, 60)
        self._lbl_count.Size      = Drawing.Size(500, 16)
        self.Controls.Add(self._lbl_count)

        self._bar = WinForms.ProgressBar()
        self._bar.Minimum  = 0
        self._bar.Maximum  = 100
        self._bar.Value    = 0
        self._bar.Style    = WinForms.ProgressBarStyle.Continuous
        self._bar.Location = Drawing.Point(16, 84)
        self._bar.Size     = Drawing.Size(500, 22)
        self.Controls.Add(self._bar)

        self._lbl_pct = WinForms.Label()
        self._lbl_pct.Text      = "0%"
        self._lbl_pct.Font      = _FONT_SMALL
        self._lbl_pct.ForeColor = Drawing.Color.Gray
        self._lbl_pct.Location  = Drawing.Point(16, 110)
        self._lbl_pct.AutoSize  = True
        self.Controls.Add(self._lbl_pct)

    def set_progress(self, current, total, filename=""):
        try:
            pct = int(100.0 * current / total) if total > 0 else 0
            self._bar.Value      = min(pct, 100)
            self._lbl_pct.Text   = "{0}%".format(pct)
            self._lbl_count.Text = "{0} / {1} files".format(current, total)
            if filename:
                disp = filename if len(filename) <= 55 else "..." + filename[-52:]
                self._lbl_file.Text = disp
            WinForms.Application.DoEvents()
        except Exception:
            pass

    def set_status(self, msg):
        try:
            self._lbl_file.Text = msg
            WinForms.Application.DoEvents()
        except Exception:
            pass

    def finish_success(self):
        self._success = True
        try:
            self._bar.Value    = 100
            self._lbl_pct.Text = "100%"
            self._lbl_file.Text = u"\u2714 Complete."
            WinForms.Application.DoEvents()
            System.Threading.Thread.Sleep(300)
            self.DialogResult = WinForms.DialogResult.OK
            self.Close()
        except Exception:
            pass

    @property
    def succeeded(self):
        return self._success


# ────────────────────────────────────────────────────────────────────────────
#  Health-check dialog  (with orphan section)
# ────────────────────────────────────────────────────────────────────────────

class HealthCheckDialog(WinForms.Form):
    def __init__(self, health, owner_form=None):
        self._health     = health
        self._owner_form = owner_form
        self.Text          = "Repository Health Check"
        self.Width         = 780
        self.Height        = 620
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
        orphans  = health.get("orphaned", [])
        issues   = missing + arch_old + len(orphans)
        colour   = _CLR_MISSING if issues > 0 else _CLR_READY
        icon     = u"\u2718 ISSUES FOUND" if issues > 0 else u"\u2714 ALL OK"

        lbl_icon = WinForms.Label()
        lbl_icon.Text      = icon
        lbl_icon.Font      = Drawing.Font("Segoe UI", 13, Drawing.FontStyle.Bold)
        lbl_icon.ForeColor = colour
        lbl_icon.Location  = Drawing.Point(16, 14)
        lbl_icon.AutoSize  = True
        self.Controls.Add(lbl_icon)

        lbl_sum = WinForms.Label()
        lbl_sum.Text = ("Total: {0}   Ready: {1}   Missing: {2}   "
                        "Archived OK: {3}   Outdated: {4}   "
                        "Orphaned: {5}".format(
                            total, ready, missing, arch_ok,
                            arch_old, len(orphans)))
        lbl_sum.Location = Drawing.Point(16, 46)
        lbl_sum.AutoSize = True
        self.Controls.Add(lbl_sum)

        y = 72

        # Missing files section
        lbl_ms = WinForms.Label()
        lbl_ms.Text = u"Missing Source Files  \u2014  select a row and click Relink:"
        lbl_ms.Font = _FONT_BOLD
        lbl_ms.Location = Drawing.Point(16, y)
        lbl_ms.AutoSize = True
        self.Controls.Add(lbl_ms)
        y += 22

        self._lv_missing = WinForms.ListView()
        self._lv_missing.View         = WinForms.View.Details
        self._lv_missing.FullRowSelect = True
        self._lv_missing.GridLines     = True
        self._lv_missing.Location      = Drawing.Point(16, y)
        self._lv_missing.Size          = Drawing.Size(730, 130)
        self._lv_missing.Font          = _FONT_NORMAL
        self._lv_missing.Columns.Add("Section",   160)
        self._lv_missing.Columns.Add("File Name", 200)
        self._lv_missing.Columns.Add("Path",      350)

        if not health["missing_list"]:
            item = self._lv_missing.Items.Add(u"\u2014")
            item.SubItems.Add("No missing source files.")
            item.SubItems.Add("")
        else:
            for m in health["missing_list"]:
                item = self._lv_missing.Items.Add(m["section"])
                item.SubItems.Add(m["label"])
                item.SubItems.Add(m["path"])
                item.ForeColor = _CLR_MISSING

        self.Controls.Add(self._lv_missing)
        y += 134

        self._btn_relink = _make_btn(u"\u27A1  Relink Selected\u2026",
                                      16, y, 160, 28,
                                      handler=self._on_relink)
        self._btn_relink.Enabled = (missing > 0)
        self.Controls.Add(self._btn_relink)
        self._lv_missing.SelectedIndexChanged += self._on_missing_sel
        y += 38

        # Orphaned files section
        lbl_or = WinForms.Label()
        lbl_or.Text = u"Orphaned Archive Files  \u2014  in repository with no manifest entry:"
        lbl_or.Font = _FONT_BOLD
        lbl_or.Location = Drawing.Point(16, y)
        lbl_or.AutoSize = True
        self.Controls.Add(lbl_or)
        y += 22

        self._lv_orphans = WinForms.ListView()
        self._lv_orphans.View         = WinForms.View.Details
        self._lv_orphans.FullRowSelect = True
        self._lv_orphans.GridLines     = True
        self._lv_orphans.Location      = Drawing.Point(16, y)
        self._lv_orphans.Size          = Drawing.Size(730, 110)
        self._lv_orphans.Font          = _FONT_NORMAL
        self._lv_orphans.Columns.Add("Section",   160)
        self._lv_orphans.Columns.Add("Filename",  240)
        self._lv_orphans.Columns.Add("Full Path", 310)
        self._orphan_data = list(orphans)

        if not orphans:
            item = self._lv_orphans.Items.Add(u"\u2014")
            item.SubItems.Add("No orphaned archive files found.")
            item.SubItems.Add("")
        else:
            for oi, o in enumerate(orphans):
                item = self._lv_orphans.Items.Add(
                    repo.SECTION_LABELS.get(o["section"], o["section"]))
                item.SubItems.Add(o["filename"])
                item.SubItems.Add(o["path"])
                item.ForeColor = _CLR_ARCHIVED_OLD
                item.Tag = oi   # store original index for reliable lookup

        self.Controls.Add(self._lv_orphans)
        y += 114

        self._btn_del_orphan = _make_btn(u"\u2716  Delete Selected Orphan",
                                          16, y, 200, 28,
                                          handler=self._on_delete_orphan)
        self._btn_del_orphan.Enabled = bool(orphans)
        self.Controls.Add(self._btn_del_orphan)

        self._btn_import_orphan = _make_btn(
            u"\u2795  Add to Repository", 224, y, 180, 28,
            primary=True, handler=self._on_import_orphan)
        self._btn_import_orphan.Enabled = bool(orphans)
        self.Controls.Add(self._btn_import_orphan)

        lbl_hint = WinForms.Label()
        lbl_hint.Text = ("Select a row, then Delete to remove from disk "
                         "or Add to Repository to track it in the hub.")
        lbl_hint.Font      = _FONT_SMALL
        lbl_hint.ForeColor = Drawing.Color.Gray
        lbl_hint.Location  = Drawing.Point(412, y + 6)
        lbl_hint.Size      = Drawing.Size(340, 18)
        self.Controls.Add(lbl_hint)
        self._lv_orphans.SelectedIndexChanged += self._on_orphan_sel
        y += 38

        self.Controls.Add(_make_btn("Close", 640, y, 100, 32, primary=True,
                                    handler=lambda s, e: self.Close()))
        self.Height = y + 70

    def _on_missing_sel(self, s, e):
        self._btn_relink.Enabled = (self._lv_missing.SelectedItems.Count == 1)

    def _on_orphan_sel(self, s, e):
        has_sel = (self._lv_orphans.SelectedItems.Count == 1)
        self._btn_del_orphan.Enabled    = has_sel
        self._btn_import_orphan.Enabled = has_sel

    def _on_import_orphan(self, s, e):
        """Add the selected orphaned archive file to the manifest."""
        try:
            if self._lv_orphans.SelectedItems.Count != 1:
                return
            sel_item = self._lv_orphans.SelectedItems[0]
            try:
                idx = int(sel_item.Tag)
            except (TypeError, ValueError):
                idx = sel_item.Index
            if idx < 0 or idx >= len(self._orphan_data):
                return
            orphan = self._orphan_data[idx]

            # Let user choose which section to add it to
            sec_labels = [repo.SECTION_LABELS.get(s, s) for s in repo.ALL_SECTIONS]
            default_sec = orphan.get("section", repo.ALL_SECTIONS[0])
            default_idx = (repo.ALL_SECTIONS.index(default_sec)
                           if default_sec in repo.ALL_SECTIONS else 0)

            dlg_sec = WinForms.Form()
            dlg_sec.Text          = u"Add to Repository \u2014 Choose Section"
            dlg_sec.Width         = 420
            dlg_sec.Height        = 200
            dlg_sec.StartPosition = WinForms.FormStartPosition.CenterParent
            dlg_sec.MinimizeBox   = False
            dlg_sec.MaximizeBox   = False
            dlg_sec.BackColor     = Drawing.Color.White
            dlg_sec.Font          = _FONT_NORMAL

            lbl2 = WinForms.Label()
            lbl2.Text     = (u"Add \"{0}\" to which section?".format(
                orphan.get("filename", "")))
            lbl2.Location = Drawing.Point(16, 14)
            lbl2.Size     = Drawing.Size(380, 36)
            dlg_sec.Controls.Add(lbl2)

            cb = WinForms.ComboBox()
            cb.DropDownStyle = WinForms.ComboBoxStyle.DropDownList
            cb.Location      = Drawing.Point(16, 56)
            cb.Size          = Drawing.Size(375, 24)
            for lbl3 in sec_labels:
                cb.Items.Add(lbl3)
            cb.SelectedIndex = default_idx
            dlg_sec.Controls.Add(cb)

            chosen_section = [default_sec]

            def _ok_import(s2, e2):
                chosen_section[0] = repo.ALL_SECTIONS[cb.SelectedIndex]
                dlg_sec.DialogResult = WinForms.DialogResult.OK
                dlg_sec.Close()

            def _cancel_import(s2, e2):
                dlg_sec.DialogResult = WinForms.DialogResult.Cancel
                dlg_sec.Close()

            dlg_sec.Controls.Add(_make_btn("Add", 220, 110, 80, 30,
                                           primary=True, handler=_ok_import))
            dlg_sec.Controls.Add(_make_btn("Cancel", 308, 110, 80, 30,
                                           handler=_cancel_import))

            if dlg_sec.ShowDialog() != WinForms.DialogResult.OK:
                return

            # Patch the orphan's section before importing
            orphan_copy = dict(orphan)
            orphan_copy["section"] = chosen_section[0]
            record = repo.add_orphan_to_manifest(orphan_copy)
            if record is None:
                WinForms.MessageBox.Show("Import failed.", "Error")
                return

            # Update the list item visually
            sel_item.ForeColor = _CLR_ARCHIVED_OK
            sel_item.SubItems[0].Text = repo.SECTION_LABELS.get(
                chosen_section[0], chosen_section[0])
            sel_item.SubItems[1].Text += u"  \u2714 added"
            self._orphan_data.pop(idx)
            self._btn_del_orphan.Enabled    = False
            self._btn_import_orphan.Enabled = False
            _log("Orphan imported: {0} -> {1}".format(
                orphan.get("filename"), chosen_section[0]))
        except Exception as exc:
            _log("Import orphan error: " + str(exc))
            WinForms.MessageBox.Show("Import failed:\n" + str(exc), "Error")

    def _on_relink(self, s, e):
        try:
            if self._lv_missing.SelectedItems.Count != 1:
                return
            sel      = self._lv_missing.SelectedItems[0]
            label    = sel.SubItems[1].Text
            old_path = sel.SubItems[2].Text
            old_name = os.path.basename(old_path) if old_path else label
            sec, idx = self._find_record(label, old_path)
            if sec is None:
                WinForms.MessageBox.Show(
                    "Could not locate this record.\nClose and Refresh.",
                    "Relink Error")
                return
            dlg = WinForms.OpenFileDialog()
            dlg.Title    = u"Relink: locate \"{0}\"".format(old_name)
            dlg.Filter   = "All Files (*.*)|*.*"
            dlg.FileName = old_name
            if dlg.ShowDialog() != WinForms.DialogResult.OK:
                return
            repo.relink_file_record(sec, idx, dlg.FileName)
            sel.SubItems[2].Text = dlg.FileName
            sel.SubItems[1].Text = os.path.basename(dlg.FileName)
            sel.ForeColor        = _CLR_READY
        except Exception as exc:
            _log("Health relink error: " + str(exc))
            WinForms.MessageBox.Show("Relink failed:\n" + str(exc), "Error")

    def _on_delete_orphan(self, s, e):
        try:
            if self._lv_orphans.SelectedItems.Count != 1:
                return
            sel_item = self._lv_orphans.SelectedItems[0]
            # Use Tag (original list index) for reliable lookup,
            # not .Index which reflects display order
            try:
                idx = int(sel_item.Tag)
            except (TypeError, ValueError):
                idx = sel_item.Index
            if idx < 0 or idx >= len(self._orphan_data):
                return
            orphan = self._orphan_data[idx]
            path   = orphan["path"]
            if WinForms.MessageBox.Show(
                    u"Permanently delete from disk?\n\n{0}".format(path),
                    u"Confirm Delete",
                    WinForms.MessageBoxButtons.YesNo,
                    WinForms.MessageBoxIcon.Warning
                    ) != WinForms.DialogResult.Yes:
                return
            try:
                if orphan.get("is_dir"):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                sel_item.ForeColor = Drawing.Color.Gray
                sel_item.SubItems[1].Text += "  (deleted)"
                _log("Deleted orphan: " + path)
                self._orphan_data.pop(idx)
            except Exception as exc:
                WinForms.MessageBox.Show("Delete failed:\n" + str(exc), "Error")
        except Exception as exc:
            _log("Delete orphan error: " + str(exc))

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
#  Open choice dialog  (source vs archive for non-ZIP archived files)
# ────────────────────────────────────────────────────────────────────────────

class OpenChoiceDialog(WinForms.Form):
    def __init__(self, record):
        self.open_path = ""
        src   = record.get("source_path", "")
        arch  = repo._resolve_archive_path(record.get("archive_path", ""))
        label = record.get("label", "File")
        self.Text          = u"Open: {0}".format(label)
        self.Width         = 660
        self.Height        = 300
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox = self.MaximizeBox = False
        self.BackColor   = Drawing.Color.White
        self.Font        = _FONT_NORMAL

        lbl = WinForms.Label()
        lbl.Text = ("This file has both a source reference and an archive copy.\n"
                    "Which would you like to open?")
        lbl.Location = Drawing.Point(16, 14)
        lbl.Size     = Drawing.Size(620, 34)
        self.Controls.Add(lbl)

        self._rb_src = WinForms.RadioButton()
        self._rb_src.Text     = "Open source file  (current working version)"
        self._rb_src.Location = Drawing.Point(16, 58)
        self._rb_src.Size     = Drawing.Size(580, 20)
        self._rb_src.Checked  = True
        self.Controls.Add(self._rb_src)

        lbl_sp = WinForms.Label()
        lbl_sp.Text = "   " + src
        lbl_sp.Font = _FONT_SMALL
        lbl_sp.ForeColor = Drawing.Color.FromArgb(60, 60, 60)
        lbl_sp.Location  = Drawing.Point(28, 80)
        lbl_sp.Size      = Drawing.Size(610, 16)
        self.Controls.Add(lbl_sp)

        try:
            src_info = u"   Modified: {0}   Size: {1:.2f} MB".format(
                datetime.datetime.fromtimestamp(
                    os.path.getmtime(src)).strftime("%Y-%m-%d %H:%M"),
                os.path.getsize(src) / (1024.0 * 1024))
        except Exception:
            src_info = ""
        lbl_si = WinForms.Label()
        lbl_si.Text = src_info
        lbl_si.Font = _FONT_SMALL
        lbl_si.ForeColor = Drawing.Color.Gray
        lbl_si.Location  = Drawing.Point(28, 96)
        lbl_si.Size      = Drawing.Size(610, 16)
        self.Controls.Add(lbl_si)

        sep = WinForms.Label()
        sep.BorderStyle = WinForms.BorderStyle.Fixed3D
        sep.Location = Drawing.Point(16, 120)
        sep.Size     = Drawing.Size(614, 2)
        self.Controls.Add(sep)

        self._rb_arch = WinForms.RadioButton()
        self._rb_arch.Text     = "Open archive copy  (snapshot in repository)"
        self._rb_arch.Location = Drawing.Point(16, 130)
        self._rb_arch.Size     = Drawing.Size(580, 20)
        self.Controls.Add(self._rb_arch)

        lbl_ap = WinForms.Label()
        lbl_ap.Text = "   " + arch
        lbl_ap.Font = _FONT_SMALL
        lbl_ap.ForeColor = Drawing.Color.FromArgb(60, 60, 60)
        lbl_ap.Location  = Drawing.Point(28, 152)
        lbl_ap.Size      = Drawing.Size(610, 16)
        self.Controls.Add(lbl_ap)

        lbl_ad = WinForms.Label()
        lbl_ad.Text = u"   Archived: " + record.get("archive_date", "")
        lbl_ad.Font = _FONT_SMALL
        lbl_ad.ForeColor = Drawing.Color.Gray
        lbl_ad.Location  = Drawing.Point(28, 168)
        lbl_ad.Size      = Drawing.Size(610, 16)
        self.Controls.Add(lbl_ad)

        self._src  = src
        self._arch = arch
        self.Controls.Add(_make_btn("Open Selected", 370, 230, 150, 34,
                                    primary=True, handler=self._open))
        self.Controls.Add(_make_btn("Cancel", 528, 230, 100, 34,
                                    handler=lambda s, e: self.Close()))

    def _open(self, s, e):
        self.open_path = self._src if self._rb_src.Checked else self._arch
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()


# ────────────────────────────────────────────────────────────────────────────
#  ZIP extract dialog  (first-time / flat extraction)
# ────────────────────────────────────────────────────────────────────────────

class ZipExtractDialog(WinForms.Form):
    def __init__(self, zip_path, label):
        self.chosen_dest = ""
        self._zip_path   = zip_path
        self._label      = label
        # Default: flat beside ZIP (same directory as the ZIP)
        self._beside = os.path.dirname(zip_path)
        self._custom = ""

        self.Text          = u"Extract Archive: {0}".format(label)
        self.Width         = 680
        self.Height        = 280
        self.MinimumSize   = Drawing.Size(500, 260)
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox   = False
        self.MaximizeBox   = True
        self.BackColor     = Drawing.Color.White
        self.Font          = _FONT_NORMAL

        lbl_hdr = WinForms.Label()
        lbl_hdr.Text = ("This file is stored as a ZIP archive. "
                        "Choose where to extract it.")
        lbl_hdr.Location = Drawing.Point(16, 14)
        lbl_hdr.Size     = Drawing.Size(620, 20)
        self.Controls.Add(lbl_hdr)

        self._rb_beside = WinForms.RadioButton()
        self._rb_beside.Text     = "Extract to repository folder  (alongside ZIP)"
        self._rb_beside.Location = Drawing.Point(16, 44)
        self._rb_beside.Size     = Drawing.Size(500, 20)
        self._rb_beside.Checked  = True
        self._rb_beside.CheckedChanged += self._on_rb
        self.Controls.Add(self._rb_beside)

        lbl_bd = WinForms.Label()
        lbl_bd.Text         = "   " + self._beside
        lbl_bd.Font         = _FONT_SMALL
        lbl_bd.ForeColor    = Drawing.Color.Gray
        lbl_bd.Location     = Drawing.Point(28, 66)
        lbl_bd.Size         = Drawing.Size(610, 16)
        lbl_bd.AutoEllipsis = True
        lbl_bd.Anchor       = (WinForms.AnchorStyles.Left |
                                WinForms.AnchorStyles.Right)
        self.Controls.Add(lbl_bd)

        self._rb_custom = WinForms.RadioButton()
        self._rb_custom.Text     = "Extract to another location"
        self._rb_custom.Location = Drawing.Point(16, 92)
        self._rb_custom.Size     = Drawing.Size(300, 20)
        self._rb_custom.CheckedChanged += self._on_rb
        self.Controls.Add(self._rb_custom)

        self._tb_custom = WinForms.TextBox()
        self._tb_custom.Location = Drawing.Point(28, 116)
        self._tb_custom.Size     = Drawing.Size(490, 24)
        self._tb_custom.Enabled  = False
        self.Controls.Add(self._tb_custom)

        self._btn_browse = _make_btn("Browse...", 526, 115, 90, 26,
                                      handler=self._browse)
        self._btn_browse.Enabled = False
        self.Controls.Add(self._btn_browse)

        self._lbl_dest = WinForms.Label()
        self._lbl_dest.Font      = _FONT_SMALL
        self._lbl_dest.ForeColor = Drawing.Color.Gray
        self._lbl_dest.Location  = Drawing.Point(28, 144)
        self._lbl_dest.Size      = Drawing.Size(610, 16)
        self.Controls.Add(self._lbl_dest)

        try:
            zip_size = os.path.getsize(zip_path)
            if zip_size > SIZE_WARN_BYTES:
                lbl_warn = WinForms.Label()
                lbl_warn.Text = (u"\u26A0 Archive is {0} -- "
                                 u"extraction may take several minutes.".format(
                                     repo.format_size(zip_size)))
                lbl_warn.Font = _FONT_SMALL
                lbl_warn.ForeColor = _CLR_ARCHIVED_OLD
                lbl_warn.Location  = Drawing.Point(16, 166)
                lbl_warn.Size      = Drawing.Size(620, 16)
                self.Controls.Add(lbl_warn)
        except Exception:
            pass

        self.Controls.Add(_make_btn("Extract and Open", 350, 214, 160, 34,
                                    primary=True, handler=self._extract))
        self.Controls.Add(_make_btn("Cancel", 518, 214, 100, 34,
                                    handler=lambda s, e: self.Close()))

    def _on_rb(self, s, e):
        custom = self._rb_custom.Checked
        self._tb_custom.Enabled  = custom
        self._btn_browse.Enabled = custom

    def _browse(self, s, e):
        dlg = WinForms.FolderBrowserDialog()
        dlg.Description = "Choose extraction folder"
        if dlg.ShowDialog() == WinForms.DialogResult.OK:
            self._custom = dlg.SelectedPath
            self._tb_custom.Text = dlg.SelectedPath
            self._lbl_dest.Text  = u"Will extract to: " + dlg.SelectedPath

    def _extract(self, s, e):
        if self._rb_beside.Checked:
            self.chosen_dest = self._beside
        else:
            if not self._custom:
                WinForms.MessageBox.Show("Please choose an extraction folder.",
                                         "No Folder Selected")
                return
            self.chosen_dest = self._custom
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()


# ────────────────────────────────────────────────────────────────────────────
#  ZIP open dialog  (subsequent opens, includes "Open source" option)
# ────────────────────────────────────────────────────────────────────────────

class ZipOpenDialog(WinForms.Form):
    OPEN_SOURCE    = "source"
    OPEN_EXISTING  = "existing"
    RE_EXTRACT     = "re_extract"
    OTHER_LOCATION = "other"

    def __init__(self, zip_path, extract_path, label, source_path=""):
        self.action      = ""
        self._other_dest = ""   # set by inline browse for OTHER_LOCATION
        self._zip_path   = zip_path
        self._extract    = extract_path
        self._source     = source_path
        self._has_source = bool(source_path) and os.path.exists(source_path)

        self._has_extract = bool(extract_path) and os.path.exists(extract_path)
        self.Text          = u"Open: {0}".format(label)
        # Height depends on how many options are shown
        h = 44  # header
        if self._has_source:   h += 52
        if self._has_extract:  h += 52
        h += 36 + 36 + 70     # re-extract, other, buttons
        self.Height        = h
        self.Width         = 680
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        self.MinimizeBox = self.MaximizeBox = False
        self.BackColor   = Drawing.Color.White
        self.Font        = _FONT_NORMAL

        lbl_hdr = WinForms.Label()
        lbl_hdr.Text = ("This archive was previously extracted. "
                        "What would you like to do?")
        lbl_hdr.Location = Drawing.Point(16, 14)
        lbl_hdr.Size     = Drawing.Size(640, 20)
        self.Controls.Add(lbl_hdr)

        y = 44

        if self._has_source:
            self._rb_src = WinForms.RadioButton()
            self._rb_src.Text     = u"Open original source file  (this machine only)"
            self._rb_src.Location = Drawing.Point(16, y)
            self._rb_src.Size     = Drawing.Size(580, 20)
            self._rb_src.Checked  = True
            self.Controls.Add(self._rb_src)
            lbl_sp = WinForms.Label()
            lbl_sp.Text = "   " + source_path
            lbl_sp.Font = _FONT_SMALL
            lbl_sp.ForeColor = Drawing.Color.Gray
            lbl_sp.Location  = Drawing.Point(28, y + 22)
            lbl_sp.Size      = Drawing.Size(630, 16)
            self.Controls.Add(lbl_sp)
            sep0 = WinForms.Label()
            sep0.BorderStyle = WinForms.BorderStyle.Fixed3D
            sep0.Location = Drawing.Point(16, y + 44)
            sep0.Size     = Drawing.Size(640, 2)
            self.Controls.Add(sep0)
            y += 52
        else:
            self._rb_src = None

        self._rb_open = None   # may remain None if no extract exists
        if self._has_extract:
            self._rb_open = WinForms.RadioButton()
            self._rb_open.Text     = "Open existing extracted copy"
            self._rb_open.Location = Drawing.Point(16, y)
            self._rb_open.Size     = Drawing.Size(500, 20)
            if not self._has_source:
                self._rb_open.Checked = True
            self.Controls.Add(self._rb_open)
            lbl_ep = WinForms.Label()
            lbl_ep.Text = "   " + extract_path
            lbl_ep.Font = _FONT_SMALL
            lbl_ep.ForeColor = Drawing.Color.Gray
            lbl_ep.Location  = Drawing.Point(28, y + 22)
            lbl_ep.Size      = Drawing.Size(630, 16)
            self.Controls.Add(lbl_ep)
            sep1 = WinForms.Label()
            sep1.BorderStyle = WinForms.BorderStyle.Fixed3D
            sep1.Location = Drawing.Point(16, y + 44)
            sep1.Size     = Drawing.Size(640, 2)
            self.Controls.Add(sep1)
            y += 52

        self._rb_re = WinForms.RadioButton()
        self._rb_re.Text     = (u"Extract to repository folder  "
                                u"(extract / re-extract ZIP here)")
        self._rb_re.Location = Drawing.Point(16, y)
        self._rb_re.Size     = Drawing.Size(580, 20)
        # Default to re-extract when no source and no existing extract
        if not self._has_source and not self._has_extract:
            self._rb_re.Checked = True
        self.Controls.Add(self._rb_re)
        sep2 = WinForms.Label()
        sep2.BorderStyle = WinForms.BorderStyle.Fixed3D
        sep2.Location = Drawing.Point(16, y + 28)
        sep2.Size     = Drawing.Size(640, 2)
        self.Controls.Add(sep2)
        y += 36

        self._rb_other = WinForms.RadioButton()
        self._rb_other.Text     = "Extract to a different location"
        self._rb_other.Location = Drawing.Point(16, y)
        self._rb_other.Size     = Drawing.Size(400, 20)
        self.Controls.Add(self._rb_other)
        y += 34

        self.Controls.Add(_make_btn("Proceed", 440, y, 110, 34,
                                    primary=True, handler=self._ok))
        self.Controls.Add(_make_btn("Cancel", 558, y, 100, 34,
                                    handler=lambda s, e: self.Close()))
        self.Height = y + 70

    def _ok(self, s, e):
        if self._rb_src is not None and self._rb_src.Checked:
            self.action = self.OPEN_SOURCE
        elif self._rb_open is not None and self._rb_open.Checked:
            self.action = self.OPEN_EXISTING
        elif self._rb_re.Checked:
            self.action = self.RE_EXTRACT
        elif self._rb_other.Checked:
            # Inline browse for destination folder
            dlg = WinForms.FolderBrowserDialog()
            dlg.Description = "Choose extraction folder"
            if dlg.ShowDialog() != WinForms.DialogResult.OK:
                return
            self._other_dest = dlg.SelectedPath
            self.action = self.OTHER_LOCATION
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()


# ────────────────────────────────────────────────────────────────────────────
#  Archive dialog
# ────────────────────────────────────────────────────────────────────────────

class ArchiveDialog(WinForms.Form):
    WBPJ_ZIP             = "zip"
    WBPJ_COPY_WITH_FILES = "copy_with_files"
    WBPJ_SKIP            = "skip"

    def __init__(self, candidates, open_project_path=None, owner=None):
        self._candidates       = candidates
        self._owner            = owner
        self._archived_results = []
        self._has_wbpj         = any(c["is_wbpj"] for c in candidates)

        self.Text          = u"Archive Repository Files"
        self.Width         = 920
        self.Height        = 560 if self._has_wbpj else 460
        self.StartPosition = WinForms.FormStartPosition.CenterParent
        if owner:
            self.Owner = owner
        self.MinimizeBox = False
        self.MaximizeBox = True
        self.BackColor   = Drawing.Color.White
        self.Font        = _FONT_NORMAL
        self._build_ui()
        self._populate_list()

    def _build_ui(self):
        y = 12
        lbl = WinForms.Label()
        lbl.Text = ("Select files to archive. "
                    "Already-archived files show current status. "
                    "Checked = will archive / re-archive.")
        lbl.Font = _FONT_SMALL
        lbl.ForeColor = Drawing.Color.Gray
        lbl.Location = Drawing.Point(16, y)
        lbl.Size     = Drawing.Size(880, 18)
        self.Controls.Add(lbl)
        y += 28

        self.Controls.Add(_make_btn("Check All",   16, y, 100, 26,
                                    handler=self._check_all))
        self.Controls.Add(_make_btn("Uncheck All", 124, y, 110, 26,
                                    handler=self._uncheck_all))
        y += 36

        self._lv = WinForms.ListView()
        self._lv.View         = WinForms.View.Details
        self._lv.CheckBoxes    = True
        self._lv.FullRowSelect = True
        self._lv.GridLines     = True
        self._lv.Location      = Drawing.Point(16, y)
        self._lv.Size          = Drawing.Size(880, 220)
        self._lv.Font          = _FONT_NORMAL
        self._lv.HeaderStyle   = WinForms.ColumnHeaderStyle.Clickable
        self._lv.Anchor        = (WinForms.AnchorStyles.Top    |
                                   WinForms.AnchorStyles.Bottom |
                                   WinForms.AnchorStyles.Left   |
                                   WinForms.AnchorStyles.Right)
        self._lv_cols = ["Section", "File Name", "Source Location", "Size", "Archive Status"]
        for name, w in [("Section", 150), ("File Name", 220),
                        ("Source Location", 240), ("Size", 80),
                        ("Archive Status", 170)]:
            self._lv.Columns.Add(name, w)
        self._lv.ColumnClick += self._on_archive_col_click
        self._archive_sort_col = -1
        self._archive_sort_asc = True
        self.Controls.Add(self._lv)
        y += 230

        # Bottom panel (anchored to bottom) contains wbpj options + buttons
        # Using a bottom Panel ensures they stay visible when window is resized.
        bottom_h = 150 if self._has_wbpj else 54
        self._bottom_panel = WinForms.Panel()
        self._bottom_panel.BackColor = Drawing.Color.White
        self._bottom_panel.Anchor    = (WinForms.AnchorStyles.Bottom |
                                         WinForms.AnchorStyles.Left  |
                                         WinForms.AnchorStyles.Right)
        self._bottom_panel.Height   = bottom_h
        self._bottom_panel.Left     = 0
        self._bottom_panel.Width    = self.Width - 16

        if self._has_wbpj:
            panel = WinForms.GroupBox()
            panel.Text     = "Workbench Project (.wbpj) Archive Method"
            panel.Location = Drawing.Point(16, 0)
            panel.Size     = Drawing.Size(850, 100)
            panel.Font     = _FONT_NORMAL
            panel.Anchor   = (WinForms.AnchorStyles.Top  |
                               WinForms.AnchorStyles.Left |
                               WinForms.AnchorStyles.Right)

            self._rb_zip = WinForms.RadioButton()
            self._rb_zip.Text     = u"Compress to ZIP  (recommended \u2014 works with any project)"
            self._rb_zip.Location = Drawing.Point(12, 20)
            self._rb_zip.Size     = Drawing.Size(560, 20)
            self._rb_zip.Checked  = True
            panel.Controls.Add(self._rb_zip)

            lbl_rec = WinForms.Label()
            lbl_rec.Text      = u"\u2714 Recommended"
            lbl_rec.ForeColor = _CLR_GREEN_DIM
            lbl_rec.Font      = _FONT_BOLD
            lbl_rec.Location  = Drawing.Point(580, 22)
            lbl_rec.AutoSize  = True
            panel.Controls.Add(lbl_rec)

            self._rb_copy = WinForms.RadioButton()
            self._rb_copy.Text     = ("Copy .wbpj + _files  "
                                      "(no compression, delta update on re-archive)")
            self._rb_copy.Location = Drawing.Point(12, 46)
            self._rb_copy.Size     = Drawing.Size(600, 20)
            panel.Controls.Add(self._rb_copy)

            self._chk_results = WinForms.CheckBox()
            self._chk_results.Text     = u"Include result files (.rst, .db, etc.)  \u2014 applies to ZIP and Copy"
            self._chk_results.Location = Drawing.Point(12, 72)
            self._chk_results.Size     = Drawing.Size(700, 20)
            self._chk_results.Checked  = False
            panel.Controls.Add(self._chk_results)

            self._bottom_panel.Controls.Add(panel)
            btn_top = 108
        else:
            self._rb_zip      = None
            self._rb_copy     = None
            self._chk_results = None
            btn_top = 8

        self._bottom_panel.Controls.Add(
            _make_btn(u"\U0001F4E6  Archive Checked Files",
                      16, btn_top, 210, 36,
                      primary=True, handler=self._on_archive))
        self._bottom_panel.Controls.Add(
            _make_btn("Cancel", 234, btn_top, 100, 36,
                      handler=lambda s, e: self._cancel()))

        self.Controls.Add(self._bottom_panel)

        # Now anchor the ListView to fill between top controls and bottom panel
        self._lv.Anchor = (WinForms.AnchorStyles.Top    |
                           WinForms.AnchorStyles.Bottom |
                           WinForms.AnchorStyles.Left   |
                           WinForms.AnchorStyles.Right)

        # Size the form and position bottom panel
        self.Height = 600 if self._has_wbpj else 480
        self.MinimumSize = Drawing.Size(700, 400)
        self._bottom_panel.Top = self.ClientSize.Height - bottom_h - 4
        self.Resize += self._on_archive_dialog_resize

    def _populate_list(self):
        self._lv.Items.Clear()
        for c in self._candidates:
            item   = WinForms.ListViewItem(c["section_label"])
            status = c["archive_status"]
            if repo.ARCH_STATUS_MISSING in status and not c.get("archive_path", ""):
                item.ForeColor = _CLR_MISSING
            elif repo.ARCH_STATUS_OK in status:
                item.ForeColor = _CLR_ARCHIVED_OK
            elif repo.ARCH_STATUS_OUTDATED in status:
                item.ForeColor = _CLR_ARCHIVED_OLD
            item.SubItems.Add(c["label"])
            item.SubItems.Add(c["source_path"])
            sz_b = c["wbpj_total_size_bytes"] if c["is_wbpj"] else c["source_size_bytes"]
            sz_s = c["wbpj_total_size_str"]   if c["is_wbpj"] else c["source_size_str"]
            if sz_b > SIZE_WARN_BYTES:
                sz_s += u"  \u26A0"
            item.SubItems.Add(sz_s)
            item.SubItems.Add(status)
            item.Checked = (repo.ARCH_STATUS_OK not in status)
            self._lv.Items.Add(item)

    def _on_archive_dialog_resize(self, s, e):
        """Keep bottom panel pinned to bottom when dialog is resized."""
        try:
            bottom_h = self._bottom_panel.Height
            self._bottom_panel.Top   = self.ClientSize.Height - bottom_h - 4
            self._bottom_panel.Width = self.ClientSize.Width - 32
        except Exception:
            pass

    def _on_archive_col_click(self, s, e):
        """Sort the archive candidate list by clicked column."""
        try:
            col = e.Column
            if self._archive_sort_col == col:
                self._archive_sort_asc = not self._archive_sort_asc
            else:
                self._archive_sort_col = col
                self._archive_sort_asc = True

            items = []
            for i in range(self._lv.Items.Count):
                item = self._lv.Items[i]
                checked = item.Checked
                row = [item.Text] + [item.SubItems[j].Text
                                     for j in range(1, item.SubItems.Count)]
                items.append((row, checked, item.ForeColor))

            def sort_key(t):
                val = t[0][col] if col < len(t[0]) else ""
                return val.lower()

            items.sort(key=sort_key, reverse=not self._archive_sort_asc)

            self._lv.Items.Clear()
            for row, checked, colour in items:
                item = WinForms.ListViewItem(row[0])
                item.ForeColor = colour
                for cell in row[1:]:
                    item.SubItems.Add(cell)
                item.Checked = checked
                self._lv.Items.Add(item)
        except Exception as exc:
            pass   # sort failure is non-fatal

    def _check_all(self, s, e):
        for i in range(self._lv.Items.Count):
            self._lv.Items[i].Checked = True

    def _uncheck_all(self, s, e):
        for i in range(self._lv.Items.Count):
            self._lv.Items[i].Checked = False

    def _get_wbpj_method(self):
        if self._rb_zip is None:
            return self.WBPJ_SKIP
        if self._rb_zip.Checked:
            return self.WBPJ_ZIP
        if self._rb_copy.Checked:
            return self.WBPJ_COPY_WITH_FILES
        return self.WBPJ_SKIP

    def _inc_results(self):
        return self._chk_results is not None and self._chk_results.Checked

    def _cancel(self):
        self.DialogResult = WinForms.DialogResult.Cancel
        self.Close()

    def _on_archive(self, s, e):
        checked = [self._candidates[i]
                   for i in range(self._lv.Items.Count)
                   if self._lv.Items[i].Checked]
        if not checked:
            WinForms.MessageBox.Show("No files checked.", "Nothing Selected")
            return

        wbpj_method = self._get_wbpj_method()
        inc_results = self._inc_results()

        large = [c for c in checked
                 if (c["wbpj_total_size_bytes"] if c["is_wbpj"]
                     else c["source_size_bytes"]) > SIZE_WARN_BYTES]
        if large:
            names = "\n".join(u"  \u2022 " + c["label"] for c in large)
            if WinForms.MessageBox.Show(
                    u"Files larger than 1 GB:\n\n{0}\n\nContinue?".format(names),
                    u"Large File Warning",
                    WinForms.MessageBoxButtons.YesNo,
                    WinForms.MessageBoxIcon.Warning) != WinForms.DialogResult.Yes:
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
                            u"Compressing: {0}".format(label),
                            owner=self._owner)
                        prog.Show()
                        WinForms.Application.DoEvents()

                        def _zip_cb(fname, cur, tot):
                            prog.set_progress(cur, tot, fname)

                        dest_path = repo.zip_wbpj_with_files(
                            src, dest_dir,
                            include_results=inc_results,
                            progress_callback=_zip_cb)
                        prog.finish_success()
                        method = "zip"

                    elif wbpj_method == self.WBPJ_COPY_WITH_FILES:
                        is_rearchive = bool(c.get("archive_path", ""))
                        lbl_txt = u"Re-copying" if is_rearchive else u"Copying"
                        prog = ArchiveProgressDialog(
                            u"{0}: {1}".format(lbl_txt, label),
                            owner=self._owner)
                        prog.Show()
                        WinForms.Application.DoEvents()

                        def _copy_cb(fname):
                            prog.set_status(u"Copying: {0}".format(fname))

                        if is_rearchive:
                            dest_path = repo.copy_wbpj_with_files_delta(
                                src, dest_dir,
                                include_results=inc_results,
                                progress_callback=_copy_cb)
                        else:
                            dest_path = repo.copy_wbpj_with_files(
                                src, dest_dir,
                                include_results=inc_results,
                                progress_callback=_copy_cb)
                        prog.finish_success()
                        method = "copy_with_files"
                    else:
                        continue
                else:
                    prog = ArchiveProgressDialog(
                        u"Copying: {0}  ({1})".format(
                            label, repo.format_size(
                                c.get("source_size_bytes", 0))),
                        owner=self._owner)
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
                _log("Archive failed [{0}]: {1}".format(
                    label, traceback.format_exc()))

        msg_parts = []
        if successes:
            msg_parts.append(u"\u2714 Archived ({0}):\n{1}".format(
                len(successes),
                "\n".join(u"  \u2022 " + s for s in successes)))
        if failures:
            msg_parts.append(u"\u2718 Failed ({0}):\n{1}".format(
                len(failures),
                "\n".join(u"  \u2022 " + f for f in failures)))

        WinForms.MessageBox.Show(
            "\n\n".join(msg_parts) if msg_parts else "No files processed.",
            "Archive Complete" if not failures else "Archive -- Partial",
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
        self._form         = form_ref
        self._expanded     = True
        self._suppress_evt = False
        self.BackColor     = Drawing.Color.FromArgb(245, 248, 252)
        self.BorderStyle   = WinForms.BorderStyle.FixedSingle
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
            self._cb_status.SelectedItem = (status if status in items
                                            else items[0])
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
        except Exception as exc:
            _log("Save error: " + str(exc))
            WinForms.MessageBox.Show("Save failed:\n" + str(exc), "Error")

    def _on_status_changed(self, s, e):
        if self._suppress_evt:
            return
        try:
            if str(self._cb_status.SelectedItem or "") != "Archived":
                return
            self._save(None, None)
            if WinForms.MessageBox.Show(
                    u"Set to \u2018Archived\u2019. Archive files now?",
                    "Archive?",
                    WinForms.MessageBoxButtons.YesNo,
                    WinForms.MessageBoxIcon.Question
                    ) == WinForms.DialogResult.Yes:
                self._form.launch_archive_dialog()
        except Exception as exc:
            _log("Status change error: " + str(exc))

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
        self.Size = (Drawing.Size(1300, 106) if self._expanded
                     else Drawing.Size(1300, 36))
        self._btn_toggle.Text = (u"\u25B2 Collapse" if self._expanded
                                 else u"\u25BC Expand")
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

        self.Text          = u"Analysis Repository Manager  \u2014  v1.0"
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
        for text, w, primary, handler in [
            (u"\u2795  Add File(s)...",   160, True,  self._on_add),
            (u"\u21BA  Refresh",          110, False, self._refresh_all),
            (u"\u25B6  Open",             100, False, self._on_open),
            (u"\u2716  Remove",           110, False, self._on_remove),
            (u"\u270E  Notes",            100, False, self._on_notes),
            (u"\u2764  Health Check",     140, False, self._on_health_check),
            (u"\U0001F4E6  Archive",      120, False, self._on_archive),
        ]:
            self.Controls.Add(_make_btn(text, x, toolbar_y, w, toolbar_h,
                                        primary=primary, handler=handler))
            x += w + 8

        # Help button — separated by a small visual gap from the action buttons
        x += 12   # extra gap makes the grouping visually distinct
        btn_help = _make_btn(u"\u2753  Help", x, toolbar_y, 90, toolbar_h,
                             handler=lambda s, e: open_help())
        btn_help.ForeColor = _CLR_ANSYS_BLUE
        btn_help.Font      = _FONT_BOLD
        self.Controls.Add(btn_help)

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
        for name, w in [("File Name",  380), ("Status",    120),
                        ("Size (MB)",   90), ("Modified", 150),
                        ("Date Added", 150), ("Notes",    230),
                        ("Full Path",  380)]:
            lv.Columns.Add(name, w)
        lv.ColumnClick  += self._on_column_click
        lv.DoubleClick  += self._on_double_click
        lv.MouseUp      += self._on_list_mouse_up
        return lv

    def _on_draw_tab(self, s, e):
        try:
            is_active = (e.Index == self._tabs.SelectedIndex)
            bg   = (_CLR_ANSYS_BLUE if is_active
                    else Drawing.Color.FromArgb(240, 240, 240))
            fg   = (Drawing.Color.White if is_active
                    else Drawing.Color.FromArgb(100, 100, 100))
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
        except Exception:
            pass

    def on_panel_resize(self):
        self._info_panel_bottom = (self._info_panel.Top +
                                   self._info_panel.Height + 4)
        self._do_layout()

    def _on_form_resize(self, s, e):
        self._do_layout()

    def _do_layout(self):
        avail = (self.ClientSize.Height - self._info_panel_bottom -
                 self._status_bar.Height - 4)
        self._tabs.Location = Drawing.Point(16, self._info_panel_bottom)
        self._tabs.Size     = Drawing.Size(self.ClientSize.Width - 32,
                                           max(avail, 100))

    def _on_tab_changed(self, s, e):
        idx = self._tabs.SelectedIndex
        if 0 <= idx < len(repo.ALL_SECTIONS):
            self._cur_section = repo.ALL_SECTIONS[idx]
        self._tabs.Invalidate()

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
            COL_FILENAME: "label", COL_STATUS: "status",
            COL_SIZE: "size_mb",   COL_MODIFIED: "modified",
            COL_DATEADDED: "date_added", COL_NOTES: "notes",
            COL_FULLPATH: "source_path",
        }
        key = key_map.get(col, "label")

        def sk(r):
            val = r.get(key, "") or ""
            if col == COL_SIZE:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return 0.0
            return val.lower()

        self._section_data[section] = sorted(records, key=sk, reverse=not asc)
        self._populate_listview(section, self._section_data[section])

    def _refresh_all(self, sender, e):
        try:
            _log("Refresh all sections")

            # ── Auto-import files manually copied into the repository dir ────
            # Scan archive subdirectories for files not in the manifest and
            # silently add them so they appear in the correct tab.
            try:
                untracked = repo.scan_untracked_archive_files()
                if untracked:
                    for u in untracked:
                        repo.add_orphan_to_manifest(u)
                    _log("Auto-imported {0} manually copied file(s)".format(
                        len(untracked)))
                    WinForms.MessageBox.Show(
                        u"{0} file(s) found in the repository directory that "
                        u"were not in the manifest.\n\n"
                        u"They have been added as Archived \u2714 records. "
                        u"Use right-click \u2192 Relink to connect them to "
                        u"a source file if one exists.".format(len(untracked)),
                        u"New Files Detected",
                        WinForms.MessageBoxButtons.OK,
                        WinForms.MessageBoxIcon.Information)
            except Exception as ui_exc:
                _log("Untracked scan error: " + str(ui_exc))

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
            # Use resolved absolute path for display and selection restore
            path = r.get("source_path_abs", "") or r.get("source_path", "")
            item.SubItems.Add(path)

            arch_abs      = r.get("archive_path_abs", "")
            truly_missing = (repo.ARCH_STATUS_MISSING in status and not arch_abs)

            if truly_missing:
                item.ForeColor = _CLR_MISSING
                item.Font      = _FONT_BOLD
            elif repo.ARCH_STATUS_OK in status:
                item.ForeColor = _CLR_ARCHIVED_OK
                item.Font      = _FONT_NORMAL
            elif repo.ARCH_STATUS_OUTDATED in status:
                item.ForeColor = _CLR_ARCHIVED_OLD
                item.Font      = _FONT_BOLD
            elif repo.ARCH_STATUS_UNARCHIVED in status:
                item.ForeColor = _CLR_UNARCHIVED
                item.Font      = _FONT_NORMAL
            elif repo.ARCH_STATUS_LOCAL in status:
                item.ForeColor = _CLR_LOCAL
                item.Font      = _FONT_NORMAL
            elif (repo.ARCH_STATUS_SRC_CHANGED in status or
                  repo.ARCH_STATUS_SRC_MISSING in status):
                item.ForeColor = _CLR_SRC_CHANGED
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
                          if (repo.ARCH_STATUS_MISSING in r.get("status", "") and
                              not r.get("archive_path_abs", "")))
            base = repo.SECTION_LABELS[sec]
            self._tabs.TabPages[i].Text = (
                u"{0}  [{1}  \u2718{2}]".format(base, total, missing)
                if missing > 0 else
                u"{0}  [{1}]".format(base, total))

    def _set_status(self, msg):
        self._status_lbl.Text = msg

    def _current_lv(self):
        return self._listviews.get(self._cur_section)

    def _record_by_manifest_index(self, section, manifest_index):
        """
        Look up a display record from _section_data by its manifest_index field.
        This is safe after sorting because manifest_index is injected by
        get_section_records() and is stable regardless of display order.
        Returns the record dict, or None if not found.
        """
        for rec in self._section_data.get(section, []):
            if rec.get("manifest_index") == manifest_index:
                return rec
        return None

    def _selected_records(self):
        """
        Return list of (manifest_index, record) for selected rows.
        Uses record["manifest_index"] — the stable manifest position —
        NOT item.Index which is the display row and changes with sorting.
        """
        lv      = self._current_lv()
        records = self._section_data.get(self._cur_section, [])
        result  = []
        for item in lv.SelectedItems:
            disp_idx = item.Index
            if 0 <= disp_idx < len(records):
                rec = records[disp_idx]
                manifest_idx = rec.get("manifest_index", disp_idx)
                result.append((manifest_idx, rec))
        return result

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

            records  = self._section_data.get(sec, [])
            disp_idx = hit.Item.Index
            if disp_idx < 0 or disp_idx >= len(records):
                return
            record   = records[disp_idx]
            idx      = record.get("manifest_index", disp_idx)  # stable manifest index
            status   = record.get("status", "")
            arch_abs = record.get("archive_path_abs", "")
            missing  = (repo.ARCH_STATUS_MISSING in status and not arch_abs)
            outdated = repo.ARCH_STATUS_OUTDATED in status
            src_path = record.get("source_path_abs", "") or record.get("source_path", "")
            # Relink available for: MISSING files AND archive-only records (no source)
            has_arch_no_src = bool(arch_abs) and not bool(src_path)

            menu = WinForms.ContextMenuStrip()

            item_open = menu.Items.Add(u"\u25B6  Open")
            item_open.Enabled = not (missing and not arch_abs)
            item_open.Click  += lambda s2, e2: self._on_open(None, None)

            item_notes = menu.Items.Add(u"\u270E  Edit Notes")
            item_notes.Click += lambda s2, e2: self._on_notes(None, None)

            menu.Items.Add(WinForms.ToolStripSeparator())

            # Open directories
            ref_dir = os.path.dirname(src_path) if src_path else ""
            item_ref = menu.Items.Add(u"\U0001F4C2  Open Reference Directory")
            item_ref.Enabled = bool(ref_dir) and os.path.isdir(ref_dir)
            _ref = ref_dir
            item_ref.Click += lambda s2, e2, d=_ref: (
                os.startfile(d) if d and os.path.isdir(d) else None)

            rep_dir = os.path.dirname(arch_abs) if arch_abs else ""
            item_rep = menu.Items.Add(u"\U0001F4C2  Open Repository Directory")
            item_rep.Enabled = bool(rep_dir) and os.path.isdir(rep_dir)
            _rep = rep_dir
            item_rep.Click += lambda s2, e2, d=_rep: (
                os.startfile(d) if d and os.path.isdir(d) else None)

            menu.Items.Add(WinForms.ToolStripSeparator())

            item_relink = menu.Items.Add(
                u"\u27A1  Connect to Source File\u2026" if has_arch_no_src
                else u"\u27A1  Relink Missing File\u2026")
            item_relink.Enabled = missing or has_arch_no_src
            _idx = idx
            _sec = sec
            item_relink.Click += lambda s2, e2: self._on_relink(_sec, _idx)

            item_rearch = menu.Items.Add(u"\u27F3  Re-archive (update copy)")
            item_rearch.Enabled = outdated
            item_rearch.Click  += lambda s2, e2: self._on_rearchive(_sec, _idx)

            # Fix 6: per-row "Archive this file..." -- opens ArchiveDialog
            # pre-filtered to just this single record.
            is_local = record.get("in_user_files", False)
            item_archive_one = menu.Items.Add(u"\U0001F4E6  Archive this file\u2026")
            item_archive_one.Enabled = not is_local
            item_archive_one.Click += lambda s2, e2: self._on_archive_single(_sec, _idx)

            # ── Option B: .wbpz source-project linkage ────────────────────────
            ext = os.path.splitext(src_path)[1].lower() if src_path else ""
            if ext == ".wbpz":
                menu.Items.Add(WinForms.ToolStripSeparator())
                has_src_link = bool(record.get("source_wbpj_path", ""))

                item_link = menu.Items.Add(u"\U0001F517  Link Source Project (.wbpj)\u2026")
                def _do_link(s2, e2, _s=_sec, _i=_idx):
                    self._on_link_source_wbpj(_s, _i)
                item_link.Click += _do_link

                item_clear_link = menu.Items.Add(u"\u26D4  Clear Source Project Link")
                item_clear_link.Enabled = has_src_link
                def _do_clear(s2, e2, _s=_sec, _i=_idx):
                    repo.clear_source_wbpj(_s, _i)
                    self._refresh_all(None, None)
                item_clear_link.Click += _do_clear

            menu.Items.Add(WinForms.ToolStripSeparator())

            item_remove = menu.Items.Add(u"\u2716  Remove from Repository")
            item_remove.Click += lambda s2, e2: self._on_remove(None, None)

            menu.Show(lv, Drawing.Point(e.X, e.Y))
        except Exception as exc:
            _log("Context menu error: " + str(exc))

    def _on_link_source_wbpj(self, section, manifest_index):
        """Option B: let user browse to the .wbpj that was archived to produce this .wbpz."""
        try:
            record = self._record_by_manifest_index(section, manifest_index)
            if record is None:
                return
            label = record.get("label", "")
            dlg = WinForms.OpenFileDialog()
            dlg.Title  = u"Link source .wbpj for \"{0}\"".format(label)
            dlg.Filter = "Workbench Projects (*.wbpj)|*.wbpj|All Files (*.*)|*.*"
            if dlg.ShowDialog() != WinForms.DialogResult.OK:
                return
            repo.link_source_wbpj(section, manifest_index, dlg.FileName)
            self._refresh_all(None, None)
            self._set_status(
                u"Source project linked: {0}".format(
                    os.path.basename(dlg.FileName)))
        except Exception as exc:
            _log("Link source wbpj error: " + str(exc))
            WinForms.MessageBox.Show("Link failed:\n" + str(exc), "Error")

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
        index is manifest_index -- the stable position in the JSON array.
        After prune_stale_fields (which may save the manifest), reload
        the record directly from the manifest using this index.
        """
        repo.prune_stale_fields(section, index)
        data    = repo.load_manifest()
        records = data["sections"].get(section, [])
        if index < 0 or index >= len(records):
            return
        record = records[index]   # re-read from manifest using stable index
        target = repo.get_open_target(record)
        mode   = target["mode"]
        _log("Open mode: {0}  label={1}".format(mode, record.get("label", "")))

        if mode == "none":
            WinForms.MessageBox.Show(
                "No accessible file found.\n\n"
                "Source path does not exist on this machine "
                "and no archive copy is available.", "Cannot Open")
        elif mode == "source":
            _smart_open_file(target["source_path"])
        elif mode == "archive_direct":
            if target["has_source"]:
                dlg = OpenChoiceDialog(record)
                if dlg.ShowDialog() == WinForms.DialogResult.OK and dlg.open_path:
                    _smart_open_file(dlg.open_path)
            else:
                _smart_open_file(target["archive_path"])
        elif mode == "extract_first":
            self._extract_and_open(section, index, record,
                                   target["archive_path"])
        elif mode == "archive_zip":
            dlg = ZipOpenDialog(
                target["archive_path"],
                target["extract_path"],
                record.get("label", ""),
                source_path=(target["source_path"]
                             if target["has_source"] else ""))
            if dlg.ShowDialog() != WinForms.DialogResult.OK:
                return
            if dlg.action == ZipOpenDialog.OPEN_SOURCE:
                _smart_open_file(target["source_path"])
            elif dlg.action == ZipOpenDialog.OPEN_EXISTING:
                _smart_open_file(target["extract_path"])
            elif dlg.action == ZipOpenDialog.RE_EXTRACT:
                # Re-extract to repository folder (alongside ZIP), NOT the
                # previous extract location -- "Extract to repository folder"
                # always targets the section archive directory.
                repo_dir = os.path.dirname(target["archive_path"])
                self._do_extract(section, index, target["archive_path"],
                                 repo_dir)
            elif dlg.action == ZipOpenDialog.OTHER_LOCATION:
                # Use the folder the user browsed to inline in ZipOpenDialog
                other_dest = getattr(dlg, "_other_dest", "")
                if other_dest:
                    self._do_extract(section, index, target["archive_path"],
                                     other_dest)
                else:
                    self._extract_and_open(section, index, record,
                                           target["archive_path"])

    def _extract_and_open(self, section, index, record, zip_path):
        dlg = ZipExtractDialog(zip_path, record.get("label", ""))
        if dlg.ShowDialog() != WinForms.DialogResult.OK:
            return
        self._do_extract(section, index, zip_path, dlg.chosen_dest)

    def _do_extract(self, section, index, zip_path, dest_dir):
        """Extract flat into dest_dir, open .wbpj, offer to set as source."""
        # Fix 3: guard against empty/whitespace dest_dir (stale local_extract_path
        # cleared, or dialog returned no destination) -- fall back to the
        # section's repository archive directory (same dir as the ZIP).
        if not dest_dir or not dest_dir.strip():
            dest_dir = os.path.dirname(zip_path)
            _log("dest_dir was empty -- falling back to: " + dest_dir)
        prog = ArchiveProgressDialog(
            u"Extracting: {0}".format(os.path.basename(zip_path)),
            owner=self)
        prog.Show()
        WinForms.Application.DoEvents()

        try:
            def _cb(fname, cur, tot):
                prog.set_progress(cur, tot, fname)

            extracted_wbpj = repo.zip_extract_to(zip_path, dest_dir,
                                                  progress_callback=_cb)
            prog.finish_success()
        except Exception as exc:
            try:
                prog.finish_success()
            except Exception:
                pass
            _log("Extraction error: " + str(exc))
            WinForms.MessageBox.Show("Extraction failed:\n" + str(exc), "Error")
            return

        if extracted_wbpj and extracted_wbpj.lower().endswith(".wbpj"):
            repo.update_local_extract(section, index, extracted_wbpj)
            _smart_open_file(extracted_wbpj)
            res = WinForms.MessageBox.Show(
                u"Extracted to:\n{0}\n\n"
                u"Set this as your working source for future re-archiving?\n\n"
                u"Yes -- re-archives will compress this copy.\n"
                u"No  -- keep original source reference.".format(
                    extracted_wbpj),
                u"Set as Working Source?",
                WinForms.MessageBoxButtons.YesNo,
                WinForms.MessageBoxIcon.Question)
            if res == WinForms.DialogResult.Yes:
                repo.update_source_path(section, index, extracted_wbpj)
            self._refresh_all(None, None)
        else:
            try:
                os.startfile(dest_dir)
            except Exception:
                WinForms.MessageBox.Show(
                    u"Extraction complete.\nExtracted to: " + dest_dir, "Done")

    def _on_double_click(self, sender, e):
        self._on_open(sender, e)

    def _on_archive_single(self, section, manifest_index):
        """Fix 6: open ArchiveDialog pre-filtered to a single record."""
        try:
            # Guard: in_user_files records are Local - no archiving needed.
            # Use manifest_index lookup (safe after sorting).
            record = self._record_by_manifest_index(section, manifest_index)
            if record and record.get("in_user_files"):
                WinForms.MessageBox.Show(
                    u"This file is a Local reference inside the project "
                    u"directory and does not need to be archived.",
                    u"Local File \u2014 No Archive Needed",
                    WinForms.MessageBoxButtons.OK,
                    WinForms.MessageBoxIcon.Information)
                return
            open_proj  = _get_open_project_path()
            candidates = repo.get_archive_candidates(
                open_proj, only_section=section, only_index=manifest_index)
            if not candidates:
                WinForms.MessageBox.Show(
                    "This file has no source path and cannot be archived "
                    "(or it is the currently open project).",
                    "Cannot Archive")
                return
            dlg = ArchiveDialog(candidates, open_proj, owner=self)
            if dlg.ShowDialog() == WinForms.DialogResult.OK:
                self._refresh_all(None, None)
                if dlg._archived_results:
                    self._set_status(
                        u"Archived {0} file(s)".format(
                            len(dlg._archived_results)))
        except Exception as exc:
            _log("_on_archive_single error: " + traceback.format_exc())
            WinForms.MessageBox.Show("Archive error:\n" + str(exc), "Error")

    def launch_archive_dialog(self):
        try:
            open_proj  = _get_open_project_path()
            candidates = repo.get_archive_candidates(open_proj)
            if not candidates:
                WinForms.MessageBox.Show(
                    "No eligible files found.\n\n"
                    "Add files first. The currently open project is excluded.",
                    "Nothing to Archive")
                return
            dlg = ArchiveDialog(candidates, open_proj, owner=self)
            if dlg.ShowDialog() == WinForms.DialogResult.OK:
                self._refresh_all(None, None)
                if dlg._archived_results:
                    self._set_status(
                        u"Archived {0} file(s)".format(
                            len(dlg._archived_results)))
        except Exception as exc:
            _log("launch_archive_dialog error: " + traceback.format_exc())
            WinForms.MessageBox.Show("Archive error:\n" + str(exc), "Error")

    def _on_rearchive(self, section, manifest_index):
        try:
            record = self._record_by_manifest_index(section, manifest_index)
            if record is None:
                return
            index  = manifest_index   # helpers use manifest_index directly
            src    = record.get("source_path_abs", "") or record.get("source_path", "")
            label  = record.get("label", "")
            method = record.get("archive_method", "copy")

            if not src or not os.path.exists(src):
                WinForms.MessageBox.Show(
                    "Source file not found. Use Relink first.", "Error")
                return

            dest_dir = repo.get_section_archive_dir(section)

            if method == "zip":
                prog = ArchiveProgressDialog(
                    u"Re-compressing: {0}".format(label), owner=self)
                prog.Show()
                WinForms.Application.DoEvents()

                def _cb(fname, cur, tot):
                    prog.set_progress(cur, tot, fname)

                dest_path = repo.zip_wbpj_with_files(
                    src, dest_dir, progress_callback=_cb)
                prog.finish_success()
                repo.update_archive_record(section, index, dest_path, "zip")

            elif method == "copy_with_files":
                prog = ArchiveProgressDialog(
                    u"Re-copying (delta): {0}".format(label), owner=self)
                prog.Show()
                WinForms.Application.DoEvents()

                def _cb2(fname):
                    prog.set_status(u"Copying: {0}".format(fname))

                dest_path = repo.copy_wbpj_with_files_delta(
                    src, dest_dir, progress_callback=_cb2)
                prog.finish_success()
                repo.update_archive_record(section, index, dest_path,
                                           "copy_with_files")
            else:
                prog = ArchiveProgressDialog(
                    u"Re-copying: {0}".format(label), owner=self)
                prog.Show()
                prog.set_status("Copying...")
                WinForms.Application.DoEvents()
                dest_path = repo.archive_regular_file(src, dest_dir)
                prog.finish_success()
                repo.update_archive_record(section, index, dest_path, "copy")

            self._refresh_all(None, None)
            self._set_status(u"Re-archived: {0}".format(label))

        except Exception as exc:
            _log("Re-archive error: " + str(exc))
            WinForms.MessageBox.Show("Re-archive failed:\n" + str(exc), "Error")

    def _on_relink(self, section, manifest_index):
        try:
            record   = self._record_by_manifest_index(section, manifest_index)
            if record is None:
                return
            old_path = record.get("source_path_abs", "") or record.get("source_path", "")
            old_name = os.path.basename(old_path) if old_path else ""
            dlg = WinForms.OpenFileDialog()
            dlg.Title    = u"Relink: locate \"{0}\"".format(old_name)
            dlg.Filter   = "All Files (*.*)|*.*"
            dlg.FileName = old_name
            if dlg.ShowDialog() != WinForms.DialogResult.OK:
                return
            repo.relink_file_record(section, manifest_index, dlg.FileName)
            self._refresh_all(None, None)
            self._set_status(
                u"Relinked: {0}".format(os.path.basename(dlg.FileName)))
        except Exception as exc:
            _log("Relink error: " + str(exc))
            WinForms.MessageBox.Show("Relink failed:\n" + str(exc), "Error")

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
            if dlg.ShowDialog() != WinForms.DialogResult.OK:
                return

            # ── Best-practice nudge: .wbpj on Supplemental tab ────────────────────
            is_supplemental = (self._cur_section == "supplemental_wb_database")
            has_wbpj = any(f.lower().endswith(".wbpj") for f in dlg.FileNames)
            if is_supplemental and has_wbpj:
                res = WinForms.MessageBox.Show(
                    u"Best Practice \u2014 Supplemental Databases\n\n"
                    u"You are adding a Workbench project (.wbpj) to the "
                    u"Supplemental WB Database section.\n\n"
                    u"Recommended workflow:\n"
                    u"  \u2022 Open the project in Workbench.\n"
                    u"  \u2022 Use File \u2192 Archive to create a .wbpz file.\n"
                    u"  \u2022 Add that .wbpz here instead of the .wbpj.\n\n"
                    u"Benefits of referencing a .wbpz:\n"
                    u"  \u2022 File opens directly \u2014 no extraction needed.\n"
                    u"  \u2022 Original .wbpj is protected from accidental edits.\n"
                    u"  \u2022 Archiving in the hub is as simple as any other file.\n\n"
                    u"Continue adding the .wbpj anyway?",
                    u"Best Practice Reminder",
                    WinForms.MessageBoxButtons.YesNo,
                    WinForms.MessageBoxIcon.Information)
                if res != WinForms.DialogResult.Yes:
                    return

            added = skipped = 0
            for path in dlg.FileNames:
                if repo.add_file_record(self._cur_section, path):
                    added += 1
                else:
                    skipped += 1
            self._refresh_all(None, None)
            self._set_status(
                u"Added {0} file(s). {1} skipped.".format(added, skipped))
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
                    "Remove {0} file(s)?\n\n{1}".format(len(sel), names),
                    "Confirm Remove",
                    WinForms.MessageBoxButtons.YesNo
                    ) != WinForms.DialogResult.Yes:
                return

            # ── Per-record archive-delete prompt ──────────────────────────────
            # Collect decisions BEFORE any removes so indices stay stable.
            # Keyed by source_path so we can re-locate the record after the
            # manifest reloads (index shifting bug fix).
            delete_archive = {}   # source_path -> bool
            for idx, record in sel:
                arch_abs = record.get("archive_path_abs", "")
                if arch_abs and os.path.exists(arch_abs):
                    label = record.get("label", os.path.basename(arch_abs))
                    res = WinForms.MessageBox.Show(
                        u"Also delete the archived copy from the "
                        u"repository for \"{0}\"?\n\n{1}".format(
                            label, arch_abs),
                        u"Delete Archive Copy?",
                        WinForms.MessageBoxButtons.YesNo,
                        WinForms.MessageBoxIcon.Question)
                    delete_archive[record.get("source_path", "")] = (
                        res == WinForms.DialogResult.Yes)

            # Remove in reverse index order so earlier indices stay valid
            for idx, record in sorted(sel, key=lambda t: t[0], reverse=True):
                removed = repo.remove_file_record(self._cur_section, idx)
                src_key = record.get("source_path", "")
                if removed and delete_archive.get(src_key, False):
                    repo.delete_archive_file(removed)

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
            file_label  = record.get("label", "")
            dlg = NotesDialog(record.get("notes", ""), file_label=file_label)
            if dlg.ShowDialog() == WinForms.DialogResult.OK:
                repo.update_file_notes(self._cur_section, idx, dlg.result_notes)
                self._refresh_all(None, None)
        except Exception as exc:
            _log("Notes error: " + str(exc))

    def _on_health_check(self, sender, e):
        try:
            self._set_status("Running health check...")
            health = repo.run_health_check()
            HealthCheckDialog(health, owner_form=self).ShowDialog()
            self._refresh_all(None, None)
            self._set_status("Health check complete.")
        except Exception as exc:
            _log("Health check error: " + str(exc))
            WinForms.MessageBox.Show("Health check failed:\n" + str(exc), "Error")

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
                u"Please save your project first (File \u2192 Save As\u2026)\n"
                "then click the Analysis Repository button again.",
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
                "Analysis Hub error:\n\n" + str(exc), "Error",
                WinForms.MessageBoxButtons.OK,
                WinForms.MessageBoxIcon.Error)
        except Exception:
            pass


# ────────────────────────────────────────────────────────────────────────────
#  ACT callbacks
# ────────────────────────────────────────────────────────────────────────────

def init(ext):
    try:
        _log("init: InstallDir = " + ext.InstallDir)
        ext_subdir = os.path.join(ext.InstallDir, "AnalysisHub")
        if ext_subdir not in sys.path:
            sys.path.insert(0, ext_subdir)
    except Exception as exc:
        _log("init error: " + str(exc))


def task_initialize(task):
    try:
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
        _launch_repository_form(task)
        _sync_task_properties(task)
    except Exception as exc:
        _log("task_edit error: " + str(exc))


def task_update(task):
    try:
        user_files_dir = _resolve_project_dir(task)
        if user_files_dir:
            repo.set_base_directory(user_files_dir)
            _sync_task_properties(task)
    except Exception as exc:
        _log("task_update error: " + str(exc))


def task_refresh(task):
    try:
        task_update(task)
    except Exception as exc:
        _log("task_refresh error: " + str(exc))


def task_reset(task):
    _log("task_reset called")


def task_status(task):
    try:
        user_files_dir = _resolve_project_dir(task)
        if not user_files_dir:
            return ["Unfulfilled", "No project directory - please save"]
        repo.set_base_directory(user_files_dir)
        total, missing = repo.get_summary_stats()
        if total == 0:
            return ["Unfulfilled", "Repository empty"]
        elif missing > 0:
            return ["Refresh Required",
                    "{0} file(s) missing".format(missing)]
        else:
            return ["UpToDate", "Repository OK - {0} tracked".format(total)]
    except Exception as exc:
        _log("task_status error: " + str(exc))
        return ["UpToDate", "Repository"]


def task_report(task, report):
    try:
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
        user_files_dir = _resolve_project_dir(task)
        if user_files_dir:
            repo.set_base_directory(user_files_dir)
        _sync_task_properties(task)
        total, missing = repo.get_summary_stats()
        WinForms.MessageBox.Show(
            u"Refreshed.\nTotal: {0}   Missing: {1}".format(total, missing),
            u"Analysis Hub")
    except Exception as exc:
        _log("context_refresh error: " + str(exc))


def context_health_check(task):
    try:
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
        _log("toolbar error: " + str(exc))


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
