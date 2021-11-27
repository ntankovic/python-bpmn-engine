class BpmnModelIsNotDAG(Exception):
    def __init__(self, element):
        self.element = element._id
    def __str__(self):
        return f"{self.element} may be activated more then once during execution!"

class NoPathsInGivenConstraint(Exception):
    def __init__(self, start, end): 
        self.start = start
        self.end = end
    def __str__(self):
        return f"There are no paths in total for given range {self.start} - {self.end}"
