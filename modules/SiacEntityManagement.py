from qgis.core import *
from qgis.gui import QgsMessageBar, QgsMapLayerComboBox, QgsFieldComboBox
from qgis.PyQt.QtCore import Qt, QThread, QSettings, QTranslator, QCoreApplication, QVariant, pyqtSignal, QAbstractTableModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QErrorMessage, QAction, QMessageBox, QProgressBar
import processing
import pandas as pd
import geopandas as geopd
import uuid

from typing import Iterable, Tuple, Dict
from collections import namedtuple
from copy import deepcopy

from .toolkit.DATA import DataProcessor
from .SiacEnumerations import SiacEntity, SiacGeometryType
from .toolkitData.SiacDataStoreLayerSource import SiacDataStoreLayerSource
from .toolkitData.SiacEntityRepresentation import SiacEntityRepresentation


class SiacEntityLayerManager:

    _supportedEntityTypes : Iterable[SiacEntity] = None
    _isLayersProcessed = None
    _dataStoreLayerSourcesForEntities : Dict[SiacEntity, Dict[SiacGeometryType, Iterable[SiacDataStoreLayerSource]]] = None
    _entityRepresentations : Dict[SiacEntity, Dict[SiacGeometryType, SiacEntityRepresentation]]= None

    def __init__(self, supportedEntityTypes) -> None:
        self._isLayersProcessed = False
        self._supportedEntityTypes = supportedEntityTypes
        self._dataStoreLayerSourcesForEntities = {}
        self._entityRepresentations = {}

    def processLayers(self):
        self._entityRepresentations = DataProcessor.ancillaryItemsToEntityRepresentations(self._dataStoreLayerSourcesForEntities, self._supportedEntityTypes)
        self._isLayersProcessed = True

    def containsEntityType(self, targetType : SiacEntity) -> bool:
        for cType in self._entityRepresentations.keys():
            if cType == targetType:
                return True
        return False

    def containedEntityTypes(self) -> Iterable[SiacEntity]:
        return self._entityRepresentations.keys()
    
    def getEntityRepresentations(self) -> Iterable[SiacEntityRepresentation]:
        result = []
        for entityType, geomDict in self._entityRepresentations.items():
            for geomType, currentEntityRepresentation in geomDict.items():
                result.append(currentEntityRepresentation)
        return result

    def getEntityTypesOfGeometryType(self, geomType : SiacGeometryType) -> Iterable[SiacEntity]:
        """Returns a list of SiacEntity types of with a given geometry type. 

        Args:
            geomType (SiacGeometryType): Geometry type of interest

        Returns:
            Iterable[SiacEntity]: List of entities with geometry type of interest
        """
        result = []
        for entityType, typeGeomDict in self._dataStoreLayerSourcesForEntities.items():
            if geomType in typeGeomDict.keys():
                result.append(entityType)
        return result
    
    def getEntityRepresentationsOfGeometryType(self, geomType : SiacGeometryType) -> Iterable[SiacEntityRepresentation]:
        """Returns a list of entity representations of a given geometry type

        Args:
            geomType (SiacGeometryType): Geometry type of interest

        Returns:
            Iterable[SiacEntityRepresentation]: Entity representations with geometry type of interest
        """
        result = []
        for entityType, typeGeomDict in self._entityRepresentations.items():
            if geomType in typeGeomDict.keys():            
                result.append( typeGeomDict[geomType] )
        return result

    def getEntityRepresentationForGeometryTypeForEntityType(self, targetEntityType : SiacEntity, targetGeometryType : SiacGeometryType) -> Tuple[bool, SiacEntityRepresentation]:
        """Returns an entity representation for a given geometry type and entity type.  

        Args:
            targetEntityType (SiacEntity): Entity type of interest
            targetGeometryType (SiacGeometryType): Geometry type of interest

        Returns:
            Tuple[bool, SiacEntityRepresentation]: Tuple with boolean value indicating existence of requested data, and entity representation. Returns [False, None] if types cannot be resolved.
        """
        if not self.containsEntityType(targetEntityType):
            return False, None
        else:

            if targetGeometryType in self._entityRepresentations[targetEntityType].keys():
                return True, self._entityRepresentations[targetEntityType][targetGeometryType]
            else:
                return False, None

    def ancillaryLayerTypesCount(self) -> int:
        return len(self._dataStoreLayerSourcesForEntities.keys())

    def insertAncillaryLayerForEntityType(self, ancillaryLayer : SiacDataStoreLayerSource, entityType : SiacEntity) -> None:
        # assert that proper key exists
        if not entityType in self._dataStoreLayerSourcesForEntities.keys():
            self._dataStoreLayerSourcesForEntities[entityType] = {}

        # get geometryType of layer
        layerGeomType = ancillaryLayer.GeometryType
        # assert that respective  geometry type exists as key
        if not layerGeomType in self._dataStoreLayerSourcesForEntities[entityType].keys():
            self._dataStoreLayerSourcesForEntities[entityType][layerGeomType] = []
        
        # add layer 
        self._dataStoreLayerSourcesForEntities[entityType][layerGeomType].append(ancillaryLayer)