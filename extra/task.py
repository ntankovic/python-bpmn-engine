class Task():
    def __init__(self, mean_time, cluster_type, task_id):
        self.mean_time = mean_time
        self.cluster_type = cluster_type
        self.task_id = task_id
    def calculate_time_based_on_cluster(self):
        #Starting cluster takes 20min ~= 0.3h
        cluster_starting_time = 0.3
        if self.cluster_type == 0:
            return self.mean_time + cluster_starting_time
        if self.cluster_type == 1:
            return self.mean_time / 1.2 + cluster_starting_time
        if self.cluster_type == 2:
            return self.mean_time / 3.4 + cluster_starting_time
        if self.cluster_type == 3:
            return self.mean_time / 6 + cluster_starting_time
    def calculate_cost_based_on_cluster(self):
        #Prices are based on Google Compute Engine, E2 standard machine type, europe-west3
        #Fixed cluster cost for running it
        fixed_cluster_cost = 0.02
        if self.cluster_type == 0:
            return self.mean_time * 0.086 + fixed_cluster_cost
        if self.cluster_type == 1:
            return self.mean_time * 0.17 + fixed_cluster_cost
        if self.cluster_type == 2:
            return self.mean_time * 0.34 + fixed_cluster_cost
        if self.cluster_type == 3:
            return self.mean_time * 0.69 + fixed_cluster_cost
    def __repr__(self):
        return f"{self.cluster_type} : {self.mean_time}"

def total_time(process):
    sum_time = [t.calculate_time_based_on_cluster() for t in process]
    return sum(sum_time)

def total_cost(process):
    sum_cost = [t.calculate_cost_based_on_cluster() for t in process]
    return sum(sum_cost)
