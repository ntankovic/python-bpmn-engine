import numpy as np
from functools import reduce

#New way to use numpy random
numpy_random = np.random.default_rng()

def calculate_gamma_shape(mean, std):
    return (mean/std)**2

def calculate_gamma_scale(mean, std):
    return std**2/mean

def calculate_exponential_lambda(mean):
    return 1/mean

def generate_distribution_with_different_size(distribution, sample_size):
    return numpy_random.choice(distribution, size=sample_size, replace=False)
def generate_gamma_distribution(mean,std,sample_size):
    shape = calculate_gamma_shape(mean,std)
    scale = calculate_gamma_scale(mean,std)
    return numpy_random.gamma(shape, scale, size=sample_size)

def generate_exponential_distribution(mean, sample_size):
    #Numpy uses scale parametar for generating exponential distribution.
    #Scale parametar is calculated as 1/lambda, which is also the mean
    return numpy_random.exponential(scale=mean, size=sample_size)

def generate_mix_distribution(distributions, weights, sample_size):
    #Check if probabilities == 1.0
    if sum(weights) != 1.0:
        raise ValueError(f"Sum of all paths probabilites for specific XOR gateway must be 1.0, recived : {weights}")
    #List for mixed sample
    mix_distribution = []
    #Take random samples from distributions with size based on its probability
    for index, distribution in enumerate(distributions):
        distribution_size = int(sample_size * weights[index])
        mix_distribution.append(numpy_random.choice(distribution, size=distribution_size, replace=False)) 
    #Concatenate all arrays into one array
    mix_distribution = np.concatenate(mix_distribution, axis=None)
    #Check len of new sample -> must be == sample size
    if len(mix_distribution) != sample_size:
        highest_path_probability = max(weights)
        #TODO
        raise NotImplementedError("Add missing points to mix_distribution from highest probability path untill len(comlex_mix_sample) == sample__size")
    #Shuffle samples in mix distribution -> essential otherwise it will give wrong results with summation
    numpy_random.shuffle(mix_distribution)
    return mix_distribution


def generate_max_distribution(distributions, cost=False):
    #If we are creating cost distribution for parallel gateway we still need
    #to pay for all tasks within parallel gateway not just the ones with
    #longest execution time
    if cost:
        max_distribution = sum(distributions)
        return max_distribution
    #As opposed to when we are calculating maximum duration for parallel gateway
    #we only need to take into consideration samples with highest execution time
    #since process can not continue unless all tasks have finished
    else:
        max_distribution = reduce(
            lambda a, c: np.maximum(a, c),
            distributions[1:],
            distributions[0],
        )
        return max_distribution



def generate_distribution(distribution_information, sample_size):
    distributions = []
    distributions_probabilities = []
    for distribution in distribution_information:
        distribution_weight = distribution_information[distribution].get("weight")
        #If weight is not None, then it's a mixture distribution
        if distribution_weight:
            distributions_probabilities.append(distribution_weight)
        #Find correct distribution
        if distribution_information[distribution].get("name") == "Gamma":
            mean = distribution_information[distribution].get("time_mean")
            std = distribution_information[distribution].get("time_std")
            distributions.append(generate_gamma_distribution(mean,std,sample_size))
        elif distribution_information[distribution].get("name") == "Exponential":
            mean = distribution_information[distribution].get("time_mean")
            distributions.append(generate_exponential_distribution(mean,sample_size))
    #If it's single distribution
    if len(distribution_information) == 1:
        return distributions[0]
    else:
        return generate_mix_distribution(distributions, distributions_probabilities, sample_size)

