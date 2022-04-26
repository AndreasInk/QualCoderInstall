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

import os
import sys
import logging
import traceback

from PyQt6 import QtWidgets, QtCore

from .GUI.ui_dialog_add_item import Ui_Dialog_add_item

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception") + ":\n" + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class DialogAddItemName(QtWidgets.QDialog):
    """ Dialog to get a new code or code category from user.
    Also used for Case and File adding attributes.
    Requires a name for Dialog title (and label in setupUI)
    Requires a list of dictionary 'name' items.
    Dialog returns ok if the item is not a duplicate of a name in the list.
    Returns one item through get_new_name method.
    """

    new_item = None
    existing_items = []
    Dialog_addItem = None

    def __init__(self, app, items, title, text, parent=None):
        super(DialogAddItemName, self).__init__(parent)
        sys.excepthook = exception_handler
        self.existing_items = []
        for i in items:
            self.existing_items.append(i['name'])
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_add_item()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("* {font-size:" + str(app.settings['fontsize']) + "pt} ")
        self.setWindowTitle(title)
        self.ui.label.setText(text)
        self.ui.lineEdit.setFocus()

    def accept(self):
        """ On pressing accept button, check there is no duplicate.
        If no duplicate then accept end close the dialog """

        this_item = str(self.ui.lineEdit.text())
        if this_item in self.existing_items:
            QtWidgets.QMessageBox.warning(None, _("Duplicated"), _("This already exists"))
            return
        self.new_item = this_item
        self.close()

    def get_new_name(self):
        """ Get the new name. """

        return self.new_item
