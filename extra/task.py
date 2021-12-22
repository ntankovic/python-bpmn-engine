import numpy as np
from copy import deepcopy

#New way to use numpy random
numpy_random = np.random.default_rng()

class Task():
    def __init__(self, mean_time, cluster_type, task_id):
        self.mean_time = mean_time
        self.cluster_type = cluster_type
        self.task_id = task_id
        self.requirments = None



    def gustafson_law(self, N, p):
        #N -> number of processors 
        #p -> fraction of time executing the parallel parts
        return (1-p) + p*N

    def amdahl_law(self, N, p):
        #p -> fraction of time executing the parallel parts
        #N -> number of processors
        return 1/((1-p) + p/N)



    def calculate_time_based_on_cluster(self):
        #Starting cluster takes 20min ~= 0.3h
        cluster_starting_time = 0.3
        #E2 machine type
        if self.cluster_type == 0:
            return self.mean_time + cluster_starting_time
        if self.cluster_type == 1:
            return self.mean_time / 1.5 + cluster_starting_time
        if self.cluster_type == 2:
            return self.mean_time / 3.4 + cluster_starting_time
        if self.cluster_type == 3:
            return self.mean_time / 6.1 + cluster_starting_time
        #N1 machine type
        if self.cluster_type == 4:
            return self.mean_time * 1.5 + cluster_starting_time
        if self.cluster_type == 5:
            return self.mean_time * 1.05 + cluster_starting_time
        if self.cluster_type == 6:
            return self.mean_time / 1.4 + cluster_starting_time
        if self.cluster_type == 7:
            return self.mean_time / 3.25 + cluster_starting_time
        
    def calculate_cost_based_on_cluster(self):
        #Prices are based on Google Compute Engine, E2 standard machine type, europe-west4
        #Fixed cluster cost for running it
        fixed_cluster_cost = 0.02
        #Virtual CPU - 2
        #Memory - 8gb
        if self.cluster_type == 0:
            return self.mean_time * 0.074 + fixed_cluster_cost
        #Virtual CPU - 4
        #Memory - 16gb
        if self.cluster_type == 1:
            return self.mean_time * 0.15 + fixed_cluster_cost
        #Virtual CPU - 8
        #Memory - 32gb
        if self.cluster_type == 2:
            return self.mean_time * 0.3 + fixed_cluster_cost
        #Virtual CPU - 16 
        #Memory - 64gb
        if self.cluster_type == 3:
            return self.mean_time * 0.59 + fixed_cluster_cost
        #N1 standard machine type, europe-west4
        #They are required for renting GPU and their prices will be later used
        #only when GPU is needed
        #Virtual CPU - 1
        #Memory - 3.75gb
        if self.cluster_type == 4:
            return self.mean_time * 0.05 + fixed_cluster_cost
        #Virtual CPU - 2
        #Memory - 7.5gb
        if self.cluster_type == 5:
            return self.mean_time * 0.10 + fixed_cluster_cost
        #Virtual CPU - 4
        #Memory - 15gb
        if self.cluster_type == 6:
            return self.mean_time * 0.21 + fixed_cluster_cost
        #Virtual CPU - 8
        #Memory - 30gb
        if self.cluster_type == 7:
            return self.mean_time * 0.42 + fixed_cluster_cost

    def __repr__(self):
        return f"{self.cluster_type} : {self.mean_time}"

class AlternativeTask():
    def __init__(self, mean_time, optimization_part, task_id):
        self.mean_time = mean_time
        requirements = [optimization_part["cpu"], optimization_part["ram"]]
        self.cluster_type = Cluster(requirements)
        self.task_id = task_id
        #Parallel law parameters
        self.a = optimization_part["a"]
        self.b = optimization_part["b"]
        self.c = optimization_part["c"]

    def calculate_time_based_on_cluster(self):
        #Starting cluster takes 20min ~= 0.3h
        cluster_starting_time = 0.3
        return self.mean_time * self.cluster_type.parallel_law(self.a, self.b, self.c) + cluster_starting_time

    def calculate_cost_based_on_cluster(self):
        #Fixed cluster cost for running it
        fixed_cluster_cost = 0.02
        return self.mean_time * self.cluster_type.cluster_cost() * self.cluster_type.nexec + fixed_cluster_cost


class Cluster():
    #Location -> EU-Frankfurt
    #https://aws.amazon.com/ec2/instance-types/
    possible_machine_type = {0:[4,32], 1:[8,64], 2:[16,128], 3:[32,256]}
    #https://aws.amazon.com/emr/pricing/?nc=sn&loc=4
    machine_prices = [0.304, 0.608, 1.216, 2.432]
    #Possible number of clusters
    possible_nexec = [1,4,9,16,25,36,49]

    def __init__(self, requirements):

        self.machine_type = None
        self.nexec = None
        self.chose_machine_type(requirements)
        
    def chose_machine_type(self, requirements):
        for key, features in Cluster.possible_machine_type.items():
            if np.array_equal(features, requirements):
                self.machine_type = key
                self.nexec = self.chose_nexec(Cluster.possible_nexec)
                return

    def chose_nexec(self, nexec_choice):
        #Only reason to convert it from numpy int-> regular python int
        #is to make it easier to serialize to json.
        #This may be fixed in future updates.
        return int(numpy_random.choice(nexec_choice))

    def cluster_cost(self):
        return Cluster.machine_prices[self.machine_type]

    def parallel_law(self, a, b, c):
        return (a/self.nexec) + b * self.nexec**c

    def new_random_cluster_count(self):
        copy_possible_nexec = deepcopy(Cluster.possible_nexec)
        index = copy_possible_nexec.index(self.nexec)
        copy_possible_nexec.pop(index)
        self.nexec = self.chose_nexec(copy_possible_nexec)



def total_time(process):
    sum_time = [t.calculate_time_based_on_cluster() for t in process]
    return sum(sum_time)

def total_cost(process):
    sum_cost = [t.calculate_cost_based_on_cluster() for t in process]
    return sum(sum_cost)
