from _utils import calculate_gamma_shape, calculate_gamma_scale
import extra_errors
from copy import deepcopy
from collections import OrderedDict, defaultdict
from functools import reduce
import time
import numpy as np
import matplotlib.pyplot as plt
import warnings
import sys
import os
#Get parent path so it's possible to import modules from parent directory
parent_path = os.path.abspath(os.path.split(sys.argv[0])[0]) + "/../"
sys.path.append(parent_path)
import bpmn_types

#New way to use numpy random
numpy_random = np.random.default_rng()

SAMPLE_SIZE = 1000000
DISTRIBUTION = numpy_random.gamma

    
class SimulationDAG():
    def __init__(self, model):
        #Contains total distribution samples
        self.total = None
        #All tasks durations
        #After calculating total it will contain durations for all main
        #complex gateways and tasks outside of gateways
        self.all_tasks_duration_dict = OrderedDict()
        #Contain each path probabily for XOR gateway
        self.path_probability_xor_dict = {}
        #Collection of paths (elements for each path) for each gateway
        self.xor_paths_dict = {}
        self.and_paths_dict = {}
        self.xor_path_samples_dictionary = defaultdict(list)
        #Temporary storage of tasks for optmization
        self.tasks_for_optimization = []
        #Temporary storage of tasks ids for optimization
        self.tasks_ids_for_optimization = []

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
            print("-" * 50)
            print("Outside : ", pending_copy)
            #Holds future pending elements
            #Required so it's possible to check if model is DAG
            helper_pending = []
            for c in pending_copy:
                print("+" * 20)
                print("CURRENT TASK : ", c)
                                
                if isinstance(c, bpmn_types.Task):
                    #Temporary solution -> needed for optimization
                    self.tasks_for_optimization.append(c.expected_time["time_mean"])
                    self.tasks_ids_for_optimization.append(c._id)
                    #Calculating shape and scale is specific to Gamma distr
                    #In the future more general approach should be taken
                    shape = calculate_gamma_shape(c.expected_time["time_mean"],c.expected_time["time_std"])
                    scale = calculate_gamma_scale(c.expected_time["time_mean"],c.expected_time["time_std"])
                    #Create task sample distribution
                    task_distribution = DISTRIBUTION(
                        shape, scale, size=SAMPLE_SIZE
                    )
                    self.all_tasks_duration_dict[c] = task_distribution
                
                #Take index of current element and put it in history
                idx = pending_copy.index(c)
                pending_history.append(pending_copy[idx])

                # Get next target in flow
                for index, sequence in enumerate(flows[c._id]):
                    target = model.elements[sequence.target]
                    print(sequence)
                    print("Target : ", target)
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
                        #If current is Gateway, add Task or Event to a
                        #corresponding Gateway dictionary
                        if isinstance(c, bpmn_types.ExclusiveGateway):
                            self.xor_paths_dict[c][target] = []
                            self.xor_paths_dict[c][target].append(target)
                        if isinstance(c, bpmn_types.ParallelGateway):
                            self.and_paths_dict[c][target] = []
                            self.and_paths_dict[c][target].append(target)
                        #If current is Task or Event, find to which gateway and 
                        #path current belongs to and if they exists append 
                        #target task to it.
                        if isinstance(c, bpmn_types.Task) or isinstance(c, bpmn_types.Event):
                            correct_gateway_and_path = self._find_correct_gateway_and_path(
                                {**self.xor_paths_dict, **self.and_paths_dict}, c
                            )
                            print("Correct gateway : ", correct_gateway_and_path)
                            if correct_gateway_and_path:
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
                            print("Decision outcome for ", c, " : ", c.decision_outcome)
                            self.path_probability_xor_dict[target] = c.decision_outcome[index]

            #Create fresh pending copy for next iteration
            pending_copy = []
            #Generate list for new iteration
            for x in helper_pending:
                if x not in pending_history:
                    pending_copy.append(x)
                else:
                    #If element already exits in history -> != DAG
                    raise extra_errors.BpmnModelIsNotDAG(x)

    def create_total_distribution(self, plot=True):
        #Check if total already exitst and if it does just return it
        if self.total:
            if plot:
                self._plot_distribution(self.total)
            return self.total

        #Create list of gateways in order they appear in the model
        ordered_gateway_list = []
        for key in self.all_tasks_duration_dict:
            if isinstance(key,bpmn_types.Gateway):
                ordered_gateway_list.append(key)
       
        # Handle complex gateways  
        for i, gateway in enumerate(ordered_gateway_list):
            print(gateway)
            #Get task time for complex gateway
            task_time = self._handle_complex_paths(
                {**self.xor_paths_dict,**self.and_paths_dict},
                gateway,
                self.xor_path_samples_dictionary
            )
            #Update complex gateway task time
            if task_time is not None:
                if len(task_time) != 0:
                    self.all_tasks_duration_dict[gateway] = task_time
            print("-" * 10)

        print("-" * 50)
        print("All tasks duration dict : ")
        print(self.all_tasks_duration_dict)
        print("-" * 50)

        all_tasks_duration_list = []
        for key, duration in self.all_tasks_duration_dict.items():
            all_tasks_duration_list.append(duration)

        # Finishing algorithm
        self.total = sum(all_tasks_duration_list)

        if plot:
            #Plot final distribution    
            self._plot_distribution(self.total)
        
        return self.total
        
    def find_path_given_duration_constraint(self, start, end, json=False):
        """
        return : path with highest sample size in range
                "start <= total time distribution <= end"
        """
        if self.total is None:
            warnings.warn("Total is None, therefor it will be calculated before proceding with this function")
            self.create_total_distribution(plot=False)

        possible_paths_for_xor = {}
        all_possible_paths = {}
        for key in self.all_tasks_duration_dict:
            if isinstance(key, bpmn_types.ExclusiveGateway):
                print(f"Handling {key}")
                possible_paths_for_xor[key] = self._find_all_possible_paths(key)

        path_counter = 0
        all_possible_paths[path_counter] = []
        for key, samples in self.all_tasks_duration_dict.items():
            if not isinstance(key, bpmn_types.ExclusiveGateway):
                current_paths = list(all_possible_paths.keys())
                for counter in current_paths:
                    all_possible_paths[counter].append({key:samples})
            else:
                #Fixed number of paths before handling additional xor possibilities
                current_paths = list(all_possible_paths.keys())
                for counter in current_paths:
                    #Get copy of path until xor
                    path_until_xor = all_possible_paths[counter]
                    for _, path in possible_paths_for_xor[key].items():
                        all_possible_paths[path_counter] = []
                        all_possible_paths[path_counter].extend(path_until_xor)
                        all_possible_paths[path_counter].extend(path)
                        #
                        path_counter = list(all_possible_paths.keys())[-1] + 1
                    path_counter = counter + 1
                path_counter = 0
        
        print("*"*50)

        total_samples_for_each_path = {}
        total_tasks_for_each_path = {}
        for path_counter, value_list in all_possible_paths.items():
            total_tasks_for_each_path[path_counter] = []
            print("Possible path ", path_counter, ":")
            print(value_list)
            print("\n")
            path_total_samples = []
            for value in value_list:
                for task, samples in value.items():
                    path_total_samples.append(samples)
                    total_tasks_for_each_path[path_counter].append(task)
            path_total_samples = sum(path_total_samples)
            total_samples_for_each_path[path_counter] = path_total_samples
        
        print("*"*50)    
        winner_path = None
        current_max = 0
        for path_counter, total_samples in total_samples_for_each_path.items():
            condition_check = np.where((start <=total_samples) & (total_samples <= end))
            subset = total_samples[condition_check]
            if len(subset) > current_max:
                winner_path = path_counter
                current_max = len(subset)

        if winner_path is not None:
            print(f"Path in range {start}-{end}")
            print(total_tasks_for_each_path[winner_path])
            if json:
                return [t._id for t in total_tasks_for_each_path[winner_path]]
            else:
                return total_tasks_for_each_path[winner_path]
        else:
            raise extra_errors.NoPathsInGivenConstraint(start,end)

    def get_tasks_for_optimization(self):
        return self.tasks_for_optimization
    
    def get_tasks_ids_for_optimization(self):
        return self.tasks_ids_for_optimization

    def _handle_complex_paths(
        self, gateway_dict, gateway, xor_possible_paths_samples=None
    ):
        """
        Recursivly handle nested gateways. 
        
        return: complex distribution sample
        """
        #First check before everything
        if gateway not in self.all_tasks_duration_dict:
            #If its not in it means it was already handled by recursion
            return 

        all_paths_time_ordered = []
        paths_probability_ordered = []
        
        path_dict = gateway_dict[gateway]

        print("Path dictionary : ",path_dict)
        for key, path in path_dict.items():
            single_path_time = []
            for p in path:
                if isinstance(p, bpmn_types.ExclusiveGateway):
                    task_time = self._handle_complex_paths(
                        gateway_dict, p, xor_possible_paths_samples
                    )
                elif isinstance(p, bpmn_types.ParallelGateway):
                    task_time = self._handle_complex_paths(
                        gateway_dict, p
                    )
                elif isinstance(p, bpmn_types.Task):
                    task_time = self.all_tasks_duration_dict[p]
                elif isinstance(p, bpmn_types.Event):
                    #Placeholder for when we start handling Events
                    continue
                del self.all_tasks_duration_dict[p]
                if len(task_time) != 0:
                    single_path_time.append(task_time)
            print("Path : ",path)
            print("Single path : ", single_path_time)
            sum_of_single_path_time = sum(single_path_time)
            all_paths_time_ordered.append(sum_of_single_path_time)
            if isinstance(gateway, bpmn_types.ExclusiveGateway):
                paths_probability_ordered.append(self.path_probability_xor_dict[key])
                #Add single path to possible paths dictionary for that gateway
                xor_possible_paths_samples[gateway].extend(single_path_time)

        print("All paths time ordered : ", all_paths_time_ordered)
        if isinstance(gateway, bpmn_types.ExclusiveGateway):
            print(f"Handling {gateway}")
            #Check if probabilities == 1.0
            if sum(paths_probability_ordered) != 1.0:
                raise ValueError("Sum of all paths probabilites for specific XOR gateway must be 1.0")
            #List for mixed sample
            complex_mix_sample = []
            #Take random samples from distributions with size based on its probability
            for index, path in enumerate(all_paths_time_ordered):
                size_for_this_path = int(SAMPLE_SIZE * paths_probability_ordered[index])
                complex_mix_sample.append(numpy_random.choice(path, size=size_for_this_path, replace=False)) 
            #Convert list to numpy array
            np.asarray(complex_mix_sample, dtype=object)
            #Stack all arrays into one array
            complex_mix_sample = np.hstack(complex_mix_sample)
            #Check len of new sample -> must be == sample size
            if len(complex_mix_sample) != SAMPLE_SIZE:
                highest_path_probability = max(paths_probability_ordered)
                #TODO
                raise NotImplementedError("Add missing points to complex_mix_sample from highest probability path untill len(comlex_mix_sample) == sample__size")
            #Shuffle samples in complex mix -> essential otherwise it will give wrong results with summation
            numpy_random.shuffle(complex_mix_sample)
            print("Complex mix sample : ", complex_mix_sample)
            #print("Complex mix type : ", complex_mix_sample.dtype)
            print("*"*20)
        else:
            complex_maximum = reduce(
                lambda a, c: np.maximum(a, c),
                all_paths_time_ordered[1:],
                all_paths_time_ordered[0],
            )

            complex_mix_sample = complex_maximum

        return complex_mix_sample

    def _find_all_possible_paths(self, gateway):
        """
        Create all possible paths task duration from final all_task_duration_dict.
        This is used in case there is single or multiple XOR gateways in final all_task_duration_dict.
        Function will calculate process duration for each possible path workflow can take,
        which will in return give a single distribution for each path.

        return : all_possible_paths_tasks_duration = {path1 : [t1:[samples],xor_path1:[samples]...], path2 : [t1:[samples], xor_path2:[samples]...],....}
        """
        
        all_possible_paths_tasks_duration =  {}

        paths_in_gateway = self.xor_paths_dict[gateway]
        sample_location = 0
        path_counter = 0
        for _, path in paths_in_gateway.items():
            all_possible_paths_tasks_duration[path_counter] = []
            for p in path:
                if not isinstance(p, bpmn_types.ExclusiveGateway):
                    #At the moment Events are ignored since they don't have
                    #distribution associated with them. In the future this 
                    #if statement should be removed and Events should be handled
                    #same as Tasks
                    print(p)
                    print(self.xor_path_samples_dictionary[gateway][sample_location])
                    if isinstance(p, bpmn_types.Event):
                        all_possible_paths_tasks_duration[path_counter].append({p : np.zeros(shape=SAMPLE_SIZE)})
                        #This is so that Event doesn't mess up order...
                        sample_location -= 1
                    else:
                        all_possible_paths_tasks_duration[path_counter].append({p : self.xor_path_samples_dictionary[gateway][sample_location]})
                else:
                    possible_paths_in_xor = self._find_all_possible_paths(p)
                    path_until_xor  = all_possible_paths_tasks_duration[path_counter]
                    for key, value in possible_paths_in_xor.items():
                        all_possible_paths_tasks_duration[path_counter] = []
                        all_possible_paths_tasks_duration[path_counter].extend(path_until_xor)
                        all_possible_paths_tasks_duration[path_counter].extend(value)
                        path_counter += 1
                    path_counter -= 1
                sample_location += 1
            path_counter += 1
        print(f"Gateway in final all task duration : {gateway}")
        print(f"Possible paths : {len(all_possible_paths_tasks_duration.keys())}")
        
        return all_possible_paths_tasks_duration
   
    def _find_opened_gateway_for_current(self, merged_path_dict, current):
        print("*" * 10)
        print(f"Find open gateway for {current} :")
        for gateway, path_dict in merged_path_dict.items():
            for path, path_list in path_dict.items():
                for p in path_list:
                    if current == p:
                        print(f"Opened XOR is {gateway}")
                        return gateway


    def _find_correct_gateway_and_path(self, merged_path_dict, current):
        print("*" * 10)
        print("Find correct gateway and path:")
        for gateway, path_dict in merged_path_dict.items():
            for path, path_list in path_dict.items():
                for p in path_list:
                    if current == p:
                        print(f"Current {current} == {p} p ")
                        print("Just check : ", merged_path_dict[gateway][path])
                        return [gateway, path]
    
    def _handle_opening_target_gateway(self, c, target):
        #Add placeholder for all tasks inside gateway
        self.all_tasks_duration_dict[target] = None
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
        #If current element is also Gateway that means
        #that current element is also closing XOR/AND
        if isinstance(c, bpmn_types.Gateway):
            #Find opened gateway on this path, for 
            #current(closing) gateway using its opening
            #gateway. If this is the case current is 
            #nested gateway.
            opened_gateway_for_this_path = (
                self._find_opened_gateway_for_current(
                    {**self.xor_paths_dict, **self.and_paths_dict},
                    self.closing_to_opening_xor_dict[c],
                )
            )
        else:
            #If current element is not gateway trace 
            #back its opening gateway
            opened_gateway_for_this_path = (
                self._find_opened_gateway_for_current(
                    {**self.xor_paths_dict, **self.and_paths_dict}, c
                )
            )
        #Map closing target Gateway to its opening
        #gateway
        if isinstance(
            opened_gateway_for_this_path,
            bpmn_types.ExclusiveGateway,
        ):
            self.closing_to_opening_xor_dict[
                target
            ] = opened_gateway_for_this_path
        else:
            self.closing_to_opening_and_dict[
                target
            ] = opened_gateway_for_this_path


    def _plot_distribution(self, samples):
        plt.hist(samples, bins="auto",color="green")
        plt.show()

