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

import datetime
import os
import re
import sys
import logging
import traceback

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import Qt


from .GUI.ui_case_file_manager import Ui_Dialog_case_file_manager
from .confirm_delete import DialogConfirmDelete
from .helpers import DialogGetStartAndEndMarks, Message
from .view_av import DialogViewAV
from .view_image import DialogViewImage

ID = 0
NAME = 1
FULLTEXT = 2
MEDIAPATH = 3
MEMO = 4
OWNER = 5
DATE = 6

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class DialogCaseFileManager(QtWidgets.QDialog):
    """ Dialog to manipulate files for a case.
    Add files to case, add all text or text portions from a text file.
    Remove file from a case. View file.
    """

    app = None
    parent_textEdit = None
    case = None
    allfiles = []
    casefiles = []
    case_text = []
    selected_text_file = None

    def __init__(self, app_, parent_textEdit, case):

        sys.excepthook = exception_handler
        self.app = app_
        self.parent_textEdit = parent_textEdit
        self.case = case
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_case_file_manager()
        self.ui.setupUi(self)
        try:
            w = int(self.app.settings['dialogcasefilemanager_w'])
            h = int(self.app.settings['dialogcasefilemanager_h'])
            if h > 50 and w > 50:
                self.resize(w, h)
        except KeyError:
            pass
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        font2 = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        font2 += '"' + self.app.settings['font'] + '";'
        self.ui.tableWidget.setStyleSheet(font2)
        self.ui.tableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.ui.tableWidget.doubleClicked.connect(self.double_clicked_to_view)
        self.ui.tableWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableWidget.customContextMenuRequested.connect(self.table_menu)
        self.ui.label_case.setText(_("Case: ") + self.case['name'])
        self.ui.pushButton_view.clicked.connect(self.view_file)
        self.ui.pushButton_auto_assign.clicked.connect(self.automark)
        self.ui.pushButton_add_files.clicked.connect(self.add_files_to_case)
        self.ui.pushButton_remove.clicked.connect(self.remove_files_from_case)
        self.ui.textBrowser.setText("")
        self.ui.textBrowser.setAutoFillBackground(True)
        self.ui.textBrowser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.textBrowser.customContextMenuRequested.connect(self.textBrowser_menu)
        self.ui.textBrowser.setOpenLinks(False)
        try:
            s0 = int(self.app.settings['dialogcasefilemanager_splitter0'])
            s1 = int(self.app.settings['dialogcasefilemanager_splitter1'])
            if s0 > 10 and s1 > 10:
                self.ui.splitter.setSizes([s0, s1])
        except KeyError:
            pass
        self.get_files()
        self.fill_table()

    def closeEvent(self, event):
        """ Save dialog and splitter dimensions. """

        self.app.settings['dialogcasefilemanager_w'] = self.size().width()
        self.app.settings['dialogcasefilemanager_h'] = self.size().height()
        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogcasefilemanager_splitter0'] = sizes[0]
        self.app.settings['dialogcasefilemanager_splitter1'] = sizes[1]

    def get_files(self):
        """ Get files for this case. """

        cur = self.app.conn.cursor()
        sql = "select distinct case_text.fid, source.name from case_text join source on case_text.fid=source.id where "
        sql += "caseid=? order by lower(source.name) asc"
        cur.execute(sql, [self.case['caseid'], ])
        self.casefiles = cur.fetchall()
        sql = "select id, name, fulltext, mediapath, memo, owner, date from  source order by source.name asc"
        cur.execute(sql)
        self.allfiles = cur.fetchall()
        msg = _("Files linked: ") + str(len(self.casefiles)) + " / " + str(len(self.allfiles))
        self.ui.label_files_linked.setText(msg)

    def table_menu(self, position):
        """ Context menu to add/remove files to case. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_add = menu.addAction(_("Add files to case"))
        action_remove = menu.addAction(_("Remove files from case"))
        action = menu.exec(self.ui.tableWidget.mapToGlobal(position))
        if action == action_add:
            self.add_files_to_case()
        if action == action_remove:
            self.remove_files_from_case()

    def add_files_to_case(self):
        """ When select file button is pressed a dialog of filenames is presented to the user.
        The entire text of the selected files is then added to the selected case.
        """

        index_list = self.ui.tableWidget.selectionModel().selectedIndexes()
        rows = []
        for i in index_list:
            rows.append(i.row())
        rows = list(set(rows))  # duplicate rows due to multiple columns
        if len(rows) == 0:
            return
        selected_files = []
        for r in rows:
            selected_files.append(self.allfiles[r])
        msg = ""
        for file_ in selected_files:
            msg += self.add_file_to_case(file_)
        # Update messages and table widget
        self.get_files()
        self.fill_table()
        Message(self.app, _("File added to case"), msg, "information").exec()
        self.parent_textEdit.append(msg)
        self.app.delete_backup = False

    def add_file_to_case(self, file_):
        """ The entire text of the selected file is added to the selected case.
        Also a non-text file is linked to to the case here. The text positions will be 0 and 0.
        param:
            file_: tuple of id, name,fulltext, mediapath, memo, owner, date
        return:
            msg: string message for link process or error
        """

        cur = self.app.conn.cursor()
        text_len = 0
        if file_[2] is not None:
            text_len = len(file_[2]) - 1
        link = {'caseid': self.case['caseid'], 'fid': file_[0], 'pos0': 0,
            'pos1': text_len, 'owner': self.app.settings['codername'],
            'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'memo': ""}

        # Check for an existing duplicated linked file first
        cur.execute("select * from case_text where caseid = ? and fid=? and pos0=? and pos1=?",
            (link['caseid'], link['fid'], link['pos0'], link['pos1']))
        result = cur.fetchall()
        if len(result) > 0:
            msg = _("This file has already been linked to this case ") + file_[1] + "\n"
            return msg
        # Even non-text files can be assigned to the case here
        sql = "insert into case_text (caseid, fid, pos0, pos1, owner, date, memo) values(?,?,?,?,?,?,?)"
        cur.execute(sql, (link['caseid'], link['fid'], link['pos0'], link['pos1'],
            link['owner'], link['date'], link['memo']))
        self.app.conn.commit()
        msg = file_[1] + _(" added to case.") + "\n"
        return msg

    def remove_files_from_case(self):
        """ Remove selected files from case. """

        index_list = self.ui.tableWidget.selectionModel().selectedIndexes()
        rows = []
        for i in index_list:
            rows.append(i.row())
        rows = list(set(rows))  # duplicate rows due to multiple columns
        if len(rows) == 0:
            return
        selected_files = []
        remove_msg = ""
        for r in rows:
            selected_files.append(self.allfiles[r])
            remove_msg += "\n" + self.allfiles[r][1]
        del_ui = DialogConfirmDelete(self.app, remove_msg)
        ok = del_ui.exec()
        if not ok:
            return
        cur = self.app.conn.cursor()
        sql = "delete from case_text where caseid=? and fid=?"
        for f in selected_files:
            try:
                cur.execute(sql, [self.case['caseid'], f[0]])
                self.app.conn.commit()
                self.parent_textEdit.append(f[1] + " removed from case " + self.case['name'])
            except Exception as e:
                print(e)
                logger.debug(str(e))
        # Update assigned files and table widget
        self.get_files()
        self.fill_table()
        self.app.delete_backup = False

    def fill_table(self):
        """ Fill list widget with file details. """

        rows = self.ui.tableWidget.rowCount()
        for c in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        header_labels = ["id", "File name", "Assigned"]
        self.ui.tableWidget.setColumnCount(len(header_labels))
        self.ui.tableWidget.setHorizontalHeaderLabels(header_labels)

        for row, f in enumerate(self.allfiles):
            self.ui.tableWidget.insertRow(row)
            item = QtWidgets.QTableWidgetItem(str(f[0]))
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget.setItem(row, 0, item)
            item = QtWidgets.QTableWidgetItem(f[1])
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget.setItem(row, 1, item)
            # Mark Yes if assigned
            assigned = ""
            for i in self.casefiles:
                if f[0] == i[0]:
                    assigned = _("Yes")
            item = QtWidgets.QTableWidgetItem(assigned)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget.setItem(row, 2, item)

        self.ui.tableWidget.hideColumn(0)
        if self.app.settings['showids'] == 'True':
            self.ui.tableWidget.showColumn(0)
        self.ui.tableWidget.resizeColumnsToContents()

    def double_clicked_to_view(self):
        """ Double click on a row allow viewing of that file.
        rows begin at 0  to n.
        param:
            row: signal emitted by doubleclick event """

        # TODO need this method? better in init to go to view_file
        self.view_file()

    def view_file(self):
        """ View text file in qTextBrowser, or open image or media file.
         Check media file link works, as media may have moved. """

        index_list = self.ui.tableWidget.selectionModel().selectedIndexes()
        index = None
        if len(index_list) > 0:
            index = index_list[0].row()
        if index is None:
            return
        self.ui.textBrowser.setText("")
        self.ui.tableWidget.selectRow(index)
        self.selected_text_file = None
        # A fulltext source is displayed if fulltext is present
        # If the mediapath is None, this represents an A/V transcribed file
        self.ui.label_file.setText(_("Displayed file: ") + self.allfiles[index][NAME])
        if self.allfiles[index][FULLTEXT] != "" and self.allfiles[index][FULLTEXT] is not None:
            self.selected_text_file = self.allfiles[index]
            self.ui.textBrowser.setText(self.allfiles[index][FULLTEXT])
            self.load_case_text()
            self.unlight()
            self.highlight()
            return
        # need the data as a dictionary to view images and audio/video
        dictionary = {'name': self.allfiles[index][NAME], 'mediapath': self.allfiles[index][MEDIAPATH],
                      'owner': self.allfiles[index][OWNER], 'id': self.allfiles[index][0],
                      'date': self.allfiles[index][DATE],
                      'memo': self.allfiles[index][MEMO], 'fulltext': self.allfiles[index][FULLTEXT]}
        # Mediapath will be None for a .transcribed empty text media entry, and 'docs:' for a linked text document
        if self.allfiles[index][MEDIAPATH] is None or self.allfiles[index][MEDIAPATH][0:5] == 'docs:':
            return
        # Added checks to test for media presence
        if self.allfiles[index][MEDIAPATH][:6] in ("/video", "video:"):
            if self.allfiles[index][MEDIAPATH][:6] == "video:":
                abs_path = self.allfiles[index][MEDIAPATH].split(':')[1]
                if not os.path.exists(abs_path):
                    return
            if self.allfiles[index][MEDIAPATH][:6] == "/video":
                abs_path = self.app.project_path + self.allfiles[index][MEDIAPATH]
                if not os.path.exists(abs_path):
                    return
            ui_av = DialogViewAV(self.app, dictionary)
            ui_av.exec()
        if self.allfiles[index][MEDIAPATH][:6] in ("/audio", "audio:"):
            if self.allfiles[index][MEDIAPATH][0:6] == "audio:":
                abs_path = self.allfiles[index][MEDIAPATH].split(':')[1]
                if not os.path.exists(abs_path):
                    return
            if self.allfiles[index][MEDIAPATH][0:6] == "/audio":
                abs_path = self.app.project_path + self.allfiles[index][MEDIAPATH]
                if not os.path.exists(abs_path):
                    return
            ui_av = DialogViewAV(self.app, dictionary)
            ui_av.exec()
        if self.allfiles[index][MEDIAPATH][:7] in ("/images", "images:"):
            if self.allfiles[index][MEDIAPATH][0:7] == "images:":
                abs_path = self.allfiles[index][MEDIAPATH].split(':')[1]
                if not os.path.exists(abs_path):
                    return
            if self.allfiles[index][MEDIAPATH][0:7] == "/images":
                abs_path = self.app.project_path + self.allfiles[index][MEDIAPATH]
                if not os.path.exists(abs_path):
                    return
            # Requires {name, mediapath, owner, id, date, memo, fulltext}
            ui_img = DialogViewImage(self.app, dictionary)
            ui_img.exec()

    def load_case_text(self):
        """ Load case text for selected_text_file """

        self.case_text = []
        if self.selected_text_file is None:
            return
        cur = self.app.conn.cursor()
        cur.execute("select caseid, fid, pos0, pos1, owner, date, memo from case_text where fid = ? and caseid = ?",
            [self.selected_text_file[ID], self.case['caseid']])
        result = cur.fetchall()
        for row in result:
            self.case_text.append({'caseid': row[0], 'fid': row[1], 'pos0': row[2],
                'pos1': row[3], 'owner': row[4], 'date': row[5], 'memo': row[6]})

    def textBrowser_menu(self, position):
        """ Context menu for textBrowser. Mark, unmark, copy, select all. """

        if self.ui.textBrowser.toPlainText() == "":
            return
        cursor = self.ui.textBrowser.cursorForPosition(position)
        selected_text = self.ui.textBrowser.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_select_all = None
        action_mark = None
        action_unmark = None
        action_copy = None
        if selected_text == "":
            action_select_all = menu.addAction(_("Select all"))
        if selected_text != "" and not self.is_marked():
            action_mark = menu.addAction(_("Mark"))
        if selected_text != "":
            action_copy = menu.addAction(_("Copy"))
        for item in self.case_text:
            if cursor.position() >= item['pos0'] and cursor.position() <= item['pos1']:
                action_unmark = menu.addAction(_("Unmark"))
                break
        action = menu.exec(self.ui.textBrowser.mapToGlobal(position))
        if action is None:
            return
        if action == action_mark:
            self.mark()
        if action == action_unmark:
            self.unmark(position)
        if action == action_copy:
            self.copy_selected_text_to_clipboard()
        if action == action_select_all:
            self.ui.textBrowser.selectAll()

    def is_marked(self):
        """ Check current text selection and return False if not marked and True if marked. """

        pos0 = self.ui.textBrowser.textCursor().selectionStart()
        pos1 = self.ui.textBrowser.textCursor().selectionEnd()
        for c in self.case_text:
            if pos0 >= c['pos0'] and pos0 <= c['pos1']:
                return True
            if pos1 >= c['pos0'] and pos1 <= c['pos1']:
                return True
        return False

    def copy_selected_text_to_clipboard(self):

        selected_text = self.ui.textBrowser.textCursor().selectedText()
        cb = QtWidgets.QApplication.clipboard()
        cb.setText(selected_text)

    def unlight(self):
        """ Remove all text highlighting from current file. """

        if self.selected_text_file is None:
            return
        if self.selected_text_file[FULLTEXT] is None:
            return
        cursor = self.ui.textBrowser.textCursor()
        try:
            cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(len(self.selected_text_file[FULLTEXT]) - 1, QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(QtGui.QTextCharFormat())
        except Exception as e:
            logger.debug((str(e) + "\n unlight, text length" + str(len(self.ui.textBrowser.toPlainText()))))

    def highlight(self):
        """ Apply text highlighting to current file.
        Highlight text of selected case with red underlining.
        #format_.setForeground(QtGui.QColor("#990000")) """

        if self.selected_text_file is None:
            return
        if self.selected_text_file[FULLTEXT] is None:
            return
        format_ = QtGui.QTextCharFormat()
        cursor = self.ui.textBrowser.textCursor()
        for item in self.case_text:
            try:
                cursor.setPosition(int(item['pos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['pos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.red)
                cursor.setCharFormat(format_)
            except:
                msg = "highlight, text length " + str(len(self.ui.textBrowser.toPlainText()))
                msg += "\npos0:" + str(item['pos0']) + ", pos1:" + str(item['pos1'])
                logger.debug(msg)

    def mark(self):
        """ Mark selected text in file with this case. """

        if self.selected_text_file is None:
            return
        # selectedText = self.textBrowser.textCursor().selectedText()
        pos0 = self.ui.textBrowser.textCursor().selectionStart()
        pos1 = self.ui.textBrowser.textCursor().selectionEnd()
        if pos0 == pos1:
            return
        # add new item to case_text list and database and update GUI
        item = {'caseid': self.case['caseid'],
                'fid': self.selected_text_file[ID],
                'pos0': pos0, 'pos1': pos1,
                'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                'memo': ""}
        self.case_text.append(item)
        self.highlight()

        cur = self.app.conn.cursor()
        # Check for an existing duplicated linkage first
        cur.execute("select * from case_text where caseid=? and fid=? and pos0<=? and pos1>=?",
                    (item['caseid'], item['fid'], item['pos0'], item['pos1']))
        result = cur.fetchall()
        if len(result) > 0:
            Message(self.app, _("Already Linked"),
                _("This segment has already been linked to this case"), "warning").exec()
            return
        cur.execute("insert into case_text (caseid,fid, pos0, pos1, owner, date, memo) values(?,?,?,?,?,?,?)",
                (item['caseid'], item['fid'], item['pos0'], item['pos1'], item['owner'], item['date'], item['memo']))
        self.app.conn.commit()
        # File may not be assigned in the table widget as Yes
        self.get_files()
        self.fill_table()
        self.app.delete_backup = False

    def unmark(self, position):
        """ Remove case marking from selected text in selected file. """

        if self.selected_text_file is None:
            return
        if len(self.case_text) == 0:
            return
        cursor = self.ui.textBrowser.cursorForPosition(position)
        self.ui.textBrowser.setTextCursor(cursor)

        location = self.ui.textBrowser.textCursor().selectionStart()
        unmarked = None
        for item in self.case_text:
            if location >= item['pos0'] and location <= item['pos1']:
                unmarked = item
        if unmarked is None:
            return

        # Delete from database, remove from case_text and update gui
        cur = self.app.conn.cursor()
        cur.execute("delete from case_text where fid=? and caseid=? and pos0=? and pos1=?",
            (unmarked['fid'], unmarked['caseid'], unmarked['pos0'], unmarked['pos1']))
        self.app.conn.commit()
        if unmarked in self.case_text:
            self.case_text.remove(unmarked)
        self.unlight()
        self.highlight()
        # The file may be assigned Yes in the table widget but should be empty
        self.get_files()
        self.fill_table()
        self.app.delete_backup = False

    def automark(self):
        """ Automark text in one or more files with selected case.
        Each selected_file is a tuple of id, name,fulltext, mediapath, memo, owner, date
        """

        index_list = self.ui.tableWidget.selectionModel().selectedIndexes()
        rows = []
        for i in index_list:
            rows.append(i.row())
        rows = list(set(rows))  # duplicate rows due to multiple columns
        if len(rows) == 0:
            return
        selected_files = []
        filenames = ""
        for r in rows:
            if self.allfiles[r][2] is not None and self.allfiles[r][2] != "":
                selected_files.append(self.allfiles[r])
                filenames += self.allfiles[r][1] + " "
        ui_se = DialogGetStartAndEndMarks(self.case['name'], filenames)
        ok = ui_se.exec()
        if not ok:
            return
        start_mark = ui_se.get_start_mark()
        end_mark = ui_se.get_end_mark()
        if start_mark == "" or end_mark == "":
            Message(self.app, _("Warning"), _('Cannot have blank text marks'), "warning").exec()
            return
        msg = _("Auto assign text to case: ") + self.case['name']
        msg += _("\nUsing ") + start_mark + _(" and ") + end_mark + _("\nIn files:\n")
        msg += filenames
        warning_msg = ""
        already_assigned = ""
        entries = 0
        cur = self.app.conn.cursor()
        for f in selected_files:
            cur.execute("select name, id, fulltext, memo, owner, date from source where id=?",
                [f[0]])
            currentfile = cur.fetchone()
            text = currentfile[2]
            text_starts = [match.start() for match in re.finditer(re.escape(start_mark), text)]
            text_ends = [match.start() for match in re.finditer(re.escape(end_mark), text)]
            # Add new code linkage items to database
            already_assigned = ""
            for start_pos in text_starts:
                text_end_iterator = 0
                try:
                    while start_pos >= text_ends[text_end_iterator]:
                        text_end_iterator += 1
                except IndexError:
                    text_end_iterator = -1
                    warning_msg += _("Auto assign. Could not find an end mark: ") + f[1] + "  " + end_mark + "\n"
                if text_end_iterator >= 0:
                    pos1 = text_ends[text_end_iterator]
                    item = {'caseid': self.case['caseid'], 'fid': f[0],
                        'pos0': start_pos, 'pos1': pos1,
                        'owner': self.app.settings['codername'],
                        'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'memo': ""}
                    # Check if already assigned to case_text
                    sql = "select id from case_text where caseid=? and fid=? and pos0=? and pos1=?"
                    cur.execute(sql, [item['caseid'], item['fid'], item['pos0'], item['pos1']])
                    res = cur.fetchone()
                    if res is None:
                        sql = "insert into case_text (caseid,fid,pos0,pos1,owner,date,memo) values(?,?,?,?,?,?,?)"
                        cur.execute(sql, (item['caseid'], item['fid'], item['pos0'], item['pos1'],
                              item['owner'], item['date'], item['memo']))
                        entries += 1
                        self.app.conn.commit()
                    else:
                        already_assigned = _("\nAlready assigned.")
        # Update messages and table widget
        self.get_files()
        self.fill_table()
        # Text file is loaded in browser then update the highlights
        self.load_case_text()
        self.highlight()
        msg += "\n" + str(entries) + _(" sections found.")
        Message(self.app, _("File added to case"), msg + "\n" + warning_msg + "\n" + already_assigned).exec()
        self.parent_textEdit.append(msg)
        self.parent_textEdit.append(warning_msg)
        self.app.delete_backup = False
