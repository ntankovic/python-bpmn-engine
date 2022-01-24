import task
import numpy as np
import random
import matplotlib.pyplot as plt
from collections import defaultdict
import time
from tqdm import tqdm
from copy import deepcopy
import json

#New way to use numpy random
numpy_random = np.random.default_rng()

def plot_parreto_front_with_previous_solutions(processes, previous_processes, chosen):
    timeAxis = []
    percAxis = []
    costAxis = []
    #print("Len of pareto :", len(processes))

    chosenParetoTimeAxis = []
    chosenParetoPercAxis = []
    chosenParetoCostAxis = []
    for index, process in enumerate(processes):
        #History solution
        process = tuple(process)
        time = solutions_time_and_cost_history[process]["time"]
        cost = solutions_time_and_cost_history[process]["cost"]
        perc = solutions_time_and_cost_history[process]["perc"]
        if index == chosen:
            chosenParetoTimeAxis.append(time)
            chosenParetoCostAxis.append(cost)
            chosenParetoPercAxis.append(perc)
            continue
        timeAxis.append(time)
        costAxis.append(cost)
        percAxis.append(perc)

    previous_time = [] 
    previous_cost = []
    previous_perc = []
    for index, process in enumerate(previous_processes):
        #History solution
        process = tuple(process)
        time = solutions_time_and_cost_history[process]["time"]
        cost = solutions_time_and_cost_history[process]["cost"]
        perc = solutions_time_and_cost_history[process]["perc"]
        previous_time.append(time)
        previous_cost.append(cost)
        previous_perc.append(perc)

    #Plot for two variables in objective function
    #plt.figure(figsize=(4.8,4.0))
    #previous = plt.scatter(previous_time,previous_cost, color = "cadetblue", s=2)
    #final = plt.scatter(timeAxis,costAxis, color = "navy", s=10)
    #chosen = plt.scatter(chosenParetoTimeAxis, chosenParetoCostAxis, color="crimson", s=10)
    #plt.xlabel("Duration in hours")
    #plt.ylabel("Cost in USD")
    #plt.legend([previous, final, chosen],["Previous generations","Pareto front","Proposed Pareto solution"])
    #plt.title("Pareto front with previous generations\nfor resource allocation")
    #plt.show()

    #3D scatter plot for three variables in objective function
    fig = plt.figure(figsize=(4.8,4.0))
    ax = fig.add_subplot(projection="3d")

    final = ax.scatter3D(percAxis,timeAxis , costAxis,color = "navy", s=10, alpha=0.7)
    #Create visual height for scatter
    for i,j,k in zip(percAxis, timeAxis, costAxis):
        #linestyle=(0,(1,8)) == loosely dotted line
        ax.plot([i,i],[j,j],[0,k], linestyle=(0, (1,8)), linewidth=0.8, color="navy")
    chosen = ax.scatter3D(chosenParetoPercAxis,chosenParetoTimeAxis , chosenParetoCostAxis, color="crimson", s=10, alpha=1.0)
    for i,j,k in zip(chosenParetoPercAxis, chosenParetoTimeAxis, chosenParetoCostAxis):
        ax.plot([i,i],[j,j],[0,k], linestyle=(0, (1,8)), linewidth=0.8, color="crimson")

    ax.set_ylabel("Mean duration in hours")
    ax.set_xlabel("99 percentile duration in hours")
    ax.set_zlabel("Mean cost in USD")
    plt.legend([final, chosen],["Pareto front","Proposed Pareto solution"],loc="best")
    plt.title("Pareto front for resource allocation")
    plt.show()

    #Plot for three variables in objective function
    fig, axis = plt.subplots(nrows=1, ncols=2, figsize=(10.0,3.5))
    #Set main title and adjust layout
    fig.suptitle("Pareto front with previous generations\nfor resource allocation", fontsize=11)
    fig.subplots_adjust(top=0.75, wspace=0.28)

    #Previous solutions
    previous_zero = axis[0].scatter(previous_time,previous_cost, color = "cadetblue", s=2)
    #Final solutions
    final_zero = axis[0].scatter(timeAxis,costAxis, color = "navy", s=10)
    #Chosen solution
    chosen_zero = axis[0].scatter(chosenParetoTimeAxis, chosenParetoCostAxis, color="crimson", s=10)
    axis[0].set_ylabel("Mean cost in USD")
    axis[0].set_xlabel("Mean duration in hours")
    axis[0].set_title("Mean duration and cost\nfor the process", fontsize=10)
    #axis[0].legend([previous_zero, final_zero, chosen_zero],["Previous generations","Pareto front","Proposed Pareto solution"])

    #Previous solutions
    previous_one = axis[1].scatter(previous_perc,previous_cost, color = "cadetblue", s=2)
    #Final solutions
    final_one = axis[1].scatter(percAxis,costAxis, color = "navy", s=10)
    #Chosen solution
    chosen_one = axis[1].scatter(chosenParetoPercAxis, chosenParetoCostAxis, color="crimson", s=10)
    axis[1].set_ylabel("Mean cost in USD")
    axis[1].set_xlabel("99 percentile duration in hours")
    axis[1].set_title(f"99 percentile duration and mean cost\nfor the process", fontsize=10)
    fig.legend([previous_one, final_one, chosen_one],["Previous generations","Pareto front","Proposed Pareto solution"], loc="center right", borderaxespad=0.8)
    plt.subplots_adjust(right=0.75)
    plt.show()


def objective_function(process):
    #f1 -> objective 1
    process_time, process_99_perc = task.total_time(process)
    #f2 -> objective 2
    process_cost = task.total_cost(process)

    process = tuple(process)
    solutions_time_and_cost_history[process] = {}
    solutions_time_and_cost_history[process]["time"] = process_time
    solutions_time_and_cost_history[process]["perc"] = process_99_perc
    solutions_time_and_cost_history[process]["cost"] = process_cost
    return (process_time, process_99_perc, process_cost)
    #return (process_99_perc, process_cost)
    #return (process_time, process_cost)



def check_mathematical_domination(x1,x2):
    """
    Condition 1: x(1) is no worse than x(2) for all objectives ( x(1) <= x(2) )
    Condition 2: x(1) is strictly better than x(2) in at least one objective
    """
    for pos,objective in enumerate(x1):
        if objective > x2[pos]:
            #Condition 1 not met
            return False
    for pos,objective in enumerate(x1):
        if objective < x2[pos]:
            return True
    #Condition 2 not met
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
        #Number of individuals that dominate p <- domination counter
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
            distance[objective_scores_in_front[k]] += abs((objective_scores_in_front[k+1][pos] - objective_scores_in_front[k-1][pos])/fm_max-fm_min)
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

    #Compare solutions
    if (i_rank <= j_rank) and distances[i] > distances[j]:
        return i
    else:
        return j

def binary_tournament_selection_for_NSGA2(population, objective_scores_for_solutions, fronts_by_level, distances):
    possible_parents = random.choices(population, k=2)
    #One-liner way to get dict key from values...
    #posible_parent_one_score = list(objective_scores_for_solutions.keys())[list(objective_scores_for_solutions.values()).index(possible_parents[0])]
    #posible_parent_two_score = list(objective_scores_for_solutions.keys())[list(objective_scores_for_solutions.values()).index(possible_parents[1])]
    #History solutions
    posible_parent_one_score = solution_with_objective_score_history[tuple(possible_parents[0])]    
    posible_parent_two_score = solution_with_objective_score_history[tuple(possible_parents[1])]
    #Return better one from crowded comparison operator -> return solution
    return objective_scores_for_solutions[crowded_comparison_operator(posible_parent_one_score, posible_parent_two_score, fronts_by_level, distances)]

def uniform_crossover(parent_one, parent_two):
    #Select uniform crossover
    uniform_coin_flip = numpy_random.uniform(0.0,1.0, size=len(parent_one))
    #Allocate children
    child_one = []
    child_two = []
    #Make crossover
    for index, flip in enumerate(uniform_coin_flip):
        #Add single gene from parent to child
        if flip < 0.5:
            child_one.append(parent_one[index])
            child_two.append(parent_two[index])
        #Switch parents 
        else:
            child_one.append(parent_two[index])
            child_two.append(parent_one[index])

    return [child_one, child_two]

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
        #Every task in process will mutate
        task.cluster_type.new_random_cluster_count()
    return child

def generate_offspring_population(parent_population, objective_scores_for_solutions, fronts_by_level, distances, population_size):
    new_generation = []
    while len(new_generation) < population_size:
        children = []
        #Tournament phase
        parent_one = binary_tournament_selection_for_NSGA2(parent_population, objective_scores_for_solutions, fronts_by_level,distances)
        #Remove parent one from parent population so that it can not be chosen
        #more then once
        #parent_population.pop(parent_population.index(parent_one))
        parent_two = binary_tournament_selection_for_NSGA2(parent_population, objective_scores_for_solutions, fronts_by_level,distances)
        #Add parent one back to population after parent two has been selected
        #parent_population.append(parent_one)
        #Crossover phase
        #children = single_point_crossover(parent_one,parent_two)
        children = uniform_crossover(parent_one, parent_two)
        #Copy of children for loop
        children_copy = deepcopy(children)

        #Mutation phase
        for pos, child in enumerate(children_copy):
            if random.uniform(0.0,1.0) < 0.2345:
                children[pos] = mutation(child)
        
        #print("Children :",children)
        #Add children in new generation
        new_generation.extend(children)
    return new_generation

solutions_time_and_cost_history = {}
solution_with_objective_score_history = {}
nexec_combination_time_and_cost_history = {}

def run(tasks_from_bpmn, tasks_ids, population_size=35, generations=50, plot=True, json=False):
    #tasks_durations = tasks_from_bpmn
    #Alternative solution
    tasks_durations = tasks_from_bpmn["mean time"]
    #print(tasks_durations)
    tasks_requirments = tasks_from_bpmn["requirements"]
    task.SIMULATION_OBJECT = tasks_from_bpmn["simulation object"]
    #End Alternative solution

    tasks_ids = tasks_ids
    process_size = len(tasks_durations)
    population_size = population_size
    generations = generations

    #Total nsga2 timer
    start_total_timer = time.time()

    #Population list
    solutions = []
    #Generate first generation of random solutions
    for s in range(population_size):
        process_tasks = []
        for i in range(process_size):
            #Alternative solution
            process_tasks.append(task.AlternativeTask(tasks_durations[i], tasks_requirments[i], tasks_ids[i] ))
        solutions.append(process_tasks)

    objective_scores_for_solutions = {}
    for s in solutions:
        nexec_combination = [ x.cluster_type.nexec for x in s]
        score = objective_function(s)
        solution_with_objective_score_history[tuple(s)]= score
        nexec_combination_time_and_cost_history[tuple(nexec_combination)] = score
        objective_scores_for_solutions[score] =  s
    
    #Calculate fast-non-dominated-sort for all solutions -> send as list
    fronts_by_level = fast_non_dominated_sorting(list(objective_scores_for_solutions))
    distances = {}
    for front in list(fronts_by_level):
        current_front = fronts_by_level[front]
        #Calculate crowding distance for all individuals in current front
        distances = {**distances,**crowding_distance_assigment(current_front)}

    offspring_population = generate_offspring_population(solutions, objective_scores_for_solutions, fronts_by_level, distances, population_size)
    #Merge parent and offspring population for start of optimization
    solutions =[*solutions, *offspring_population]

    #Colletion of previous solutions for plot
    previous_solutions = []

    #Standard optimization loop
    for gen in range(generations):
        print("-"*10,f"Generation {gen}","-"*10)
        #Start Timer
        start = time.time()
        #Diagnostics
        if gen != generations - 1:
            previous_solutions.extend(solutions)

        #Generate objective score for each member of population -> save to dict for easy accessing
        for s in solutions:
            nexec_combination = [ x.cluster_type.nexec for x in s]
            try:
                score = nexec_combination_time_and_cost_history[tuple(nexec_combination)]
                solution_with_objective_score_history[tuple(s)]= score
                #Get previous process with same score
                previous_process = list(solution_with_objective_score_history.keys())[list(solution_with_objective_score_history.values()).index(score)]
                solutions_time_and_cost_history[tuple(s)] = solutions_time_and_cost_history[previous_process]
            except KeyError:
                score = objective_function(s)
                solution_with_objective_score_history[tuple(s)] = score
                nexec_combination_time_and_cost_history[tuple(nexec_combination)] = score
            objective_scores_for_solutions[score] =  s
        

        print("Nexec solutions combinations so far : ", len(list(nexec_combination_time_and_cost_history)))
        print("Len of objective scores in current generation :", len(list(objective_scores_for_solutions)))
        #print("Begining non dominated sorting")

        #Calculate fast-non-dominated-sort for all solutions -> send as list
        fronts_by_level = fast_non_dominated_sorting(list(objective_scores_for_solutions))
        print("Len of front 1 :",len(fronts_by_level[1]))

        #Create new parent population -> P_t+1
        parent_population = list()
        
        #Front counter -> i
        front_level = 1
        #Shorter name -> just for convinience
        current_front = fronts_by_level[front_level]
        #Collection of all crowding distances  
        distances = {}
        #Until parent population is filled 
        while (len(parent_population) + len(fronts_by_level[front_level])) <= population_size:
            #Reassign new level to current front
            current_front = fronts_by_level[front_level]
            #For debugging purposes, this should never happen
            if len(current_front) == 0:
                print("Current front :", front_level)
                print("Population on front :", len(fronts_by_level[front_level]))
                print("Parent population :", len(parent_population))
                print("Population size :", population_size)
                raise ValueError(f"Not good -> length of current front {front_level} is 0")
            #Calculate crowding distance for all individuals in current front
            distances = {**distances,**crowding_distance_assigment(current_front)}
            #Add all solutions from current front to parent population
            for x in current_front:
                parent_population.append(objective_scores_for_solutions[x])
            #print(f"Parent population after rank {front_level} : {len(parent_population)}")
            front_level += 1
            #If it's last generation we just need pareto solutions
            if gen == generations-1:
                #print("It's last generation")
                break
        
        #Reassign new level to current front
        current_front = fronts_by_level[front_level]
        ##Diagnostics
        #print("Parent after first loop : ", len(parent_population))
        #print("Front level :", front_level)
        #print("Len of current front : ", len(current_front))
        
        #If parent population is less then population size
        if (population_size - len(parent_population)) > 0:
            #Calculate distances for last front
            distances = {**distances,**crowding_distance_assigment(current_front)}
            #Sort last front by Crowded-Comparison operator.
            #As they all on same front, meaning all have same rank,
            #only their distances must be check and sort in descending order,
            #so that better solutions goes to the next generation
            current_front = sorted(current_front, key= lambda x: distances[x],reverse=True)
            #If it's last generation and front level is 1 take all solutions 
            #from that front, aka pareto solutions
            if gen == generations-1 and front_level == 1:
                current_front = current_front[:]
            #If it's last generation and it's not the first front,
            #just return pareto solutions
            elif gen == generations-1 and front_level != 1:
                #print("It's last generation and front level is not 1")
                solutions = parent_population
                continue
            else:
                #Take only n idividuals from last front, so that population size == parent population
                current_front = current_front[:population_size - len(parent_population)] 
            for score in current_front:
                parent_population.append(objective_scores_for_solutions[score])
        
        #It's last generation and we took all solutions from the first front
        if gen == generations-1:
            #print("Its last generation")
            solutions = parent_population
            continue

        #Make new generation -> Q_t+1
        offspring_population = generate_offspring_population(parent_population, objective_scores_for_solutions, fronts_by_level, distances, population_size)
        #Merge parent and offspring population for next iteration
        solutions =[*parent_population, *offspring_population]

        #Create empty storage for new generation
        objective_scores_for_solutions = {}

        ##Diagnostics
        #print("Parent :",len(parent_population))
        #print("Offspring :", len(offspring_population))
        #print("Solutions : ", len(solutions))
        #End Timer
        end = time.time() - start
        print(f"Time for generation {gen} : {end}")


    print("Total nsga2 time in minutes : ", (time.time()-start_total_timer)/60)

    chosen = int(len(solutions)/2)

    if plot:
        plot_parreto_front_with_previous_solutions(solutions, previous_solutions, chosen)
    if json:
        return convert_solutions_to_json(solutions[chosen])
    else:
        return solutions

def convert_solutions_to_json(solutions):
    """
    Converts solutions to json so they can be displayed on frontend.
    In the future this function should be objective function agnostic.
    """
    json_solutions = {}
    json_solutions["solutions"] = []
    #This means it's list of lists
    if all(isinstance(x, list) for x in solutions):
        for solution in solutions:
            create_json_solution(json_solutions, solution)
    else:
        #This is single list solution
        create_json_solution(json_solutions, solutions, single_solution=True)
    return json_solutions
        
def create_json_solution(json_dict, solution, single_solution=False):
    s = {}
    #Alternative task solution
    process = tuple(solution)
    solution_time = solutions_time_and_cost_history[process]["time"]
    solution_cost = solutions_time_and_cost_history[process]["cost"] 
    tasks_list = []
    for task in solution:
        tasks_list.append(json.dumps(task.__dict__, default=lambda o: o.__dict__))
    s["time"] = solution_time
    s["cost"] = solution_cost
    s["tasks_list"] = tasks_list
    if single_solution:
        json_dict["solutions"] = s
    else:
        json_dict["solutions"].append(s)

