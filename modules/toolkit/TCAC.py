from qgis.core import *
from qgis.gui import QgsMessageBar, QgsMapLayerComboBox, QgsFieldComboBox
from qgis.PyQt.QtCore import Qt, QThread, QSettings, QTranslator, QCoreApplication, QVariant, pyqtSignal, QAbstractTableModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QErrorMessage, QAction, QMessageBox, QProgressBar
import processing
import traceback
from collections import Counter
import statistics as st
import math

from ..SiacEnumerations import *
from ..SiacFoundation import LayerHelper, SelectionHelper, Utilities, FeatureCache, CachedLayerItem
from ..TreeRichnessAndDiversityAssessment import *
from ..toolkitData.SiacDataStoreLayerSource import SiacDataStoreLayerSource
from ..toolkitData.SiacOrientedMbr import SiacOrientedMinimumBoundingRectangle

class TcacAssessmentResult:

    _NearestNeighbourAssessmentResult = None
    _ContainedTreeFeatures = None
    _TreeIds = None
    _OrientedMinimumBoundingRectangleClass = None
    _LinearityThreshold = None
    _RichnessAndDiversityAssessmentResult = None
    _FeatureSiacId = None
    _FeatureId = None
    _FeatureGeometry = None
    _NearestNetworkLayer = None

    def __init__(self, feature, linearityThreshold) -> None:
        self._FeatureId = feature.id()
        self._FeatureGeometry = feature.geometry()
        self._LinearityThreshold = linearityThreshold
        self._OrientedMinimumBoundingRectangleClass = SiacOrientedMinimumBoundingRectangle(self.FeatureGeometry, self._LinearityThreshold)
        self._FeatureSiacId = feature[SiacField.UID_CANOPY.value]

    @property
    def NearestNetworkLayer(self):
        return self._NearestNetworkLayer

    @NearestNetworkLayer.setter
    def NearestNetworkLayer(self, value):
        self._NearestNetworkLayer = value

    @property
    def FeatureGeometry(self):
        return self._FeatureGeometry
    
    @property
    def SiacId(self):
        return self._FeatureSiacId
    
    @property 
    def FeatureId(self):
        return self._FeatureId

    @property
    def LocalTreeAbundance(self):
        return len(self.ContainedTreeFeatures)
    
    @property
    def ContainedTreeFeatures(self):
        return self._ContainedTreeFeatures
    
    @ContainedTreeFeatures.setter
    def ContainedTreeFeatures(self, value):
        self._ContainedTreeFeatures = value

    @property
    def NearestNeighbourAssessmentResult(self):
        return self._NearestNeighbourAssessmentResult
    
    @NearestNeighbourAssessmentResult.setter
    def NearestNeighbourAssessmentResult(self, value):
        self._NearestNeighbourAssessmentResult = value    

    @property
    def TreeIds(self):
        return self._TreeIds
    
    @TreeIds.setter
    def TreeIds(self, value):
        self._TreeIds = value

    @property
    def OrientedMinimumBoundingRectangle(self) -> SiacOrientedMinimumBoundingRectangle:
        return self._OrientedMinimumBoundingRectangleClass

    @property
    def RichnessAndDiversityAssessmentResult(self):
        return self._RichnessAndDiversityAssessmentResult

    @RichnessAndDiversityAssessmentResult.setter
    def RichnessAndDiversityAssessmentResult(self, value):
        self._RichnessAndDiversityAssessmentResult = value  
    
    @property
    def TreeConfigurationClass(self):

        # default value
        classificationResult = TreePatternConfiguration.UNDEFINED

        if ( self.NearestNeighbourAssessmentResult['POINT_COUNT'] == 1):
            classificationResult = TreePatternConfiguration.SOLITARY
        else:

            # assuming there are more than 1 tree in the current canopy; if the width of the 
            # oriented mbr is within a certain tolerance with respect to modelled canopy width/radius, 
            # this would speak to a linear orientation.
            # such linear configurations may be clustered or dispersed as well

            # dimensions of particle as a > b > c, however, with only two dimensions, we have a > b, and elongation is equal to b/a           
            if self.OrientedMinimumBoundingRectangle.IsLinear:
                # assuming linear grouping tendency
                classificationResult = TreePatternConfiguration.CLUSTERED_LINEAR_GROUPING if self.NearestNeighbourAssessmentResult['Z_SCORE'] < 0 else TreePatternConfiguration.DISPERSED_OR_REGULAR_LINEAR_GROUPING 
            else:
                # assuming non-linear grouping tendency
                classificationResult = TreePatternConfiguration.CLUSTERED_GROUPING if self.NearestNeighbourAssessmentResult['Z_SCORE'] < 0 else TreePatternConfiguration.DISPERSED_OR_REGULAR_GROUPING
        
        return classificationResult

class TreeConfigurationAssessmentAndClassification(QgsTask):
    """
    Assessment of the spatial configuration of trees and the classification of tree entities
    as solitary, linear or grouped. It supports the following tasks:

    Canopy cover modelling

    Extends: QgsTask.
    
    
    Parameters
    ----------
    workerParams : Key-value pairs containing the input data for the QgsTask worker.
        DataLayer.TREES : Tree cadastral data in the form of a feature layer of point geometry type
        TREE_CROWN_DIAMETER : Canopy cover radius used for modelling of canopy cover
        CRS : Coordinate Reference System used for return layers 
    
    Attributes
    ----------
    
    """

    MESSAGE_CATEGORY = "SIAC"
    
    siacToolMaximumProgressValue = pyqtSignal(int)
    siacToolProgressValue = pyqtSignal(int)
    siacToolProgressMessage = pyqtSignal(object, object)
    jobFinished = pyqtSignal(bool, object)
    

    # note: worker parameters contain the following parameters:
    # ... CANOPY_COVER_WIDTH : width/radius of cover to be used, either float (fixed distance) or string (field attribute)
    # ... CRS : target crs

    def __init__(self, workerParams):
        super().__init__("TCAC Task", QgsTask.CanCancel)
        self.stopWorker = False
        self.params = workerParams
        self.results = {}

        self.uidFieldName = SiacField.SIAC_ID.value

        self.params['exception'] = ""
        self.params['results'] = {}
        self.params['results']['REPORT'] = []

    def finished(self, result):
        if result:
            self.jobFinished.emit(True, self.params ) 
        else:
            self.jobFinished.emit(False, self.params )
        
    def run(self):
        
        currentTask : TcacTask = self.params['TASK']

        if currentTask == TcacTask.MODEL_TREE_COVER:
            return self.modelCanopyCoverLayer()
        elif currentTask == TcacTask.TREE_PATTERN_ASSESSMENT_AND_CLASSIFICATION:
            return self.assessTreeConfiguration()        
        elif currentTask == TcacTask.MODEL_TRAITS_FROM_TALLO or TcacTask.MODEL_TRAITS_FROM_UTDB:
            return self.determineTreeCrownDiameterFromDatabase()
        

    def determineTreeCrownDiameterFromDatabase(self):
        
        self.siacToolMaximumProgressValue.emit(4)
        self.siacToolProgressValue.emit(0)

        self.siacToolProgressMessage.emit("Preparing data", Qgis.MessageLevel.Info)

        # make result layer
        self.params['results'][DataLayer.TREES] = self.params[DataLayer.TREES].clone()
        targetLayer : QgsVectorLayer = self.params['results'][DataLayer.TREES].LayerSource
        targetLayer, idxTreeCrownDiameterField = LayerHelper.addAttributeToLayer(targetLayer, 'CROWN_DIA', QVariant.Double)

        self.siacToolProgressValue.emit(1)

        # get database and db type and other params
        current_db = self.params['DB']
        current_db_type = self.params['DB_TYPE']
        targetSpeciesFieldName = self.params['SPECIES_ATTRIBUTE']

        # prepare relevant field names, depending on type of database provided
        dbSpeciesField : str = None
        dbCrownDiameterField : str = None
        groupedData : pd.DataFrame = None
        # set species field and crown diameter field for current db type 
        if current_db_type == SiacToolkitDataType.TALLO_DB:
            dbSpeciesField = "species"
            dbCrownDiameterField = "crown_radius_m"
        elif current_db_type == SiacToolkitDataType.URBAN_TREE_DB:
            dbSpeciesField = "ScientificName"
            dbCrownDiameterField = "AvgCdia (m)"

        # lower-case species field
        current_db[dbSpeciesField] = current_db[dbSpeciesField].str.lower()        
        # group by species, average crown radius, and drop nan in the process
        groupedData = current_db.groupby([dbSpeciesField])[dbCrownDiameterField].mean().dropna().reset_index()

        self.siacToolProgressValue.emit(2)

        self.siacToolProgressMessage.emit("Iterating tree features", Qgis.MessageLevel.Info)
        
        # iterate over features
        updateMap = {}
        processedFeatures = 0
        totalFeatures = targetLayer.featureCount()
        
        targetLayer.startEditing()
        for f in targetLayer.getFeatures():

            # get species entry from feature, to lowercase for comparison 
            featureSpecies = f[targetSpeciesFieldName].lower()

            # get entry from db
            meanCrownDiameterValue = groupedData.loc[ groupedData[dbSpeciesField] == featureSpecies ][dbCrownDiameterField]

            if len(meanCrownDiameterValue.values) > 0:
                updateMap[f.id()] = { idxTreeCrownDiameterField : meanCrownDiameterValue.values.item(0) }
            else:
                QgsMessageLog.logMessage("No data found in database for {}".format(featureSpecies), self.MESSAGE_CATEGORY, level=Qgis.MessageLevel.Critical)

            # report progress
            processedFeatures += 1
            self.setProgress( (processedFeatures/totalFeatures)*100 ) 

        self.siacToolProgressValue.emit(3)

        self.siacToolProgressMessage.emit("Writing results to layer", Qgis.MessageLevel.Info)
        targetLayer.dataProvider().changeAttributeValues(updateMap)
        targetLayer.commitChanges()

        self.siacToolProgressValue.emit(4)
        return True


    def assessTreeConfiguration(self):
        
        self.siacToolMaximumProgressValue.emit(6)
        self.siacToolProgressValue.emit(0)

        # add certain fields to save results of assessment
        self.params['results']['TOTAL_TREE_ABUNDANCE'] = 0
        self.params['results']['TOTAL_CANOPY_ABUNDANCE'] = 0
       
        self.siacToolProgressMessage.emit("Preparing data", Qgis.MessageLevel.Info)

        
        # create result layers   
        self.params['results'][DataLayer.TREE_COVER] = self.params[DataLayer.TREE_COVER].clone()
        

        classidfiedTrDs = SiacDataStoreLayerSource()
        classidfiedTrDs.LayerName = DataLayer.CLASSIFIED_TREES.value
        classidfiedTrDs.LayerType = DataLayer.CLASSIFIED_TREES.value
        classidfiedTrDs.LayerSource = LayerHelper.copyLayer(self.params[DataLayer.TREES].LayerSource)
        classidfiedTrDs.SetTouched()

        self.params['results'][DataLayer.CLASSIFIED_TREES] = classidfiedTrDs        
        self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource = LayerHelper.createLayerUniqueId(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, SiacField.UID_TREE.value)   
        self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, _ = LayerHelper.addAttributeToLayer( self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, SiacField.TREE_CLASSIFICATION.value, QVariant.String )
        
        # force cache update at this point        
        # cache is needed later on and for initializing diversity assessment, if needed
        self.params["CACHE"].cacheLayer(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, DataLayer.CLASSIFIED_TREES)

        # determine if we have the information to assess tree species diversity
        if not self.params[SiacToolkitOptionValue.TCAC_PARAMS_SPECIES_FIELDNAME].strip():
            QgsMessageLog.logMessage("Disabled tree species richness assessment", self.MESSAGE_CATEGORY, Qgis.MessageLevel.Warning)
            self.params['ASSESS_TREE_SPECIES_RICHNESS'] = False
            self.params['results']['DIVERSITY'] = None
        else:
            QgsMessageLog.logMessage("Enabled tree species richness assessment", self.MESSAGE_CATEGORY, Qgis.MessageLevel.Success)
            self.params['ASSESS_TREE_SPECIES_RICHNESS'] = True
            self.params['results']['DIVERSITY'] = TreeRichnessAndDiversityAssessment(self.params['CACHE'].getFromCache(DataLayer.CLASSIFIED_TREES), self.params[SiacToolkitOptionValue.TCAC_PARAMS_SPECIES_FIELDNAME], self.params[SiacToolkitOptionValue.TCAC_PARAMS_FRUITTREE_SPECIES_LIST]) 
                
        self.siacToolProgressValue.emit(1)     

        # add fields to dissolved canopy cover layer to store NN analysis results
        fields_dissolvedCanopyCoverLayer = [    
            QgsField(SiacField.CONTAINED_TREE_IDS.value, QVariant.String),        
            QgsField("OMBR_ANGLE", QVariant.Double),          
            QgsField("OMBR_WIDTH", QVariant.Double),
            QgsField("OMBR_HEIGHT", QVariant.Double),
            QgsField("LINEARITY", QVariant.Double), 
            QgsField(SiacField.MORPHOLOGY_TREE_COUNT.value, QVariant.Double), 
            QgsField("OBSERVED_DIST", QVariant.Double),
            QgsField("EXPECTED_DIST", QVariant.Double),
            QgsField("NN_INDEX", QVariant.Double), 
            QgsField("NN_ZSCORE", QVariant.Double),             
            QgsField(SiacField.TREE_CLASSIFICATION.value, QVariant.String)
        ]         

        # take care of additional fields to contain tree species richness, if enables
        if self.params['ASSESS_TREE_SPECIES_RICHNESS']:
            fields_dissolvedCanopyCoverLayer.append(QgsField(SiacField.MORPHOLOGY_TREE_SPECIES_RICHNESS.value, QVariant.Int ))
            fields_dissolvedCanopyCoverLayer.append(QgsField(SiacField.TREE_SPECIES.value, QVariant.String ))
            fields_dissolvedCanopyCoverLayer.append(QgsField(SiacField.TREE_SPECIES_COUNTS.value, QVariant.String ))
            fields_dissolvedCanopyCoverLayer.append(QgsField(SiacField.MORPHOLOGY_CONTAINS_FRUIT_TREES.value, QVariant.Int ))
            fields_dissolvedCanopyCoverLayer.append(QgsField(SiacField.FRUIT_TREE_COUNT.value, QVariant.Int ))
            fields_dissolvedCanopyCoverLayer.append(QgsField(SiacField.FRUIT_TREE_SHARE.value, QVariant.Double ))

        self.params['results'][DataLayer.TREE_COVER].LayerSource = LayerHelper.createTemporaryLayerAttributes(self.params['results'][DataLayer.TREE_COVER].LayerSource, fields_dissolvedCanopyCoverLayer)
        self.siacToolProgressValue.emit(2)     
        
        # assess properties for each tree cover
        assessedCanopies = self.assessTreeCoverConfiguration()
        self.siacToolProgressValue.emit(3)

        # update layers as needed
        self.writeTcacResultsToLayers(assessedCanopies)
        self.siacToolProgressValue.emit(4)

        # assess tree features
        self.params["CACHE"].cacheLayer(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, DataLayer.CLASSIFIED_TREES)
        self.assessTreeFeaturesAsIndividuals()
        self.siacToolProgressValue.emit(5)

        # finishing
        self.reportTcacSummary()
        self.siacToolProgressValue.emit(6)
        return True


    def cancel(self):
        self.stopWorker = True
        super().cancel()

    
    def modelCanopyCoverLayer(self):
        
        self.siacToolProgressMessage.emit("Modelling Tree Cover", Qgis.MessageLevel.Info)
        self.siacToolMaximumProgressValue.emit(3)
        self.siacToolProgressValue.emit(0)

        # cache tree features
        cacheOfTrees : CachedLayerItem = FeatureCache.layerToCache(self.params[DataLayer.TREES].LayerSource, None, None)

        # determine if a fixed distance or field should be used as buffer distance
        distVal = None
        useDefinedTreeCrownDiameterValue = self.params[SiacToolkitOptionValue.TCAC_PARAMS_USER_DEFINED_TREE_CROWN_DIAMETER]
        if useDefinedTreeCrownDiameterValue:
            # use fixed distance: the tree crown diameter is divided by 2 to adjust to radius needed for buffering
            distVal = ( self.params[SiacToolkitOptionValue.TCAC_PARAMS_TREE_CROWN_DIAMETER_VALUE] / 2)
        else:
            # use field that holds values
            distVal = QgsProperty.fromExpression('"' + self.params[SiacToolkitOptionValue.TCAC_PARAMS_TREE_CROWN_DIAMETER_FIELDNAME] + '"')

        # create buffers using processing
        toolSource = self.params[DataLayer.TREES].LayerSource
        tmp = processing.run("native:buffer", {'INPUT': toolSource, 'DISTANCE' : distVal, 'SEGMENTS' : 10, 'OUTPUT' : 'TEMPORARY_OUTPUT' })
        
        newDs = SiacDataStoreLayerSource()
        newDs.LayerType = DataLayer.TREES_ENVELOPES.value
        newDs.LayerName = DataLayer.TREES_ENVELOPES.value
        newDs.LayerSource = tmp['OUTPUT']  
        newDs.SetTouched()
        self.params['results'][DataLayer.TREES_ENVELOPES] = newDs

        self.siacToolProgressValue.emit(1)
        self.siacToolProgressMessage.emit("Dissolving Tree Cover Features", Qgis.Info)

        # the buffered layer has the fields of the original layer; 
        # we do not want to carry them over, thus, delete
        fieldNameList = []
        for field in self.params['results'][DataLayer.TREES_ENVELOPES].LayerSource.fields():            
            fieldNameList.append(field.name())
        tmp = processing.run('qgis:deletecolumn',  {'INPUT': self.params['results'][DataLayer.TREES_ENVELOPES].LayerSource, 'COLUMN': fieldNameList, 'OUTPUT': 'memory:'})        
        self.params['results'][DataLayer.TREES_ENVELOPES].LayerSource = tmp['OUTPUT']           

        # dissolve individual buffers into single features
        tmp = processing.run("native:dissolve", {'INPUT': self.params['results'][DataLayer.TREES_ENVELOPES].LayerSource, 'SEPARATE_DISJOINT' : True, 'OUTPUT': 'TEMPORARY_OUTPUT' }) 
        
        tcDs = SiacDataStoreLayerSource()
        tcDs.LayerName = DataLayer.TREE_COVER.value
        tcDs.LayerType = DataLayer.TREE_COVER.value
        tcDs.LayerSource = tmp['OUTPUT']  
        tcDs.SetTouched()
        self.params['results'][DataLayer.TREE_COVER] = tcDs

        self.siacToolProgressValue.emit(2)

        self.siacToolProgressMessage.emit("Determining Basic Tree Cover Properties", Qgis.Info)

        # create unique id fie ld for dissolved tree canopy layer
        self.params['results'][DataLayer.TREE_COVER].LayerSource = LayerHelper.createLayerUniqueId(self.params['results'][DataLayer.TREE_COVER].LayerSource, SiacField.UID_CANOPY.value)                 
        self.params['results'][DataLayer.TREE_COVER].LayerSource, idxCanopyLayerRelevantFeatureAreaField = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.TREE_COVER].LayerSource, SiacField.RELEVANT_FEATURE_AREA.value, QVariant.Double)
        
        # add averaged tree health field, if needed
        if self.params[SiacToolkitOptionValue.TCAC_PARAMS_ASSESS_TREE_ESS_SCALING] == True:
            self.params['results'][DataLayer.TREE_COVER].LayerSource, idxScalingValueField = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.TREE_COVER].LayerSource, SiacField.ESS_MEDIATION.value, QVariant.Double)

        processedFeatureCount = 0
        totalFeatureCount = self.params['results'][DataLayer.TREE_COVER].LayerSource.featureCount()

        updateMap = {}
        for f in self.params['results'][DataLayer.TREE_COVER].LayerSource.getFeatures():
            
            currentCanopyFeatureGeometry = f.geometry()
            updateMap[f.id()] = { idxCanopyLayerRelevantFeatureAreaField : currentCanopyFeatureGeometry.area() }
            
            # determine intersecting trees, but write only average k value to canopy.
            # reason: assessment of tree configuration also relies on tree ids, but they refer to clasified tree cadastre, whereas here, only the raw input data would be available
            # the id sets would thus be different and likely confusing
            if self.params[SiacToolkitOptionValue.TCAC_PARAMS_ASSESS_TREE_ESS_SCALING] == True:
                containedTreeEntities = cacheOfTrees.getFeaturesFromCacheInGeometry(currentCanopyFeatureGeometry, TopologyRule.INTERSECTS)
                listOfScalingValues = [ k[self.params[SiacToolkitOptionValue.TCAC_PARAMS_TREE_HEALTH_FIELDNAME]] for k in list(containedTreeEntities)]

                # average values in list
                averageScalingFactorForCurrentCanopy = st.mean(listOfScalingValues)
                print(averageScalingFactorForCurrentCanopy)

                # write averages to update map
                updateMap[f.id()][idxScalingValueField] = averageScalingFactorForCurrentCanopy

            processedFeatureCount += 1        
            self.setProgress( processedFeatureCount/totalFeatureCount*100 )
        
        
        self.params['results'][DataLayer.TREE_COVER].LayerSource.startEditing()
        self.params['results'][DataLayer.TREE_COVER].LayerSource.dataProvider().changeAttributeValues(updateMap)
        self.params['results'][DataLayer.TREE_COVER].LayerSource.commitChanges()

        self.siacToolProgressValue.emit(3)

        # some reporting
        self.params['results']['REPORT'].append('A user-assumed fixed tree crown diameter is used for modelling of tree cover' if useDefinedTreeCrownDiameterValue else 'Field {} is used as tree-specific tree crown diameter'.format(self.params[SiacToolkitOptionValue.TCAC_PARAMS_TREE_CROWN_DIAMETER_FIELDNAME])) 
        if useDefinedTreeCrownDiameterValue:
            self.params['results']['REPORT'].append('A fixed value of {}m has been used as tree crown diameter'.format(self.params[SiacToolkitOptionValue.TCAC_PARAMS_TREE_CROWN_DIAMETER_VALUE]))

        self.params['results']['REPORT'].append("\n\nThe total tree abundance is estimated at {} tree features".format(self.params[DataLayer.TREES].LayerSource.featureCount()))
        self.params['results']['REPORT'].append("A total of {} canopy features were modelled".format(self.params['results'][DataLayer.TREE_COVER].LayerSource.featureCount()))

        return True

    

    #######################################
    # Function handling the actual assessing of tree canopies that is called from the iteration over canopies
    #######################################
    def assessTreeCanopyFeature(self, canopyCoverFeature):
        
        cacheOfTrees = self.params['CACHE'].getFromCache(DataLayer.CLASSIFIED_TREES)
        currentCrs = self.params['CRS']

        # result 
        CurrentAssessmentResult = TcacAssessmentResult(canopyCoverFeature, self.params[SiacToolkitOptionValue.TYPOLOGY_LINEARITY_THRESHOLD])

        # get trees that are within the current canopy-covered area
        CurrentAssessmentResult.ContainedTreeFeatures = SelectionHelper.getIntersectingFeatureIds( CurrentAssessmentResult.FeatureGeometry, cacheOfTrees, TopologyRule.CONTAINS )              

        # use cache instead of getFeatures from layer # containedClassifiedTreeFeatures = layerClassifiedTrees.getFeatures(CurrentAssessmentResult.ContainedTreeFeatures)
        containedClassifiedTreeFeatures = cacheOfTrees.getFeaturesFromCache(CurrentAssessmentResult.ContainedTreeFeatures)
        CurrentAssessmentResult.TreeIds = ','.join( str(f[SiacField.UID_TREE.value]) for f in containedClassifiedTreeFeatures) 

        if CurrentAssessmentResult.LocalTreeAbundance > 1:
            
            # write selected tree features to a temporary layer
            #selectedFeatures = containedClassifiedTreeFeatures 
            
            CurrentAssessmentResult.NearestNetworkLayer = LayerHelper.createTemporaryLayer(currentCrs, "tmpSelection", "point")
            CurrentAssessmentResult.NearestNetworkLayer.startEditing()
            CurrentAssessmentResult.NearestNetworkLayer.dataProvider().addFeatures(containedClassifiedTreeFeatures)
            CurrentAssessmentResult.NearestNetworkLayer.commitChanges()

            # assess NN statistics 
            CurrentAssessmentResult.NearestNeighbourAssessmentResult = processing.run("native:nearestneighbouranalysis", {'INPUT': CurrentAssessmentResult.NearestNetworkLayer })
            
        
        else:
            CurrentAssessmentResult.NearestNeighbourAssessmentResult = {
                'POINT_COUNT' : 1,
                'OBSERVED_MD' : 0,
                'EXPECTED_MD' : 0,
                'NN_INDEX' : 1,
                'Z_SCORE'  : 0        
            }   

        if self.params['results']['DIVERSITY'] is not None:
            CurrentAssessmentResult.RichnessAndDiversityAssessmentResult = self.params['results']['DIVERSITY'].assessSpatialUnitOfAnalysis(CurrentAssessmentResult.FeatureId, CurrentAssessmentResult.ContainedTreeFeatures)
                            
        return CurrentAssessmentResult

    

    def writeTcacResultsToLayers(self, tcacAssessmentResults):
        
        self.siacToolProgressMessage.emit("Writing results to layers", Qgis.Info)

        # # prepare layers
        # mbrDs = SiacDataStoreLayerSource()
        # mbrDs.LayerName = DataLayer.TREE_COVER_MBR.value
        # mbrDs.LayerType = DataLayer.TREE_COVER_MBR.value
        # mbrDs.LayerSource = LayerHelper.copyLayer(self.params['results'][DataLayer.TREE_COVER].LayerSource)
        # mbrDs.SetTouched()
        # self.params['results'][DataLayer.TREE_COVER_MBR] = mbrDs

        # get field indices for update map
        idxTreeLayerTreeClassField = self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource.fields().indexFromName(SiacField.TREE_CLASSIFICATION.value)
        
        idxCanopyLayerTreeIdField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName(SiacField.CONTAINED_TREE_IDS.value)
        idxCanopyLayerOmbrAngleField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName("OMBR_ANGLE")
        idxCanopyLayerOmbrWidthField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName("OMBR_WIDTH")
        idxCanopyLayerOmbrHeightField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName("OMBR_HEIGHT")
        idxCanopyLayerTreeCountField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName(SiacField.MORPHOLOGY_TREE_COUNT.value)
        idxCanopyLayerObservedDistanceField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName("OBSERVED_DIST")
        idxCanopyLayerExpectedDistanceField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName("EXPECTED_DIST")
        idxCanopyLayerNnIndexField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName("NN_INDEX")
        idxCanopyLayerNnZscoreField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName("NN_ZSCORE")
        idxCanopyLayerTreeClassField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName(SiacField.TREE_CLASSIFICATION.value)
        idxCanopyLayerLinearityField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName("LINEARITY")
        idxCanopyLayerSiacIdField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName(SiacField.UID_CANOPY.value)

        if self.params['ASSESS_TREE_SPECIES_RICHNESS']:
            idxCanopyLayerRichnessField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName(SiacIndicator.TREE_SPECIES_RICHNESS.fieldName)
            idxCanopyLayerSpeciesField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName(SiacField.TREE_SPECIES.value)
            idxCanopyLayerSpeciesCountsField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName(SiacField.TREE_SPECIES_COUNTS.value)
            idxCanopyLayerFruitTreeContainmentField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName(SiacField.MORPHOLOGY_CONTAINS_FRUIT_TREES.value)
            idxCanopyLayerFruitTreeCountField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName(SiacField.FRUIT_TREE_COUNT.value)
            idxCanopyLayerFruitTreeShareField = self.params['results'][DataLayer.TREE_COVER].LayerSource.fields().indexFromName(SiacField.FRUIT_TREE_SHARE.value)

        # start editing session
        self.params['results'][DataLayer.TREE_COVER].LayerSource.startEditing()
        #self.params['results'][DataLayer.TREE_COVER_MBR].LayerSource.startEditing()
        self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource.startEditing()

        canopyLayerUpdateMap = {}
        treeLayerUpdateMap = {}

        self.params['results']['TOTAL_CANOPY_ABUNDANCE'] = self.params['results'][DataLayer.TREE_COVER].LayerSource.featureCount()

        processedResults = 0
        totalResults = len(tcacAssessmentResults)

        tcacResult : TcacAssessmentResult
        for tcacResult in tcacAssessmentResults:

            # get corresponding feature from OMBR layer
            #oriented_feature = self.params['results'][DataLayer.TREE_COVER_MBR].LayerSource.getFeature(tcacResult.FeatureId)  
            #oriented_feature.setGeometry(tcacResult.OrientedMinimumBoundingRectangle.OrientedMinimumBoundingRectangle[0])
            #self.params['results'][DataLayer.TREE_COVER_MBR].LayerSource.updateFeature(oriented_feature)

            # update abundance at dataset level
            self.params['results']['TOTAL_TREE_ABUNDANCE'] += tcacResult.LocalTreeAbundance            
            # get current tree classification
            currentClass = tcacResult.TreeConfigurationClass
            
            # prepare tree update map
            for treeId in tcacResult.ContainedTreeFeatures:
                treeLayerUpdateMap[treeId] = { idxTreeLayerTreeClassField : currentClass.value }

            canopyLayerUpdateMap[tcacResult.FeatureId] = {
                idxCanopyLayerTreeIdField : tcacResult.TreeIds,
                idxCanopyLayerOmbrAngleField : tcacResult.OrientedMinimumBoundingRectangle.OrientedMinimumBoundingRectangle[2],
                idxCanopyLayerOmbrWidthField : tcacResult.OrientedMinimumBoundingRectangle.OrientedMinimumBoundingRectangle[3],
                idxCanopyLayerOmbrHeightField : tcacResult.OrientedMinimumBoundingRectangle.OrientedMinimumBoundingRectangle[4],
                idxCanopyLayerTreeCountField : tcacResult.LocalTreeAbundance,
                idxCanopyLayerObservedDistanceField : tcacResult.NearestNeighbourAssessmentResult['OBSERVED_MD'],
                idxCanopyLayerExpectedDistanceField : tcacResult.NearestNeighbourAssessmentResult['EXPECTED_MD'],
                idxCanopyLayerNnIndexField : tcacResult.NearestNeighbourAssessmentResult['NN_INDEX'],
                idxCanopyLayerNnZscoreField : tcacResult.NearestNeighbourAssessmentResult['Z_SCORE'],
                idxCanopyLayerTreeClassField : currentClass.value,
                idxCanopyLayerLinearityField : tcacResult.OrientedMinimumBoundingRectangle.Linearity,
                idxCanopyLayerSiacIdField : tcacResult.SiacId
            }

            if self.params['ASSESS_TREE_SPECIES_RICHNESS']:
                canopyLayerUpdateMap[tcacResult.FeatureId][idxCanopyLayerRichnessField] = tcacResult.RichnessAndDiversityAssessmentResult.Richness
                canopyLayerUpdateMap[tcacResult.FeatureId][idxCanopyLayerSpeciesField] = tcacResult.RichnessAndDiversityAssessmentResult.LocalSpeciesAsString
                canopyLayerUpdateMap[tcacResult.FeatureId][idxCanopyLayerSpeciesCountsField] = tcacResult.RichnessAndDiversityAssessmentResult.LocalSpeciesWithCountsAsString
                canopyLayerUpdateMap[tcacResult.FeatureId][idxCanopyLayerFruitTreeContainmentField] = tcacResult.RichnessAndDiversityAssessmentResult.ContainsFruitTreeAsNumeric
                canopyLayerUpdateMap[tcacResult.FeatureId][idxCanopyLayerFruitTreeCountField] = tcacResult.RichnessAndDiversityAssessmentResult.FruitTreeCount
                canopyLayerUpdateMap[tcacResult.FeatureId][idxCanopyLayerFruitTreeShareField] = tcacResult.RichnessAndDiversityAssessmentResult.FruitTreeShare

            # report progress
            processedResults += 1
            self.setProgress( (processedResults/totalResults)*100 ) 

        # apply updates 
        self.params['results'][DataLayer.TREE_COVER].LayerSource.dataProvider().changeAttributeValues(canopyLayerUpdateMap)
        self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource.dataProvider().changeAttributeValues(treeLayerUpdateMap)
        #self.params['results'][DataLayer.TREE_COVER_MBR].LayerSource.dataProvider().changeAttributeValues(canopyLayerUpdateMap)

        # commit changes
        self.params['results'][DataLayer.TREE_COVER].LayerSource.commitChanges()
        #self.params['results'][DataLayer.TREE_COVER_MBR].LayerSource.commitChanges()
        self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource.commitChanges()
        

    def reportTcacSummary(self):
               
        # classification overview
        resLayer = self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource
        treeClasses = [x[SiacField.TREE_CLASSIFICATION.value] for x in resLayer.getFeatures()]
        classStr = 'Tree entities were morphologically classified tentatively as follows:'
        for cls, cnt in Counter(treeClasses).items():
            classStr += '\n{}: {}'.format(cls, cnt)
        self.params['results']['REPORT'].append(classStr)

        # generate certain indices etc. as needed
        if self.params['ASSESS_TREE_SPECIES_RICHNESS']:   
            # report of selected field
            self.params['results']['REPORT'].append("\n\nThe field '{}' is used for the assessment of species richness".format(self.params[SiacToolkitOptionValue.TCAC_PARAMS_SPECIES_FIELDNAME]))
            self.params['results']['REPORT'] += self.params['results']['DIVERSITY'].summary()

        else:
            self.params['results']['REPORT'].append("\n\nNo genus or species field has been selected, therefore, the assessment of species richness has been omitted")
        
        return True
   
    def assessTreeCoverConfiguration(self):
               
        self.siacToolProgressMessage.emit("Assessing Tree Configuration", Qgis.Info)

        # get all canopy cover features to assess
        canopyFeatures = self.params['results'][DataLayer.TREE_COVER].LayerSource.getFeatures()
        # in single process we cannot avoid for loop here
        assessmentResults = []

        processedFeatureCount = 0
        totalFeatureCount = self.params['results'][DataLayer.TREE_COVER].LayerSource.featureCount()

        for f in canopyFeatures:
            currentCanopyAssessmentResult = self.assessTreeCanopyFeature(f)
            assessmentResults.append(currentCanopyAssessmentResult)

            # report progress
            processedFeatureCount += 1
            self.setProgress( (processedFeatureCount/totalFeatureCount)*100 ) 

        return assessmentResults
    
    
    def assessTreeFeaturesAsIndividuals(self):
        
        self.siacToolProgressMessage.emit("Assessing Tree Entities", Qgis.Info)

        self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, idxNewClassField = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, SiacField.SOLITARY_TREE_CLASSIFICATION.value, QVariant.String)

        # get layers and cache
        treeLayer = self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource
        cacheOfTrees : CachedLayerItem = self.params['CACHE'].getFromCache(DataLayer.CLASSIFIED_TREES) #FeatureCache.layerToCache(treeLayer, None, None)
        adjacencyThreshold = self.params[SiacToolkitOptionValue.TYPOLOGY_NEAR_THRESHOLD]


        updateMap = {}
        treeLayer.startEditing()

        processedFeatureCount = 0
        totalFeatureCount = treeLayer.featureCount()
        for t in treeLayer.getFeatures():
            
            # skip if not a solitary tree
            if t[SiacField.TREE_CLASSIFICATION.value] == TreePatternConfiguration.SOLITARY.value:

                pnts = [ t.geometry().asPoint() ]

                bufferedGeometry = t.geometry().buffer(adjacencyThreshold, 100)
                
                treesInBuffer = cacheOfTrees.getFeaturesFromCacheInGeometry(bufferedGeometry, TopologyRule.CONTAINS)
                for f in treesInBuffer:
                    pnts.append(f.geometry().asPoint())
                
                
                treeConfig = TreePatternConfiguration.UNDEFINED
                if len(pnts) > 2:
                    # row is determined from a minimum of 3 trees, although that is likely still rather challenging to assess correctly
                    geoms = QgsGeometry.fromMultiPointXY(pnts)
                    ombr = geoms.orientedMinimumBoundingBox()
                    a = ombr[3] # width
                    b = ombr[4] # height
                    elongation = (b/a) if a > b else (a/b)
                    linearity = 1-elongation

                    treeConfig = TreePatternConfiguration.SOLITARY_POTENTIAL_ROW if linearity > self.params[SiacToolkitOptionValue.TYPOLOGY_LINEARITY_THRESHOLD] else TreePatternConfiguration.SOLITARY_OTHER_GROUPING

                elif len(pnts) == 2:
                    # with two points, it is a pair of trees
                    treeConfig = TreePatternConfiguration.SOLITARY_PAIR

                elif len(pnts) < 2:
                    # this would basically the single tree of interest, no other trees in adjacency
                    treeConfig = TreePatternConfiguration.SOLITARY_SINGLE_TREE

                updateMap[t.id()] = { idxNewClassField : treeConfig.value } 


            else:
                pass
            
            processedFeatureCount += 1
            self.setProgress( (processedFeatureCount/totalFeatureCount)*100 ) 

        treeLayer.dataProvider().changeAttributeValues(updateMap)
        treeLayer.commitChanges()


