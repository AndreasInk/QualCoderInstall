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

from copy import copy
import logging
import os
import sys
import traceback

from PyQt6 import QtGui, QtWidgets

from .helpers import Message

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


class Codebook:
    """ Create a codebook and export to file. """

    app = None
    parent_textEdit = None
    code_names = []
    categories = []
    tree = None

    def __init__(self, app, parent_textedit):

        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textedit
        self.code_names, self.categories = self.app.get_codes_categories()
        self.get_code_frequencies()
        self.tree = QtWidgets.QTreeWidget()
        self.fill_tree()
        self.export()

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes
        """

        cats = copy(self.categories)
        codes = copy(self.code_names)
        self.tree.clear()
        self.tree.setColumnCount(4)
        # add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                self.tree.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)

        ''' Add child categories. look at each unmatched category, iterate through tree
         to add as child then remove matched categories from the list. '''

        count = 0
        while len(cats) > 0 or count < 10000:
            remove_list = []
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.tree)
                item = it.value()
                while item:  # while there is an item in the list
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        memo = ""
                        if c['memo'] != "":
                            memo = "Memo"
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                        child.setIcon(0, QtGui.QIcon("GUI/icon_cat.png"))
                        item.addChild(child)
                        remove_list.append(c)
                    it += 1
                    item = it.value()
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
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo, str(c['freq'])])
                self.tree.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)
        # Add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.tree)
            item = it.value()
            while item:
                if item.text(1) == 'catid:' + str(c['catid']):
                    memo = ""
                    if c['memo'] != "":
                        memo = "Memo"
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo, str(c['freq'])])
                    item.addChild(child)
                    c['catid'] = -1  # make unmatchable
                it += 1
                item = it.value()

    def export(self):
        """ Export codes to a plain text file, filename will have .txt ending. """

        filename = "codebook.txt"
        options = QtWidgets.QFileDialog.Option.DontResolveSymlinks | QtWidgets.QFileDialog.Option.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
            _("Select directory to save file"), self.app.settings['directory'], options)
        if directory == "":
            return
        filename = directory + "/" + filename
        filedata = _("Codebook for ") + self.app.project_name + "\n========"
        it = QtWidgets.QTreeWidgetItemIterator(self.tree)
        item = it.value()
        while item:
            self.depthgauge(item)
            cat = False
            if item.text(1).split(':')[0] == "catid":
                cat = True
            id_ = int(item.text(1).split(':')[1])
            memo = ""
            owner = ""
            prefix = ""
            for i in range(0, self.depthgauge(item)):
                prefix += "--"
            if cat:
                filedata += "\n" + prefix + _("Category: ") + item.text(0) + ", " + item.text(1)
                for i in self.categories:
                    if i['catid'] == id_:
                        memo = i['memo']
                        owner = i['owner']
            else:
                filedata += "\n" + prefix + _("Code: ") + item.text(0) + ", " + item.text(1)
                filedata += ", Frq: " + item.text(3)
                for i in self.code_names:
                    if i['cid'] == id_:
                        memo = i['memo']
                        owner = i['owner']
            filedata += _(", Owner: ") + owner
            if memo is None:
                memo = ""
            filedata += "\n" + prefix + _("Memo: ") + memo

            it += 1
            item = it.value()
        f = open(filename, 'w')
        f.write(filedata)
        f.close()
        Message(self.app, _('Codebook exported'), _("Text representation of codebook exported:") + "\n" + filename).exec()
        self.parent_textEdit.append(_("Codebook exported to ") + filename)

    def depthgauge(self, item):
        """ Get depth for treewidget item. """

        depth = 0
        while item.parent() is not None:
            item = item.parent()
            depth += 1
        return depth

    def get_code_frequencies(self):
        """ Called from init. For each code, get the
        frequency from coded text, images and audio/video. """

        cur = self.app.conn.cursor()
        for c in self.code_names:
            c['freq'] = 0
            cur.execute("select count(cid) from code_text where cid=?", [c['cid'], ])
            result = cur.fetchone()
            if result is not None:
                c['freq'] += result[0]
            cur.execute("select count(imid) from code_image where cid=?", [c['cid'], ])
            result = cur.fetchone()
            if result is not None:
                c['freq'] += result[0]
            cur.execute("select count(avid) from code_av where cid=?", [c['cid'], ])
            result = cur.fetchone()
            if result is not None:
                c['freq'] += result[0]
