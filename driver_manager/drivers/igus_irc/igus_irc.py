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

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from .cri_lib import CRIController
from ..driver import driver, VariableQuality, VariableOperation

class igus_irc(driver):
    '''
    This driver uses the RoboDK API to connect to a robot controller. It is based on the Robodk API (https://robodk.com/offline-programming).
    
    The driver will always provide access to the robot axis through the variable called "Axis" (float[6]).
    Optional variable definitions are used to access Station Parameters in RobotDK to be read or written by the driver.

    Parameters:
    
    controller: str
        Robot name in RoboDK. Default = '', will take the first that founds.

    ip: str
        IP address of the PC running the RoboDK simulation. Default = 'localhost'
    
    port: int
        Port looking for the RoboDK API connection (Tools-Options-Other-RoboDK API). Default = None
    '''

    def __init__(self, name: str, pipe: multiprocessing.Pipe = None, params:dict = None):
        """
        :param name: (optional) Name for the driver
        :param pipe: (optional) Pipe used to communicate with the driver thread. See gateway.py
        """
        # Inherit
        driver.__init__(self, name, pipe, params)

        # Parameters
        self.controller = ''
        self.ip = '127.0.0.1'
        self.port = 3921


    def connect(self) -> bool:
        """ Connect driver.
        
        : returns: True if connection established False if not
        """
        try:
            #assert ROBODK_API_FOUND, "RoboDK API is not available."
            self._connection = CRIController()
            if self._connection.connect(self.ip, self.port):
                return True
            else:
                self.sendDebugInfo(f'Connection with Igus iRC not possible.')

        except Exception as e:
            self.sendDebugInfo('Exception '+str(e))
        
        return False

    def disconnect(self):
        """ Disconnect driver.
        """
        if self._connection:
            self._connection.close()


    def addVariables(self, variables: dict):
        """ Add variables to the driver. Correctly added variables will be added to internal dictionary 'variables'.
        Any error adding a variable should be communicated to the server using sendDebugInfo() method.

        : param variables: Variables to add in a dict following the setup format. (See documentation) 
        
        """
        for var_id, var_data in variables.items():
            try:
                if var_id == 'Axis':
                    var_data['value'] = [None for i in range(var_data['size'])]
                    self.variables[var_id] = var_data
                elif var_id[:4] in ["GSig", "DOut"] or var_id[:3]=="DIn":
                    if var_id[:4] =="GSig":
                        number = int(var_id[4:])-1
                        assert 0<=number<=99
                        if var_data['operation'] == VariableOperation.READ:
                            var_data['value'] = None
                        else:
                            var_data['value'] = self._connection.robot_state.global_signals[number]
                    else:
                        if var_id[:4] =="DOut":
                            number = int(var_id[4:])-1
                            assert 0<=number<=63
                            var_data['value'] = None
                        else:
                            number = int(var_id[3:])-1
                            assert 0<=number<=63
                            var_data['value'] = self._connection.robot_state.din[number]
                    self.variables[var_id] = var_data
                    self.sendDebugVarInfo((f'SETUP: Variable found {var_id}', var_id))
            except:
                self.sendDebugVarInfo((f'SETUP: Variable not found {var_id}', var_id))


    def readVariables(self, variables: list) -> list:
        """ Read given variable values. In case that the read is not possible or generates an error BAD quality should be returned.
        : param variables: List of variable ids to be read. 

        : returns: list of tupples including (var_id, var_value, VariableQuality)
        """
        res = []
        for var_id in variables:
            try:
                if var_id == 'Axis':
                    new_value = self._connection.robot_state.joints_current # robot joint rotations [Rax_1, Rax_2, Rax_3, Rax_4, Rax_5, Rax_6]
                    new_value = [round(x,3) for x in [new_value.A1, new_value.A2, new_value.A3, new_value.A4, new_value.A5, new_value.A6]]
                    res.append((var_id, new_value, VariableQuality.GOOD))
                elif var_id[:4] == "DOut":
                    number = int(var_id[4:])-1
                    new_value = self._connection.robot_state.dout[number]
                    res.append((var_id, new_value, VariableQuality.GOOD))
                elif var_id[:4] == "GSig":
                    number = int(var_id[4:])-1
                    new_value = self._connection.robot_state.global_signals[number]
                    res.append((var_id, new_value, VariableQuality.GOOD))
            except:
                res.append((var_id, self.variables[var_id]['value'], VariableQuality.BAD))
            
        return res


    def writeVariables(self, variables: list) -> list:
        """ Write given variable values. In case that the write is not possible or generates an error BAD quality should be returned.
        : param variables: List of tupples with variable ids and the values to be written (var_id, var_value). 

        : returns: list of tupples including (var_id, var_value, VariableQuality)
        """
        res = []
        for (var_id, new_value) in variables:
            try:
                if var_id[:3] == "DIn":
                    number = int(var_id[3:])-1
                    print("write", var_id, new_value)
                    self._connection.set_din(number,new_value)
                    res.append((var_id, new_value, VariableQuality.GOOD))
                elif var_id[:4] == "GSig":
                    number = int(var_id[4:])-1
                    self._connection.set_global_signal(number,new_value)
                    res.append((var_id, new_value, VariableQuality.GOOD))
            except Exception as e:
                res.append((var_id, new_value, VariableQuality.BAD))
                     
        return res
