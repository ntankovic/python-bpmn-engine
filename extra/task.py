import time_distribution_probability as simulation
import json
import numpy as np
from copy import deepcopy
import os
import sys
#Get parent path so it's possible to import modules from parent directory
parent_path = os.path.abspath(os.path.split(sys.argv[0])[0]) + "/../"
sys.path.append(parent_path)
import bpmn_types

#New way to use numpy random
numpy_random = np.random.default_rng()

class AlternativeTask():
    def __init__(self,mean_time,optimization_part,task_id):
        self.mean_time = mean_time
        requirements = [optimization_part["cpu"], optimization_part["ram"]]
        self.cluster_type = Cluster(requirements)
        self.task_id = task_id
        #Parallel law parameters
        self.a = optimization_part["a"]
        self.b = optimization_part["b"]
        self.c = optimization_part["c"]
    
    def gustafson_law(self, N, p):
        #N -> number of processors 
        #p -> fraction of time executing the parallel parts
        return (1-p) + p*N

    def amdahl_law(self, N, p):
        #p -> fraction of time executing the parallel parts
        #N -> number of processors
        return 1/((1-p) + p/N)

    def get_json_load_for_task(self):
        temp = json.dumps(self.__dict__, default=lambda o: o.__dict__)
        return json.loads(temp)

    def calculate_time_based_on_cluster(self):
        #Starting cluster takes 20min ~= 0.3h
        cluster_starting_time = 0.3
        time = self.mean_time * self.cluster_type.parallel_law(self.a, self.b, self.c) + cluster_starting_time
        self.cluster_type.time_based_on_cluster = time
        return time
    def calculate_cost_based_on_cluster(self):
        #Fixed cluster cost for running it
        fixed_cluster_cost = 0.02
        if self.cluster_type.time_based_on_cluster is None:
            self.calculate_time_based_on_cluster()
        ec2_charges = self.cluster_type.time_based_on_cluster * self.cluster_type.ec2_cost() * self.cluster_type.nexec 
        emr_charges = self.cluster_type.time_based_on_cluster * self.cluster_type.emr_cost() * self.cluster_type.nexec 
        cost = ec2_charges + emr_charges + fixed_cluster_cost
        self.cluster_type.cost_based_on_cluster = cost
        return cost

class Cluster():
    #Location -> EU-Frankfurt
    #https://aws.amazon.com/ec2/instance-types/
    _possible_machine_type = {0:[4,32], 1:[8,64], 2:[16,128], 3:[32,256]}
    #https://aws.amazon.com/emr/pricing/?nc=sn&loc=4
    _machine_prices = [0.304, 0.608, 1.216, 2.432]
    _emr_machine_prices = [0.063, 0.126, 0.252, 0.27]
    #Possible number of clusters
    _possible_nexec = [1,4,9,16,25,36,49,64]

    def __init__(self, requirements, nexec=None):
        self.time_based_on_cluster = None
        self.cost_based_on_cluster = None
        self.machine_type = None
        self.nexec = nexec
        self.chose_machine_type(requirements)
        
    def chose_machine_type(self, requirements):
        for key, features in Cluster._possible_machine_type.items():
            if np.array_equal(features, requirements):
                self.machine_type = key
                if self.nexec is None:
                    self.nexec = self.chose_nexec(Cluster._possible_nexec)
                return

    def chose_nexec(self, nexec_choice):
        #Only reason to convert it from numpy int-> regular python int
        #is to make it easier to serialize to json.
        #This may be fixed in future updates.
        return int(numpy_random.choice(nexec_choice))

    def emr_cost(self):
        return Cluster._emr_machine_prices[self.machine_type]

    def ec2_cost(self):
        return Cluster._machine_prices[self.machine_type]

    def parallel_law(self, a, b, c):
        if self.nexec == 1:
            return 1
        else:
            return (a/self.nexec) + b * self.nexec**c

    def new_random_cluster_count(self):
        copy_possible_nexec = deepcopy(Cluster._possible_nexec)
        index = copy_possible_nexec.index(self.nexec)
        copy_possible_nexec.pop(index)
        self.nexec = self.chose_nexec(copy_possible_nexec)


def master_and_core_cost(time):
    #Master and Core cost per process
    #m5-2xlarge
    ec2 = time * 0.46
    emr = time * 0.096
    return 2*(ec2+emr)

SIMULATION_OBJECT = None

process_total_time_history = {}

def total_time(process):
    for t in process:
        t.calculate_time_based_on_cluster() 
    tasks = [x.get_json_load_for_task() for x in process]
    optimized_distribution = SIMULATION_OBJECT.create_optimized_total_distribution(tasks, plot=False, sample_size=100)[0]
    #Round for precision in 1 minute, more decimal points is currently 
    #unnecessary
    total_perc = np.round(np.percentile(optimized_distribution, 99), 3)
    total_time = np.round(np.mean(optimized_distribution),3)
    #History solution
    process = tuple(process)
    process_total_time_history[process] = float(total_time)
    return float(total_time), float(total_perc)

def total_cost(process):
    time = process_total_time_history[tuple(process)]
    master_and_core = master_and_core_cost(time)
    sum_cost = [t.calculate_cost_based_on_cluster() for t in process]
    #Round cost to 2 decimals, since cost is calculated in USD
    return np.round(sum(sum_cost) + master_and_core, 2)
