NS = {
    "dmn": "https://www.omg.org/spec/DMN/20191111/MODEL/"
}

DMN_MAPPINGS = {}

def dmn_tag(tag):
    def wrap(object):
        object.tag = tag
        DMN_MAPPINGS[tag] = object
        return object

    return wrap

class DmnObject(object):
    def __repr__(self):
        return f"{type(self).__name__}({self.name or self._id})"

    def parse(self, element):
        self._id = element.attrib["id"]
        self.name = element.attrib["name"] if "name" in element.attrib else None
    def run(self):
        return True

@dmn_tag("dmn:decision")
class Decision(DmnObject):
    def __init__(self):
        self.required_decisions = []
        self.decision_table = None
    def parse(self, element):
        super(Decision,self).parse(element)
        for req_decision in element.findall(".//dmn:requiredDecision", NS):
            self.required_decisions.append(req_decision.attrib["href"][1:])
        self.decision_table = DecisionTable()
        self.decision_table.parse(element.find("dmn:decisionTable",NS))
    def run(self, variables):
        return self.decision_table.run(variables)

class DecisionTable(DmnObject):
    def __init__(self):
        self.hit_policy = None
        self.input_variables = []
        self.output_names = []
        self.rules = []
    def parse(self,element):
        super(DecisionTable, self).parse(element)
        self.hit_policy = element.attrib["hitPolicy"] if "hitPolicy" in element.attrib else "UNIQUE"
        #The input expression determines the input value of a column 
        for input_expression in element.findall(".//dmn:inputExpression",NS):
            self.input_variables.append(input_expression.find("dmn:text",NS).text)
        for output in element.findall("dmn:output",NS):
            self.output_names.append(output.attrib["name"])
        for rule in element.findall("dmn:rule",NS):
            rule_dict = {"input":{}, "output":{}}
            for position, input_entry in enumerate(rule.findall("dmn:inputEntry",NS)):
                rule_dict["input"][self.input_variables[position]] = input_entry.find("dmn:text",NS).text
            for position, output_entry in enumerate(rule.findall("dmn:outputEntry",NS)):
                rule_dict["output"][self.output_names[position]] = output_entry.find("dmn:text",NS).text
            self.rules.append(rule_dict)
    
    @staticmethod
    def check_rule(rule, variables):
        check_list = []
        for column in rule:
            if not rule[column]:
                check_list.append(True)
                continue
            try:
                variables[column]
            except KeyError:
                check_list.append(False)
                continue
            if rule[column] == variables[column]:
                check_list.append(True)
            else:
                check_list.append(False)
        return all(check_list)
    
    def unique_hit_policy_run(self,variables):
        pass
    
    def first_hit_policy_run(self, variables):
        for rule in self.rules:
            if self.check_rule(rule["input"],variables):
                return rule["output"]
    
    def run(self, variables):
        if self.hit_policy == "UNIQUE":
            output = self.unique_hit_policy_run(variables)
        if self.hit_policy == "FIRST":
            output = self.first_hit_policy_run(variables)
        return output