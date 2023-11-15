from qgis.core import *
from qgis.gui import QgsMessageBar, QgsMapLayerComboBox, QgsFieldComboBox
from qgis.PyQt.QtCore import Qt, QThread, QSettings, QTranslator, QCoreApplication, QVariant, pyqtSignal, QAbstractTableModel
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QErrorMessage, QAction, QMessageBox, QProgressBar
import processing
import pandas as pd
import geopandas as geopd

import math
from .SiacEnumerations import *
from collections import Counter
from .SiacFoundation import LayerHelper

class TreeRichnessAndDiversityAssessmentResult:

    _LocalListOfTree = None   
    _FruitTreeCount = None

    def __init__(self) -> None:
        self._LocalListOfTree = {}   
        self._FruitTreeCount = 0

    @property
    def LocalListOfTree(self):
        return self._LocalListOfTree
    
    @LocalListOfTree.setter
    def LocalListOfTree(self, value):
        self._LocalListOfTree = value

    @property
    def TreeCount(self):       
        return sum([x for x in self._LocalListOfTree.values()])
    
    @property 
    def Richness(self):
        return len(self._LocalListOfTree.keys())

    @property
    def LocalSpeciesAsString(self):
        return ";".join(self._LocalListOfTree.keys())
    
    @property
    def LocalSpeciesWithCountsAsString(self):
        result = ""
        for species, countVal in self._LocalListOfTree.items():
            if result != "":
                result += "|"
            result += '{}={}'.format(species, countVal)
        return result

    @property
    def FruitTreeCount(self):
        return self._FruitTreeCount

    @FruitTreeCount.setter
    def FruitTreeCount(self, value):
        self._FruitTreeCount = value

    @property
    def ContainsFruitTreeAsNumeric(self):
        returnValue = 1 if self._FruitTreeCount > 0 else 0
        return returnValue

    @property
    def FruitTreeShare(self):
        localShare = (self._FruitTreeCount/self.TreeCount) if self.TreeCount > 0 else 0
        return localShare 

    def addLocalTree(self, treeSpeciesName, isFruitTree, countVal = 1):
        # add as key, if not yet present, and intialize with the added tree as count value
        countVal = int(countVal)

        if not treeSpeciesName in self._LocalListOfTree.keys():
            self._LocalListOfTree[treeSpeciesName] = countVal
        else:
            # increment tree count by 1
            self._LocalListOfTree[treeSpeciesName] += countVal

        if isFruitTree == True:
            self._FruitTreeCount += countVal



class TreeRichnessAndDiversityAssessment:
    
    # make a class
    params = {}
    globalListOfSpecies = {}
    localAssessments = {}   

    @property
    def SpeciesData(self):
        return self.globalListOfSpecies

    @property
    def Richness(self):
        return len(self.globalListOfSpecies.keys())
    
    @property
    def TreeAbundance(self):
        return sum([x for x in self.globalListOfSpecies.values()])
    
    @property
    def TotalNumberOfFruitTrees(self):
        return sum([x.FruitTreeCount for x in self.localAssessments.values()])

    @property
    def RelativeAbundance(self):
        totalAbundance = self.TreeAbundance
        relativeAbundances = {}
        for species, count in self.globalListOfSpecies.items():
            relativeAbundances[species] = count/totalAbundance
        return relativeAbundances

    @property
    def MenhinickIndex(self):
        return self.Richness / (math.sqrt(self.TreeAbundance))

    @property
    def MargalefIndex(self):
        return ( self.Richness-1) / (math.log(self.TreeAbundance))

    @property
    def SimpsonIndex(self):
        # D = sum(pi²)
        return sum([pow(x,2) for x in self.RelativeAbundance.values()])
    @property
    def ComplementedSimpsonIndex(self):
        # 1-D
        return 1-self.SimpsonIndex
    
    @property
    def ShannonWienerDiversityIndex(self):
        # - sum(pi * ln(pi))
        summedExpression = sum([ (x * math.log(x)) for x in self.RelativeAbundance.values() ]) 
        return -1 * summedExpression
        
    @property
    def PielouEvennessIndex(self):
        # https://link.springer.com/chapter/10.1007/978-3-030-22044-0_8
        # H/ln(S)
        return self.ShannonWienerDiversityIndex/math.log(self.Richness)

    @property
    def BrillouinIndex(self):
        # H = 1/N(math.log(N!)-sum(ln(n!)))
        sumExpression = sum([ math.log( math.factorial(x) ) for x in self.globalListOfSpecies.values()])
        return (1/self.TreeAbundance)*( math.log(math.factorial(self.TreeAbundance)) - sumExpression )

    @property
    def ReportMostCommonSpecies(self):
        totalAbundance = self.TreeAbundance
        report = ["\n\nThe five most-common species in the dataset:"]
        k = Counter(self.globalListOfSpecies)
        high = k.most_common(5)
        for species, count in high:
            report.append("{}: {} individuals ({:0.4f}%)".format( species, count, 100*(count/totalAbundance)))
        
        
        return report
    
    @property 
    def TreeAbundanceAsDataFrame(self):
        k = Counter(self.globalListOfSpecies)
        speciesList = k.keys()
        abundance = k.values()
        df = pd.DataFrame({ 'species' : speciesList, 'total' : abundance })
        df['relative'] = df['total']/self.TreeAbundance
        return df

    def __init__(self, treeFeatureCache, speciesAttribute, fruitTreeList):
        
        self.params['TREE_CACHE'] = treeFeatureCache
        self.params['SPECIES_ATTRIBUTE'] = speciesAttribute
        self.params['FRUIT_TREE_LIST'] = fruitTreeList

    def addGlobalTree(self, treeSpeciesName, countVal = 1):
        countVal = int(countVal)
        if not treeSpeciesName in self.globalListOfSpecies.keys():
            self.globalListOfSpecies[treeSpeciesName] = countVal
        else:
            self.globalListOfSpecies[treeSpeciesName] += countVal

    def getSpeciesNameOrNone(self, treeFeature):
        currentSpeciesRawValue = treeFeature[self.params['SPECIES_ATTRIBUTE']]
        if currentSpeciesRawValue != "" and isinstance(currentSpeciesRawValue, str):
            return currentSpeciesRawValue.strip().lower() 
        else:
            return None
        
    def isFruitTree(self, speciesName):
        return any([x in speciesName for x in [x.strip().lower() for x in self.params['FRUIT_TREE_LIST'] ]])
        
    def assessSpatialUnitOfAnalysis(self, unitId, containedTreeFeatures) -> TreeRichnessAndDiversityAssessmentResult:
        
        # results are stored using helper class
        localResult = TreeRichnessAndDiversityAssessmentResult()
        
        # iterate over local trees
        for treeId in containedTreeFeatures:
            currentTreeFeature = self.params['TREE_CACHE'].LayerCache[treeId]
            speciesName = self.getSpeciesNameOrNone(currentTreeFeature)

            if speciesName is not None:
            
                # add to local list, taking care of increments and fruit tree "tracking"
                isFruitTree = self.isFruitTree(speciesName)
                localResult.addLocalTree(speciesName, isFruitTree)
                                    
                # add to global list
                self.addGlobalTree(speciesName)

        # results are stored in dicts using unitId as key
        self.localAssessments[unitId] = localResult
        return localResult
    
    def assessSpatialUnitOfAnalysisByAttributes(self, feature ):
        # results are stored using helper class
        localResult = TreeRichnessAndDiversityAssessmentResult()

        # read tree species count field        
        # this field has the form of speciesname=count|...
        currentSpeciesCountStr : str = feature[SiacField.TREE_SPECIES_COUNTS.value]

        if currentSpeciesCountStr != "":
            for speciesData in currentSpeciesCountStr.split('|'):
                
                splits = speciesData.split('=')
                isFruitTree = self.isFruitTree(splits[0])
                localResult.addLocalTree(splits[0], isFruitTree, countVal=splits[1])
            
            # add to global list as well
            self.addGlobalTree(splits[0], countVal=splits[1])

        self.localAssessments[feature.id()] = localResult

    
    def summary(self, returnAsListOfSentences : bool = True):

        report = []

        # Richness
        report.append("The total species richness is estimated at {}".format( self.Richness ))
        # Menhinick's index: richness / sqrt(abundance)           
        report.append("Menhinick's index is estimated at {:0.5f}".format( self.MenhinickIndex))            
        # Margalef's index: (richness - 1) / ln(abundance)          
        report.append("Margalef's index is estimated at {:0.5f}".format(self.MargalefIndex))
        # Simpsons's index
        report.append("Simpson's index (1-D) is estimated at {:0.5f}".format(self.ComplementedSimpsonIndex))
        # Brillouin index
        report.append("Brillouin index H is estimated at {:0.5f}".format(self.BrillouinIndex))
        # Shannon-Weiner-Index
        report.append("Shannon–Wiener Diversity Index H' is estimated at {:0.5f}".format(self.ShannonWienerDiversityIndex))
        # Pielou index
        report.append("Pielou Evenness Index J' is estimated at {:0.5f}".format(self.PielouEvennessIndex))
        
        # apend relative abundances as text: most common species
        relativeAbundances = self.ReportMostCommonSpecies
        for relAb in relativeAbundances:
            report.append(relAb)

        return report if returnAsListOfSentences == True else '.'.join(report) 