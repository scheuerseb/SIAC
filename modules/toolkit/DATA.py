from qgis.core import *
from qgis.core import *
from qgis.gui import QgsMessageBar, QgsMapLayerComboBox, QgsFieldComboBox
from qgis.PyQt.QtCore import Qt, QThread, QSettings, QTranslator, QCoreApplication, QVariant, pyqtSignal, QAbstractTableModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QErrorMessage, QAction, QMessageBox, QProgressBar
import processing
from typing import Iterable, Dict, NamedTuple
import uuid
from collections import Counter

from ..SiacEnumerations import *
from ..SiacFoundation import LayerHelper, SelectionHelper, FeatureCache
from ..MomepyIntegration import MomepyHelper
from ..toolkitData.SiacDataSourceOptions import ProjectDataSourceOptions
from ..toolkitData.SiacDataStoreLayerSource import SiacDataStoreLayerSource
from ..toolkitData.AttributeValueMapping import AttributeValueMapping, SiacLayerMappingType
from ..toolkitData.SiacEntityRepresentation import SiacEntityRepresentation



class DataProcessor(QgsTask):

    MESSAGE_CATEGORY = "DATA PROCESSOR"
    
    siacToolMaximumProgressValue = pyqtSignal(int)
    siacToolProgressValue = pyqtSignal(int)
    siacToolProgressMessage = pyqtSignal(object, object)
    jobFinished = pyqtSignal(bool, object)

    
    @staticmethod
    def combineLayers(layers : Iterable[QgsVectorLayer], geomType : SiacGeometryType, referenceCrs ) -> QgsVectorLayer:
        resLayer = LayerHelper.createTemporaryLayer(referenceCrs, "tmpAncillaryLayer", geomType.value)
        resLayer.startEditing()
        for layer in layers:
            resLayer.dataProvider().addFeatures(layer.getFeatures())
        resLayer.commitChanges()
        return resLayer


    @staticmethod
    def obtainLayerForEntityType(entityType : SiacEntity, layers : Dict[SiacGeometryType, Iterable[SiacDataStoreLayerSource]], referenceCrs) -> Dict[SiacGeometryType, QgsVectorLayer]:
        # all ds in layers represent, one way or another, the entity in question.
        # this may be either a complete layer, or certain features with specific attribute values
        # unify all of those into a single dissolved layer and return this layer
        
        if layers is None:
            return

        # result is a dict geometrytype, layer
        resultLayerSet = {}

        # iterate over geometry types
        for geomType in SiacGeometryType:
            
            if geomType in layers.keys():
                if layers[geomType] is not None:
                    if len(layers[geomType]) > 0:

                        # TODO: optimize! a single layer with features and a by-layer definition results in simply copying the layer?

                        # we have asserted that geometry type is contained, is not none, and there is at least one layer of said geometry type
                        resLayer = LayerHelper.createTemporaryLayer(referenceCrs, "tmpAncillaryLayer", geomType.value)
                        resLayer.startEditing()
        
                        for layer in layers[geomType]:
                            # add complete layer if mapping type is by-layer
                            if layer.LayerMapping.MappingType ==  SiacLayerMappingType.BY_LAYER:            
                                resLayer.dataProvider().addFeatures(layer.LayerSource.getFeatures())
                            
                            # add relevant features based on their attribute value-type mappings
                            elif layer.LayerMapping.MappingType == SiacLayerMappingType.BY_ATTRIBUTE:

                                # get all relevant mappings (value-entity type combinations)
                                relevantMappings = layer.LayerMapping.getMappingsForEntityType(entityType)                                 
                                for mapping in relevantMappings:                                    
                                    selectedFeatures = layer.LayerSource.getFeatures(QgsFeatureRequest(QgsExpression("\"{}\" = '{}'".format(layer.LayerMapping.FieldName, mapping.AttributeValue))))                    
                                    resLayer.dataProvider().addFeatures(selectedFeatures)
                                    
                        resLayer.commitChanges()
                        dissolvedResLayer = processing.run("native:dissolve", {'INPUT': resLayer, 'SEPARATE_DISJOINT' : True, 'OUTPUT': 'TEMPORARY_OUTPUT' })['OUTPUT']
                        resultLayerSet[geomType] = dissolvedResLayer


        return resultLayerSet

    @staticmethod
    def ancillaryItemsToEntityRepresentations(ancillaryData : Dict[SiacEntity, Dict[SiacGeometryType, Iterable[QgsVectorLayer]]], entityTypes : Iterable[SiacEntity]) -> Dict[SiacEntity, Dict[SiacGeometryType, SiacEntityRepresentation]]:
        res = {}

        for ent in entityTypes:
            if ent in ancillaryData.keys():                    
                                
                # entityLayers is a dict of iterable datastorelayersources, sorted by geometry type
                entityLayers : Dict[SiacGeometryType, Iterable[SiacDataStoreLayerSource]] = ancillaryData[ent]
                # we merge layers into target layer per entity, one per geometry type if needed
                tmp : Dict[SiacGeometryType, QgsVectorLayer] = DataProcessor.obtainLayerForEntityType(ent, entityLayers, ProjectDataSourceOptions.Crs) 
                
                if tmp is None:
                    continue
                else:    
                    res[ent] = {}
                    for geomType, correspondingLayer in tmp.items():    

                        newItem = SiacDataStoreLayerSource.makeNewDataStoreLayerSourceItem(correspondingLayer, DataLayer.ANCILLARY_DATA.value, ent.label, None)
                        valueMapping = AttributeValueMapping(uuid.uuid4().hex)
                        valueMapping.MappingType = SiacLayerMappingType.BY_LAYER
                        valueMapping.LayerEntityType = ent
                        newItem.LayerMapping = valueMapping
                        newItem.SetTouched()

                        currentRepr = SiacEntityRepresentation(ent)                    
                        currentRepr.Layer = newItem                       
                        currentRepr.Cache = FeatureCache.layerToCache( newItem.LayerSource, None, None ) 
                        res[ent][geomType] = currentRepr
            
        return res
    
    @staticmethod
    def rectifyLayers(inputLayer, adjustmentLayers : Dict[any, QgsVectorLayer], dissolveInputLayer = True):
        
        # dissolve input layer
        dissolvedInputLayer = inputLayer if dissolveInputLayer == False else processing.run("native:dissolve", {'INPUT': inputLayer, 'SEPARATE_DISJOINT' : True, 'OUTPUT': 'TEMPORARY_OUTPUT' })['OUTPUT']
        
        # dissolve adj layers
        adjLayers = {}
        for adjustmentLayerType, adjustmentLayer in adjustmentLayers.items():
            dissolvedAdjLayer = processing.run("native:dissolve", {'INPUT': adjustmentLayer, 'SEPARATE_DISJOINT' : True, 'OUTPUT': 'TEMPORARY_OUTPUT' })['OUTPUT']
            adjLayers[adjustmentLayerType] = dissolvedAdjLayer
        
        # iterate over adj layers and subtract from input
        # we have at least one layer here that we substract, then subtract remaining ones as well
        tmpLayers = list(adjLayers.values())
        cdiff = processing.run("native:difference", {'INPUT': dissolvedInputLayer, 'OVERLAY': tmpLayers[0],'OUTPUT':'TEMPORARY_OUTPUT','GRID_SIZE':None})['OUTPUT']
        for layer in tmpLayers[1:]:
            cdiff = processing.run("native:difference", {'INPUT': cdiff, 'OVERLAY': layer,'OUTPUT':'TEMPORARY_OUTPUT','GRID_SIZE':None})['OUTPUT']
        
        return cdiff, adjLayers


    def __init__(self, workerParams):
        super().__init__("DATA PROCESSOR Task", QgsTask.CanCancel)
        self.stopWorker = False
        self.params = workerParams
        self.results = {}
        self.uidFieldName = SiacField.SIAC_ID.value
        self.params['exception'] = ""
        self.params['results'] = {}
        self.params['geodf'] = {}

    def finished(self, result):
        if result:
            self.jobFinished.emit(True, self.params ) 
        else:
            self.jobFinished.emit(False, self.params )

    def cancel(self):
        self.stopWorker = True
        super().cancel()

    def run(self):
        
        self.siacToolProgressMessage.emit("Initializing", Qgis.Info)  
        self.assessDataTask()
        return True

    def assessDataTask(self):

        if self.params['TASK'] is DataProcessorTask.COMPUTE_STREET_MORPHOLOGY:
            
            # assess street profile using momepy: Do all required steps here            
            self.siacToolMaximumProgressValue.emit(5)
            self.siacToolProgressValue.emit(0)

            self.siacToolProgressMessage.emit("Create unique identifiers", Qgis.Info) 
            self.params[DataLayer.STREETS].LayerSource = LayerHelper.createLayerUniqueId(self.params[DataLayer.STREETS].LayerSource, SiacField.UID_STREETSEGMENT.value)
            self.params[DataLayer.BUILDINGS].LayerSource = LayerHelper.createLayerUniqueId(self.params[DataLayer.BUILDINGS].LayerSource, SiacField.UID_BUILDING.value)
            self.siacToolProgressValue.emit(1)

            # create geo-dfs from qgsvectorlayers
            self.siacToolProgressMessage.emit("Generating tool data", Qgis.Info) 
            self.params['geodf'][DataLayer.STREETS] = LayerHelper.convertQgsLayerToGeoDataFrame(self.params[DataLayer.STREETS].LayerSource, SiacField.UID_STREETSEGMENT.value, self.setProgress, self.params['CRS'])
            self.params['geodf'][DataLayer.BUILDINGS] = LayerHelper.convertQgsLayerToGeoDataFrame(self.params[DataLayer.BUILDINGS].LayerSource, SiacField.UID_BUILDING.value, self.setProgress, self.params['CRS'])
            self.siacToolProgressValue.emit(2)

            # compute street widths and convert result back to QgsVectorLayer
            self.siacToolProgressMessage.emit("Assessing street features", Qgis.Info) 
            self.params['geodf'][DataLayer.MORPHOLOGY_STREETS] = MomepyHelper.determineStreetProfile(self.params['geodf'][DataLayer.STREETS], self.params['geodf'][DataLayer.BUILDINGS], self.params['MAXIMUM_STREET_WIDTH'], None )
            self.siacToolProgressValue.emit(3)
            
            # convert result to qgsvectorlayer
            self.siacToolProgressMessage.emit("Generating layer", Qgis.Info) 
            tmpLayer = LayerHelper.convertGeoDataFrameToQgsLayer(self.params['geodf'][DataLayer.MORPHOLOGY_STREETS], DataLayer.MORPHOLOGY_STREETS.value, self.params['CRS'])     
            
            strDs = SiacDataStoreLayerSource.makeNewDataStoreLayerSourceItem(tmpLayer, DataLayer.MORPHOLOGY_STREETS.value, DataLayer.MORPHOLOGY_STREETS.value, None)
            strDs.SetTouched()
            self.params['results'][DataLayer.MORPHOLOGY_STREETS] = strDs

            self.siacToolProgressValue.emit(4)

            # buffer around street centerlines based on momepy widths
            self.siacToolProgressMessage.emit("Modelling street morphology", Qgis.Info) 
            toolSource = self.params['results'][DataLayer.MORPHOLOGY_STREETS].LayerSource
            tmp = processing.run("native:buffer", {'INPUT': toolSource, 'DISTANCE' : QgsProperty.fromExpression('"width"/2'), 'END_CAP_STYLE' : 2, 'DISSOLVE' : False, 'SEGMENTS' : 10, 'OUTPUT' : 'TEMPORARY_OUTPUT' })
            self.params['results'][DataLayer.MORPHOLOGY_STREETS].LayerSource = tmp['OUTPUT'] 
            self.siacToolProgressValue.emit(5)
                  
            return True

        if self.params['TASK'] is DataProcessorTask.COMPUTE_CLOSED_TESSELLATION:
            
            # enclosed tessellation
            self.siacToolProgressMessage.emit("Building enclosed tessellation from street and building geometries", Qgis.Info) 
            self.siacToolMaximumProgressValue.emit(4)
            self.siacToolProgressValue.emit(0)
            
            self.siacToolProgressMessage.emit("Create unique identifiers", Qgis.Info) 
            self.params[DataLayer.STREETS].LayerSource = LayerHelper.createLayerUniqueId(self.params[DataLayer.STREETS].LayerSource, self.uidFieldName)
            self.params[DataLayer.BUILDINGS].LayerSource = LayerHelper.createLayerUniqueId(self.params[DataLayer.BUILDINGS].LayerSource, self.uidFieldName)
            self.siacToolProgressValue.emit(1)

            # create geo-dfs from qgsvectorlayers
            self.siacToolProgressMessage.emit("Generating tool data", Qgis.Info) 
            self.params['geodf'][DataLayer.STREETS] = LayerHelper.convertQgsLayerToGeoDataFrame(self.params[DataLayer.STREETS].LayerSource, self.uidFieldName, self.setProgress, self.params['CRS'])
            self.params['geodf'][DataLayer.BUILDINGS] = LayerHelper.convertQgsLayerToGeoDataFrame(self.params[DataLayer.BUILDINGS].LayerSource, self.uidFieldName, self.setProgress, self.params['CRS'])
            self.siacToolProgressValue.emit(2)
            
            # tessellation using momepy            

            # TODO: add land-use based barriers support when respective data is provided in the tool
            self.siacToolProgressMessage.emit("Generating tessellation", Qgis.Info)             
            self.params['geodf'][DataLayer.MORPHOLOGY_PLOTS] = MomepyHelper.enclosedTessellation(self.params['geodf'][DataLayer.BUILDINGS], self.params['geodf'][DataLayer.STREETS], self.uidFieldName, useConvexHull=False, limitingDistance=100)
            self.siacToolProgressValue.emit(3)
            
            # convert result to qgsvectorlayer
            self.siacToolProgressMessage.emit("Generating layer", Qgis.Info) 
            tmpLayer = LayerHelper.convertGeoDataFrameToQgsLayer(self.params['geodf'][DataLayer.MORPHOLOGY_PLOTS], DataLayer.MORPHOLOGY_PLOTS.value, self.params['CRS'])                    
            
            plotDs = SiacDataStore.makeNewDataStoreLayerSourceItem(tmpLayer, DataLayer.MORPHOLOGY_PLOTS.value, DataLayer.MORPHOLOGY_PLOTS.value, None )
            plotDs.SetTouched()
            self.params['results'][DataLayer.MORPHOLOGY_PLOTS] = plotDs
            
            self.params['results'][DataLayer.MORPHOLOGY_PLOTS].LayerSource = LayerHelper.createLayerUniqueId(self.params['results'][DataLayer.MORPHOLOGY_PLOTS].LayerSource, SiacField.SIAC_ID.value)
            self.siacToolProgressValue.emit(4)
        
            return True

      
