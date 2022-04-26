# -*- coding: utf-8 -*-

"""
Copyright (c) 2022 Colin Curtain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
"""
import sqlite3
from copy import copy, deepcopy
import datetime
import difflib
import logging
from operator import itemgetter
import os
from random import randint
import re
import sys
import traceback
import webbrowser

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtGui import QHelpEvent
from PyQt6.QtCore import Qt  #, QTextCodec
from PyQt6.QtGui import QBrush, QColor

from .add_item_name import DialogAddItemName
from .color_selector import DialogColorSelect
from .color_selector import colors, TextColor
from .confirm_delete import DialogConfirmDelete
from .helpers import Message, DialogCodeInAllFiles, DialogGetStartAndEndMarks, ExportDirectoryPathDialog
from .GUI.base64_helper import *
from .GUI.ui_dialog_code_text import Ui_Dialog_code_text
from .memo import DialogMemo
from .report_attributes import DialogSelectAttributeParameters
from .reports import DialogReportCoderComparisons, DialogReportCodeFrequencies  # for isinstance()
from .report_codes import DialogReportCodes
from .report_code_summary import DialogReportCodeSummary  # for isinstance()
from .select_items import DialogSelectItems  # for isinstance()

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

CHAR_LIMIT = 50000  # For loading text file chunks


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text_ = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text_)
    logger.error(_("Uncaught exception:") + "\n" + text_)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text_)
    mb.exec()


class DialogCodeText(QtWidgets.QWidget):
    """ Code management. Add, delete codes. Mark and unmark text.
    Add memos and colors to codes.
    Trialled using setHtml for documents, but on marking text Html formatting was replaced, also
    on unmarking text, the unmark was not immediately cleared (needed to reload the file). """

    NAME_COLUMN = 0
    ID_COLUMN = 1
    MEMO_COLUMN = 2
    app = None
    parent_textEdit = None
    tab_reports = None  # Tab widget reports, used for updates to codes
    codes = []
    recent_codes = []  # list of recent codes (up to 5) for textedit context menu
    categories = []
    filenames = []
    file_ = None  # contains filename and file id returned from SelectItems
    code_text = []
    annotations = []
    undo_deleted_codes = []  # undo last deleted code(s), multiple may have been deleted at th same time, so a list
    # Overlapping coded text details
    overlaps_at_pos = []
    overlaps_at_pos_idx = 0
    # Search text variables
    search_indices = []
    search_index = 0
    search_term = ""
    search_type = "3"  # 3 chars or 5 chars or 1 for Enter
    selected_code_index = 0
    eventFilter = None
    important = False  # Show/hide important codes
    attributes = []  # Show selected files using these attributes in list widget
    # A list of dictionaries of autcode history {title, list of dictionary of sql commands}
    autocode_history = []
    # Timers to reduce overly sensitive key events: overlap, re-size oversteps by multiple characters
    code_resize_timer = 0
    overlap_timer = 0
    text = ""

    # Variables for Edit mode, text above also
    ed_codetext = []
    ed_annotations = []
    ed_casetext = []
    prev_text = ""
    code_deletions = []
    edit_mode = False
    edit_pos = 0
    no_codes_annotes_cases = None

    # Variables associated with right-hand side splitter, for project memo, current journal, code rule
    project_memo = False
    journal_entry = False
    code_rule = False

    def __init__(self, app, parent_textedit, tab_reports):

        super(DialogCodeText, self).__init__()
        self.app = app
        self.tab_reports = tab_reports
        sys.excepthook = exception_handler
        self.parent_textEdit = parent_textedit
        self.search_indices = []
        self.search_index = 0
        self.codes, self.categories = self.app.get_codes_categories()
        self.annotations = self.app.get_annotations()
        self.recent_codes = []
        self.autocode_history = []
        self.undo_deleted_codes = []
        self.journal = False
        self.project_memo = False
        self.code_rule = False
        self.important = False
        self.attributes = []
        self.code_resize_timer = datetime.datetime.now()
        self.overlap_timer = datetime.datetime.now()
        self.ui = Ui_Dialog_code_text()
        self.ui.setupUi(self)
        self.ui.groupBox_edit_mode.hide()
        ee = _("EDITING TEXT MODE (Ctrl+E)") + " "
        ee += _(
            "Avoid selecting sections of text with a combination of not underlined (not coded / annotated / case-assigned) and underlined (coded, annotated, case-assigned).")
        ee += " " + _(
            "Positions of the underlying codes / annotations / case-assigned may not correctly adjust if text is typed over or deleted.")
        self.ui.label_editing.setText(ee)
        self.edit_pos = 0
        self.edit_mode = False
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        tree_font = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        tree_font += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(tree_font)
        doc_font = 'font: ' + str(self.app.settings['docfontsize']) + 'pt '
        doc_font += '"' + self.app.settings['font'] + '";'
        self.ui.textEdit.setStyleSheet(doc_font)
        self.ui.label_coder.setText("Coder: " + self.app.settings['codername'])
        self.ui.textEdit.setPlainText("")
        self.ui.textEdit.setAutoFillBackground(True)
        self.ui.textEdit.setToolTip("")
        self.ui.textEdit.setMouseTracking(True)
        self.ui.textEdit.setReadOnly(True)
        self.ui.textEdit.installEventFilter(self)
        self.eventFilterTT = ToolTipEventFilter()
        self.ui.textEdit.installEventFilter(self.eventFilterTT)
        self.ui.textEdit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.textEdit.customContextMenuRequested.connect(self.text_edit_menu)
        self.ui.textEdit.cursorPositionChanged.connect(self.overlapping_codes_in_text)
        self.ui.listWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listWidget.customContextMenuRequested.connect(self.viewfile_menu)
        self.ui.listWidget.setStyleSheet(tree_font)
        self.ui.listWidget.itemClicked.connect(self.listwidgetitem_view_file)
        self.ui.lineEdit_search.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.lineEdit_search.customContextMenuRequested.connect(self.lineedit_search_menu)
        self.get_files()

        # Icons marked icon_24 icons are 24x24 px but need a button of 28
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(playback_next_icon_24), "png")
        self.ui.pushButton_latest.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_latest.pressed.connect(self.go_to_latest_coded_file)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(playback_play_icon_24), "png")
        self.ui.pushButton_next_file.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_next_file.pressed.connect(self.go_to_next_file)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(bookmark_icon_24), "png")
        self.ui.pushButton_bookmark_go.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_bookmark_go.pressed.connect(self.go_to_bookmark)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(notepad_2_icon_24), "png")
        self.ui.pushButton_document_memo.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_document_memo.pressed.connect(self.file_memo)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_next.pressed.connect(self.show_selected_code_in_text_next)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_prev.pressed.connect(self.show_selected_code_in_text_previous)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_grid_icon_24), "png")
        self.ui.pushButton_show_all_codings.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_all_codings.pressed.connect(self.show_all_codes_in_text)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(notepad_pencil_icon), "png")
        self.ui.pushButton_annotate.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_annotate.pressed.connect(self.annotate)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(eye_doc_icon), "png")
        self.ui.pushButton_show_annotations.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_annotations.pressed.connect(self.show_annotations)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(notepad_pencil_red_icon), "png")
        self.ui.pushButton_coding_memo.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_coding_memo.pressed.connect(self.coded_text_memo)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(eye_doc_icon), "png")
        self.ui.pushButton_show_memos.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_memos.pressed.connect(self.show_memos)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(magic_wand_icon), "png")
        self.ui.pushButton_auto_code.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_auto_code.clicked.connect(self.auto_code)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(wand_one_file_icon), "png")
        self.ui.pushButton_auto_code_frag_this_file.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_auto_code_frag_this_file.pressed.connect(self.button_autocode_sentences_this_file)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(wand_all_files_icon), "png")
        self.ui.pushButton_auto_code_frag_all_files.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_auto_code_frag_all_files.pressed.connect(self.button_autocode_sentences_all_files)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(wand_one_file_brackets_icon), "png")
        self.ui.pushButton_auto_code_surround.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_auto_code_surround.pressed.connect(self.button_autocode_surround)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(undo_icon), "png")
        self.ui.pushButton_auto_code_undo.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_auto_code_undo.pressed.connect(self.undo_autocoding)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_icon), "png")
        self.ui.label_exports.setPixmap(pm.scaled(22, 22))
        # Right hand side splitter buttons
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(coding_icon), "png")
        self.ui.pushButton_code_rule.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_code_rule.pressed.connect(self.show_code_rule)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(journal_icon), "png")
        self.ui.pushButton_journal.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_journal.pressed.connect(self.show_current_journal)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(project_icon), "png")
        self.ui.pushButton_project_memo.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_project_memo.pressed.connect(self.show_project_memo)
        self.ui.textEdit_info.textChanged.connect(self.rhs_splitter_text_changed)

        self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
        self.ui.lineEdit_search.setEnabled(False)
        self.ui.checkBox_search_all_files.stateChanged.connect(self.search_for_text)
        self.ui.checkBox_search_all_files.setEnabled(False)
        self.ui.checkBox_search_case.stateChanged.connect(self.search_for_text)
        self.ui.checkBox_search_case.setEnabled(False)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(question_icon), "png")
        self.ui.label_search_regex.setPixmap(QtGui.QPixmap(pm).scaled(22, 22))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(text_letter_t_icon), "png")
        self.ui.label_search_case_sensitive.setPixmap(QtGui.QPixmap(pm).scaled(22, 22))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(clipboard_copy_icon), "png")
        self.ui.label_search_all_files.setPixmap(QtGui.QPixmap(pm).scaled(22, 22))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(font_size_icon), "png")
        self.ui.label_font_size.setPixmap(QtGui.QPixmap(pm).scaled(22, 22))
        self.ui.spinBox_font_size.setValue(self.app.settings['docfontsize'])
        self.ui.spinBox_font_size.valueChanged.connect(self.change_text_font_size)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(playback_back_icon), "png")
        self.ui.pushButton_previous.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_previous.setEnabled(False)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(playback_play_icon), "png")
        self.ui.pushButton_next.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_next.setEnabled(False)
        self.ui.pushButton_next.pressed.connect(self.move_to_next_search_text)
        self.ui.pushButton_previous.pressed.connect(self.move_to_previous_search_text)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(question_icon), "png")
        self.ui.pushButton_help.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_help.pressed.connect(self.help)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(delete_icon), "png")
        self.ui.pushButton_delete_all_codes.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_delete_all_codes.pressed.connect(self.delete_all_codes_from_file)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(tag_icon32), "png")
        self.ui.pushButton_file_attributes.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_file_attributes.pressed.connect(self.get_files_from_attributes)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(star_icon32), "png")
        self.ui.pushButton_important.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_important.pressed.connect(self.show_important_coded)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(pencil_icon), "png")
        self.ui.pushButton_edit.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_edit.pressed.connect(self.edit_mode_toggle)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(pencil_icon), "png")
        self.ui.pushButton_exit_edit.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_exit_edit.pressed.connect(self.edit_mode_toggle)
        self.ui.label_codes_count.setEnabled(False)
        self.ui.treeWidget.setDragEnabled(True)
        self.ui.treeWidget.setAcceptDrops(True)
        self.ui.treeWidget.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.treeWidget.customContextMenuRequested.connect(self.tree_menu)
        self.ui.treeWidget.itemClicked.connect(self.fill_code_label_undo_show_selected_code)
        self.ui.comboBox_export.currentIndexChanged.connect(self.export_option_selected)
        self.ui.splitter.setSizes([150, 400])
        try:
            s0 = int(self.app.settings['dialogcodetext_splitter0'])
            s1 = int(self.app.settings['dialogcodetext_splitter1'])
            if s0 > 5 and s1 > 5:
                self.ui.splitter.setSizes([s0, s1])
            v0 = int(self.app.settings['dialogcodetext_splitter_v0'])
            v1 = int(self.app.settings['dialogcodetext_splitter_v1'])
            if v0 > 5 and v1 > 5:
                # 30s are for the groupboxes containing buttons
                self.ui.leftsplitter.setSizes([v1, 30, v0, 30])
        except KeyError:
            pass
        self.ui.splitter.splitterMoved.connect(self.update_sizes)
        self.ui.leftsplitter.splitterMoved.connect(self.update_sizes)
        self.fill_tree()

    @staticmethod
    def help():
        """ Open help for transcribe section in browser. """

        url = "https://github.com/ccbogel/QualCoder/wiki/07-Coding-Text"
        webbrowser.open(url)

    def change_text_font_size(self):
        """ Spinbox font size changed, range: 6 - 32 points. """

        font = 'font: ' + str(self.ui.spinBox_font_size.value()) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.ui.textEdit.setStyleSheet(font)

    def get_files(self, ids=None):
        """ Get files with additional details and fill list widget.
         Called by: init, get_files_from_attributes
         param:
         ids: list, fill with ids to limit file selection.
         """

        if ids is None:
            ids = []
        self.ui.listWidget.clear()
        self.filenames = self.app.get_text_filenames(ids)
        # Fill additional details about each file in the memo
        cur = self.app.conn.cursor()
        sql = "select length(fulltext), fulltext from source where id=?"
        sql_codings = "select count(cid) from code_text where fid=? and owner=?"
        for f in self.filenames:
            cur.execute(sql, [f['id'], ])
            res = cur.fetchone()
            if res is None:  # Safety catch
                res = [0, ""]
            tt = _("Characters: ") + str(res[0])
            f['characters'] = res[0]
            f['start'] = 0
            f['end'] = res[0]
            f['fulltext'] = res[1]
            cur.execute(sql_codings, [f['id'], self.app.settings['codername']])
            res = cur.fetchone()
            tt += "\n" + _("Codings: ") + str(res[0])
            tt += "\n" + _("From: ") + str(f['start']) + _(" to ") + str(f['end'])
            item = QtWidgets.QListWidgetItem(f['name'])
            if f['memo'] is not None and f['memo'] != "":
                tt += "\nMemo: " + f['memo']
            item.setToolTip(tt)
            self.ui.listWidget.addItem(item)

    def update_file_tooltip(self):
        """ Create tooltip for file containing characters, codings and from: to: if partially loaded.
        Called by get_files, updates to add, remove codings, text edits.
        Requires self.file_ """

        if self.file_ is None:
            return
        cur = self.app.conn.cursor()
        sql = "select length(fulltext), fulltext from source where id=?"
        cur.execute(sql, [self.file_['id'], ])
        res = cur.fetchone()
        if res is None:  # Safety catch
            res = [0, ""]
        tt = _("Characters: ") + str(res[0])
        f = {'characters': res[0], 'start': 0, 'end': res[0], 'fulltext': res[1]}
        sql_codings = "select count(cid) from code_text where fid=? and owner=?"
        cur.execute(sql_codings, [self.file_['id'], self.app.settings['codername']])
        res = cur.fetchone()
        tt += "\n" + _("Codings: ") + str(res[0])
        tt += "\n" + _("From: ") + str(f['start']) + _(" to ") + str(f['end'])
        if self.file_['memo'] is not None and self.file_['memo'] != "":
            tt += "\nMemo: " + self.file_['memo']
        # Find item to update tooltip
        items = self.ui.listWidget.findItems(self.file_['name'], Qt.MatchFlag.MatchExactly)
        if len(items) == 0:
            return
        items[0].setToolTip(tt)

    def get_files_from_attributes(self):
        """ Trim the files list to files identified by attributes.
        Attribute dialing results are a dictionary of:
        [0] attribute name, or 'case name'
        [1] attribute type: character, numeric
        [2] modifier: > < == != like between
        [3] comparison value as list, one item or two items for between

        DialogSelectAttributeParameters returns lists for each parameter selected of:
        attribute name, file or case, character or numeric, operator, list of one or two comparator values
        two comparator values are used with the 'between' operator
        ['source', 'file', 'character', '==', ["'interview'"]]
        ['case name', 'case', 'character', '==', ["'ID1'"]]

        Note, sqls are NOT parameterised.
        results from multiple parameters are intersected, an AND boolean function.
        """

        pm = QtGui.QPixmap()
        ui = DialogSelectAttributeParameters(self.app, "file")
        ui.fill_parameters(self.attributes)
        ok = ui.exec()
        if not ok:
            self.attributes = []
            pm.loadFromData(QtCore.QByteArray.fromBase64(tag_icon32), "png")
            self.ui.pushButton_file_attributes.setIcon(QtGui.QIcon(pm))
            self.ui.pushButton_file_attributes.setToolTip(_("Show files with file attributes"))
            self.get_files()
            return
        self.attributes = ui.parameters
        if not self.attributes:
            pm.loadFromData(QtCore.QByteArray.fromBase64(tag_icon32), "png")
            self.ui.pushButton_file_attributes.setIcon(QtGui.QIcon(pm))
            self.ui.pushButton_file_attributes.setToolTip(_("Show files with file attributes"))
            self.get_files()
            return

        file_ids = []
        case_file_ids = []
        cur = self.app.conn.cursor()
        # Run a series of sql based on each selected attribute
        # Apply a set to the resulting ids to determine the final list of ids
        for a in self.attributes:
            sql = "select id from attribute where "
            # File attributes
            if a[1] == 'file':
                sql += "attribute.name = '" + a[0] + "' "
                sql += " and attribute.value " + a[3] + " "
                if a[3] == 'between':
                    sql += a[4][0] + " and " + a[4][1] + " "
                if a[3] in ('in', 'not in'):
                    sql += "(" + ','.join(a[4]) + ") "  # One item the comma is skipped
                if a[3] not in ('between', 'in', 'not in'):
                    sql += a[4][0]
                if a[2] == 'numeric':
                    sql = sql.replace(' attribute.value ', ' cast(attribute.value as real) ')
                sql += " and attribute.attr_type='file'"
                cur.execute(sql)
                result = cur.fetchall()
                for i in result:
                    file_ids.append(i[0])
            # Case names
            if a[1] == "case":
                # Case text table also links av and images
                sql = "select distinct case_text.fid from cases join case_text on case_text.caseid=cases.caseid "
                sql += "join source on source.id=case_text.fid where cases.name " + a[3]
                if a[3] != "like":
                    sql += a[4][0]
                else:
                    sql += "'%" + a[4][0][1:-1] + "%'"  # remove apstrophies in a[4][0]
                cur.execute(sql)
                case_result = cur.fetchall()
                for i in case_result:
                    case_file_ids.append(i[0])
        if file_ids == [] and case_file_ids == []:
            Message(self.app, "Nothing found", "Nothing found").exec()
            return
        set_ids = {}
        set_file_ids = set(file_ids)
        set_case_file_ids = set(case_file_ids)
        # Need to intersect case file ids and file ids
        if file_ids != [] and case_file_ids != []:
            set_ids = set_file_ids.intersection(set_case_file_ids)
        if file_ids != [] and case_file_ids == []:
            set_ids = set_file_ids
        if file_ids == [] and case_file_ids != []:
            set_ids = set_case_file_ids
        self.get_files(list(set_ids))
        # Prepare message for label tooltop
        msg = ""
        for a in self.attributes:
            if a[1] == 'file':
                msg += " or" + "\n" + a[0] + " " + a[3] + " " + ",".join(a[4])
        if len(msg) > 3:
            msg = msg[3:]
        for a in self.attributes:
            if a[1] == 'case':
                msg += " and" + "\n" + a[0] + " " + a[3] + " " + ",".join(a[4])
        self.ui.pushButton_file_attributes.setToolTip(_("Show files:") + msg)
        pm.loadFromData(QtCore.QByteArray.fromBase64(tag_iconyellow32), "png")
        self.ui.pushButton_file_attributes.setIcon(QtGui.QIcon(pm))

    def update_sizes(self):
        """ Called by changed splitter size """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogcodetext_splitter0'] = sizes[0]
        self.app.settings['dialogcodetext_splitter1'] = sizes[1]
        v_sizes = self.ui.leftsplitter.sizes()
        self.app.settings['dialogcodetext_splitter_v0'] = v_sizes[0]
        self.app.settings['dialogcodetext_splitter_v1'] = v_sizes[1]

    def fill_code_label_undo_show_selected_code(self):
        """ Fill code label with currently selected item's code name and colour.
         Also, if text is highlighted, assign the text to this code.

         Called by: treewidgetitem_clicked, select_tree_item_by_code_name """

        current = self.ui.treeWidget.currentItem()
        # Extra to fill right-hand side splitter details
        self.show_code_rule()

        if current.text(1)[0:3] == 'cat':
            self.ui.label_code.hide()
            self.ui.label_code.setToolTip("")
            return
        self.ui.label_code.show()
        # Set background colour of label to code color, and store current code for underlining
        for c in self.codes:
            if current.text(0) == c['name']:
                fg_color = TextColor(c['color']).recommendation
                style = "QLabel {background-color :" + c['color'] + "; color : " + fg_color + ";}"
                self.ui.label_code.setStyleSheet(style)
                self.ui.label_code.setAutoFillBackground(True)
                tt = c['name'] + "\n"
                if c['memo'] is not None and c['memo'] != "":
                    tt += _("Memo: ") + c['memo']
                self.ui.label_code.setToolTip(tt)
                break
        selected_text = self.ui.textEdit.textCursor().selectedText()
        if len(selected_text) > 0:
            self.mark()
        # When a code is selected undo the show selected code features
        self.highlight()
        # Reload button icons as they dissapear on Windows
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes.
        The Count column counts the number of times that code has been used by selected coder in selected file. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), _("Id"), _("Memo"), _("Count")])
        if self.app.settings['showids'] == 'False':
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "" and c['memo'] is not None:
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)

        ''' Add child categories. look at each unmatched category, iterate through tree
         to add as child, then remove matched categories from the list '''
        count = 0
        while len(cats) > 0 and count < 10000:
            remove_list = []
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                count2 = 0
                while item and count2 < 10000:  # while there is an item in the list
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        memo = ""
                        if c['memo'] != "" and c['memo'] is not None:
                            memo = _("Memo")
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                        child.setToolTip(2, c['memo'])
                        item.addChild(child)
                        remove_list.append(c)
                    it += 1
                    item = it.value()
                    count2 += 1
            for item in remove_list:
                cats.remove(item)
            count += 1

        # Add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                memo = ""
                if c['memo'] != "" and c['memo'] is not None:
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                top_item.setToolTip(2, c['memo'])
                top_item.setBackground(0, QBrush(QColor(c['color']), Qt.BrushStyle.SolidPattern))
                color = TextColor(c['color']).recommendation
                top_item.setForeground(0, QBrush(QColor(color)))
                top_item.setFlags(
                    Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable |
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)
        # Add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            count = 0
            while item and count < 10000:
                if item.text(1) == 'catid:' + str(c['catid']):
                    memo = ""
                    if c['memo'] != "" and c['memo'] is not None:
                        memo = _("Memo")
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                    child.setBackground(0, QBrush(QColor(c['color']), Qt.BrushStyle.SolidPattern))
                    color = TextColor(c['color']).recommendation
                    child.setForeground(0, QBrush(QColor(color)))
                    child.setToolTip(2, c['memo'])
                    child.setFlags(
                        Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable |
                        Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # Make unmatchable
                it += 1
                item = it.value()
                count += 1
        self.ui.treeWidget.expandAll()
        self.fill_code_counts_in_tree()

    def fill_code_counts_in_tree(self):
        """ Count instances of each code for current coder and in the selected file.
        Called by: fill_tree
        """

        if self.file_ is None:
            return
        cur = self.app.conn.cursor()
        sql = "select count(cid) from code_text where cid=? and fid=? and owner=?"
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        count = 0
        while item and count < 10000:
            if item.text(1)[0:4] == "cid:":
                cid = str(item.text(1)[4:])
                try:
                    cur.execute(sql, [cid, self.file_['id'], self.app.settings['codername']])
                    result = cur.fetchone()
                    if result[0] > 0:
                        item.setText(3, str(result[0]))
                        item.setToolTip(3, self.app.settings['codername'])
                    else:
                        item.setText(3, "")
                except Exception as e:
                    msg = "Fill code counts error\n" + str(e) + "\n"
                    msg += sql + "\n"
                    msg += "cid " + str(cid) + "\n"
                    msg += "self.file_['id'] " + str(self.file_['id']) + "\n"
                    logger.debug(msg)
                    item.setText(3, "")
            it += 1
            item = it.value()
            count += 1

    def get_codes_and_categories(self):
        """ Called from init, delete category/code.
        Also called on other coding dialogs in the dialog_list. """

        self.codes, self.categories = self.app.get_codes_categories()

    # RHS splitter details for code rule, current journal, project memo
    def show_code_rule(self):
        """ Show current journal text in right-hand side splitter pane. """

        selected = self.ui.treeWidget.currentItem()
        if selected is None:
            return
        self.project_memo = False
        self.journal_entry = False
        self.code_rule = True
        self.ui.label_info.setText(selected.text(0))
        txt = ""
        if selected.text(1)[0:3] == 'cat':
            for c in self.categories:
                if c['catid'] == int(selected.text(1)[6:]):
                    txt += (c['memo'])
                    break
            self.ui.textEdit_info.hide()
        else:  # Code is selected
            for c in self.codes:
                if c['cid'] == int(selected.text(1)[4:]):
                    if c['memo'] is not None:
                        txt += c['memo']
                    break
            self.ui.textEdit_info.show()
            # Get coded examples
            txt += "\n\n" + _("Examples:") + "\n"
            cur = self.app.conn.cursor()
            cur.execute("select seltext from code_text where length(seltext) > 0 and cid=? order by random() limit 3",
                        [int(selected.text(1)[4:])])
            res = cur.fetchall()
            for i, r in enumerate(res):
                txt += str(i + 1) + ": " + r[0] + "\n"
        self.ui.textEdit_info.setReadOnly(True)
        self.ui.textEdit_info.blockSignals(True)
        self.ui.textEdit_info.setText(txt)

    def show_current_journal(self):
        """ Show current journal text in right-hand side splitter pane. """

        journals = self.app.get_journal_texts()
        if not journals:
            self.journal_entry = False
            return
        self.project_memo = False
        self.journal_entry = journals[0]
        self.code_rule = False
        self.ui.label_info.setText(self.journal_entry['name'])
        self.ui.textEdit_info.setReadOnly(False)
        self.ui.textEdit_info.blockSignals(True)
        self.ui.textEdit_info.setText(self.journal_entry['jentry'])
        self.ui.textEdit_info.blockSignals(False)

    def show_project_memo(self):
        """ Show project memo in right-hand side splitter pane """

        cur = self.app.conn.cursor()
        cur.execute("select memo from project")
        res = cur.fetchone()
        self.project_memo = True
        self.journal_entry = False
        self.code_rule = False
        self.ui.label_info.setText(_("Project memo"))

        self.ui.textEdit_info.setReadOnly(False)
        self.ui.textEdit_info.blockSignals(True)
        self.ui.textEdit_info.setText(res[0])
        self.ui.textEdit_info.blockSignals(False)

    def rhs_splitter_text_changed(self):
        """ Database is updated as text is changed in textEdit_info.
        Text is updated for the current journal, or the overall project memo.
        """

        if self.code_rule:
            return
        cur = self.app.conn.cursor()
        txt = self.ui.textEdit_info.toPlainText()
        if self.journal_entry is not False:
            now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("update journal set jentry=?, date=?, owner=? where jid=?",
                        [txt, now_date, self.app.settings['codername'], self.journal_entry['jid']])
        if self.project_memo is not False:
            cur.execute("update project set memo=?", [txt])
        self.app.conn.commit()
        self.app.delete_backup = False

    # Header section widgets
    def delete_all_codes_from_file(self):
        """ Delete all codes from this file by this coder. """

        if self.file_ is None:
            return
        msg = _("Delete all codings in this file made by ") + self.app.settings['codername']
        ui = DialogConfirmDelete(self.app, msg)
        ok = ui.exec()
        if not ok:
            return
        cur = self.app.conn.cursor()
        sql = "delete from code_text where fid=? and owner=?"
        cur.execute(sql, (self.file_['id'], self.app.settings['codername']))
        self.app.conn.commit()
        self.get_coded_text_update_eventfilter_tooltips()
        self.app.delete_backup = False
        msg = _("All codes by ") + self.app.settings['codername'] + _(" deleted from ") + self.file_['name']
        self.parent_textEdit.append(msg)

    # Search for text methods
    def search_for_text(self):
        """ On text changed in lineEdit_search OR Enter pressed, find indices of matching text.
        Only where text is >=3 OR 5 characters long. Or Enter is pressed (search_type==1).
        Resets current search_index.
        If all files is checked then searches for all matching text across all text files
        and displays the file text and current position to user.
        If case sensitive is checked then text searched is matched for case sensitivity.
        """

        if self.file_ is None:
            return
        if not self.search_indices:
            self.ui.pushButton_next.setEnabled(False)
            self.ui.pushButton_previous.setEnabled(False)
        self.search_indices = []
        self.search_index = -1
        self.search_term = self.ui.lineEdit_search.text()
        self.ui.label_search_totals.setText("0 / 0")
        if len(self.search_term) < int(self.search_type):
            return
        pattern = None
        flags = 0
        if not self.ui.checkBox_search_case.isChecked():
            flags |= re.IGNORECASE
        '''if self.ui.checkBox_search_escaped.isChecked():
            pattern = re.compile(re.escape(self.search_term), flags)
        else:
            try:
                pattern = re.compile(self.search_term, flags)
            except:
                logger.warning('Bad escape')'''
        try:
            pattern = re.compile(self.search_term, flags)
        except re.error as e_:
            logger.warning('re error Bad escape ' + str(e_))
        if pattern is None:
            return
        self.search_indices = []
        if self.ui.checkBox_search_all_files.isChecked():
            """ Search for this text across all files. """
            for filedata in self.app.get_file_texts():
                try:
                    text_ = filedata['fulltext']
                    for match in pattern.finditer(text_):
                        self.search_indices.append((filedata, match.start(), len(match.group(0))))
                except:
                    logger.exception('Failed searching text %s for %s', filedata['name'], self.search_term)
        else:
            try:
                if self.text:
                    for match in pattern.finditer(self.text):
                        # Get result as first dictionary item
                        source_name = self.app.get_file_texts([self.file_['id'], ])[0]
                        self.search_indices.append((source_name, match.start(), len(match.group(0))))
            except:
                logger.exception('Failed searching current file for %s', self.search_term)
        if len(self.search_indices) > 0:
            self.ui.pushButton_next.setEnabled(True)
            self.ui.pushButton_previous.setEnabled(True)
        self.ui.label_search_totals.setText("0 / " + str(len(self.search_indices)))

    def move_to_previous_search_text(self):
        """ Push button pressed to move to previous search text position. """

        if self.file_ is None or self.search_indices == []:
            return
        self.search_index -= 1
        if self.search_index < 0:
            self.search_index = len(self.search_indices) - 1
        cursor = self.ui.textEdit.textCursor()
        prev_result = self.search_indices[self.search_index]
        # prev_result is a tuple containing a dictionary of
        # (name, id, fullltext, memo, owner, date) and char position and search string length
        if self.file_ is None or self.file_['id'] != prev_result[0]['id']:
            self.load_file(prev_result[0])
            self.ui.lineEdit_search.setText(self.search_term)
        cursor.setPosition(prev_result[1])
        cursor.setPosition(cursor.position() + prev_result[2], QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(str(self.search_index + 1) + " / " + str(len(self.search_indices)))

    def move_to_next_search_text(self):
        """ Push button pressed to move to next search text position. """

        if self.file_ is None or self.search_indices == []:
            return
        self.search_index += 1
        if self.search_index == len(self.search_indices):
            self.search_index = 0
        cursor = self.ui.textEdit.textCursor()
        next_result = self.search_indices[self.search_index]
        # next_result is a tuple containing a dictionary of
        # (name, id, fullltext, memo, owner, date) and char position and search string length
        if self.file_ is None or self.file_['id'] != next_result[0]['id']:
            self.load_file(next_result[0])
            self.ui.lineEdit_search.setText(self.search_term)
        cursor.setPosition(cursor.position() + next_result[2])
        self.ui.textEdit.setTextCursor(cursor)

        # Highlight selected text
        cursor.setPosition(next_result[1])
        cursor.setPosition(cursor.position() + next_result[2], QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(str(self.search_index + 1) + " / " + str(len(self.search_indices)))

    def lineedit_search_menu(self, position):
        """ Option to change from automatic search on 3 characters or more to press Enter to search """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_char3 = QtGui.QAction(_("Automatic search 3 or more characters"))
        action_char5 = QtGui.QAction(_("Automatic search 5 or more characters"))
        action_enter = QtGui.QAction(_("Press Enter to search"))
        if self.search_type != "3":
            menu.addAction(action_char3)
        if self.search_type != "5":
            menu.addAction(action_char5)
        if self.search_type != "Enter":
            menu.addAction(action_enter)
        action = menu.exec(self.ui.lineEdit_search.mapToGlobal(position))
        if action is None:
            return
        if action == action_char3:
            self.search_type = 3
            self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
            self.ui.lineEdit_search.returnPressed.disconnect(self.search_for_text)
            return
        if action == action_char5:
            self.search_type = 5
            self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
            self.ui.lineEdit_search.returnPressed.disconnect(self.search_for_text)
            return
        if action == action_enter:
            self.search_type = 1
            self.ui.lineEdit_search.textEdited.disconnect(self.search_for_text)
            self.ui.lineEdit_search.returnPressed.connect(self.search_for_text)
            return

    def text_edit_recent_codes_menu(self, position):
        """ Alternative context menu.
        Shows a list of recent codes to select from.
        Called by R key press in the text edit pane, only if there is some selected text. """

        if self.ui.textEdit.toPlainText() == "":
            return
        selected_text = self.ui.textEdit.textCursor().selectedText()
        if selected_text == "":
            return
        if len(self.recent_codes) == 0:
            return
        menu = QtWidgets.QMenu()
        for item in self.recent_codes:
            menu.addAction(item['name'])
        action = menu.exec(self.ui.textEdit.mapToGlobal(position))
        if action is None:
            return
        # Remaining actions will be the submenu codes
        self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), action.text())
        self.mark()

    def text_edit_menu(self, position):
        """ Context menu for textEdit.
        Mark, unmark, annotate, copy, memo coded, coded importance. """

        if self.ui.textEdit.toPlainText() == "" or self.edit_mode:
            return
        cursor = self.ui.textEdit.cursorForPosition(position)
        selected_text = self.ui.textEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_annotate = None
        action_copy = None
        action_code_memo = None
        action_edit_annotate = None
        action_end_pos = None
        action_important = None
        action_mark = None
        action_not_important = None
        action_start_pos = None
        action_unmark = None

        # Can have multiple coded text at this position
        for item in self.code_text:
            if cursor.position() + self.file_['start'] >= item['pos0'] and cursor.position() <= item['pos1']:
                action_unmark = QtGui.QAction(_("Unmark"))
                action_code_memo = QtGui.QAction(_("Memo coded text (M)"))
                action_start_pos = QtGui.QAction(_("Change start position (SHIFT LEFT/ALT RIGHT)"))
                action_end_pos = QtGui.QAction(_("Change end position (SHIFT RIGHT/ALT LEFT)"))
                if item['important'] is None or item['important'] > 1:
                    action_important = QtGui.QAction(_("Add important mark (I)"))
                if item['important'] == 1:
                    action_not_important = QtGui.QAction(_("Remove important mark"))
        if action_unmark:
            menu.addAction(action_unmark)
        if action_code_memo:
            menu.addAction(action_code_memo)
        if action_start_pos:
            menu.addAction(action_start_pos)
        if action_end_pos:
            menu.addAction(action_end_pos)
        if action_important:
            menu.addAction(action_important)
        if action_not_important:
            menu.addAction(action_not_important)

        if selected_text != "":
            if self.ui.treeWidget.currentItem() is not None:
                action_mark = menu.addAction(_("Mark (Q)"))
            # Use up to 10 recent codes
            if len(self.recent_codes) > 0:
                submenu = menu.addMenu(_("Mark with recent code (R)"))
                for item in self.recent_codes:
                    submenu.addAction(item['name'])
            action_annotate = menu.addAction(_("Annotate (A)"))
            action_copy = menu.addAction(_("Copy to clipboard"))
        if selected_text == "" and self.is_annotated(cursor.position()):
            action_edit_annotate = menu.addAction(_("Edit annotation"))
        action_set_bookmark = menu.addAction(_("Set bookmark (B)"))
        action = menu.exec(self.ui.textEdit.mapToGlobal(position))
        if action is None:
            return
        if action == action_important:
            self.set_important(cursor.position())
            return
        if action == action_not_important:
            self.set_important(cursor.position(), False)
            return
        if selected_text != "" and action == action_copy:
            self.copy_selected_text_to_clipboard()
            return
        if selected_text != "" and self.ui.treeWidget.currentItem() is not None and action == action_mark:
            self.mark()
            return
        if action == action_annotate:
            self.annotate()
            return
        if action == action_edit_annotate:
            # Used fora point text press rather than a selected text
            self.annotate(cursor.position())
            return
        if action == action_unmark:
            self.unmark(cursor.position())
            return
        if action == action_code_memo:
            self.coded_text_memo(cursor.position())
            return
        if action == action_start_pos:
            self.change_code_pos(cursor.position(), "start")
            return
        if action == action_end_pos:
            self.change_code_pos(cursor.position(), "end")
            return
        if action == action_set_bookmark:
            cur = self.app.conn.cursor()
            bookmark_pos = cursor.position() + self.file_['start']
            cur.execute("update project set bookmarkfile=?, bookmarkpos=?", [self.file_['id'], bookmark_pos])
            self.app.conn.commit()
            return
        # Remaining actions will be the submenu codes
        self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), action.text())
        self.mark()

    def recursive_set_current_item(self, item, text_):
        """ Set matching item to be the current selected item.
        Recurse through any child categories.
        Tried to use QTreeWidget.finditems - but this did not find matching item text
        Called by: textEdit recent codes menu option
        Required for: mark()
        """

        child_count = item.childCount()
        for i in range(child_count):
            if item.child(i).text(0) == text_ and item.child(i).text(1)[0:3] == "cid":
                self.ui.treeWidget.setCurrentItem(item.child(i))
            self.recursive_set_current_item(item.child(i), text_)

    def is_annotated(self, position):
        """ Check if position is annotated to provide annotation menu option.
        Returns True or False """

        for note in self.annotations:
            if (position + self.file_['start'] >= note['pos0'] and position + self.file_['start'] <= note['pos1']) \
                    and note['fid'] == self.file_['id']:
                return True
        return False

    def set_important(self, position, important=True):
        """ Set or unset importance to coded text.
        Importance is denoted using '1'
        params:
            position: textEdit character cursor position
            important: boolean, default True """

        # Need to get coded segments at this position
        if position is None:
            # Called via button
            position = self.ui.textEdit.textCursor().position()
        if self.file_ is None:
            return
        coded_text_list = []
        for item in self.code_text:
            if position + self.file_['start'] >= item['pos0'] and position + self.file_['start'] <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername'] and \
                    ((not important and item['important'] == 1) or (important and item['important'] != 1)):
                coded_text_list.append(item)
        if not coded_text_list:
            return
        text_items = []
        if len(coded_text_list) == 1:
            text_items = [coded_text_list[0]]
        # Multiple codes at this position to select from
        if len(coded_text_list) > 1:
            ui = DialogSelectItems(self.app, coded_text_list, _("Select codes"), "multi")
            ok = ui.exec()
            if not ok:
                return
            text_items = ui.get_selected()
        if not text_items:
            return
        importance = None
        if important:
            importance = 1
        cur = self.app.conn.cursor()
        sql = "update code_text set important=? where cid=? and fid=? and seltext=? and pos0=? and pos1=? and owner=?"
        for item in text_items:
            cur.execute(sql,
                        (importance, item['cid'], item['fid'], item['seltext'], item['pos0'], item['pos1'],
                         item['owner']))
            self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def file_memo(self):
        """ Open file memo to view or edit. """

        if self.file_ is None:
            return
        ui = DialogMemo(self.app, _("Memo for file: ") + self.file_['name'], self.file_['memo'])
        ui.exec()
        memo = ui.memo
        if memo == self.file_['memo']:
            return
        self.file_['memo'] = memo
        cur = self.app.conn.cursor()
        cur.execute("update source set memo=? where id=?", (memo, self.file_['id']))
        self.app.conn.commit()
        self.filenames = self.app.get_text_filenames()
        self.ui.listWidget.clear()
        for f in self.filenames:
            item = QtWidgets.QListWidgetItem(f['name'])
            item.setToolTip(f['memo'])
            self.ui.listWidget.addItem(item)
        self.app.delete_backup = False

    def coded_text_memo(self, position=None):
        """ Add or edit a memo for this coded text. """

        if position is None:
            # Called via button
            position = self.ui.textEdit.textCursor().position()
        if self.file_ is None:
            return
        coded_text_list = []
        for item in self.code_text:
            if position + self.file_['start'] >= item['pos0'] and position + self.file_['start'] <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                coded_text_list.append(item)
        if not coded_text_list:
            return
        text_item = None
        if len(coded_text_list) == 1:
            text_item = coded_text_list[0]
        # Multiple codes at this position to select from
        if len(coded_text_list) > 1:
            ui = DialogSelectItems(self.app, coded_text_list, _("Select code to memo"), "single")
            ok = ui.exec()
            if not ok:
                return
            text_item = ui.get_selected()
        if text_item is None:
            return
        # Dictionary with cid fid seltext owner date name color memo
        msg = text_item['name'] + " [" + str(text_item['pos0']) + "-" + str(text_item['pos1']) + "]"
        ui = DialogMemo(self.app, _("Memo for Coded text: ") + msg, text_item['memo'], "show", text_item['seltext'])
        ui.exec()
        memo = ui.memo
        if memo == text_item['memo']:
            return
        cur = self.app.conn.cursor()
        cur.execute("update code_text set memo=? where cid=? and fid=? and seltext=? and pos0=? and pos1=? and owner=?",
                    (memo, text_item['cid'], text_item['fid'], text_item['seltext'], text_item['pos0'],
                     text_item['pos1'],
                     text_item['owner']))
        self.app.conn.commit()
        for i in self.code_text:
            if text_item['cid'] == i['cid'] and text_item['seltext'] == i['seltext'] and text_item['pos0'] == i['pos0'] \
                    and text_item['pos1'] == i['pos1'] and text_item['owner'] == self.app.settings['codername']:
                i['memo'] = memo
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def change_code_pos(self, location, start_or_end):
        """  Called via textedit_menu. """
        if self.file_ is None:
            return
        code_list = []
        for item in self.code_text:
            if location + self.file_['start'] >= item['pos0'] and location + self.file_['start'] <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                code_list.append(item)
        if not code_list:
            return
        code_to_edit = None
        if len(code_list) == 1:
            code_to_edit = code_list[0]
        # Multiple codes to select from
        if len(code_list) > 1:
            ui = DialogSelectItems(self.app, code_list, _("Select code for change"), "single")
            ok = ui.exec()
            if not ok:
                return
            code_to_edit = ui.get_selected()
        if code_to_edit is None:
            return
        txt_len = len(self.ui.textEdit.toPlainText())
        changed_start = 0
        changed_end = 0
        int_dialog = QtWidgets.QInputDialog()
        int_dialog.setMinimumSize(60, 150)
        # Remove context flag does not work here
        int_dialog.setWindowFlags(int_dialog.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        msg = _("Key shortcuts\nShift left Arrow\nShift Right Arrow\nAlt Left Arrow\nAlt Right Arrow")
        int_dialog.setWhatsThis(msg)
        int_dialog.setToolTip(msg)
        if start_or_end == "start":
            max_ = code_to_edit['pos1'] - code_to_edit['pos0'] - 1
            min_ = -1 * code_to_edit['pos0']
            changed_start, ok = int_dialog.getInt(self, _("Change start position"),
                                                  _("Change start character position. Positive or negative number:"), 0,
                                                  min_, max_, 1)
            if not ok:
                return
        if start_or_end == "end":
            max_ = txt_len - code_to_edit['pos1']
            min_ = code_to_edit['pos0'] - code_to_edit['pos1'] + 1
            changed_end, ok = int_dialog.getInt(self, _("Change end position"),
                                                _("Change end character position. Positive or negative number:"), 0,
                                                min_, max_, 1)
            if not ok:
                return
        if changed_start == 0 and changed_end == 0:
            return
        int_dialog.done(1)  # need this, as reactiveated when called again with same int value.

        # Update database, reload code_text and highlights
        new_pos0 = code_to_edit['pos0'] + changed_start
        new_pos1 = code_to_edit['pos1'] + changed_end
        cur = self.app.conn.cursor()
        sql = "update code_text set pos0=?, pos1=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
                    (new_pos0, new_pos1, code_to_edit['cid'], code_to_edit['fid'], code_to_edit['pos0'],
                     code_to_edit['pos1'],
                     self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def copy_selected_text_to_clipboard(self):
        """ Copy text to clipboard for external use.
        For example adding text to another document. """

        selected_text = self.ui.textEdit.textCursor().selectedText()
        cb = QtWidgets.QApplication.clipboard()
        cb.setText(selected_text)

    def tree_menu(self, position):
        """ Context menu for treewidget code/category items.
        Add, rename, memo, move or delete code or category. Change code color.
        Assign selected text to current hovered code. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        selected = self.ui.treeWidget.currentItem()
        action_add_code_to_category = None
        action_add_category_to_category = None
        action_merge_category = None
        if selected is not None and selected.text(1)[0:3] == 'cat':
            action_add_code_to_category = menu.addAction(_("Add new code to category"))
            action_add_category_to_category = menu.addAction(_("Add a new category to category"))
            action_merge_category = menu.addAction(_("Merge category into category"))
        action_add_code = menu.addAction(_("Add a new code"))
        action_add_category = menu.addAction(_("Add a new category"))
        action_rename = menu.addAction(_("Rename"))
        action_edit_memo = menu.addAction(_("View or edit memo"))
        action_delete = menu.addAction(_("Delete"))
        action_color = None
        action_show_coded_media = None
        action_move_code = None
        if selected is not None and selected.text(1)[0:3] == 'cid':
            action_color = menu.addAction(_("Change code color"))
            action_show_coded_media = menu.addAction(_("Show coded files"))
            action_move_code = menu.addAction(_("Move code to"))
        action_show_codes_like = menu.addAction(_("Show codes like"))

        action = menu.exec(self.ui.treeWidget.mapToGlobal(position))
        if action is not None:
            if action == action_show_codes_like:
                self.show_codes_like()
            if selected is not None and action == action_color:
                self.change_code_color(selected)
            if action == action_add_category:
                self.add_category()
            if action == action_add_code:
                self.add_code()
            if action == action_merge_category:
                catid = int(selected.text(1).split(":")[1])
                self.merge_category(catid)
            if action == action_add_code_to_category:
                catid = int(selected.text(1).split(":")[1])
                self.add_code(catid)
            if action == action_add_category_to_category:
                catid = int(selected.text(1).split(":")[1])
                self.add_category(catid)
            if selected is not None and action == action_move_code:
                self.move_code(selected)
            if selected is not None and action == action_rename:
                self.rename_category_or_code(selected)
            if selected is not None and action == action_edit_memo:
                self.add_edit__cat_or_code_memo(selected)
            if selected is not None and action == action_delete:
                self.delete_category_or_code(selected)
            if selected is not None and action == action_show_coded_media:
                found_code = None
                tofind = int(selected.text(1)[4:])
                for code in self.codes:
                    if code['cid'] == tofind:
                        found_code = code
                        break
                if found_code:
                    self.coded_media_dialog(found_code)

    def recursive_non_merge_item(self, item, no_merge_list):
        """ Find matching item to be the current selected item.
        Recurse through any child categories.
        Tried to use QTreeWidget.finditems - but this did not find matching item text
        Called by: textEdit recent codes menu option
        Required for: merge_category()
        """

        child_count = item.childCount()
        for i in range(child_count):
            if item.child(i).text(1)[0:3] == "cat":
                no_merge_list.append(item.child(i).text(1)[6:])
            self.recursive_non_merge_item(item.child(i), no_merge_list)
        return no_merge_list

    def merge_category(self, catid):
        """ Select another category to merge this category into. """

        nons = []
        nons = self.recursive_non_merge_item(self.ui.treeWidget.currentItem(), nons)
        nons.append(str(catid))
        non_str = "(" + ",".join(nons) + ")"
        sql = "select name, catid, supercatid from code_cat where catid not in "
        sql += non_str + " order by name"
        cur = self.app.conn.cursor()
        cur.execute(sql)
        res = cur.fetchall()
        category_list = [{'name': "", 'catid': None, 'supercatid': None}]
        for r in res:
            category_list.append({'name': r[0], 'catid': r[1], "supercatid": r[2]})
        ui = DialogSelectItems(self.app, category_list, _("Select blank or category"), "single")
        ok = ui.exec()
        if not ok:
            return
        category = ui.get_selected()
        for c in self.codes:
            if c['catid'] == catid:
                cur.execute("update code_name set catid=? where catid=?", [category['catid'], catid])
        cur.execute("delete from code_cat where catid=?", [catid])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        for cat in self.categories:
            if cat['supercatid'] == catid:
                cur.execute("update code_cat set supercatid=? where supercatid=?", [category['catid'], catid])
        self.app.conn.commit()
        # Clear any orphan supercatids
        sql = "select supercatid from code_cat where supercatid not in (select catid from code_cat)"
        cur.execute(sql)
        orphans = cur.fetchall()
        sql = "update code_cat set supercatid=Null where supercatid=?"
        for i in orphans:
            cur.execute(sql, [i[0]])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()

    def move_code(self, selected):
        """ Move code to another category or to no category.
        Uses a list selection.
        param:
            selected : QTreeWidgetItem
         """

        cid = int(selected.text(1)[4:])
        cur = self.app.conn.cursor()
        cur.execute("select name, catid from code_cat order by name")
        res = cur.fetchall()
        category_list = [{'name': "", 'catid': None}]
        for r in res:
            category_list.append({'name': r[0], 'catid': r[1]})
        ui = DialogSelectItems(self.app, category_list, _("Select blank or category"), "single")
        ok = ui.exec()
        if not ok:
            return
        category = ui.get_selected()
        cur.execute("update code_name set catid=? where cid=?", [category['catid'], cid])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()

    def show_memos(self):
        """ Show all memos for coded text in dialog. """

        if self.file_ is None:
            return
        text_ = ""
        cur = self.app.conn.cursor()
        sql = "select code_name.name, pos0,pos1, seltext, code_text.memo "
        sql += "from code_text join code_name on code_text.cid = code_name.cid "
        sql += "where length(code_text.memo)>0 and fid=? and code_text.owner=? order by pos0"
        cur.execute(sql, [self.file_['id'], self.app.settings['codername']])
        res = cur.fetchall()
        if not res:
            return
        for r in res:
            text_ += '[' + str(r[1]) + '-' + str(r[2]) + '] ' + _("Code: ") + r[0] + "\n"
            text_ += _("Text: ") + r[3] + "\n"
            text_ += _("Memo: ") + r[4] + "\n\n"
        ui = DialogMemo(self.app, _("Memos for file: ") + self.file_['name'], text_)
        ui.ui.pushButton_clear.hide()
        ui.ui.textEdit.setReadOnly(True)
        ui.exec()

    def show_annotations(self):
        """ Show all annotations for text in dialog. """

        if self.file_ is None:
            return
        text_ = ""
        cur = self.app.conn.cursor()
        sql = "select substr(source.fulltext,pos0+1 ,pos1-pos0), pos0, pos1, annotation.memo "
        sql += "from annotation join source on annotation.fid = source.id "
        sql += "where fid=? and annotation.owner=? order by pos0"
        cur.execute(sql, [self.file_['id'], self.app.settings['codername']])
        res = cur.fetchall()
        if not res:
            return
        for r in res:
            text_ += '[' + str(r[1]) + '-' + str(r[2]) + '] ' + "\n"
            text_ += _("Text: ") + r[0] + "\n"
            text_ += _("Annotation: ") + r[3] + "\n\n"
        ui = DialogMemo(self.app, _("Annotations for file: ") + self.file_['name'], text_)
        ui.ui.pushButton_clear.hide()
        ui.ui.textEdit.setReadOnly(True)
        ui.exec()

    def show_important_coded(self):
        """ Show codes flagged as important. """

        self.important = not self.important
        pm = QtGui.QPixmap()
        if self.important:
            pm.loadFromData(QtCore.QByteArray.fromBase64(star_icon_yellow32), "png")
            self.ui.pushButton_important.setToolTip(_("Showing important codings"))
        else:
            pm.loadFromData(QtCore.QByteArray.fromBase64(star_icon32), "png")
            self.ui.pushButton_important.setToolTip(_("Show codings flagged important"))
        self.ui.pushButton_important.setIcon(QtGui.QIcon(pm))
        self.get_coded_text_update_eventfilter_tooltips()

    def show_codes_like(self):
        """ Show all codes if text is empty.
         Show selected codes that contain entered text.
         The input dialog is too narrow, so it is re-created. """

        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Show some codes"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setLabelText(_("Show codes containing the text. (Blank for all)"))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        text_ = str(dialog.textValue())
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, text_)

    def recursive_traverse(self, item, text_):
        """ Find all children codes of this item that match or not and hide or unhide based on 'text'.
        Recurse through all child categories.
        Called by: show_codes_like
        param:
            item: a QTreeWidgetItem
            text:  Text string for matching with code names
        """

        child_count = item.childCount()
        for i in range(child_count):
            if "cid:" in item.child(i).text(1) and len(text_) > 0 and text_ not in item.child(i).text(0):
                item.child(i).setHidden(True)
            if "cid:" in item.child(i).text(1) and text_ == "":
                item.child(i).setHidden(False)
            self.recursive_traverse(item.child(i), text_)

    def keyPressEvent(self, event):
        """ This works best without the modifiers.
         As pressing Ctrl + E give the Ctrl but not the E.
         These key presses are not used in edi mode.

        A annotate - for current selection
        Q Quick Mark with code - for current selection
        B Create bookmark - at clicked position
        H Hide / Unhide top groupbox
        I Tag important
        M memo code - at clicked position
        O Shortcut to cycle through overlapping codes - at clicked position
        S search text - may include current selection
        R opens a context menu for recently used codes for marking text
        """

        if not self.ui.textEdit.hasFocus():
            return
        # Ignore all other key events if edit mode is active
        if self.edit_mode:
            return
        key = event.key()
        # mod = QtGui.QGuiApplication.keyboardModifiers()
        cursor_pos = self.ui.textEdit.textCursor().position()
        selected_text = self.ui.textEdit.textCursor().selectedText()
        codes_here = []
        for item in self.code_text:
            if cursor_pos + self.file_['start'] >= item['pos0'] and \
                    cursor_pos + self.file_['start'] <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                codes_here.append(item)
        # Annotate selected
        if key == QtCore.Qt.Key.Key_A and selected_text != "":
            self.annotate()
            return
        # Bookmark
        if key == QtCore.Qt.Key.Key_B and self.file_ is not None:
            text_pos = self.ui.textEdit.textCursor().position() + self.file_['start']
            cur = self.app.conn.cursor()
            cur.execute("update project set bookmarkfile=?, bookmarkpos=?", [self.file_['id'], text_pos])
            self.app.conn.commit()
            return
        # Hide unHide top groupbox
        if key == QtCore.Qt.Key.Key_H:
            self.ui.groupBox.setHidden(not (self.ui.groupBox.isHidden()))
            return
        # Important  for coded text
        if key == QtCore.Qt.Key.Key_I:
            self.set_important(cursor_pos)
            return
        # Memo for current code
        if key == QtCore.Qt.Key.Key_M:
            self.coded_text_memo(cursor_pos)
            return
        # Overlapping codes cycle
        now = datetime.datetime.now()
        overlap_diff = now - self.overlap_timer
        if key == QtCore.Qt.Key.Key_O and len(self.overlaps_at_pos) > 0 and overlap_diff.microseconds > 150000:
            self.overlap_timer = datetime.datetime.now()
            self.highlight_selected_overlap()
            return
        # Quick mark selected
        if key == QtCore.Qt.Key.Key_Q and selected_text != "":
            self.mark()
            return
        # Recent codes context menu
        if key == QtCore.Qt.Key.Key_R and self.file_ is not None and self.ui.textEdit.textCursor().selectedText() != "":
            self.text_edit_recent_codes_menu(self.ui.textEdit.cursorRect().topLeft())
            return
        # Search, with or without selected
        if key == QtCore.Qt.Key.Key_S and self.file_ is not None:
            if selected_text == "":
                self.ui.lineEdit_search.setFocus()
            else:
                self.ui.lineEdit_search.setText(selected_text)
                self.search_for_text()
                self.ui.pushButton_next.setFocus()

    def highlight_selected_overlap(self):
        """ Highlight the current overlapping text code, by placing formatting on top. """

        self.overlaps_at_pos_idx += 1
        if self.overlaps_at_pos_idx >= len(self.overlaps_at_pos):
            self.overlaps_at_pos_idx = 0
        item = self.overlaps_at_pos[self.overlaps_at_pos_idx]
        # Remove formatting
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(int(item['pos0'] - self.file_['start']), QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(int(item['pos1'] - self.file_['start']), QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())
        # Reapply formatting
        color = ""
        for code in self.codes:
            if code['cid'] == item['cid']:
                color = code['color']
        fmt = QtGui.QTextCharFormat()
        brush = QBrush(QColor(color))
        fmt.setBackground(brush)
        if item['important']:
            fmt.setFontWeight(QtGui.QFont.Weight.Bold)
        fmt.setForeground(QBrush(QColor(TextColor(color).recommendation)))
        cursor.setCharFormat(fmt)
        self.apply_underline_to_overlaps()

    def overlapping_codes_in_text(self):
        """ When coded text is clicked on.
        Only enabled if two or more codes are here.
        Adjust for when portion of full text file loaded.
        Called by: textEdit cursor position changed. """

        self.overlaps_at_pos = []
        self.overlaps_at_pos_idx = 0
        pos = self.ui.textEdit.textCursor().position()
        for item in self.code_text:
            if item['pos0'] <= pos + self.file_['start'] and item['pos1'] >= pos + self.file_['start']:
                # logger.debug("Code name for selected pos0:" + str(item['pos0'])+" pos1:"+str(item['pos1'])
                self.overlaps_at_pos.append(item)
        if len(self.overlaps_at_pos) < 2:
            self.overlaps_at_pos = []
            self.overlaps_at_pos_idx = 0

    def export_option_selected(self):
        """ ComboBox export option selected. """

        text_ = self.ui.comboBox_export.currentText()
        if text_ == "":
            return
        if text_ == "html":
            self.export_html_file()
        if text_ == "odt":
            self.export_odt_file()
        self.ui.comboBox_export.setCurrentIndex(0)

    def export_odt_file(self):
        """ Export text to open document format with .odt ending.
        QTextWriter supports plaintext, ODF and HTML.
        Cannot export tooltips.
        Called by export_option_selected
        """

        if len(self.ui.textEdit.document().toPlainText()) == 0:
            return
        filename = self.file_['name'] + ".odt"
        exp_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = exp_dir.filepath
        if filepath is None:
            return
        tw = QtGui.QTextDocumentWriter()
        tw.setFileName(filepath)
        tw.setFormat(b'ODF')  # byte array needed for Windows 10
        tw.write(self.ui.textEdit.document())
        msg = _("Coded text file exported: ") + filepath
        self.parent_textEdit.append(msg)
        Message(self.app, _('Coded text file exported'), msg, "information").exec()

    def export_html_file(self):
        """ Export text to html file.
        Called by export_option_selected.
        TODO export tooltips. """

        if len(self.ui.textEdit.document().toPlainText()) == 0:
            return
        html_filename = self.file_['name'] + ".html"
        exp_dir = ExportDirectoryPathDialog(self.app, html_filename)
        filepath = exp_dir.filepath
        if filepath is None:
            return
        tw = QtGui.QTextDocumentWriter()
        tw.setFileName(filepath)
        tw.setFormat(b'HTML')  # byte array needed for Windows 10
        #tw.setCodec(QTextCodec.codecForName('UTF-8'))  # for Windows 10
        tw.write(self.ui.textEdit.document())
        msg = _("Coded text file exported to: ") + filepath
        self.parent_textEdit.append(msg)
        Message(self.app, _('Coded text file exported'), msg, "information").exec()

    def eventFilter(self, object_, event):
        """ Using this event filter to identify treeWidgetItem drop events.
        http://doc.qt.io/qt-5/qevent.html#Type-enum
        QEvent::Drop 63 A drag and drop operation is completed (QDropEvent).
        https://stackoverflow.com/questions/28994494/why-does-qtreeview-not-fire-a-drop-or-move-event-during-drag-and-drop

        Also use it to detect key events in the textedit.
        These are used to extend or shrink a text coding.
        Only works if clicked on a code (text cursor is in the coded text).
        Shrink start and end code positions using alt arrow left and alt arrow right
        Extend start and end code positions using shift arrow left, shift arrow right
        Ctrl + E Turn Edit mode on or off
        Ctrl + Z Undo the last coding deletion.
        """

        if object_ is self.ui.treeWidget.viewport():
            if event.type() == QtCore.QEvent.Type.Drop:
                item = self.ui.treeWidget.currentItem()
                # event position is QPointF, itemAt requires toPoint
                parent = self.ui.treeWidget.itemAt(event.position().toPoint())
                self.item_moved_update_data(item, parent)
                return True
        # Change start and end code positions using alt arrow left and alt arrow right
        # and shift arrow left, shift arrow right
        # QtGui.QKeyEvent = 7
        if type(event) == QtGui.QKeyEvent:
            key = event.key()
            mod = event.modifiers()
            if key == QtCore.Qt.Key.Key_Z and mod == QtCore.Qt.KeyboardModifier.ControlModifier:
                self.undo_last_unmarked_code()
                return True
        if type(event) == QtGui.QKeyEvent and self.ui.textEdit.hasFocus():
            key = event.key()
            mod = event.modifiers()
            # using timer for a lot of things
            now = datetime.datetime.now()
            diff = now - self.code_resize_timer
            if diff.microseconds < 100000:
                return False
            # Ctrl + E Edit mode
            if key == QtCore.Qt.Key.Key_E and mod == QtCore.Qt.KeyboardModifier.ControlModifier:
                self.edit_mode_toggle()
                return True
            # Ignore all other key events if edit mode is active
            if self.edit_mode:
                return False
            cursor_pos = self.ui.textEdit.textCursor().position()
            codes_here = []
            for item in self.code_text:
                if cursor_pos + self.file_['start'] >= item['pos0'] and \
                        cursor_pos + self.file_['start'] <= item['pos1'] and \
                        item['owner'] == self.app.settings['codername']:
                    codes_here.append(item)
            if len(codes_here) == 1:
                # Key event can be too sensitive, adjusted  for 150 millisecond gap
                self.code_resize_timer = datetime.datetime.now()
                if key == QtCore.Qt.Key.Key_Left and mod == QtCore.Qt.KeyboardModifier.AltModifier:
                    self.shrink_to_left(codes_here[0])
                    return True
                if key == QtCore.Qt.Key.Key_Right and mod == QtCore.Qt.KeyboardModifier.AltModifier:
                    self.shrink_to_right(codes_here[0])
                    return True
                if key == QtCore.Qt.Key.Key_Left and mod == QtCore.Qt.KeyboardModifier.ShiftModifier:
                    self.extend_left(codes_here[0])
                    return True
                if key == QtCore.Qt.Key.Key_Right and mod == QtCore.Qt.KeyboardModifier.ShiftModifier:
                    self.extend_right(codes_here[0])
                    return True
        return False

    def extend_left(self, code_):
        """ Shift left arrow. """

        if code_['pos0'] < 1:
            return
        code_['pos0'] -= 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos0=?, seltext=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
                    (code_['pos0'], seltext, code_['cid'], code_['fid'], code_['pos0'] + 1, code_['pos1'],
                     self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def extend_right(self, code_):
        """ Shift right arrow. """

        if code_['pos1'] + 1 >= len(self.ui.textEdit.toPlainText()):
            return
        code_['pos1'] += 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos1=?, seltext=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
                    (code_['pos1'], seltext, code_['cid'], code_['fid'], code_['pos0'], code_['pos1'] - 1,
                     self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def shrink_to_left(self, code_):
        """ Alt left arrow, shrinks code from the right end of the code. """

        if code_['pos1'] <= code_['pos0'] + 1:
            return
        code_['pos1'] -= 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos1=?, seltext=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
                    (code_['pos1'], seltext, code_['cid'], code_['fid'], code_['pos0'], code_['pos1'] + 1,
                     self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def shrink_to_right(self, code_):
        """ Alt right arrow shrinks code from the left end of the code. """

        if code_['pos0'] >= code_['pos1'] - 1:
            return
        code_['pos0'] += 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos0=?, seltext=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
                    (code_['pos0'], seltext, code_['cid'], code_['fid'], code_['pos0'] - 1, code_['pos1'],
                     self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def show_selected_code_in_text_next(self):
        """ Highlight only the selected code in the text. Move to next instance in text
        from the current textEdit cursor position.
        Adjust for a portion of text loaded.
        Called by: pushButton_show_codings_next
        """

        if self.file_ is None:
            return
        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1)[0:3] == 'cat':
            return
        cid = int(item.text(1)[4:])
        # Index list has to be dynamic, as a new code_text item could be created before this method is called again
        # Develop indexs and tooltip coded text list
        indexes = []
        tt_code_text = []
        for ct in self.code_text:
            if ct['cid'] == cid:
                indexes.append(ct)
                tt_code_text.append(ct)
        indexes = sorted(indexes, key=itemgetter('pos0'))
        cursor = self.ui.textEdit.textCursor()
        cur_pos = cursor.position()
        end_pos = 0
        found_larger = False
        msg = "/" + str(len(indexes))
        for i, index in enumerate(indexes):
            if index['pos0'] - self.file_['start'] > cur_pos:
                cur_pos = index['pos0'] - self.file_['start']
                end_pos = index['pos1'] - self.file_['start']
                found_larger = True
                msg = str(i + 1) + msg
                break
        if not found_larger and indexes == []:
            return
        # loop around to highest index
        if not found_larger and indexes != []:
            cur_pos = indexes[0]['pos0'] - self.file_['start']
            end_pos = indexes[0]['pos1'] - self.file_['start']
            msg = "1" + msg
        if not found_larger:
            cursor = self.ui.textEdit.textCursor()
            cursor.setPosition(0)
            self.ui.textEdit.setTextCursor(cursor)
        self.unlight()
        msg = " " + _("Code:") + " " + msg
        # Highlight the code in the text
        color = ""
        for c in self.codes:
            if c['cid'] == cid:
                color = c['color']
        cursor.setPosition(cur_pos)
        self.ui.textEdit.setTextCursor(cursor)
        cursor.setPosition(cur_pos, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(end_pos, QtGui.QTextCursor.MoveMode.KeepAnchor)
        brush = QBrush(QColor(color))
        fmt = QtGui.QTextCharFormat()
        fmt.setBackground(brush)
        foregroundcol = TextColor(color).recommendation
        fmt.setForeground(QBrush(QColor(foregroundcol)))
        cursor.mergeCharFormat(fmt)
        # Update tooltips to show only this code
        self.eventFilterTT.set_codes_and_annotations(tt_code_text, self.codes, self.annotations, self.file_['start'])
        # Need to reload arrow iconsas they dissapear on Windows
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_color_grid_icon_24), "png")
        self.ui.pushButton_show_all_codings.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_prev.setStyleSheet("background-color : " + color + ";color:" + foregroundcol)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        tt = _("Show previous coding of selected code") + msg
        self.ui.pushButton_show_codings_prev.setToolTip(tt)
        self.ui.pushButton_show_codings_next.setStyleSheet("background-color : " + color + ";color:" + foregroundcol)
        tt = _("Show next coding of selected code") + msg
        self.ui.pushButton_show_codings_next.setToolTip(tt)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))

    def show_selected_code_in_text_previous(self):
        """ Highlight only the selected code in the text. Move to previous instance in text from
        the current textEdit cursor position.
        Called by: pushButton_show_codings_previous
        """

        if self.file_ is None:
            return
        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1)[0:3] == 'cat':
            return
        cid = int(item.text(1)[4:])
        # Index list has to be dynamic, as a new code_text item could be created before this method is called again
        # Develop indexes and tooltip coded text list
        indexes = []
        tt_code_text = []
        for ct in self.code_text:
            if ct['cid'] == cid:
                indexes.append(ct)
                tt_code_text.append(ct)
        indexes = sorted(indexes, key=itemgetter('pos0'), reverse=True)
        cursor = self.ui.textEdit.textCursor()
        cur_pos = cursor.position()
        end_pos = 0
        found_smaller = False
        msg = "/" + str(len(indexes))
        for i, index in enumerate(indexes):
            if index['pos0'] - self.file_['start'] < cur_pos - 1:
                cur_pos = index['pos0'] - self.file_['start']
                end_pos = index['pos1'] - self.file_['start']
                found_smaller = True
                msg = str(len(indexes) - i) + msg
                break
        if not found_smaller and indexes == []:
            return
        # Loop around to highest index
        if not found_smaller and indexes != []:
            cur_pos = indexes[0]['pos0'] - self.file_['start']
            end_pos = indexes[0]['pos1'] - self.file_['start']
            msg = str(len(indexes)) + msg
        msg += " " + _("Code:") + " " + msg
        self.unlight()
        # Highlight the code in the text
        color = ""
        for c in self.codes:
            if c['cid'] == cid:
                color = c['color']
        cursor.setPosition(cur_pos)
        self.ui.textEdit.setTextCursor(cursor)
        cursor.setPosition(cur_pos, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(end_pos, QtGui.QTextCursor.MoveMode.KeepAnchor)
        brush = QBrush(QColor(color))
        fmt = QtGui.QTextCharFormat()
        fmt.setBackground(brush)
        foregroundcol = TextColor(color).recommendation
        fmt.setForeground(QBrush(QColor(foregroundcol)))
        cursor.mergeCharFormat(fmt)
        # Update tooltips to show only this code
        self.eventFilterTT.set_codes_and_annotations(tt_code_text, self.codes, self.annotations, self.file_['start'])
        # Need to reload arrow icons as they dissapear on Windows
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_color_grid_icon_24), "png")
        self.ui.pushButton_show_all_codings.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_prev.setStyleSheet("background-color : " + color + ";color:" + foregroundcol)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        tt = _("Show previous coding of selected code") + msg
        self.ui.pushButton_show_codings_prev.setToolTip(tt)
        self.ui.pushButton_show_codings_next.setStyleSheet("background-color : " + color + ";color:" + foregroundcol)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))
        tt = _("Show next coding of selected code") + msg
        self.ui.pushButton_show_codings_next.setToolTip(tt)

    def show_all_codes_in_text(self):
        """ Opposes show selected code methods.
        Highlights all the codes in the text. """

        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_grid_icon_24), "png")
        self.ui.pushButton_show_all_codings.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_prev.setStyleSheet("")
        self.ui.pushButton_show_codings_next.setStyleSheet("")
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        tt = _("Show previous coding of selected code")
        self.ui.pushButton_show_codings_prev.setToolTip(tt)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))
        tt = _("Show next coding of selected code")
        self.ui.pushButton_show_codings_next.setToolTip(tt)
        self.unlight()
        self.highlight()
        self.get_coded_text_update_eventfilter_tooltips()

    def coded_media_dialog(self, code_dict):
        """ Display all coded media for this code, in a separate modal dialog.
        Coded media comes from ALL files for this coder.
        Need to store textedit start and end positions so that code in context can be used.
        Called from tree_menu.
        param:
            code_dict : code dictionary
        """

        DialogCodeInAllFiles(self.app, code_dict)

    def item_moved_update_data(self, item, parent):
        """ Called from drop event in treeWidget view port.
        identify code or category to move.
        Also merge codes if one code is dropped on another code. """

        # find the category in the list
        if item.text(1)[0:3] == 'cat':
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(item.text(1)[6:]):
                    found = i
            if found == -1:
                return
            if parent is None:
                self.categories[found]['supercatid'] = None
            else:
                if parent.text(1).split(':')[0] == 'cid':
                    # parent is code (leaf) cannot add child
                    return
                supercatid = int(parent.text(1).split(':')[1])
                if supercatid == self.categories[found]['catid']:
                    # something went wrong
                    return
                self.categories[found]['supercatid'] = supercatid
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set supercatid=? where catid=?",
                        [self.categories[found]['supercatid'], self.categories[found]['catid']])
            self.app.conn.commit()
            self.update_dialog_codes_and_categories()
            self.app.delete_backup = False
            return

        # find the code in the list
        if item.text(1)[0:3] == 'cid':
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(item.text(1)[4:]):
                    found = i
            if found == -1:
                return
            if parent is None:
                self.codes[found]['catid'] = None
            else:
                if parent.text(1).split(':')[0] == 'cid':
                    # parent is code (leaf) cannot add child, but can merge
                    self.merge_codes(self.codes[found], parent)
                    return
                catid = int(parent.text(1).split(':')[1])
                self.codes[found]['catid'] = catid

            cur = self.app.conn.cursor()
            cur.execute("update code_name set catid=? where cid=?",
                        [self.codes[found]['catid'], self.codes[found]['cid']])
            self.app.conn.commit()
            self.app.delete_backup = False
            self.update_dialog_codes_and_categories()

    def merge_codes(self, item, parent):
        """ Merge code or category with another code or category.
        Called by item_moved_update_data when a code is moved onto another code. """

        msg = '<p style="font-size:' + str(self.app.settings['fontsize']) + 'px">'
        msg += _("Merge code: ") + item['name'] + _(" into code: ") + parent.text(0) + '</p>'
        reply = QtWidgets.QMessageBox.question(None, _('Merge codes'),
                                               msg, QtWidgets.QMessageBox.StandardButton.Yes,
                                               QtWidgets.QMessageBox.StandardButton.No)
        if reply == QtWidgets.QMessageBox.StandardButton.No:
            return
        cur = self.app.conn.cursor()
        old_cid = item['cid']
        new_cid = int(parent.text(1).split(':')[1])
        try:
            cur.execute("update code_text set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_av set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_image set cid=? where cid=?", [new_cid, old_cid])
            self.app.conn.commit()
        except sqlite3.Error:
            pass
        cur.execute("delete from code_name where cid=?", [old_cid, ])
        self.app.conn.commit()
        self.app.delete_backup = False
        msg = msg.replace("\n", " ")
        self.parent_textEdit.append(msg)
        self.update_dialog_codes_and_categories()
        self.get_coded_text_update_eventfilter_tooltips()

    def add_code(self, catid=None):
        """ Use add_item dialog to get new code text. Add_code_name dialog checks for
        duplicate code name. A random color is selected for the code.
        New code is added to data and database.
        param:
            catid : None to add to without category, catid to add to to category. """

        ui = DialogAddItemName(self.app, self.codes, _("Add new code"), _("Code name"))
        ui.exec()
        code_name = ui.get_new_name()
        if code_name is None:
            return
        code_color = colors[randint(0, len(colors) - 1)]
        item = {'name': code_name, 'memo': "", 'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'catid': catid,
                'color': code_color}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,?,?,?,?)",
                    (item['name'], item['memo'], item['owner'], item['date'], item['catid'], item['color']))
        self.app.conn.commit()
        self.app.delete_backup = False
        cur.execute("select last_insert_rowid()")
        cid = cur.fetchone()[0]
        item['cid'] = cid
        self.parent_textEdit.append(_("New code: ") + item['name'])
        self.update_dialog_codes_and_categories()
        self.get_coded_text_update_eventfilter_tooltips()

    def update_dialog_codes_and_categories(self):
        """ Update code and category tree here and in DialogReportCodes, ReportCoderComparisons, ReportCodeFrequencies
        Using try except blocks for each instance, as instance may have been deleted. """

        self.get_codes_and_categories()
        self.fill_tree()
        self.unlight()
        self.highlight()
        self.get_coded_text_update_eventfilter_tooltips()

        contents = self.tab_reports.layout()
        if contents:
            for i in reversed(range(contents.count())):
                c = contents.itemAt(i).widget()
                if isinstance(c, DialogReportCodes):
                    c.get_codes_categories_coders()
                    c.fill_tree()
                if isinstance(c, DialogReportCoderComparisons):
                    c.get_data()
                    c.fill_tree()
                if isinstance(c, DialogReportCodeFrequencies):
                    c.get_data()
                    c.fill_tree()
                if isinstance(c, DialogReportCodeSummary):
                    c.get_codes_and_categories()
                    c.fill_tree()

    def add_category(self, supercatid=None):
        """ When button pressed, add a new category.
        Note: the addItem dialog does the checking for duplicate category names
        param:
            suoercatid : None to add without category, supercatid to add to category. """

        ui = DialogAddItemName(self.app, self.categories, _("Category"), _("Category name"))
        ui.exec()
        new_category_name = ui.get_new_name()
        if new_category_name is None:
            return
        item = {'name': new_category_name, 'cid': None, 'memo': "",
                'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)",
                    (item['name'], item['memo'], item['owner'], item['date'], supercatid))
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False
        self.parent_textEdit.append(_("New category: ") + item['name'])

    def delete_category_or_code(self, selected):
        """ Determine if selected item is a code or category before deletion. """

        if selected.text(1)[0:3] == 'cat':
            self.delete_category(selected)
            return  # Avoid error as selected is now None
        if selected.text(1)[0:3] == 'cid':
            self.delete_code(selected)

    def delete_code(self, selected):
        """ Find code, remove from database, refresh and code data and fill treeWidget.
        """

        # Find the code in the list, check to delete
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                found = i
        if found == -1:
            return
        code_ = self.codes[found]
        ui = DialogConfirmDelete(self.app, _("Code: ") + selected.text(0))
        ok = ui.exec()
        if not ok:
            return
        cur = self.app.conn.cursor()
        cur.execute("delete from code_name where cid=?", [code_['cid'], ])
        cur.execute("delete from code_text where cid=?", [code_['cid'], ])
        cur.execute("delete from code_av where cid=?", [code_['cid'], ])
        cur.execute("delete from code_image where cid=?", [code_['cid'], ])
        self.app.conn.commit()
        self.app.delete_backup = False
        self.update_dialog_codes_and_categories()
        self.parent_textEdit.append(_("Code deleted: ") + code_['name'] + "\n")
        # Remove from recent codes
        for item in self.recent_codes:
            if item['name'] == code_['name']:
                self.recent_codes.remove(item)
                break
        self.update_dialog_codes_and_categories()

    def delete_category(self, selected):
        """ Find category, remove from database, refresh categories and code data
        and fill treeWidget. """

        found = -1
        for i in range(0, len(self.categories)):
            if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                found = i
        if found == -1:
            return
        category = self.categories[found]
        ui = DialogConfirmDelete(self.app, _("Category: ") + selected.text(0))
        ok = ui.exec()
        if not ok:
            return
        cur = self.app.conn.cursor()
        cur.execute("update code_name set catid=null where catid=?", [category['catid'], ])
        cur.execute("update code_cat set supercatid=null where catid = ?", [category['catid'], ])
        cur.execute("delete from code_cat where catid = ?", [category['catid'], ])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False
        self.parent_textEdit.append(_("Category deleted: ") + category['name'])

    def add_edit__cat_or_code_memo(self, selected):
        """ View and edit a memo for a category or code. """

        if selected.text(1)[0:3] == 'cid':
            # Find the code in the list
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.app, _("Memo for Code: ") + self.codes[found]['name'], self.codes[found]['memo'])
            ui.exec()
            memo = ui.memo
            if memo != self.codes[found]['memo']:
                self.codes[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_name set memo=? where cid=?", (memo, self.codes[found]['cid']))
                self.app.conn.commit()
                self.app.delete_backup = False
            if memo == "":
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, _("Memo"))
                self.parent_textEdit.append(_("Memo for code: ") + self.codes[found]['name'])

        if selected.text(1)[0:3] == 'cat':
            # Find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.app, _("Memo for Category: ") + self.categories[found]['name'],
                            self.categories[found]['memo'])
            ui.exec()
            memo = ui.memo
            if memo != self.categories[found]['memo']:
                self.categories[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_cat set memo=? where catid=?", (memo, self.categories[found]['catid']))
                self.app.conn.commit()
                self.app.delete_backup = False
            if memo == "":
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, _("Memo"))
                self.parent_textEdit.append(_("Memo for category: ") + self.categories[found]['name'])
        self.update_dialog_codes_and_categories()

    def rename_category_or_code(self, selected):
        """ Rename a code or category.
        Check that the code or category name is not currently in use.
        param:
            selected : QTreeWidgetItem """

        if selected.text(1)[0:3] == 'cid':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename code"),
                                                          _("New code name:"), QtWidgets.QLineEdit.EchoMode.Normal,
                                                          selected.text(0))
            if not ok or new_name == '':
                return
            # Check that no other code has this name
            for c in self.codes:
                if c['name'] == new_name:
                    Message(self.app, _("Name in use"),
                            new_name + _(" is already in use, choose another name."), "warning").exec()
                    return
            # Find the code in the list
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            # Rename in recent codes
            for item in self.recent_codes:
                if item['name'] == self.codes[found]['name']:
                    item['name'] = new_name
                    break
            # Update codes list and database
            cur = self.app.conn.cursor()
            cur.execute("update code_name set name=? where cid=?", (new_name, self.codes[found]['cid']))
            self.app.conn.commit()
            self.app.delete_backup = False
            old_name = self.codes[found]['name']
            self.parent_textEdit.append(_("Code renamed from: ") + old_name + _(" to: ") + new_name)
            self.update_dialog_codes_and_categories()
            return

        if selected.text(1)[0:3] == 'cat':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename category"), _("New category name:"),
                                                          QtWidgets.QLineEdit.EchoMode.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # Check that no other category has this name
            for c in self.categories:
                if c['name'] == new_name:
                    msg = _("This code name is already in use.")
                    Message(self.app, _("Duplicate code name"), msg, "warning").exec()
                    return
            # Find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            # Update category list and database
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set name=? where catid=?",
                        (new_name, self.categories[found]['catid']))
            self.app.conn.commit()
            self.app.delete_backup = False
            old_name = self.categories[found]['name']
            self.update_dialog_codes_and_categories()
            self.parent_textEdit.append(_("Category renamed from: ") + old_name + _(" to: ") + new_name)

    def change_code_color(self, selected):
        """ Change the colour of the currently selected code.
        param:
            selected : QTreeWidgetItem """

        cid = int(selected.text(1)[4:])
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == cid:
                found = i
        if found == -1:
            return
        ui = DialogColorSelect(self.app, self.codes[found])
        ok = ui.exec()
        if not ok:
            return
        new_color = ui.get_color()
        if new_color is None:
            return
        selected.setBackground(0, QBrush(QColor(new_color), Qt.BrushStyle.SolidPattern))
        # Update codes list, database and color markings
        self.codes[found]['color'] = new_color
        cur = self.app.conn.cursor()
        cur.execute("update code_name set color=? where cid=?",
                    (self.codes[found]['color'], self.codes[found]['cid']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.update_dialog_codes_and_categories()

    def viewfile_menu(self, position):
        """ Context menu for listWidget files to get to the next file and
        to go to the file with the latest codings by this coder.
        Each file dictionary item in self.filenames contains:
        {'id', 'name', 'memo', 'characters'= number of characters in the file,
        'start' = showing characters from this position, 'end' = showing characters to this position}

        param:
            position : """

        selected = self.ui.listWidget.currentItem()
        file_ = None
        for f in self.filenames:
            if selected.text() == f['name']:
                file_ = f

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_next = None
        action_latest = None
        action_next_chars = None
        action_prev_chars = None
        if len(self.filenames) > 1:
            action_next = menu.addAction(_("Next file"))
            action_latest = menu.addAction(_("File with latest coding"))
        if file_['characters'] > CHAR_LIMIT:
            action_next_chars = menu.addAction(str(CHAR_LIMIT) + _(" next  characters"))
            if file_['start'] > 0:
                action_prev_chars = menu.addAction(str(CHAR_LIMIT) + _(" previous  characters"))
        action_go_to_bookmark = menu.addAction(_("Go to bookmark"))
        action = menu.exec(self.ui.listWidget.mapToGlobal(position))
        if action is None:
            return
        if action == action_next:
            self.go_to_next_file()
        if action == action_latest:
            self.go_to_latest_coded_file()
        if action == action_go_to_bookmark:
            self.go_to_bookmark()
        if action == action_next_chars:
            self.next_chars(file_, selected)
        if action == action_prev_chars:
            self.prev_chars(file_, selected)

    def prev_chars(self, file_, selected):
        """ Load previous CHAR_LIMIT chunk of the text file.
        params:
            file_  : selected file, Dictionary
            selected:  list widget item """

        # Already at start
        if file_['start'] == 0:
            return
        file_['end'] = file_['start']
        file_['start'] = file_['start'] - CHAR_LIMIT
        # Forward track to the first line ending for a better start of text chunk
        line_ending = False
        i = 0
        while file_['start'] + i < file_['end'] and not line_ending:
            if file_['fulltext'][file_['start'] + i] == "\n":
                line_ending = True
            else:
                i += 1
        file_['start'] += i
        # Check displayed text not going before start of characters
        if file_['start'] < 0:
            file_['start'] = 0
        # Update tooltip for listItem
        tt = selected.toolTip()
        tt2 = tt.split("From: ")[0]
        tt2 += "\n" + _("From: ") + str(file_['start']) + _(" to ") + str(file_['end'])
        selected.setToolTip(tt2)
        # Load file section into textEdit
        self.load_file(file_)

    def next_chars(self, file_, selected):
        """ Load next CHAR_LIMIT chunk of the text file.
        params:
            file_  : selected file, Dictionary
            selected:  list widget item """

        # First time
        if file_['start'] == 0 and file_['end'] == file_['characters']:
            # Backtrack to the first line ending for a better end of text chunk
            i = CHAR_LIMIT
            line_ending = False
            while i > 0 and not line_ending:
                if file_['fulltext'][i] == "\n":
                    line_ending = True
                else:
                    i -= 1
            if i <= 0:
                file_['end'] = CHAR_LIMIT
            else:
                file_['end'] = i
        else:
            file_['start'] = file_['start'] + CHAR_LIMIT
            # Backtrack from start to next line ending for a better start of text chunk
            line_ending = False
            while file_['start'] > 0 and not line_ending:
                if file_['fulltext'][file_['start']] == "\n":
                    line_ending = True
                else:
                    file_['start'] -= 1
            # Backtrack from end to next line ending for a better end of text chunk
            i = CHAR_LIMIT
            if file_['start'] + i >= file_['characters']:
                i = file_['characters'] - file_['start'] - 1  # To prevent Index out of range error
            line_ending = False
            while i > 0 and not line_ending:
                if file_['fulltext'][file_['start'] + i] == "\n":
                    line_ending = True
                else:
                    i -= 1
            file_['end'] = file_['start'] + i
            # Check displayed text going past end of characters
            if file_['end'] >= file_['characters']:
                file_['end'] = file_['characters'] - 1

        # Update tooltip for listItem
        tt = selected.toolTip()
        tt2 = tt.split("From: ")[0]
        tt2 += "\n" + _("From: ") + str(file_['start']) + _(" to ") + str(file_['end'])
        selected.setToolTip(tt2)
        # Load file section into textEdit
        self.load_file(file_)

    def go_to_next_file(self):
        """ Go to next file in list. Button. """

        if self.file_ is None:
            self.load_file(self.filenames[0])
            self.ui.listWidget.setCurrentRow(0)
            return
        for i in range(0, len(self.filenames) - 1):
            if self.file_ == self.filenames[i]:
                found = self.filenames[i + 1]
                self.ui.listWidget.setCurrentRow(i + 1)
                self.load_file(found)
                self.search_term = ""
                return

    def go_to_latest_coded_file(self):
        """ Go and open file with the latest coding. Button. """

        sql = "SELECT fid FROM code_text where owner=? order by date desc limit 1"
        cur = self.app.conn.cursor()
        cur.execute(sql, [self.app.settings['codername'], ])
        result = cur.fetchone()
        if result is None:
            return
        for i, f in enumerate(self.filenames):
            if f['id'] == result[0]:
                self.ui.listWidget.setCurrentRow(i)
                self.load_file(f)
                self.search_term = ""
                break

    def go_to_bookmark(self):
        """ Find bookmark, open the file and highlight the bookmarked character.
        Adjust for start of text file, as this may be a smaller portion of the full text file.

        The currently loaded text portion may not contain the bookmark.
        Solution - reset the file start and end marks to the entire file length and
        load the entire text file.
        """

        cur = self.app.conn.cursor()
        cur.execute("select bookmarkfile, bookmarkpos from project")
        result = cur.fetchone()
        for i, f in enumerate(self.filenames):
            if f['id'] == result[0]:
                f['start'] = 0
                if f['end'] != f['characters']:
                    msg = _("Entire text file will be loaded")
                    Message(self.app, _('Information'), msg).exec()
                f['end'] = f['characters']
                try:
                    self.ui.listWidget.setCurrentRow(i)
                    self.load_file(f)
                    self.search_term = ""
                    # Set text cursor position and also highlight one character, to show location.
                    text_cursor = self.ui.textEdit.textCursor()
                    text_cursor.setPosition(result[1])
                    endpos = result[1] - 1
                    if endpos < 0:
                        endpos = 0
                    text_cursor.setPosition(endpos, QtGui.QTextCursor.MoveMode.KeepAnchor)
                    self.ui.textEdit.setTextCursor(text_cursor)
                except Exception as e:
                    logger.debug(str(e))
                break

    def listwidgetitem_view_file(self):
        """ When listwidget item is pressed load the file.
        The selected file is then displayed for coding.
        Note: file segment is also loaded from listWidget context menu """

        if len(self.filenames) == 0:
            return
        itemname = self.ui.listWidget.currentItem().text()
        for f in self.filenames:
            if f['name'] == itemname:
                self.file_ = f
                self.load_file(self.file_)
                self.search_term = ""
                break

    def load_file(self, file_):
        """ Load and display file text for this file.
        Set the file as a selected item in the list widget. (due to the search text function searching across files).
        Get and display coding highlights.

        Called from:
            view_file_dialog, context_menu
        param: file_ : dictionary of name, id, memo, characters, start, end, fulltext
        """

        for x in range(self.ui.listWidget.count()):
            if self.ui.listWidget.item(x).text() == file_['name']:
                self.ui.listWidget.item(x).setSelected(True)

        self.file_ = file_
        if "start" not in self.file_:
            self.file_['start'] = 0
        sql_values = []
        file_result = self.app.get_file_texts([file_['id']])[0]
        if "end" not in self.file_:
            self.file_['end'] = len(file_result['fulltext'])
        sql_values.append(int(file_result['id']))
        self.text = file_result['fulltext'][self.file_['start']:self.file_['end']]
        self.ui.textEdit.setPlainText(self.text)
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.show_all_codes_in_text()  # Deactivates the show_selected_code if this is active
        self.setWindowTitle(_("Code text: ") + self.file_['name'])
        self.ui.lineEdit_search.setEnabled(True)
        self.ui.checkBox_search_case.setEnabled(True)
        self.ui.checkBox_search_all_files.setEnabled(True)
        self.ui.lineEdit_search.setText("")
        self.ui.label_search_totals.setText("0 / 0")

    def get_coded_text_update_eventfilter_tooltips(self):
        """ Called by load_file, and from other dialogs on update.
        Tooltips are for all coded_text or only for important if important is flagged.
        """

        if self.file_ is None:
            return
        sql_values = [int(self.file_['id']), self.app.settings['codername'], self.file_['start'], self.file_['end']]
        # Get code text for this file and for this coder
        self.code_text = []
        # seltext length, longest first, so overlapping shorter text is superimposed.
        sql = "select code_text.ctid, code_text.cid, fid, seltext, pos0, pos1, code_text.owner, code_text.date, " \
              "code_text.memo, important, name"
        sql += " from code_text join code_name on code_text.cid = code_name.cid"
        sql += " where fid=? and code_text.owner=? "
        # For file text which is currently loaded
        sql += " and pos0 >=? and pos1 <=? "
        sql += "order by length(seltext) desc, important asc"
        cur = self.app.conn.cursor()
        cur.execute(sql, sql_values)
        code_results = cur.fetchall()
        keys = 'ctid', 'cid', 'fid', 'seltext', 'pos0', 'pos1', 'owner', 'date', 'memo', 'important', 'name'
        for row in code_results:
            self.code_text.append(dict(zip(keys, row)))
        # Update filter for tooltip and redo formatting
        if self.important:
            imp_coded = []
            for c in self.code_text:
                if c['important'] == 1:
                    imp_coded.append(c)
            self.eventFilterTT.set_codes_and_annotations(imp_coded, self.codes, self.annotations, self.file_['start'])
        else:
            self.eventFilterTT.set_codes_and_annotations(self.code_text, self.codes, self.annotations,
                                                         self.file_['start'])
        self.unlight()
        self.highlight()

    def unlight(self):
        """ Remove all text highlighting from current file. """

        if self.text is None:
            return
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(len(self.text) - 1, QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())

    def highlight(self):
        """ Apply text highlighting to current file.
        If no colour has been assigned to a code, those coded text fragments are coloured gray.
        Each code text item contains: fid, date, pos0, pos1, seltext, cid, status, memo,
        name, owner.
        For defined colours in color_selector, make text light on dark, and conversely dark on light
        """

        if self.file_ is None:
            return
        if self.text is not None:
            # Add coding highlights
            codes = {x['cid']: x for x in self.codes}
            for item in self.code_text:
                fmt = QtGui.QTextCharFormat()
                cursor = self.ui.textEdit.textCursor()
                cursor.setPosition(int(item['pos0'] - self.file_['start']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['pos1'] - self.file_['start']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                color = codes.get(item['cid'], {}).get('color', "#777777")  # default gray
                brush = QBrush(QColor(color))
                fmt.setBackground(brush)
                # Foreground depends on the defined need_white_text color in color_selector
                text_brush = QBrush(QColor(TextColor(color).recommendation))
                fmt.setForeground(text_brush)
                # Highlight codes with memos - these are italicised
                # Italics also used for overlapping codes
                if item['memo'] is not None and item['memo'] != "":
                    fmt.setFontItalic(True)
                else:
                    fmt.setFontItalic(False)
                # Bold important codes
                if item['important']:
                    fmt.setFontWeight(QtGui.QFont.Weight.Bold)
                # Use important flag for ONLY showing important codes (button selected)
                if self.important and item['important'] == 1:
                    cursor.setCharFormat(fmt)
                # Show all codes, as important button not selected
                if not self.important:
                    cursor.setCharFormat(fmt)

            # Add annotation marks - these are in bold, important codings are also bold
            for note in self.annotations:
                if len(self.file_.keys()) > 0:  # will be zero if using autocode and no file is loaded
                    # Cursor pos could be negative if annotation was for an earlier text portion
                    cursor = self.ui.textEdit.textCursor()
                    if note['fid'] == self.file_['id'] and \
                            int(note['pos0']) - self.file_['start'] >= 0 and \
                            int(note['pos1']) - self.file_['start'] > 0 and \
                            int(note['pos1']) - self.file_['start'] <= len(self.ui.textEdit.toPlainText()):
                        cursor.setPosition(int(note['pos0']) - self.file_['start'], QtGui.QTextCursor.MoveMode.MoveAnchor)
                        cursor.setPosition(int(note['pos1']) - self.file_['start'], QtGui.QTextCursor.MoveMode.KeepAnchor)
                        format_bold = QtGui.QTextCharFormat()
                        format_bold.setFontWeight(QtGui.QFont.Weight.Bold)
                        cursor.mergeCharFormat(format_bold)
        self.apply_underline_to_overlaps()

    def apply_underline_to_overlaps(self):
        """ Apply underline format to coded text sections which are overlapping.
        Qt underline options: # NoUnderline, SingleUnderline, DashUnderline, DotLine, DashDotLine, WaveUnderline
        Adjust for start of text file, as this may be a smaller portion of the full text file.
        """

        if self.important:
            return
        overlaps = []
        for i in self.code_text:
            for j in self.code_text:
                if j != i:
                    if j['pos0'] <= i['pos0'] and j['pos1'] >= i['pos0']:
                        if j['pos0'] >= i['pos0'] and j['pos1'] <= i['pos1']:
                            overlaps.append([j['pos0'], j['pos1']])
                        elif i['pos0'] >= j['pos0'] and i['pos1'] <= j['pos1']:
                            overlaps.append([i['pos0'], i['pos1']])
                        elif j['pos0'] > i['pos0']:
                            overlaps.append([j['pos0'], i['pos1']])
                        else:  # j['pos0'] < i['pos0']:
                            overlaps.append([j['pos1'], i['pos0']])
        cursor = self.ui.textEdit.textCursor()
        for o in overlaps:
            fmt = QtGui.QTextCharFormat()
            fmt.setUnderlineStyle(QtGui.QTextCharFormat.UnderlineStyle.SingleUnderline)
            if self.app.settings['stylesheet'] == 'dark':
                fmt.setUnderlineColor(QColor("#000000"))
            else:
                fmt.setUnderlineColor(QColor("#FFFFFF"))
            cursor.setPosition(o[0] - self.file_['start'], QtGui.QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(o[1] - self.file_['start'], QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(fmt)

    def select_tree_item_by_code_name(self, codename):
        """ Set a tree item code. This still call fill_code_label and
         put the selected code in the top left code label and
         underline matching text in the textedit.
         param:
            codename: a string of the codename
         """

        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        while item:
            if item.text(0) == codename:
                self.ui.treeWidget.setCurrentItem(item)
            it += 1
            item = it.value()
        self.fill_code_label_undo_show_selected_code()

    def mark(self):
        """ Mark selected text in file with currently selected code.
       Need to check for multiple same codes at same pos0 and pos1.
       Update recent_codes list.
       Adjust for start of text file, as this may be a smaller portion of the full text file.
       """

        if self.file_ is None:
            Message(self.app, _('Warning'), _("No file was selected"), "warning").exec()
            return
        item = self.ui.treeWidget.currentItem()
        if item is None:
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        if item.text(1).split(':')[0] == 'catid':  # must be a code
            return
        cid = int(item.text(1).split(':')[1])
        selected_text = self.ui.textEdit.textCursor().selectedText()
        pos0 = self.ui.textEdit.textCursor().selectionStart() + self.file_['start']
        pos1 = self.ui.textEdit.textCursor().selectionEnd() + self.file_['start']
        if pos0 == pos1:
            return
        # Add the coded section to code text, add to database and update GUI
        coded = {'cid': cid, 'fid': int(self.file_['id']), 'seltext': selected_text,
                 'pos0': pos0, 'pos1': pos1, 'owner': self.app.settings['codername'], 'memo': "",
                 'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                 'important': None}

        # Check for an existing duplicated marking first
        cur = self.app.conn.cursor()
        cur.execute("select * from code_text where cid = ? and fid=? and pos0=? and pos1=? and owner=?",
                    (coded['cid'], coded['fid'], coded['pos0'], coded['pos1'], coded['owner']))
        result = cur.fetchall()
        if len(result) > 0:
            # The event can trigger multiple times, so dont present a warning to the user
            return
        self.code_text.append(coded)
        self.highlight()
        cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
            memo,date, important) values(?,?,?,?,?,?,?,?,?)", (coded['cid'], coded['fid'],
                                                               coded['seltext'], coded['pos0'], coded['pos1'],
                                                               coded['owner'],
                                                               coded['memo'], coded['date'], coded['important']))
        self.app.conn.commit()
        self.app.delete_backup = False
        # Update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        # Update recent_codes
        tmp_code = None
        for c in self.codes:
            if c['cid'] == cid:
                tmp_code = c
        if tmp_code is None:
            return
        # Need to remove from recent_codes, if there and add back in first position
        for item in self.recent_codes:
            if item == tmp_code:
                self.recent_codes.remove(item)
                break
        self.recent_codes.insert(0, tmp_code)
        if len(self.recent_codes) > 10:
            self.recent_codes = self.recent_codes[:10]
        self.update_file_tooltip()

    def undo_last_unmarked_code(self):
        """ Restore the last deleted code(s).
        One code or multiple, depends on what was selected when the unmark method was used.
        Requires self.undo_deleted_codes """

        if not self.undo_deleted_codes:
            return
        cur = self.app.conn.cursor()
        for item in self.undo_deleted_codes:
            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
                memo,date, important) values(?,?,?,?,?,?,?,?,?)", (item['cid'], item['fid'],
                                                                   item['seltext'], item['pos0'], item['pos1'],
                                                                   item['owner'],
                                                                   item['memo'], item['date'], item['important']))
        self.app.conn.commit()
        self.undo_deleted_codes = []
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    def unmark(self, location):
        """ Remove code marking by this coder from selected text in current file.
        Called by text_edit_context_menu
        Adjust for start of text file, as this may be a smaller portion of the full text file.

        param:
            location: text cursor location, Integer
        """

        if self.file_ is None:
            return
        unmarked_list = []
        for item in self.code_text:
            if location + self.file_['start'] >= item['pos0'] and location + self.file_['start'] <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                unmarked_list.append(item)
        if not unmarked_list:
            return
        to_unmark = []
        if len(unmarked_list) == 1:
            to_unmark = [unmarked_list[0]]
        # Multiple codes to select from
        if len(unmarked_list) > 1:
            ui = DialogSelectItems(self.app, unmarked_list, _("Select code to unmark"), "multi")
            ok = ui.exec()
            if not ok:
                return
            to_unmark = ui.get_selected()
        if to_unmark is None:
            return
        self.undo_deleted_codes = deepcopy(to_unmark)
        # Delete from db, remove from coding and update highlights
        cur = self.app.conn.cursor()
        for item in to_unmark:
            cur.execute("delete from code_text where cid=? and pos0=? and pos1=? and owner=? and fid=?",
                        (item['cid'], item['pos0'], item['pos1'], self.app.settings['codername'], item['fid']))
            self.app.conn.commit()
        # Update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.update_file_tooltip()
        self.app.delete_backup = False

    def annotate(self, cursor_pos=None):
        """ Add view, or remove an annotation for selected text.
        Annotation positions are displayed as bold text.
        Adjust for start of text file, as this may be a smaller portion of the full text file.

        Called via context menu, button
        """

        if self.file_ is None:
            Message(self.app, _('Warning'), _("No file was selected"), "warning").exec()
            return
        pos0 = self.ui.textEdit.textCursor().selectionStart()
        pos1 = self.ui.textEdit.textCursor().selectionEnd()
        text_length = len(self.ui.textEdit.toPlainText())
        if pos0 >= text_length or pos1 > text_length:
            return
        item = None
        details = ""
        annotation = ""
        # Find annotation at this position for this file
        if cursor_pos is None:
            for note in self.annotations:
                if ((pos0 + self.file_['start'] >= note['pos0'] and pos0 + self.file_['start'] <= note['pos1']) or
                    (pos1 + self.file_['start'] >= note['pos0'] and pos1 + self.file_['start'] <= note['pos1'])) \
                        and note['fid'] == self.file_['id']:
                    item = note  # use existing annotation
                    details = item['owner'] + " " + item['date']
                    break
        if cursor_pos is not None:  # Try point position, if cursor is on an annotation, but no text selected
            for note in self.annotations:
                if cursor_pos + self.file_['start'] >= note['pos0'] and cursor_pos <= note['pos1'] + self.file_['start'] \
                        and note['fid'] == self.file_['id']:
                    item = note  # use existing annotation
                    details = item['owner'] + " " + item['date']
                    pos0 = cursor_pos
                    pos1 = cursor_pos
                    break
        # Exit this method if no text selected and there is no annotation at this position
        if pos0 == pos1 and item is None:
            return

        # Add new item to annotations, add to database and update GUI
        if item is None:
            item = {'fid': int(self.file_['id']), 'pos0': pos0 + self.file_['start'],
                    'pos1': pos1 + self.file_['start'],
                    'memo': str(annotation), 'owner': self.app.settings['codername'],
                    'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'anid': -1}
            ui = DialogMemo(self.app, _("Annotation: ") + details, item['memo'])
            ui.exec()
            item['memo'] = ui.memo
            if item['memo'] != "":
                cur = self.app.conn.cursor()
                cur.execute("insert into annotation (fid,pos0, pos1,memo,owner,date) \
                    values(?,?,?,?,?,?)", (item['fid'], item['pos0'], item['pos1'],
                                           item['memo'], item['owner'], item['date']))
                self.app.conn.commit()
                self.app.delete_backup = False
                cur.execute("select last_insert_rowid()")
                anid = cur.fetchone()[0]
                item['anid'] = anid
                self.annotations.append(item)
                self.parent_textEdit.append(_("Annotation added at position: ") \
                                            + str(item['pos0']) + "-" + str(item['pos1']) + _(" for: ") + self.file_[
                                                'name'])
                self.get_coded_text_update_eventfilter_tooltips()
            return

        # Edit existing annotation
        ui = DialogMemo(self.app, _("Annotation: ") + details, item['memo'])
        ui.exec()
        item['memo'] = ui.memo
        if item['memo'] != "":
            item['date'] = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            cur = self.app.conn.cursor()
            sql = "update annotation set memo=?, date=? where anid=?"
            cur.execute(sql, (item['memo'], item['date'], item['anid']))
            self.app.conn.commit()
            self.app.delete_backup = False

            self.annotations = self.app.get_annotations()
            self.get_coded_text_update_eventfilter_tooltips()
            return

        # If blank delete the annotation
        if item['memo'] == "":
            cur = self.app.conn.cursor()
            cur.execute("delete from annotation where pos0 = ?", (item['pos0'],))
            self.app.conn.commit()
            self.app.delete_backup = False
            self.annotations = self.app.get_annotations()
            self.parent_textEdit.append(_("Annotation removed from position ")
                                        + str(item['pos0']) + _(" for: ") + self.file_['name'])
        self.get_coded_text_update_eventfilter_tooltips()

    def button_autocode_sentences_this_file(self):
        """ Flag to autocode sentences in one file """

        self.code_sentences("")

    def button_autocode_sentences_all_files(self):
        """ Flag to autocode sentences across all text files. """

        self.code_sentences("all")

    def button_autocode_surround(self):
        """ Autocode with selected code using start and end marks.
         Currently, only using the current selected file.
         Line ending text representation \\n is replaced with the actual line ending character. """

        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1)[0:3] == 'cat':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        if self.file_ is None:
            Message(self.app, _('Warning'), _("No file was selected"), "warning").exec()
            return
        ui = DialogGetStartAndEndMarks(self.file_['name'], self.file_['name'])
        ok = ui.exec()
        if not ok:
            return
        start_mark = ui.get_start_mark()
        if "\\n" in start_mark:
            start_mark = start_mark.replace("\\n", "\n")
        end_mark = ui.get_end_mark()
        if "\\n" in end_mark:
            end_mark = end_mark.replace("\\n", "\n")
        if start_mark == "" or end_mark == "":
            Message(self.app, _('Warning'), _("Cannot have blank text marks"), "warning").exec()
            return

        msg = _("Code text using start and end marks: ") + self.file_['name']
        msg += _("\nUsing ") + start_mark + _(" and ") + end_mark + "\n"

        text_starts = [match.start() for match in re.finditer(re.escape(start_mark), self.file_['fulltext'])]
        text_ends = [match.start() for match in re.finditer(re.escape(end_mark), self.file_['fulltext'])]
        # Find and insert into database
        already_assigned = 0
        cid = int(item.text(1)[4:])
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        entries = 0
        undo_list = []
        cur = self.app.conn.cursor()
        for start_pos in text_starts:
            pos1 = -1  # Default if not found
            text_end_iterator = 0
            try:
                while start_pos >= text_ends[text_end_iterator]:
                    text_end_iterator += 1
            except IndexError:
                text_end_iterator = -1
            if text_end_iterator >= 0:
                pos1 = text_ends[text_end_iterator]
                # Check if already coded in this file for this coder
                sql = "select cid from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?"
                cur.execute(sql, [cid, self.file_['id'], start_pos, pos1, self.app.settings['codername']])
                res = cur.fetchone()
                if res is None:
                    seltext = self.file_['fulltext'][start_pos: pos1]
                    sql = "insert into code_text (cid, fid, seltext, pos0, pos1, owner, date, memo) values(?,?,?,?,?,?,?,?)"
                    cur.execute(sql, (cid, self.file_['id'], seltext, start_pos, pos1,
                                      self.app.settings['codername'], now_date, ""))
                    # Add to undo auto-coding history
                    undo = {"sql": "delete from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                            "cid": cid, "fid": self.file_['id'], "pos0": start_pos, "pos1": pos1,
                            "owner": self.app.settings['codername']
                            }
                    undo_list.append(undo)
                    entries += 1
                    self.app.conn.commit()
                else:
                    already_assigned += 1
        # Add to undo auto-coding history
        if len(undo_list) > 0:
            name = _("Coding using start and end marks") + _("\nCode: ") + item.text(0)
            name += _("\nWith start mark: ") + start_mark + _("\nEnd mark: ") + end_mark
            undo_dict = {"name": name, "sql_list": undo_list}
            self.autocode_history.insert(0, undo_dict)
        # Update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        msg += str(entries) + _(" new coded sections found.") + "\n"
        if already_assigned > 0:
            msg += str(already_assigned) + " " + _("previously coded.") + "\n"
        self.parent_textEdit.append(msg)
        self.app.delete_backup = False

    def undo_autocoding(self):
        """ Present a list of choices for the undo operation.
         Use selects and undoes the chosen autocoding operation.
         The autocode_history is a list of dictionaries with 'name' and 'sql_list' """

        if not self.autocode_history:
            return
        ui = DialogSelectItems(self.app, self.autocode_history, _("Select auto-codings to undo"), "single")
        ok = ui.exec()
        if not ok:
            return
        undo = ui.get_selected()
        self.autocode_history.remove(undo)

        # Run all sqls
        cur = self.app.conn.cursor()
        for i in undo['sql_list']:
            cur.execute(i['sql'], [i['cid'], i['fid'], i['pos0'], i['pos1'], i['owner']])
        self.app.conn.commit()
        self.parent_textEdit.append(_("Undo autocoding: " + undo['name'] + "\n"))

        # Update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    def code_sentences(self, all_=""):
        """ Code full sentence based on text fragment.

        param:
            all = "" :  for this text file only.
            all = "all" :  for all text files.
        """

        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1)[0:3] == 'cat':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        cid = int(item.text(1).split(':')[1])
        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Code sentence"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setLabelText(_("Auto code sentence using this text fragment:"))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        text_ = dialog.textValue()
        if text_ == "":
            return
        dialog2 = QtWidgets.QInputDialog(None)
        dialog2.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog2.setWindowTitle(_("Code sentence"))
        dialog2.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog2.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog2.setToolTip("Use \\n for line ending")
        dialog2.setLabelText(_("Define sentence ending. Default is period space.\nUse \\n for line ending:"))
        dialog2.setTextValue(". ")
        dialog2.resize(200, 40)
        ok2 = dialog2.exec()
        if not ok2:
            return
        ending = dialog2.textValue()
        if ending == "":
            return
        ending = ending.replace("\\n", "\n")
        files = []
        if all_ == "all":
            files = self.app.get_file_texts()
        else:
            files = self.app.get_file_texts([self.file_['id'], ])
        cur = self.app.conn.cursor()
        msg = ""
        undo_list = []
        for f in files:
            sentences = f['fulltext'].split(ending)
            pos0 = 0
            codes_added = 0
            for sentence in sentences:
                if text_ in sentence:
                    i = {'cid': cid, 'fid': int(f['id']), 'seltext': str(sentence),
                         'pos0': pos0, 'pos1': pos0 + len(sentence),
                         'owner': self.app.settings['codername'], 'memo': "",
                         'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
                    # Possible IntegrityError: UNIQUE constraint failed
                    try:
                        codes_added += 1
                        cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,\
                            owner,memo,date) values(?,?,?,?,?,?,?,?)",
                                    (i['cid'], i['fid'], i['seltext'], i['pos0'],
                                     i['pos1'], i['owner'], i['memo'], i['date']))
                        self.app.conn.commit()
                        # Record a list of undo sql
                        undo = {"sql": "delete from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                                "cid": i['cid'], "fid": i['fid'], "pos0": i['pos0'], "pos1": i['pos1'],
                                "owner": i['owner']
                                }
                        undo_list.append(undo)
                    except Exception as e:
                        print("Autocode insert error ", str(e))
                        logger.debug(_("Autocode insert error ") + str(e))
                pos0 += len(sentence) + len(ending)
            if codes_added > 0:
                msg += _("File: ") + f['name'] + " " + str(codes_added) + _(" added codes") + "\n"
        if len(undo_list) > 0:
            name = _("Sentence coding: ") + _("\nCode: ") + item.text(0)
            name += _("\nWith: ") + text_ + _("\nUsing line ending: ") + ending
            undo_dict = {"name": name, "sql_list": undo_list}
            self.autocode_history.insert(0, undo_dict)
        self.parent_textEdit.append(_("Automatic code sentence in files:") \
                                    + _("\nCode: ") + item.text(0)
                                    + _("\nWith text fragment: ") 
                                    + text.decode("utf-8") 
                                    + _("\nUsing line ending: ") 
                                    + ending + "\n" + msg)
        self.app.delete_backup = False
        # Update tooltip filter and code tree code counts
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    def auto_code(self):
        """ Autocode text in one file or all files with currently selected code.
        """

        code_item = self.ui.treeWidget.currentItem()
        if code_item is None or code_item.text(1)[0:3] == 'cat':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        cid = int(code_item.text(1).split(':')[1])
        # Input dialog too narrow, so code below
        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Automatic coding"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setToolTip(_("Use | to code multiple texts"))
        dialog.setLabelText(_("Auto code files with the current code for this text:") + "\n" + code_item.text(0))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        find_text = str(dialog.textValue())
        if find_text == "" or find_text is None:
            return
        texts = find_text.split('|')
        tmp = list(set(texts))
        texts = []
        for t in tmp:
            if t != "":
                texts.append(t)
        if len(self.filenames) == 0:
            return
        ui = DialogSelectItems(self.app, self.filenames, _("Select files to code"), "many")
        ok = ui.exec()
        if not ok:
            return
        files = ui.get_selected()
        if len(files) == 0:
            return
        undo_list = []
        cur = self.app.conn.cursor()
        for txt in texts:
            filenames = ""
            for f in files:
                filenames += f['name'] + " "
                cur.execute("select name, id, fulltext, memo, owner, date from source where id=? and mediapath is Null",
                            [f['id']])
                currentfile = cur.fetchone()
                text_ = currentfile[2]
                text_starts = [match.start() for match in re.finditer(re.escape(txt), text_)]
                # Add new items to database
                for startPos in text_starts:
                    item = {'cid': cid, 'fid': int(f['id']), 'seltext': str(txt),
                            'pos0': startPos, 'pos1': startPos + len(txt),
                            'owner': self.app.settings['codername'], 'memo': "",
                            'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
                    # TODO IntegrityError: UNIQUE constraint failed
                    try:
                        cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,\
                            owner,memo,date) values(?,?,?,?,?,?,?,?)",
                                    (item['cid'], item['fid'], item['seltext'], item['pos0'],
                                     item['pos1'], item['owner'], item['memo'], item['date']))
                        self.app.conn.commit()
                        # Record a list of undo sql
                        undo = {"sql": "delete from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                                "cid": item['cid'], "fid": item['fid'], "pos0": item['pos0'], "pos1": item['pos1'],
                                "owner": item['owner']}
                        undo_list.append(undo)
                    except Exception as e:
                        logger.debug(_("Autocode insert error ") + str(e))
                    self.app.delete_backup = False
                self.parent_textEdit.append(_("Automatic coding in files: ") + filenames \
                                            + _(". with text: ") + txt)
        if len(undo_list) > 0:
            name = _("Text coding: ") + _("\nCode: ") + code_item.text(0)
            name += _("\nWith: ") + find_text
            undo_dict = {"name": name, "sql_list": undo_list}
            self.autocode_history.insert(0, undo_dict)
        # Update tooltip filter and code tree code counts
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    # Methods for Editing mode
    def edit_mode_toggle(self):
        """ Activate or deactivate edit mode.
        When activated, hide most widgets, remove tooltips, remove text edit menu.
        Called: event filter Ctrl+E
        The edit mode toggle fires multiple times. so the initial edit_pos changes from the corect pos to 0
        """

        if self.file_ is None:
            return
        self.edit_mode = not self.edit_mode
        if self.edit_mode:
            self.edit_mode_on()
            return
        self.edit_mode_off()

    def edit_mode_on(self):
        """ Hide most widgets, remove tooltips, remove text edit menu.
        Need to load entire file, if only a section is currently loaded. """

        temp_edit_pos = self.ui.textEdit.textCursor().position() + self.file_['start']
        if temp_edit_pos > 0:
            self.edit_pos = temp_edit_pos
        self.ui.groupBox.hide()
        self.ui.groupBox_edit_mode.show()
        self.ui.listWidget.setEnabled(False)
        self.ui.listWidget.hide()
        self.ui.treeWidget.hide()
        self.ui.groupBox_file_buttons.setEnabled(False)
        self.ui.groupBox_file_buttons.setMaximumSize(4000, 4000)
        self.ui.groupBox_coding_buttons.setEnabled(False)
        self.ui.treeWidget.setEnabled(False)
        file_result = self.app.get_file_texts([self.file_['id']])[0]
        if self.file_['end'] != len(file_result['fulltext']) and self.file_['start'] != 0:
            self.file_['start'] = 0
            self.file_['end'] = len(file_result['fulltext'])
            self.text = file_result['fulltext']
            self.ui.textEdit.setText(self.text)
        self.prev_text = copy(self.text)
        self.ui.textEdit.removeEventFilter(self.eventFilterTT)
        self.get_cases_codings_annotations()
        self.ui.textEdit.setReadOnly(False)
        self.ed_highlight()
        self.ui.textEdit.textChanged.connect(self.update_positions)
        text_cursor = self.ui.textEdit.textCursor()
        if self.edit_pos >= len(self.text):
            self.edit_pos = len(self.text) - 1
        text_cursor.setPosition(self.edit_pos, QtGui.QTextCursor.MoveMode.MoveAnchor)
        self.ui.textEdit.setTextCursor(text_cursor)

    def edit_mode_off(self):
        """ Show widgets.
        Try and set cursor positon to 'current text' position.
        but this may have changed a lot. """

        self.ui.groupBox.show()
        self.ui.groupBox_edit_mode.hide()
        self.ui.listWidget.setEnabled(True)
        self.ui.groupBox_file_buttons.setEnabled(True)
        self.ui.groupBox_file_buttons.setMaximumSize(4000, 30)
        self.ui.groupBox_coding_buttons.setEnabled(True)
        self.ui.treeWidget.setEnabled(True)
        self.ui.listWidget.show()
        self.ui.treeWidget.show()
        self.prev_text = ""
        self.text = self.ui.textEdit.toPlainText()
        self.file_['fulltext'] = self.text
        self.file_['end'] = len(self.text)
        cur = self.app.conn.cursor()
        cur.execute("update source set fulltext=? where id=?", (self.text, self.file_['id']))
        self.app.conn.commit()
        for item in self.code_deletions:
            cur.execute(item)
        self.app.conn.commit()
        self.code_deletions = []
        self.ed_update_codings()
        self.ed_update_annotations()
        self.ed_update_casetext()
        self.ui.textEdit.setReadOnly(True)
        self.ui.textEdit.installEventFilter(self.eventFilterTT)
        self.annotations = self.app.get_annotations()
        self.load_file(self.file_)
        self.update_file_tooltip()
        text_cursor = self.ui.textEdit.textCursor()
        if self.edit_pos > len(self.ui.textEdit.toPlainText()):
            self.edit_pos = len(self.ui.textEdit.toPlainText()) - 1
        text_cursor.setPosition(self.edit_pos, QtGui.QTextCursor.MoveMode.MoveAnchor)
        self.ui.textEdit.setTextCursor(text_cursor)

    def update_positions(self):
        """ Update positions for code text, annotations and case text as each character changes
        via adding or deleting.

        Output: adding an e at pos 4:
        ---

        +++

        @@ -4,0 +5 @@

        +e
        """

        # No need to update positions (unless entire file is a case)
        if self.no_codes_annotes_cases or not self.edit_mode:
            return
        self.text = self.ui.textEdit.toPlainText()
        # n is how many context lines to show
        d = list(difflib.unified_diff(self.prev_text, self.text, n=0))
        if len(d) < 4:
            return
        char = d[3]
        position = d[2][4:]  # Removes prefix @@ -
        position = position[:-4]  # Removes suffix space@@\n
        previous = position.split(" ")[0]
        pre_start = int(previous.split(",")[0])
        pre_chars = None
        try:
            pre_chars = previous.split(",")[1]
        except IndexError:
            pass
        post = position.split(" ")[1]
        post_start = int(post.split(",")[0])
        post_chars = None
        try:
            post_chars = post.split(",")[1]
        except IndexError:
            pass
        # No additions or deletions
        if pre_start == post_start and pre_chars == post_chars:
            self.highlight()
            self.prev_text = copy(self.text)
            return

        """
        Adding 'X' at inserted position 5, note: None as no number is provided from difflib
        +X  previous 4 0  post 5 None

        Adding 'qda' at inserted position 5 (After 'This')
        +q  previous 4 0  post 5 3

        Removing 'X' from position 5, note None
        -X  previous 5 None  post 4 0

        Removing 'the' from position 13
        -t  previous 13 3  post 12 0
        """
        if pre_chars is None:
            pre_chars = 1
        pre_chars = -1 * int(pre_chars)  # String if not None
        if post_chars is None:
            post_chars = 1
        post_chars = int(post_chars)  # String if not None
        # print("XXX", char, " previous", pre_start, pre_chars, " post", post_start, post_chars)
        # Adding characters
        if char[0] == "+":
            for c in self.ed_codetext:
                changed = False
                if c['npos0'] is not None and c['npos0'] >= pre_start and c['npos0'] >= pre_start + -1 * pre_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                if not changed and pre_start > c['npos0'] and pre_start < c['npos1']:
                    c['npos1'] += pre_chars + post_chars
            for c in self.ed_annotations:
                changed = False
                if c['npos0'] is not None and c['npos0'] >= pre_start and c['npos0'] >= pre_start + -1 * pre_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                if c['npos0'] is not None and not changed and pre_start > c['npos0'] and pre_start < c['npos1']:
                    c['npos1'] += pre_chars + post_chars
            for c in self.ed_casetext:
                changed = False
                # print("npos0", c['npos0'], "pre start", pre_start)
                if c['npos0'] is not None and c['npos0'] >= pre_start and c['npos0'] >= pre_start + -1 * pre_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                if c['npos0'] is not None and not changed and pre_start > c['npos0'] and pre_start < c['npos1']:
                    c['npos1'] += pre_chars + post_chars
            self.ed_highlight()
            self.prev_text = copy(self.text)
            return

        # Removing characters
        if char[0] == "-":
            for c in self.ed_codetext:
                changed = False
                # print("CODE npos0", c['npos0'], "pre start", pre_start, pre_chars, post_chars)
                if c['npos0'] is not None and c['npos0'] >= pre_start and c['npos0'] >= pre_start + -1 * pre_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                # print(changed, c['npos0'],  pre_start, c['npos1'], pre_chars, post_chars)
                # print(c['npos0'], ">",  pre_start, "and", c['npos1'], "<", pre_start + -1*pre_chars + post_chars)
                if c['npos0'] is not None and not changed and c['npos0'] >= pre_start and \
                        c['npos1'] < pre_start + -1 * pre_chars + post_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                    self.code_deletions.append("delete from code_text where ctid=" + str(c['ctid']))
                    c['npos0'] = None
                if c['npos0'] is not None and not changed and pre_start > c['npos0'] and pre_start <= c['npos1']:
                    c['npos1'] += pre_chars + post_chars
                    if c['npos1'] < c['npos0']:
                        self.code_deletions.append("delete from code_text where ctid=" + str(c['ctid']))
                        c['npos0'] = None
            for c in self.ed_annotations:
                changed = False
                if c['npos0'] is not None and c['npos0'] >= pre_start and c['npos0'] >= pre_start + -1 * pre_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                    # Remove, as entire text is being removed (e.g. copy replace)
                    # print(changed, c['npos0'],  pre_start, c['npos1'], pre_chars, post_chars)
                    # print(c['npos0'], ">",  pre_start, "and", c['npos1'], "<", pre_start + -1*pre_chars + post_chars)
                    if not changed and c['npos0'] >= pre_start and c['npos1'] < pre_start + -1 * pre_chars + post_chars:
                        c['npos0'] += pre_chars + post_chars
                        c['npos1'] += pre_chars + post_chars
                        changed = True
                        self.code_deletions.append("delete from annotations where anid=" + str(c['anid']))
                        c['npos0'] = None
                if c['npos0'] is not None and not changed and pre_start > c['npos0'] and pre_start <= c['npos1']:
                    c['npos1'] += pre_chars + post_chars
                    if c['npos1'] < c['npos0']:
                        self.code_deletions.append("delete from annotation where anid=" + str(c['anid']))
                        c['npos0'] = None
            for c in self.ed_casetext:
                changed = False
                if c['npos0'] is not None and c['npos0'] >= pre_start and c['npos0'] >= pre_start + -1 * pre_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                # print(changed, c['npos0'],  pre_start, c['npos1'], pre_chars, post_chars)
                # print(c['npos0'], ">",  pre_start, "and", c['npos1'], "<", pre_start + -1*pre_chars + post_chars)
                if c['npos0'] is not None and not changed and c['npos0'] >= pre_start and \
                        c['npos1'] < pre_start + -1 * pre_chars + post_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                    self.code_deletions.append("delete from case_text where id=" + str(c['id']))
                    c['npos0'] = None
                if c['npos0'] is not None and not changed and pre_start > c['npos0'] and pre_start <= c['npos1']:
                    c['npos1'] += pre_chars + post_chars
                    if c['npos1'] < c['npos0']:
                        self.code_deletions.append("delete from case_text where id=" + str(c['id']))
                        c['npos0'] = None
        self.ed_highlight()
        self.prev_text = copy(self.text)

    def ed_highlight(self):
        """ Add coding and annotation highlights. """

        self.remove_formatting()
        format_ = QtGui.QTextCharFormat()
        format_.setFontFamily(self.app.settings['font'])
        format_.setFontPointSize(self.app.settings['docfontsize'])
        self.ui.textEdit.blockSignals(True)
        cursor = self.ui.textEdit.textCursor()
        for item in self.ed_casetext:
            if item['npos0'] is not None:
                cursor.setPosition(int(item['npos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['npos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.green)
                cursor.setCharFormat(format_)
        for item in self.ed_annotations:
            if item['npos0'] is not None:
                cursor.setPosition(int(item['npos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['npos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.yellow)
                cursor.setCharFormat(format_)
        for item in self.ed_codetext:
            if item['npos0'] is not None:
                cursor.setPosition(int(item['npos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['npos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.red)
                cursor.setCharFormat(format_)
        self.ui.textEdit.blockSignals(False)

    def remove_formatting(self):
        """ Remove formatting from text edit on changed text.
         Useful when pasting mime data (rich text or html) from clipboard. """

        self.ui.textEdit.blockSignals(True)
        format_ = QtGui.QTextCharFormat()
        format_.setFontFamily(self.app.settings['font'])
        format_.setFontPointSize(self.app.settings['docfontsize'])
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(len(self.ui.textEdit.toPlainText()), QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(format_)
        self.ui.textEdit.blockSignals(False)

    def get_cases_codings_annotations(self):
        """ Get all linked cases, coded text and annotations for this file.
         For editing mode. """

        cur = self.app.conn.cursor()
        sql = "select ctid, cid, pos0, pos1, seltext, owner from code_text where fid=?"
        cur.execute(sql, [self.file_['id']])
        res = cur.fetchall()
        self.ed_codetext = []
        for r in res:
            self.ed_codetext.append({'ctid': r[0], 'cid': r[1], 'pos0': r[2], 'pos1': r[3], 'seltext': r[4],
                                     'owner': r[5], 'npos0': r[2], 'npos1': r[3]})
        sql = "select anid, pos0, pos1 from annotation where fid=?"
        cur.execute(sql, [self.file_['id']])
        res = cur.fetchall()
        self.ed_annotations = []
        for r in res:
            self.ed_annotations.append({'anid': r[0], 'pos0': r[1], 'pos1': r[2],
                                        'npos0': r[1], 'npos1': r[2]})
        sql = "select id, pos0, pos1 from case_text where fid=?"
        cur.execute(sql, [self.file_['id']])
        res = cur.fetchall()
        self.ed_casetext = []
        for r in res:
            self.ed_casetext.append({'id': r[0], 'pos0': r[1], 'pos1': r[2],
                                     'npos0': r[1], 'npos1': r[2]})
        self.no_codes_annotes_cases = False
        if self.ed_casetext == [] and self.ed_annotations == [] and self.ed_codetext == []:
            self.no_codes_annotes_cases = True

    def ed_update_casetext(self):
        """ Update linked case text positions. """

        sql = "update case_text set pos0=?, pos1=? where id=? and (pos0 !=? or pos1 !=?)"
        cur = self.app.conn.cursor()
        for c in self.ed_casetext:
            if c['npos0'] is not None:
                cur.execute(sql, [c['npos0'], c['npos1'], c['id'], c['npos0'], c['npos1']])
            if c['npos1'] >= len(self.text):
                cur.execute("delete from case_text where id=?", [c['id']])
        self.app.conn.commit()

    def ed_update_annotations(self):
        """ Update annotation positions. """

        sql = "update annotation set pos0=?, pos1=? where anid=? and (pos0 !=? or pos1 !=?)"
        cur = self.app.conn.cursor()
        for a in self.ed_annotations:
            if a['npos0'] is not None:
                cur.execute(sql, [a['npos0'], a['npos1'], a['anid'], a['npos0'], a['npos1']])
            if a['npos1'] >= len(self.text):
                cur.execute("delete from annotation where anid=?", [a['anid']])
        self.app.conn.commit()

    def ed_update_codings(self):
        """ Update coding positions and seltext. """

        cur = self.app.conn.cursor()
        sql = "update code_text set pos0=?, pos1=?, seltext=? where ctid=?"
        for c in self.ed_codetext:
            if c['npos0'] is not None:
                seltext = self.text[c['npos0']:c['npos1']]
                cur.execute(sql, [c['npos0'], c['npos1'], seltext, c['ctid']])
            if c['npos1'] >= len(self.text):
                cur.execute("delete from code_text where ctid=?", [c['ctid']])
        self.app.conn.commit()


class ToolTipEventFilter(QtCore.QObject):
    """ Used to add a dynamic tooltip for the textEdit.
    The tool top text is changed according to its position in the text.
    If over a coded section the codename(s) or Annotation note are displayed in the tooltip.
    """

    codes = None
    code_text = None
    annotations = None
    offset = 0

    def set_codes_and_annotations(self, code_text, codes, annotations, offset):
        """ Code_text contains the coded text to be displayed in a tooptip.
        Annotations - a mention is made if current position is annotated

        param:
            code_text: List of dictionaries of the coded text contains: pos0, pos1, seltext, cid, memo
            codes: List of dictionaries contains id, name, color
            annotations: List of dictionaries of
            offset: integer 0 if all the text is loaded, other numbers mean a portion of the text is loaded,
            beginning at the offset
        """

        self.code_text = code_text
        self.codes = codes
        self.annotations = annotations
        self.offset = offset
        for item in self.code_text:
            for c in self.codes:
                if item['cid'] == c['cid']:
                    item['name'] = c['name']
                    item['color'] = c['color']

    def eventFilter(self, receiver, event):
        # QtGui.QToolTip.showText(QtGui.QCursor.pos(), tip)
        if event.type() == QtCore.QEvent.Type.ToolTip:
            cursor = receiver.cursorForPosition(event.pos())
            pos = cursor.position()
            receiver.setToolTip("")
            text_ = ""
            multiple_msg = '<p style="color:#f89407">' + _("Press O to cycle overlapping codes") + "</p>"
            multiple = 0
            # Occasional None type error
            if self.code_text is None:
                # Call Base Class Method to Continue Normal Event Processing
                return super(ToolTipEventFilter, self).eventFilter(receiver, event)
            for item in self.code_text:
                if item['pos0'] - self.offset <= pos and item['pos1'] - self.offset >= pos and \
                        item['seltext'] is not None:
                    seltext = item['seltext']
                    seltext = seltext.replace("\n", "")
                    seltext = seltext.replace("\r", "")
                    # Selected text with a readable cut off, not cut off halfway through a word.
                    if len(seltext) > 90:
                        pre = seltext[0:40].split(' ')
                        post = seltext[len(seltext) - 40:].split(' ')
                        try:
                            pre = pre[:-1]
                        except IndexError:
                            pass
                        try:
                            post = post[1:]
                        except IndexError:
                            pass
                        seltext = " ".join(pre) + " ... " + " ".join(post)
                    try:
                        color = TextColor(item['color']).recommendation
                        text_ += '<p style="background-color:' + item['color'] + "; color:" + color + '"><em>'
                        text_ += item['name'] + "</em><br />" + seltext
                        if item['memo'] is not None and item['memo'] != "":
                            text_ += "<br /><em>" + _("Memo: ") + item['memo'] + "</em>"
                        if item['important'] == 1:
                            text_ += "<br /><em>IMPORTANT</em>"
                        text_ += "</p>"
                        multiple += 1
                    except Exception as e:
                        msg = "Codes ToolTipEventFilter Exception\n" + str(e) + ". Possible key error: \n"
                        msg += str(item)
                        logger.error(msg)
            if multiple > 1:
                text_ = multiple_msg + text_
            # Check annotations
            for item in self.annotations:
                if item['pos0'] - self.offset <= pos and item['pos1'] - self.offset >= pos:
                    text_ += "<p>" + _("ANNOTATED") + "</p>"
            if text_ != "":
                receiver.setToolTip(text_)
        # Call Base Class Method to Continue Normal Event Processing
        return super(ToolTipEventFilter, self).eventFilter(receiver, event)
