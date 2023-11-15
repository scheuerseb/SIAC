from qgis.core import *
from qgis.core import *
from qgis.gui import QgsMessageBar, QgsMapLayerComboBox, QgsFieldComboBox
from qgis.PyQt.QtCore import Qt, QThread, QSettings, QTranslator, QCoreApplication, QVariant, pyqtSignal, QAbstractTableModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QErrorMessage, QAction, QMessageBox, QProgressBar
import processing
import statsmodels.api as sm
from typing import Iterable, Dict
import statistics as sts
import pandas as pd

from .TCAC import TreeRichnessAndDiversityAssessment, TreeRichnessAndDiversityAssessmentResult
from ..SiacRegressionModule import LocalRegressionParameters, SiacRegressionModule
from ..SiacEnumerations import *
from ..SiacFoundation import LayerHelper, SelectionHelper, Utilities, CachedLayerItem, FeatureCache
from ..MomepyIntegration import MomepyHelper
from ..toolkitData.SiacEntityRepresentation import SiacEntityRepresentation
from ..toolkitData.SiacDataStoreLayerSource import SiacDataStoreLayerSource
from ..toolkitData.SiacOrientedMbr import SiacOrientedMinimumBoundingRectangle
from ..toolkitData.SiacDataSourceOptions import ProjectDataSourceOptions
from .DATA import DataProcessor
from ..SiacEntityManagement import SiacEntityLayerManager
from .SITA import SiteAssessment



# see https://api.qgis.org/api/3.16/classQgsAggregateCalculator.html#a51eb9f5752cf107d72266829a21cf2fa for available summary statistics


# indicator assessment: structure of requests:
# REQUESTS : []
# a Request: { INDICATOR : type, INPUTS : [ layers and parameters ], "ADD_AS_OUTPUT" : Not supported at this moment, "REPORT" : [ params to eval ] }



class IndicatorComputation(QgsTask):

    MESSAGE_CATEGORY = "COIN"

    siacToolMaximumProgressValue = pyqtSignal(int)
    siacToolProgressValue = pyqtSignal(int)
    siacToolProgressMessage = pyqtSignal(object, object)
    jobFinished = pyqtSignal(bool, object)
    
    def __init__(self, workerParams):
        super().__init__("COIN Task", QgsTask.CanCancel)
        self.stopWorker = False
        self.params = workerParams        
        self.uidFieldName = SiacField.SIAC_ID.value
        
        self.params['exception'] = ""
        self.params['results'] = {}
        
        self.params['results']['OUTPUTS'] = []
        self.params['results']['REPORT'] = []

        self.totalSteps = 3

    @staticmethod
    def getModuleSupportedSiacEntityTypes(targetIndicator : SiacIndicator) -> Iterable[SiacEntity]:
        if targetIndicator == SiacIndicator.LOCAL_OLS_IMPACT:
            return [SiacEntity.FOREST, SiacEntity.WATER_BODIES, SiacEntity.URBAN_GREEN_SPACE]
        if targetIndicator == SiacIndicator.TREE_COVER or targetIndicator == SiacIndicator.FOREST_COVER:
            return [SiacEntity.FOREST]
        if targetIndicator == SiacIndicator.AIR_QUALITY_REMOVED_NO2 or targetIndicator == SiacIndicator.AIR_QUALITY_REMOVED_SO2 or targetIndicator == SiacIndicator.AIR_QUALITY_REMOVED_PM10 or targetIndicator == SiacIndicator.AIR_QUALITY_REMOVED_O3 or targetIndicator == SiacIndicator.AIR_QUALITY_REMOVED_CO:
            return [SiacEntity.FOREST]
        if targetIndicator == SiacIndicator.AVERAGE_CARBON_STORAGE or targetIndicator == SiacIndicator.AVERAGE_CARBON_SEQUESTRATION:
            return [SiacEntity.FOREST]      
        return None

    def finished(self, result):
        if result:
            self.jobFinished.emit(True, self.params ) 
        else:
            self.jobFinished.emit(False, self.params )


    def cancel(self):
        self.stopWorker = True
        super().cancel()


    def run(self):                
        
        self.totalSteps = 1 + len(self.params['REQUESTS'])
        self.isStep = 1

        self.siacToolMaximumProgressValue.emit(self.totalSteps)
        self.siacToolProgressValue.emit(0)  

        self.params['results']['LAYERS'] = {}
        self.params['results']['ENTITIES'] = {}


        # retrieve input layers for all requests
        self.siacToolProgressMessage.emit("Preparing data", Qgis.Info)        

        for coinRequest in self.params['REQUESTS']:
            
            # prepare layers
            if len(coinRequest['INPUTS']['LAYERS']) > 0:            
                
                for l in coinRequest['INPUTS']['LAYERS']:
                    # retrieve layer
                    sourceItem : SiacDataStoreLayerSource = l                
                    newItem = sourceItem.clone()                
                    self.params['results']['LAYERS'][sourceItem.ItemId] = newItem
                
            # check if all required data is available, depending on the request
            dataIsAvailable = self.assessDataAvailability(coinRequest)
            if not dataIsAvailable:
                self.params['exception'] = "Required fields missing in active layer"
                return False


        self.siacToolProgressValue.emit(1)  


        self.siacToolProgressMessage.emit("Computing indicators", Qgis.Info)
        for coinRequest in self.params['REQUESTS']:
            retval = self.assess(coinRequest)

            self.isStep += 1
            self.siacToolProgressValue.emit(self.isStep)  

        self.siacToolProgressValue.emit(self.totalSteps)  
        
        return True


    def assessDataAvailability(self, params):

        indicatorType : SiacIndicator = params['INDICATOR']

        # sanity checks for required fields/data in layer (at minimum required data)
        # input/base layer is used  
        if indicatorType == SiacIndicator.TREE_COVER:
            inputLayer = self.params['results']['LAYERS'][ params['INPUTS']['LAYERS'][0].ItemId ].LayerSource 
            if not LayerHelper.containsFieldWithName(inputLayer, SiacField.MORPHOLOGY_TREE_COVER_TOTAL.value):
                return False  

        if indicatorType == SiacIndicator.FOREST_COVER:
            forestIdentificationEngineType = params['INPUTS']['PARAMS'][0]
            if forestIdentificationEngineType == CoinForestCoverIdentificationEngine.SITE_SPECIFIC_TRAITS:
                # here, we have one input layer, that is the SITA-assessed layer that contains relevant fields
                inputLayer = self.params['results']['LAYERS'][ params['INPUTS']['LAYERS'][0].ItemId ].LayerSource 
                if not LayerHelper.containsFieldWithName(inputLayer, SiacField.MORPHOLOGY_TREE_COVER_TOTAL.value):
                    return False
                
            elif forestIdentificationEngineType == CoinForestCoverIdentificationEngine.SELF_REFERENTIAL:
                # here, have the tree cover layer (and potentially also the ombr layer)
                pass

        if indicatorType == SiacIndicator.STREET_TREE_DENSITY:
            classifiedTreesLayer = self.params['results']['LAYERS'][ params['INPUTS']['LAYERS'][0].ItemId ].LayerSource 
            if not LayerHelper.containsFieldWithName(classifiedTreesLayer, SiacField.TOPOLOGY_CONTAINMENT_IN_STREET.value) or not LayerHelper.containsFieldWithName(classifiedTreesLayer, SiacField.TOPOLOGY_ADJACENCY_TO_STREET.value):
                return False
        
        if indicatorType == SiacIndicator.TREE_DENSITY:
            pass   
        
        if indicatorType == SiacIndicator.AVERAGE_CARBON_STORAGE or indicatorType == SiacIndicator.AVERAGE_CARBON_SEQUESTRATION:
            inputLayer = self.params['results']['LAYERS'][ params['INPUTS']['LAYERS'][0].ItemId ].LayerSource 
            if not LayerHelper.containsFieldWithName(inputLayer, SiacField.MORPHOLOGY_TREE_COVER_TOTAL.value):
                return False 
            if params['INPUTS']['PARAMS'][2] and not LayerHelper.containsFieldWithName(inputLayer, SiacField.ESS_MEDIATION.value):   
                return False

        if indicatorType == SiacIndicator.AIR_QUALITY_REMOVED_NO2 or indicatorType == SiacIndicator.AIR_QUALITY_REMOVED_SO2 or indicatorType == SiacIndicator.AIR_QUALITY_REMOVED_PM10 or indicatorType == SiacIndicator.AIR_QUALITY_REMOVED_O3 or indicatorType == SiacIndicator.AIR_QUALITY_REMOVED_CO:
            inputLayer = self.params['results']['LAYERS'][ params['INPUTS']['LAYERS'][0].ItemId ].LayerSource             
            if not LayerHelper.containsFieldWithName(inputLayer, SiacField.MORPHOLOGY_TREE_COVER_TOTAL.value):
                return False    
            
            
        if indicatorType == SiacIndicator.LOCAL_OLS_IMPACT:                
            inputLayer = self.params['results']['LAYERS'][ params['INPUTS']['LAYERS'][0].ItemId ].LayerSource 
            
            predictorCoverType : LocalRegressionConverType = params['INPUTS']['PARAMS'][1]     
            imperviousPredictorChoice = LstRegressionPredictorSet(params['INPUTS']['PARAMS'][3])

            fieldSuffix = 'RELATIVE' if predictorCoverType == LocalRegressionConverType.USE_SHARE else 'TOTAL'
            requiredFieldNames = [ SiacField['MORPHOLOGY_TREE_COVER_{}'.format(fieldSuffix)].value ]        
            
            if imperviousPredictorChoice == LstRegressionPredictorSet.INCLUDE_IMPV_AS_SINGLE:
                requiredFieldNames.append(SiacField['MORPHOLOGY_IMPERVIOUS_AREA_{}'.format(fieldSuffix)].value)
            elif imperviousPredictorChoice == LstRegressionPredictorSet.INCLUDE_IMPV_AS_MULTIPLE:
                requiredFieldNames.append(SiacField['MORPHOLOGY_BUILDING_{}'.format(fieldSuffix)].value)
                requiredFieldNames.append(SiacField['MORPHOLOGY_STREET_{}'.format(fieldSuffix)].value)
                            
            for fname in requiredFieldNames:
                if not LayerHelper.containsFieldWithName(inputLayer, fname):
                    return False        

        if indicatorType == SiacIndicator.TREE_SPECIES_RICHNESS:
            inputLayer = self.params['results']['LAYERS'][ params['INPUTS']['LAYERS'][0].ItemId ].LayerSource 
            if not LayerHelper.containsFieldWithName(inputLayer, SiacField.TREE_SPECIES_COUNTS.value):        
                return False 

        return True


    def assess(self, params):
        # determine indicator to be assessed
        
    
        indicatorType : SiacIndicator = params['INDICATOR']
        
        # check for further benefits in teh literature
        # stormwater retention given as average percentage of retention: Szota et al. (2019) found an average storm water retention by urban trees of on average 18.3%
        # in: https://link.springer.com/chapter/10.1007/124_2020_46#Sec6

        # direct mm rate intercepted by tree crowns, with a three-fold variation in interception from 0.6 to 1.8 mm depending on species;
        # The mean value across all species was 0.86 mm (0.11 mm SD). 
        # https://acsess.onlinelibrary.wiley.com/doi/abs/10.2134/jeq2015.02.0092

        # air temperature anomaly as a function of tree cover ratio within defined buffer areas 10/30/60/90m around reference Tair measurement point
        # https://www.pnas.org/doi/10.1073/pnas.1817561116#supplementary-materials


        if indicatorType == SiacIndicator.TREE_COVER:
            self.assessTreeCover(params)   

        if indicatorType == SiacIndicator.FOREST_COVER:
            self.assessForestCover(params)            

        if indicatorType == SiacIndicator.TREE_DENSITY:    
            pass

        if indicatorType == SiacIndicator.TREE_SPECIES_RICHNESS:
            self.summarizeTreeRichnessAndDiversity(params)

        if indicatorType == SiacIndicator.AVERAGE_CARBON_STORAGE or indicatorType == SiacIndicator.AVERAGE_CARBON_SEQUESTRATION:
            self.assessCarbonStorageAndSequestration(params)
        
        if indicatorType == SiacIndicator.AIR_QUALITY_REMOVED_NO2 or indicatorType == SiacIndicator.AIR_QUALITY_REMOVED_SO2 or indicatorType == SiacIndicator.AIR_QUALITY_REMOVED_PM10 or indicatorType == SiacIndicator.AIR_QUALITY_REMOVED_O3 or indicatorType == SiacIndicator.AIR_QUALITY_REMOVED_CO:
            self.assessAirQualityRegulation(params)
        
        if indicatorType == SiacIndicator.LOCAL_OLS_IMPACT:
            self.assessLocalOlsRegression(params)

        if indicatorType == SiacIndicator.STREET_TREE_DENSITY:
            self.assessStreetTreeDensity(params)

        return None
      

    def assessTreeDensity(self, params):
        pass

    def summarizeTreeRichnessAndDiversity(self, params):
        
        # get inputs and prepare outputs
        inputLayer = self.params['results']['LAYERS'][ params['INPUTS']['LAYERS'][0].ItemId ].LayerSource
        fruitTreeGenusList = params['INPUTS']['PARAMS'][0]

        assessor = TreeRichnessAndDiversityAssessment(None, None, fruitTreeGenusList)

        totalFeatureCount = inputLayer.featureCount()
        processedFeatureCount = 0
        for f in inputLayer.getFeatures():
            assessor.assessSpatialUnitOfAnalysisByAttributes(f)

            # report progress
            processedFeatureCount += 1
            self.setProgress( (processedFeatureCount/totalFeatureCount)*100 )  


        self.params['results'][SiacToolkitDataType.RICHNESS_AND_DIVERSITY_ASSESSMENT] = assessor
        self.params['results']['REPORT'] += assessor.summary()

    def assessTreeCover(self, params):
        
        # get parameters
        indicatorType : SiacIndicator = params['INDICATOR']
        inputLayer = self.params['results']['LAYERS'][ params['INPUTS']['LAYERS'][0].ItemId ].LayerSource
        relativeTreeCoverThreshold = params['INPUTS']['PARAMS'][0]

        # add required fields, as needed
        inputLayer, _ = LayerHelper.addAttributeToLayer(inputLayer, indicatorType.fieldName, QVariant.Double)
        
        # indicatorExpression will evaluate tree cover total * rate; inputs correspond to plots, not tree cover anymore
        indicatorExpression = '({0}/10000)'.format( SiacField.MORPHOLOGY_TREE_COVER_TOTAL.value ) 

        # in addition, if forest has been included as entity, reduce land use to tree cover and also apply rate accordingly
        containtsForestEntity = LayerHelper.containsFieldWithName(inputLayer, SiacEntity.FOREST.getTotalCoverFieldName())
        if containtsForestEntity:
            indicatorExpression = indicatorExpression + ' + (({0} * {1})/10000)'.format(SiacEntity.FOREST.getTotalCoverFieldName(), relativeTreeCoverThreshold)   

        self.applyCoinExpressionToInputLayer(params, indicatorType, indicatorExpression, inputLayer)   

        forestParticipation = "Forest land-use has {}been included in this assessment".format( 'not ' if containtsForestEntity == False else '' )
        self.params['results']['REPORT'].append(forestParticipation)
        
        # determine reporting
        if 'AGGREGATE' in params:
            descriptiveResults = self.getAggregateStatistics(indicatorType, inputLayer, params['AGGREGATE'])
            self.aggregateStatisticsToReport(indicatorType, descriptiveResults)

    def assessForestCover(self, params):

        # get active layer provided by user as base layer
        indicatorType : SiacIndicator = params['INDICATOR']
        forestIdentificationEngineType = params['INPUTS']['PARAMS'][0]
        relativeTreeCoverThreshold = params['INPUTS']['PARAMS'][1]
        linearityThreshold = params['INPUTS']['PARAMS'][2]
        nearThreshold = params['INPUTS']['PARAMS'][3]
        minimumPatchSize = params['INPUTS']['PARAMS'][4]

        self.siacToolProgressMessage.emit("Preparing input layers", Qgis.Info)  
        if forestIdentificationEngineType == CoinForestCoverIdentificationEngine.SELF_REFERENTIAL:

            # obtain layers
            treeCoverLayer = self.params['results']['LAYERS'][ params['INPUTS']['LAYERS'][0].ItemId ].LayerSource
            # cache layer
            treeCoverCache : CachedLayerItem = FeatureCache.layerToCache( treeCoverLayer, None, None )
            
            # here, make an ombr layer of geometries
            # prepare layers
            tmp = treeCoverLayer
            if nearThreshold > 0:
                tmp = processing.run("native:buffer", {'INPUT': treeCoverLayer, 'DISTANCE' : nearThreshold, 'SEGMENTS' : 10, 'OUTPUT' : 'TEMPORARY_OUTPUT' })['OUTPUT']                                 

            ombrLayer = LayerHelper.createTemporaryLayer(ProjectDataSourceOptions.Crs, DataLayer.TREE_COVER_MBR.value, SiacGeometryType.POLYGON.value)

            # make ombrs, also considering potential near relationships if needed
            ombrLayer.startEditing()
            totalFeatureCount = tmp.featureCount()
            processedFeatureCount = 0

            for f in tmp.getFeatures():
                currentOmbr = SiacOrientedMinimumBoundingRectangle(f.geometry(), linearityThreshold)
                # make feature and add to layer
                currentOmbrFeature = QgsFeature() # TODO: add fields
                currentOmbrFeature.setGeometry(currentOmbr.getOrientedMinimumBoundingRectangleGeometry())
                ombrLayer.addFeature(currentOmbrFeature)

                processedFeatureCount += 1
                self.setProgress( (processedFeatureCount/totalFeatureCount)*100 )  

            ombrLayer.commitChanges()
 
            # make proper data source item
            mbrDs = SiacDataStoreLayerSource()
            mbrDs.LayerName = DataLayer.TREE_COVER_MBR.value
            mbrDs.LayerType = DataLayer.TREE_COVER_MBR.value
            mbrDs.LayerSource = ombrLayer
            mbrDs.SetTouched()
            self.params['results'][DataLayer.TREE_COVER_MBR] = mbrDs

            # dissolve ombr layer
            dissolvedOmbrLayer = processing.run("native:dissolve", {'INPUT': ombrLayer, 'SEPARATE_DISJOINT' : True, 'OUTPUT': 'TEMPORARY_OUTPUT' })['OUTPUT']
            dissolvedOmbrLayer, idxTcTotalField = LayerHelper.addAttributeToLayer(dissolvedOmbrLayer, SiacField.MORPHOLOGY_TREE_COVER_TOTAL.value, QVariant.Double)
            dissolvedOmbrLayer, idxTcRelativeField = LayerHelper.addAttributeToLayer(dissolvedOmbrLayer, SiacField.MORPHOLOGY_TREE_COVER_RELATIVE.value, QVariant.Double)
            
            # iterate ombr features and determine tree cover
            dissolvedOmbrLayer.startEditing()
            updateMap = {}
            for f in dissolvedOmbrLayer.getFeatures():
                # get intersecting tree cover, determine absolute and relative cover
                intersectingTreeCoverFeatures = treeCoverCache.getFeaturesFromCacheInGeometry( f.geometry(), TopologyRule.INTERSECTS )
                totalCover, relativeCover,_ = SiteAssessment.determineAbsoluteAndRelativeCoverFromIntersectingFeatures(f.geometry(), intersectingTreeCoverFeatures)
                updateMap[f.id()] = { idxTcTotalField : totalCover, idxTcRelativeField : relativeCover }
            dissolvedOmbrLayer.dataProvider().changeAttributeValues(updateMap)
            dissolvedOmbrLayer.commitChanges()

            # potentially, also make use of other ancillary layers later one

            # input layer is prepared. assign and then continue below
            dissolvedOmbrDs : SiacDataStoreLayerSource = SiacDataStoreLayerSource.makeNewDataStoreLayerSourceItem(dissolvedOmbrLayer, DataLayer.TREE_COVER_DISSOLVED_MBR.value, DataLayer.TREE_COVER_DISSOLVED_MBR.value, None)
            dissolvedOmbrDs.SetTouched()
            self.params['results']['LAYERS'][ dissolvedOmbrDs.ItemId ] = dissolvedOmbrDs
            inputLayer = dissolvedOmbrDs.LayerSource

        elif forestIdentificationEngineType == CoinForestCoverIdentificationEngine.SITE_SPECIFIC_TRAITS:
            # get SITA-prepared input layer
            inputLayer = self.params['results']['LAYERS'][ params['INPUTS']['LAYERS'][0].ItemId ].LayerSource

        # from here on, iteration over polygons would be the same?
        self.siacToolProgressMessage.emit("Adding fields to output layer", Qgis.Info)  
        # we need these fields for classification
        inputLayer, idxClassTreedAreaField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.CLASS_TREED_AREA.value, QVariant.Int )        
        inputLayer, idxClassForestField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.CLASS_FOREST.value, QVariant.Int )        
        
        # we need this field for summation later on
        inputLayer, idxForestArea = LayerHelper.addAttributeToLayer(inputLayer, indicatorType.fieldName, QVariant.Double)

        # determine present fields for ancillary data
        containsForestEntityData = LayerHelper.containsFieldWithName(inputLayer, SiacEntity.FOREST.getTotalCoverFieldName())   

        self.siacToolProgressMessage.emit("Iterating fields", Qgis.Info)  

        totalFeatureCount = inputLayer.featureCount()
        processedFeatureCount = 0

        inputLayer.startEditing()
        updateMap = {}

        forestArea = 0
        forestStands = 0


        for f in inputLayer.getFeatures():

            # intersect feature with trees
            polygonId = f.id()
            polygonGeometry = f.geometry()
            polygonArea = polygonGeometry.area()

            updateMap[polygonId] = {}

            # identify total relative tree cover
            absoluteTreeCover = f[SiacField.MORPHOLOGY_TREE_COVER_TOTAL.value] # area in m²

            # determine relative tree cover share from forest land use by re-converting land use area to hypothetical tree cover
            if containsForestEntityData:
                forestLandUseArea = f[SiacEntity.FOREST.getTotalCoverFieldName()] 
                effectiveForestTreeCoverArea = forestLandUseArea * relativeTreeCoverThreshold
                absoluteTreeCover += effectiveForestTreeCoverArea

            # treed area : canopy cover > 50%, theoretically with 2d grouping but that may be tentatively excluded
            # forest: treed area & size >= 5000 sqm
            relativeTreeCover = (absoluteTreeCover/polygonArea) 
            isTreedArea = 1 if relativeTreeCover >= relativeTreeCoverThreshold else 0
            isForest = 1 if isTreedArea == 1 and polygonArea >= minimumPatchSize else 0             
            
            updateMap[polygonId][idxClassTreedAreaField] = isTreedArea
            updateMap[polygonId][idxClassForestField] = isForest
            updateMap[polygonId][idxForestArea] = (polygonArea/10000) if isForest == 1 else 0
            
            forestArea += polygonArea if isForest == 1 else 0
            forestStands += isForest

            # report progress
            processedFeatureCount += 1
            self.setProgress( (processedFeatureCount/totalFeatureCount)*100 )  
                

        # done iterating over all features in analysis layer
        # update features
        # write results
        inputLayer.dataProvider().changeAttributeValues(updateMap)
        inputLayer.commitChanges()        
        forestIdEngine = "Forest cover has been estimated {}".format('top-down' if forestIdentificationEngineType == CoinForestCoverIdentificationEngine.SITE_SPECIFIC_TRAITS else 'bottom-up')
        forestParticipation = "Forest land-use has {}been included in this assessment.".format( 'not ' if containsForestEntityData == False else '' )
        self.params['results']['REPORT'].append('{}. Forest entities are defined by relative tree cover greater than or equal to {}% and a minimum area of {} ha. {} In total, an area of {:0.4f} {} in {} individual forest stands has been classified as forest'.format( forestIdEngine, relativeTreeCoverThreshold * 100, minimumPatchSize/10000, forestParticipation, ( forestArea * indicatorType.conversionFactor ), indicatorType.convertedUnit, forestStands ))

        # determine reporting
        if 'AGGREGATE' in params:
            descriptiveResults = self.getAggregateStatistics(indicatorType, inputLayer, params['AGGREGATE'])
            self.aggregateStatisticsToReport(indicatorType, descriptiveResults)
               
    def assessCarbonStorageAndSequestration(self, params):

        # get parameters
        indicatorType : SiacIndicator = params['INDICATOR']
        inputLayer = self.params['results']['LAYERS'][ params['INPUTS']['LAYERS'][0].ItemId ].LayerSource
        relativeTreeCoverThreshold = params['INPUTS']['PARAMS'][1]
        # should we consider scaling of ESS delivery?
        scaleEssDelivery = params['INPUTS']['PARAMS'][2]

        # add required fields, as needed
        inputLayer, _ = LayerHelper.addAttributeToLayer(inputLayer, indicatorType.fieldName, QVariant.Double)

        # indicatorExpression will evaluate tree cover total * rate; inputs correspond to plots, not tree cover anymore
        scalingFactor = SiacField.ESS_MEDIATION.value if scaleEssDelivery == True else 1
        indicatorExpression = '({0} * ({1} * {2}))'.format(scalingFactor, SiacField.MORPHOLOGY_TREE_COVER_TOTAL.value, params['INPUTS']['PARAMS'][0] ) 

        # in addition, if forest has been included as entity, reduce land use to tree cover and also apply rate accordingly
        containtsForestEntity = LayerHelper.containsFieldWithName(inputLayer, SiacEntity.FOREST.getTotalCoverFieldName())
        if containtsForestEntity:
            indicatorExpression = indicatorExpression + ' + (({0} * {1}) * {2})'.format(SiacEntity.FOREST.getTotalCoverFieldName(), relativeTreeCoverThreshold, params['INPUTS']['PARAMS'][0])   

        self.applyCoinExpressionToInputLayer(params, indicatorType, indicatorExpression, inputLayer)   

        # report assessment conditions
        essScalingConsidered = "The mediation of ecosystem service delivery has been {}".format('enabled' if scaleEssDelivery else 'disabled')
        self.params['results']['REPORT'].append(essScalingConsidered)
        forestParticipation = "Forest land-use has {}been included in this assessment".format( 'not ' if containtsForestEntity == False else '' )
        self.params['results']['REPORT'].append(forestParticipation)

        # determine reporting
        if 'AGGREGATE' in params:
            descriptiveResults = self.getAggregateStatistics(indicatorType, inputLayer, params['AGGREGATE'])
            self.aggregateStatisticsToReport(indicatorType, descriptiveResults)

    def assessAirQualityRegulation(self, params):

        # TODO: ADD SUPPORT FOR ESS K SERVICE PROVISIONING MEDIATION
        # TODO: HOW TO CONSIDER K FOR ANCILLARY CLASSES?

        # get parameters
        indicatorType : SiacIndicator = params['INDICATOR']
        inputLayer = self.params['results']['LAYERS'][ params['INPUTS']['LAYERS'][0].ItemId ].LayerSource
        relativeTreeCoverThreshold = params['INPUTS']['PARAMS'][1]

        # add required fields, as needed
        inputLayer, _ = LayerHelper.addAttributeToLayer(inputLayer, indicatorType.fieldName, QVariant.Double)

        indicatorExpression = '({0} * {1})'.format( SiacField.MORPHOLOGY_TREE_COVER_TOTAL.value, params['INPUTS']['PARAMS'][0] ) 

         # in addition, if forest has been included as entity, reduce land use to tree cover and also apply rate accordingly
        containtsForestEntity = LayerHelper.containsFieldWithName(inputLayer, SiacEntity.FOREST.getTotalCoverFieldName())
        if containtsForestEntity:
            indicatorExpression = indicatorExpression + ' + (({0} * {1}) * {2})'.format(SiacEntity.FOREST.getTotalCoverFieldName(), relativeTreeCoverThreshold, params['INPUTS']['PARAMS'][0])   

        self.applyCoinExpressionToInputLayer(params, indicatorType, indicatorExpression, inputLayer )    

        forestParticipation = "Forest land-use has {}been included in this assessment".format( 'not ' if containtsForestEntity == False else '' )
        self.params['results']['REPORT'].append(forestParticipation)
        
        # determine reporting
        if 'AGGREGATE' in params:
            descriptiveResults = self.getAggregateStatistics(indicatorType, inputLayer, params['AGGREGATE'])
            self.aggregateStatisticsToReport(indicatorType, descriptiveResults)





    def assessStreetTreeDensity(self, params):
        classifiedTreesLayer = self.params['results']['LAYERS'][params['INPUTS']['LAYERS'][0].ItemId].LayerSource
        streetCenterlinesLayer = self.params['results']['LAYERS'][params['INPUTS']['LAYERS'][1].ItemId].LayerSource

        # determine sum of street centerlines length
        totalStreetLength = sum([seg.geometry().length() for seg in streetCenterlinesLayer.getFeatures()])
              
        # determine number of street trees from classified tree cadastre
        qgsExpression = "\"{}\" = 1".format(SiacField.TOPOLOGY_CONTAINMENT_IN_STREET.value)      
        treeFeatures = classifiedTreesLayer.getFeatures(QgsFeatureRequest(QgsExpression(qgsExpression)))
        treeFeatureCount = len(list(treeFeatures))
        
        qgsExpression = "\"{}\" IS NULL AND \"{}\" = 1".format(SiacField.TOPOLOGY_CONTAINMENT_IN_STREET.value, SiacField.TOPOLOGY_ADJACENCY_TO_STREET.value)      
        adjacentTreeFeatures = classifiedTreesLayer.getFeatures(QgsFeatureRequest(QgsExpression(qgsExpression)))
        adjacentTreeFeatureCount = len(list(adjacentTreeFeatures))
        
        # report corresponding density trees/km : convert m to km in length unit
        streetTreeDensity = treeFeatureCount/(totalStreetLength/1000)
        streetTreeDensityInclNearTrees = (treeFeatureCount + adjacentTreeFeatureCount)/(totalStreetLength/1000)
        self.params['results']['REPORT'].append('Overall street tree density considering potential street trees only is estimated at {:0.2f} trees/km'.format(streetTreeDensity))
        self.params['results']['REPORT'].append('Overall street tree density considering potential street trees and near trees is estimated at {:0.2f} trees/km'.format(streetTreeDensityInclNearTrees))

    def assessLocalOlsRegression(self, params):

        # get parameters    
        
        layerType = params['INPUTS']['LAYERS'][0].LayerType
        inputLayer = self.params['results']['LAYERS'][params['INPUTS']['LAYERS'][0].ItemId].LayerSource    
        hasOlsDependentVariableValuesFieldInLayer : LocalRegressionParameters = params['INPUTS']['PARAMS'][0]
        
        predictorCoverType : LocalRegressionConverType = params['INPUTS']['PARAMS'][1]     
        includeLowessInPlots = params['INPUTS']['PARAMS'][2] 
        imperviousPredictorChoice = LstRegressionPredictorSet(params['INPUTS']['PARAMS'][3])
        includeAncillaryTypes = params['INPUTS']['PARAMS'][4]


        # from here onwards, we continue in teh same way for either new or re-used data
        # consider also regression type: determine field suffix based on chosen type
        fieldSuffix = 'RELATIVE' if predictorCoverType == LocalRegressionConverType.USE_SHARE else 'TOTAL'

        # determine whether an existing (pre-processed data) model should be re-used, so only regression re-computed                
        if not hasOlsDependentVariableValuesFieldInLayer :

            # this basically creates a regression params and extracts LST to features from input layer
            # can be skipped if previous model is re-used, as in this case, LST has already been extracted
            

            # at this point, we need to pre-process data, extract LST, write to file etc.
            # first, lets retrieve LST from model
            self.siacToolProgressMessage.emit("Pre-processing dependent variable value layer", Qgis.Info)  
            
            dependentVariableValueLayer =  params['INPUTS']['PARAMS'][5]
            cacheOfTargetValuePoints = FeatureCache.layerToCache(dependentVariableValueLayer, None, None, None) 

            self.siacToolProgressMessage.emit("Touching Input Layer", Qgis.Info)                   

            # add relevant fields to input layer
            inputLayer, idxLstMeanField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.OLS_DEPENDENT_MEAN.value, QVariant.Double )
            inputLayer, idxLstMinField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.OLS_DEPENDENT_MIN.value, QVariant.Double )
            inputLayer, idxLstMaxField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.OLS_DEPENDENT_MAX.value, QVariant.Double )
            inputLayer, idxLstStdField = LayerHelper.addAttributeToLayer(inputLayer, SiacField.OLS_DEPENDENT_STD.value, QVariant.Double )

            # prepare feature update map
            updateMap = {}

            # progress reporting
            processedFeatures = 0
            totalFeatures = inputLayer.featureCount()

            # assess number of trees per analysis unit
            inputLayer.startEditing()

            self.siacToolProgressMessage.emit("Iterating Features and Extract Values", Qgis.Info)  
            for polygonFeature in inputLayer.getFeatures():
                
                # intersect feature with trees
                polygonId = polygonFeature.id()
                polygonGeometry = polygonFeature.geometry()
                updateMap[polygonId] = {}

                # lst assessment: average points
                lstPoints = cacheOfTargetValuePoints.getFeaturesFromCacheInGeometry(polygonGeometry, TopologyRule.INTERSECTS)
                tempVals = [ pnt['VALUE'] for pnt in lstPoints ]

                updateMap[polygonId][idxLstMeanField] = NULL if len(tempVals) == 0 else sts.mean(tempVals)
                updateMap[polygonId][idxLstMinField] = NULL if len(tempVals) == 0 else min(tempVals)
                updateMap[polygonId][idxLstMaxField] = NULL if len(tempVals) == 0 else max(tempVals)
                updateMap[polygonId][idxLstStdField] = NULL if len(tempVals) == 0 else 0 if len(tempVals) < 2 else sts.stdev(tempVals)

                # report progress
                processedFeatures += 1
                self.setProgress( (processedFeatures/totalFeatures)*100 )  
                    
            # update features
            inputLayer.dataProvider().changeAttributeValues(updateMap)
            inputLayer.commitChanges()
        
        # prepare dataframe
        self.siacToolProgressMessage.emit("Preparing data for regression", Qgis.Info)  

        # prepare regression parameters
        currentRegressionParameters = LocalRegressionParameters()
                
        # treat required/mandatory fields we know should be there:
        # collect fields of all required layers
        currentRegressionParameters.DependentVariable = SiacField.OLS_DEPENDENT_MEAN.value   
        currentRegressionParameters.IndependentVariables.append(SiacField['MORPHOLOGY_TREE_COVER_{}'.format(fieldSuffix)].value) 
        currentRegressionParameters.PlotDefinitions.append( [ (SiacField['MORPHOLOGY_TREE_COVER_{}'.format(fieldSuffix)].value, SiacField.OLS_DEPENDENT_MEAN.value) ] )
        

        if imperviousPredictorChoice == LstRegressionPredictorSet.INCLUDE_IMPV_AS_SINGLE:
            currentRegressionParameters.IndependentVariables.append(SiacField['MORPHOLOGY_IMPERVIOUS_AREA_{}'.format(fieldSuffix)].value)
            # define plots
            currentRegressionParameters.PlotDefinitions.append( [ (SiacField['MORPHOLOGY_IMPERVIOUS_AREA_{}'.format(fieldSuffix)].value, SiacField.OLS_DEPENDENT_MEAN.value) ] )
        elif imperviousPredictorChoice == LstRegressionPredictorSet.INCLUDE_IMPV_AS_MULTIPLE:
            currentRegressionParameters.IndependentVariables.append(SiacField['MORPHOLOGY_BUILDING_{}'.format(fieldSuffix)].value)
            currentRegressionParameters.IndependentVariables.append(SiacField['MORPHOLOGY_STREET_{}'.format(fieldSuffix)].value)
            # define plots accordingly
            currentRegressionParameters.PlotDefinitions.append( [ (SiacField['MORPHOLOGY_BUILDING_{}'.format(fieldSuffix)].value, SiacField.OLS_DEPENDENT_MEAN.value),  (SiacField['MORPHOLOGY_STREET_{}'.format(fieldSuffix)].value, SiacField.OLS_DEPENDENT_MEAN.value) ] )
        

        # lets see if we have valid fields in the layer for supported entitity types
        # add entity type if we have the corresponding polygon type field
        # however, add those only if requested by user to be included in regression model
        if includeAncillaryTypes:
            for entityType in IndicatorComputation.getModuleSupportedSiacEntityTypes(SiacIndicator.LOCAL_OLS_IMPACT):
                
                # first determine what type of field we are looking for: absolute or relative cover
                relevantFieldName = entityType.getRelativeCoverFieldName() if predictorCoverType == LocalRegressionConverType.USE_SHARE else entityType.getTotalCoverFieldName()                        
                if LayerHelper.containsFieldWithName(inputLayer, relevantFieldName):
                    currentRegressionParameters.ParticipatingEntityTypes.append(entityType)
                    currentRegressionParameters.IndependentVariables.append(relevantFieldName)
                    currentRegressionParameters.PlotDefinitions.append([(relevantFieldName, SiacField.OLS_DEPENDENT_MEAN.value)])

        currentRegressionParameters.IncludeLowess = includeLowessInPlots

        # finally, prepare training dataset
        # select features using query that have no null values: "AVGLST" != 'NULL'
        lstFeatures = inputLayer.getFeatures( QgsFeatureRequest(QgsExpression("\"{}\" != '{}'".format( SiacField.OLS_DEPENDENT_MEAN.value , NULL))) )
        # drop unneccessary columns from this data frame:
        dropFields = []
        for field in [f for f in inputLayer.fields() if not f.name() in currentRegressionParameters.getRequiredFieldNames()]:
            dropFields.append(field.name())

        currentRegressionParameters.DataFrame = LayerHelper.convertQgsLayerToDataFrame(lstFeatures, inputLayer.fields(), dropColumns=dropFields)                               
        model = SiacRegressionModule.computeOlsRegression(currentRegressionParameters.DataFrame, currentRegressionParameters.IndependentVariables, currentRegressionParameters.DependentVariable)        

        # now that we have the model, also see if we can basically add input field that states estimated cooling potential        
        # write results to layer
        self.siacToolProgressMessage.emit("Applying regression model", Qgis.Info) 
        # write field
        inputLayer, _ = LayerHelper.addAttributeToLayer(inputLayer, SiacIndicator.LOCAL_OLS_IMPACT.fieldName, QVariant.Double)
        
        indicatorExpression = "" 
        for x in currentRegressionParameters.IndependentVariables:
            if indicatorExpression != "":
                indicatorExpression += " + "            
            indicatorExpression += '({0} * {1})'.format( x, model.params[x] )   
        
        self.applyCoinExpressionToInputLayer(params, SiacIndicator.LOCAL_OLS_IMPACT, indicatorExpression, inputLayer )    

      
        self.params['results']['REPORT'].append( '{}'.format(model.summary()) )
        self.params['results'][SiacToolkitDataType.LOCAL_COOLING_POTENTIAL_DATA] = currentRegressionParameters    

   


    def applyCoinExpressionToInputLayer(self, params, indicatorType, indicatorExpression, inputLayer):
        
        # with the expression prepared, lets continue to compute the field, then have the field statistics calculated as requested
        expression = QgsExpression(indicatorExpression)        

        # compute result using specified input fields
        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(inputLayer))
                
        inputLayer.startEditing()
        for f in inputLayer.getFeatures():
            context.setFeature(f)
            f[indicatorType.fieldName] = expression.evaluate(context)
            inputLayer.updateFeature(f)
        inputLayer.commitChanges()
            
            


    def reportAggregateStatisticsForMultipleLayers(self, indicatorType : SiacIndicator, toolLayers : Iterable[QgsVectorLayer]) -> Iterable[float]:
        pass

    def getAggregateStatistics(self, indicatorType : SiacIndicator, inputLayer, params : Iterable[DescriptiveParameter]) -> Dict[DescriptiveParameter, any]:
        
        results = {}

        # iterate over requested agggregate statistics
        for descriptiveParameter in params:                
            
            paramValue = None
            # aggregate returns a Tuple[any, bool]
            if descriptiveParameter == DescriptiveParameter.AVERAGE:
                paramValue = inputLayer.aggregate(QgsAggregateCalculator.Mean, indicatorType.fieldName)            
            if descriptiveParameter == DescriptiveParameter.SUM:
                paramValue = inputLayer.aggregate(QgsAggregateCalculator.Sum, indicatorType.fieldName)
            results[descriptiveParameter] = paramValue[0]
                
        return results
    
    
    def aggregateStatisticsToReport(self, indicatorType : SiacIndicator, aggrStats : Dict[DescriptiveParameter, any]) -> None:
        for descriptiveParameter, paramValue in aggrStats.items():
            # append to report
            if descriptiveParameter == DescriptiveParameter.AVERAGE:
                self.params['results']['REPORT'].append( 'The average {} is estimated at {:0.4f} {}'.format( indicatorType.label, paramValue, indicatorType.baseUnit ) )            
            if descriptiveParameter == DescriptiveParameter.SUM:
                self.params['results']['REPORT'].append( 'The total {} is estimated at {:0.4f} {}'.format( indicatorType.label, (paramValue * indicatorType.conversionFactor ), indicatorType.convertedUnit ) )
                
