from qgis.core import *
from qgis.gui import QgsMessageBar, QgsMapLayerComboBox, QgsFieldComboBox
from qgis.PyQt.QtCore import Qt, QThread, QSettings, QTranslator, QCoreApplication, QVariant, pyqtSignal, QAbstractTableModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QErrorMessage, QAction, QMessageBox, QProgressBar

import uuid

from .AttributeValueMapping import AttributeValueMapping
from ..SiacEnumerations import *
from ..SiacFoundation import LayerHelper

class SiacDataStoreLayerSource:
    
    _ItemId = None
    _MapLayerId = None
    _LayerName = None
    _LayerType = None
    _LayerMapping = None
    _LayerSource = None
    _IsTouched = None

    def __init__(self):
        self._ItemId = uuid.uuid4().hex
        self._IsTouched = False

    def clone(self):

        newSource = SiacDataStoreLayerSource()
        newSource.ItemId = self.ItemId
        newSource.MapLayerId = self.MapLayerId
        newSource.LayerName = self.LayerName
        newSource.LayerType = self.LayerType
        newSource.LayerMapping = self.LayerMapping
        newSource.LayerSource = LayerHelper.copyLayer(self.LayerSource)
        newSource.LayerSource.setName(self.LayerSource.name())        
        newSource.SetTouched()
        return newSource


    def SetTouched(self):
        self._IsTouched = True
    def IsTouched(self):
        return self._IsTouched

    @property
    def ItemId(self) -> str:
        return self._ItemId
    
    @ItemId.setter
    def ItemId(self, value : str) -> None:
        self._ItemId = value

    @property
    def LayerMapping(self) -> AttributeValueMapping:
        return self._LayerMapping
    
    @LayerMapping.setter
    def LayerMapping(self, value):
        self._LayerMapping = value

    @property
    def LayerSource(self):
        return self._LayerSource
    
    @LayerSource.setter
    def LayerSource(self, value):
        self._LayerSource = value

    @property
    def LayerName(self):
        return self._LayerName
    
    @LayerName.setter
    def LayerName(self, value):
        self._LayerName = value

    @property
    def LayerType(self) -> str:
        return self._LayerType

    @LayerType.setter
    def LayerType(self, value : str):
        self._LayerType = value

    @property
    def MapLayerId(self):
        return self._MapLayerId

    @MapLayerId.setter
    def MapLayerId(self, value):
        self._MapLayerId = value
    
    @property
    def GeometryType(self) -> SiacGeometryType:
        if self._LayerSource.geometryType() == 0:
            return SiacGeometryType.POINT
        if self._LayerSource.geometryType() == 2:
            return SiacGeometryType.POLYGON
        return None
    


    @staticmethod
    def makeNewDataStoreLayerSourceItem(layer : any, layerType : str, layerName : str, layerId : str, ancillaryLayerId : str = None ):
        newLayerSource = SiacDataStoreLayerSource() # new item automatically received new item id
        QgsMessageLog.logMessage('Creating DataStoreLayerSource {}'.format(newLayerSource.ItemId), "SIAC", level=Qgis.MessageLevel.Info)
        
        newLayerSource.LayerSource = layer
        newLayerSource.LayerType = layerType
        newLayerSource.LayerName = layerName
        newLayerSource.MapLayerId = layerId 
        newLayerSource.LayerMapping = AttributeValueMapping(uuid.uuid4().hex if ancillaryLayerId is None else ancillaryLayerId)
        

        return newLayerSource