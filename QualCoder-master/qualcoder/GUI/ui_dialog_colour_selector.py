# Form implementation generated from reading ui file 'ui_dialog_colour_selector.ui'
#
# Created by: PyQt6 UI code generator 6.2.3
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_Dialog_colour_selector(object):
    def setupUi(self, Dialog_colour_selector):
        Dialog_colour_selector.setObjectName("Dialog_colour_selector")
        Dialog_colour_selector.resize(554, 484)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(Dialog_colour_selector.sizePolicy().hasHeightForWidth())
        Dialog_colour_selector.setSizePolicy(sizePolicy)
        Dialog_colour_selector.setMinimumSize(QtCore.QSize(554, 484))
        Dialog_colour_selector.setMaximumSize(QtCore.QSize(554, 484))
        self.gridLayout = QtWidgets.QGridLayout(Dialog_colour_selector)
        self.gridLayout.setObjectName("gridLayout")
        self.groupBox = QtWidgets.QGroupBox(Dialog_colour_selector)
        self.groupBox.setMinimumSize(QtCore.QSize(0, 80))
        self.groupBox.setMaximumSize(QtCore.QSize(16777215, 80))
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.label_colour_old = QtWidgets.QLabel(self.groupBox)
        self.label_colour_old.setGeometry(QtCore.QRect(10, 10, 281, 31))
        self.label_colour_old.setText("")
        self.label_colour_old.setWordWrap(True)
        self.label_colour_old.setObjectName("label_colour_old")
        self.label_colour_new = QtWidgets.QLabel(self.groupBox)
        self.label_colour_new.setGeometry(QtCore.QRect(10, 50, 281, 31))
        self.label_colour_new.setText("")
        self.label_colour_new.setWordWrap(True)
        self.label_colour_new.setObjectName("label_colour_new")
        self.buttonBox = QtWidgets.QDialogButtonBox(self.groupBox)
        self.buttonBox.setGeometry(QtCore.QRect(430, 10, 81, 71))
        self.buttonBox.setOrientation(QtCore.Qt.Orientation.Vertical)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Cancel|QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.label_used = QtWidgets.QLabel(self.groupBox)
        self.label_used.setGeometry(QtCore.QRect(310, 10, 101, 41))
        self.label_used.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeading|QtCore.Qt.AlignmentFlag.AlignLeft|QtCore.Qt.AlignmentFlag.AlignTop)
        self.label_used.setWordWrap(True)
        self.label_used.setObjectName("label_used")
        self.gridLayout.addWidget(self.groupBox, 0, 0, 1, 1)
        self.tableWidget = QtWidgets.QTableWidget(Dialog_colour_selector)
        self.tableWidget.setObjectName("tableWidget")
        self.tableWidget.setColumnCount(0)
        self.tableWidget.setRowCount(0)
        self.gridLayout.addWidget(self.tableWidget, 1, 0, 1, 1)

        self.retranslateUi(Dialog_colour_selector)
        self.buttonBox.accepted.connect(Dialog_colour_selector.accept) # type: ignore
        self.buttonBox.rejected.connect(Dialog_colour_selector.reject) # type: ignore
        QtCore.QMetaObject.connectSlotsByName(Dialog_colour_selector)

    def retranslateUi(self, Dialog_colour_selector):
        _translate = QtCore.QCoreApplication.translate
        Dialog_colour_selector.setWindowTitle(_translate("Dialog_colour_selector", "Colour selector"))
        self.label_used.setText(_translate("Dialog_colour_selector", "* Used"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_colour_selector = QtWidgets.QDialog()
    ui = Ui_Dialog_colour_selector()
    ui.setupUi(Dialog_colour_selector)
    Dialog_colour_selector.show()
    sys.exit(app.exec())
