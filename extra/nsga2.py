from .task import Task, total_cost, total_time
import numpy as np
import random
import matplotlib.pyplot as plt
from collections import defaultdict
import time
from tqdm import tqdm
from copy import deepcopy

def plot_parreto_front(processes):
    timeAxis = []
    costAxis = []
    for process in processes:
        timeAxis.append(total_time(process))
        costAxis.append(total_cost(process))
    plt.scatter(timeAxis, costAxis)
    plt.xlabel("Time")
    plt.ylabel("Cost")
    plt.title("Parreto front")
    plt.show()

def plot_parreto_front_with_previous_solutions(processes, previous_processes):
    timeAxis = []
    costAxis = []
    for process in processes:
        timeAxis.append(total_time(process))
        costAxis.append(total_cost(process))
    previous_time = [] 
    previous_cost = []
    for process in previous_processes:
        previous_time.append(total_time(process))
        previous_cost.append(total_cost(process))

    plt.scatter(previous_time,previous_cost, color = "lightgreen")
    plt.scatter(timeAxis,costAxis, color = "red")
    plt.xlabel("Time")
    plt.ylabel("Cost")
    plt.title("Pareto with previous generations from BPMN")
    plt.show()
        


def objective_function(process):
    #f1 -> objective 1
    process_time = total_time(process)
    #f2 -> objective 2
    process_cost = total_cost(process)
    return (process_time, process_cost)



def check_mathematical_domination(x1,x2):
    """
    https://en.wikipedia.org/wiki/Multi-objective_optimization
    Condition 1: x(1) is no worse than x(2) for all objectives
    Condition 2: x(1) is strictly better than x(2) in at least one objective
    """
    condition_one_objectives = []
    for pos,objective in enumerate(x1):
        if objective <= x2[pos]:
            condition_one_objectives.append(True)
        else:
            condition_one_objectives.append(False)
    if all(condition_one_objectives):
        for pos,objective in enumerate(x1):
            if objective < x2[pos]:
                return True
        #Condition 2 not met
        return False
    else:
        #Condition 1 not met
        return False

def fast_non_dominated_sorting(population):
    #Sorted fronts by level -> we return this
    fronts_by_level = defaultdict(list)
    
    #Dictionary collection of S_p and n_p for each p
    dictionary_collection_for_each_p = {}

    #For each individual p in main population
    for pos,p in enumerate(population):
        #print("Printing p :",p)
        #Set of all individuals that are dominated by p
        S_p = set()
        #Number of individuals that dominate p / domination counter
        n_p = 0
        #Create population without p
        if pos == 0:
            population_without_p = population[1:]
        elif pos == len(population)-1:
            population_without_p = population[:-1]
        else:
            population_without_p = population[:pos] + population[pos+1:]
        for q in population_without_p:
            #print("Printing q :",q)
            #if p is dominating q
            if check_mathematical_domination(p,q):
                #print("p is dominating q")
                S_p.add(q)
            #if q is dominating p
            elif check_mathematical_domination(q,p):
                #increase domination counter
                n_p += 1
        #print(f"N_p for {p} : {n_p}" )
        #If no individuals dominate p
        if n_p == 0:
            p_rank = 1
            fronts_by_level[p_rank].append(p)
        #Add S_p and n_p to helper dictionary -> needed for stage 2 of algorithm
        dictionary_collection_for_each_p[p] = {"S_p":S_p,"n_p":n_p}
    #Front counter
    i = 1
    #While front is nonempty
    while len(fronts_by_level[i]) != 0:
        #Set for storing individuals for i+1 front 
        Q = set()
        for p in fronts_by_level[i]:
            #print("P:",p)
            #print(dictionary_collection_for_each_p[p]["S_p"])
            for q in dictionary_collection_for_each_p[p]["S_p"]:
                #Initialize n_q for q -> from dictionary collection 
                n_q = dictionary_collection_for_each_p[q]["n_p"]
                #Decrement the domination count for q
                n_q -= 1
                #print("After :",q,n_q)
                #q belongs to the next front
                if n_q == 0:
                    #print("OK")
                    Q.add(q)
                #Update dictionary collection
                dictionary_collection_for_each_p[q]["n_p"] = n_q
        i += 1
        fronts_by_level[i] = list(Q)
        #print(fronts_by_level)
    #Delete empty last front
    del fronts_by_level[i] 
    return fronts_by_level
        

def crowding_distance_assigment(objective_scores_in_front):
    distance = dict()
    #Number of indivudials in front
    n = len(objective_scores_in_front)
    #Initialize distance 0 for all individuals in front
    for i in objective_scores_in_front:
        distance[i] = 0
    #For each objective function 
    for pos, _ in enumerate(objective_scores_in_front[0]):
        #Sort objective scores by m 
        objective_scores_in_front = sorted(objective_scores_in_front, key= lambda x: x[pos])
        #Assign infinite distance to boundry values
        distance[objective_scores_in_front[0]] = np.inf
        distance[objective_scores_in_front[-1]] = np.inf
        #Get minimum and maximum value for each objective in front
        fm_max = max(objective_scores_in_front, key= lambda x: x[pos])[pos]
        fm_min = min(objective_scores_in_front, key= lambda x: x[pos])[pos]
        #Calculate distance for the rest of individuals in front
        for k in range(1, n-1):
            distance[objective_scores_in_front[k]] += (objective_scores_in_front[k+1][pos] - objective_scores_in_front[k-1][pos])/fm_max-fm_min
    return distance

def crowded_comparison_operator(i, j, fronts_by_level, distances):
    """
    i and j are objective scores
    return: better objective score 
    """
    for level, objective_scores_for_solutions in fronts_by_level.items():
        for score in objective_scores_for_solutions:
            if score == i:
                i_rank = level
            if score == j:
                j_rank = level
    if (i_rank <= j_rank) and distances[i] > distances[j]:
        return i
    else:
        return j

def binary_tournament_selection_for_NSGA2(population, objective_scores_for_solutions, fronts_by_level, distances):
    possible_parents = random.choices(population, k=2)
    #One-liner way to get dict key from values...
    posible_parent_one_score = list(objective_scores_for_solutions.keys())[list(objective_scores_for_solutions.values()).index(possible_parents[0])]
    posible_parent_two_score = list(objective_scores_for_solutions.keys())[list(objective_scores_for_solutions.values()).index(possible_parents[1])]
    #Return better one from crowded comparison operator -> return solution
    return objective_scores_for_solutions[crowded_comparison_operator(posible_parent_one_score, posible_parent_two_score, fronts_by_level, distances)]

def single_point_crossover(parent_one, parent_two):
    #Select random crossover percentage
    crossover_percentage = random.uniform(0,1.0)
    #Make fixed crossover point
    crossover_point = int(len(parent_one)*crossover_percentage)
    #Split parents 
    first_part_of_parent_one = parent_one[:crossover_point]
    second_part_of_parent_one = parent_one[crossover_point:]
    first_part_of_parent_two = parent_two[:crossover_point]
    second_part_of_parent_two = parent_two[crossover_point:]
    #Make children
    child_one = first_part_of_parent_one + second_part_of_parent_two
    child_two = first_part_of_parent_two + second_part_of_parent_one

    return [child_one, child_two]

def mutation(child):
    for task in child: 
        if random.uniform(0.0,1.0) < 0.5:
            cluster_types = [0,1,2,3]
            cluster_types.pop(task.cluster_type)
            task.cluster_type = random.choice(cluster_types)
    return child

def generate_offspring_population(parent_population, objective_scores_for_solutions, fronts_by_level, distances, population_size):
    new_generation = []
    while len(new_generation) < population_size:
        children = []
        #Tournament phase
        parent_one = binary_tournament_selection_for_NSGA2(parent_population, objective_scores_for_solutions, fronts_by_level,distances)
        parent_two = binary_tournament_selection_for_NSGA2(parent_population, objective_scores_for_solutions, fronts_by_level,distances)
        #Crossover phase
        children = single_point_crossover(parent_one,parent_two)
        #Copy of children for loop
        children_copy = deepcopy(children)
        #Mutation phase
        for pos, child in enumerate(children_copy):
            if random.uniform(0.0,1.0) < 0.042:
                children[pos] = mutation(child)
        
        #print("Children :",children)
        #Add children in new generation
        new_generation.extend(children)
    return new_generation

def run_nsga2(tasks_mean_duration):
    tasks_durations = tasks_mean_duration
    process_size = len(tasks_durations)
    population_size = 100
    number_of_generations = 100

    mean_tasks_duration_on_normal_clusters = sum(tasks_durations)
    mean_tasks_cost_on_normal_clusters = sum(tasks_durations) * 0.086

    print("Mean time on normal cluster :",mean_tasks_duration_on_normal_clusters)
    print("Cost on normal cluster :", mean_tasks_cost_on_normal_clusters)

    #Population list
    solutions = []
    #Generate first generation of random solutions
    for s in range(population_size):
        process_tasks = []
        for i in range(process_size):
            process_tasks.append(Task(tasks_durations[i], random.choice([0,1,2,3])))
        solutions.append(process_tasks)

    #Diagnostics
    previous_solutions = []

    #Start Timer
    start = time.time()
    #Standard optimization loop
    for j in tqdm(range(number_of_generations)):
        #Diagnostics
        if j != number_of_generations - 1:
            previous_solutions.extend(solutions)

        #Generate objective score for each member of population -> save to dict for easy accessing
        objective_scores_for_solutions = {}
        for s in solutions:
            objective_scores_for_solutions[objective_function(s)] =  s
        
        #Create set of objective score to remove duplicates
        objective_scores_set = set(objective_scores_for_solutions)

        #Calculate fast-non-dominated-sort for all solutions -> send as list
        fronts_by_level = fast_non_dominated_sorting(list(objective_scores_set))

        #Diagnostics
        #for key,value in fronts_by_level.items():
        #    print(key,":", len(value))

        #Create new parent population -> P_t+1
        parent_population = list()
        
        #Front counter -> i
        front_level = 1
        #Shorter name -> just for convinience
        current_front = fronts_by_level[front_level]
        #Collection of all crowding distances  
        distances = {}
        #Until parent population is filled 
        while (len(parent_population) + len(fronts_by_level[front_level])) < population_size:
            #Reassign new level to current front
            current_front = fronts_by_level[front_level]
            #For debugging purposes, this should never happen
            if len(current_front) == 0:
                print(front_level)
                raise ValueError("Not good -> length of current front is 0")
            #Calculate crowding distance for all individuals in current front
            distances = {**distances,**crowding_distance_assigment(current_front)}
            #Add all solutions from current front to parent population
            for x in current_front:
                parent_population.append(objective_scores_for_solutions[x])
            front_level += 1
        
        ##Diagnostics
        #print("Parent after first loop : ", len(parent_population))
        #print("Len of current front : ", len(current_front))
        #print("Front level :", front_level)
        
        #Reassign new level to current front
        current_front = fronts_by_level[front_level]
        #If parent population is less then population size
        if (population_size - len(parent_population)) > 0:  
            #Calculate distances for last front
            distances = {**distances,**crowding_distance_assigment(current_front)}
            #Sort last front by Crowded-Comparison operator.
            #As they all on same front, meaning all have same rank,
            #only their distances must be check and sort in descending order
            current_front = sorted(current_front, key= lambda x: distances[x],reverse=True)
            #Take only n idividuals from last front, so that population size == parent population
            current_front = current_front[:population_size - len(parent_population)] 
            for score in current_front:
                parent_population.append(objective_scores_for_solutions[score])
        #Make new generation -> Q_t+1
        offspring_population = generate_offspring_population(parent_population, objective_scores_for_solutions, fronts_by_level,distances, population_size)
        #Merge parent and offspring population for next iteration
        solutions = [*parent_population, *offspring_population]

        ##Diagnostics
        #print("Parent :",len(parent_population))
        #print("Offspring :", len(offspring_population))
        #print("Solutions : ", len(solutions))
        #print("*"*20)

    #End Timer
    end = time.time() - start

    fronts_by_level[1] = sorted(fronts_by_level[1])
    print("Total time for last solution on pareto front from parent population : ", total_time(objective_scores_for_solutions[fronts_by_level[1][-1]]))
    print("Total cost for last solution on pareto front from parent population : ", total_cost(objective_scores_for_solutions[fronts_by_level[1][-1]]))
    from collections import Counter
    cluster_list = []
    for task in objective_scores_for_solutions[fronts_by_level[1][-1]]:
        cluster_list.append(task.cluster_type)
    print("Clusters for last solution on pareto front from parent population: ", Counter(cluster_list))
    #print(solutions)

    print("Time for NSGA2: ", end)
    #plot_parreto_front(solutions)
    plot_parreto_front_with_previous_solutions(solutions, previous_solutions)



