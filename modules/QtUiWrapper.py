from qgis.core import *
from qgis.gui import QgsMessageBar, QgsMapLayerComboBox, QgsFieldComboBox, QgsMapToolEmitPoint
from qgis.PyQt.QtCore import Qt, QThread, QSettings, QTranslator, QCoreApplication, QVariant, pyqtSignal, QAbstractTableModel, QModelIndex
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QErrorMessage, QAction, QMessageBox, QProgressBar, QMenu, QHeaderView, QFileDialog
from PyQt5 import QtWidgets


class QtWrapper:
    @staticmethod
    def showErrorMessage(parent, messageText):
        error_dialog = QErrorMessage(parent)
        error_dialog.showMessage(messageText)

