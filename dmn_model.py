import xml.etree.ElementTree as ET
from dmn_types import *
from collections import deque
from copy import deepcopy

class DmnModel():
    def __init__(self, model_path):
        self.model_path = model_path
        self.decisions = {}

        model_tree = ET.parse(self.model_path)
        model_root = model_tree.getroot()
        decisions = model_root.findall("dmn:decision", NS)
        for decision in decisions:
            d = DMN_MAPPINGS["dmn:decision"]()
            d.parse(decision)
            self.decisions[d._id] = d

    async def create_instance(self, _id, bpmn_input_variables):
        instance = DmnInstance(_id, bpmn_input_variables, model = self)
        return instance
class DmnInstance():
    def __init__(self, _id, bpmn_input_variables, model):
        self._id = _id
        self.bpmn_input_variables = bpmn_input_variables
        self.model = model
        self.decisions = model.decisions
        self.decisions_queue = deque(self.sort_required_decision_list())
        
        print("Final Decision queue : ",self.decisions_queue)
    
    def sort_required_decision_list(self):
        helper_list = []
        for current, _ in self.model.decisions.items():
            helper_list.append(current)
            list_copy = deepcopy(helper_list)
            if not self.decisions[current].required_decisions:
                helper_list.remove(current)
                helper_list.insert(0, current)
                continue
            for pos,dec in enumerate(list_copy):
                #Current is required for decisions in helper list
                if current in self.decisions[dec].required_decisions:
                    #Current is already in good position
                    if helper_list.index(current) < helper_list.index(dec):
                        continue
                    #Put current before decision it is required for
                    else:
                        helper_list.remove(current)
                        helper_list.insert(pos,current)
                if dec in self.decisions[current].required_decisions:
                    #Current is before its required decision...
                    #I don't think this case is possible, but additional testing is needed 
                    if helper_list.index(current) < helper_list.index(dec):
                        print("Intervention needed")
        return helper_list
    
    async def run(self):
        decisions_queue = deepcopy(self.decisions_queue)
        input_variables = deepcopy(self.bpmn_input_variables)
        while decisions_queue:
            current_decision = decisions_queue.popleft()
            current_decision = self.decisions[current_decision]
            output = current_decision.run(input_variables)
            input_variables = {**output, **input_variables}
        return output

if __name__ == "__main__":
    d = DmnModel("models/test_dmn.dmn")
    i = DmnInstance(123, {"input_2":"test_2"}, d)
    #output = i.run()
    #print(output)
    #for k,v in d.decisions.items():
    #    print(v.decision_table.rules)