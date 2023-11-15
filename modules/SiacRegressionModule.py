import statistics as sts
from sklearn import linear_model
from sklearn.linear_model import Ridge
import statsmodels.api as sm
from typing import Iterable, Dict, Tuple
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt


from .SiacEnumerations import *

class LocalRegressionParameters:
    _DataFrame = None
    _IndependentVariables = None
    _DependentVariable = None
    _PlotDefinitions = None
    _Summary = None
    _Plots = None
    _ParticipatingEntityTypes = None
    _IncludeLowess = None

    def __init__(self) -> None:
        self._ParticipatingEntityTypes = []
        self.newModel()

    def newModel(self):
        self._PlotDefinitions = []
        self._IndependentVariables = []
        self._IncludeLowess = False
        self._DependentVariable = None


    @property
    def IncludeLowess(self) -> bool:
        return self._IncludeLowess
    @IncludeLowess.setter
    def IncludeLowess(self, value : bool) -> None:
        self._IncludeLowess = value

    def getRequiredFieldNames(self) -> Iterable[str]:
        result = []
        result.append(self.DependentVariable)
        for x in self.IndependentVariables:
            result.append(x)
        return result

    @property
    def DataFrame(self) -> pd.DataFrame:
        return self._DataFrame
    @DataFrame.setter
    def DataFrame(self, value : pd.DataFrame) -> None:
        self._DataFrame = value

    @property
    def IndependentVariables(self) -> Iterable[str]:
        return self._IndependentVariables
    @IndependentVariables.setter
    def IndependentVariables(self, value : Iterable[str]) -> None:
        self._IndependentVariables = value

    @property
    def DependentVariable(self) -> str:
        return self._DependentVariable
    @DependentVariable.setter
    def DependentVariable(self, value : str ) -> None:
        self._DependentVariable = value 

    @property
    def PlotDefinitions(self) -> Iterable[Iterable[Tuple[str,str]]]:
        return self._PlotDefinitions
    @PlotDefinitions.setter
    def PlotDefinitions(self, value : Iterable[Iterable[Tuple[str,str]]]):
        self._PlotDefinitions = value

    @property
    def Plots(self) -> Iterable[any]:
        return self._Plots
    @Plots.setter
    def Plots(self, value : Iterable[any]):
        self._Plots = value

    @property
    def Summary(self) -> str:
        return self._Summary
    @Summary.setter
    def Summary(self, value : str):
        self._Summary = value

    @property
    def ParticipatingEntityTypes(self) -> Iterable[SiacEntity]:
        return self._ParticipatingEntityTypes
    @ParticipatingEntityTypes.setter
    def ParticipatingEntityTypes(self, value : str):
        self._ParticipatingEntityTypes = value

class SiacRegressionModule:

    @staticmethod
    def makeRegressionPlots(regressionOutput : LocalRegressionParameters, includeLowess=False):
        regrPlots = []
        for cFig in regressionOutput.PlotDefinitions:
            
            # each item in plotDefs is an Iterable[Tuple[str,str]]
            fig, axs = plt.subplots(ncols=len(cFig), nrows=1)
            for idx, cPlot in enumerate(cFig):
                g = sns.regplot( x=cPlot[0], y=cPlot[1], data=regressionOutput.DataFrame, ax=axs[idx] if len(cFig) > 1 else axs, scatter_kws={"color": "black", "s" : 7}, line_kws={"color": "red", "lw" : 2} )
                if includeLowess:
                    gg = sns.regplot( x=cPlot[0], y=cPlot[1], data=regressionOutput.DataFrame, ax=axs[idx] if len(cFig) > 1 else axs, scatter_kws={"color": "black", "s" : 7}, line_kws={"color": "black", "lw" : 1}, lowess=True )
            
            regrPlots.append(fig)
        
        return regrPlots

    @staticmethod
    def computeOlsRegression(df : pd.DataFrame, listOfIndependentVariableNames : Iterable[str], dependenVariableName : str):
        
            independentVariables = df[listOfIndependentVariableNames]
            dependentVariable = df[dependenVariableName]

            # with statsmodels
            independentVariables = sm.add_constant(independentVariables) # adding a constant
            model = sm.OLS(dependentVariable, independentVariables).fit()

            return model
            