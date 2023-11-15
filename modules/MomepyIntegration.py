import momepy
import geopandas as gpd

# Momepy integration
class MomepyHelper:

    @staticmethod
    def sourceToTargetId(gdfTopologySource, gdfTopologyTarget, topologySourceIdFieldName, topologyTargetUniqueIdFieldName, min_size ):   
        resultLayer = gdfTopologySource.copy(deep = True)     
        resultLayer[topologySourceIdFieldName] = momepy.get_network_id( resultLayer, gdfTopologyTarget, topologyTargetUniqueIdFieldName, min_size )        
        return resultLayer

    @staticmethod
    def determineStreetProfile(gdfStreetLayer, gdfBuildingLayer, maximumStreetWidth, heightAttribute):
        street_profile = momepy.StreetProfile(gdfStreetLayer, gdfBuildingLayer, tick_length = maximumStreetWidth, heights=heightAttribute)
        gdfStreetLayer['width'] = street_profile.w
        gdfStreetLayer['widthDeviation'] = street_profile.wd
        gdfStreetLayer['openness'] = street_profile.o
        return gdfStreetLayer

    @staticmethod
    def morphologicalTessellation(gdfBuildingLayer, uniqueIdFieldName, limitingDistance):
        limit = momepy.buffered_limit(gdfBuildingLayer, buffer=limitingDistance)
        tessellation = momepy.Tessellation(gdfBuildingLayer, unique_id=uniqueIdFieldName, limit=limit)
        tessellation_gdf = tessellation.tessellation
        return tessellation_gdf

    @staticmethod
    def enclosedTessellation(gdfBuildingLayer, gdfStreetLayer, uniqueIdFieldName, useConvexHull=True, limitingDistance=250 ):
        
        limit = None
        if useConvexHull:
            convex_hull = gdfStreetLayer.unary_union.convex_hull
            limit = gpd.GeoSeries([convex_hull])
        else:
            limit = momepy.buffered_limit(gdfBuildingLayer, buffer=limitingDistance)
                
        enclosures = momepy.enclosures(gdfStreetLayer, limit=limit) #, additional_barriers=[railway, rivers])
        enclosed_tessellation = momepy.Tessellation(gdfBuildingLayer, unique_id=uniqueIdFieldName, enclosures=enclosures, use_dask=False)
        enclosed_tessellation_gdf = enclosed_tessellation.tessellation
        return enclosed_tessellation_gdf