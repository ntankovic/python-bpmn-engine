import requests
import os
import env
from utils.common import parse_expression

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "camunda": "http://camunda.org/schema/1.0/bpmn",
}

BPMN_MAPPINGS = {}


def bpmn_tag(tag):
    def wrap(object):
        object.tag = tag
        BPMN_MAPPINGS[tag] = object
        return object

    return wrap


class BpmnObject(object):
    def __repr__(self):
        return f"{type(self).__name__}({self.name or self._id})"

    def to_json(self):
        return {
            "_id": self._id,
            "name": self.name,
        }

    def parse(self, element):
        self._id = element.attrib["id"]
        self.name = element.attrib["name"] if "name" in element.attrib else None

    def run(self):
        return True


@bpmn_tag("bpmn:process")
class Process(BpmnObject):
    def __init__(self):
        self.is_main_in_collaboration = None
        self.name = None

    def parse(self, element):
        super(Process, self).parse(element)
        # Extensions should exists only if it's Collaboration diagram
        self.name = element.attrib["name"] if element.attrib.get("name") else ""
        if element.find(".bpmn:extensionElements", NS):
            ext = element.find(".bpmn:extensionElements", NS)
            for p in ext.findall(".//camunda:property", NS):
                # Find property is_main
                if p.attrib["name"] == "is_main" and p.attrib["value"] == "True":
                    self.is_main_in_collaboration = True


@bpmn_tag("bpmn:sequenceFlow")
class SequenceFlow(BpmnObject):
    def __init__(self):
        self.source = None
        self.target = None
        self.condition = None

    def parse(self, element):
        super(SequenceFlow, self).parse(element)
        self.source = element.attrib["sourceRef"]
        self.target = element.attrib["targetRef"]
        for c in element.findall("bpmn:conditionExpression", NS):
            self.condition = c.text

    def __repr__(self):
        condition = f" w. {len(self.condition)} con. " if self.condition else ""
        return f"{type(self).__name__}({self._id}): {self.source} -> {self.target}{condition}"

    pass


@bpmn_tag("bpmn:task")
class Task(BpmnObject):
    def __init__(self):
        self.simulation_properties = {}
        self.simulation_properties["probability"] = {}
        self.simulation_properties["optimization"] = {}
        #This helps to keep track of multiple probability distributions
        #for specific task
        self.current_distribution = None

    def parse(self, element):
        super(Task, self).parse(element)
        for p in element.findall(".//camunda:property", NS):
            property_name = p.attrib.get("name")
            self._check_probability_properties(p, property_name)
            self._check_optimization_properties(property_name)

    def _check_probability_properties(self, p, property_name):
        if property_name is not None and "distribution-" in property_name:
            self.current_distribution = property_name
            self.simulation_properties["probability"][self.current_distribution] = {}
            self.simulation_properties["probability"][self.current_distribution]["name"] = p.attrib["value"]
        if (property_name == "time_mean" or property_name == "time_std"):
            #This if statement is just for backwards compatibility and it
            #should be removed in the future updates as ./extra/ will not 
            #work without current_distribution parameter
            if self.current_distribution:
                self.simulation_properties["probability"][self.current_distribution][property_name] = float(p.attrib["value"])
        if (property_name == "weights"):
            #Create list from string
            weights = [float(x) for x in p.attrib["value"].split(",")]
            #Add correct weight to each distribution
            for index, distribution in enumerate(self.simulation_properties["probability"]):
                self.simulation_properties["probability"][distribution]["weight"] = weights[index]

    def _check_optimization_properties(self, property_name):
        pass

    def get_info(self):
        return {"type": self.tag}


@bpmn_tag("bpmn:manualTask")
class ManualTask(Task):
    pass


@bpmn_tag("bpmn:userTask")
class UserTask(Task):
    def __init__(self):
        self.form_fields = {}
        self.documentation = ""

    def parse(self, element):
        super(UserTask, self).parse(element)
        for f in element.findall(".//camunda:formField", NS):
            form_field_properties_dict = {}
            form_field_validations_dict = {}

            self.form_fields[f.attrib["id"]] = {}
            self.form_fields[f.attrib["id"]]["type"] = f.attrib["type"]
            if "label" in f.attrib:
                self.form_fields[f.attrib["id"]]["label"] = f.attrib["label"]
            else:
                self.form_fields[f.attrib["id"]]["label"] = ""

            for p in f.findall(".//camunda:property", NS):
                form_field_properties_dict[p.attrib["id"]] = parse_expression(
                    p.attrib["value"], {**env.SYSTEM_VARS, **env.DS}
                )

            for v in f.findall(".//camunda:constraint", NS):
                form_field_validations_dict[v.attrib["name"]] = v.attrib["config"]

            self.form_fields[f.attrib["id"]]["validation"] = form_field_validations_dict
            self.form_fields[f.attrib["id"]]["properties"] = form_field_properties_dict

        for d in element.findall(".//bpmn:documentation", NS):
            self.documentation = d.text

    def run(self, state, user_input):
        for k, v in user_input.items():
            if k in self.form_fields:
                state[k] = v
        return True

    def get_info(self):
        info = super(UserTask, self).get_info()
        return {
            **info,
            "form_fields": self.form_fields,
            "documentation": self.documentation,
        }


@bpmn_tag("bpmn:serviceTask")
class ServiceTask(Task):
    def __init__(self):
        self.properties_fields = {}
        self.input_variables = {}
        self.output_variables = {}
        self.connector_fields = {
            "connector_id": "",
            "input_variables": {},
            "output_variables": {},
        }

    def parse(self, element):
        super(ServiceTask, self).parse(element)

        datasources = {}
        try:
            datasources = env.DS
        except Exception:
            print("No DS in env.py")

        for ee in element.findall(".//bpmn:extensionElements", NS):
            # Find direct children inputOutput, Input/Output tab in Camunda
            self._parse_input_output_variables(
                ee, self.input_variables, self.output_variables
            )
            # Find connector data, Connector tab in Camunda
            for con in ee.findall(".camunda:connector", NS):
                self._parse_input_output_variables(
                    con,
                    self.connector_fields["input_variables"],
                    self.connector_fields["output_variables"],
                )
                connector_id = con.find("camunda:connectorId", NS).text
                if connector_id in datasources:
                    ds = datasources[connector_id]
                    self.connector_fields["connector_id"] = ds["type"]
                    self.connector_fields["input_variables"]["base_url"] = ds["url"]

    def _parse_input_output_variables(self, element, input_dict, output_dict):
        for io in element.findall(".camunda:inputOutput", NS):
            for inparam in io.findall(".camunda:inputParameter", NS):
                self._parse_input_output_parameters(inparam, input_dict)
            for outparam in io.findall(".camunda:outputParameter", NS):
                self._parse_input_output_parameters(outparam, output_dict)

    def _parse_input_output_parameters(self, element, dictionary):
        if element.findall(".camunda:list", NS):
            helper_list = []
            for lv in element.find("camunda:list", NS):
                helper_list.append(lv.text) if lv.text else ""
            dictionary[element.attrib["name"]] = helper_list
        elif element.findall(".camunda:map", NS):
            helper_dict = {}
            for mv in element.find("camunda:map", NS):
                helper_dict[mv.attrib["key"]] = mv.text
            dictionary[element.attrib["name"]] = helper_dict
        elif element.findall(".camunda:script", NS):
            # script not supported
            pass
        else:
            dictionary[element.attrib["name"]] = element.text if element.text else ""

    async def run_connector(self, variables, instance_id):
        # Check for URL parameters
        parameters = {}
        if self.connector_fields["input_variables"].get("url_parameter"):
            for key, value in self.connector_fields["input_variables"][
                "url_parameter"
            ].items():
                # Parse expression and add to parameters
                parameters[key] = parse_expression(value, variables)

        # JSON data for API
        data = {}
        for key, value in self.input_variables.items():
            # Parse expression if it exists
            if isinstance(value, str):
                value = parse_expression(value, variables)
            elif isinstance(value, list):
                value = [parse_expression(v, variables) for v in value]
            elif isinstance(value, dict):
                for k, v in value.items():
                    value[k] = parse_expression(v, variables)
            # Special case for instance id
            if key == "id_instance":
                value = instance_id
            # Add parsed value to data
            data[key] = value
        # system vars
        data = {**data, **env.SYSTEM_VARS}

        url = os.path.join(
            self.connector_fields["input_variables"].get("base_url", ""),
            self.connector_fields["input_variables"]["url"].lstrip("/"),
        )

        # Check method and make request
        method = self.connector_fields["input_variables"].get("method")
        if method:
            if method == "POST":
                call_function = requests.post
            elif method == "PATCH":
                call_function = requests.patch
            else:
                call_function = requests.get

            response = call_function(
                url,
                params=parameters,
                json=data,
            )

        if response.status_code not in (200, 201):
            raise Exception(response.text)

        # Check for output variables
        if self.output_variables:
            r = response.json()
            for key in self.output_variables:
                if key in r:
                    variables[key] = r[key]

    async def run(self, variables, instance_id):
        if self.connector_fields["connector_id"] == "http-connector":
            await self.run_connector(variables, instance_id)
        return True


@bpmn_tag("bpmn:sendTask")
class SendTask(ServiceTask):
    def parse(self, element):
        super(SendTask, self).parse(element)


@bpmn_tag("bpmn:callActivity")
class CallActivity(Task):
    def __init__(self):
        self.deployment = False
        self.called_element = ""

    def parse(self, element):
        super(CallActivity, self).parse(element)
        if element.attrib.get("calledElement"):
            self.called_element = element.attrib["calledElement"]
        if (
            element.attrib.get(f"{{{NS['camunda']}}}calledElementBinding")
            and element.attrib.get(f"{{{NS['camunda']}}}calledElementBinding")
            == "deployment"
        ):
            self.deployment = True


@bpmn_tag("bpmn:businessRule")
class BusinessRule(ServiceTask):
    def __init__(self):
        self.decision_ref = None

    def parse(self, element):
        super(BusinessRule, self).parse(element)


@bpmn_tag("bpmn:event")
class Event(BpmnObject):
    pass


@bpmn_tag("bpmn:startEvent")
class StartEvent(Event):
    pass


@bpmn_tag("bpmn:endEvent")
class EndEvent(Event):
    pass

@bpmn_tag("bpmn:intermediateThrowEvent")
class IntermediateThrowEvent(Event):
    pass

@bpmn_tag("bpmn:gateway")
class Gateway(BpmnObject):
    def parse(self, element):
        self.incoming = len(element.findall("bpmn:incoming", NS))
        self.outgoing = len(element.findall("bpmn:outgoing", NS))
        super(Gateway, self).parse(element)


@bpmn_tag("bpmn:parallelGateway")
class ParallelGateway(Gateway):
    def add_token(self):
        self.incoming -= 1

    def run(self):
        return self.incoming == 0


@bpmn_tag("bpmn:exclusiveGateway")
class ExclusiveGateway(Gateway):
    def __init__(self):
        self.default = False
        self.decision_outcome = None
        super(ExclusiveGateway, self).__init__()

    def parse(self, element):
        self.default = (
            element.attrib["default"] if "default" in element.attrib else None
        )
        super(ExclusiveGateway, self).parse(element)
        for p in element.findall(".//camunda:property", NS):
            if p.attrib.get("name"):
                self.decision_outcome = [float(x) for x in p.attrib["value"].split(",")]
