from qgis.core import *
from qgis.gui import QgsMessageBar, QgsMapLayerComboBox, QgsFieldComboBox
from qgis.PyQt.QtCore import Qt, QThread, QSettings, QTranslator, QCoreApplication, QVariant, pyqtSignal, QAbstractTableModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QErrorMessage, QAction, QMessageBox, QProgressBar
import processing
import pandas as pd
import geopandas as geopd
from typing import Iterable
from collections import namedtuple

from .SiacEnumerations import *

class CachedLayerItem:
    
    _ItemType = None
    _SpatialIndex = None
    _LayerCache = None
    _AttributeToIdMapping = None
    _Crs = None    
    _GeometryType = None

    def __init__(self, type) -> None:
        self._ItemType = type      

    @property
    def GeometryType(self) -> str:
        
        if self._GeometryType == 0:
            return "point"
        if self._GeometryType == 2:
            return "polygon"
        
        return None
    
    @GeometryType.setter
    def GeometryType(self, value):
        self._GeometryType = value

    @property
    def Crs(self):
        return self._Crs

    @Crs.setter
    def Crs(self, value):
        self._Crs = value

    @property
    def ItemType(self):
        return self._ItemType
    
    @ItemType.setter
    def ItemType(self, value):
        self._ItemType = value

    @property
    def SpatialIndex(self):
        return self._SpatialIndex
    
    @SpatialIndex.setter
    def SpatialIndex(self, value):
        self._SpatialIndex = value

    @property
    def LayerCache(self):
        return self._LayerCache

    @LayerCache.setter
    def LayerCache(self, value):
        self._LayerCache = value

    @property
    def AttributeToIdMapping(self):
        return self._AttributeToIdMapping

    @AttributeToIdMapping.setter
    def AttributeToIdMapping(self, value):
        self._AttributeToIdMapping = value

    def getFeaturesFromCache(self, ids):
        featureSet = []
        for id in ids:
            featureSet.append(self._LayerCache[id])
        return featureSet
    
    def getFeaturesFromCacheInGeometry(self, srcGeometry, topologicalRelationship : TopologyRule ):
        intersectingIds = SelectionHelper.getIntersectingFeatureIds(srcGeometry, self, topologicalRelationship)
        features = self.getFeaturesFromCache(intersectingIds)
        return features
    
class FeatureCache:

    @staticmethod
    def layerToCache(layer : object, type : DataLayer, mapIdToAttribute = None, ancillaryType : SiacEntity = None) -> CachedLayerItem:
        
        # create object
        tmp = CachedLayerItem(type)        
        tmp.SpatialIndex = QgsSpatialIndex(layer.getFeatures(), flags=QgsSpatialIndex.FlagStoreFeatureGeometries)   
                      
        # build feature cache to quick-access indexed features
        tmp.LayerCache = { feature.id() : feature for (feature) in layer.getFeatures()}    
        tmp.Crs = layer.crs().authid().split(":")[1]
        tmp.GeometryType = layer.geometryType()

        if mapIdToAttribute is not None:
            QgsMessageLog.logMessage("Creating CachedLayerItem with field {} mapped to Feature Id".format(mapIdToAttribute), "SIAC", Qgis.MessageLevel.Info)
            mappedAttrib = {}
            for feat in layer.getFeatures():
                mappedAttrib[str(feat[mapIdToAttribute])] = feat.id()
            tmp.AttributeToIdMapping = mappedAttrib
               
        # return build cache
        return tmp

    def __init__(self) -> None:
        self.cache = {}


    def getFromCache(self, type : DataLayer) -> CachedLayerItem:
        if type in self.cache:
            return self.cache[type]
        else:
            return None


    def isCached(self, type : DataLayer) -> bool:
        if type in self.cache:
            return True
        else:
            return False


    def cacheLayer(self, layer : object, type : DataLayer, mapIdToAttribute = None, ancillaryType : SiacEntity = None) -> CachedLayerItem:        
        tmp = FeatureCache.layerToCache(layer, type, mapIdToAttribute=mapIdToAttribute, ancillaryType=ancillaryType)        
        # insert into cache
        self.cache[type] = tmp        
        # return CachedLayerItem
        return tmp





class Utilities:
    @staticmethod
    def is_float(element: any) -> bool:
        #If you expect None to be passed:
        if element is None: 
            return False
        try:
            float(element)
            return True
        except ValueError:
            return False


class SelectionHelper:

    ######################################
    #
    # Return feature ids of those features from an index that intersect / touch / etc. a specific geometry
    # TODO: Consider adding a QgsGeometryEngine for faster execution
    # # https://gis.stackexchange.com/questions/419308/how-to-speed-up-pyqgis-code-for-finding-intersection-of-features-in-the-same-lay
    # # https://stackoverflow.com/questions/41717156/qgis-select-polygons-which-intersect-points-with-python
    ######################################
    @staticmethod
    def getIntersectingFeatureIds(srcGeometry : QgsGeometry, cacheItem : CachedLayerItem, topologicalRelationship : TopologyRule ) -> Iterable[int]:
        
        featureIndex = cacheItem.SpatialIndex
        featureCache = cacheItem.LayerCache
        
        # determine the ids of those features that intersect the srcGeometry
        intersectingFeatureIds = []

        # identify features in cache that intersect the bounding box of the source feature geometry 
        candidateFeaturesIds = featureIndex.intersects( srcGeometry.boundingBox() )
        
        # for returned feature ids, test more carefully for actual intersection irrespective of only bounding box
        for id in candidateFeaturesIds:
            candidateFeature = featureCache[id]
            candidateGeometry = candidateFeature.geometry()

            topologyIsTrue = False
            if( topologicalRelationship == TopologyRule.CONTAINS):
                topologyIsTrue = srcGeometry.contains(candidateGeometry)

            elif ( topologicalRelationship == TopologyRule.INTERSECTS):
                topologyIsTrue = srcGeometry.intersects(candidateGeometry)
            
            elif ( topologicalRelationship == TopologyRule.TOUCHES):
                topologyIsTrue = srcGeometry.touches(candidateGeometry)
            
            elif( topologicalRelationship == TopologyRule.CROSSES):
                topologyIsTrue = srcGeometry.crosses(candidateGeometry)
            
            elif( topologicalRelationship == TopologyRule.WITHIN):
                topologyIsTrue = srcGeometry.within(candidateGeometry)
            
            # true intersect will result in id being returned 
            if topologyIsTrue == True:
                intersectingFeatureIds.append(candidateFeature.id())


        return intersectingFeatureIds

    

class LayerHelper:

    @staticmethod
    def getFieldIndex(layer, fieldName):
        return layer.fields().indexFromName(fieldName)
    
    # Helper function to remove fields except the ones specified as parameter
    @staticmethod
    def removeFieldsFromLayer(layer, fieldsToRetain = []):
        layerFields = layer.fields()
        fieldsToDelete = []
        for field in [f for f in layerFields if not f.name() in fieldsToRetain]:
            fieldIndex = layerFields.indexFromName(field.name())
            fieldsToDelete.append(fieldIndex)
        
        layer.startEditing()
        layer.deleteAttributes(fieldsToDelete)
        layer.commitChanges()

        return layer

    @staticmethod
    def containsFieldWithName(layer, fieldName):
        hasField = True if fieldName in layer.fields().names() else False
        return hasField

    # Helper function to create an in-memory shape layer
    @staticmethod
    def createTemporaryLayer(DestCrs, LayerName, GeometryType):
        return QgsVectorLayer('%s?crs=epsg:%s' % (GeometryType, DestCrs), LayerName, "memory")

    # Clone layer
    def copyLayer(layer):        
        
        layer.selectAll()
        clone_layer = processing.run("native:saveselectedfeatures", {'INPUT': layer, 'OUTPUT': 'memory:'})['OUTPUT']
        layer.removeSelection()
        return clone_layer


    # Create in-memory layer, and add attributes as required
    @staticmethod
    def createTemporaryLayerAttributes(layer, fields):
        layer.startEditing()        
        if fields is not None:
            layer.dataProvider().addAttributes( fields )
            layer.updateFields()
        layer.commitChanges()
        return layer

    @staticmethod
    def addAttributeToLayer(layer : QgsVectorLayer, fieldName, fieldType, defaultValue = None):
        # if the field does not exist, create. otherwise, we already have a unique id field and should not overwrite that.
        field_index = True if fieldName in layer.fields().names() else False        
        
        if field_index == False and defaultValue is None:
            QgsMessageLog.logMessage("Initializing {} with default value null in layer {}".format(fieldName, layer.name()), "SIAC", Qgis.MessageLevel.Info)
            layer.dataProvider().addAttributes([QgsField(fieldName, fieldType)])
            layer.updateFields()


        if field_index == False and defaultValue is not None:
            QgsMessageLog.logMessage("Initializing {} with default value {} in layer {}".format(fieldName, str(defaultValue), layer.name()), "SIAC", Qgis.MessageLevel.Info)
            
            # use processing for faster performance, hopefully
            # match QVariant to QGIS
            qgsFieldEnum = None
            if fieldType == QVariant.Int:
                qgsFieldEnum = 0
            elif fieldType == QVariant.Double:
                qgsFieldEnum = 1
            elif fieldType == QVariant.String:
                qgsFieldEnum = 2

            tmp = processing.run("qgis:advancedpythonfieldcalculator", {'INPUT': layer,'FIELD_NAME': fieldName,'FIELD_TYPE': qgsFieldEnum,'GLOBAL':'','FORMULA':'value = {}'.format(defaultValue),'OUTPUT':'TEMPORARY_OUTPUT'})
            layer = tmp['OUTPUT']                    

        newFieldIndex = LayerHelper.getFieldIndex(layer, fieldName)

        return layer, newFieldIndex


    @staticmethod
    def createLayerUniqueId(layer : QgsVectorLayer, fieldName):
        QgsMessageLog.logMessage('Adding SIAC ID to layer {}'.format(layer.name()), "SIAC", Qgis.MessageLevel.Info)                            

        # if the field does not exist, create. otherwise, we already have a unique id field and should not overwrite that.
        field_index = True if fieldName in layer.fields().names() else False        
        if field_index == False:            
            # use processing for better performance
            tmp = processing.run("native:addautoincrementalfield", {'INPUT': layer,'FIELD_NAME': fieldName,'START': 991,'MODULUS':0,'GROUP_FIELDS':[],'SORT_EXPRESSION':'','SORT_ASCENDING':True,'SORT_NULLS_FIRST':False,'OUTPUT':'TEMPORARY_OUTPUT'})
            return tmp['OUTPUT']            
        else:
            QgsMessageLog.logMessage("Layer {} has SIAC ID. Skipping initialization of SIAC ID.".format(layer.name()), "SIAC", Qgis.MessageLevel.Warning)

        return layer
    
    @staticmethod
    def convertQgsLayerToDataFrame(featureSet, fields, dropColumns = None):
        df = pd.DataFrame([feat.attributes() for feat in featureSet], columns=[field.name() for field in fields])
        # drop columns, if needed
        if dropColumns is not None:
            df.drop(dropColumns, axis=1, inplace=True)
        return df

    @staticmethod
    def convertQgsLayerToGeoDataFrame(layer, uidFieldName, progressCallback, crs):

        # variables to compute progress        
        processedFeatureCount = 0
        totalFeatureCount = layer.featureCount()

        # create empty pandas df to be converted later
        df = pd.DataFrame(columns = [uidFieldName, 'wkt'])
                        
        # iterate over features and append to geodataframe
        for layerFeature in layer.getFeatures():
            new_row = pd.Series({uidFieldName : layerFeature[uidFieldName], 'wkt' : layerFeature.geometry().asWkt() })
            df = pd.concat([df, new_row.to_frame().T], ignore_index=True)
            
            # report progress
            processedFeatureCount += 1
            progressCallback( (processedFeatureCount/totalFeatureCount)*100 )  
        
        df['geom'] = geopd.GeoSeries.from_wkt(df['wkt'])
        geodf = geopd.GeoDataFrame(df, geometry='geom', crs=crs)
        geodf = geodf.drop(columns=['wkt'])
        
        progressCallback(0)
        return geodf

    @staticmethod
    def convertGeoDataFrameToQgsLayer(geodf, name, crs):
        tmp = QgsVectorLayer( '%s?crs=epsg:%s' % (geodf.to_json(), crs), name, "ogr")
        layerCrs = QgsCoordinateReferenceSystem("EPSG:" + crs)
        tmp.setCrs(layerCrs) # change the coordinate reference system
        return tmp

    @staticmethod
    def getUniqueValuesForField(layer, fieldName):
        res = []
        # iterate over features in layer, obtain value
        for f in layer.getFeatures():
            cval = f[fieldName]
            if not cval in res:
                res.append(cval)
        return res

