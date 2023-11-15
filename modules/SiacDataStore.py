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

from .SiacEnumerations import *
from .TableViewDataModels import DataSourceViewModel
from .toolkitData.AttributeValueMapping import AttributeValueMapping, SiacLayerMappingType, SerializableAttributeValueMappingDefinition, AttributeValueToEntityMapping
from .SiacFoundation import LayerHelper, CachedLayerItem
from .SiacEntityManagement import SiacEntityLayerManager
from .toolkitData.SiacDataStoreLayerSource import SiacDataStoreLayerSource
from .toolkitData.SiacEntityRepresentation import SiacEntityRepresentation
from .toolkitData.SiacDataSourceOptions import ProjectDataSourceOptions


class SiacDataStore:

    data = None
    dataModel = None
    activeLayer = None
    qgsProjectInstance = None
    entityLayerManager = None

    uiUpdateActiveLayerFieldCallback = None

    def __init__(self, qgsInstance, activeFieldUpdateCallback) -> None:
        self.data : Iterable[SiacDataStoreLayerSource] = []
        self.dataModel = DataSourceViewModel(self)
        self.qgsProjectInstance = qgsInstance
        self.uiUpdateActiveLayerFieldCallback = activeFieldUpdateCallback

    def setActiveLayer(self, layer : SiacDataStoreLayerSource) -> None:
        self.activeLayer = layer
        self.uiUpdateActiveLayerFieldCallback(None if layer is None else layer.LayerName)

    def getActiveLayer(self) -> SiacDataStoreLayerSource:
        return self.activeLayer


    def containsAncillaryDataUid(self, uid):
        for l in self.getAncillaryItems():
            if l.LayerMapping.MappingId == uid:
                return True, l            
        return False, None

    def containsItemWithId(self, id : str) -> SiacDataStoreLayerSource:
        for l in self.data:
            if l.ItemId == id:
                return l
        return None

    def addDataStoreLayerSource(self, layerSourceToAdd : SiacDataStoreLayerSource) -> SiacDataStoreLayerSource:
        
        # TODO: The current implementation actually allows duplication of layer types in the model
        # This is actually not the worst feature, as certain layer types can easily be included multiple times. However others should not, this needs to be resolved!

        # determine if a layer is in model and map:
        # if present, remove map layer and previous store item; then re-add map layer and to store
        # if not present, simply and item to store
        # a new layer is represented by not being touched yet
        mapLayer = None
        
        # check if we have correct CRS etc.
        if layerSourceToAdd.LayerSource.crs().authid().split(":")[1] != ProjectDataSourceOptions.Crs:
            QgsMessageLog.logMessage('Projecting map layer {} to project CRS'.format(layerSourceToAdd.LayerName), "SIAC", Qgis.MessageLevel.Warning)            
            projLayer = processing.run("native:reprojectlayer", {'INPUT': layerSourceToAdd.LayerSource,'TARGET_CRS' : QgsCoordinateReferenceSystem('EPSG:{}'.format(ProjectDataSourceOptions.Crs)),'OUTPUT':'TEMPORARY_OUTPUT'})['OUTPUT']
            layerSourceToAdd.LayerSource = projLayer
            layerSourceToAdd.SetTouched()

        # check if siac id is present for required data layer types
        if DataLayer(layerSourceToAdd.LayerType) == DataLayer.TREE_COVER:
            if not LayerHelper.containsFieldWithName(layerSourceToAdd.LayerSource, SiacField.UID_CANOPY.value):
                uidLayer = LayerHelper.createLayerUniqueId(layerSourceToAdd.LayerSource, SiacField.UID_CANOPY.value)
                layerSourceToAdd.LayerSource = uidLayer
                layerSourceToAdd.SetTouched()

        # check map layers based on id for presence of layer and remove from map
        # we only need to update map layer if touched
        if layerSourceToAdd.IsTouched() and layerSourceToAdd.MapLayerId is not None:
            layerIds = [ k for k in self.qgsProjectInstance.mapLayers().keys() ]
            if layerSourceToAdd.MapLayerId in layerIds:
                QgsMessageLog.logMessage('Removing layer {} from map'.format(layerSourceToAdd.LayerName), "SIAC", Qgis.MessageLevel.Info)                            
                self.qgsProjectInstance.removeMapLayer(layerSourceToAdd.MapLayerId)

        # check store and update datastorelayersource accordingly
        # the new datastorelayersource simply replaces the existing item: this mechanism is primarily intended for augmented input layers          
        # when the new datatorelayersource was created, all relevant information were copied over
        reSetAsActiveLayer = False
        previousSource = self.containsItemWithId(layerSourceToAdd.ItemId)
        if previousSource is not None:
            # remove previous source from store
            if self.getActiveLayer() is not None:
                if self.getActiveLayer().ItemId == previousSource.ItemId:
                    reSetAsActiveLayer = True
                    self.setActiveLayer(None)
            
            self.data.remove(previousSource)


        # above mechanism, however, fails if we create a new datasource, this leads to duplicates. consequently, we also need to check if we already have such a layer in the model, then replace the other layer
        # note that only for ancillary data, we can have more than one layer
        if DataLayer(layerSourceToAdd.LayerType) != DataLayer.ANCILLARY_DATA and DataLayer(layerSourceToAdd.LayerType) != DataLayer.TOPOLOGY_TREES_NEAR_ENTITY:
            hasPreviousSource, previousSource = self.containsLayerSourceForType( DataLayer(layerSourceToAdd.LayerType) )
            if previousSource is not None:
                if self.getActiveLayer() is not None:
                    if self.getActiveLayer().ItemId == previousSource.ItemId:
                        reSetAsActiveLayer = True
                        self.setActiveLayer(None)
                self.data.remove(previousSource)
                self.qgsProjectInstance.removeMapLayer(previousSource.MapLayerId)



        # re-add respective layer to gqs map instance and retrieve corresponding maplayer item
        if layerSourceToAdd.IsTouched():
            QgsMessageLog.logMessage('Adding layer {} to map'.format(layerSourceToAdd.LayerName), "SIAC", Qgis.MessageLevel.Info)                            
            mapLayer = self.qgsProjectInstance.addMapLayer(layerSourceToAdd.LayerSource)        
            mapLayer.setName(layerSourceToAdd.LayerName)
            # update layerSource MapItemId, but keep the item's unique id
            layerSourceToAdd.MapLayerId = mapLayer.id() 

        # re-insert datastorelayersource into data store
        self.data.append(layerSourceToAdd)   
        if reSetAsActiveLayer:
            QgsMessageLog.logMessage('Updated active layer with item {}'.format(layerSourceToAdd.LayerName), "SIAC", Qgis.MessageLevel.Info)            
            self.setActiveLayer(layerSourceToAdd)     

        # update view model
        self.emitViewModelChange()
        
        return layerSourceToAdd

    def getItem(self, type : DataLayer) -> SiacDataStoreLayerSource:
        for ds in self.data:
            if ds.LayerType == type.value:
                return ds
        return None

    def getData(self) -> Iterable[SiacDataStoreLayerSource]:
        return self.data   

    def getItems(self, type : DataLayer) -> Iterable[SiacDataStoreLayerSource]:
        retval = []
        for ds in self.data:
            if ds.LayerType == type.value:
                retval.append(ds)                
        return retval
    
    def getAncillaryItems(self) -> Iterable[SiacDataStoreLayerSource]:
        layers = self.getItems(DataLayer.ANCILLARY_DATA)
        return layers

    def getAncillaryLayerItemsForEntityType(self, entityType : SiacEntity) -> Iterable[SiacDataStoreLayerSource]:
        result = []
        ancillaryLayers = self.getAncillaryItems()
        for layer in ancillaryLayers:
            if layer.LayerMapping.representsEntityType(entityType):
                result.append(layer)                
        return result if len(result) > 0 else None
    
    def getEntityLayerManager(self, entityTypes : Iterable[SiacEntity]) -> SiacEntityLayerManager:      
           
        result = SiacEntityLayerManager(entityTypes) 

        for currentEntityType in entityTypes:            
            tmp : Iterable[SiacDataStoreLayerSource] = self.getAncillaryLayerItemsForEntityType(currentEntityType)
            if tmp is not None:      
                for currentSourceItem in tmp:
                    result.insertAncillaryLayerForEntityType(currentSourceItem, currentEntityType)
                        
        return result # if result.ancillaryLayerTypesCount() > 0 else None

    def getItemAtIndex(self, idx) -> SiacDataStoreLayerSource:
        return self.data[idx]

    def removeAtIndex(self, idx) -> SiacDataStoreLayerSource:        
        removedItem : SiacDataStoreLayerSource = self.data.pop(idx)
        if self.getActiveLayer() is not None and self.getActiveLayer().ItemId == removedItem.ItemId:
            self.setActiveLayer(None)

        self.emitViewModelChange()
        return removedItem
    
    def updateMapLayerId(self, type : DataLayer, newId):
        for ds in self.data:
            if ds.LayerType == type.value:
                ds.MapLayerId = newId

    def getLayers(self) -> Iterable[SiacDataStoreLayerSource]:
        return self.data

    def clear(self):
        self.data = []
        self.setActiveLayer(None)
        self.emitViewModelChange()

    def getLayersOfType(self, type : DataLayer):
        retval = []
        for ds in self.data:
            if ds.LayerType == type.value:
                retval.append(ds.LayerSource)                
        return retval

    def getLayerOfType(self, type : DataLayer):
        for ds in self.data:
            if ds.LayerType == type.value:
                return True, ds.LayerSource                  
        return False, None    

    def containsLayerSourceForType(self, type : DataLayer) -> Tuple[bool, SiacDataStoreLayerSource]:
        for ds in self.data:
            if ds.LayerType == type.value:
                return True, ds
        return False, None

    def emitViewModelChange(self):
        self.dataModel.layoutChanged.emit()       

    def getViewModel(self):
        return self.dataModel    
    
    def serializeLayerDefinitions(self):
        result = []

        for ds in self.data:        
            tmp = {}
            tmp['LAYER_NAME'] = ds.LayerName
            tmp['LAYER_TYPE'] = ds.LayerType
            tmp['LAYER_MAPPING'] = None if ds.LayerMapping is None else SerializableAttributeValueMappingDefinition(ds.LayerMapping)
            result.append(tmp)

        return result 
