class Task():
    def __init__(self, mean_time, cluster_type, task_id):
        self.mean_time = mean_time
        self.cluster_type = cluster_type
        self.task_id = task_id
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
            return self.mean_time * 0.5 + cluster_starting_time
        if self.cluster_type == 5:
            return self.mean_time * 0.01 + cluster_starting_time
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

def total_time(process):
    sum_time = [t.calculate_time_based_on_cluster() for t in process]
    return sum(sum_time)

def total_cost(process):
    sum_cost = [t.calculate_cost_based_on_cluster() for t in process]
    return sum(sum_cost)
