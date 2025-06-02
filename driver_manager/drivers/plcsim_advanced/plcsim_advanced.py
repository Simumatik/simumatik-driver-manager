# Simumatik Gateway - Simumatik 3rd party integration tool
# Copyright (C) 2021 Simumatik AB
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import sys 
import os
import multiprocessing

from ..driver import driver, VariableQuality, VariableOperation, DriverStatus

try:
    if os.name == 'nt':# Just try on windows
        import clr
        if getattr(sys, 'frozen', False):
            p = os.path.dirname(sys.executable)
        else:
            p = os.path.dirname(os.path.abspath(__file__))
        sys.path.append(p)
        if sys.maxsize > 2**32: # 64-Bit OS
            clr.FindAssembly("Siemens.Simatic.Simulation.Runtime.Api.x64")
            clr.AddReference("Siemens.Simatic.Simulation.Runtime.Api.x64")
        else: # 32-Bit OS
            clr.FindAssembly("Siemens.Simatic.Simulation.Runtime.Api.x86")
            clr.AddReference("Siemens.Simatic.Simulation.Runtime.Api.x86")
        from Siemens.Simatic.Simulation.Runtime import SimulationRuntimeManager, SDataValue, SDataValueByName, EPrimitiveDataType, ETagListDetails
except:
    pass

class plcsim_advanced(driver):
    '''
    Driver that can be used together with a local PLCSim Advanced Instance, using the Simulation Runtime API.
    Parameters:
    instanceName : The name of the PLC Sim Advanced Instance
    HMIVisibleTagsOnly (bool): Browse HMI visible tags only. Default True
    '''

    def __init__(self, name: str, pipe: multiprocessing.Pipe = None, params:dict = None):
        """
        :param name: (optional) Name for the driver
        :param pipe: (optional) Pipe used to communicate with the driver thread. See gateway.py
        """
        # Inherit
        driver.__init__(self, name, pipe, params)
        # Parameters
        self.instanceName = "s7-1500"
        self.HMIVisibleTagsOnly = True
        
    def connect(self) -> bool:
        """ Connect driver.
        
        : returns: True if connection established False if not
        """
        # Make sure to send a debug message if method returns False
        # self.sendDebugInfo('Error message here') 
        try:
            if SimulationRuntimeManager.RegisteredInstanceInfo.Length > 0:
                for instance in SimulationRuntimeManager.RegisteredInstanceInfo:
                    if instance.Name == self.instanceName:
                        self._connection = SimulationRuntimeManager.CreateInterface(self.instanceName)
                        self._connection.UpdateTagList(ETagListDetails.IO, True) # This is to make sure the connection is valid
                        return True
                self.sendDebugInfo(f"No PLC Sim Advanced instance with name {self.instanceName} found")
            else: 
                self.sendDebugInfo("No PLC Sim Advanced instance running")
        except Exception as e:
            self.sendDebugInfo(f"Connection failed, {e}")
        return False

    def disconnect(self):
        """ Disconnect driver.
        """
        pass

    def addVariables(self, variables: dict):
        """ Add variables to the driver. Correctly added variables will be added to internal dictionary 'variables'.
        Any error adding a variable should be communicated to the server using sendDebugInfo() method.
        : param variables: Variables to add in a dict following the setup format. (See documentation) 
        
        """
        self._connection.UpdateTagList(ETagListDetails.IOMCTDB, self.HMIVisibleTagsOnly) # Update all IO, M, CT and DB.
        for var_id in list(variables.keys()):
            try:
                var_data = dict(variables[var_id])
                var_data['SDataValueByName'] = SDataValueByName()
                var_data['SDataValueByName'].Name = var_id
                var_data['SDataValueByName'].DataValue = self._connection.Read(var_data['SDataValueByName'].Name)
                var_data['PrimitiveDataType'] = var_data['SDataValueByName'].DataValue.Type
                if var_data['operation'] == VariableOperation.READ:
                    var_data['value'] = None # Force first update
                else:
                    var_data['value'] = self.defaultVariableValue(var_data['datatype'], var_data['size'])
                self.variables[var_id] = var_data
            except Exception as e:
                self.sendDebugVarInfo(('SETUP: Bad variable definition: {}'.format(var_id), var_id))
    
    def readVariables(self, variables: list) -> list:
        """ Read given variable values. In case that the read is not possible or generates an error BAD quality should be returned.
        : param variables: List of variable ids to be read. 
        : returns: list of tupples including (var_id, var_value, VariableQuality)
        """
        signals = []
        res = []
        try:
            for var_id in variables:
                signals.append(self.variables[var_id]['SDataValueByName'])
            signals = self._connection.ReadSignals(signals)
            for signal in signals:
                var_id = signal.Name
                if signal.DataValue.Type == EPrimitiveDataType.Bool:
                    value = signal.DataValue.Bool
                elif signal.DataValue.Type == EPrimitiveDataType.Int8:
                    value = signal.DataValue.Int8
                elif signal.DataValue.Type == EPrimitiveDataType.Int16:
                    value = signal.DataValue.Int16
                elif signal.DataValue.Type == EPrimitiveDataType.Int32:
                    value = signal.DataValue.Int32
                elif signal.DataValue.Type == EPrimitiveDataType.Int64:
                    value = signal.DataValue.Int64
                elif signal.DataValue.Type == EPrimitiveDataType.UInt8:
                    value = signal.DataValue.UInt8
                elif signal.DataValue.Type == EPrimitiveDataType.UInt16:
                    value = signal.DataValue.UInt16
                elif signal.DataValue.Type == EPrimitiveDataType.UInt32:
                    value = signal.DataValue.UInt32
                elif signal.DataValue.Type == EPrimitiveDataType.UInt64:
                    value = signal.DataValue.UInt64
                elif signal.DataValue.Type == EPrimitiveDataType.Float:
                    value = signal.DataValue.Float
                elif signal.DataValue.Type == EPrimitiveDataType.Double:
                    value = signal.DataValue.Double
                elif signal.DataValue.Type == EPrimitiveDataType.Char:
                    value = signal.DataValue.Char
                res.append((var_id, value, VariableQuality.GOOD))  
        except Exception as e:
            if "NotUpToDate" in e.Message:
                self.changeStatus(DriverStatus.ERROR)
            res = []
            for var_id in variables:
                res.append((var_id, None, VariableQuality.BAD))
        return res

    def writeVariables(self, variables: list) -> list:
        """ Write given variable values. In case that the write is not possible or generates an error BAD quality should be returned.
        : param variables: List of tupples with variable ids and the values to be written (var_id, var_value). 
        : returns: list of tupples including (var_id, var_value, VariableQuality)
        """
        res = []
        signals = []
        for (var_id, value) in variables:
            try:
                sdatavalue = SDataValue()
                sdatavalue.Type = self.variables[var_id]['PrimitiveDataType']
                if sdatavalue.Type == EPrimitiveDataType.Bool:
                    sdatavalue.Bool = bool(value)
                elif sdatavalue.Type == EPrimitiveDataType.Int8:
                    sdatavalue.Int8 = value
                elif sdatavalue.Type == EPrimitiveDataType.Int16:
                    sdatavalue.Int16 = value
                elif sdatavalue.Type == EPrimitiveDataType.Int32:
                    sdatavalue.Int32 = value
                elif sdatavalue.Type == EPrimitiveDataType.Int64:
                    sdatavalue.Int64 = value
                elif sdatavalue.Type == EPrimitiveDataType.UInt8:
                    sdatavalue.UInt8 = value    
                elif sdatavalue.Type == EPrimitiveDataType.UInt16:
                    sdatavalue.UInt16 = value
                elif sdatavalue.Type == EPrimitiveDataType.UInt32:
                    sdatavalue.UInt32 = value
                elif sdatavalue.Type == EPrimitiveDataType.UInt64:
                    sdatavalue.UInt64 = value
                elif sdatavalue.Type == EPrimitiveDataType.Float:
                    sdatavalue.Float = value  
                elif sdatavalue.Type == EPrimitiveDataType.Double:
                    sdatavalue.Double = value    
                elif sdatavalue.Type== EPrimitiveDataType.Char:
                    sdatavalue.Char = value
                self.variables[var_id]['SDataValueByName'].DataValue = sdatavalue
                signals.append(self.variables[var_id]['SDataValueByName'])     
            except Exception as e:
                res.append((var_id, None, VariableQuality.BAD))
            else:
                res.append((var_id, value, VariableQuality.GOOD))  
        try:
            self._connection.WriteSignals(signals)
        except Exception as e:
            if "NotUpToDate" in e.Message:
                self.changeStatus(DriverStatus.ERROR)
            res = []
            for var_id in variables:
                res.append((var_id, None, VariableQuality.BAD))
        return res
