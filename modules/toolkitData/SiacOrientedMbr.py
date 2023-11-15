from qgis.core import *
from qgis.core import *
from qgis.gui import QgsMessageBar, QgsMapLayerComboBox, QgsFieldComboBox
from qgis.PyQt.QtCore import Qt, QThread, QSettings, QTranslator, QCoreApplication, QVariant, pyqtSignal, QAbstractTableModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QErrorMessage, QAction, QMessageBox, QProgressBar
import processing

from typing import Iterable, Dict

class SiacOrientedMinimumBoundingRectangle:

    _FeatureGeometry = None
    _OrientedMinimumBoundingRectangle = None
    _LinearityThreshold = None

    def __init__(self, featureGeometry : QgsGeometry, linearityThreshold : float) -> None:
        self._FeatureGeometry = featureGeometry
        self._LinearityThreshold = linearityThreshold
        self._OrientedMinimumBoundingRectangle = featureGeometry.orientedMinimumBoundingBox()

    def getOrientedMinimumBoundingRectangleGeometry(self):
        return self._OrientedMinimumBoundingRectangle[0]

    @property
    def FeatureGeometry(self) -> QgsGeometry:
        return self._FeatureGeometry
    
    @property
    def OrientedMinimumBoundingRectangle(self):
        return self._OrientedMinimumBoundingRectangle

    @OrientedMinimumBoundingRectangle.setter
    def OrientedMinimumBoundingRectangle(self, value):
        self._OrientedMinimumBoundingRectangle = value

    @property
    def Elongation(self):
        a = self._OrientedMinimumBoundingRectangle[3] # width
        b = self._OrientedMinimumBoundingRectangle[4] # height        
        elongation = (b/a) if a > b else (a/b) 
        return elongation
    
    @property
    def LinearityThreshold(self):
        return self._LinearityThreshold
    
    @property
    def Linearity(self):
        return 1 - self.Elongation
    
    @property
    def IsLinear(self):
        return True if self.Linearity > self.LinearityThreshold else False