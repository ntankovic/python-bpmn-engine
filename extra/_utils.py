def calculate_gamma_shape(mean, std):
    return (mean/std)**2

def calculate_gamma_scale(mean, std):
    return std**2/mean


