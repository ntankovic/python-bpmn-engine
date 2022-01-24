import _utils 
import extra_errors
from copy import deepcopy
from collections import OrderedDict, defaultdict
import time
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import sys
import os
from task import Cluster, master_and_core_cost
#Get parent path so it's possible to import modules from parent directory
parent_path = os.path.abspath(os.path.split(sys.argv[0])[0]) + "/../"
sys.path.append(parent_path)
import bpmn_types


class SimulationDAG():
    #In the future updates, this parametar will be set within SimlationDAG class
    SAMPLE_SIZE = 1000000
    def __init__(self, model):
        #Diagnostics
        self.diagnostics_list = []
        #Is optimized flag -> in case there is need to recreated original 
        #distribution, since after creating optimized original is overwritten
        self.is_optimized = False
        #Contains total time distribution samples
        self.total_time = None
        #Contains total cost distribution samples
        self.total_cost = None
        #Original totals -> without optimization
        self.original_total_time = None
        self.original_total_cost = None
        #All tasks durations
        #After calculating total it will contain durations for all main
        #complex gateways and tasks outside of gateways
        self.all_tasks_duration_dict = OrderedDict()
        self.all_tasks_cost_dict = OrderedDict()
        #Original duration and cost samples for use later with optization
        self.original_tasks_duration_dict = {} 
        self.original_tasks_cost_dict = {}
        #Contain each path probabily for XOR gateway
        self.path_probability_xor_dict = {}
        #Collection of paths (elements for each path) for each gateway
        self.xor_paths_dict = {}
        self.and_paths_dict = {}
        #Necessary for finding path given time/cost constraint
        self.possible_paths_for_gateways = defaultdict(dict)
        #Temporary storage of tasks for optmization
        #self.tasks_for_optimization = []
        #Alternative temporary storage of tasks for optimization
        self.tasks_for_optimization = {}
        self.tasks_for_optimization["mean time"]=[]
        self.tasks_for_optimization["requirements"] = []
        #Temporary storage of tasks ids for optimization
        self.tasks_ids_for_optimization = []
        #Temporary task -> gateway storage
        self.task_gateway_storage = {}

        flows = deepcopy(model.flow)
        pending_copy = deepcopy(model.pending)
        #Holds history of what was parsed already, to ensure model is DAG
        pending_history = []

        #Sets number of incoming paths for each gateway to 0
        #It's required to distinguish opening from closing gateways
        helper_incoming_gateway_dict = {
            model.elements[x]: 0
            for x in flows
            if isinstance(model.elements[x], bpmn_types.Gateway)
        }

        #Maps closing gateway to its associated opening gateway
        self.closing_to_opening_xor_dict = {}
        self.closing_to_opening_and_dict = {}

        #Start parsing the model
        while len(pending_copy) > 0:
            #print("-" * 50)
            #print("Outside : ", pending_copy)
            #Holds future pending elements
            #Required so it's possible to check if model is DAG
            helper_pending = []
            for c in pending_copy:
                #print("+" * 20)
                #print("CURRENT TASK : ", c)
                                
                if isinstance(c, bpmn_types.Task):
                    #Create task sample distribution
                    #print("Distributions", c.simulation_properties["probability"])
                    task_distribution = _utils.generate_distribution(c.simulation_properties["probability"], SimulationDAG.SAMPLE_SIZE) 
                    self.all_tasks_duration_dict[c] = task_distribution
                    #Temporary solution -> needed for optimization
                    #self.tasks_for_optimization.append(np.mean(task_distribution))
                    #Alternative temporary solution -> current solution
                    #distribution_95_percentile = np.percentile(task_distribution,95)
                    distribution_mean = np.mean(task_distribution)
                    optimization_parameters = c.simulation_properties["optimization"]
                    #Add task's gateway to optimization parameters
                    #if self.task_gateway_storage.get(c): 
                    #    main_gateway, gateway_list = self._find_main_gateway({**self.xor_paths_dict, **self.and_paths_dict}, c)
                    #    #print("Gateway list :", gateway_list)
                    #    #print("Main gateway : ", main_gateway)
                    #    optimization_parameters["gateway"] = main_gateway
                    optimization_parameters["gateway"] = self.task_gateway_storage[c] if self.task_gateway_storage.get(c) else None
                    #print(optimization_parameters)
                    self.tasks_for_optimization["mean time"].append(distribution_mean)
                    self.tasks_for_optimization["requirements"].append(optimization_parameters)
                    self.tasks_ids_for_optimization.append(c._id)
                    #Add cost samples
                    task_cost_distribution = self._create_cost_samples(task_distribution, optimization_parameters, 1)
                    self.all_tasks_cost_dict[c] = task_cost_distribution
                    self._save_original_distributions(c, task_distribution, task_cost_distribution)
                
                #Take index of current element and put it in history
                idx = pending_copy.index(c)
                pending_history.append(pending_copy[idx])

                # Get next target in flow
                for index, sequence in enumerate(flows[c._id]):
                    target = model.elements[sequence.target]
                    #print(sequence)
                    #print("Target : ", target)
                    #Logic for handling Gateway as next target
                    if isinstance(target, bpmn_types.Gateway):
                        helper_incoming_gateway_dict[target] += 1
                        #Check if Gateway already exists in helper_pending
                        #Also check if all elements that are before this Gateway
                        #are parsed before. This is required so that order of 
                        #elements in model is preserved.
                        #If conditions are not met element will be parsed in
                        #later iterations.
                        if (
                            target not in helper_pending
                            and target.incoming == helper_incoming_gateway_dict[target]
                        ):
                            helper_pending.append(target)
                            #Register Gateway to its corresponding dictionary
                            if isinstance(target, bpmn_types.ParallelGateway):
                                if not self.and_paths_dict.get(target):
                                    self.and_paths_dict[target] = {}
                            if isinstance(target, bpmn_types.ExclusiveGateway):
                                if not self.xor_paths_dict.get(target):
                                    self.xor_paths_dict[target] = {}
                            #If its more then 1 outgoing -> target Gateway is
                            #opening XOR/AND
                            if target.outgoing > 1:
                                self._handle_opening_target_gateway(c, target)
                            # Else -> target Gateway is closing XOR/AND
                            else:
                                self._handle_closing_target_gateway(c, target)
                    #Logic for handling target if it's Task or Event
                    else: 
                        #If current is Gateway add 
                        #Task or Event to a corresponding Gateway dictionary
                        if isinstance(c, bpmn_types.Gateway):
                            #Check to see if current is closing gateway
                            try:
                                opening_gateway_for_current = {**self.closing_to_opening_xor_dict,**self.closing_to_opening_and_dict}[c]
                            #If exception raises, it's opening gateway
                            except KeyError:
                                opening_gateway_for_current = None
                            #Special case for current being closing gateway
                            if opening_gateway_for_current is not None:
                                #print(f"{c} is closing gateway followed by {target}")
                                #print(f"Opening gateway for {c} is {opening_gateway_for_current}")
                                correct_gateway_and_path = (
                                    self._find_correct_gateway_and_path(
                                        {**self.xor_paths_dict, **self.and_paths_dict},
                                        opening_gateway_for_current 
                                    )
                                )
                                #Check if correct gateway and paths exist
                                #If it's None, then opened gateway is on main
                                #path
                                if correct_gateway_and_path:
                                    self._add_target_into_existing_gateway_path(correct_gateway_and_path[0], correct_gateway_and_path[1], target)

                            #Regular case when current is opening gateway
                            else:
                                self._add_target_into_current_gateway_path(c, target)
                                self.task_gateway_storage[target] = c
                        #If current is Task or Event, find to which gateway and 
                        #path current belongs to and if they exists append 
                        #target task to it.
                        if isinstance(c, bpmn_types.Task) or isinstance(c, bpmn_types.Event):
                            correct_gateway_and_path = self._find_correct_gateway_and_path(
                                {**self.xor_paths_dict, **self.and_paths_dict}, c
                            )
                            if correct_gateway_and_path:
                                self.task_gateway_storage[target] = c
                                if isinstance(
                                    correct_gateway_and_path[0], bpmn_types.ExclusiveGateway
                                ):
                                    self.xor_paths_dict[correct_gateway_and_path[0]][
                                        correct_gateway_and_path[1]
                                    ].append(target)
                                else:
                                    self.and_paths_dict[correct_gateway_and_path[0]][
                                        correct_gateway_and_path[1]
                                    ].append(target)
                        if target not in helper_pending:
                            helper_pending.append(target)
                    if len(flows[c._id]) > 1:
                        if isinstance(c, bpmn_types.ExclusiveGateway):
                            #If more then 1 flow and XOR Gateway, add paths
                            #probabilities to its dictionary
                            try:
                                #print(f"From {c} decision outcome for {target} :  {c.decision_outcome[index]}")
                                self.path_probability_xor_dict[c][target] = c.decision_outcome[index]
                            except:
                                self.path_probability_xor_dict[c] = {}
                                self.path_probability_xor_dict[c][target] = c.decision_outcome[index]


            #Create fresh pending copy for next iteration
            pending_copy = []
            #Generate list for new iteration
            for x in helper_pending:
                if x not in pending_history:
                    pending_copy.append(x)
                else:
                    #If element already exits in history -> != DAG
                    raise extra_errors.BpmnModelIsNotDAG(x)

        #Diagnostics
        #print("-" * 50)
        #print("All tasks duration dict : ")
        #print(self.all_tasks_duration_dict)
        #print("-" * 50)
        #print("XOR paths dict : ")
        #print(self.xor_paths_dict)
        #print("-" * 50)
        #print("Path probability xor dict : ")
        #print(self.path_probability_xor_dict)
        #print("-" * 50)
        #print("AND paths dict : ")
        #print(self.and_paths_dict)
        #print("-" * 50)
        #print("Incoming gateway dict : ")
        #print(helper_incoming_gateway_dict)
        #print("-" * 50)
        #print("Closing to opening XOR dict : ")
        #print(self.closing_to_opening_xor_dict)
        #print("-" * 50)
        #print("Closing to opening AND dict : ")
        #print(self.closing_to_opening_and_dict)
        #print("-" * 50)
        #print("Task to gateway storage : ")
        #print(self.task_gateway_storage)
        #print("-" * 50)

        #Add XOR and AND paths to optimization parameters
        self.tasks_for_optimization["XOR paths"] = self.xor_paths_dict
        self.tasks_for_optimization["AND paths"] = self.and_paths_dict

    def create_total_distribution(self, plot=True, optimized=False, sample_size=1000000):
        SimulationDAG.SAMPLE_SIZE = sample_size
        #Check if total already exitst and if it does just return it
        if self.total_time is not None:
            if plot:
                self._plot_distribution(self.total_time, self.total_cost, optimized)
            return self.total_time, self.total_cost

        #Create list of gateways in order they appear in the model
        ordered_gateway_list = []
        for key in self.all_tasks_duration_dict:
            if isinstance(key,bpmn_types.Gateway):
                ordered_gateway_list.append(key)
       
        # Handle complex gateways  
        for i, gateway in enumerate(ordered_gateway_list):
            #print("Total distribution call for ",gateway)
            #Get task time for complex gateway
            task_time, task_cost = self._handle_complex_paths(
                {**self.xor_paths_dict,**self.and_paths_dict},
                gateway,
                self.possible_paths_for_gateways
            )
            #Update complex gateway task time
            if task_time is not None:
                if len(task_time) != 0:
                    self.all_tasks_duration_dict[gateway] = task_time
                    self.all_tasks_cost_dict[gateway] = task_cost
            #print("-" * 10)

        #print("-" * 50)
        #print("All tasks duration dict for total distribution : ")
        #print(self.all_tasks_duration_dict)
        #print("-" * 50)

        all_tasks_duration_list = [duration for key,duration in self.all_tasks_duration_dict.items()]
        all_tasks_cost_list = [cost for key,cost in self.all_tasks_cost_dict.items()]

        # Finishing algorithm
        self.total_time = sum(all_tasks_duration_list)
        self.total_cost = sum(all_tasks_cost_list)
        #We add 0.3(~20mins) for starting time of cluster
        self.total_time += 0.3
        #Add master and core cost for whole process
        self.total_cost += master_and_core_cost(self.total_time)
        #print("Master and core cost : ", master_and_core_cost(self.total_time))
        #print("Mean time of process : ",np.mean(self.total_time))
        #print("Mean cost of process : ", np.mean(self.total_cost))

        if plot:
            #Plot final distribution    
            self._plot_distribution(self.total_time, self.total_cost, optimized)
        
        if not optimized:
            self.original_total_time = self.total_time
            self.original_total_cost = self.total_cost
            self.tasks_for_optimization["original total time"] = self.original_total_time
            self.tasks_for_optimization["original total cost"] = self.original_total_cost
        return self.total_time, self.total_cost


    def create_optimized_total_distribution(self, optimized_process, plot=True, sample_size=1000000):
        SimulationDAG.SAMPLE_SIZE = sample_size
        for optimized_task in optimized_process:
            #print("Task id :",optimized_task["task_id"])
            for original_task in self.original_tasks_duration_dict:
                if isinstance(original_task, bpmn_types.Gateway):
                    self.all_tasks_duration_dict[original_task] = None
                    self.all_tasks_cost_dict[original_task] = None
                if original_task._id == optimized_task["task_id"]:
                    #print(original_task._id)
                    #Create optimized time distribution
                    original_time_mean = np.mean(self.original_tasks_duration_dict[original_task])
                    #print("Original time mean : ", original_time_mean)
                    optimized_time_mean = optimized_task["cluster_type"]["time_based_on_cluster"]
                    #print("Optimized time mean : ", optimized_time_mean)
                    optimized_time_difference = original_time_mean/optimized_time_mean
                    #print("Difference : ", optimized_time_difference)
                    optimized_time_distribution = self.original_tasks_duration_dict[original_task] / optimized_time_difference
                    optimized_time_distribution = _utils.generate_distribution_with_different_size(optimized_time_distribution, SimulationDAG.SAMPLE_SIZE)
                    #print("Mean of smaller distribution :", np.mean(optimized_time_distribution))
                    self.diagnostics_list.append(optimized_time_mean/ np.mean(optimized_time_distribution))
                    self.all_tasks_duration_dict[original_task] = optimized_time_distribution
                    #Create optimized cost distribution 
                    index = self.tasks_ids_for_optimization.index(original_task._id)
                    cluster_requirements = self.tasks_for_optimization["requirements"][index]
                    nexec = optimized_task["cluster_type"]["nexec"]
                    optimized_cost_distribution = self._create_cost_samples(optimized_time_distribution, cluster_requirements, nexec)
                    self.all_tasks_cost_dict[original_task] = optimized_cost_distribution
        #Reset total time and cost
        self.total_time = None
        self.total_cost = None

        return self.create_total_distribution(plot=plot, optimized=True, sample_size=sample_size)

    def find_path_given_duration_constraint(self, start, end, json=False):
        """
        return : path with highest sample size in range
                "start <= total time distribution <= end"
        """
        if self.total_time is None:
            print("Total is None, therefor it will be calculated before proceding with this function")
            self.create_total_distribution(plot=False)

        possible_paths_for_xor = {}
        possible_paths_for_and = {}

        all_possible_paths = {}

        for key in self.all_tasks_duration_dict:
            if isinstance(key, bpmn_types.ExclusiveGateway):
                possible_paths_for_xor[key] = self.find_all_possible_paths(key)
            elif isinstance(key, bpmn_types.ParallelGateway):
                possible_paths_for_and[key] = self.find_all_possible_paths(key,xor=False)

        #print("*"*50)

        path_counter = 0
        all_possible_paths[path_counter] = []

        for key, samples in self.all_tasks_duration_dict.items():
            if not isinstance(key, bpmn_types.Gateway):
                #Get list of paths
                current_paths = list(all_possible_paths.keys())
                #If it's not gateway add element with its samples into all 
                #possible paths
                for counter in current_paths:
                    all_possible_paths[counter].append({key:samples})
            else:
                #Get list of paths
                current_paths = list(all_possible_paths)
                for counter in current_paths:
                    #Get copy of path until gateway
                    path_until_gateway = all_possible_paths[counter]
                    if isinstance(key, bpmn_types.ParallelGateway):
                        #print("Key :",key)
                        #print("Paths :", possible_paths_for_and[key])
                        for _, path in possible_paths_for_and[key].items():
                            all_possible_paths[path_counter] = []
                            all_possible_paths[path_counter].extend(path_until_gateway)
                            all_possible_paths[path_counter].extend(path)
                            path_counter = list(all_possible_paths)[-1] + 1
                    elif isinstance(key, bpmn_types.ExclusiveGateway):
                        #print("Key :",key)
                        #print("Paths :", possible_paths_for_xor[key])
                        for _, path in possible_paths_for_xor[key].items():
                            all_possible_paths[path_counter] = []
                            all_possible_paths[path_counter].extend(path_until_gateway)
                            all_possible_paths[path_counter].extend(path)
                            #Create new path -> last path in all paths + 1
                            #For some reason it doesn't work when current_paths
                            #is used...
                            path_counter = list(all_possible_paths)[-1] + 1
                    #Set path counter to next counter in current paths
                    path_counter = counter + 1
                #Reset path counter back to 0 
                path_counter = 0
        
        #print("*"*50)

        total_samples_for_each_path = {}
        total_tasks_for_each_path = {}
        for path_counter, value_list in all_possible_paths.items():
            total_tasks_for_each_path[path_counter] = []
            #print("Possible path ", path_counter, ":")
            #print(value_list)
            #print("\n")
            path_total_samples = []
            for value in value_list:
                if isinstance(value, str):
                    continue
                for task, samples in value.items():
                    path_total_samples.append(samples)
                    total_tasks_for_each_path[path_counter].append(task)
            path_total_samples = sum(path_total_samples)
            total_samples_for_each_path[path_counter] = path_total_samples
        
        #print("*"*50)    
        winner_path = None
        current_max = 0
        for path_counter, total_samples in total_samples_for_each_path.items():
            condition_check = np.where((start <=total_samples) & (total_samples <= end))
            subset = total_samples[condition_check]
            if len(subset) > current_max:
                winner_path = path_counter
                current_max = len(subset)

        if winner_path is not None:
            #print(f"Path in range {start}-{end}")
            #print(total_tasks_for_each_path[winner_path])
            if json:
                return [t._id for t in total_tasks_for_each_path[winner_path]]
            else:
                return total_tasks_for_each_path[winner_path]
        else:
            raise extra_errors.NoPathsInGivenConstraint(start,end)

    def find_all_possible_paths(self, gateway, xor=True):
        """
        Create all possible paths task duration from final all_task_duration_dict.
        This is used in case there is single or multiple XOR gateways in final all_task_duration_dict.
        Function will calculate process duration for each possible path workflow can take,
        which will in return give array of distributions for each path.

        parameters : 
        gateway -> find all paths for this gateway
        xor -> True == XOR gateway, False == AND gateway

        return : all_possible_paths_tasks_duration = {path1 : [t1:[samples],xor_path1:[samples]...], path2 : [t1:[samples], xor_path2:[samples]...],....}
        """
        
        #print("="*50)
        #print(f"Finding all paths for {gateway}")
        all_possible_paths_tasks_duration =  {}

        if xor:
            paths_in_gateway = self.xor_paths_dict[gateway]
            gateway_type = "XOR"
        else:
            paths_in_gateway = self.and_paths_dict[gateway]
            gateway_type = "AND"

        regular_and_paths_counter = {}
        regular_and_paths_counter[gateway] = []

        #For loop counters
        sample_location = 0
        path_counter = 0

        #print("Paths in gateway : ", paths_in_gateway)
        for _, path in paths_in_gateway.items():
            all_possible_paths_tasks_duration[path_counter] = []
            #Helper counter
            xor_nested_in_and_counter = 0
            for p in path:
                #print(f"Path counter for {p} is {path_counter}")
                #print(f"Sample location for {p} is {sample_location}")
                #If it's not Gateway append it to the current path
                if not isinstance(p, bpmn_types.Gateway):
                    #At the moment Events are ignored since they don't have
                    #distribution associated with them. In the future this 
                    #if statement should be removed and Events should be handled
                    #same as Tasks
                    if isinstance(p, bpmn_types.Event):
                        all_possible_paths_tasks_duration[path_counter].append({p : np.zeros(shape=SimulationDAG.SAMPLE_SIZE)})
                        #This is so that Event doesn't mess up the order...
                        sample_location -= 1
                    else:
                        #print(f"Possible samples for {gateway} : ")
                        for sample in self.possible_paths_for_gateways[gateway_type][gateway]:
                            pass
                            #print(sample)
                            #print(type(sample))
                        #print(f"Number of possible samples for {gateway} : {len(self.possible_paths_for_gateways[gateway_type][gateway])}")
                        #Check if task is after xor nested in and gateway
                        if "nested" in all_possible_paths_tasks_duration[path_counter]:
                            temp_counter = path_counter
                            #Add task to all path of xor nested in and
                            for _ in range(0,xor_nested_in_and_counter):
                                all_possible_paths_tasks_duration[temp_counter].append({p : self.possible_paths_for_gateways[gateway_type][gateway][sample_location]})
                                temp_counter -= 1
                        else:
                            #Add task distribution
                            all_possible_paths_tasks_duration[path_counter].append({p : self.possible_paths_for_gateways[gateway_type][gateway][sample_location]})
                #This condition means that there are nested gateways inside 
                #current gateway
                else:
                    #Flag to check for nested XOR gateway inside AND gateway
                    xor_inside_and = False
                    #Flag to check for nested AND gateway inside XOR gateway
                    and_inside_xor = False
                    #Get copy of all tasks for current path counter
                    path_until_gateway  = all_possible_paths_tasks_duration[path_counter]

                    #print(f"{p} inside {gateway}")
                    if isinstance(p, bpmn_types.ParallelGateway):
                        #Check if AND is inside XOR gateway
                        if isinstance(gateway, bpmn_types.ExclusiveGateway):
                            and_inside_xor = True
                        possible_paths_in_gateway = self.find_all_possible_paths(p, xor=False)
                    elif isinstance(p, bpmn_types.ExclusiveGateway):
                        #Check if XOR is inside AND gateway
                        if isinstance(gateway, bpmn_types.ParallelGateway):
                            xor_inside_and = True
                        possible_paths_in_gateway = self.find_all_possible_paths(p)

                    #Helps to keep track of previous nested xor paths in AND
                    xor_in_and_paths_history = []
                    #Helper counter
                    xor_nested_in_and_counter = 0
                    #Helper flag
                    reduce_path_counter = True
                    #print("Main gateway : ", gateway)
                    #print("Paths until",p," before for loop :", path_until_gateway)
                    #For each nested gateway path create new path in 
                    #all_possible_paths, then add value to it 
                    for _, value in possible_paths_in_gateway.items():
                        #print("Handling value :", value)
                        #print("Path counter : ", path_counter)
                        #print("Sample location :", sample_location)
                        #If it's regular AND gateway skip this step
                        if reduce_path_counter:
                            #Create empty path for current path counter
                            all_possible_paths_tasks_duration[path_counter] = []
                        #Add marker for XOR nested inside AND gateway
                        if xor_inside_and and isinstance(p, bpmn_types.ExclusiveGateway):
                            all_possible_paths_tasks_duration[path_counter].append("nested")
                            xor_nested_in_and_counter += 1

                        #Check if there exists nested XOR path inside AND
                        #gateway
                        if isinstance(p, bpmn_types.ParallelGateway) and "nested" in value:
                            #Increase path counter if regular AND path
                            #was before
                            if not reduce_path_counter:
                                reduce_path_counter = True
                                path_counter += 1
                            #print("XOR nested Path counter :", regular_and_paths_counter[gateway])
                            #print("XOR nested counter :", xor_nested_in_and_counter)
                            #Remove nested marker from the list
                            #value.pop(value.index("nested"))
                            for n in regular_and_paths_counter[gateway]:
                                previous_and_path = all_possible_paths_tasks_duration[n]
                                if xor_nested_in_and_counter == 0:
                                    #print("Previous and path :", previous_and_path)
                                    previous_and_path.extend(value)
                                else:
                                    #print("XOR history :", xor_in_and_paths_history)
                                    for history_path in xor_in_and_paths_history:
                                        #Check if it's nested marker
                                        if isinstance(history_path, str):
                                            continue
                                        #print("History path : ",history_path)
                                        pos = previous_and_path.index(history_path)
                                        #Make previous_and_path without old xor
                                        #paths, while preserving existing paths
                                        if pos == 0:
                                            previous_and_path = previous_and_path[1:]
                                        elif pos == len(previous_and_path)-1:
                                            previous_and_path = previous_and_path[:-1]
                                        else:
                                            previous_and_path = previous_and_path[:pos] + previous_and_path[pos+1:]
                                    #print("Previous and path :", previous_and_path)
                                    all_possible_paths_tasks_duration[path_counter].extend(previous_and_path)
                                    all_possible_paths_tasks_duration[path_counter].extend(value)
                                    path_counter += 1
                            xor_nested_in_and_counter += 1
                            xor_in_and_paths_history.extend(value)
                        #If its regular (non-xor-nested) path, add path counter
                        #to xor nested paths counter
                        elif isinstance(p, bpmn_types.ParallelGateway) and "nested" not in value:
                            regular_and_paths_counter[gateway].append(path_counter)
                            #print(f"Regular and paths counter : {regular_and_paths_counter}")
                            #If its regular AND gateway, all paths from it go
                            #to the path before it
                            reduce_path_counter = False
                            #Add values to current path
                            path_until_gateway.extend(value)
                            all_possible_paths_tasks_duration[path_counter] = path_until_gateway
                        else:
                            if not reduce_path_counter:
                                reduce_path_counter = True
                            #Add all tasks until gateway to current path
                            all_possible_paths_tasks_duration[path_counter].extend(path_until_gateway)
                            #Add values to current path
                            all_possible_paths_tasks_duration[path_counter].extend(value)
                            path_counter += 1
                        if reduce_path_counter:
                            pass
                            #print("Path after handling value : ", all_possible_paths_tasks_duration[path_counter-1])
                        else:
                            pass
                            #print("Path after handling value : ", all_possible_paths_tasks_duration[path_counter])
                    #Reduce path counter for 1 so it stays in sync 
                    if reduce_path_counter:
                        path_counter -= 1
                sample_location += 1
            #Increase path counter for path
            path_counter += 1
        #print(f"All possible paths for : {gateway}")
        #print(f"Possible paths : {len(all_possible_paths_tasks_duration.keys())}")
        #print(f"Paths duration: {all_possible_paths_tasks_duration}")
        #print("="*50)
        return all_possible_paths_tasks_duration
   
    def get_tasks_for_optimization(self):
        if self.original_total_time is None:
            print("Total is None, therefor it will be calculated before proceding with this function")
            self.create_total_distribution(plot=False)
        return self.tasks_for_optimization
    
    def get_tasks_ids_for_optimization(self):
        return self.tasks_ids_for_optimization

    def _handle_complex_paths(
        self, gateway_dict, gateway, possible_paths_samples
    ):
        """
        Recursivly handle nested gateways. 
        
        return: complex distribution sample
        """
        #First check before everything
        if gateway not in self.all_tasks_duration_dict or gateway not in self.all_tasks_cost_dict:
            #If its not in it means it was already handled by recursion
            return None,None

        all_paths_time_ordered = []
        all_paths_cost_ordered = []
        paths_probability_ordered = []
        
        path_dict = gateway_dict[gateway]

        #print("Handling Complex Gateway : ",gateway)
        #print("Path dictionary : ",path_dict)
        for key, path in path_dict.items():
            single_path_time = []
            single_path_cost = []
            for p in path:
                #print("Element on path : ",p)
                if isinstance(p, bpmn_types.Gateway):
                    task_time, task_cost = self._handle_complex_paths(
                        gateway_dict, p, possible_paths_samples
                    )
                elif isinstance(p, bpmn_types.Task):
                    task_time = self.all_tasks_duration_dict[p]
                    task_cost = self.all_tasks_cost_dict[p]
                elif isinstance(p, bpmn_types.Event):
                    #Placeholder for when we start handling Events
                    continue
                del self.all_tasks_duration_dict[p]
                del self.all_tasks_cost_dict[p]
                if len(task_time) != 0:
                    single_path_time.append(task_time)
                if len(task_cost) != 0:
                    single_path_cost.append(task_cost)
            #print("Path : ",path)
            #print("Single path time: ", single_path_time)
            #print("Single path cost: ", single_path_cost)
            sum_of_single_path_time = sum(single_path_time)
            sum_of_single_path_cost = sum(single_path_cost)
            all_paths_time_ordered.append(sum_of_single_path_time)
            all_paths_cost_ordered.append(sum_of_single_path_cost)
            if isinstance(gateway, bpmn_types.ExclusiveGateway):
                paths_probability_ordered.append(self.path_probability_xor_dict[gateway][key])
                #Add single path to possible paths dictionary for that gateway
                if possible_paths_samples["XOR"].get(gateway):
                    possible_paths_samples["XOR"][gateway].extend(single_path_time)
                else:
                    possible_paths_samples["XOR"][gateway] = []
                    possible_paths_samples["XOR"][gateway].extend(single_path_time)
            elif isinstance(gateway, bpmn_types.ParallelGateway):
                if possible_paths_samples["AND"].get(gateway):
                    possible_paths_samples["AND"][gateway].extend(single_path_time)
                else:
                    possible_paths_samples["AND"][gateway] = []
                    possible_paths_samples["AND"][gateway].extend(single_path_time)

        #print("All paths time ordered : ", all_paths_time_ordered)
        #print("All paths cost ordered : ", all_paths_cost_ordered)
        if isinstance(gateway, bpmn_types.ExclusiveGateway):
            complex_time_sample = _utils.generate_mix_distribution(all_paths_time_ordered, paths_probability_ordered, SimulationDAG.SAMPLE_SIZE)
            complex_cost_sample =  _utils.generate_mix_distribution(all_paths_cost_ordered, paths_probability_ordered, SimulationDAG.SAMPLE_SIZE)
        else:
            complex_time_sample = _utils.generate_max_distribution(all_paths_time_ordered)
            complex_cost_sample = _utils.generate_max_distribution(all_paths_cost_ordered, cost=True)

        #print(f"Complex time sample for {gateway} :{complex_time_sample}")
        #print(f"Complex cost sample for {gateway} :{complex_cost_sample}")
        return complex_time_sample, complex_cost_sample


    def _find_opened_gateway_for_current(self, merged_path_dict, current):
        for gateway, path_dict in merged_path_dict.items():
            for path, path_list in path_dict.items():
                for p in path_list:
                    if current == p:
                        #print(f"Opened Gateway for {current} is {gateway}")
                        return gateway

    def _find_correct_gateway_and_path(self, merged_path_dict, current):
        for gateway, path_dict in merged_path_dict.items():
            for path, path_list in path_dict.items():
                for p in path_list:
                    if current == p:
                        #print(f"Correct gateway and path for {current} : {gateway} and {path}")
                        return [gateway, path]

    def _find_main_gateway(self, merged_path_dict, current, gateway_list = None):
        if gateway_list is None:
            gateway_list = []
        #print(f"Finding the main gateway for {current}")
        main_gateway = self._find_opened_gateway_for_current(merged_path_dict, current)
        if main_gateway is not None:
            if main_gateway not in gateway_list:
                gateway_list.append(main_gateway)
            current = self._find_main_gateway(merged_path_dict, main_gateway, gateway_list)[0]
        return current, gateway_list

    def _handle_opening_target_gateway(self, c, target):
        #print(f"Handling opening gateway: {target}")
        #Add placeholders for all tasks inside gateway
        self.all_tasks_duration_dict[target] = None
        self.all_tasks_cost_dict[target] = None
        self._save_original_distributions(target, None, None)
        #If current is Gateway AND it's not closing gateway
        #Add target Gateway to a corresponding current Gateway path dictionary
        if isinstance(c, bpmn_types.Gateway) and c not in {**self.closing_to_opening_xor_dict,**self.closing_to_opening_and_dict}:
            self._add_target_into_current_gateway_path(c, target)
            #Since we added target Gateway to currents Gateway path we can 
            #safely return and not continue with the rest of the function.
            return
        #Find correct gateway inside self.xor_paths_dict
        #and self.and_paths_dict
        correct_gateway_and_path = self._find_correct_gateway_and_path(
            {**self.xor_paths_dict, **self.and_paths_dict}, c
        )
        #If current element is nested inside AND or XOR
        if correct_gateway_and_path:
            #That means that Gateway is also nested and 
            #it needs to be appended as element to
            #correct path and gateway
            if isinstance(
                correct_gateway_and_path[0],
                bpmn_types.ExclusiveGateway,
            ):
                self.xor_paths_dict[correct_gateway_and_path[0]][
                    correct_gateway_and_path[1]
                ].append(target)
            else:
                self.and_paths_dict[correct_gateway_and_path[0]][
                    correct_gateway_and_path[1]
                ].append(target)


    def _handle_closing_target_gateway(self, c, target):
        #print(f"Handling closing gateway {target}")
        #If current element is also Gateway that means
        #that current element is also closing XOR/AND
        if isinstance(c, bpmn_types.Gateway):
            #Find opened gateway on this path, for 
            #current(closing) gateway using its opening
            #gateway. If this is the case current is 
            #nested gateway.
            opening_gateway_for_current = {**self.closing_to_opening_xor_dict,**self.closing_to_opening_and_dict}[c]
            opened_gateway_for_this_path = (
                self._find_opened_gateway_for_current(
                    {**self.xor_paths_dict, **self.and_paths_dict},
                    opening_gateway_for_current 
                )
            )
            self._map_closing_to_opening_gateway(target,opened_gateway_for_this_path)
        else:
            #If current element is not gateway trace 
            #back its opening gateway
            opened_gateway_for_this_path = (
                self._find_opened_gateway_for_current(
                    {**self.xor_paths_dict, **self.and_paths_dict}, c
                )
            )
            self._map_closing_to_opening_gateway(target,opened_gateway_for_this_path)

    def _map_closing_to_opening_gateway(self, target, opened_gateway_for_path):
        #Map closing target Gateway to its opening
        #gateway
        #print(f"Mapping {target} to {opened_gateway_for_path}")
        if isinstance(opened_gateway_for_path,bpmn_types.ExclusiveGateway):
            self.closing_to_opening_xor_dict[target] = opened_gateway_for_path
        else:
            self.closing_to_opening_and_dict[target] = opened_gateway_for_path


    def _add_target_into_current_gateway_path(self, current, target):
        #print(f"Adding {target} to {current} path")
        if isinstance(current, bpmn_types.ExclusiveGateway):
            self.xor_paths_dict[current][target] = []
            self.xor_paths_dict[current][target].append(target)
        if isinstance(current, bpmn_types.ParallelGateway):
            self.and_paths_dict[current][target] = []
            self.and_paths_dict[current][target].append(target)
    
    def _add_target_into_existing_gateway_path(self, current, path, target):
        #print(f"Adding {target} to {current} and path {path}")
        if isinstance(current, bpmn_types.ExclusiveGateway):
            self.xor_paths_dict[current][path].append(target)
        if isinstance(current, bpmn_types.ParallelGateway):
            self.and_paths_dict[current][path].append(target)
    
    def _create_cost_samples(self, distribution, optimization_params, nexec):
        requirements = [optimization_params["cpu"], optimization_params["ram"]]
        cluster = Cluster(requirements, nexec)
        #Cluster starting time ~20min
        starting_time = 0.3
        #Fixed cluster cost
        fixed_cost = 0.02
        #print("Task cost distribution : ", ((distribution+starting_time) * cluster.ec2_cost() + (distribution+starting_time) * cluster.emr_cost())+fixed_cost)
        return ((distribution+starting_time) * cluster.ec2_cost() * cluster.nexec + (distribution+starting_time) * cluster.emr_cost() * cluster.nexec) + fixed_cost


    def _save_original_distributions(self, task, duration_distribution, cost_distribution):
        self.original_tasks_duration_dict[task] = duration_distribution
        self.original_tasks_cost_dict[task] = cost_distribution 

    def _plot_distribution(self, time_samples, cost_samples, optimized=False):
        if optimized:
            title_name = "Optimized"
        else:
            title_name = "Original"
        fig, axis = plt.subplots(nrows=1, ncols=2, figsize=(8.0,3.5))
        #Set main title and adjust layout
        fig.suptitle(f"Probability density functions for the business process", fontsize=11)
        fig.subplots_adjust(top=0.85, wspace=0.28)

        #Time plot
        sns.kdeplot(time_samples, ax=axis[0], color="green")
        axis[0].set_ylim([0.0,None])
        axis[0].set_xlabel("Hours")
        axis[0].set_title(f"{title_name} total time distribution", fontsize=10)

        #Cost plot
        sns.kdeplot(cost_samples, ax=axis[1], color="blue")
        axis[1].set_ylim([0.0,None])
        axis[1].set_xlabel("USD")
        axis[1].set_title(f"{title_name} total cost distribution", fontsize=10)
        plt.show()

