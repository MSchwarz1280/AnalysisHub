# -*- coding: utf-8 -*-
"""
main.py  —  AnalysisHub ACT Extension  (Entry Point)
=====================================================
Implements all ACT callbacks (task lifecycle, context menus, toolbar)
and defines the WinForms-based Repository Manager UI.

Environment: IronPython 2.7 inside ANSYS Workbench 2024 R2 (v242)+
             .NET 4.x / System.Windows.Forms available via clr.

Key design rules
----------------
* All UI is built with System.Windows.Forms — no external dependencies.
* Backend logic lives exclusively in repository_helpers.py.
* Every public function is try/except-wrapped and writes to the debug log.
* IronPython 2.7 syntax: no f-strings, no Python-3-only builtins.

Cumulative changes
------------------
* Project directory resolved via Project.GetProjectFile() (ANSYS documented API)
* Log resets at module load time so Reload Extension always gives a clean log
* Column header sort — click any column to sort; each tab independent
* Right-click context menu — Open, Edit Notes, Relink Missing File, Remove
* Relink missing files from both the main list and the Health Check dialog
* Active tab painted blue/bold; inactive tabs grey
* Tab padding and fixed height for readability
* Bold column headers; HeaderStyle.Clickable for sort support
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
#  Logging — reset at module load so Reload Extension clears the log
# ────────────────────────────────────────────────────────────────────────────

LOG_PATH = r"C:\Temp\AnalysisHub_debug.log"

try:
    with open(LOG_PATH, "w") as _fh:
        _fh.write("=" * 80 + "\n")
        _fh.write("  AnalysisHub  -  Module loaded / reloaded: {0}\n".format(
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
    """Return the user_files path for the open project, or None."""
    try:
        wbpj_path = Project.GetProjectFile()
        if wbpj_path and wbpj_path.strip():
            wbpj_path  = wbpj_path.strip()
            proj_dir   = wbpj_path[:wbpj_path.rfind("\\")]
            proj_name  = wbpj_path[wbpj_path.rfind("\\") + 1:-5]
            user_files = proj_dir + "\\" + proj_name + "_files\\user_files"
            _log("Resolved user_files via Project.GetProjectFile(): " + user_files)
            if os.path.exists(proj_dir):
                return user_files
    except Exception as exc:
        _log("Project.GetProjectFile() failed: " + str(exc))

    if task is not None:
        try:
            ad = task.ActiveDirectory
            if ad and os.path.isdir(ad):
                _log("Resolved via task.ActiveDirectory: " + ad)
                return ad
        except Exception as exc:
            _log("task.ActiveDirectory failed: " + str(exc))

    try:
        for tg in ExtAPI.DataModel.TaskGroups:
            if tg.Name == "AnalysisHubGroup":
                for t in tg.Tasks:
                    ad = t.ActiveDirectory
                    if ad and os.path.isdir(ad):
                        _log("Resolved via DataModel task: " + ad)
                        return ad
    except Exception as exc:
        _log("DataModel scan failed: " + str(exc))

    _log("WARNING: No saved project found.")
    return None


# ────────────────────────────────────────────────────────────────────────────
#  Smart file opener
# ────────────────────────────────────────────────────────────────────────────

def _smart_open_file(path):
    if not path or not os.path.exists(path):
        _log("Open failed - file does not exist: " + str(path))
        return False
    ext = os.path.splitext(path)[1].lower()
    _log("Opening: {0}  (ext={1})".format(path, ext))
    try:
        if ext in (".wbpj", ".wbpz"):
            try:
                install_root = Ansys.Utilities.ApplicationConfiguration.DefaultConfiguration.AwpRootEnvironmentVariableValue
                platform     = Ansys.Utilities.ApplicationConfiguration.DefaultConfiguration.Platform
                runwb2       = System.IO.Path.Combine(install_root, "Framework", "bin", platform, "runwb2.exe")
                if System.IO.File.Exists(runwb2):
                    info = System.Diagnostics.ProcessStartInfo()
                    info.FileName        = runwb2
                    info.Arguments       = '-F "{0}"'.format(path)
                    info.UseShellExecute = False
                    System.Diagnostics.Process.Start(info)
                    _log("Opened .wbpj with runwb2")
                    return True
            except Exception as exc:
                _log("runwb2 launch error: " + str(exc))

        if ext in (".txt", ".py", ".log", ".csv", ".md", ".xml", ".json", ".ini", ".bat"):
            notepadpp = r"C:\Program Files\Notepad++\notepad++.exe"
            if os.path.exists(notepadpp):
                System.Diagnostics.Process.Start(notepadpp, '"{0}"'.format(path))
                _log("Opened with Notepad++")
                return True

        os.startfile(path)
        _log("Opened with default application")
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
#  UI colours / fonts / column index constants
# ────────────────────────────────────────────────────────────────────────────

_CLR_ANSYS_BLUE  = Drawing.Color.FromArgb(0,  120, 212)
_CLR_READY       = Drawing.Color.FromArgb(16, 124,  16)
_CLR_MISSING     = Drawing.Color.FromArgb(209,  52,  56)
_CLR_ROW_ALT     = Drawing.Color.FromArgb(245, 247, 250)
_CLR_SECTION_HDR = Drawing.Color.FromArgb(220, 230, 245)

_FONT_NORMAL = Drawing.Font("Segoe UI",  9.5)
_FONT_BOLD   = Drawing.Font("Segoe UI",  9.5, Drawing.FontStyle.Bold)
_FONT_TITLE  = Drawing.Font("Segoe UI", 13,   Drawing.FontStyle.Bold)
_FONT_SMALL  = Drawing.Font("Segoe UI",  8.5)

# Column index constants
COL_FILENAME  = 0
COL_STATUS    = 1
COL_SIZE      = 2
COL_MODIFIED  = 3
COL_DATEADDED = 4
COL_NOTES     = 5
COL_FULLPATH  = 6


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

        self.Controls.Add(_make_btn("OK",     260, 185, 90, 32, primary=True, handler=self._ok))
        self.Controls.Add(_make_btn("Cancel", 360, 185, 90, 32, handler=self._cancel))

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

        self.Controls.Add(_make_btn("Save",   240, 172, 90, 32, primary=True, handler=self._ok))
        self.Controls.Add(_make_btn("Cancel", 340, 172, 90, 32, handler=self._cancel))

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
#  Health-check dialog  (with inline Relink support)
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
        colour  = _CLR_MISSING if missing > 0 else _CLR_READY
        icon    = u"\u2718 ISSUES FOUND" if missing > 0 else u"\u2714 ALL FILES OK"

        lbl_icon = WinForms.Label()
        lbl_icon.Text      = icon
        lbl_icon.Font      = Drawing.Font("Segoe UI", 13, Drawing.FontStyle.Bold)
        lbl_icon.ForeColor = colour
        lbl_icon.Location  = Drawing.Point(16, 14)
        lbl_icon.AutoSize  = True
        self.Controls.Add(lbl_icon)

        lbl_sum = WinForms.Label()
        lbl_sum.Text     = "Total: {0}   Ready: {1}   Missing: {2}".format(
            total, ready, missing)
        lbl_sum.Location = Drawing.Point(16, 46)
        lbl_sum.AutoSize = True
        self.Controls.Add(lbl_sum)

        if missing > 0:
            lbl_hint = WinForms.Label()
            lbl_hint.Text      = u"Select a missing file and click \u27A1 Relink to locate it."
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

        self.Controls.Add(_make_btn("Close", 620, 440, 100, 32, primary=True,
                                    handler=lambda s, e: self.Close()))

    def _on_selection_changed(self, s, e):
        """Enable Relink only when exactly one row is selected."""
        self._btn_relink.Enabled = (self._lv.SelectedItems.Count == 1)

    def _on_relink(self, s, e):
        """Browse for the new location of the selected missing file."""
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
                    "Could not locate this record in the manifest.\n"
                    "Close and use Refresh, then try again.",
                    "Relink Error")
                return

            dlg = WinForms.OpenFileDialog()
            dlg.Title    = u"Relink: locate \"{0}\"".format(old_name)
            dlg.Filter   = "All Files (*.*)|*.*"
            dlg.FileName = old_name

            if dlg.ShowDialog() != WinForms.DialogResult.OK:
                return

            new_path = dlg.FileName
            repo.relink_file_record(section, index, new_path)
            _log("Health check relink: {0} -> {1}".format(old_path, new_path))

            # Update the row in place — no need to close and reopen
            selected.SubItems[2].Text = new_path
            selected.SubItems[1].Text = os.path.basename(new_path)
            selected.ForeColor        = _CLR_READY

            still_missing = sum(
                1 for i in range(self._lv.Items.Count)
                if self._lv.Items[i].ForeColor == _CLR_MISSING)

            if still_missing == 0:
                WinForms.MessageBox.Show(
                    u"\u2714 All missing files have been relinked.\n\n"
                    "Click Close then Refresh to update the main list.",
                    "Relink Complete")

        except Exception as exc:
            _log("Health check relink error: " + str(exc))
            WinForms.MessageBox.Show("Relink failed:\n" + str(exc), "Error")

    def _find_record(self, label, old_path):
        """Locate the manifest section and index for a missing file entry."""
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
#  Project-info panel
# ────────────────────────────────────────────────────────────────────────────

class ProjectInfoPanel(WinForms.Panel):
    def __init__(self, form_ref):
        self._form     = form_ref
        self._expanded = True
        self.BackColor   = Drawing.Color.FromArgb(245, 248, 252)
        self.BorderStyle = WinForms.BorderStyle.FixedSingle
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

        self.Controls.Add(_make_btn("Save Info", 300, 4, 90, 22, primary=True,
                                    handler=self._save))

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
            _log("ProjectInfoPanel save error: " + str(exc))
            WinForms.MessageBox.Show("Save failed:\n" + str(exc), "Error")

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

        self.Controls.Add(_make_btn(u"\u2795  Add File(s)...", 16,  toolbar_y, 160,
                                    toolbar_h, primary=True, handler=self._on_add))
        self.Controls.Add(_make_btn(u"\u21BA  Refresh",        186, toolbar_y, 110,
                                    toolbar_h, handler=self._refresh_all))
        self.Controls.Add(_make_btn(u"\u25B6  Open",           306, toolbar_y, 100,
                                    toolbar_h, handler=self._on_open))
        self.Controls.Add(_make_btn(u"\u2716  Remove",         416, toolbar_y, 110,
                                    toolbar_h, handler=self._on_remove))
        self.Controls.Add(_make_btn(u"\u270E  Notes",          536, toolbar_y, 100,
                                    toolbar_h, handler=self._on_notes))
        self.Controls.Add(_make_btn(u"\u2764  Health Check",   646, toolbar_y, 140,
                                    toolbar_h, handler=self._on_health_check))

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
                                   e.Bounds.Width, e.Bounds.Height),
                fmt)
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

        sorted_records = sorted(records, key=sort_key, reverse=not asc)
        self._section_data[section] = sorted_records
        self._populate_listview(section, sorted_records)

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

            if status == "MISSING":
                item.ForeColor = _CLR_MISSING
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
            missing = sum(1 for r in records if r.get("status") == "MISSING")
            base    = repo.SECTION_LABELS[sec]
            if missing > 0:
                self._tabs.TabPages[i].Text = u"{0}  [{1}  \u2718{2}]".format(
                    base, total, missing)
            else:
                self._tabs.TabPages[i].Text = u"{0}  [{1}]".format(base, total)

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
            missing = record.get("status") == "MISSING"

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

            menu.Items.Add(WinForms.ToolStripSeparator())

            item_remove = menu.Items.Add(u"\u2716  Remove from Repository")
            item_remove.Click += lambda s2, e2: self._on_remove(None, None)

            menu.Show(lv, Drawing.Point(e.X, e.Y))
        except Exception as exc:
            _log("Context menu error: " + str(exc))

    # ── Relink (main list) ────────────────────────────────────────────────

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
            _log("Relinking [{0}] index {1}: {2} -> {3}".format(
                section, index, old_path, new_path))
            repo.relink_file_record(section, index, new_path)
            self._refresh_all(None, None)
            self._set_status(u"Relinked: {0}".format(os.path.basename(new_path)))
        except Exception as exc:
            _log("Relink error: " + str(exc))
            WinForms.MessageBox.Show("Relink failed:\n" + str(exc), "Error")

    # ── Toolbar handlers ──────────────────────────────────────────────────

    def _on_add(self, sender, e):
        try:
            _log("Add File clicked for section: " + self._cur_section)
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
                WinForms.MessageBox.Show("Failed to open:\n" + path, "Open Error")
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
                    WinForms.MessageBoxButtons.YesNo) != WinForms.DialogResult.Yes:
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
            # Refresh main list in case user relinked files in the dialog
            self._refresh_all(None, None)
            self._set_status("Health check complete.")
        except Exception as exc:
            _log("Health check error: " + str(exc))
            WinForms.MessageBox.Show("Health check failed:\n" + str(exc), "Error")


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
                "Then click the Analysis Repository button again.\n\n"
                "Each project must be saved before its repository can be "
                "created, so that the manifest is stored alongside the "
                "project files.",
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