from qgis.core import *
from qgis.core import *
from qgis.gui import QgsMessageBar, QgsMapLayerComboBox, QgsFieldComboBox
from qgis.PyQt.QtCore import Qt, QThread, QSettings, QTranslator, QCoreApplication, QVariant, pyqtSignal, QAbstractTableModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QErrorMessage, QAction, QMessageBox, QProgressBar
import processing

from typing import Iterable, Dict

import statistics as stats
import itertools
import networkx as nx
from networkx.algorithms.connectivity.edge_kcomponents import bridge_components

from math import factorial

from ..SiacEnumerations import *
from ..SiacFoundation import LayerHelper, SelectionHelper, CachedLayerItem, FeatureCache
from ..MomepyIntegration import MomepyHelper
from ..SiacDataStore import SiacDataStore
from ..toolkitData.SiacDataStoreLayerSource import SiacDataStoreLayerSource
from ..SiacEntityManagement import SiacEntityRepresentation, SiacEntityLayerManager
from .DATA import DataProcessor
from ..toolkitData.SiacDataSourceOptions import ProjectDataSourceOptions

class TopologyModeller(QgsTask):

    MESSAGE_CATEGORY = "TOPOMOD"
    
    siacToolMaximumProgressValue = pyqtSignal(int)
    siacToolProgressValue = pyqtSignal(int)
    siacToolProgressMessage = pyqtSignal(object, object)
    jobFinished = pyqtSignal(bool, object)

    @staticmethod
    def getModuleSupportedEntityTypes(task : TopomodTask) -> Iterable[SiacEntity]:
        if task == TopomodTask.COMPUTE_TOPOLOGY:
            return [ SiacEntity.URBAN_GREEN_SPACE, SiacEntity.WATER_BODIES ]
        if task == TopomodTask.COMPUTE_NEAREST_NEIGHBOUR_NETWORK:
            return [ SiacEntity.URBAN_GREEN_SPACE, SiacEntity.FOREST ]
        if task == TopomodTask.COMPUTE_CONNECTIVITY:
            return []
        if task == TopomodTask.ASSESS_FRAGMENTATION:
            return []

    def __init__(self, workerParams):
        super().__init__("TOPOMOD Task", QgsTask.CanCancel)
        self.stopWorker = False
        self.params = workerParams
        self.results = {}
        self.totalSteps = 8
        self.uidFieldName = SiacField.SIAC_ID.value        
        self.params['exception'] = ""
        self.params['results'] = {}
        self.params['results'][SiacToolkitDataType.NEAR_LAYER] = []
        self.params['results']['REPORT'] = []
        self.params['results'][SiacToolkitDataType.GRAPH] = {}

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
                
        self.siacToolProgressMessage.emit("Preparing TOPOMOD environment", Qgis.Info)  
    
        # get ancillary data
        ancillaryDataManager : SiacEntityLayerManager = self.params[DataLayer.ANCILLARY_DATA]
        ancillaryDataManager.processLayers()
                
        # prepare data layers, create attributes as needed
        if self.params['TASK'] == TopomodTask.COMPUTE_TOPOLOGY:  

            # prepare required layers
            self.params['results'][DataLayer.TREE_COVER] = self.params[DataLayer.TREE_COVER].clone() 
            self.params['results'][DataLayer.TREE_COVER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.TREE_COVER].LayerSource, SiacField.TOPOLOGY_CONTAINMENT_IN_STREET.value, QVariant.Int )
                        
            self.siacToolProgressValue.emit(1)
            
            # add fields to street morphology layer and building layer that will hold tree counts
            # however, add fields only if we actually do the assessment, i.e., if classified trees layer is provided
            # here, also make sure that we have unique ids in the these layers
            self.params['results'][DataLayer.MORPHOLOGY_STREETS] = self.params[DataLayer.MORPHOLOGY_STREETS].clone() 
            self.params['results'][DataLayer.BUILDINGS] = self.params[DataLayer.BUILDINGS].clone()

            # assertain that layers have the proper UID fields included, otherwise, create these fields
            if not LayerHelper.containsFieldWithName(self.params['results'][DataLayer.MORPHOLOGY_STREETS].LayerSource, SiacField.UID_STREETSEGMENT.value):
                self.params['results'][DataLayer.MORPHOLOGY_STREETS].LayerSource = LayerHelper.createLayerUniqueId(self.params['results'][DataLayer.MORPHOLOGY_STREETS].LayerSource, SiacField.UID_STREETSEGMENT.value)
            if not LayerHelper.containsFieldWithName(self.params['results'][DataLayer.BUILDINGS].LayerSource, SiacField.UID_BUILDING.value):
                self.params['results'][DataLayer.BUILDINGS].LayerSource = LayerHelper.createLayerUniqueId(self.params['results'][DataLayer.BUILDINGS].LayerSource, SiacField.UID_BUILDING.value)            
            
            if self.params[DataLayer.CLASSIFIED_TREES] is not None:
                self.params['results'][DataLayer.MORPHOLOGY_STREETS].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.MORPHOLOGY_STREETS].LayerSource, SiacField.TOPOLOGY_IN_TREE_COUNT.value, QVariant.Int, 0);
                self.params['results'][DataLayer.MORPHOLOGY_STREETS].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.MORPHOLOGY_STREETS].LayerSource, SiacField.TOPOLOGY_NEAR_TREE_COUNT.value, QVariant.Int, 0);
                self.params['results'][DataLayer.BUILDINGS].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.BUILDINGS].LayerSource, SiacField.TOPOLOGY_NEAR_TREE_COUNT.value, QVariant.Int, 0);

            # at this stage, we would likely also need to rectify geometries again if we have ancillary classes, i.e., similar to SITA,
            # attempt to correct topological relationships
            # for compute_topology task, adjust street topology with ancillary types, similar to SITA
            # base this on prepared street morphology layer
            self.params[TopomodTask.COMPUTE_TOPOLOGY] = {}
            self.params[TopomodTask.COMPUTE_TOPOLOGY][DataLayer.MORPHOLOGY_STREETS] = self.params['results'][DataLayer.MORPHOLOGY_STREETS].clone()

            adjLayers = {}            
            r : SiacEntityRepresentation
            for r in ancillaryDataManager.getEntityRepresentationsOfGeometryType(SiacGeometryType.POLYGON):
                adjLayers[r.Layer.ItemId] = r.Layer.LayerSource
            
            if len(adjLayers.keys()) > 0:
                # we have something to adjust for; 
                self.params[TopomodTask.COMPUTE_TOPOLOGY][DataLayer.MORPHOLOGY_STREETS].LayerSource, _ = DataProcessor.rectifyLayers( self.params[TopomodTask.COMPUTE_TOPOLOGY][DataLayer.MORPHOLOGY_STREETS].LayerSource, adjLayers, False )  
            
            self.params[TopomodTask.COMPUTE_TOPOLOGY][DataLayer.MORPHOLOGY_STREETS].LayerSource.setName(DataLayer.MORPHOLOGY_STREETS.value) 

             # prepare optional layers
            if self.params[DataLayer.CLASSIFIED_TREES] is not None:
                # add basic fields as needed to classified trees
                self.params['results'][DataLayer.CLASSIFIED_TREES] = self.params[DataLayer.CLASSIFIED_TREES].clone() 
                self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, SiacField.TOPOLOGY_CONTAINMENT_IN_STREET.value, QVariant.Int)
                self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, SiacField.TOPOLOGY_DISTANCE_TO_STREET.value, QVariant.Double)
                self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, SiacField.TOPOLOGY_DISTANCE_TO_BUILDING.value, QVariant.Double)
                self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, SiacField.TOPOLOGY_ADJACENCY_TO_STREET.value, QVariant.Int)
                self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, SiacField.TOPOLOGY_ADJACENCY_TO_BUILDING.value, QVariant.Int)

            # prepare caches
            self.params["CACHE"].cacheLayer(self.params[TopomodTask.COMPUTE_TOPOLOGY][DataLayer.MORPHOLOGY_STREETS].LayerSource, DataLayer.MORPHOLOGY_STREETS)
            self.params["CACHE"].cacheLayer(self.params['results'][DataLayer.TREE_COVER].LayerSource, DataLayer.TREE_COVER, SiacField.UID_CANOPY.value)   
            self.params["CACHE"].cacheLayer(self.params['results'][DataLayer.BUILDINGS].LayerSource, DataLayer.BUILDINGS, SiacField.UID_BUILDING.value) 

            # TODO: ADD BLDG UNIQUE ID

            self.siacToolProgressValue.emit(2)            

        if self.params['TASK'] == TopomodTask.COMPUTE_NEAREST_NEIGHBOUR_NETWORK:
            pass

        if self.params['TASK'] == TopomodTask.ASSESS_FRAGMENTATION:

            self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER] = self.params[DataLayer.CONNECTIVITY_BASE_LAYER].clone()  
            self.siacToolProgressValue.emit(1)
            
            self.params["CACHE"].cacheLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, DataLayer.CONNECTIVITY_BASE_LAYER, SiacField.UID_CONNECT.value)   
            self.params["CACHE"].cacheLayer(self.params[DataLayer.BUILDINGS].LayerSource, DataLayer.BUILDINGS)   

        if self.params['TASK'] == TopomodTask.COMPUTE_CONNECTIVITY:   
            
            # prepare data layers
            # copy shortest lines input layer to be re-used as edges layer, but keeping original for further evaluations
            self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER] = self.params[DataLayer.CONNECTIVITY_BASE_LAYER].clone()            
            self.params['results'][DataLayer.BUILDINGS] = self.params[DataLayer.BUILDINGS].clone()
            self.siacToolProgressValue.emit(1)

            # add relevant fields to layers           
            self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, SiacField.CONNECTIVITY_CANOPY_CPL.value, QVariant.Double )
            self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, SiacField.CONNECTIVITY_CANOPY_LNK.value, QVariant.Int )        
            self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, SiacField.CONNECTIVITY_CANOPY_CAPACITY.value, QVariant.Double )        
            self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, SiacField.CONNECTIVITY_COMPONENT_ID.value, QVariant.Int )
            self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, SiacField.CONNECTIVITY_COMPONENT_NK.value, QVariant.Int )
            self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, SiacField.CONNECTIVITY_COMPONENT_CAPACITY.value, QVariant.Double )
            self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, SiacField.CONNECTIVITY_IS_BRIDGE.value, QVariant.Int )
            self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, SiacField.CONNECTIVITY_IS_ARTICULATION_POINT.value, QVariant.Int )            
            
            if self.params["ADVANCED_INDICATORS"]["CLOSENESS"] == True:
                self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, SiacField.CONNECTIVITY_CLOSENESS_CENTRALITY.value, QVariant.Double )
            
            if self.params["ADVANCED_INDICATORS"]["ECCENTRICITY"] == True:
                self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, SiacField.CONNECTIVITY_ECCENTRICITY.value, QVariant.Double )
            
            if self.params["ADVANCED_INDICATORS"]["DIAMETER"] == True:
                self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, SiacField.CONNECTIVITY_COMPONENT_DIAMETER.value, QVariant.Double )
            
            if self.params["ADVANCED_INDICATORS"]["DEGREE_CENTRALITY"] == True:
                self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, SiacField.CONNECTIVITY_DEGREE_CENTRALITY.value, QVariant.Double )
            
            if self.params["ADVANCED_INDICATORS"]["BETWEENNESS"] == True:
                self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, SiacField.CONNECTIVITY_BETWEENNESS_CENTRALITY.value, QVariant.Double )

            self.siacToolProgressValue.emit(2)            


            self.params["CACHE"].cacheLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, DataLayer.CONNECTIVITY_BASE_LAYER, SiacField.UID_CONNECT.value)   
            self.params["CACHE"].cacheLayer(self.params['results'][DataLayer.BUILDINGS].LayerSource, DataLayer.BUILDINGS)   











             
        self.siacToolProgressValue.emit(3)

        # depending on task, do work
        if self.params['TASK'] == TopomodTask.COMPUTE_TOPOLOGY:                         

            # prepare additional cache layers for this task as needed
            self.params["CACHE"].cacheLayer(self.params[DataLayer.STREETS].LayerSource, DataLayer.STREETS)            
            if self.params[DataLayer.CLASSIFIED_TREES] is not None:
                self.params["CACHE"].cacheLayer(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, DataLayer.CLASSIFIED_TREES, SiacField.UID_TREE.value)  
            
            # assess feature associations with street layer
            self.siacToolProgressMessage.emit("Modelling topological relationships to street features", Qgis.Info) 
            self.relationshipModellingTreeEntityContainmentInFeatureClass(SiacField.TOPOLOGY_CONTAINMENT_IN_STREET.value, self.params[TopomodTask.COMPUTE_TOPOLOGY][DataLayer.MORPHOLOGY_STREETS].LayerSource, uidField=SiacField.UID_STREETSEGMENT.value, targetLayerToUpdate=self.params['results'][DataLayer.MORPHOLOGY_STREETS].LayerSource)                    
            self.siacToolProgressValue.emit(4)

            # near analysis trees to streets
            self.siacToolProgressMessage.emit("Assessing distance metrics and asserting adjacency to street features", Qgis.Info) 
            barriers = [ self.params[DataLayer.BUILDINGS] ]
            # TODO: Add other entity types that prevent adjacency, e.g., waterbodies etc.
            self.relationshipModellingTreeEntityDistanceAndAdjacencyToFeatureClass(DataLayer.MORPHOLOGY_STREETS.value, SiacField.TOPOLOGY_ADJACENCY_TO_STREET.value, SiacField.TOPOLOGY_DISTANCE_TO_STREET.value, self.params[TopomodTask.COMPUTE_TOPOLOGY][DataLayer.MORPHOLOGY_STREETS].LayerSource, barriers, self.params[SiacToolkitOptionValue.TYPOLOGY_NEAR_THRESHOLD], uidField=SiacField.UID_STREETSEGMENT.value, targetLayerToUpdate=self.params['results'][DataLayer.MORPHOLOGY_STREETS].LayerSource)
            
            self.siacToolProgressValue.emit(5)

            # near analysis trees to buildings
            self.siacToolProgressMessage.emit("Assessing distance metrics and asserting adjacency to building features", Qgis.Info) 
            barriers = [ self.params[DataLayer.STREETS] ]
            # TODO: Add other entity types that prevent adjacency, e.g., waterbodies etc.
            self.relationshipModellingTreeEntityDistanceAndAdjacencyToFeatureClass(DataLayer.BUILDINGS.value, SiacField.TOPOLOGY_ADJACENCY_TO_BUILDING.value, SiacField.TOPOLOGY_DISTANCE_TO_BUILDING.value, self.params['results'][DataLayer.BUILDINGS].LayerSource, barriers, self.params[SiacToolkitOptionValue.TYPOLOGY_NEAR_THRESHOLD], uidField=SiacField.UID_BUILDING.value)
            self.siacToolProgressValue.emit(6)

            # topolgy analysis to ancillary classes/entity types
            polygonEntityRepresentations = ancillaryDataManager.getEntityRepresentationsOfGeometryType(SiacGeometryType.POLYGON)    
            for r in polygonEntityRepresentations:
                
                self.siacToolProgressMessage.emit("Assessing topology for {}".format(r.EntityType.label), Qgis.Info)

                # depending on the type of entity, assess containment, adjacency, or both
                if r.EntityType == SiacEntity.URBAN_GREEN_SPACE:
                    
                    barriers = [ self.params[DataLayer.BUILDINGS], self.params[DataLayer.STREETS] ]

                    # add relevant fields to the input layer, then call corresponding tool function
                    self.params['results'][DataLayer.TREE_COVER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.TREE_COVER].LayerSource, r.EntityType.getOtherEntityIsContainedFieldName(), QVariant.Int )
                    self.params['results'][DataLayer.TREE_COVER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.TREE_COVER].LayerSource, r.EntityType.getAdjacencyToEntityFieldName(), QVariant.Int )
                    self.params['results'][DataLayer.TREE_COVER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.TREE_COVER].LayerSource, r.EntityType.getDistanceToEntityFieldName(), QVariant.Double )
                    
                    if self.params[DataLayer.CLASSIFIED_TREES] is not None:
                        self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, _ =LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, r.EntityType.getOtherEntityIsContainedFieldName(), QVariant.Int )
                        self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, _ =LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, r.EntityType.getAdjacencyToEntityFieldName(), QVariant.Int )
                        self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, _ =LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, r.EntityType.getDistanceToEntityFieldName(), QVariant.Double )
                        
                    self.relationshipModellingTreeEntityContainmentInFeatureClass(r.EntityType.getOtherEntityIsContainedFieldName(), r.Layer.LayerSource, None) 
                    self.relationshipModellingTreeEntityDistanceAndAdjacencyToFeatureClass( r.EntityType.label, r.EntityType.getAdjacencyToEntityFieldName(), r.EntityType.getDistanceToEntityFieldName(), r.Layer.LayerSource, barriers, self.params[SiacToolkitOptionValue.TYPOLOGY_NEAR_THRESHOLD] )

                if r.EntityType == SiacEntity.WATER_BODIES:
                    barriers = [ self.params[DataLayer.BUILDINGS], self.params[DataLayer.STREETS] ]
                    
                    # add relevant fields to the input layer, then call corresponding tool function
                    self.params['results'][DataLayer.TREE_COVER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.TREE_COVER].LayerSource, r.EntityType.getAdjacencyToEntityFieldName(), QVariant.Int )
                    self.params['results'][DataLayer.TREE_COVER].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.TREE_COVER].LayerSource, r.EntityType.getDistanceToEntityFieldName(), QVariant.Double )

                    if self.params[DataLayer.CLASSIFIED_TREES] is not None:
                        self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, _ =LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, r.EntityType.getAdjacencyToEntityFieldName(), QVariant.Int )
                        self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, _ =LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, r.EntityType.getDistanceToEntityFieldName(), QVariant.Double )

                    self.relationshipModellingTreeEntityDistanceAndAdjacencyToFeatureClass( r.EntityType.label, r.EntityType.getAdjacencyToEntityFieldName(), r.EntityType.getDistanceToEntityFieldName(), r.Layer.LayerSource, barriers, self.params[SiacToolkitOptionValue.TYPOLOGY_NEAR_THRESHOLD] )
                    
        if self.params['TASK'] == TopomodTask.COMPUTE_NEAREST_NEIGHBOUR_NETWORK:
            
            # construct shortest lines, then return
            self.siacToolProgressMessage.emit("Generating shortest lines feature layer", Qgis.Info) 
            self.connectivityModellingGenerateNearestNeighbourNetwork()
            self.siacToolProgressValue.emit(4)

        if self.params['TASK'] == TopomodTask.ASSESS_FRAGMENTATION:
            
            self.siacToolProgressMessage.emit("Assessing Fragmentation", Qgis.Info) 
            distanceRanges = self.params['RANGES']
            self.connectivityModellingAssessFragmentation(distanceRanges)

        if self.params['TASK'] == TopomodTask.COMPUTE_CONNECTIVITY:  

            # use single distance threshold value
            distVal = self.params['CONNECTIVITY_THRESHOLD']  

            # graph construction from shortest lines layer
            self.siacToolProgressMessage.emit("Constructing connectivity graph", Qgis.Info) 
            self.connectivityModellingGenerateGraph(distVal, True)
            self.siacToolProgressValue.emit(4)

            # connectivity assessment
            self.siacToolProgressMessage.emit("Evaluating graph and connectivity", Qgis.Info)
            self.connectivityModellingAssessStructuralConnectivity(distVal)
            self.siacToolProgressValue.emit(5)
        
        # set progress to full
        self.siacToolProgressValue.emit(8)
        return True
         

    def relationshipModellingTreeEntityDistanceAndAdjacencyToFeatureClass(self, entityName, adjacencyTargetFieldName, distanceTargetFieldName, targetLayer : QgsVectorLayer, barrierLayers : Iterable[SiacDataStoreLayerSource], nearThreshold, uidField = None, targetLayerToUpdate = None ):
        
        # target layer is the layer, and distance and adjacency is being identified relative to features of this layer

        # build a cache of barrier layers
        barrierCaches : Dict[str, CachedLayerItem] = {}
        for barrierLayer in barrierLayers:
            barrierCaches[barrierLayer.ItemId] = self.params['CACHE'].getFromCache(DataLayer(barrierLayer.LayerType))

        # for now, this function only operates at the level of individual trees, not canopies
        if self.params[DataLayer.CLASSIFIED_TREES] is not None:            
            idxTreeAdjacencyField = LayerHelper.getFieldIndex(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, adjacencyTargetFieldName)
            idxTreeDistanceField = LayerHelper.getFieldIndex(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, distanceTargetFieldName)

            cacheOfClassifiedTreeFeatures : CachedLayerItem = self.params['CACHE'].getFromCache(DataLayer.CLASSIFIED_TREES)  

            
            
            if uidField is not None:
                
                # determine layer to update
                if targetLayerToUpdate is None:
                    targetLayerToUpdate = targetLayer

                cacheOfTargetFeatures : CachedLayerItem = FeatureCache.layerToCache(targetLayerToUpdate, None, uidField)          
                idxNearTreeCountField = LayerHelper.getFieldIndex(targetLayerToUpdate, SiacField.TOPOLOGY_NEAR_TREE_COUNT.value) if LayerHelper.containsFieldWithName(targetLayerToUpdate, SiacField.TOPOLOGY_NEAR_TREE_COUNT.value) else None
                targetLayerUpdateMap = {}

            self.siacToolProgressMessage.emit("Computing shortest lines from tree entities to {}".format(targetLayer.name()), Qgis.Info) 
            nearlayer = processing.run("native:shortestline", { 'SOURCE': self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource,'DESTINATION': targetLayer,'METHOD':0,'NEIGHBORS':1,'DISTANCE':None,'OUTPUT':'TEMPORARY_OUTPUT'})['OUTPUT']
            
            nearLayerName = "Trees near {}".format(entityName.lower())

            # make a data source from the shortest lines output
            treeLinesDataSource = SiacDataStoreLayerSource.makeNewDataStoreLayerSourceItem(nearlayer, DataLayer.TOPOLOGY_TREES_NEAR_ENTITY.value, nearLayerName, None)
            treeLinesDataSource.SetTouched()
            self.params['results'][SiacToolkitDataType.NEAR_LAYER].append(treeLinesDataSource)


            # iterate over shortest lines features
            processedCount = 0
            totalCount = treeLinesDataSource.LayerSource.featureCount()

            updateMap = {}
            for shortestLineFeature in treeLinesDataSource.LayerSource.getFeatures():

                if self.stopWorker:
                    return False

                # this is the line feature
                currentFeatureDistance = shortestLineFeature['distance']
                featureGeometry = shortestLineFeature.geometry()

                # get source, i.e., the tree entity
                sourceTreeId = shortestLineFeature[SiacField.UID_TREE.value] # SIAC UID of corresonding tree feature in classified trees                
                mappedFeatureId = cacheOfClassifiedTreeFeatures.AttributeToIdMapping[str(sourceTreeId)] 
                updateMap[mappedFeatureId] = { idxTreeDistanceField : currentFeatureDistance }
                

                # determine if features from layers acting as barriers are intersected; then no adjacency is assumed
                barrierIsIntersected = False
                for barrierLayer in barrierLayers:
                    # get from target layer cache intersected features
                    intersectingFeatureFromBarrierLayer = barrierCaches[barrierLayer.ItemId].getFeaturesFromCacheInGeometry(featureGeometry, TopologyRule.INTERSECTS )
                    if len(intersectingFeatureFromBarrierLayer) > 0:
                        barrierIsIntersected = True
                        break 

                # determine adjacency/is near
                # this is true if not intersected by barrier, and if distance within near threshold. otherwise, not considered adjacent
                isAdjacent = 0 if (barrierIsIntersected == True or currentFeatureDistance > nearThreshold) else 1
                updateMap[mappedFeatureId][idxTreeAdjacencyField] = isAdjacent

                # also, get target, and update number of associated trees with that target in the following
                # the target is either the unique id field name provided, or id if nont
                # since many lines may, at any time, be linkted to a given target feature, update target counts in target layer update map
                if idxNearTreeCountField is not None and uidField is not None and isAdjacent == 1:
                    featureUid = str(shortestLineFeature[uidField])                    
                    origId = cacheOfTargetFeatures.AttributeToIdMapping[featureUid]       
                    if origId in targetLayerUpdateMap.keys():
                        targetLayerUpdateMap[origId][idxNearTreeCountField] += 1
                    else:
                        targetLayerUpdateMap[origId] = { idxNearTreeCountField : 1 }

                # report progress
                processedCount += 1
                self.setProgress( (processedCount/totalCount)*100 )  

            # update classified tree features
            self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource.startEditing()
            self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource.dataProvider().changeAttributeValues(updateMap)
            self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource.commitChanges()

            # write near tree counts to targetlayer
            targetLayerToUpdate.startEditing()
            targetLayerToUpdate.dataProvider().changeAttributeValues(targetLayerUpdateMap)
            targetLayerToUpdate.commitChanges()



    def relationshipModellingTreeEntityContainmentInFeatureClass(self, targetFieldName, targetLayer, uidField = None, targetLayerToUpdate = None ):
        
        # this function assesses containment and adjacency of tree entities within given target layer features
        # typically, target layer to update should be the very same as target layer, so none would be default. 
        # however, if we want to write data to an actually different layer than the one used for the analysis (i.e., write to base layer instead of internally topologcally corrected one),
        # then the target layer to update machanism can be used. e.g., in case of street morphology

        # get relevant data and caches and
        # determine target field names
        cacheOfCanopyFeatures : CachedLayerItem = self.params['CACHE'].getFromCache(DataLayer.TREE_COVER)
        idxTreeCoverContainmentField = LayerHelper.getFieldIndex(self.params['results'][DataLayer.TREE_COVER].LayerSource, targetFieldName)
        
        # determine layer to update
        if targetLayerToUpdate is None:
            targetLayerToUpdate = targetLayer
        cacheOfTargetFeatures : CachedLayerItem = FeatureCache.layerToCache(targetLayerToUpdate, None, uidField) if uidField is not None else FeatureCache.layerToCache(targetLayerToUpdate, None, None)

        if self.params[DataLayer.CLASSIFIED_TREES] is not None:
            idxTreeContainmentField = LayerHelper.getFieldIndex(self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource, targetFieldName)
            cacheOfClassifiedTrees : CachedLayerItem = self.params['CACHE'].getFromCache(DataLayer.CLASSIFIED_TREES)  

        # determine containment/intersection: iterate over entity features
        self.siacToolProgressMessage.emit("Iterating street features", Qgis.Info) 
        
        # progress reporting
        processedEntityFeatureCount = 0
        totalEntityFeatureCount = targetLayer.featureCount()
        self.siacToolMaximumProgressValue.emit(totalEntityFeatureCount)
        self.siacToolProgressValue.emit(0) 

        idxCountInTreeField = LayerHelper.getFieldIndex(targetLayer, SiacField.TOPOLOGY_IN_TREE_COUNT.value) if LayerHelper.containsFieldWithName(targetLayer, SiacField.TOPOLOGY_IN_TREE_COUNT.value) else None
        targetLayerUpdateMap = {}
        for targetFeature in targetLayer.getFeatures():

            if self.stopWorker:
                return False
                       
            # containment for canopies is assessed by intersection: the whole canopy will be marked as contained if parts intersect target layer features
            featureGeometry = targetFeature.geometry()
            featureUid = str(targetFeature[uidField]) if uidField is not None else targetFeature.id()

            touchingCanopies = cacheOfCanopyFeatures.getFeaturesFromCacheInGeometry(featureGeometry, TopologyRule.INTERSECTS )
            canopyFeatureCount = len(touchingCanopies)
            
            # containment for trees is determined individually: even if they are part of a canopy, their respective trait is assessed independently
            treeFeatureCount = 0
            if self.params[DataLayer.CLASSIFIED_TREES] is not None:
                containedTrees = cacheOfClassifiedTrees.getFeaturesFromCacheInGeometry(featureGeometry, TopologyRule.INTERSECTS )
                treeFeatureCount = len(containedTrees)
                
                if idxCountInTreeField is not None:   
                    origID = cacheOfTargetFeatures.AttributeToIdMapping[featureUid] if uidField is not None else featureUid            
                    targetLayerUpdateMap[origID] = { idxCountInTreeField : treeFeatureCount }

            # progress reporting
            processedCount = 0
            progressTotalCount = canopyFeatureCount + treeFeatureCount
            
            updateMap = {}
            for f in touchingCanopies:
                updateMap[f.id()] = { idxTreeCoverContainmentField : 1 }

                # report progress
                processedCount += 1
                self.setProgress( (processedCount/progressTotalCount)*100 )  
            
            self.params['results'][DataLayer.TREE_COVER].LayerSource.startEditing()
            self.params['results'][DataLayer.TREE_COVER].LayerSource.dataProvider().changeAttributeValues(updateMap)
            self.params['results'][DataLayer.TREE_COVER].LayerSource.commitChanges()
            
            updateMap = {}  
            if self.params[DataLayer.CLASSIFIED_TREES] is not None:
                for f in containedTrees:
                    updateMap[f.id()] = { idxTreeContainmentField : 1 }

                    # report progress
                    processedCount += 1
                    self.setProgress( (processedCount/progressTotalCount)*100 )  

                self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource.startEditing()
                self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource.dataProvider().changeAttributeValues(updateMap)
                self.params['results'][DataLayer.CLASSIFIED_TREES].LayerSource.commitChanges()



            processedEntityFeatureCount += 1
            self.siacToolProgressValue.emit(processedEntityFeatureCount)   

        # finally, we should also update the target layer's TR_CNT_IN attribute
        targetLayerToUpdate.startEditing()
        targetLayerToUpdate.dataProvider().changeAttributeValues(targetLayerUpdateMap)
        targetLayerToUpdate.commitChanges()



    def connectivityModellingGenerateNearestNeighbourNetwork(self):
        
        # compute shortest lines from canopy to canopy, using X neighbours  
        # https://docs.qgis.org/3.28/en/docs/user_manual/processing_algs/qgis/vectoranalysis.html#shortest-line-between-features 
                
        # define parameters for shortestlines algorithm
        nn_count = int(self.params['NN_COUNT'])        
        anchor = self.params['ANCHOR']  
        
        # prior creation of input layer, process also ancillary classes
        # first, we get all polygon-type entities, and we merge all of them together with tree cover into a single entity
        # this is needed so that we can create the nearest lines layer effectively
        ancillaryDataManager : SiacEntityLayerManager = self.params[DataLayer.ANCILLARY_DATA]
        polygonRepresentations = ancillaryDataManager.getEntityRepresentationsOfGeometryType(SiacGeometryType.POLYGON)        
        layersToCombine = [ self.params[DataLayer.TREE_COVER].LayerSource ]
        for r in polygonRepresentations:
            layersToCombine.append(r.Layer.LayerSource)
        
        combinedLayer = DataProcessor.combineLayers(layersToCombine, SiacGeometryType.POLYGON, ProjectDataSourceOptions.Crs)
        combinedLayer = LayerHelper.createLayerUniqueId(combinedLayer, SiacField.UID_CONNECT.value)

        baseDs = SiacDataStoreLayerSource.makeNewDataStoreLayerSourceItem(combinedLayer, DataLayer.CONNECTIVITY_BASE_LAYER.value, DataLayer.CONNECTIVITY_BASE_LAYER.value, None )
        baseDs.SetTouched()        
        self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER] = baseDs

        # potentially, if centroid, add points
        # this determines the input, i.e., polygon boundaries or centroids
        linesLayer = None
        if anchor == 0:
            linesLayer = combinedLayer #self.params[DataLayer.TREE_COVER].LayerSource
        elif anchor == 1:
            nodeLayer = processing.run("native:centroids", { 'INPUT': combinedLayer, 'OUTPUT':'TEMPORARY_OUTPUT'}) # self.params[DataLayer.TREE_COVER].LayerSource            
            linesLayer = nodeLayer['OUTPUT']
        

        self.siacToolProgressMessage.emit("Computing shortest lines using canopies as nodes ({})".format(str(nn_count)), Qgis.Info) 
        nearlayer = processing.run("native:shortestline", { 'SOURCE': linesLayer, 'DESTINATION': linesLayer, 'METHOD': anchor, 'NEIGHBORS': nn_count, 'DISTANCE': None, 'OUTPUT':'TEMPORARY_OUTPUT'})                
        nnlayer = LayerHelper.removeFieldsFromLayer(nearlayer['OUTPUT'], fieldsToRetain=[ SiacField.UID_CONNECT.value, SiacField.UID_CANOPY.value, "{}_2".format(SiacField.UID_CONNECT.value), "{}_2".format(SiacField.UID_CANOPY.value), "distance" ])
        
        nearDs = SiacDataStoreLayerSource.makeNewDataStoreLayerSourceItem(nnlayer, DataLayer.CONNECTIVITY_NEAREST_NEIGHBOURS.value, DataLayer.CONNECTIVITY_NEAREST_NEIGHBOURS.value, None)
        nearDs.SetTouched()
        self.params['results'][DataLayer.CONNECTIVITY_NEAREST_NEIGHBOURS] = nearDs

        self.params['results']['REPORT'].append("The number of neighbours used for connectivity network construction is {:0.0f}".format(self.params['NN_COUNT']))        


    def connectivityModellingAssessFragmentation(self, distanceValues):
        
        self.params['results']['C_DELTA'] = []
        self.params['results']['REPORT'].append('Buildings {}act as barrier'.format( "" if self.params['BUILDINGS_AS_BARRIERS'] == True else "do not " ))

        for distVal in distanceValues:

            setOfComponentCapacities = []
            totalCapacity = 0

            self.connectivityModellingGenerateGraph(distVal, False)
            numberOfComponents = len(list(nx.connected_components(self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)])))

            for currentComponentNodes in nx.connected_components(self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)]):   
                for nodeSiacId in currentComponentNodes:
                    totalCapacity += self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)].nodes[nodeSiacId]['capacity']
                setOfComponentCapacities.append(totalCapacity)
            
            meanSize = stats.mean(setOfComponentCapacities)
            maxSize = max(setOfComponentCapacities)
            minSize = min(setOfComponentCapacities)

            self.params['results']['C_DELTA'].append({ 'dist' : distVal, 'components' : numberOfComponents, 'mean_size' : meanSize })       

            self.params['results']['REPORT'].append("\Connectivity threshold has been set at {:0.2f}m".format(distVal))
            self.params['results']['REPORT'].append("The number of components is estimated at {:0.0f}".format(numberOfComponents))
            self.params['results']['REPORT'].append("The size of the smallest component is estimated at {:0.2f}m²".format(minSize))
            self.params['results']['REPORT'].append("Mean size of the components is estimated at {:0.2f}m²".format(meanSize))
            self.params['results']['REPORT'].append("The size of the largest component is estimated at {:0.2f}m²".format(maxSize))



    def connectivityModellingGenerateGraph(self, distVal, writeLayer):

        self.siacToolProgressMessage.emit("Generating graph nodes", Qgis.Info)        

        # construct a real graph using networkx library                
        self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)] = nx.Graph()

        cacheOfBuildingFeatures = self.params['CACHE'].getFromCache(DataLayer.BUILDINGS)
        
        if writeLayer == True:
            self.params['results'][DataLayer.CONNECTIVITY_EDGES] = SiacDataStoreLayerSource.makeNewDataStoreLayerSourceItem( LayerHelper.copyLayer(self.params[DataLayer.CONNECTIVITY_NEAREST_NEIGHBOURS].LayerSource), DataLayer.CONNECTIVITY_EDGES.value, DataLayer.CONNECTIVITY_EDGES.value, None )
            self.params['results'][DataLayer.CONNECTIVITY_EDGES].SetTouched() 

            # add attribute to indicate whether this shortest line is considered obstructed (not counted towards NN-based canopy network) or not
            self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource, idxObstructionStateField = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource, SiacField.CONNECTIVITY_LINK_OBSTRUCTED.value, QVariant.Int )
            self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource, idxOutOfReachStateField = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource, SiacField.CONNECTIVITY_LINK_OUT_OF_RANGE.value, QVariant.Int )        
            self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource, idxLinkValidField = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource, SiacField.CONNECTIVITY_LINK_VALID.value, QVariant.Int )    
            self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource, _ = LayerHelper.addAttributeToLayer(self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource, SiacField.CONNECTIVITY_IS_BRIDGE.value, QVariant.Int )                

            # start editing sessions
            self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource.startEditing()        
        
        # attempt a feature update using map
        updateFeatureMap = {}   

        # add nodes
        totalNodes = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.featureCount()
        processedNodes = 0

        for f in self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.getFeatures():            
            if self.stopWorker:
                return False
            
            self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)].add_node( str(f[SiacField.UID_CONNECT.value]), siacid=f[SiacField.UID_CONNECT.value], capacity=f.geometry().area(), fid=f.id())
            
            processedNodes += 1
            self.setProgress( (processedNodes/totalNodes)*100 )  


        self.siacToolProgressMessage.emit("Generating graph edges", Qgis.Info)        

        # add edges
        relevantLayer = self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource if writeLayer == True else self.params[DataLayer.CONNECTIVITY_NEAREST_NEIGHBOURS].LayerSource
        numberOfShortestLines = relevantLayer.featureCount()
        processedShortestLines = 0

        for shortestLineFeature in relevantLayer.getFeatures():

            if self.stopWorker:
                return False

            # get source and target of edge
            sourceCanopyId = str(shortestLineFeature[SiacField.UID_CONNECT.value])   
            graphHasSourceNode = self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)].has_node(sourceCanopyId)

            targetCanopyId = str(shortestLineFeature["{}_2".format(SiacField.UID_CONNECT.value)])
            graphHasTargetNode = self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)].has_node(targetCanopyId)

            # test if all nodes exist
            if not graphHasSourceNode or not graphHasTargetNode:
                QgsMessageLog.logMessage("Issue adding source node {} ({}) and target node {} ({})".format(sourceCanopyId, str(graphHasSourceNode), targetCanopyId, str(graphHasTargetNode)), "SIAC", level=Qgis.MessageLevel.Critical)
            
            # determine if the length of this geometry is longer than specified threshold
            exceedsConnectivityThresholdStateValue = 1 if shortestLineFeature.geometry().length() > distVal else 0
            
            # determine if this line intersects a building; only needs to do so when we do not exceed threshold
            if self.params['BUILDINGS_AS_BARRIERS'] == True and exceedsConnectivityThresholdStateValue == 0:            
                intersectedBuildings = SelectionHelper.getIntersectingFeatureIds(shortestLineFeature.geometry(), cacheOfBuildingFeatures, TopologyRule.INTERSECTS)
                obstructionStateValue = 1 if len(intersectedBuildings) > 0 else 0
            else:
                obstructionStateValue = 0
            
            isValidLinkValue = 0 if (exceedsConnectivityThresholdStateValue > 0 or obstructionStateValue > 0) else 1
            
            
            # exclude links to self (which are indicated by a 0-length distance)
            if isValidLinkValue == 1 and shortestLineFeature['distance'] > 0:                               
                # add edge to Graph 
                # the ids in the graph are SIAC_IDs and not Feature Ids!
                self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)].add_edges_from([(sourceCanopyId, targetCanopyId, {'distance' : shortestLineFeature['distance'], 'lineId' : shortestLineFeature.id() })])

            # add to update map
            if writeLayer:
                updateFeatureMap[shortestLineFeature.id()] = { idxObstructionStateField : obstructionStateValue, idxOutOfReachStateField : exceedsConnectivityThresholdStateValue, idxLinkValidField : isValidLinkValue }

            processedShortestLines += 1
            self.setProgress( (processedShortestLines/numberOfShortestLines)*100 )  


        # update multiple features via update map    
        if writeLayer == True:
            # update
            self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource.dataProvider().changeAttributeValues(updateFeatureMap)
            # close editing sessions
            self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource.commitChanges()
         

    def connectivityModellingAssessStructuralConnectivity(self, distVal):

        idxCanopyLayerComponentIdField = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.fields().indexFromName(SiacField.CONNECTIVITY_COMPONENT_ID.value)
        idxCanopyLayerNumberOfPatchesField = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.fields().indexFromName(SiacField.CONNECTIVITY_COMPONENT_NK.value)
        idxCanopyLayerComponentCapacityField = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.fields().indexFromName(SiacField.CONNECTIVITY_COMPONENT_CAPACITY.value)
        idxCanopyLayerMeanDistanceField = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.fields().indexFromName(SiacField.CONNECTIVITY_CANOPY_CPL.value)
        idxCanopyLayerNeighbourCountField = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.fields().indexFromName(SiacField.CONNECTIVITY_CANOPY_LNK.value)
        idxCanopyLayerPatchCapacityField = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.fields().indexFromName(SiacField.CONNECTIVITY_CANOPY_CAPACITY.value)
        idxCanopyLayerBridgeNodeField = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.fields().indexFromName(SiacField.CONNECTIVITY_IS_BRIDGE.value)
        idxCanopyLayerArticulationPointField = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.fields().indexFromName(SiacField.CONNECTIVITY_IS_ARTICULATION_POINT.value)

        idxEdgeLayerBridgeField = self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource.fields().indexFromName(SiacField.CONNECTIVITY_IS_BRIDGE.value)

        # add certain fields only if we require advanced indicators: Note that these may be computationally really heavy
        idxCanopyLayerBetweennessCentralityField = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.fields().indexFromName(SiacField.CONNECTIVITY_BETWEENNESS_CENTRALITY.value) if self.params["ADVANCED_INDICATORS"]["BETWEENNESS"] == True else None
        idxCanopyLayerClosenessCentralityField = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.fields().indexFromName(SiacField.CONNECTIVITY_CLOSENESS_CENTRALITY.value) if self.params["ADVANCED_INDICATORS"]["CLOSENESS"] == True else None
        idxCanopyLayerEccentricityField = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.fields().indexFromName(SiacField.CONNECTIVITY_ECCENTRICITY.value) if self.params["ADVANCED_INDICATORS"]["ECCENTRICITY"] == True else None
        idxCanopyLayerDiameterField = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.fields().indexFromName(SiacField.CONNECTIVITY_COMPONENT_DIAMETER.value) if self.params["ADVANCED_INDICATORS"]["DIAMETER"] == True else None
        idxCanopyLayerDegreeField = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.fields().indexFromName(SiacField.CONNECTIVITY_DEGREE_CENTRALITY.value) if self.params["ADVANCED_INDICATORS"]["DEGREE_CENTRALITY"] == True else None
        
        # determine number of patches in component
        # update found patches, i.e., indicate component membership, etc., so that we may derive even more indicators later as patches can then be treated as components within the graph itself
        cacheOfCanopyFeatures = self.params['CACHE'].cacheLayer(self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, DataLayer.CONNECTIVITY_BASE_LAYER, SiacField.UID_CONNECT.value) 
        
        self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.startEditing()
        self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource.startEditing()

        
        self.siacToolProgressMessage.emit("Assessing Components", Qgis.Info)

        # determine components based on actual connections from the graph object created
        # from shortestlines algorithm
        canopyFeatureUpdateMap = {}
        edgesFeatureUpdateMap = {}

        setOfComponentCapacities = []
        setOfPatchCapacities = []
        setOfPatchCPL = []
        setOfPatchLinks = []

        totalNumberOfNodes = self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.featureCount()
        processedNodes = 0

        currentComponentId = 0    

        for currentComponentNodes in nx.connected_components(self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)]):            
                        
            # increase id
            currentComponentId += 1

            # get feature ids for all nodes from siac ids in the graph
            currentComponentFeatureIds = []  
            totalCapacity = 0

            # get current subgraph 
            # TODO : Only get subgraph if we need it
            currentComponentSubgraph = self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)].subgraph(currentComponentNodes).copy()

            eccentricities = None

            if self.params["ADVANCED_INDICATORS"]["BETWEENNESS"] == True:
                betweennessCentralities = dict(nx.betweenness_centrality(currentComponentSubgraph, weight="distance"))

            if self.params["ADVANCED_INDICATORS"]["CLOSENESS"] == True:
                closenessValues = dict(nx.closeness_centrality(currentComponentSubgraph, distance="distance"))
            
            if self.params["ADVANCED_INDICATORS"]["DEGREE_CENTRALITY"] == True:
                degreeCentrality = dict(nx.degree_centrality(currentComponentSubgraph))
            
            if self.params["ADVANCED_INDICATORS"]["DIAMETER"] == True:
                eccentricities = dict( nx.eccentricity(currentComponentSubgraph, weight="distance"))
                componentDiameter = nx.diameter(currentComponentSubgraph, e=eccentricities, weight="distance")
            
            if self.params["ADVANCED_INDICATORS"]["ECCENTRICITY"] == True:
                if eccentricities is None:
                    eccentricities = dict( nx.eccentricity(currentComponentSubgraph, weight="distance"))
            
           
            # first iteration: determine component-level and advanced metrics     
            for nodeSiacId in currentComponentNodes:
                totalCapacity += self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)].nodes[nodeSiacId]['capacity']
            setOfComponentCapacities.append(totalCapacity)
                
            
            # iteration: determine other metrics and include writing of component-level indicators
            for nodeSiacId in currentComponentNodes:                                
                mappedFeatureId = self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)].nodes[nodeSiacId]['fid'] 
                currentComponentFeatureIds.append(mappedFeatureId)
                canopyFeatureUpdateMap[mappedFeatureId] = {}

                # prepare update of component id                 
                canopyFeatureUpdateMap[mappedFeatureId][idxCanopyLayerComponentIdField] = currentComponentId
                
                # determine number of links (edges in the graph)
                nodeEdges = self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)].edges(nodeSiacId, True) # get edges for node, and include node attributes (distance)
                canopyFeatureUpdateMap[mappedFeatureId][idxCanopyLayerNeighbourCountField] = len(nodeEdges)
                setOfPatchLinks.append(len(nodeEdges))

                # number of patches in component
                canopyFeatureUpdateMap[mappedFeatureId][idxCanopyLayerNumberOfPatchesField] = len(currentComponentNodes)
                
                # CPL of patch
                distVals = []
                for edge in nodeEdges:
                    distVals.append(edge[2]['distance'])                    
                patchCplValue =  stats.mean(distVals) if len(distVals) > 0 else 0                
                canopyFeatureUpdateMap[mappedFeatureId][idxCanopyLayerMeanDistanceField] = patchCplValue 
                setOfPatchCPL.append(patchCplValue)

                # patch capacity
                patchCapacityValue = self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)].nodes[nodeSiacId]['capacity'] #cacheOfCanopyFeatures.LayerCache[mappedFeatureId][SiacField.RELEVANT_FEATURE_AREA.value]
                setOfPatchCapacities.append(patchCapacityValue)
                canopyFeatureUpdateMap[mappedFeatureId][idxCanopyLayerPatchCapacityField] = patchCapacityValue

                # component capacity
                canopyFeatureUpdateMap[mappedFeatureId][idxCanopyLayerComponentCapacityField] = totalCapacity

                if self.params["ADVANCED_INDICATORS"]["BETWEENNESS"] == True:
                    canopyFeatureUpdateMap[mappedFeatureId][idxCanopyLayerBetweennessCentralityField] = betweennessCentralities[nodeSiacId]
                if self.params["ADVANCED_INDICATORS"]["CLOSENESS"] == True:
                    canopyFeatureUpdateMap[mappedFeatureId][idxCanopyLayerClosenessCentralityField] = closenessValues[nodeSiacId]
                if self.params["ADVANCED_INDICATORS"]["DEGREE_CENTRALITY"] == True:
                    canopyFeatureUpdateMap[mappedFeatureId][idxCanopyLayerDegreeField] = degreeCentrality[nodeSiacId]
                if self.params["ADVANCED_INDICATORS"]["DIAMETER"] == True:
                    canopyFeatureUpdateMap[mappedFeatureId][idxCanopyLayerDiameterField] = componentDiameter
                if self.params["ADVANCED_INDICATORS"]["ECCENTRICITY"] == True:
                    canopyFeatureUpdateMap[mappedFeatureId][idxCanopyLayerEccentricityField] = eccentricities[nodeSiacId]

                processedNodes += 1
                self.setProgress( (processedNodes/totalNumberOfNodes)*100 )  
                
        # do we have articulation points and bridges?
        try:
            for ap in nx.articulation_points(self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)]):
                mappedNodeId = self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)].nodes[ap]['fid']
                canopyFeatureUpdateMap[mappedNodeId][idxCanopyLayerArticulationPointField] = 1
        except:
            pass
        
        # iterate over all bridges and mark their nodes as IS_BRIDGE=1
        try:
            for bridge in nx.bridges(self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)]):
                
                bridgeSourceId = bridge[0]
                bridgeTargetId = bridge[1]

                shortestLineId = self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)].edges[bridgeSourceId, bridgeTargetId]['lineId']
                edgesFeatureUpdateMap[shortestLineId] = { idxEdgeLayerBridgeField : 1 }
            
                mappedSourceFeatureId = self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)].nodes[bridgeSourceId]['fid']
                mappedTargetFeatureId = self.params['results'][SiacToolkitDataType.GRAPH][str(distVal)].nodes[bridgeTargetId]['fid']
                canopyFeatureUpdateMap[mappedSourceFeatureId][idxCanopyLayerBridgeNodeField] = 1
                canopyFeatureUpdateMap[mappedTargetFeatureId][idxCanopyLayerBridgeNodeField] = 1

        except:
            pass
       
        # update features
        self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.dataProvider().changeAttributeValues(canopyFeatureUpdateMap)
        self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource.dataProvider().changeAttributeValues(edgesFeatureUpdateMap)

        # commit changes and stop editing session
        self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.commitChanges()
        self.params['results'][DataLayer.CONNECTIVITY_EDGES].LayerSource.commitChanges()
        
        # also create a node layer for visualization purposes
        keepFields = [ SiacField.CONNECTIVITY_IS_BRIDGE.value, SiacField.CONNECTIVITY_CANOPY_CAPACITY.value, SiacField.CONNECTIVITY_CANOPY_CPL.value, SiacField.CONNECTIVITY_CANOPY_LNK.value, SiacField.CONNECTIVITY_CLOSENESS_CENTRALITY.value, SiacField.CONNECTIVITY_COMPONENT_CAPACITY.value, SiacField.CONNECTIVITY_COMPONENT_DIAMETER.value, SiacField.CONNECTIVITY_COMPONENT_ID.value, SiacField.CONNECTIVITY_COMPONENT_NK.value, SiacField.CONNECTIVITY_DEGREE_CENTRALITY.value, SiacField.CONNECTIVITY_ECCENTRICITY.value, SiacField.UID_CANOPY.value, SiacField.CONNECTIVITY_BETWEENNESS_CENTRALITY.value, SiacField.CONNECTIVITY_IS_ARTICULATION_POINT.value ]
        self.siacToolProgressMessage.emit("Computing Nodes from Canopies", Qgis.Info) 
        nodeLayer = processing.run("native:centroids", { 'INPUT': self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource, 'OUTPUT':'TEMPORARY_OUTPUT'})
        cleanNodeLayer = LayerHelper.removeFieldsFromLayer(nodeLayer['OUTPUT'], fieldsToRetain=keepFields)
        
        nodeDs = SiacDataStoreLayerSource.makeNewDataStoreLayerSourceItem(cleanNodeLayer, DataLayer.CONNECTIVITY_NODES.value, DataLayer.CONNECTIVITY_NODES.value, None)
        nodeDs.SetTouched()        
        self.params['results'][DataLayer.CONNECTIVITY_NODES] = nodeDs

        # number of components
        componentsCount = currentComponentId # id was increased in the iteration above; we can re-use this here

        # produce summaries and parameters
        self.params['results']['REPORT'].append('Buildings {}act as barrier'.format( "" if self.params['BUILDINGS_AS_BARRIERS'] == True else "do not " ))
        self.params['results']['REPORT'].append('The connectivity threshold has been set at {:0.2f}m'.format(self.params['CONNECTIVITY_THRESHOLD']))
        self.params['results']['REPORT'].append("\n\nThe total number of patches (tree canopies and potential ancillary types) is estimated at {:0.0f}".format( self.params['results'][DataLayer.CONNECTIVITY_BASE_LAYER].LayerSource.featureCount()))
        self.params['results']['REPORT'].append("The minimum patch capacity is estimated at {:0.2f}m²".format(min(setOfPatchCapacities)))
        self.params['results']['REPORT'].append("The mean patch capacity is estimated at {:0.2f}m²".format(stats.mean(setOfPatchCapacities)))
        self.params['results']['REPORT'].append("The maximum patch capacity is estimated at {:0.2f}m²".format(max(setOfPatchCapacities)))
        self.params['results']['REPORT'].append("The mean characteristic path length (CPL), averaged across all patches, is estimated at {:0.2f}m, with a sample standard deviation of {:0.2f}m".format(stats.mean(setOfPatchCPL), stats.stdev(setOfPatchCPL)))
        self.params['results']['REPORT'].append("The minimum number of links is estimated at {:0.0f}".format(min(setOfPatchLinks)))
        self.params['results']['REPORT'].append("The average number of links is estimated at {:0.0f}".format(stats.mean(setOfPatchLinks)))
        self.params['results']['REPORT'].append("The maximum number of links is estimated at {:0.0f}".format(max(setOfPatchLinks)))        
        self.params['results']['REPORT'].append('The total number of components is estimated at {:0.0f}'.format(componentsCount))
        self.params['results']['REPORT'].append('The size of the smallest components is estimated at {:0.2f}m²'.format( min(setOfComponentCapacities) ))
        self.params['results']['REPORT'].append('The mean size of the components is estimated at {:0.2f}m²'.format( stats.mean(setOfComponentCapacities) ))
        self.params['results']['REPORT'].append('The size of the largest component is estimated at {:0.2f}m²'.format( max(setOfComponentCapacities) ))
