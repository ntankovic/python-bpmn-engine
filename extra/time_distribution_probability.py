import bpmn_types
from .nsga2 import run_nsga2
from copy import deepcopy
from collections import OrderedDict, defaultdict
from functools import reduce
import time
import numpy as np
import matplotlib.pyplot as plt

#New way to use numpy random
numpy_random = np.random.default_rng()

SAMPLE_SIZE = 1000000
DISTRIBUTION = numpy_random.gamma

#Temporary solution
tasks_mean_duration = []

def calculate_gamma_shape(mean, std):
    return (mean/std)**2

def calculate_gamma_scale(mean, std):
    return std**2/mean

def handle_time_distribution_probability(model):
    start = time.time()

    flows = deepcopy(model.flow)
    pending_copy = deepcopy(model.pending)
    pending_history = []

    helper_incoming_gateway_dict = {
        model.elements[x]: 0
        for x in flows
        if isinstance(model.elements[x], bpmn_types.Gateway)
    }

    all_tasks_duration_dict = OrderedDict()

    path_probability_xor_dict = {}
    xor_paths_dict = {}
    closing_to_opening_xor_dict = {}

    and_paths_dict = {}
    closing_to_opening_and_dict = {}

    while len(pending_copy) > 0:
        print("-" * 50)
        print("Outside : ", pending_copy)
        helper_pending = []
        for c in pending_copy:
            print("+" * 20)
            print("CURRENT TASK : ", c)
            if isinstance(c, bpmn_types.Task):
                #Temporary solution
                tasks_mean_duration.append(c.expected_time["time_mean"])
                shape = calculate_gamma_shape(c.expected_time["time_mean"],c.expected_time["time_std"])
                scale = calculate_gamma_scale(c.expected_time["time_mean"],c.expected_time["time_std"])
                task_distribution = DISTRIBUTION(
                    shape, scale, size=SAMPLE_SIZE
                )
                all_tasks_duration_dict[c] = task_distribution
            
            idx = pending_copy.index(c)
            pending_history.append(pending_copy[idx])

            # Get next target in flow
            for index, sequence in enumerate(flows[c._id]):
                target = model.elements[sequence.target]
                print(sequence)
                print("Target : ", target)
                if isinstance(target, bpmn_types.Gateway):
                    helper_incoming_gateway_dict[target] += 1
                    if (
                        target not in helper_pending
                        and target.incoming == helper_incoming_gateway_dict[target]
                    ):
                        helper_pending.append(target)
                        if isinstance(target, bpmn_types.ParallelGateway):
                            if not and_paths_dict.get(target):
                                and_paths_dict[target] = {}
                        if isinstance(target, bpmn_types.ExclusiveGateway):
                            if not xor_paths_dict.get(target):
                                xor_paths_dict[target] = {}
                        # If its more then 1 outgoing -> opening XOR/AND
                        if target.outgoing > 1:
                            # Add placeholder for all tasks inside gateway
                            all_tasks_duration_dict[target] = None
                            #Find correct gateway inside xor_paths_dict and and_paths_dict
                            correct_gateway_and_path = find_correct_gateway_and_path(
                                {**xor_paths_dict, **and_paths_dict}, c
                            )
                            #If current is inside AND or XOR 
                            if correct_gateway_and_path:
                                if isinstance(
                                    correct_gateway_and_path[0],
                                    bpmn_types.ExclusiveGateway,
                                ):
                                    xor_paths_dict[correct_gateway_and_path[0]][
                                        correct_gateway_and_path[1]
                                    ].append(target)
                                else:
                                    and_paths_dict[correct_gateway_and_path[0]][
                                        correct_gateway_and_path[1]
                                    ].append(target)
                        # Else -> closing XOR/AND
                        else:
                            if isinstance(c, bpmn_types.Gateway):
                                opened_gateway_for_this_path = (
                                    find_opened_gateway_for_current(
                                        {**xor_paths_dict, **and_paths_dict},
                                        closing_to_opening_xor_dict[c],
                                    )
                                )
                                closing_to_opening_xor_dict[
                                    target
                                ] = opened_gateway_for_this_path
                            else:
                                opened_gateway_for_this_path = (
                                    find_opened_gateway_for_current(
                                        {**xor_paths_dict, **and_paths_dict}, c
                                    )
                                )
                                if isinstance(
                                    opened_gateway_for_this_path,
                                    bpmn_types.ExclusiveGateway,
                                ):
                                    closing_to_opening_xor_dict[
                                        target
                                    ] = opened_gateway_for_this_path
                                else:
                                    closing_to_opening_and_dict[
                                        target
                                    ] = opened_gateway_for_this_path

                elif isinstance(target, bpmn_types.Task):
                    if isinstance(c, bpmn_types.ExclusiveGateway):
                        xor_paths_dict[c][target] = []
                        xor_paths_dict[c][target].append(target)
                    if isinstance(c, bpmn_types.ParallelGateway):
                        and_paths_dict[c][target] = []
                        and_paths_dict[c][target].append(target)
                    if isinstance(c, bpmn_types.Task):
                        correct_gateway_and_path = find_correct_gateway_and_path(
                            {**xor_paths_dict, **and_paths_dict}, c
                        )
                        print("Correct gateway : ", correct_gateway_and_path)
                        if correct_gateway_and_path:
                            if isinstance(
                                correct_gateway_and_path[0], bpmn_types.ExclusiveGateway
                            ):
                                xor_paths_dict[correct_gateway_and_path[0]][
                                    correct_gateway_and_path[1]
                                ].append(target)
                            else:
                                and_paths_dict[correct_gateway_and_path[0]][
                                    correct_gateway_and_path[1]
                                ].append(target)
                    if target not in helper_pending:
                        helper_pending.append(target)
                else:
                    if target not in helper_pending:
                        helper_pending.append(target)
                # Check if more then 1 flow
                if len(flows[c._id]) > 1:
                    if isinstance(c, bpmn_types.ExclusiveGateway):
                        print("Decision outcome for ", c, " : ", c.decision_outcome)
                        path_probability_xor_dict[target] = c.decision_outcome[index]

        pending_copy = []
        for x in helper_pending:
            if x not in pending_history:
                pending_copy.append(x)

    print("-" * 50)
    print("All tasks duration dict : ")
    print(all_tasks_duration_dict)
    print("-" * 50)
    print("XOR paths dict : ")
    print(xor_paths_dict)
    print("-" * 50)
    print("Path probability xor dict : ")
    print(path_probability_xor_dict)
    print("-" * 50)
    print("AND paths dict : ")
    print(and_paths_dict)
    print("-" * 50)
    print("Incoming gateway dict : ")
    print(helper_incoming_gateway_dict)
    print("-" * 50)
    print("Closing to opening XOR dict : ")
    print(closing_to_opening_xor_dict)
    print("-" * 50)
    print("Closing to opening AND dict : ")
    print(closing_to_opening_and_dict)
    print("-" * 50)
    
    #Create list of gateways in order they appear in the model
    ordered_gateway_list = []
    for key in all_tasks_duration_dict:
        if isinstance(key,bpmn_types.Gateway):
            ordered_gateway_list.append(key)
   
    #Posible paths dictionary
    xor_path_samples_dictionary = defaultdict(list)

    # Handle complex gateways - PYMC3
    for i, gateway in enumerate(ordered_gateway_list):
        print(gateway)
        task_time = handle_complex_paths(
            {**xor_paths_dict,**and_paths_dict},
            all_tasks_duration_dict,
            gateway,
            path_probability_xor_dict,
            xor_path_samples_dictionary
        )
        if task_time is not None:
            if len(task_time) != 0:
                all_tasks_duration_dict[gateway] = task_time
        print("-" * 10)

    print("-" * 50)
    print("All tasks duration dict : ")
    print(all_tasks_duration_dict)
    print("-" * 50)

    all_tasks_duration_list = []
    for key, duration in all_tasks_duration_dict.items():
        all_tasks_duration_list.append(duration)

    # Finishing algorithm
    total = sum(all_tasks_duration_list)

    #Plot final distribution    
    plt.hist(total, bins="auto",color="green")
    print(f"time : {time.time()-start}")
    plt.show()

    #Additional stuff
    print("-"*50)
    print("Additional")
    find_path_given_duration_constraint(100, 152, all_tasks_duration_dict, xor_path_samples_dictionary, xor_paths_dict)

    run_nsga2(tasks_mean_duration)
    
def handle_complex_paths(
    gateway_dict, all_tasks_duration, gateway, path_probability=None, xor_possible_paths_samples=None
):
    #First check before everything
    if gateway not in all_tasks_duration:
        return
    
    all_paths_time_ordered = []
    paths_probability_ordered = []
    
    path_dict = gateway_dict[gateway]
    if not path_dict:
        return

    print("Path dictionary : ",path_dict)
    for key, path in path_dict.items():
        single_path_time = []
        for p in path:
            if isinstance(p, bpmn_types.ExclusiveGateway):
                task_time = handle_complex_paths(
                    gateway_dict, all_tasks_duration, p, path_probability, xor_possible_paths_samples
                )
            elif isinstance(p, bpmn_types.ParallelGateway):
                task_time = handle_complex_paths(
                    gateway_dict, all_tasks_duration, p
                )
            elif isinstance(p, bpmn_types.Task):
                task_time = all_tasks_duration[p]
            del all_tasks_duration[p]
            if len(task_time) != 0:
                single_path_time.append(task_time)
        print("Path : ",path)
        print("Single path : ", single_path_time)
        sum_of_single_path_time = sum(single_path_time)
        all_paths_time_ordered.append(sum_of_single_path_time)
        if isinstance(gateway, bpmn_types.ExclusiveGateway):
            paths_probability_ordered.append(path_probability[key])
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


def find_opened_gateway_for_current(merged_path_dict, current):
    print("*" * 10)
    print(f"Find open gateway for {current} :")
    for gateway, path_dict in merged_path_dict.items():
        for path, path_list in path_dict.items():
            for p in path_list:
                if current == p:
                    print(f"Opened XOR is {gateway}")
                    return gateway


def find_correct_gateway_and_path(merged_path_dict, current):
    print("*" * 10)
    print("Find correct gateway and path:")
    for gateway, path_dict in merged_path_dict.items():
        for path, path_list in path_dict.items():
            for p in path_list:
                if current == p:
                    print(f"Current {current} == {p} p ")
                    print("Just check : ", merged_path_dict[gateway][path])
                    return [gateway, path]


def find_all_possible_paths(gateway, xor_path_samples_dictionary, xor_paths_dict):
    """
    Create all possible paths task duration from final all_task_duration_dict.
    This is used in case there is single or multiple XOR gateways in final all_task_duration_dict.
    Function will calculate process duration for each possible path workflow can take,
    which will in return give a single distribution for each path.

    return : all_possible_paths_tasks_duration = {path1 : [t1:[samples],xor_path1:[samples]...], path2 : [t1:[samples], xor_path2:[samples]...],....}
    """
    
    all_possible_paths_tasks_duration =  {}

    paths_in_gateway = xor_paths_dict[gateway]
    sample_location = 0
    path_counter = 0
    for _, path in paths_in_gateway.items():
        all_possible_paths_tasks_duration[path_counter] = []
        for p in path:
            if not isinstance(p, bpmn_types.ExclusiveGateway):
                all_possible_paths_tasks_duration[path_counter].append({p : xor_path_samples_dictionary[gateway][sample_location]})
            else:
                possible_paths_in_xor = find_all_possible_paths(p,xor_path_samples_dictionary, xor_paths_dict)
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

def find_path_given_duration_constraint(start, end, all_tasks_duration_dict, xor_path_samples_dictionary, xor_paths_dict):
    """

    return : path where "start <= total time distribution <= end"
    """
    possible_paths_for_xor = {}
    all_possible_paths = {}
    for key in all_tasks_duration_dict:
        if isinstance(key, bpmn_types.ExclusiveGateway):
            print(f"Handling {key}")
            possible_paths_for_xor[key] = find_all_possible_paths(key, xor_path_samples_dictionary, xor_paths_dict)

    path_counter = 0
    all_possible_paths[path_counter] = []
    for key, samples in all_tasks_duration_dict.items():
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
        return total_tasks_for_each_path[winner_path]
    else:
        print("No paths in given duration constraint")
        return None

