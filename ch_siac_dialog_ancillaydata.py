# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'ch_siac_dialog_ancillarydata.ui'
#
# Created by: PyQt5 UI code generator 5.15.4
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.
from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from PyQt5 import QtCore, QtGui, QtWidgets
import os

from .modules.AncillaryDataEditor import AncillaryDataEditor

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'ch_siac_dialog_ancillarydata.ui'))

class Ui_ancillaryLayerDialog(QtWidgets.QDialog, FORM_CLASS):

    editor = None

    def __init__(self, layerPackage, parent=None):
        super(Ui_ancillaryLayerDialog, self).__init__(parent)
        self.setupUi(self)
        self.editor = AncillaryDataEditor(self, layerPackage)