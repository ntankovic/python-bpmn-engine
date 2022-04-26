from isoduration import parse_duration
from datetime import datetime
import math
import requests
import os
import env
from utils.common import parse_expression
import re
import asyncio

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "camunda": "http://camunda.org/schema/1.0/bpmn",
}

# Holds all classes defined with bpmn_tag decorator
BPMN_MAPPINGS = {}

EVENT_SUBTYPE_MAPPINGS = {}

def bpmn_tag(tag):
    def wrap(object):
        object.tag = tag
        BPMN_MAPPINGS[tag] = object
        return object

    return wrap

def event_subtype(tag):
    def wrap(object):
        EVENT_SUBTYPE_MAPPINGS[tag] = object
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

    def parse(self, element):
        super(Process, self).parse(element)
        # Extensions should exists only if it's Collaboration diagram
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
        self.attached_events = []

        # Simulation attributes
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
            self._check_optimization_properties(p, property_name)

    def _check_probability_properties(self, p, property_name):
        """
        Properties for distributions MUST be in following order:
        distribution-1 name
        distribution-1 parameters
        distribution-2 name
        ...

        """
        if property_name is not None and "distribution-" in property_name:
            self.current_distribution = property_name
            self.simulation_properties["probability"][self.current_distribution] = {}
            self.simulation_properties["probability"][self.current_distribution]["name"] = p.attrib["value"]
        if (property_name == "time_mean" or property_name == "time_std"):
            self.simulation_properties["probability"][self.current_distribution][property_name] = float(p.attrib["value"])
        if (property_name == "weights"):
            #Create list from string
            weights = [float(x) for x in p.attrib["value"].split(",")]
            #Add correct weight to each distribution
            for index, distribution in enumerate(self.simulation_properties["probability"]):
                self.simulation_properties["probability"][distribution]["weight"] = weights[index]

    def _check_optimization_properties(self, p, property_name):
        if property_name is not None and "constraint-" in property_name:
            constr = property_name.split("constraint-")[1]
            self.simulation_properties["optimization"][constr] = float(p.attrib["value"])


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

    def run_connector(self, variables, instance_id):
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
            self.run_connector(variables, instance_id)
        return True


@bpmn_tag("bpmn:sendTask")
class SendTask(ServiceTask):
    def parse(self, element):
        super(SendTask, self).parse(element)

    async def run(self, variables, instance_id):
        if self.connector_fields["connector_id"] == "http-connector":
            self.run_connector(variables, instance_id)


@bpmn_tag("bpmn:businessRule")
class BusinessRule(Task):
    def __init__(self):
        self.decision_ref = None

    def parse(self, element):
        super(BusinessRule, self).parse(element)

### SUBPROCESSES ### 

@bpmn_tag("bpmn:subProcess")
class SubProcess(Task):
    pass

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

### EVENTS ###

@bpmn_tag("bpmn:event")
class Event(BpmnObject):
    def __init__(self):
        self.subtype = None
    
    def parse(self, element):
        super(Event, self).parse(element)
        for e in element:
            #Find event subtype
            if re.search("\w+EventDefinition",str(e.tag)):
                event_subtype = str(e.tag).split("}")[1]
                self.subtype = EVENT_SUBTYPE_MAPPINGS[event_subtype](e)

    def get_info(self):
        return {"type": self.tag, "subtype":str(self.subtype)}

@bpmn_tag("bpmn:boundaryEvent")
class BoundaryEvent(Event):
    def __init__(self):
        self.attached_to = None
        self.cancle_activity = None
    
    def parse(self, element):
        super(BoundaryEvent, self).parse(element)
        self.attached_to = element.attrib["attachedToRef"]
        self.cancle_activity = False if "cancelActivity" in element.attrib else True


    async def run(self):
        try:
            await self.subtype.run()
        except asyncio.CancelledError:
            return True
    

@bpmn_tag("bpmn:startEvent")
class StartEvent(Event):
    async def run(self):
        if self.subtype:
            try:
                await self.subtype.run()
            except asyncio.CancelledError:
                return True
        else:
            return True

@bpmn_tag("bpmn:endEvent")
class EndEvent(Event):
    pass

@bpmn_tag("bpmn:intermediateThrowEvent")
class IntermediateThrowEvent(Event):
    pass

@bpmn_tag("bpmn:intermediateCatchEvent")
class IntermediateCatchEvent(Event):
    async def run(self):
        await self.subtype.run()

### Event Types ### 

@event_subtype("errorEventDefinition")
class ErrorEvent():
    def __init__(self,element):
        # Used for end events
        self.error_ref = None
        # Set from bpmn_model
        self.error_message = None
        # Used for boundary events, it must match self.error_message from 
        # ErrorEndEvent
        self.error_message_variable = None
        self.parse(element)

    def parse(self,element):
        self.error_ref = element.attrib["errorRef"] if "errorRef" in element.attrib else None
        if f"{{{NS['camunda']}}}errorMessageVariable" in element.attrib:
            self.error_message_variable = element.attrib[f"{{{NS['camunda']}}}errorMessageVariable"]

    async def run(self):
        try:
            # Do nothing...
            # Logic is handled within bpmn_model.
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise

    def __str__(self):
        return "Error Event"

@event_subtype("timerEventDefinition")
class TimerEvent():
    def __init__(self,element):
        self.timer_type = None
        self.duration = None
        self.parse(element)
    
    def parse(self,element):
        for e in element:
            if re.search("\w+Duration",str(e.tag)):
                # Duration text should be "PnYnMnWnDTnHnMnS"
                # n - number
                # P - is obligatory
                # T - is obligatory when specifing hours,minutues and/or seconds
                self.timer_type = "duration"
                self.duration = self._handle_duration_string(e.text)

    async def run(self):
        # Start specific timer
        if self.timer_type == "duration":
            await asyncio.sleep(self.duration)
            return True

    def _handle_duration_string(self, duration_string):
        """
        Convert string to seconds (int)

        """
        iso_string = parse_duration(duration_string.upper())
        current_time = datetime.now()
        new_datetime = current_time + iso_string
        # We lose miliseconds on calculations, so we round up to closes integer,
        # to get intended value 
        return math.ceil(new_datetime.timestamp() - current_time.timestamp())

    def __str__(self):
        return "Timer Event"

        

@event_subtype("terminateEventDefinition")
class TerminateEvent():
    def __init__(self,element):
        pass
    def __str__(self):
        return "Terminate Event"

@event_subtype("messageEventDefinition")
class MessageEvent():
    def __init__(self,element):
        pass
    
    async def run(self):
        try:
            # Do nothing...
            # Logic is handled within bpmn_model.
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise

    def __str__(self):
        return "Message Event"

### GATEWAYS ### 

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
