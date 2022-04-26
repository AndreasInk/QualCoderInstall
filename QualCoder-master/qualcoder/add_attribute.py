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

from PyQt6 import QtWidgets, QtCore
import os
import sys
import logging
import traceback

from .GUI.ui_attribute import Ui_DialogAddAttribute
from .helpers import Message

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


class DialogAddAttribute(QtWidgets.QDialog):
    """
    Dialog to get a new code or code category from user.
    Also used for Case and File adding attributes.
    Requires a name for Dialog title (and label in setupUI)
    Requires a list of dictionary 'name' items.
    Dialog returns ok if the item is not a duplicate of a name in the list.
    """

    existing_names = []
    new_name = ""
    value_type = "character"
    app = None

    def __init__(self, app, names, parent=None):
        super(DialogAddAttribute, self).__init__(parent)  # overrride accept method

        sys.excepthook = exception_handler
        self.app = app
        for n in names:
            self.existing_names.append(n['name'])
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_DialogAddAttribute()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(app.settings['fontsize']) + 'pt '
        font += '"' + app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.ui.radioButton_character.setChecked(True)
        self.ui.lineEdit_name.setFocus()

    def accept(self):
        """ On pressing accept button, check there is no duplicate name.
        If no duplicate then accept and return True. """

        self.value_type = "character"
        new_name = str(self.ui.lineEdit_name.text())
        duplicate = False
        if new_name in self.existing_names:
            duplicate = True
            Message(self.app, _("Duplicated"), _("This already exists"), "warning").exec()
            self.new_name = ""
            self.done(0)
        if duplicate is False:
            self.new_name = new_name
        if self.ui.radioButton_numeric.isChecked():
            self.value_type = "numeric"
        self.done(1)
