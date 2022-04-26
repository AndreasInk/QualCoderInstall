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
https://qualcoder.wordpress.com/
"""

from copy import copy, deepcopy
import csv
import logging
import os
from PIL import Image
from shutil import copyfile
import sys
import traceback

from PyQt6 import QtGui, QtWidgets, QtCore
from PyQt6.QtGui import QHelpEvent
from PyQt6.QtCore import Qt  #, QTextCodec
from PyQt6.QtGui import QBrush

from .color_selector import TextColor
from .GUI.base64_helper import *
from .GUI.ui_dialog_report_codings import Ui_Dialog_reportCodings
from .helpers import Message, msecs_to_hours_mins_secs, DialogCodeInImage, DialogCodeInAV, DialogCodeInText, \
    ExportDirectoryPathDialog
from .report_attributes import DialogSelectAttributeParameters
import qualcoder.vlc as vlc

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text_ = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text_)
    logger.error(_("Uncaught exception: ") + text_)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text_)


class DialogReportCodes(QtWidgets.QDialog):
    """ Get reports on coded text/images/audio/video using a range of variables:
        Files, Cases, Coders, text limiters, Attribute limiters.
        Export reports as plain text, ODT, html or csv.

        Text context of a coded text portion is shown in the thord splitter pan in a text edit.
        Case matrix is also shown in a qtablewidget in the third splitter pane.
        If a case matrix is displayed, the text-in-context method overrides it and replaces the matrix with the
        text in context.
        TODO - export case matrix
    """

    app = None
    parent_textEdit = None
    code_names = []
    coders = [""]
    categories = []
    files = []
    cases = []
    html_links = []  # For html output with media link (images, av)
    results = []
    te = []  # Matrix (table) [row][col] of textEditWidget results
    # Variables for search restrictions
    file_ids = ""
    case_ids = ""
    attributes = []
    attribute_file_ids = []
    attributes_msg = ""
    # Text positions in the main textEdit for right-click context menu to View original file
    text_links = []
    # Text positions in the matrix textEdits for right-click context menu to View original file
    # list of dictionaries of row, col, textEdit, list of links
    matrix_links = []

    def __init__(self, app, parent_textedit):
        super(DialogReportCodes, self).__init__()
        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textedit
        self.get_codes_categories_coders()
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_reportCodings()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        treefont = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        treefont += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(treefont)
        doc_font = 'font: ' + str(self.app.settings['docfontsize']) + 'pt '
        doc_font += '"' + self.app.settings['font'] + '";'
        self.ui.textEdit.setStyleSheet(doc_font)
        self.ui.treeWidget.installEventFilter(self)  # For H key
        self.ui.listWidget_files.setStyleSheet(treefont)
        self.ui.listWidget_files.installEventFilter(self)  # For H key
        self.ui.listWidget_files.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.ui.listWidget_cases.setStyleSheet(treefont)
        self.ui.listWidget_cases.installEventFilter(self)  # For H key
        self.ui.listWidget_cases.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.ui.treeWidget.setSelectionMode(QtWidgets.QTreeWidget.SelectionMode.ExtendedSelection)
        self.ui.comboBox_coders.insertItems(0, self.coders)
        self.fill_tree()
        self.ui.pushButton_search.clicked.connect(self.search)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(cogs_icon), "png")
        self.ui.pushButton_search.setIcon(QtGui.QIcon(pm))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_icon), "png")
        self.ui.label_exports.setPixmap(pm.scaled(22, 22))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(attributes_icon), "png")
        self.ui.pushButton_attributeselect.setIcon(QtGui.QIcon(pm))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_color_grid_icon_24), "png")
        self.ui.label_matrix.setPixmap(pm)
        options = ["", _("Top categories by case"), _("Top categories by file"), _("Categories by case"),
                   _("Categories by file"), _("Codes by case"), _("Codes by file")]
        self.ui.comboBox_matrix.addItems(options)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(notepad_pencil_red_icon), "png")
        self.ui.label_memos.setPixmap(pm)
        options = [_("None"), _("Code text memos"), _("All memos"), _("Annotations")]
        self.ui.comboBox_memos.addItems(options)
        cur = self.app.conn.cursor()
        sql = "select count(name) from attribute_type"
        cur.execute(sql)
        res = cur.fetchone()
        if res[0] == 0:
            self.ui.pushButton_attributeselect.setEnabled(False)
        self.ui.pushButton_attributeselect.clicked.connect(self.select_attributes)
        self.ui.comboBox_export.currentIndexChanged.connect(self.export_option_selected)
        self.ui.comboBox_export.setEnabled(False)
        self.ui.textEdit.installEventFilter(self)  # for H key
        self.ui.textEdit.setReadOnly(True)
        self.ui.textEdit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.textEdit.customContextMenuRequested.connect(self.text_edit_menu)
        self.ui.splitter.setSizes([100, 200, 0])
        try:
            s0 = int(self.app.settings['dialogreportcodes_splitter0'])
            s1 = int(self.app.settings['dialogreportcodes_splitter1'])
            if s0 > 10 and s1 > 10:
                self.ui.splitter.setSizes([s0, s1, 0])
            v0 = int(self.app.settings['dialogreportcodes_splitter_v0'])
            v1 = int(self.app.settings['dialogreportcodes_splitter_v1'])
            v2 = int(self.app.settings['dialogreportcodes_splitter_v2'])
            self.ui.splitter_vert.setSizes([v0, v1, v2])
        except KeyError:
            pass
        self.ui.splitter.splitterMoved.connect(self.splitter_sizes)
        self.ui.splitter_vert.splitterMoved.connect(self.splitter_sizes)
        self.get_files_and_cases()
        self.ui.listWidget_files.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listWidget_files.customContextMenuRequested.connect(self.listwidget_files_menu)
        self.ui.listWidget_cases.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listWidget_cases.customContextMenuRequested.connect(self.listwidget_cases_menu)
        self.eventFilterTT = ToolTipEventFilter()
        self.ui.textEdit.installEventFilter(self.eventFilterTT)

    def splitter_sizes(self):
        """ Detect size changes in splitter and store in app.settings variable. """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogreportcodes_splitter0'] = sizes[0]
        self.app.settings['dialogreportcodes_splitter1'] = sizes[1]
        sizes_vert = self.ui.splitter_vert.sizes()
        self.app.settings['dialogreportcodes_splitter_v0'] = sizes_vert[0]
        self.app.settings['dialogreportcodes_splitter_v1'] = sizes_vert[1]
        self.app.settings['dialogreportcodes_splitter_v2'] = sizes_vert[2]

    def get_files_and_cases(self):
        """ Get source files with additional details and fill files list widget.
        Get cases and fill case list widget
        Called from : init, manage_files.delete manage_files.delete_button_multiple_files
        """

        self.ui.listWidget_files.clear()
        self.files = self.app.get_filenames()
        # Fill additional details about each file in the memo
        cur = self.app.conn.cursor()
        sql = "select length(fulltext), mediapath from source where id=?"
        sql_text_codings = "select count(cid) from code_text where fid=?"
        sql_av_codings = "select count(cid) from code_av where id=?"
        sql_image_codings = "select count(cid) from code_image where id=?"
        item = QtWidgets.QListWidgetItem("")
        item.setToolTip(_("No file selection"))
        self.ui.listWidget_files.addItem(item)
        for f in self.files:
            cur.execute(sql, [f['id'], ])
            res = cur.fetchone()
            if res is None:  # safety catch
                res = [0]
            tt = ""
            if res[1] is None or res[1][0:5] == "docs:":
                tt += _("Text file\n")
                tt += _("Characters: ") + str(res[0])
            if res[1] is not None and (res[1][0:7] == "images:" or res[1][0:7] == "/images"):
                tt += _("Image")
            if res[1] is not None and (res[1][0:6] == "audio:" or res[1][0:6] == "/audio"):
                tt += _("Audio")
            if res[1] is not None and (res[1][0:6] == "video:" or res[1][0:6] == "/video"):
                tt += _("Video")
            cur.execute(sql_text_codings, [f['id']])
            txt_res = cur.fetchone()
            cur.execute(sql_av_codings, [f['id']])
            av_res = cur.fetchone()
            cur.execute(sql_image_codings, [f['id']])
            img_res = cur.fetchone()
            tt += _("\nCodings: ")
            if txt_res[0] > 0:
                tt += str(txt_res[0])
            if av_res[0] > 0:
                tt += str(av_res[0])
            if img_res[0] > 0:
                tt += str(img_res[0])
            item = QtWidgets.QListWidgetItem(f['name'])
            if f['memo'] is not None and f['memo'] != "":
                tt += _("\nMemo: ") + f['memo']
            item.setToolTip(tt)
            self.ui.listWidget_files.addItem(item)

        self.ui.listWidget_cases.clear()
        self.cases = self.app.get_casenames()
        item = QtWidgets.QListWidgetItem("")
        item.setToolTip(_("No case selection"))
        self.ui.listWidget_cases.addItem(item)
        for c in self.cases:
            tt = ""
            item = QtWidgets.QListWidgetItem(c['name'])
            if c['memo'] is not None and c['memo'] != "":
                tt = _("Memo: ") + c['memo']
            item.setToolTip(tt)
            self.ui.listWidget_cases.addItem(item)

    def get_codes_categories_coders(self):
        """ Called from init, delete category. Load codes, categories, and coders. """

        self.code_names, self.categories = self.app.get_codes_categories()
        cur = self.app.conn.cursor()
        self.coders = []
        cur.execute("select distinct owner from code_text")
        result = cur.fetchall()
        self.coders = [""]
        for row in result:
            self.coders.append(row[0])

    def get_selected_files_and_cases(self):
        """ Fill file_ids and case_ids Strings used in the search.
        Clear attribute selection.
         Called by: search """

        selected_files = []
        self.file_ids = ""
        for item in self.ui.listWidget_files.selectedItems():
            selected_files.append(item.text())
            for f in self.files:
                if f['name'] == item.text():
                    self.file_ids += "," + str(f['id'])
        if len(self.file_ids) > 0:
            self.file_ids = self.file_ids[1:]
        selected_cases = []
        self.case_ids = ""
        for item in self.ui.listWidget_cases.selectedItems():
            selected_cases.append(item.text())
            for c in self.cases:
                if c['name'] == item.text():
                    self.case_ids += "," + str(c['id'])
        if len(self.case_ids) > 0:
            self.case_ids = self.case_ids[1:]

    def listwidget_files_menu(self, position):
        """ Context menu for file selection. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_all_files = menu.addAction(_("Select all files"))
        action_files_like = menu.addAction(_("Select files like"))
        action_files_none = menu.addAction(_("Select none"))
        action = menu.exec(self.ui.listWidget_files.mapToGlobal(position))
        if action == action_all_files:
            self.ui.listWidget_files.selectAll()
            self.ui.listWidget_files.item(0).setSelected(False)
        if action == action_files_none:
            for i in range(self.ui.listWidget_files.count()):
                self.ui.listWidget_files.item(i).setSelected(False)
        if action == action_files_like:
            # Input dialog narrow, so code below
            dialog = QtWidgets.QInputDialog(None)
            dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            dialog.setWindowTitle(_("Select some files"))
            dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
            dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
            dialog.setLabelText(_("Show files containing text"))
            dialog.resize(200, 20)
            ok = dialog.exec()
            if not ok:
                return
            dlg_text = str(dialog.textValue())
            for i in range(self.ui.listWidget_files.count()):
                item_name = self.ui.listWidget_files.item(i).text()
                if dlg_text in item_name:
                    self.ui.listWidget_files.item(i).setSelected(True)
                else:
                    self.ui.listWidget_files.item(i).setSelected(False)

    def listwidget_cases_menu(self, position):
        """ Context menu for case selection. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_all_cases = menu.addAction(_("Select all cases"))
        action_cases_like = menu.addAction(_("Select cases like"))
        action_cases_none = menu.addAction(_("Select none"))
        action = menu.exec(self.ui.listWidget_cases.mapToGlobal(position))
        if action == action_all_cases:
            self.ui.listWidget_cases.selectAll()
            self.ui.listWidget_cases.item(0).setSelected(False)
        if action == action_cases_none:
            for i in range(self.ui.listWidget_cases.count()):
                self.ui.listWidget_cases.item(i).setSelected(False)
        if action == action_cases_like:
            # Input dialog narrow, so code below
            dialog = QtWidgets.QInputDialog(None)
            dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            dialog.setWindowTitle(_("Select some cases"))
            dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
            dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
            dialog.setLabelText(_("Select cases containing text"))
            dialog.resize(200, 20)
            ok = dialog.exec()
            if not ok:
                return
            text_ = str(dialog.textValue())
            for i in range(self.ui.listWidget_cases.count()):
                item_name = self.ui.listWidget_cases.item(i).text()
                if text_ in item_name:
                    self.ui.listWidget_cases.item(i).setSelected(True)
                else:
                    self.ui.listWidget_cases.item(i).setSelected(False)

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes. """

        cats = copy(self.categories)
        codes = copy(self.code_names)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), "Id", _("Memo"), _("Count")])
        self.ui.treeWidget.header().setToolTip(_("Codes and categories"))
        if self.app.settings['showids'] == 'False':
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # Add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)

        ''' Add child categories. Look at each unmatched category, iterate through tree
        to add as child then remove matched categories from the list. '''
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
                        if c['memo'] != "":
                            memo = "Memo"
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
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                color = TextColor(c['color']).recommendation
                top_item.setForeground(0, QBrush(QtGui.QColor(color)))
                top_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                top_item.setToolTip(2, c['memo'])
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
                    if c['memo'] != "":
                        memo = _("Memo")
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                    color = TextColor(c['color']).recommendation
                    child.setForeground(0, QBrush(QtGui.QColor(color)))
                    child.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                    child.setToolTip(2, c['memo'])
                    item.addChild(child)
                    c['catid'] = -1  # make unmatchable
                it += 1
                item = it.value()
                count += 1
        self.fill_code_counts_in_tree()
        self.ui.treeWidget.expandAll()

    def fill_code_counts_in_tree(self):
        """ Count instances of each code from all coders and all files. """

        cur = self.app.conn.cursor()
        sql = "select count(cid) from code_text where cid=? union "
        sql += "select count(cid) from code_av where cid=? union "
        sql += "select count(cid) from code_image where cid=?"
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        count = 0
        while item and count < 10000:
            if item.text(1)[0:4] == "cid:":
                cid = str(item.text(1)[4:])
                cur.execute(sql, [cid, cid, cid])  # , self.app.settings['codername']])
                result = cur.fetchall()
                total = 0
                for row in result:
                    total = total + row[0]
                if total > 0:
                    item.setText(3, str(total))
                else:
                    item.setText(3, "")
            it += 1
            item = it.value()
            count += 1

    def export_option_selected(self):
        """ ComboBox export option selected. """

        # TODO add case matrix as csv, xlsx options
        text_ = self.ui.comboBox_export.currentText()
        if text_ == "":
            return
        if text_ == "html":
            self.export_html_file()
        if text_ == "odt":
            self.export_odt_file()
        if text_ == "txt":
            self.export_text_file()
        if text_ == "csv":
            self.export_csv_file()
        self.ui.comboBox_export.setCurrentIndex(0)

    def export_text_file(self):
        """ Export report to a plain text file with .txt ending.
        QTextWriter supports plaintext, ODF and HTML.
        BUT QTextWriter does not support utf-8-sig
        """

        if len(self.ui.textEdit.document().toPlainText()) == 0:
            return
        filename = "Report_codings.txt"
        e = ExportDirectoryPathDialog(self.app, filename)
        filepath = e.filepath
        if filepath is None:
            return
        ''' https://stackoverflow.com/questions/39422573/python-writing-weird-unicode-to-csv
        Using a byte order mark so that other software recognises UTF-8
        '''
        data = self.ui.textEdit.toPlainText()
        f = open(filepath, 'w', encoding='utf-8-sig')
        f.write(data)
        f.close()
        msg = _('Report exported: ') + filepath
        Message(self.app, _('Report exported'), msg, "information").exec()
        self.parent_textEdit.append(msg)

    def export_odt_file(self):
        """ Export report to open document format with .odt ending.
        QTextWriter supports plaintext, ODF and HTML .
        """

        if len(self.ui.textEdit.document().toPlainText()) == 0:
            return
        filename = "Report_codings.odt"
        e = ExportDirectoryPathDialog(self.app, filename)
        filepath = e.filepath
        if filepath is None:
            return
        tw = QtGui.QTextDocumentWriter()
        tw.setFileName(filepath)
        tw.setFormat(b'ODF')  # byte array needed for Windows 10
        tw.write(self.ui.textEdit.document())
        msg = _("Report exported: ") + filepath
        self.parent_textEdit.append(msg)
        Message(self.app, _('Report exported'), msg, "information").exec()

    def export_csv_file(self):
        """ Export report to csv file.
        Export coded data as csv with codes as column headings.
        Draw data from self.text_results, self.image_results, self.av_results
        First need to determine number of columns based on the distinct number of codes in the results.
        Then the number of rows based on the most frequently assigned code.
        Each data cell contains coded text, or the memo if A/V or image and the file or case name.
        """

        if not self.results:
            return
        codes_all = []
        codes_freq_list = []
        for i in self.results:
            codes_all.append(i['codename'])
        codes_set = list(set(codes_all))
        codes_set.sort()
        for x in codes_set:
            codes_freq_list.append(codes_all.count(x))
        ncols = len(codes_set)
        nrows = sorted(codes_freq_list)[-1]

        # Prepare data rows for csv writer
        csv_data = []
        for r in range(0, nrows):
            row = []
            for c in range(0, ncols):
                row.append("")
            csv_data.append(row)

        # Look at each code and fill column with data
        for col, code in enumerate(codes_set):
            row = 0
            for i in self.results:
                if i['codename'] == code:
                    if i['result_type'] == 'text':
                        d = i['text'] + "\n" + i['file_or_casename']
                        # Add file id if results are based on attribute selection
                        if i['file_or_case'] == "":
                            d += " fid:" + str(i['fid'])
                        csv_data[row][col] = d
                        row += 1
                    if i['result_type'] == 'image':
                        d = ""
                        try:
                            d = i['memo']
                        except KeyError:
                            pass
                        if d == "":
                            d = _("NO MEMO")
                        d += "\n" + i['file_or_casename']
                        # Add filename if results are based on attribute selection
                        if i['file_or_case'] == "":
                            d += " " + i['mediapath'][8:]
                        csv_data[row][col] = d
                        row += 1
                    if i['result_type'] == 'av':
                        d = ""
                        try:
                            d = i['memo']
                        except KeyError:
                            pass
                        if d == "":
                            d = _("NO MEMO")
                        d += "\n"
                        # av 'text' contains video/filename, time slot and memo, so trim some out
                        trimmed = i['text'][6:]
                        pos = trimmed.find(']')
                        trimmed = trimmed[:pos + 1]
                        # Add case name as well as file name and time slot
                        if i['file_or_case'] != "File":
                            trimmed = i['file_or_casename'] + " " + trimmed
                        d += trimmed
                        csv_data[row][col] = d
                        row += 1
        filename = "Report_codings.csv"
        e = ExportDirectoryPathDialog(self.app, filename)
        filepath = e.filepath
        if filepath is None:
            return
        with open(filepath, 'w', encoding='utf-8-sig', newline='') as csvfile:
            filewriter = csv.writer(csvfile, delimiter=',',
                                    quotechar='"', quoting=csv.QUOTE_MINIMAL)
            filewriter.writerow(codes_set)  # header row
            for row in csv_data:
                filewriter.writerow(row)
        msg = _('Report exported: ') + filepath
        Message(self.app, _('Report exported'), msg, "information").exec()
        self.parent_textEdit.append(msg)

    def export_html_file(self):
        """ Export report to a html file. Create folder of images and change refs to the
        folder.
        """

        if len(self.ui.textEdit.document().toPlainText()) == 0:
            return
        html_filename = "Report_codings.html"
        e = ExportDirectoryPathDialog(self.app, html_filename)
        filepath = e.filepath
        if filepath is None:
            return
        tw = QtGui.QTextDocumentWriter()
        tw.setFileName(filepath)
        tw.setFormat(b'HTML')  # byte array needed for Windows 10
        print("Trying without QTextCodec")
        #tw.setCodec(QTextCodec.codecForName('UTF-8'))  # for Windows 10
        tw.write(self.ui.textEdit.document())
        need_media_folders = False
        for item in self.html_links:
            if item['image'] is not None or item['avname'] is not None:
                need_media_folders = True
        html_folder_name = ""
        if need_media_folders:
            # Create folder with sub-folders for inages, audio and video
            html_folder_name = filepath[:-5]
            try:
                os.mkdir(html_folder_name)
                os.mkdir(html_folder_name + "/images")
                os.mkdir(html_folder_name + "/audio")
                os.mkdir(html_folder_name + "/video")
            except Exception as e:
                logger.warning(_("html folder creation error ") + str(e))
                Message(self.app, _("Folder creation"), html_folder_name + _(" error ") + str(e), "critical").exec()
                return
        try:
            with open(filepath, 'r') as f:
                html = f.read()
        except Exception as e:
            logger.warning(_('html file reading error:') + str(e))
            return

        # Change html links to reference the html folder
        for item in self.html_links:
            if item['imagename'] is not None:
                image_name = item['imagename'].replace('/images/', '')
                # print("IMG NAME: ", item['imagename'])
                img_path = html_folder_name + "/images/" + image_name
                # print("IMG PATH", img_path)
                # item['image'] is  QtGui.QImage object
                item['image'].save(img_path)
                html = html.replace(item['imagename'], img_path)
            if item['avname'] is not None:
                # Add audio/video to html folder
                mediatype = "video"
                if item['avname'][0:6] in ("/audio", "audio:"):
                    mediatype = "audio"
                # Remove link prefix and note if link or not
                linked = False
                av_path = item['avname']
                if av_path[0:6] == "video:":
                    av_path = av_path[6:]
                    linked = True
                if av_path[0:6] == "audio:":
                    linked = True
                    av_path = av_path[6:]
                av_destination = html_folder_name + av_path
                # Copy non-linked a/v file to html folder
                if not linked and not os.path.isfile(html_folder_name + av_path):
                    copyfile(self.app.project_path + item['avname'], html_folder_name + av_path)
                    av_destination = html_folder_name + av_path
                # Copy Linked video file to html folder
                if mediatype == "video" and linked:
                    av_destination = html_folder_name + "/video/" + av_path.split('/')[-1]
                    if not os.path.isfile(html_folder_name + "/video/" + av_path.split('/')[-1]):
                        copyfile(av_path, av_destination)
                # Copy Linked audio file to html folder
                if mediatype == "audio" and linked:
                    av_destination = html_folder_name + "/audio/" + av_path.split('/')[-1]
                    if not os.path.isfile(html_folder_name + "/audio/" + av_path.split('/')[-1]):
                        copyfile(av_path, av_destination)
                # Create html to display media time positions
                extension = item['avname'][item['avname'].rfind('.') + 1:]
                extra = "</p>\n<" + mediatype + " controls>"
                extra += '<source src="' + av_destination
                extra += '#t=' + item['av0'] + ',' + item['av1'] + '"'
                extra += ' type="' + mediatype + '/' + extension + '">'
                extra += '</' + mediatype + '><p>\n'
                # Hopefully only one location with exact audio/video/link: [mins.secs - mins.secs]
                location = html.find(item['avtext'].replace('&', '&amp;'))
                location = location + len(['avtext']) - 1
                tmp = html[:location] + extra + html[location:]
                html = tmp
        with open(filepath, 'w', encoding='utf-8-sig') as f:
            f.write(html)
        msg = _("Report exported to: ") + filepath
        if need_media_folders:
            msg += "\n" + _("Media folder: ") + html_folder_name
        self.parent_textEdit.append(msg)
        Message(self.app, _('Report exported'), msg, "information").exec()

    def eventFilter(self, object_, event):
        """ Used to detect key events in the textedit.
        H Hide / Unhide top groupbox
        """

        if type(event) == QtGui.QKeyEvent and (self.ui.textEdit.hasFocus() or self.ui.treeWidget.hasFocus() or
                                               self.ui.listWidget_files.hasFocus() or
                                               self.ui.listWidget_cases.hasFocus()):
            key = event.key()
            # Hide unHide top groupbox
            if key == QtCore.Qt.Key.Key_H:
                self.ui.groupBox.setHidden(not (self.ui.groupBox.isHidden()))
                return True
        return False

    def recursive_set_selected(self, item):
        """ Set all children of this item to be selected if the item is selected.
        Recurse through any child categories.
        Called by: search
        """

        child_count = item.childCount()
        for i in range(child_count):
            if item.isSelected():
                item.child(i).setSelected(True)
            self.recursive_set_selected(item.child(i))

    def search_annotations(self):
        """ Find and display annotations from selected text files. """

        # Get variables for search: search text, coders, codes, files,cases, attributes
        coder = self.ui.comboBox_coders.currentText()
        self.html_links = []  # For html file output with media
        search_text = self.ui.lineEdit.text()
        self.get_selected_files_and_cases()
        if self.file_ids == "":
            Message(self.app, _("Warning"), _("No files selected for annotations")).exec()
            return
        self.ui.treeWidget.clearSelection()
        self.ui.listWidget_cases.clearSelection()

        cur = self.app.conn.cursor()
        sql = "select anid, fid, source.name, pos0, pos1, annotation.memo, annotation.owner, annotation.date, "
        sql += "substr(fulltext, pos0 + 1, pos1 - pos0) as subtext "
        sql += "from annotation join source on source.id=annotation.fid "
        sql += "where source.fulltext is not null and fid in (" + self.file_ids + ") "
        # Coder limiter
        values = []
        if coder != "":
            sql += " and annotation.owner=? "
            values.append(coder)
        if search_text != "":
            sql += " and instr(subtext, ?) is not null "
            values.append(search_text)
        sql += " order by source.name, anid asc"
        if not values:
            cur.execute(sql)
        else:
            cur.execute(sql, values)
        res = cur.fetchall()
        annotes = []
        keys = "anid", "fid", "filename", "pos0", "pos1", "annotation", "owner", "date", "text"
        for row in res:
            annotes.append(dict(zip(keys, row)))

        self.ui.textEdit.clear()
        # Display search parameters
        self.ui.textEdit.append(_("Annotation search parameters") + "\n==========")
        if coder == "":
            self.ui.textEdit.append(_("Coder: All coders"))
        else:
            self.ui.textEdit.append(_("Coder: ") + coder)
        if search_text != "":
            self.ui.textEdit.append(_("Search text: ") + search_text)
        self.ui.textEdit.append(_("Files:"))
        cur.execute(
            "select name from source where id in (" + self.file_ids + ") and source.fulltext is not null order by name")
        res = cur.fetchall()
        file_txt = ""
        for r in res:
            file_txt += r[0] + ", "
        self.ui.textEdit.append(file_txt)
        self.ui.textEdit.append("==========")
        for a in annotes:
            txt = "\n" + _("File") + ": " + a['filename'] + " anid: " + str(a['anid']) + " " + _("Date:") + " "
            txt += a['date'][0:10] + " " + _("Coder:") + " " + a['owner'] + ", "
            txt += _("Position") + ": " + str(a['pos0']) + " - " + str(a['pos1']) + "\n"
            txt += _("TEXT") + ": " + a['text'] + "\n"
            txt += _("ANNOTATION") + ": " + a['annotation']
            self.ui.textEdit.append(txt)
        self.ui.comboBox_export.setEnabled(True)

    def select_attributes(self):
        """ Select files based on attribute selections.
        Attribute results are a dictionary of:
        [0] attribute name,
        [1] attribute type: character, numeric
        [2] modifier: > < == != like between
        [3] comparison value as list, one item or two items for between

        DialogSelectAttributeParameters returns lists for each parameter selected of:
        attribute name, file or case, character or numeric, operator, list of one or two comparator values
        two comparator values are used with the 'between' operator
        ['source', 'file', 'character', '==', ["'interview'"]]
        ['case name', 'case', 'character', '==', ["'ID1'"]]

        sqls are NOT parameterised.
        Results from multiple parameters are intersected, an AND boolean function.
        """

        # Clear ui
        self.attributes_msg = ""
        self.attribute_file_ids = []
        self.ui.pushButton_attributeselect.setToolTip(_("Attributes"))
        self.ui.splitter.setSizes([300, 300, 0])
        self.file_ids = ""
        for i in range(self.ui.listWidget_files.count()):
            self.ui.listWidget_files.item(i).setSelected(False)
        self.case_ids = ""
        for i in range(self.ui.listWidget_cases.count()):
            self.ui.listWidget_cases.item(i).setSelected(False)

        ui = DialogSelectAttributeParameters(self.app)
        ui.fill_parameters(self.attributes)
        temp_attributes = deepcopy(self.attributes)
        self.attributes = []
        ok = ui.exec()
        if not ok:
            self.attributes = temp_attributes
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(attributes_icon), "png")
            self.ui.pushButton_attributeselect.setIcon(QtGui.QIcon(pm))
            self.ui.pushButton_attributeselect.setToolTip(_("Attributes"))
            if self.attributes:
                pm = QtGui.QPixmap()
                pm.loadFromData(QtCore.QByteArray.fromBase64(attributes_selected_icon), "png")
                self.ui.pushButton_attributeselect.setIcon(QtGui.QIcon(pm))
            return
        self.attributes = ui.parameters
        if not self.attributes:
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(attributes_icon), "png")
            self.ui.pushButton_attributeselect.setIcon(QtGui.QIcon(pm))
            self.ui.pushButton_attributeselect.setToolTip(_("Attributes"))
            return
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(attributes_selected_icon), "png")
        self.ui.pushButton_attributeselect.setIcon(QtGui.QIcon(pm))
        file_ids = []
        case_file_ids = []
        cur = self.app.conn.cursor()
        # Run a series of sql based on each selected attribute
        # Apply a set to the resulting ids to determine the final list of ids
        for a in self.attributes:
            # File attributes
            file_sql = "select id from attribute where "
            if a[1] == 'file':
                file_sql += "attribute.name = '" + a[0] + "' "
                file_sql += " and attribute.value " + a[3] + " "
                if a[3] == 'between':
                    file_sql += a[4][0] + " and " + a[4][1] + " "
                if a[3] in ('in', 'not in'):
                    file_sql += "(" + ','.join(a[4]) + ") "  # One item the comma is skipped
                if a[3] not in ('between', 'in', 'not in'):
                    file_sql += a[4][0]
                if a[2] == 'numeric':
                    file_sql = file_sql.replace(' attribute.value ', ' cast(attribute.value as real) ')
                file_sql += " and attribute.attr_type='file'"
                cur.execute(file_sql)
                result = cur.fetchall()
                for i in result:
                    file_ids.append(i[0])
            # Case attributes
            if a[1] == 'case':
                # Case text table also links av and images
                case_sql = "select distinct case_text.fid from cases "
                case_sql += "join case_text on case_text.caseid=cases.caseid "
                case_sql += "join attribute on cases.caseid=attribute.id "
                case_sql += " where "
                case_sql += "attribute.name = '" + a[0] + "' "
                case_sql += " and attribute.value " + a[3] + " "
                if a[3] == 'between':
                    case_sql += a[4][0] + " and " + a[4][1] + " "
                if a[3] in ('in', 'not in'):
                    case_sql += "(" + ','.join(a[4]) + ") "  # One item the comma is skipped
                if a[3] not in ('between', 'in', 'not in'):
                    case_sql += a[4][0]
                if a[2] == 'numeric':
                    case_sql = case_sql.replace(' attribute.value ', ' cast(attribute.value as real) ')
                case_sql += " and attribute.attr_type='case'"
                # print("Attribute selected: ", a)
                # print(case_sql)
                cur.execute(case_sql)
                case_result = cur.fetchall()
                for i in case_result:
                    case_file_ids.append(i[0])
        # Consolidate csse and file ids
        if file_ids == [] and case_file_ids == []:
            Message(self.app, "Nothing found", "Nothing found").exec()
            return
        set_ids = {}
        set_file_ids = set(file_ids)
        set_case_file_ids = set(case_file_ids)
        # Intersect case file ids and file ids
        if file_ids != [] and case_file_ids != []:
            set_ids = set_file_ids.intersection(set_case_file_ids)
        if file_ids != [] and case_file_ids == []:
            set_ids = set_file_ids
        if file_ids == [] and case_file_ids != []:
            set_ids = set_case_file_ids
        self.attribute_file_ids = list(set_ids)
        # print("Attribute file ids", self.attribute_file_ids)
        # Prepare message for label tooltip
        self.attributes_msg = ""
        file_msg = ""
        case_msg = ""
        for a in self.attributes:
            if a[1] == 'file':
                file_msg += " or " + a[0] + " " + a[3] + " " + ",".join(a[4])
        if len(file_msg) > 4:
            file_msg = "(" + _("File: ") + file_msg[3:] + ")"
        for a in self.attributes:
            if a[1] == 'case':
                case_msg += " or " + a[0] + " " + a[3] + " " + ",".join(a[4])
        if len(case_msg) > 5:
            case_msg = "(" + _("Case: ") + case_msg[4:] + ")"
        if file_msg != "" and case_msg != "":
            self.attributes_msg = file_msg + " and " + case_msg
        else:
            self.attributes_msg = file_msg + case_msg
        self.ui.pushButton_attributeselect.setToolTip(_("Attributes: ") + self.attributes_msg)

    def search(self):
        """ Search for selected codings.
        There are three main search pathways.
        1:  file selection only.
        2: case selection combined with files selection. (No files selected presumes ALL files)
        3: attribute selection, which may include files or cases.
        """

        # If Annotations is selected only look at selected text file annotations. Separate search and report method.
        choice = self.ui.comboBox_memos.currentText()
        if choice == "Annotations":
            self.search_annotations()
            return

        # Get variables for search: search text, coders, codes, files,cases, attribute file ids
        coder = self.ui.comboBox_coders.currentText()
        self.html_links = []  # For html file output with media
        search_text = self.ui.lineEdit.text()
        self.get_selected_files_and_cases()

        # Select all code items under selected categories
        self.recursive_set_selected(self.ui.treeWidget.invisibleRootItem())
        items = self.ui.treeWidget.selectedItems()
        if len(items) == 0:
            msg = _("No codes have been selected.")
            Message(self.app, _('No codes'), msg, "warning").exec()
            return
        if self.file_ids == "" and self.case_ids == "" and self.attributes == []:
            msg = _("No files, cases or attributes have been selected.")
            Message(self.app, _('Nothing selected'), msg, "warning").exec()
            return

        # Prepare results table and results lists
        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        # Default for attributes selection
        file_or_case = ""
        if self.file_ids != "":
            file_or_case = "File"
        if self.case_ids != "":
            file_or_case = "Case"
        # Add search terms to textEdit
        self.ui.comboBox_export.setEnabled(True)
        self.ui.textEdit.clear()
        self.ui.textEdit.insertPlainText(_("Search parameters") + "\n==========\n")
        if coder == "":
            self.ui.textEdit.insertPlainText(_("Coding by: All coders") + "\n")
        else:
            self.ui.textEdit.insertPlainText(_("Coding by: ") + coder + "\n")
        codes_string = _("Codes: ") + "\n"
        codes_count = 0
        for i in items:
            if i.text(1)[0:3] == 'cid':
                codes_count += 1
                codes_string += i.text(0) + ". "
        codes_string += _("Codes: ") + str(codes_count) + " / " + str(len(self.code_names))
        self.ui.textEdit.insertPlainText(codes_string)
        important = self.ui.checkBox_important.isChecked()

        cur = self.app.conn.cursor()
        parameters = ""
        if self.attribute_file_ids:
            self.file_ids = ""
            for a in self.attribute_file_ids:
                self.file_ids += "," + str(a)
            self.file_ids = self.file_ids[1:]
            for i in range(self.ui.listWidget_files.count()):
                self.ui.listWidget_files.item(i).setSelected(False)
            self.case_ids = ""
            for i in range(self.ui.listWidget_cases.count()):
                self.ui.listWidget_cases.item(i).setSelected(False)
            parameters += _("\nAttributes:\n") + self.attributes_msg + "\n"
        if self.file_ids != "":
            parameters += _("\nFiles:\n")
            cur.execute("select name from source where id in (" + self.file_ids + ") order by name")
            res = cur.fetchall()
            for r in res:
                parameters += r[0] + ", "
            parameters += _(" Files: ") + str(len(res)) + " / " + str(len(self.files))
        if self.case_ids != "":
            parameters += _("\nCases:\n")
            cur.execute("select name from cases where caseid in (" + self.case_ids + ") order by name")
            res = cur.fetchall()
            for r in res:
                parameters += r[0] + ", "
        self.ui.textEdit.insertPlainText(parameters + "\n")
        if search_text != "":
            self.ui.textEdit.insertPlainText("\n" + _("Search text: ") + search_text + "\n")
        self.ui.textEdit.insertPlainText("\n==========\n")

        # Get selected codes
        code_ids = ""
        for i in items:
            if i.text(1)[0:3] == 'cid':
                code_ids += "," + i.text(1)[4:]
        code_ids = code_ids[1:]
        self.html_links = []
        self.results = []
        parameters = []

        # FILES SEARCH, ALSO ATTRIBUTES FILE IDS SEARCH
        if self.file_ids != "" and self.case_ids == "":
            # Coded text
            sql = "select code_name.name, color, source.name, pos0, pos1, seltext, "
            sql += "code_text.owner, fid, code_text.memo, code_name.memo, source.memo "
            sql += " from code_text join code_name "
            sql += "on code_name.cid = code_text.cid join source on fid = source.id "
            sql += "where code_name.cid in (" + code_ids + ") "
            sql += "and source.id in (" + self.file_ids + ") "
            if coder != "":
                sql += " and code_text.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and seltext like ? "
                parameters.append("%" + str(search_text) + "%")
            if important:
                sql += " and code_text.important=1 "
            sql += " order by code_name.name, source.name, pos0"
            if not parameters:
                cur.execute(sql)
            else:
                cur.execute(sql, parameters)
            result = cur.fetchall()
            keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'text', 'coder', 'fid', 'coded_memo', \
                   'codename_memo', 'source_memo'
            for row in result:
                tmp = dict(zip(keys, row))
                tmp['result_type'] = 'text'
                tmp['file_or_case'] = file_or_case
                tmp['pretext'] = ""
                tmp['posttext'] = ""
                self.results.append(tmp)
            if self.ui.checkBox_text_context.isChecked():
                self.get_prettext_and_posttext()

            # Coded images
            parameters = []
            sql = "select code_name.name, color, source.name, x1, y1, width, height,"
            sql += "code_image.owner, source.mediapath, source.id, code_image.memo, "
            sql += "code_name.memo, source.memo "
            sql += " from code_image join code_name "
            sql += "on code_name.cid = code_image.cid join source on code_image.id = source.id "
            sql += "where code_name.cid in (" + code_ids + ") "
            sql += "and source.id in (" + self.file_ids + ") "
            if coder != "":
                sql += " and code_image.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and code_image.memo like ? "
                parameters.append("%" + str(search_text) + "%")
            if important:
                sql += " and code_image.important=1 "
            sql += " order by code_name.name, source.name, x1"
            if not parameters:
                cur.execute(sql)
            else:
                cur.execute(sql, parameters)
            result = cur.fetchall()
            keys = 'codename', 'color', 'file_or_casename', 'x1', 'y1', 'width', 'height', 'coder', 'mediapath', \
                   'fid', 'coded_memo', 'codename_memo', 'source_memo'
            for row in result:
                tmp = dict(zip(keys, row))
                tmp['result_type'] = 'image'
                tmp['file_or_case'] = file_or_case
                self.results.append(tmp)

            # Coded audio and video, also looks for search_text in coded segment memo
            parameters = []
            sql = "select code_name.name, color, source.name, pos0, pos1, code_av.memo, "
            sql += " code_av.owner, source.mediapath, source.id, code_name.memo, source.memo "
            sql += " from code_av join code_name "
            sql += "on code_name.cid = code_av.cid join source on code_av.id = source.id "
            sql += "where code_name.cid in (" + code_ids + ") "
            sql += "and source.id in (" + self.file_ids + ") "
            if coder != "":
                sql += " and code_av.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and code_av.memo like ? "
                parameters.append("%" + str(search_text) + "%")
            if important:
                sql += " and code_av.important=1 "
            sql += " order by code_name.name, source.name, pos0"
            if not parameters:
                cur.execute(sql)
            else:
                cur.execute(sql, parameters)
            result = cur.fetchall()
            keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'coded_memo', 'coder', 'mediapath', 'fid', \
                   'codename_memo', 'source_memo'
            for row in result:
                tmp = dict(zip(keys, row))
                tmp['result_type'] = 'av'
                tmp['file_or_case'] = file_or_case
                text_ = str(tmp['file_or_casename']) + " "
                if len(tmp['coded_memo']) > 0:
                    text_ += "\nMemo: " + tmp['coded_memo']
                text_ += " " + msecs_to_hours_mins_secs(tmp['pos0']) + " - " + msecs_to_hours_mins_secs(tmp['pos1'])
                tmp['text'] = text_
                self.html_links.append({'imagename': None, 'image': None,
                                        'avname': tmp['mediapath'], 'av0': str(int(tmp['pos0'] / 1000)),
                                        'av1': str(int(tmp['pos1'] / 1000)), 'avtext': text_})
                self.results.append(tmp)

        # CASES AND FILES SEARCH
        # Default to all files if none are selected, otherwise limit to the selected files
        if self.case_ids != "":
            # Coded text
            sql = "select code_name.name, color, cases.name, "
            sql += "code_text.pos0, code_text.pos1, seltext, code_text.owner, code_text.fid, "
            sql += "cases.memo, code_text.memo, code_name.memo, source.memo "
            sql += "from code_text join code_name on code_name.cid = code_text.cid "
            sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += "code_text.fid = case_text.fid "
            sql += "join source on source.id=code_text.fid "
            sql += "where code_name.cid in (" + code_ids + ") "
            sql += "and case_text.caseid in (" + self.case_ids + ") "
            if self.file_ids != "":
                sql += " and code_text.fid in (" + self.file_ids + ")"
            sql += "and (code_text.pos0 >= case_text.pos0 and code_text.pos1 <= case_text.pos1)"
            if coder != "":
                sql += " and code_text.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and seltext like ? "
                parameters.append("%" + str(search_text) + "%")
            sql += " order by code_name.name, cases.name"
            if not parameters:
                cur.execute(sql)
            else:
                cur.execute(sql, parameters)
            results = cur.fetchall()
            keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'text', 'coder', 'fid', \
                   'cases_memo', 'coded_memo', 'codename_memo', 'source_memo'
            for row in results:
                tmp = dict(zip(keys, row))
                tmp['result_type'] = 'text'
                tmp['file_or_case'] = file_or_case
                tmp['pretext'] = ""
                tmp['posttext'] = ""
                self.results.append(tmp)
            if self.ui.checkBox_text_context.isChecked():
                self.get_prettext_and_posttext()

            # Coded images
            parameters = []
            sql = "select code_name.name, color, cases.name, "
            sql += "x1, y1, width, height, code_image.owner,source.mediapath, source.id, "
            sql += "code_image.memo, cases.memo, code_name.memo, source.memo from "
            sql += "code_image join code_name on code_name.cid = code_image.cid "
            sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += "code_image.id = case_text.fid "
            sql += " join source on case_text.fid = source.id "
            sql += "where code_name.cid in (" + code_ids + ") "
            sql += "and case_text.caseid in (" + self.case_ids + ") "
            if self.file_ids != "":
                sql += " and source.id in (" + self.file_ids + ")"
            if coder != "":
                sql += " and code_image.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and code_image.memo like ? "
                parameters.append("%" + str(search_text) + "%")
            sql += " order by code_name.name, cases.name"
            if not parameters:
                cur.execute(sql)
            else:
                cur.execute(sql, parameters)
            imgresults = cur.fetchall()
            keys = 'codename', 'color', 'file_or_casename', 'x1', 'y1', 'width', 'height', 'coder', 'mediapath', 'fid', \
                   'coded_memo', 'case_memo', 'codename_memo', 'source_memo'
            for row in imgresults:
                tmp = dict(zip(keys, row))
                tmp['result_type'] = 'image'
                tmp['file_or_case'] = file_or_case
                self.results.append(tmp)

            # Coded audio and video
            parameters = []
            av_sql = "select distinct code_name.name, color, cases.name as case_name, "
            av_sql += "code_av.pos0, code_av.pos1, code_av.owner,source.mediapath, source.id, "
            av_sql += "code_av.memo as coded_memo, cases.memo as case_memo, code_name.memo, source.memo "
            av_sql += " from code_av join code_name on code_name.cid = code_av.cid "
            av_sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
            av_sql += "code_av.id = case_text.fid "
            av_sql += " join source on case_text.fid = source.id "
            av_sql += "where code_name.cid in (" + code_ids + ") "
            av_sql += "and case_text.caseid in (" + self.case_ids + ") "
            if self.file_ids != "":
                av_sql += " and source.id in (" + self.file_ids + ")"
            if coder != "":
                av_sql += " and code_av.owner=? "
                parameters.append(coder)
            if search_text != "":
                av_sql += " and code_av.memo like ? "
                parameters.append("%" + str(search_text) + "%")
            sql += " order by code_name.name, cases.name"
            if not parameters:
                cur.execute(av_sql)
            else:
                cur.execute(av_sql, parameters)
            avresults = cur.fetchall()
            keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', \
                   'coder', 'mediapath', 'fid', 'coded_memo', 'case_memo', 'codename_memo', 'source_memo'
            for row in avresults:
                tmp = dict(zip(keys, row))
                tmp['result_type'] = 'av'
                tmp['file_or_case'] = file_or_case
                tmp_text = str(tmp['file_or_casename']) + " "
                if len(tmp['coded_memo']) > 0:
                    tmp_text += "\nMemo: " + tmp['coded_memo']
                tmp_text += " " + msecs_to_hours_mins_secs(tmp['pos0']) + " - " + msecs_to_hours_mins_secs(tmp['pos1'])
                tmp['text'] = tmp_text
                self.html_links.append({'imagename': None, 'image': None,
                                        'avname': tmp['mediapath'], 'av0': str(int(tmp['pos0'] / 1000)),
                                        'av1': str(int(tmp['pos1'] / 1000)), 'avtext': tmp_text})
                self.results.append(tmp)

        # Organise results by code name, ascending
        self.results = sorted(self.results, key=lambda i_: i_['codename'])
        self.fill_text_edit_with_search_results()
        # Clean up for next search. Except attributes list
        self.attribute_file_ids = []
        self.file_ids = ""
        self.case_ids = ""
        self.attributes_msg = ""
        self.ui.pushButton_attributeselect.setToolTip(_("Attributes"))

    def get_prettext_and_posttext(self):
        """ Get surrounding text 200 characters.
        When context checkbox is checked """

        cur = self.app.conn.cursor()
        for r in self.results:
            # Pre text
            pre_text_length = 200
            if r['pos0'] > pre_text_length - 1:
                pre_text_start = r['pos0'] - pre_text_length + 1  # sqlite strings start at 1 not 0
            else:
                pre_text_start = 1  # sqlite strings start at 1 not 0
                pre_text_length = r['pos0']  # sqlite strings start at 1 not 0, so this length is OK
            if pre_text_start < 1:
                pre_text_start = 1
            sql = "select substr(fulltext,?,?) from source where id=?"
            cur.execute(sql, [pre_text_start, pre_text_length, r['fid']])
            res_pre = cur.fetchone()
            if res_pre is not None:
                r['pretext'] = res_pre[0]
            # Post text
            post_text_start = r['pos1'] + 1  # sqlite strings start at 1 not 0
            post_text_length = 200
            sql = "select substr(fulltext,?,?) from source where id=?"
            cur.execute(sql, [post_text_start, post_text_length, r['fid']])
            res_post = cur.fetchone()
            if res_post is not None:
                r['posttext'] = res_post[0]

    def text_code_count_and_percent(self):
        """ First part of results, fill code counts and text percentages.
        Text percentages is total of coded text divided by total of text source characters. """

        # Get file text lengths for the text files from the files in the results
        file_ids = []
        code_names = []
        for r in self.results:
            if r['result_type'] == 'text':
                file_ids.append(r['fid'])
                code_names.append(r['codename'])
        file_ids = list(set(file_ids))
        code_names = list(set(code_names))
        code_names.sort()
        cur = self.app.conn.cursor()
        sql = "select id, length(fulltext), name from source where fulltext is not null and id=? order by name"
        file_lengths = []
        for id_ in file_ids:
            cur.execute(sql, [id_])
            res = cur.fetchone()
            res_dict = {"fid": res[0], "length": res[1], "filename": res[2]}
            file_lengths.append(res_dict)
        # Stats results dictionary preparation
        stats = []
        for c in code_names:
            for f in file_lengths:
                stats.append({'codename': c, 'fid': f['fid'], 'filetextlength': f['length'],
                              'filename': f['filename'], 'codecount': 0,
                              'codetextlength': 0, 'percent': 0})
        # Stats results calculated
        """
        {codename , color , file_or_casename , pos0 , pos1 , text , coder, fid, 
        coded_memo codename_memo, source_memo, result_type, file_or_case': 'File'}
        """
        for st in stats:
            for r in self.results:
                if st['codename'] == r['codename'] and st['fid'] == r['fid']:
                    st['codecount'] += 1
                    st['codetextlength'] += len(r['text'])
                    # 2 decimal places
                    st['percent'] = round((st['codetextlength'] / st['filetextlength']) * 100, 2)
        final_stats = []
        for st in stats:
            if st['codecount'] > 0:
                final_stats.append(st)
        msg = _("Text code statistics:")
        for st in final_stats:
            msg += "\n" + st['codename'] + " | " + st['filename'] + " | " + _("Count: ") + str(st['codecount']) + " | "
            msg += _("Percent of file: ") + str(st['percent']) + "%"
        msg += "\n========"
        if len(final_stats) == 0:
            msg = ""
        return stats, msg

    def image_code_count_and_percent(self):
        """ First part of results, fill code counts and image percentages.
        Image percentages is total of coded area divided by total of Image source area. """

        # Get file area for each image
        file_ids = []
        code_names = []
        for r in self.results:
            if r['result_type'] == 'image':
                file_ids.append(r['fid'])
                code_names.append(r['codename'])
        file_ids = list(set(file_ids))
        code_names = list(set(code_names))
        code_names.sort()
        cur = self.app.conn.cursor()
        sql = "select id, name, mediapath from source where id=? order by name"
        file_areas = []
        for id_ in file_ids:
            cur.execute(sql, [id_])
            res = cur.fetchone()
            abs_path = ""
            w, h = 1, 1
            if 'images:' == res[2][0:7]:
                abs_path = res[2][7:]
            else:
                abs_path = self.app.project_path + res[2]
            try:
                image = Image.open(abs_path)
                w, h = image.size
            except FileNotFoundError:
                pass
            res_dict = {"fid": res[0], "area": w * h, "filename": res[1]}
            file_areas.append(res_dict)

        # Stats results dictionary preparation
        stats = []
        for c in code_names:
            for f in file_areas:
                stats.append({'codename': c, 'fid': f['fid'], 'filearea': f['area'],
                              'filename': f['filename'], 'codecount': 0,
                              'codedarea': 0, 'percent': 0})
        # Stats results calculated
        for st in stats:
            for r in self.results:
                if st['codename'] == r['codename'] and st['fid'] == r['fid']:
                    st['codecount'] += 1
                    st['codedarea'] += r['width'] * r['height']
                    # 2 decimal places
                    st['percent'] = round((st['codedarea'] / st['filearea']) * 100, 2)
        final_stats = []
        for st in stats:
            if st['codecount'] > 0:
                final_stats.append(st)
        msg = _("Image code statistics:")
        for st in final_stats:
            msg += "\n" + st['codename'] + " | " + st['filename'] + " | " + _("Count: ") + str(st['codecount']) + " | "
            msg += _("Percent of file: ") + str(st['percent']) + "%"
        msg += "\n========"
        if len(final_stats) == 0:
            msg = ""
        return stats, msg

    def av_code_count_and_percent(self):
        """ First part of results, fill code counts and AV percentages.
        AV percentages is total of coded text divided by total of AV source duration. """

        # Get file lengths
        file_ids = []
        code_names = []
        for r in self.results:
            if r['result_type'] == 'av':
                file_ids.append(r['fid'])
                code_names.append(r['codename'])
        file_ids = list(set(file_ids))
        code_names = list(set(code_names))
        code_names.sort()
        cur = self.app.conn.cursor()
        sql = "select id, name, mediapath from source where id=? order by name"
        file_lengths = []
        for id_ in file_ids:
            cur.execute(sql, [id_])
            res = cur.fetchone()
            abs_path = ""
            if 'audio:' == res[2][0:6]:
                abs_path = res[2][6:]
            elif 'video:' == res[2][0:6]:
                abs_path = res[2][6:]
            else:
                abs_path = self.app.project_path + res[2]
            instance = vlc.Instance()
            msecs = 1
            try:
                media = instance.media_new(abs_path)
                media.parse()
                msecs = media.get_duration()
            except FileNotFoundError:
                pass
            res_dict = {"fid": res[0], "file_duration": msecs, "filename": res[1]}
            file_lengths.append(res_dict)
        # Stats results dictionary preparation
        stats = []
        for c in code_names:
            for f in file_lengths:
                stats.append({'codename': c, 'fid': f['fid'], 'file_duration': f['file_duration'],
                              'filename': f['filename'], 'codecount': 0,
                              'coded_duration': 0, 'percent': 0})
        # Stats results calculated
        for st in stats:
            for r in self.results:
                if st['codename'] == r['codename'] and st['fid'] == r['fid']:
                    st['codecount'] += 1
                    st['coded_duration'] += r['pos1'] - r['pos0']
                    # 2 decimal places
                    st['percent'] = round((st['coded_duration'] / st['file_duration']) * 100, 2)
        final_stats = []
        for st in stats:
            if st['codecount'] > 0:
                final_stats.append(st)
        msg = _("A/V code statistics:")
        for st in final_stats:
            msg += "\n" + st['codename'] + " | " + st['filename'] + " | " + _("Count: ") + str(st['codecount']) + " | "
            msg += _("Percent of file: ") + str(st['percent']) + "%"
        msg += "\n========"
        if len(final_stats) == 0:
            msg = ""
        return stats, msg

    def fill_text_edit_stats_results(self):
        """ Fill text edit with statistics for codes.
         As total counts and count and percent per file. """

        text_stats, text_msg = self.text_code_count_and_percent()
        img_stats, img_msg = self.image_code_count_and_percent()
        av_stats, av_msg = self.av_code_count_and_percent()
        counts = []
        for s in text_stats:
            counts.append(s['codename'])
        for s in img_stats:
            counts.append(s['codename'])
        for s in av_stats:
            counts.append(s['codename'])
        counts = list(set(counts))
        counts.sort()
        # Display code count totals
        msg = ""
        total_count = 0
        for c in counts:
            count = 0
            for s in text_stats:
                if s['codename'] == c:
                    count += s['codecount']
            for s in img_stats:
                if s['codename'] == c:
                    count += s['codecount']
            for s in av_stats:
                if s['codename'] == c:
                    count += s['codecount']
            msg += "\n" + c + " : " + str(count)
            total_count += count
        msg = _("Code count totals") + ": " + str(total_count) + "\n============" + msg
        msg += "\n============"
        self.ui.textEdit.append(msg)
        if text_msg != "":
            self.ui.textEdit.append(text_msg)
        if img_msg != "":
            self.ui.textEdit.append(img_msg)
        if av_msg != "":
            self.ui.textEdit.append(av_msg)

    def fill_text_edit_with_search_results(self):
        """ The textEdit.document is filled with the search results.
        Results are drawn from the textEdit.document to fill reports in .txt and .odt formats.
        Results are drawn from the textEdit.document and html_links variable to fill reports in html format.
        Results are drawn from self.text_results, self.image_results and self.av_results to prepare a csv file.
        The results are converted from tuples to dictionaries.
        As results are added to the textEdit, positions for the headings (code, file, codername) are recorded for
        right-click context menu to display contextualised coding in another dialog.
        """

        self.text_links = []
        self.matrix_links = []
        if self.ui.checkBox_show_stats.isChecked():
            self.fill_text_edit_stats_results()

        # Add textedit positioning for context on clicking appropriate heading in results
        # Fill text edit with heading, text, image or
        fmt_normal = QtGui.QTextCharFormat()
        fmt_normal.setFontWeight(QtGui.QFont.Weight.Normal)
        fmt_bold = QtGui.QTextCharFormat()
        fmt_bold.setFontWeight(QtGui.QFont.Weight.Bold)
        choice = self.ui.comboBox_memos.currentText()
        for i, row in enumerate(self.results):
            self.heading(row)
            if row['result_type'] == 'text':
                cursor = self.ui.textEdit.textCursor()
                pos0 = len(self.ui.textEdit.toPlainText())
                self.ui.textEdit.insertPlainText("\n")
                self.ui.textEdit.insertPlainText(row['pretext'])
                pos1 = len(self.ui.textEdit.toPlainText())
                cursor.setPosition(pos0, QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(pos1, QtGui.QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(fmt_normal)
                pos0 = len(self.ui.textEdit.toPlainText())
                self.ui.textEdit.insertPlainText(row['text'])
                pos1 = len(self.ui.textEdit.toPlainText())
                cursor.setPosition(pos0, QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(pos1, QtGui.QTextCursor.MoveMode.KeepAnchor)
                if self.ui.checkBox_text_context.isChecked():
                    cursor.setCharFormat(fmt_bold)
                pos0 = len(self.ui.textEdit.toPlainText())
                self.ui.textEdit.insertPlainText(row['posttext'])
                pos1 = len(self.ui.textEdit.toPlainText())
                cursor.setPosition(pos0, QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(pos1, QtGui.QTextCursor.MoveMode.KeepAnchor)
                if self.ui.checkBox_text_context.isChecked():
                    cursor.setCharFormat(fmt_normal)
                self.ui.textEdit.insertPlainText("\n")
                if choice in ("All memos", "Code text memos") and row['coded_memo'] != "":
                    self.ui.textEdit.insertPlainText(_("Coded memo: ") + row['coded_memo'] + "\n")
            if row['result_type'] == 'image':
                self.put_image_into_textedit(row, i, self.ui.textEdit)
            if row['result_type'] == 'av':
                self.ui.textEdit.insertPlainText("\n" + row['text'] + "\n")
            self.text_links.append(row)
        self.eventFilterTT.set_positions(self.text_links)

        # Fill matrix or clear third splitter pane.
        self.ui.tableWidget.setColumnCount(0)
        self.ui.tableWidget.setRowCount(0)
        matrix_option = self.ui.comboBox_matrix.currentText()
        if matrix_option in ("Categories by case", "Top categories by case", "Codes by case") and self.case_ids == "":
            Message(self.app, _("No case matrix"), _("Cases not selected")).exec()
        if matrix_option in ("Categories by file", "Top categories by file", "Codes by file") and self.case_ids != "":
            Message(self.app, _("No file matrix"), _("Cases are selected")).exec()
        if matrix_option == "Categories by case" and self.case_ids != "":
            self.matrix_fill_by_categories(self.results, self.case_ids, "case")
        if matrix_option == "Categories by file" and self.case_ids == "":
            self.matrix_fill_by_categories(self.results, self.file_ids)
        if matrix_option == "Top categories by case" and self.case_ids != "":
            self.matrix_fill_by_top_categories(self.results, self.case_ids, "case")
        if matrix_option == "Top categories by file" and self.case_ids == "":
            self.matrix_fill_by_top_categories(self.results, self.file_ids)
        if matrix_option == "Codes by case" and self.case_ids != "":
            self.matrix_fill_by_codes(self.results, self.case_ids, "case")
        if matrix_option == "Codes by file" and self.case_ids == "":
            self.matrix_fill_by_codes(self.results, self.file_ids)

    def put_image_into_textedit(self, img, counter, text_edit):
        """ Scale image, add resource to document, insert image.
        """

        text_edit.append("\n")
        path_ = self.app.project_path + img['mediapath']
        if img['mediapath'][0:7] == "images:":
            path_ = img['mediapath'][7:]
        document = text_edit.document()
        image = QtGui.QImageReader(path_).read()
        image = image.copy(int(img['x1']), int(img['y1']), int(img['width']), int(img['height']))
        # Scale to max 300 wide or high. perhaps add option to change maximum limit?
        scaler_w = 1.0
        scaler_h = 1.0
        if image.width() > 300:
            scaler_w = 300 / image.width()
        if image.height() > 300:
            scaler_h = 300 / image.height()
        if scaler_w < scaler_h:
            scaler = scaler_w
        else:
            scaler = scaler_h
        # Need unique image names or the same image from the same path is reproduced
        # Default for an image  stored in the project folder.
        imagename = str(counter) + '-' + img['mediapath']
        # Check and change path for a linked image file
        if img['mediapath'][0:7] == "images:":
            imagename = str(counter) + '-' + "/images/" + img['mediapath'].split('/')[-1]
        # imagename is now: 0-/images/filename.jpg  # where 0- is the counter 1-, 2- etc

        url = QtCore.QUrl(imagename)
        document.addResource(QtGui.QTextDocument.ResourceType.ImageResource.value, url, image)
        cursor = text_edit.textCursor()
        image_format = QtGui.QTextImageFormat()
        image_format.setWidth(image.width() * scaler)
        image_format.setHeight(image.height() * scaler)
        image_format.setName(url.toString())
        cursor.insertImage(image_format)
        text_edit.insertHtml("<br />")
        self.html_links.append({'imagename': imagename, 'image': image,
                                'avname': None, 'av0': None, 'av1': None, 'avtext': None})
        if img['coded_memo'] != "":
            text_edit.insertPlainText(_("Memo: ") + img['coded_memo'] + "\n")

    def heading(self, item):
        """ Takes a dictionary item and creates a html heading for the coded text portion.
        Inserts the heading into the main textEdit.
        Fills the textedit_start and textedit_end link positions
        param:
            item: dictionary of code, file_or_casename, positions, text, coder
        """

        cur = self.app.conn.cursor()
        cur.execute("select name from source where id=?", [item['fid']])
        filename = ""
        res = cur.fetchone()
        if res is not None:
            filename = res[0]
        head = "\n" + _("[VIEW] ")
        head += item['codename'] + ", "
        choice = self.ui.comboBox_memos.currentText()
        if choice == "All memos" and item['codename_memo'] != "" and item['codename_memo'] is not None:
            head += _("Code memo: ") + item['codename_memo'] + "<br />"
        head += _("File: ") + filename + ", "
        if choice == "All memos" and item['source_memo'] != "" and item['source_memo'] is not None:
            head += _(" File memo: ") + item['source_memo']
        if item['file_or_case'] == 'Case':
            head += " " + _("Case: ") + item['file_or_casename']
            if choice == "All memos":
                cur = self.app.conn.cursor()
                cur.execute("select memo from cases where name=?", [item['file_or_casename']])
                res = cur.fetchone()
                if res is not None and res[0] != "" and res[0] is not None:
                    head += ", " + _("Case memo: ") + res[0]
        head += " " + _("Coder: ") + item['coder']

        cursor = self.ui.textEdit.textCursor()
        fmt = QtGui.QTextCharFormat()
        pos0 = len(self.ui.textEdit.toPlainText())
        item['textedit_start'] = pos0
        self.ui.textEdit.append(head)
        cursor.setPosition(pos0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        pos1 = len(self.ui.textEdit.toPlainText())
        cursor.setPosition(pos1, QtGui.QTextCursor.MoveMode.KeepAnchor)
        brush = QBrush(QtGui.QColor(item['color']))
        fmt.setBackground(brush)
        text_brush = QBrush(QtGui.QColor(TextColor(item['color']).recommendation))
        fmt.setForeground(text_brush)
        cursor.setCharFormat(fmt)
        item['textedit_end'] = len(self.ui.textEdit.toPlainText())

    def text_edit_menu(self, position):
        """ Context menu for textEdit.
        To view coded in context. """

        if self.ui.textEdit.toPlainText() == "":
            return
        cursor_context_pos = self.ui.textEdit.cursorForPosition(position)
        pos = cursor_context_pos.position()
        selected_text = self.ui.textEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")

        # Check that there is a link to view at this location before showing menu option
        action_view = None
        found = None
        for row in self.results:
            if pos >= row['textedit_start'] and pos < row['textedit_end']:
                found = True
                break
        if found:
            action_view = menu.addAction(_("View in context"))
        action_copy = None
        if selected_text != "":
            action_copy = menu.addAction(_("Copy to clipboard"))
        action_copy_all = menu.addAction(_("Copy all to clipboard"))
        action = menu.exec(self.ui.textEdit.mapToGlobal(position))
        if action is None:
            return
        if action == action_view:
            self.show_context_from_text_edit(cursor_context_pos)
        if action == action_copy:
            cb = QtWidgets.QApplication.clipboard()
            cb.setText(selected_text)
        if action == action_copy_all:
            cb = QtWidgets.QApplication.clipboard()
            te_text = self.ui.textEdit.toPlainText()
            cb.setText(te_text)

    def show_context_from_text_edit(self, cursor_context_pos):
        """ Heading (code, file, owner) in textEdit clicked so show context of coding in dialog.
        Called by: textEdit.cursorPositionChanged, after results are filled.
        text/image/av results contain textedit_start and textedit_end which map the cursor position to the specific result.
        Called by context menu.
        """

        pos = cursor_context_pos.position()
        for row in self.results:
            if pos >= row['textedit_start'] and pos < row['textedit_end']:
                if row['result_type'] == 'text':
                    ui = DialogCodeInText(self.app, row)
                    ui.exec()
                if row['result_type'] == 'image':
                    ui = DialogCodeInImage(self.app, row)
                    ui.exec()
                if row['result_type'] == 'av':
                    ui = DialogCodeInAV(self.app, row)
                    ui.exec()

    def matrix_heading(self, item, text_edit):
        """ Takes a dictionary item and creates a heading for the coded text portion.
        Also adds the textEdit start and end character positions for this text in this text edit
        param:
            item: dictionary of code, file_or_casename, positions, text, coder
        """

        cur = self.app.conn.cursor()
        cur.execute("select name from source where id=?", [item['fid']])
        filename = ""
        res = cur.fetchone()
        if res is not None:
            filename = res[0]
        choice = self.ui.comboBox_memos.currentText()
        head = "\n" + _("[VIEW] ")
        head += item['codename'] + ", "
        if choice == "All memos" and item['codename_memo'] != "":
            head += _("Code memo: ") + item['codename_memo'] + "<br />"
        head += _("File: ") + filename + ", "
        if choice == "All memos" and item['source_memo'] != "":
            head += _(" File memo: ") + item['source_memo']
        if item['file_or_case'] == 'Case:':
            head += " " + item['file_or_case'] + ": " + item['file_or_casename'] + ", "
            if choice == "All memos":
                cur = self.app.conn.cursor()
                cur.execute("select memo from cases where name=?", [item['file_or_casename']])
                res = cur.fetchone()
                if res is not None and res != "":
                    head += ", " + _("Case memo: ") + res[0]
        head += item['coder']
        cursor = text_edit.textCursor()
        fmt = QtGui.QTextCharFormat()
        pos0 = len(text_edit.toPlainText())
        item['textedit_start'] = pos0
        text_edit.append(head)
        cursor.setPosition(pos0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        pos1 = len(text_edit.toPlainText())
        cursor.setPosition(pos1, QtGui.QTextCursor.MoveMode.KeepAnchor)
        brush = QBrush(QtGui.QColor(item['color']))
        fmt.setBackground(brush)
        text_brush = QBrush(QtGui.QColor(TextColor(item['color']).recommendation))
        fmt.setForeground(text_brush)
        cursor.setCharFormat(fmt)
        item['textedit_end'] = len(text_edit.toPlainText())

    def matrix_fill_by_codes(self, results_, ids, type_="file"):
        """ Fill a tableWidget with rows of cases and columns of codes.
        First identify all codes.
        Fill tableWidget with columns of codes and rows of cases.
        Called by: fill_text_edit_with_search_results
        param:
            text_results : list of dictionary text result items
            image_results : list of dictionary image result items
            av_results : list of dictionary av result items
            ids : list of case ids OR file ids - as a string of integers, comma separated
            type_ : 'file' or 'case'
        """

        # Do not overwrite positions in original text_links object
        results = deepcopy(results_)
        # Get selected codes (Matrix columns)
        items = self.ui.treeWidget.selectedItems()
        horizontal_labels = []  # column (code) labels
        for item in items:
            if item.text(1)[:3] == "cid":
                horizontal_labels.append(item.text(0))

        # Get cases (rows)
        cur = self.app.conn.cursor()
        sql = "select distinct id, name from source where id in (" + ids + ") order by name"
        if type_ == "case":
            sql = "select caseid, name from cases where caseid in (" + ids + ")"
        cur.execute(sql)
        id_and_name = cur.fetchall()
        vertical_labels = []
        for c in id_and_name:
            vertical_labels.append(c[1])

        transpose = self.ui.checkBox_matrix_transpose.isChecked()
        if transpose:
            vertical_labels, horizontal_labels = horizontal_labels, vertical_labels

        # Clear and fill tableWidget
        doc_font = 'font: ' + str(self.app.settings['docfontsize']) + 'pt '
        doc_font += '"' + self.app.settings['font'] + '";'
        self.ui.tableWidget.setStyleSheet(doc_font)
        self.ui.tableWidget.setColumnCount(len(horizontal_labels))
        self.ui.tableWidget.setHorizontalHeaderLabels(horizontal_labels)
        self.ui.tableWidget.setRowCount(len(vertical_labels))
        self.ui.tableWidget.setVerticalHeaderLabels(vertical_labels)
        # Need to create a table of separate textEdits for reference for cursorPositionChanged event.
        self.te = []
        for _ in vertical_labels:
            column_list = []
            for _ in horizontal_labels:
                tedit = QtWidgets.QTextEdit("")
                tedit.setReadOnly(True)
                tedit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                tedit.customContextMenuRequested.connect(self.table_text_edit_menu)
                column_list.append(tedit)
            self.te.append(column_list)
        self.matrix_links = []
        choice = self.ui.comboBox_memos.currentText()
        if transpose:
            for row in range(len(vertical_labels)):
                for col in range(len(horizontal_labels)):
                    for counter, r in enumerate(results):
                        if r['file_or_casename'] == horizontal_labels[col] and r['codename'] == vertical_labels[row]:
                            r['row'] = row
                            r['col'] = col
                            self.te[row][col].insertHtml(self.matrix_heading(r, self.te[row][col]))
                            if r['result_type'] == 'text':
                                self.te[row][col].append(r['text'])
                                if choice in ("All memos", "Code text memos") and r['coded_memo'] != "":
                                    self.te[row][col].append(_("Coded memo: ") + r['coded_memo'])
                                self.te[row][col].insertPlainText("\n")
                            if r['result_type'] == 'image':
                                self.put_image_into_textedit(r, counter, self.te[row][col])
                            if r['result_type'] == 'av':
                                self.te[row][col].insertPlainText(r['text'] + "\n")
                            self.matrix_links.append(r)
                    self.ui.tableWidget.setCellWidget(row, col, self.te[row][col])
        else:
            for row in range(len(vertical_labels)):
                for col in range(len(horizontal_labels)):
                    for counter, r in enumerate(results):
                        if r['file_or_casename'] == vertical_labels[row] and r['codename'] == horizontal_labels[col]:
                            r['row'] = row
                            r['col'] = col
                            self.te[row][col].insertHtml(self.matrix_heading(r, self.te[row][col]))
                            if r['result_type'] == 'text':
                                self.te[row][col].append(r['text'])
                                if choice in ("All memos", "Code text memos") and r['coded_memo'] != "":
                                    self.te[row][col].append(_("Coded memo: ") + r['coded_memo'])
                                self.te[row][col].insertPlainText("\n")
                            if r['result_type'] == 'image':
                                self.put_image_into_textedit(r, counter, self.te[row][col])
                            if r['result_type'] == 'av':
                                self.te[row][col].insertPlainText(r['text'] + "\n")
                            self.matrix_links.append(r)
                    self.ui.tableWidget.setCellWidget(row, col, self.te[row][col])
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.resizeColumnsToContents()
        # Maximise the space from one column or one row
        if self.ui.tableWidget.columnCount() == 1:
            self.ui.tableWidget.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        if self.ui.tableWidget.rowCount() == 1:
            self.ui.tableWidget.verticalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.ui.splitter.setSizes([100, 300, 300])

    def matrix_fill_by_categories(self, results_, ids, type_="file"):
        """ Fill a tableWidget with rows of case or file name and columns of categories.
        First identify the categories. Then map all codes which are directly assigned to the categories.
        Called by: fill_text_edit_with_search_results
        param:
            text_results : list of dictionary text result items
            image_results : list of dictionary image result items
            av_results : list of dictionary av result items
            ids : list of case ids OR file ids, as string of comma separated integers
            type_ : file or case ids
        """

        # Do not overwrite positions in original text_links object
        results = deepcopy(results_)
        # All categories within selection
        items = self.ui.treeWidget.selectedItems()
        top_level = []  # the categories at any level
        horizontal_labels = []
        sub_codes = []
        for item in items:
            if item.text(1)[0:3] == "cat":
                top_level.append({'name': item.text(0), 'cat': item.text(1)})
                horizontal_labels.append(item.text(0))
            # Find sub-code and traverse upwards to map to category
            if item.text(1)[0:3] == 'cid':
                sub_code = {'codename': item.text(0), 'cid': item.text(1)}
                # May be None of a top level code - as this will have no parent
                if item.parent() is not None:
                    sub_code['top'] = item.parent().text(0)
                    sub_codes.append(sub_code)
                    add_cat = True
                    for tl in top_level:
                        if tl['name'] == item.parent().text(0):
                            add_cat = False
                    if add_cat:
                        top_level.append({'name': item.parent().text(0), 'cat': item.parent().text(1)})
                        horizontal_labels.append(item.parent().text(0))

        # Add category name - which will match the tableWidget column category name
        res_categories = []
        for i in results:
            # Replaces the top-level name by mapping to the correct top-level category name (column)
            # Codes will not have 'top' key
            for s in sub_codes:
                if i['codename'] == s['codename']:
                    i['top'] = s['top']
            if "top" in i:
                res_categories.append(i)
        cur = self.app.conn.cursor()
        sql = "select distinct id, name from source where id in (" + ids + ") order by name"
        if type_ == "case":
            sql = "select caseid, name from cases where caseid in (" + ids + ")"
        cur.execute(sql)
        id_and_name = cur.fetchall()
        vertical_labels = []
        for c in id_and_name:
            vertical_labels.append(c[1])
        transpose = self.ui.checkBox_matrix_transpose.isChecked()
        if transpose:
            vertical_labels, horizontal_labels = horizontal_labels, vertical_labels

        # Clear and fill the tableWidget
        doc_font = 'font: ' + str(self.app.settings['docfontsize']) + 'pt '
        doc_font += '"' + self.app.settings['font'] + '";'
        self.ui.tableWidget.setStyleSheet(doc_font)
        self.ui.tableWidget.setColumnCount(len(horizontal_labels))
        self.ui.tableWidget.setHorizontalHeaderLabels(horizontal_labels)
        self.ui.tableWidget.setRowCount(len(id_and_name))
        self.ui.tableWidget.setVerticalHeaderLabels(vertical_labels)
        # Need to create a table of separate textEdits for reference for cursorPositionChanged event.
        self.te = []
        choice = self.ui.comboBox_memos.currentText()
        for _ in id_and_name:
            column_list = []
            for _ in horizontal_labels:
                tedit = QtWidgets.QTextEdit("")
                tedit.setReadOnly(True)
                tedit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                tedit.customContextMenuRequested.connect(self.table_text_edit_menu)
                column_list.append(tedit)
            self.te.append(column_list)
        self.matrix_links = []

        if transpose:
            for row in range(len(vertical_labels)):
                for col in range(len(horizontal_labels)):
                    self.te[row][col].setReadOnly(True)
                    for counter, r in enumerate(res_categories):
                        if r['file_or_casename'] == horizontal_labels[col] and r['top'] == vertical_labels[row]:
                            r['row'] = row
                            r['col'] = col
                            self.te[row][col].insertHtml(self.matrix_heading(r, self.te[row][col]))
                            if r['result_type'] == 'text':
                                self.te[row][col].append(r['text'])
                                if choice in ("All memos", "Code text memos") and r['coded_memo'] != "":
                                    self.te.append(_("Coded memo: ") + r['coded_memo'])
                            if r['result_type'] == 'image':
                                self.put_image_into_textedit(r, counter, self.te[row][col])
                            if r['result_type'] == 'av':
                                self.te[row][col].append(r['text'] + "\n")
                            self.te[row][col].insertPlainText("\n")
                            self.matrix_links.append(r)
                    self.ui.tableWidget.setCellWidget(row, col, self.te[row][col])
        else:
            for row in range(len(vertical_labels)):
                for col in range(len(horizontal_labels)):
                    self.te[row][col].setReadOnly(True)
                    for counter, r in enumerate(res_categories):
                        if r['file_or_casename'] == vertical_labels[row] and r['top'] == horizontal_labels[col]:
                            r['row'] = row
                            r['col'] = col
                            self.te[row][col].insertHtml(self.matrix_heading(r, self.te[row][col]))
                            if r['result_type'] == 'text':
                                self.te[row][col].append(r['text'])
                                if choice in ("All memos", "Code text memos") and r['coded_memo'] != "":
                                    self.te.append(_("Coded memo: ") + r['coded_memo'])
                            if r['result_type'] == 'image':
                                self.put_image_into_textedit(r, counter, self.te[row][col])
                            if r['result_type'] == 'av':
                                self.te[row][col].append(r['text'] + "\n")
                            self.te[row][col].insertPlainText("\n")
                            self.matrix_links.append(r)
                    self.ui.tableWidget.setCellWidget(row, col, self.te[row][col])
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.resizeColumnsToContents()
        # Maximise the space from one column or one row
        if self.ui.tableWidget.columnCount() == 1:
            self.ui.tableWidget.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        if self.ui.tableWidget.rowCount() == 1:
            self.ui.tableWidget.verticalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.ui.splitter.setSizes([100, 300, 300])

    def matrix_fill_by_top_categories(self, results_, ids, type_="file"):
        """ Fill a tableWidget with rows of case or file name and columns of top level categories.
        First identify top-level categories. Then map all other codes to the
        top-level categories.
        Called by: fill_text_edit_with_search_results
        param:
            text_results : list of dictionary text result items
            image_results : list of dictionary image result items
            av_results : list of dictionary av result items
            ids : string list of case ids or file ids, comma separated
            type_ : file or case
        """

        # Do not overwrite positions in original text_links object
        results = deepcopy(results_)

        # Get top level categories
        items = self.ui.treeWidget.selectedItems()
        top_level = []
        horizontal_labels = []
        sub_codes = []
        for item in items:
            root = self.ui.treeWidget.indexOfTopLevelItem(item)
            if root > -1 and item.text(1)[0:3] == "cat":
                top_level.append({'name': item.text(0), 'cat': item.text(1)})
                horizontal_labels.append(item.text(0))
            # Find sub-code and traverse upwards to map to top-level category
            if root == -1 and item.text(1)[0:3] == 'cid':
                not_top = True
                sub_code = {'codename': item.text(0), 'cid': item.text(1)}
                top_id = None
                while not_top:
                    item = item.parent()
                    if self.ui.treeWidget.indexOfTopLevelItem(item) > -1:
                        not_top = False
                        sub_code['top'] = item.text(0)
                        top_id = item.text(1)
                        sub_codes.append(sub_code)
                add_cat = True
                for tl in top_level:
                    if tl['name'] == sub_code['top']:
                        add_cat = False
                if add_cat and top_id is not None:
                    top_level.append({'name': sub_code['top'], 'cat': top_id})
                    horizontal_labels.append(sub_code['top'])

        # Add the top-level name - which will match the tableWidget column category name
        res_categories = []
        for i in results:
            # Replaces the top-level name by mapping to the correct top-level category name (column)
            # Codes will not have 'top' key
            for s in sub_codes:
                if i['codename'] == s['codename']:
                    i['top'] = s['top']
            if "top" in i:
                res_categories.append(i)

        cur = self.app.conn.cursor()
        sql = "select distinct id, name from source where id in (" + ids + ") order by name"
        if type_ == "case":
            sql = "select caseid, name from cases where caseid in (" + ids + ")"
        cur.execute(sql)
        id_and_name = cur.fetchall()
        vertical_labels = []
        for c in id_and_name:
            vertical_labels.append(c[1])

        transpose = self.ui.checkBox_matrix_transpose.isChecked()
        if transpose:
            vertical_labels, horizontal_labels = horizontal_labels, vertical_labels

        # Clear and fill the tableWidget
        doc_font = 'font: ' + str(self.app.settings['docfontsize']) + 'pt '
        doc_font += '"' + self.app.settings['font'] + '";'
        self.ui.tableWidget.setStyleSheet(doc_font)
        self.ui.tableWidget.setColumnCount(len(horizontal_labels))
        self.ui.tableWidget.setHorizontalHeaderLabels(horizontal_labels)
        self.ui.tableWidget.setRowCount(len(id_and_name))
        self.ui.tableWidget.setVerticalHeaderLabels(vertical_labels)
        # Need to create a table of separate textEdits for reference for cursorPositionChanged event.
        self.te = []
        for _ in id_and_name:
            column_list = []
            for _ in horizontal_labels:
                tedit = QtWidgets.QTextEdit("")
                tedit.setReadOnly(True)
                tedit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                tedit.customContextMenuRequested.connect(self.table_text_edit_menu)
                column_list.append(tedit)
            self.te.append(column_list)
        self.matrix_links = []
        choice = self.ui.comboBox_memos.currentText()

        if transpose:
            for row in range(len(vertical_labels)):
                for col in range(len(horizontal_labels)):
                    self.te[row][col].setReadOnly(True)
                    for counter, r in enumerate(res_categories):
                        if r['file_or_casename'] == horizontal_labels[col] and r['top'] == vertical_labels[row]:
                            r['row'] = row
                            r['col'] = col
                            self.te[row][col].insertHtml(self.matrix_heading(r, self.te[row][col]))
                            self.matrix_links.append(r)
                            if r['result_type'] == 'text':
                                self.te[row][col].append(r['text'])
                                if choice in ("All memos", "Code text memos") and r['coded_memo'] != "":
                                    self.te[row][col].append(_("Coded memo: ") + r['coded_memo'])
                            if r['result_type'] == 'image':
                                self.put_image_into_textedit(r, counter, self.te[row][col])
                            if r['result_type'] == 'av':
                                self.te[row][col].append(r['text'] + "\n")  # The time duration
                            self.te[row][col].insertPlainText("\n")
                    self.ui.tableWidget.setCellWidget(row, col, self.te[row][col])
        else:
            for row in range(len(vertical_labels)):
                for col in range(len(horizontal_labels)):
                    self.te[row][col].setReadOnly(True)
                    for counter, r in enumerate(res_categories):
                        if r['file_or_casename'] == vertical_labels[row] and r['top'] == horizontal_labels[col]:
                            r['row'] = row
                            r['col'] = col
                            self.te[row][col].insertHtml(self.matrix_heading(r, self.te[row][col]))
                            self.matrix_links.append(r)
                            if r['result_type'] == 'text':
                                self.te[row][col].append(r['text'])
                                if choice in ("All memos", "Code text memos") and r['coded_memo'] != "":
                                    self.te[row][col].append(_("Coded memo: ") + r['coded_memo'])
                            if r['result_type'] == 'image':
                                self.put_image_into_textedit(r, counter, self.te[row][col])
                            if r['result_type'] == 'av':
                                self.te[row][col].append(r['text'] + "\n")  # The time duration
                            self.te[row][col].insertPlainText("\n")
                    self.ui.tableWidget.setCellWidget(row, col, self.te[row][col])
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.resizeColumnsToContents()
        # Maximise the space from one column or one row
        if self.ui.tableWidget.columnCount() == 1:
            self.ui.tableWidget.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        if self.ui.tableWidget.rowCount() == 1:
            self.ui.tableWidget.verticalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.ui.splitter.setSizes([100, 300, 300])

    def table_text_edit_menu(self, position):
        """ Context menu for textEdit.
        To view coded in context. """

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        te = self.te[x][y]
        te_text = te.toPlainText()
        if te_text == "":
            return
        cursor_context_pos = te.cursorForPosition(position)
        pos = cursor_context_pos.position()
        selected_text = te.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")

        # Check that there is a link to view at this location before showing menu option
        action_view = None
        found = None
        for m in self.matrix_links:
            if m['row'] == x and m['col'] == y and pos >= m['textedit_start'] and pos < m['textedit_end']:
                found = True
        if found:
            action_view = menu.addAction(_("View in context"))
        action_copy = None
        if selected_text != "":
            action_copy = menu.addAction(_("Copy to clipboard"))
        action_copy_all = menu.addAction(_("Copy all to clipboard"))
        action = menu.exec(te.mapToGlobal(position))
        if action is None:
            return
        if action == action_copy:
            cb = QtWidgets.QApplication.clipboard()
            cb.setText(selected_text)
        if action == action_copy_all:
            cb = QtWidgets.QApplication.clipboard()
            te_text = te.toPlainText()
            cb.setText(te_text)
        if action == action_view:
            for m in self.matrix_links:
                if m['row'] == x and m['col'] == y and pos >= m['textedit_start'] and pos < m['textedit_end']:
                    if 'mediapath' not in m:
                        ui = DialogCodeInText(self.app, m)
                        ui.exec()
                        return
                    if m['mediapath'][0:7] in ('images:', '/images'):
                        ui = DialogCodeInImage(self.app, m)
                        ui.exec()
                        return
                    if m['mediapath'][0:6] in ('audio:', 'video:', '/audio', '/video'):
                        ui = DialogCodeInAV(self.app, m)
                        ui.exec()
                        return


class ToolTipEventFilter(QtCore.QObject):
    """ Used to add a dynamic tooltip for the textBrowser.
    The tool top text is presented according to its position in the text.
    """

    media_data = None

    def set_positions(self, media_data):
        """ Code_text contains the positions for the tooltip to be displayed.

        param:
            media_data: List of dictionaries of the text contains: pos0, pos1
        """

        self.media_data = media_data

    def eventFilter(self, receiver, event):
        if event.type() == QtCore.QEvent.Type.ToolTip:
            cursor = receiver.cursorForPosition(event.pos())
            pos = cursor.position()
            receiver.setToolTip("")
            if self.media_data is None:
                return super(ToolTipEventFilter, self).eventFilter(receiver, event)
            for item in self.media_data:
                if item['textedit_start'] <= pos and item['textedit_end'] >= pos:
                    receiver.setToolTip(_("Right click to view"))
        # Call Base Class Method to Continue Normal Event Processing
        return super(ToolTipEventFilter, self).eventFilter(receiver, event)
