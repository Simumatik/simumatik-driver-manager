import time
import multiprocessing
import threading
import copy
import enum 

from driver_manager.drivers import *

VERSION = "2.0.2"

def RunDriverManager(pipe:multiprocessing.Pipe, use_processes:bool=False, status_file_path:str='') -> None:
    _object = DriverManager(use_processes, status_file_path)
    _object.run_forever(pipe)
    
def RunDriver(driver_object:any, name:str, pipe:multiprocessing.Pipe, params:dict) -> None:
    _object = driver_object(name, pipe, params)
    _object.run()

class DriverMgrCommands(str, enum.Enum):
    SETUP_DRIVERS = 'SETUP_DRIVERS'
    CLEAN = 'CLEAN'
    UPDATES = 'UPDATES'
    STATUS = 'STATUS'
    INFO = 'INFO'
    VAR_INFO = 'VAR_INFO'
    STATS = 'STATS'

class DriverStructure():
    
    def __init__(self, class_name:str, driver_name:str, handle:str, parameters:dict, pipe:multiprocessing.Pipe, driver_process:any):
        self.class_name = class_name
        self.name = driver_name
        self.handlers = [handle]
        self.parameters = parameters
        self.variables = {}
        self.status = ""
        self.info = ""
        self.info_log = []
        self.latency = ""
        self.pipe = pipe
        self.process = driver_process
        self.updates = {}
        
    def add_handle(self, handle:str):
        self.handlers.append(handle)
    
    def is_compatible(self, driver_data: dict) -> bool:
        """ Tells if the driver is compatible with the given class and setup parameters. 

        :param driver_data: Driver setup data, including parameters. (See documentation)

        :returns: True if compatible or False if not
        """
        driver_class_name = driver_data.get("DRIVER", "None")
        setup_data = driver_data.get("SETUP", {})
        parameters = setup_data.get("parameters", None)
        if self.class_name == driver_class_name:
            for key, value in parameters.items():
                if key in self.parameters:
                    if self.parameters[key] != value:
                        return False
            return True
        return False

    def add_driver_variables(self, variables:dict) -> dict:
        """ Adds variables to the given driver. 
        :param variables: Dictionary with all variables to be added. (See documentation)
        
        :returns: Dictionary with {<var_handle>: (<var_id>, <driver_name>)}
        """          
        res = {}
        var_setup_data = {}
        for var_id, var_data in variables.items(): 
            var_handle = var_data.get('handle', None)
            if var_handle is not None:
                if var_id not in self.variables:
                    var_structure = VariableStructure(var_handle, var_data)
                    self.variables[var_id] = var_structure
                    var_setup_data[var_id] = var_data
                else:
                    # TODO: Consider a variable that already has ben setup but now is the other type (READ/WRITE) so it should be changed to BOTH
                    # An option can be to store the variable operation as well in the self.variables dict ([handles], operation)
                    var_structure = self.variables[var_id] 
                    var_structure.add_handle(var_handle)   
                res[var_handle] = (var_id, self.name)
        if self.pipe and var_setup_data:
            self.pipe.send((DriverActions.ADD_VARIABLES, var_setup_data))
        return res
    
class VariableStructure():
    
    def __init__(self, handle:str, parameters:dict):
        self.handlers = [handle]
        self.parameters = parameters
        self.value = None
        self.info = ''
        self.write_count = 0
        self.read_count = 0

    def add_handle(self, handle:str):
        self.handlers.append(handle)

class DriverManager():
    
    def __init__(self, use_processes:bool=False, status_file_path:str='') -> None:
        """

        :param use_processes: Allows to use processes instead of threads.
            it will have impact in performance and used resources

        :param log_level: Sets the logging level.

        
        """      
        self._logs = []
        self._use_processes = use_processes
        self._status_file_path = status_file_path
        self._drivers = {} # Dict to store drivers: {<driver_name>:<driver_struct>}
        self._driver_counter = 0
        self._handles = {} # Dict to store variables data: {<handle>: (<var_id>, <driver name>)}
        self.log("info", f"Driver Manager: Started v{VERSION}")     
        if self._status_file_path:    
            self.log("info", f"Driver Manager: Status File path is {self._status_file_path}")
        else:
            self.log("info", f"Driver Manager: Status File path not defined.")
        self._running = True
        self._stats_updates = {}
        self._status_updates = {}
        self._info_updates = {}
        self._var_info_updates = {}
        self._value_updates = {}
        self._start_time = int(time.perf_counter())
        self._last_status_record = 0
        self._save_status_time = 0
    
    def log(self, level:str="", message:str=""):
        """
        TODO
        """
        if True:
            self._logs.append((time.perf_counter(), level, message))
    
    def save_status(self, now_sec:int):
        """
        TODO:
        """
        start = time.perf_counter()
        try:
            with open(self._status_file_path, 'w') as f:
                N = 100
                f.write(f'Driver Manager status: (clock = {now_sec}s, {round(self._save_status_time*1000,2)}ms to write)\n')
                f.write('-'*N+'\n')
                for driver_struct in self._drivers.values():
                    f.write(f' {driver_struct.name}:\n') 
                    f.write(f'   - Type = {driver_struct.class_name}, Status = {driver_struct.status.value}\n')
                    f.write(f'   - {driver_struct.latency}\n')
                    f.write(f'   - Info:\n')
                    for info_line in driver_struct.info_log:
                        f.write(f'     * {info_line}\n')
                    f.write(f'   - Parameters = {driver_struct.parameters}\n')
                    f.write(f'   - Handles = {driver_struct.handlers}, Variable count = {len(driver_struct.variables)}\n')
                    f.write(f'   - Variables:\n')
                    for var_id, var_struct in driver_struct.variables.items():
                        f.write(f'    - {var_id} {var_struct.handlers} = {var_struct.value}  (R:{var_struct.read_count} W:{var_struct.write_count}) - {var_struct.info}\n')
                    f.write('-'*N+'\n')
                f.write('\n')
                f.write('Logs: \n')
                old_logs = self._logs[-50:]
                while self._logs:
                    (timestamp, level, message) = self._logs.pop()
                    f.write(f'{round(timestamp,3)} - {level}: {message}\n')
                f.write('-'*N+'\n')
                self._logs = old_logs
        except Exception as e:
            self.log("error", f"Driver Manager: Status file cannot be written, {e}")
        self._save_status_time = time.perf_counter() - start

    def send_command(self, command:DriverMgrCommands, data:any=None)->any:
        """
        :param command: Command sent to the Driver Manager

        :param data: Data related to the command

        :returns: Data returned by the command

        Class to help testing drivers.
        """
        ret_data = None

        if command == DriverMgrCommands.CLEAN:
            self.log("info", "Driver Manager: Clean request received")
            ret_data = "SUCCESS"
            self.clean_drivers()
            self._running = False
        elif command == DriverMgrCommands.SETUP_DRIVERS:
            self.log("info", "Driver Manager: Setup Drivers request received")
            ret_data = self.setup_drivers(data)
        elif command == DriverMgrCommands.UPDATES:
            for var_handle, var_value in data.items():
                (var_id, driver_name) = self._handles.get(var_handle, (None, None))
                if driver_name:
                    if self._drivers[driver_name].status == DriverStatus.RUNNING:
                        if self._drivers[driver_name].variables[var_id].value != var_value:
                            self._drivers[driver_name].updates[var_id] = var_value    
                            self._drivers[driver_name].variables[var_id].write_count += 1
                            self._drivers[driver_name].variables[var_id].value = var_value 
                else:
                    self.log("error", f"Driver Manager: Variable handle not found! {var_handle} value = {var_value}")
            for driver_struct in self._drivers.values():
                if driver_struct.updates:
                    driver_struct.pipe.send((DriverActions.UPDATE, driver_struct.updates))
                    driver_struct.updates = {}
        else:
            self.log("error", f"Driver Manager: Command not implemented!!!! {command}")
        return ret_data
    
    def run_once(self, max_pipe_loops:int=10)->bool:
        """
        Executes the logic once to check if there is any update from a driver.

        :param max_pipe_loops: limits the amount of checks done in each driver pipe to limit the running execution time,

        :returns: True if there is any update data to be retrieved, getUpdates() should be called.
        """
        for driver_struct in self._drivers.values():
            counter = 0
            while driver_struct.pipe.poll():
                (command, data) = driver_struct.pipe.recv()
                if command == DriverActions.STATUS:
                    if driver_struct.status != data:
                        driver_struct.status = data
                        for handle in driver_struct.handlers:
                            self._status_updates.update({handle: data})
                elif command == DriverActions.INFO:
                    if "Latency" in data:
                        driver_struct.latency = data
                    else:
                        driver_struct.info_log.append(data)
                        if len(driver_struct.info_log) > 5: driver_struct.info_log = driver_struct.info_log[-5:]
                        driver_struct.info = data
                        for handle in driver_struct.handlers:
                            self._info_updates.update({handle: data})       
                elif command == DriverActions.VAR_INFO:
                    (msg, var_id) = data
                    var_struct = driver_struct.variables.get(var_id, None)
                    if var_struct is not None:
                        if var_struct.info != msg:
                            var_struct.info = msg
                            for handle in var_struct.handlers:
                                self._var_info_updates.update({handle: msg})       
                elif command == DriverActions.UPDATE:
                    for var_id, value in data.items():
                        var_struct = driver_struct.variables.get(var_id, None)
                        if var_struct is not None:
                            if var_struct.value != value:
                                var_struct.value = value
                                var_struct.read_count += 1
                                for handle in var_struct.handlers:
                                    self._value_updates.update({handle: value})       
                else:
                    self.log("error", f"Driver Manager: Message received from {driver_struct.name}, {command} -> {data}")
                counter += 1
                if counter>=max_pipe_loops: 
                    break

        # Write status file
        now_sec = int(time.perf_counter()) - self._start_time
        if now_sec - self._last_status_record >= 1:
            self._last_status_record = now_sec
            self._stats_updates = {
                "DRIVER_COUNT":len(self._drivers),
                "VARIABLE_COUNT":len(self._handles),
                }
            if self._status_file_path:
                self.save_status(now_sec)

        return self._status_updates or self._info_updates or self._var_info_updates or self._value_updates

    def get_updates(self)->tuple:
        """
        Call this method to receive all updates from the driver manager

        :returns: status_updates, info_updates, var_info_updates, value_updates, stats_updates (every second)
        """
        res = (copy.copy(self._status_updates), copy.copy(self._info_updates), copy.copy(self._var_info_updates), copy.copy(self._value_updates), copy.copy(self._stats_updates))
        self._status_updates = {}
        self._info_updates = {}
        self._var_info_updates = {}
        self._value_updates = {}
        self._stats_updates = {}
        return res

    def run_forever(self, pipe) -> None:
        """
        TODO
        """
        self.log("info", "Driver Manager: Running")
        while self._running:
            can_sleep = True
            # Send commands
            counter = 0
            while pipe.poll():
                can_sleep = False
                (command, data) = pipe.recv()
                res_data = self.send_command(command, data)
                if res_data is not None:
                    pipe.send((command, res_data))
                counter += 1
                if counter>=10: 
                    break
                
            # Run Once and return updates
            if self._running:
                if self.run_once():
                    can_sleep = False
                    if self._status_updates:
                        pipe.send((DriverMgrCommands.STATUS, self._status_updates))
                        self._status_updates = {}
                    if self._info_updates:
                        pipe.send((DriverMgrCommands.INFO, self._info_updates))
                        self._info_updates = {}
                    if self._var_info_updates:
                        pipe.send((DriverMgrCommands.VAR_INFO, self._var_info_updates))
                        self._var_info_updates = {}
                    if self._value_updates:
                        pipe.send((DriverMgrCommands.UPDATES, self._value_updates))
                        self._value_updates = {}
                    if self._stats_updates:
                        pipe.send((DriverMgrCommands.STATS, self._stats_updates))
                        self._stats_updates = {}

            # Sleep if nothing happens to release CPU usage
            if can_sleep:
                time.sleep(1e-3)
                
        self.log("info", "Driver Manager: Closed")
    
    def setup_drivers(self, drivers_setup_data:dict)->dict:
        """
        TODO:
        """
        res = {}
        for driver_handle, driver_data in drivers_setup_data.items():
            driver_struct = self.find_compatible_driver(driver_data)
            if driver_struct is not None:
                driver_struct.add_handle(driver_handle)
                self.log("info", f"Driver Manager: Driver {driver_handle} using compatible driver {driver_struct.name}")
                res[driver_handle] = "SUCCESS"
                self._status_updates.update({driver_handle:driver_struct.status})
            else:
                driver_struct = self.start_driver(driver_handle, driver_data)
                if driver_struct is not None:
                    self._drivers[driver_struct.name] = driver_struct
                    self.log("info", f"Driver Manager: New Driver started {driver_struct.name} -> {driver_struct.class_name}")
                    res[driver_handle] = "SUCCESS"
                else:
                    res[driver_handle] = "FAILED"
            if driver_struct is not None:
                setup_data = driver_data.get("SETUP", {})
                self._handles.update(driver_struct.add_driver_variables(setup_data.get("variables", {})))
        return res
    
    def clean_drivers(self)->True:
        """
        TODO:
        """
        for driver_name, driver_struct in self._drivers.items():
            self.log("info", f"Driver Manager: Exit command sent to driver {driver_name}")
            driver_struct.pipe.send((DriverActions.EXIT, None))
        
        while self._drivers:
            driver_name, driver_struct = self._drivers.popitem()
            driver_struct.process.join()
            self.log("info", f"Driver Manager: Driver {driver_name} closed")
    
    def start_driver(self, driver_handle:str, driver_data:dict) -> DriverStructure:
        """ Starts a new Driver Process using the given parameters. 

        :param driver_handle: Driver handle procived by the user. (See documentation)

        :param driver_data: Driver setup data, including parameters. (See documentation)

        :returns: DriverStructure if Driver has been created, or None if not
        """
        driver_class_name = driver_data.get("DRIVER", "None")
        (driver_class, _) = registered_drivers.get(driver_class_name, (None, None))
        if driver_class is not None:
            self._driver_counter += 1
            driver_name = f"DRIVER_{self._driver_counter}"
            setup_data = driver_data.get("SETUP", {})
            parameters = setup_data.get("parameters", None)
            pipe, driver_pipe = multiprocessing.Pipe()
            if self._use_processes:
                driver_proc = multiprocessing.Process(target=RunDriver, args=(driver_class, driver_name, driver_pipe, parameters,), daemon=True)
            else:
                driver_proc = threading.Thread(target=RunDriver, args=(driver_class, driver_name, driver_pipe, parameters,), daemon=True)
            driver_proc.start()
            new_driver = DriverStructure(driver_class_name, driver_name, driver_handle, parameters, pipe, driver_proc)
            return new_driver
        return None
    
    def find_compatible_driver(self, driver_data: dict) -> DriverStructure:
        """ Finds a compatible driver comparing the class and setup parameters within the existing ones. 

        :param driver_data: Driver setup data, including parameters. (See documentation)

        :returns: DriverStructure if compatible driver found or None if note
        """
        for driver_structure in self._drivers.values():
            if driver_structure.is_compatible(driver_data):
                return driver_structure
        return None