# Form implementation generated from reading ui file 'ui_dialog_memo.ui'
#
# Created by: PyQt6 UI code generator 6.2.3
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_Dialog_memo(object):
    def setupUi(self, Dialog_memo):
        Dialog_memo.setObjectName("Dialog_memo")
        Dialog_memo.resize(541, 396)
        self.gridLayout = QtWidgets.QGridLayout(Dialog_memo)
        self.gridLayout.setObjectName("gridLayout")
        self.textEdit = QtWidgets.QTextEdit(Dialog_memo)
        self.textEdit.setObjectName("textEdit")
        self.gridLayout.addWidget(self.textEdit, 0, 0, 1, 1)
        self.groupBox = QtWidgets.QGroupBox(Dialog_memo)
        self.groupBox.setMinimumSize(QtCore.QSize(0, 30))
        self.groupBox.setMaximumSize(QtCore.QSize(16777215, 30))
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.buttonBox = QtWidgets.QDialogButtonBox(self.groupBox)
        self.buttonBox.setGeometry(QtCore.QRect(170, 0, 221, 25))
        self.buttonBox.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Cancel|QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.pushButton_clear = QtWidgets.QPushButton(self.groupBox)
        self.pushButton_clear.setGeometry(QtCore.QRect(10, 0, 89, 25))
        self.pushButton_clear.setObjectName("pushButton_clear")
        self.gridLayout.addWidget(self.groupBox, 1, 0, 1, 1)

        self.retranslateUi(Dialog_memo)
        self.buttonBox.accepted.connect(Dialog_memo.accept) # type: ignore
        self.buttonBox.rejected.connect(Dialog_memo.reject) # type: ignore
        QtCore.QMetaObject.connectSlotsByName(Dialog_memo)

    def retranslateUi(self, Dialog_memo):
        _translate = QtCore.QCoreApplication.translate
        Dialog_memo.setWindowTitle(_translate("Dialog_memo", "Memo"))
        self.pushButton_clear.setText(_translate("Dialog_memo", "Clear"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    Dialog_memo = QtWidgets.QDialog()
    ui = Ui_Dialog_memo()
    ui.setupUi(Dialog_memo)
    Dialog_memo.show()
    sys.exit(app.exec())
