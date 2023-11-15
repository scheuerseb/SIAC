import os.path
import xlsxwriter as xlsx
from typing import Iterable, Dict, Tuple
from qgis.core import *
from qgis.gui import QgsMessageBar, QgsMapLayerComboBox, QgsFieldComboBox, QgsMapToolEmitPoint
from qgis.PyQt.QtCore import Qt, QThread, QSettings, QTranslator, QCoreApplication, QVariant, pyqtSignal, QAbstractTableModel, QModelIndex
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QErrorMessage, QAction, QMessageBox, QProgressBar, QMenu, QHeaderView, QFileDialog
from PyQt5 import QtWidgets
import networkx as nx
import pickle
import pandas as pd


from .QtUiWrapper import QtWrapper
from .TreeRichnessAndDiversityAssessment import TreeRichnessAndDiversityAssessmentResult

class SiacExporter:
    
    @staticmethod
    def toGraphMl(qtroot, graph):
        fileName, filterString = QtWidgets.QFileDialog.getSaveFileName(qtroot, "Save File", "", "GraphML (*.graphml)")
        if fileName:
            nx.write_graphml( graph, fileName )
            QtWrapper.showErrorMessage(qtroot, "Data written to GraphML file")
            

    @staticmethod
    def toExcel():
        pass

    @staticmethod
    def toText(qtroot, txtData, fileTypeStr = "Text files (*.txt)"):
        fileName, filterString = QtWidgets.QFileDialog.getSaveFileName(qtroot, "Save File", "", fileTypeStr)
        if fileName:
            with open(fileName, 'w') as txtFile:
                txtFile.write(txtData)
            QtWrapper.showErrorMessage(qtroot, "Data written to file")
            



    @staticmethod
    def toPickle(qtroot, fileTypeStr, data):
        fileName, filterString = QtWidgets.QFileDialog.getSaveFileName(qtroot, "Save File", "", fileTypeStr)
        if fileName:        
            output = open(fileName, 'wb')
            # Pickle dictionary using protocol 0.
            pickle.dump(data, output)
            output.close()
            QtWrapper.showErrorMessage(qtroot, "Data written to file")

    


class SiacImporter:

    @staticmethod
    def fromPickle(qtroot, fileTypeStr):
        data = None
        fileName, filterString = QtWidgets.QFileDialog.getOpenFileName(qtroot, "Load File", "", fileTypeStr)
        if fileName:
            with open(fileName , 'rb') as f:  
                data = pickle.load(f)
        
        return data 
    
    @staticmethod
    def fromCsv(qtroot):
        fileName, filterString = QtWidgets.QFileDialog.getOpenFileName(qtroot, "Load File", "", "CSV File (*.csv)" )
        if fileName:
            data = pd.read_csv(fileName)
            return data
        else:
            return None
