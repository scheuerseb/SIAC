from qgis.core import *
from qgis.gui import QgsMessageBar, QgsMapLayerComboBox, QgsFieldComboBox, QgsMapTool
from qgis.PyQt.QtCore import Qt, QThread, QSettings, QTranslator, QCoreApplication, QVariant, pyqtSignal, QAbstractTableModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QErrorMessage, QAction, QMessageBox, QProgressBar
import processing

import statistics as sts
from sklearn import linear_model
import statsmodels.api as sm
from collections import namedtuple
from typing import Iterable, Dict, NamedTuple

from ..SiacDataStore import SiacDataStoreLayerSource
from ..SiacEnumerations import *
from ..SiacFoundation import LayerHelper, SelectionHelper, FeatureCache, CachedLayerItem
from ..MomepyIntegration import MomepyHelper
from ..TreeRichnessAndDiversityAssessment import *
from ..toolkitData.SiacDataSourceOptions import ProjectDataSourceOptions
from ..SiacRegressionModule import LocalRegressionParameters, SiacRegressionModule
from ..toolkitData.SiacDataStoreLayerSource import SiacDataStoreLayerSource
from ..toolkitData.SiacEntityRepresentation import SiacEntityRepresentation
from ..toolkitData.SiacEntities import SiacEntity
from ..SiacEntityManagement import SiacEntityLayerManager
from .DATA import DataProcessor
#from .COIN import IndicatorComputation


class SiteAssessment(QgsTask):
    """
    Assessment of spatial analysis units: Determine total and relative tree cover etc.

    Extends: QgsTask.
    
    Parameters
    ----------
    workerParams : Key-value pairs containing the input data for the QgsTask worker.

    """

    @staticmethod 
    def getModuleSupportedSiacEntityTypes() -> Iterable[SiacEntity]:
        # this tool module currently supports the following entities
        return [SiacEntity.URBAN_GREEN_SPACE, SiacEntity.WATER_BODIES, SiacEntity.FOREST, SiacEntity.AMENITY_FEATURES_GENERAL]

    @staticmethod
    def determineAbsoluteAndRelativeCoverFromIntersectingFeatures(referenceGeometry, targetFeatures, weightedAverageVariables : Iterable[str] = None):

        
        weightedAverages = {}

        # weightedAverageVariables is a list of field names, for which the weighted average is to be determined from/for the intersecting features
        if weightedAverageVariables is not None:
            for v in weightedAverageVariables:
                weightedAverages[v] = 0

        totalArea = 0
        for f in targetFeatures:
            intersectingPart = referenceGeometry.intersection(f.geometry())
            areaOfIntersectingPart = intersectingPart.area() 

            # if weighted average should be determined for variable(s), then iterate over the list, retrieve the value of field for current feature
            # multiply by intersecting area and add to total
            if weightedAverageVariables is not None:
                for v in weightedAverageVariables:
                    currentValue = f[v]
                    weightedAverages[v] += (currentValue * areaOfIntersectingPart)
            
            totalArea += areaOfIntersectingPart  

        if weightedAverageVariables is not None:
            for v in weightedAverageVariables:
                weightedAverages[v] = weightedAverages[v] / totalArea if totalArea > 0 else 0
 

        relativeArea = totalArea/referenceGeometry.area() if totalArea <= referenceGeometry.area() else 1 # rectify problems due to wrongly dissolved input layers for now in this way       
        return totalArea, relativeArea, weightedAverages
    
       

    @staticmethod
    def rectifyLayersForGeometry(referenceGeometry, inputLayerCache, adjustmentLayerCaches ):

        inputFeatureIds = SelectionHelper.getIntersectingFeatureIds(referenceGeometry.buffer(100,100), inputLayerCache, TopologyRule.INTERSECTS)
        inputFeatures = inputLayerCache.getFeaturesFromCache(inputFeatureIds)

        # make temporary layer for input features
        tmpInputLayer = LayerHelper.createTemporaryLayer(inputLayerCache.Crs, "tmpInputs", inputLayerCache.GeometryType)
        tmpInputLayer.startEditing()
        tmpInputLayer.dataProvider().addFeatures(inputFeatures)
        tmpInputLayer.commitChanges()

        adjustmentFeatureLayerSet = []
        for adjustmentLayerCache in adjustmentLayerCaches:
            adjLayerFeatureIds = SelectionHelper.getIntersectingFeatureIds(referenceGeometry.buffer(100,100), adjustmentLayerCache, TopologyRule.INTERSECTS)
            adjFeatures = adjustmentLayerCache.getFeaturesFromCache(adjLayerFeatureIds)

            # make temporary layer for input features
            tmpAdjInputLayer = LayerHelper.createTemporaryLayer(adjustmentLayerCache.Crs, "tmpAdjInputs", adjustmentLayerCache.GeometryType)
            tmpAdjInputLayer.startEditing()
            tmpAdjInputLayer.dataProvider().addFeatures(adjFeatures)
            tmpAdjInputLayer.commitChanges()

            adjustmentFeatureLayerSet.append(tmpAdjInputLayer)

        # try to dissolve and unify layers
        # first, dissolve each layer quickly
        dissolvedInputLayer = processing.run("native:dissolve", {'INPUT': tmpInputLayer, 'SEPARATE_DISJOINT' : True, 'OUTPUT': 'TEMPORARY_OUTPUT' })['OUTPUT']

        dissolvedAdjLayers = []
        for layer in adjustmentFeatureLayerSet:
            tmp = processing.run("native:dissolve", {'INPUT': layer, 'SEPARATE_DISJOINT' : True, 'OUTPUT': 'TEMPORARY_OUTPUT' }) 
            dissolvedAdjLayers.append(tmp['OUTPUT'])

        # now try to subtract stepwise 
        # we should have at least one adj layer; so 0 is difference by default
        cdiff = processing.run("native:difference", {'INPUT': dissolvedInputLayer, 'OVERLAY': dissolvedAdjLayers[0],'OUTPUT':'TEMPORARY_OUTPUT','GRID_SIZE':None})['OUTPUT']
        for layer in dissolvedAdjLayers[1:]:
            cdiff = processing.run("native:difference", {'INPUT': cdiff, 'OVERLAY': layer,'OUTPUT':'TEMPORARY_OUTPUT','GRID_SIZE':None})['OUTPUT']
        
        return cdiff





    @staticmethod
    def assessMapLocation(toolParams):
               
        cacheOfCanopyCoverFeatures = toolParams['CACHE'].getFromCache(DataLayer.TREE_COVER)
        cacheOfStreetFeatures = toolParams['CACHE'].getFromCache(DataLayer.MORPHOLOGY_STREETS)
        cacheOfBuildingFeatures = toolParams['CACHE'].getFromCache(DataLayer.BUILDINGS)

        toolParams['LAYER'].startEditing()

        cDiameter = toolParams["DIAMETER"]()

        # construct a feature geometry from coordinates
        feat = QgsFeature(toolParams['LAYER'].fields())
        circleGeometry = QgsGeometry.fromPointXY(QgsPointXY(toolParams['COORDINATE_X'], toolParams['COORDINATE_Y'])).buffer( cDiameter/2 ,100)
        feat.setGeometry(circleGeometry)

        # now rectify input layers
        diffs = SiteAssessment.rectifyLayersForGeometry(circleGeometry, cacheOfStreetFeatures, [cacheOfBuildingFeatures])

        # determine canopies within the geometry      
        treeCoverFeatures = cacheOfCanopyCoverFeatures.getFeaturesFromCacheInGeometry(circleGeometry, TopologyRule.INTERSECTS )  
        totalWoodyVegetationCover, treeCoverShare = SiteAssessment.determineAbsoluteAndRelativeCoverFromIntersectingFeatures(circleGeometry, treeCoverFeatures)
        totalBuildingCover, buildingCoverShare = SiteAssessment.determineAbsoluteAndRelativeCoverFromIntersectingFeatures(circleGeometry, cacheOfBuildingFeatures.getFeaturesFromCacheInGeometry(circleGeometry, TopologyRule.INTERSECTS ) )
        totalStreetCover, streetCoverShare = SiteAssessment.determineAbsoluteAndRelativeCoverFromIntersectingFeatures(circleGeometry, list(diffs.getFeatures()) )
        
        
        totalImperviousArea = totalBuildingCover + totalStreetCover
        imperviousAreaShare = totalImperviousArea/circleGeometry.area() if totalImperviousArea <= circleGeometry.area() else 1 # TODO: assess layers better to avoid this altogether
        
        feat.setAttributes( [ cDiameter, len(treeCoverFeatures), totalWoodyVegetationCover, treeCoverShare, totalImperviousArea, imperviousAreaShare ] )

        toolParams['LAYER'].dataProvider().addFeatures([feat])
        toolParams['LAYER'].commitChanges()
        
        # add to tool output window
        log = [
            "Within a radius of {:0.2f}m from location ({:0.2f},{:0.2f}), tree cover share is {:0.2f}% and impervious area share is {:0.2f}%".format( cDiameter/2, toolParams['COORDINATE_X'], toolParams['COORDINATE_Y'], 100*treeCoverShare, 100*imperviousAreaShare )
        ]
        toolParams['LOGGER'](SiacToolkitModule.MAP_PERIMETER_TOOL, log)

        

    
    MESSAGE_CATEGORY = "SIAC"
    
    siacToolMaximumProgressValue = pyqtSignal(int)
    siacToolProgressValue = pyqtSignal(int)
    siacToolProgressMessage = pyqtSignal(object, object)
    jobFinished = pyqtSignal(bool, object)



    def __init__(self, workerParams):
        super().__init__("SITA Task", QgsTask.CanCancel)
        self.stopWorker = False
        self.params = workerParams
        self.results = {}
        self.totalSteps = 5
        self.uidFieldName = SiacField.SIAC_ID.value
        self.params['exception'] = ""

        self.params['results'] = {}
        self.params['results'][SiacToolkitDataType.LOCAL_COOLING_POTENTIAL_DATA] = None
        self.params['results']['REPORT'] = []


    def finished(self, result):
        if result:
            self.jobFinished.emit(True, self.params ) 
        else:
            self.jobFinished.emit(False, self.params )

    def cancel(self):
        self.stopWorker = True
        super().cancel()

    def run(self):       
        
        self.siacToolMaximumProgressValue.emit(self.totalSteps)
        self.siacToolProgressValue.emit(0)

        # update caches
        self.siacToolProgressMessage.emit("Update caches", Qgis.Info)  
        self.params["CACHE"].cacheLayer(self.params[DataLayer.TREE_COVER], DataLayer.TREE_COVER, SiacField.UID_CANOPY.value)   
        self.params["CACHE"].cacheLayer(self.params[DataLayer.BUILDINGS], DataLayer.BUILDINGS)
        self.params["CACHE"].cacheLayer(self.params[DataLayer.MORPHOLOGY_STREETS], DataLayer.MORPHOLOGY_STREETS)

        self.siacToolProgressValue.emit(1)

        # act upon availability of optional layers and ancillary data
        if self.params[DataLayer.CLASSIFIED_TREES] is not None:
            self.params["CACHE"].cacheLayer(self.params[DataLayer.CLASSIFIED_TREES], DataLayer.CLASSIFIED_TREES, SiacField.UID_TREE.value)  

        #self.params['ENTITY_LAYERS'] : Dict[SiacEntity, Dict[SiacGeometryType, EntityRepresentation]] = {}
        self.params['ENTITY_LAYERS'] : SiacEntityLayerManager = self.params[DataLayer.ANCILLARY_DATA]
        
        if self.params[DataLayer.ANCILLARY_DATA] is not None:    

            self.siacToolProgressMessage.emit("Extracting entities", Qgis.Info)              
            
            # make the manager process the data
            ancillaryLayerManager : SiacEntityLayerManager = self.params['ENTITY_LAYERS']
            ancillaryLayerManager.processLayers()

            #ancillaryData : Dict[SiacEntity, Dict[SiacGeometryType, Iterable[SiacDataStoreLayerSource]]] = self.params[DataLayer.ANCILLARY_DATA]
            #res : Dict[SiacEntity, Dict[SiacGeometryType, EntityRepresentation]] = DataProcessor.ancillaryItemsToEntityRepresentations(ancillaryData, SiteAssessment.getModuleSupportedSiacEntityTypes())
            
            # we now have a single layer, stored as entity representation with datastorelayersource as layer, per entity type and geometry type.
            # now pre-process layers further according to SITA requirements 
            for ent in ancillaryLayerManager.containedEntityTypes():
                # here, we further prepare polygon data layers for SITA to improve performance
                hasLayer, currentEntityRepresentation = ancillaryLayerManager.getEntityRepresentationForGeometryTypeForEntityType(ent, SiacGeometryType.POLYGON)
                if hasLayer:

                    # TODO: Add further actions depending on type of entity
                    # These should mainly address rectification of certain topological issues                    
                    adjLayers = { DataLayer.BUILDINGS : self.params[DataLayer.BUILDINGS] }   

                    if currentEntityRepresentation.EntityType == SiacEntity.FOREST:
                        # if forest, subtract from these areas also tree cover
                        # there may only be one tree cover at a given location, either tree cover from trees, or from forest, so to say
                        adjLayers[DataLayer.TREE_COVER] = self.params[DataLayer.TREE_COVER]

                    rectifiedTmpLayer, _ = DataProcessor.rectifyLayers( currentEntityRepresentation.Layer.LayerSource, adjLayers )        
                    currentEntityRepresentation.Layer.LayerSource = rectifiedTmpLayer 
                    #processing.run("native:intersection", {'INPUT': rectifiedTmpLayer, 'OVERLAY': self.params['BASE_LAYER'].LayerSource,'INPUT_FIELDS':[],'OVERLAY_FIELDS':[],'OVERLAY_FIELDS_PREFIX':'','OUTPUT':'TEMPORARY_OUTPUT','GRID_SIZE':None})['OUTPUT']
                    currentEntityRepresentation.Cache = FeatureCache.layerToCache(currentEntityRepresentation.Layer.LayerSource, DataLayer.ANCILLARY_DATA, None, None)         

        self.siacToolProgressValue.emit(2)

        # determine if we have the information to assess tree species diversity
        if not self.params['SPECIES_ATTRIBUTE'].strip() or self.params[DataLayer.CLASSIFIED_TREES] is None:
            QgsMessageLog.logMessage("Disabled tree species richness assessment", self.MESSAGE_CATEGORY, Qgis.MessageLevel.Warning)
            self.params['ASSESS_TREE_SPECIES_RICHNESS'] = False
            self.params['results'][SiacToolkitDataType.RICHNESS_AND_DIVERSITY_ASSESSMENT] = None
        else:
            QgsMessageLog.logMessage("Enabled tree species richness assessment", self.MESSAGE_CATEGORY, Qgis.Success)
            self.params['ASSESS_TREE_SPECIES_RICHNESS'] = True
            self.params['results'][SiacToolkitDataType.RICHNESS_AND_DIVERSITY_ASSESSMENT] = TreeRichnessAndDiversityAssessment(self.params['CACHE'].getFromCache(DataLayer.CLASSIFIED_TREES), self.params['SPECIES_ATTRIBUTE'], self.params['FRUIT_TREE_SPECIES']) # new class that keeps track of everything


        self.siacToolProgressMessage.emit("Starting Site Assessment", Qgis.Info)  


        if self.params['TASK'] == SitaTask.ITERATE_PLOTS:
            self.params['results']['BASE_LAYER'] = self.params['BASE_LAYER'].clone() #LayerHelper.copyLayer(self.params['BASE_LAYER'].LayerSource)              
            self.assessInputLayer('BASE_LAYER')

        
        if self.params['TASK'] == SitaTask.ITERATE_SAMPLED_LOCATIONS:
            # generate sample points
            # additionally, create a new datastorelayersource item to hold the result
            resultItem = SiacDataStoreLayerSource()
            resultItem.LayerName = DataLayer.SITA_SAMPLED_LOCATIONS.value
            resultItem.LayerType = DataLayer.SITA_SAMPLED_LOCATIONS.value
            resultItem.SetTouched()
            
            sampleSize = self.params['SAMPLE_SIZE'] 
            sampleDist = self.params['SAMPLE_DIST']
            sampleDiameter = self.params['SAMPLE_DIAMETER']
            
            sampledPoints = processing.run("qgis:randompointsinlayerbounds", {'INPUT': self.params[DataLayer.TREE_COVER],'POINTS_NUMBER': sampleSize, 'MIN_DISTANCE' : sampleDist, 'OUTPUT':'TEMPORARY_OUTPUT'})['OUTPUT']
            
            # generate the layer to iterate over
            resultItem.LayerSource = LayerHelper.createTemporaryLayer(ProjectDataSourceOptions.Crs, "Sampled Locations", "polygon")
            resultItem.LayerSource.startEditing()

            # iterate over random point features
            for p in sampledPoints.getFeatures():
                feat = QgsFeature()
                circleGeometry = QgsGeometry.fromPointXY(QgsPointXY(p.geometry().asPoint().x(), p.geometry().asPoint().y())).buffer( sampleDiameter/2 ,100)
                feat.setGeometry(circleGeometry)
                resultItem.LayerSource.addFeature(feat)            
            resultItem.LayerSource.commitChanges()

            self.params['results'][DataLayer.SITA_SAMPLED_LOCATIONS] = resultItem

            # pass it to the assessor
            self.assessInputLayer(DataLayer.SITA_SAMPLED_LOCATIONS)


        return True

    def assessInputLayer(self, layerType, params = None):

        # get reference to data source
        inputLayer = self.params['results'][layerType].LayerSource
        
        # get caches
        self.siacToolProgressMessage.emit("Collecting Caches", Qgis.Info)  

        cacheOfCanopyCoverFeatures = self.params['CACHE'].getFromCache(DataLayer.TREE_COVER)
        cacheOfStreetFeatures = self.params['CACHE'].getFromCache(DataLayer.MORPHOLOGY_STREETS)
        cacheOfBuildingFeatures = self.params['CACHE'].getFromCache(DataLayer.BUILDINGS)

        # determine presence of ESS scaling value field in tree cover input layer
        containsEssScalingField = LayerHelper.containsFieldWithName(self.params[DataLayer.TREE_COVER], SiacField.ESS_MEDIATION.value)

        # optional layers
        if self.params[DataLayer.CLASSIFIED_TREES] is not None:
            cacheOfClassifiedTreeFeatures = self.params['CACHE'].getFromCache(DataLayer.CLASSIFIED_TREES)       
        
        self.siacToolProgressValue.emit(3)
        
        self.siacToolProgressMessage.emit("Collecting Fields", Qgis.Info)  

        # add relevant fields to input layer
        # add certain indicator fields
        # inputLayer, _ = LayerHelper.addAttributeToLayer(inputLayer, SiacField.RELEVANT_FEATURE_AREA.value, QVariant.Double )        
        inputLayer, idxCanopyAreaTotalField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.MORPHOLOGY_TREE_COVER_TOTAL.value, QVariant.Double )
        inputLayer, idxCanopyAreaShareField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.MORPHOLOGY_TREE_COVER_RELATIVE.value, QVariant.Double )                                
        inputLayer, idxBuildingTotalField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.MORPHOLOGY_BUILDING_TOTAL.value, QVariant.Double )
        inputLayer, idxBuildingShareField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.MORPHOLOGY_BUILDING_RELATIVE.value, QVariant.Double )
        inputLayer, idxStreetTotalField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.MORPHOLOGY_STREET_TOTAL.value, QVariant.Double )
        inputLayer, idxStreetShareField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.MORPHOLOGY_STREET_RELATIVE.value, QVariant.Double )        
        inputLayer, idxImperviousAreaTotalField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.MORPHOLOGY_IMPERVIOUS_AREA_TOTAL.value, QVariant.Double )
        inputLayer, idxImperviousAreaShareField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.MORPHOLOGY_IMPERVIOUS_AREA_RELATIVE.value, QVariant.Double )                        
        
        # following fields optional for classified trees being provided
        if self.params[DataLayer.CLASSIFIED_TREES] is not None:
            inputLayer, idxTreeCountField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.MORPHOLOGY_TREE_COUNT.value, QVariant.Int )
            inputLayer, idxTreeDensityField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.MORPHOLOGY_TREE_DENSITY.value, QVariant.Double )        

        # conditionally add fields as function of available data/level of details
        if self.params['ASSESS_TREE_SPECIES_RICHNESS'] == True:
            inputLayer, idxTreeSpeciesDiversityField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.MORPHOLOGY_TREE_SPECIES_RICHNESS.value, QVariant.Int )
            inputLayer, idxSpeciesListField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.TREE_SPECIES.value, QVariant.String )
            inputLayer, idxTreeSpeciesCountField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.TREE_SPECIES_COUNTS.value, QVariant.String )
            inputLayer, idxContainsFruitTreesField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.MORPHOLOGY_CONTAINS_FRUIT_TREES.value, QVariant.Int )
            inputLayer, idxFruitTreeCountField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.FRUIT_TREE_COUNT.value, QVariant.Int )
            inputLayer, idxFruitTreeShareField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.FRUIT_TREE_SHARE.value, QVariant.Double )

        # add ESS_K field if present in tree cover 
        if containsEssScalingField:
            inputLayer, idxEssScalingField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.ESS_MEDIATION.value, QVariant.Double)
        
        self.siacToolProgressMessage.emit("Collecting Ancillary Data Sources", Qgis.Info)  
        alignmentLayers = { DataLayer.BUILDINGS : self.params[DataLayer.BUILDINGS] }                 
                
        # depending on entity geometry types, add fields to output layer     
        # we want to indicate presence or absence of point entities
        # we want to indicate total and relative area of polygon features   
        entityRepresentations : Iterable[SiacEntityRepresentation] = self.params['ENTITY_LAYERS'].getEntityRepresentations()

        entity : SiacEntityRepresentation
        for entity in entityRepresentations:
            
            if entity.Layer.GeometryType == SiacGeometryType.POINT:
                inputLayer, entity.FieldIndexContainment = LayerHelper.addAttributeToLayer(inputLayer, entity.EntityType.getContainmentFieldName(), QVariant.Int ) 

            if entity.Layer.GeometryType == SiacGeometryType.POLYGON:
                # shares and total area fields are only written if ancillary type is polygon geometry; otherwise, we require a containment field
                inputLayer, entity.FieldIndexTotal = LayerHelper.addAttributeToLayer(inputLayer, entity.EntityType.getTotalCoverFieldName(), QVariant.Double ) 
                inputLayer, entity.FieldIndexRelative = LayerHelper.addAttributeToLayer(inputLayer, entity.EntityType.getRelativeCoverFieldName(), QVariant.Double ) 
                alignmentLayers[entity.EntityType] = entity.Layer.LayerSource


        # make proper layers
        # consider all ancillary data layers (TODO: with only polygon geometry) to correct street morph.        
        self.siacToolProgressMessage.emit("Collecting Input Layers", Qgis.Info)  
        
        rectifiedStreetMorphologyLayer, dissolvedAdjustmentLayers = DataProcessor.rectifyLayers(self.params[DataLayer.MORPHOLOGY_STREETS], alignmentLayers )
        intersectedRectifiedStreetMorphologyLayer = processing.run("native:intersection", {'INPUT': rectifiedStreetMorphologyLayer, 'OVERLAY': inputLayer,'INPUT_FIELDS':[],'OVERLAY_FIELDS':[],'OVERLAY_FIELDS_PREFIX':'','OUTPUT':'TEMPORARY_OUTPUT','GRID_SIZE':None})['OUTPUT']
        intersectedRectifiedStreetMorphologyLayerCache = FeatureCache.layerToCache( intersectedRectifiedStreetMorphologyLayer, None, None )

        # prepare feature update map
        updateMap = {}

        # progress reporting
        processedFeatures = 0
        totalFeatures = inputLayer.featureCount()

        inputLayer.startEditing()

        self.siacToolProgressMessage.emit("Iterating Features", Qgis.Info)  
        for polygonFeature in inputLayer.getFeatures():

            # intersect feature with trees
            polygonId = polygonFeature.id()
            polygonGeometry = polygonFeature.geometry()
            polygonArea = polygonGeometry.area()

            updateMap[polygonId] = {}

            # shares of total and relative covers: tree cover, building and streets as impervious cover            
            # note that for tree cover, if ESS_K field is present, for this field the weighted average should be determined to carry over averaged tree health into the plot feature
            if containsEssScalingField:
                totalTreeCover, treeCoverShare, weightedAverages = SiteAssessment.determineAbsoluteAndRelativeCoverFromIntersectingFeatures(polygonGeometry, cacheOfCanopyCoverFeatures.getFeaturesFromCacheInGeometry(polygonGeometry, TopologyRule.INTERSECTS ), weightedAverageVariables=[SiacField.ESS_MEDIATION.value]  )
                updateMap[polygonId][idxEssScalingField] = weightedAverages[SiacField.ESS_MEDIATION.value]        
            else:
                totalTreeCover, treeCoverShare, _ = SiteAssessment.determineAbsoluteAndRelativeCoverFromIntersectingFeatures(polygonGeometry, cacheOfCanopyCoverFeatures.getFeaturesFromCacheInGeometry(polygonGeometry, TopologyRule.INTERSECTS )  )

            totalBuildingCover, buildingCoverShare, _ = SiteAssessment.determineAbsoluteAndRelativeCoverFromIntersectingFeatures(polygonGeometry, cacheOfBuildingFeatures.getFeaturesFromCacheInGeometry(polygonGeometry, TopologyRule.INTERSECTS ) )
            totalStreetCover, streetCoverShare, _ = SiteAssessment.determineAbsoluteAndRelativeCoverFromIntersectingFeatures(polygonGeometry, intersectedRectifiedStreetMorphologyLayerCache.getFeaturesFromCacheInGeometry(polygonGeometry, TopologyRule.INTERSECTS) )

            # total impervious area: possibly, add certain values later if there're entities of relevance in ancillary data layers            
            totalImperviousArea = totalBuildingCover + totalStreetCover
            
            # determine for each ancillary layer of relevance total and share
            entityRepresentations : Iterable[SiacEntityRepresentation] = self.params['ENTITY_LAYERS'].getEntityRepresentations()
            for entity in entityRepresentations:
                
                # TODO: add further logic depending on entity type

                # TODO: add further logic depending on geometry type
                # for points, determine intersection and thereupon presence or absence
                # for polygons, determine spatial properties of intersects
                if entity.Layer.GeometryType == SiacGeometryType.POINT:
                    intersectingPointFeatures = entity.Cache.getFeaturesFromCacheInGeometry(polygonGeometry, TopologyRule.INTERSECTS)
                    updateMap[polygonId][entity.FieldIndexContainment] =  1 if len(intersectingPointFeatures) > 0 else 0
                        
                if entity.Layer.GeometryType == SiacGeometryType.POLYGON:
                    totalCover, relativeCover, _ = SiteAssessment.determineAbsoluteAndRelativeCoverFromIntersectingFeatures(polygonGeometry, entity.Cache.getFeaturesFromCacheInGeometry(polygonGeometry, TopologyRule.INTERSECTS ) )
                    updateMap[polygonId][entity.FieldIndexTotal] = totalCover
                    updateMap[polygonId][entity.FieldIndexRelative] = relativeCover


            imperviousAreaShare = totalImperviousArea/polygonArea if totalImperviousArea <= polygonArea else 1 # TODO: assess layers better to avoid this altogether

            updateMap[polygonId][idxCanopyAreaTotalField] = totalTreeCover
            updateMap[polygonId][idxCanopyAreaShareField] = treeCoverShare                                           
            updateMap[polygonId][idxBuildingTotalField] = totalBuildingCover
            updateMap[polygonId][idxBuildingShareField] = buildingCoverShare
            updateMap[polygonId][idxStreetTotalField] = totalStreetCover
            updateMap[polygonId][idxStreetShareField] = streetCoverShare            
            updateMap[polygonId][idxImperviousAreaTotalField] = totalImperviousArea
            updateMap[polygonId][idxImperviousAreaShareField] = imperviousAreaShare
            

            # consideration of indicators that are only available if optional layers are provided
            if self.params[DataLayer.CLASSIFIED_TREES] is not None:
                # tree count
                containedTrees = SelectionHelper.getIntersectingFeatureIds(polygonGeometry, cacheOfClassifiedTreeFeatures, TopologyRule.INTERSECTS)                        
                treeCount = len(containedTrees)
                updateMap[polygonId][idxTreeCountField] = treeCount
                                    
                # tree density
                treeDensity = treeCount/(polygonArea/10000)
                updateMap[polygonId][idxTreeDensityField] = treeDensity
                
                # tree species richness assessment
                if self.params['ASSESS_TREE_SPECIES_RICHNESS']:
                    resultLocalDiversity : TreeRichnessAndDiversityAssessmentResult = self.params['results'][SiacToolkitDataType.RICHNESS_AND_DIVERSITY_ASSESSMENT].assessSpatialUnitOfAnalysis(polygonId, containedTrees)
                    
                    updateMap[polygonId][idxTreeSpeciesDiversityField] = resultLocalDiversity.Richness 
                    updateMap[polygonId][idxSpeciesListField] = resultLocalDiversity.LocalSpeciesAsString
                    updateMap[polygonId][idxTreeSpeciesCountField] = resultLocalDiversity.LocalSpeciesWithCountsAsString
                    updateMap[polygonId][idxContainsFruitTreesField] = resultLocalDiversity.ContainsFruitTreeAsNumeric
                    updateMap[polygonId][idxFruitTreeCountField] = resultLocalDiversity.FruitTreeCount 
                    updateMap[polygonId][idxFruitTreeShareField] = resultLocalDiversity.FruitTreeShare


            # report progress
            processedFeatures += 1
            self.setProgress( (processedFeatures/totalFeatures)*100 )  
                

        # done iterating over all features in analysis layer
        # update features
        # write results
        inputLayer.dataProvider().changeAttributeValues(updateMap)
        inputLayer.commitChanges()
        
        self.siacToolProgressValue.emit(4)
        self.siacToolProgressMessage.emit("Finishing ...", Qgis.Info)  

        self.params['results']['REPORT'].append('Assessed {} features'.format(totalFeatures))


        


        
