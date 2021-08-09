import requests

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

    def parse(self, element):
        self._id = element.attrib["id"]
        self.name = element.attrib["name"] if "name" in element.attrib else None

    def run(self):
        return True


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
    def parse(self, element):
        super(Task, self).parse(element)

    def get_info(self):
        return {"type": self.tag}


@bpmn_tag("bpmn:manualTask")
class ManualTask(Task):
    pass


@bpmn_tag("bpmn:userTask")
class UserTask(Task):
    def __init__(self):
        self.form_fields = {}
        self.documentation= ""

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
                form_field_properties_dict[p.attrib["id"]] = p.attrib["value"]

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
        return {**info, "form_fields": self.form_fields, "documentation":self.documentation}


@bpmn_tag("bpmn:serviceTask")
class ServiceTask(Task):
    def __init__(self):
        self.properties_fields = {}
    def parse(self, element):
        super(ServiceTask, self).parse(element)
        for f in element.findall(".//camunda:property",NS):
            if ',' in f.attrib["value"]:
                self.properties_fields[f.attrib["name"]] = list(f.attrib["value"].split(','))
            else:
                self.properties_fields[f.attrib["name"]] = f.attrib["value"]
    
    def run_database_service(self, state, database_location, instance_id):
        if "db_key" in self.properties_fields and self.properties_fields["db_key"] in state:
            param = {self.properties_fields["db_key"]:state[self.properties_fields["db_key"]]}
        else:
            param = {}

        if "db_parametars" in self.properties_fields:
            data = {}
            if isinstance(self.properties_fields["db_parametars"], str):
                p = self.properties_fields["db_parametars"]
                data[p] = state[p]
            else:
                for p in self.properties_fields["db_parametars"]:
                    data[p] = state[p]
        else:
            data = {}
        
        if "db_request_type" in self.properties_fields:
            if self.properties_fields["db_request_type"] == "GET":
                response = requests.get(self.properties_fields["db_location"], params=param, json=data)
            elif self.properties_fields["db_request_type"] == "POST":
                response = requests.post(self.properties_fields["db_location"], params=param, json=data)
            elif self.properties_fields["db_request_type"] == "PATCH":
                response = requests.patch(self.properties_fields["db_location"], params=param, json=data)
        else:
            print("Database service request type must be specified in properties as db_request_type")
        
        if "db_response" in self.properties_fields:
            if isinstance(self.properties_fields["db_response"], str):
                p = self.properties_fields["db_response"]
                for r in response.json():
                    state[p] = r[p]
            else:
                for p in self.properties_fields["db_response"]:
                    for r in response.json():
                        if p in r:
                            state[p]=r[p]

    def run_web_service(self, state, web_service_location, instance_id):
        if "web_service_request_type" in self.properties_fields:
            if self.properties_fields["web_service_request_type"] == "POST":
                if "web_service_parametars" in self.properties_fields:
                    data_to_post = dict()
                    if isinstance(self.properties_fields["web_service_parametars"], str):
                        p = self.properties_fields["web_service_parametars"]
                        data_to_post[p] = state[p]
                    else:
                        for p in self.properties_fields["web_service_parametars"]:
                            if p in state:
                                data_to_post[p] = state[p]
                    response = requests.post(self.properties_fields["web_service_location"], json=data_to_post)

                    if "web_service_response" in self.properties_fields:
                        if isinstance(self.properties_fields["web_service_response"], str):
                            p = self.properties_fields["web_service_response"]
                            for r in response.json():
                                if p in r:
                                    state[p] = r[p]
                        else:
                            for p in self.properties_fields["web_service_response"]:
                                for r in response.json():
                                    if p in r:
                                        state[p] = r[p]
            else:
                print("Supported web_service_request_type value is POST")
        else:
            print("Web service request type must be specified in properties as web_service_request_type")
    
    def run(self, state, instance_id):
        if "db_location" in self.properties_fields:
            self.run_database_service(state, self.properties_fields["db_location"], instance_id)
        if "web_service_location" in self.properties_fields:
            self.run_web_service(state, self.properties_fields["web_service_location"], instance_id)
        return True

            

@bpmn_tag("bpmn:event")
class Event(BpmnObject):
    pass


@bpmn_tag("bpmn:startEvent")
class StartEvent(Event):
    pass


@bpmn_tag("bpmn:endEvent")
class EndEvent(Event):
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
        super(ExclusiveGateway, self).__init__()

    def parse(self, element):
        self.default = (
            element.attrib["default"] if "default" in element.attrib else None
        )
        super(ExclusiveGateway, self).parse(element)

@bpmn_tag("bpmn:sendTask")
class SendTask(ServiceTask):
    def __init__(self):
        super(SendTask, self).__init__()
    
    def parse(self, element):
        super(SendTask, self).parse(element)
    
    def run_notification_service(self, state, notification_service_location, instance_id):
        if "notification_service_request_type" in self.properties_fields:
            if self.properties_fields["notification_service_request_type"] == "POST":
                if "notification_service_receiver" in self.properties_fields:
                    if self.properties_fields["notification_service_receiver"] in state:
                        params = {"to": state[self.properties_fields["notification_service_receiver"]]}
                        if "notification_service_parametars" in self.properties_fields:
                            data_to_post = dict()
                            if isinstance(self.properties_fields["notification_service_parametars"], str):
                                p = self.properties_fields["notification_service_parametars"]
                                if p == "id_instance":
                                    data_to_post[p] = instance_id
                                else:
                                    if p in state:
                                        data_to_post[p] = state[p]
                            else:
                                for p in self.properties_fields["notification_service_parametars"]:
                                    if p == "id_instance":
                                        data_to_post[p] = instance_id
                                    if p in state:
                                        data_to_post[p] = state[p]
                            if "notification_service_next_task" in self.properties_fields:
                                data_to_post["next_task"] = self.properties_fields["notification_service_next_task"]
                            response = requests.post(self.properties_fields["notification_service_location"], json=data_to_post, params=params)
                        else:
                            pass
                    else:
                        print("{} not found in proces variables".format(self.properties_fields["notification_service_receiver"]))
                        return
                    
                else:
                    print("Notification receiver must be specified as notification_service_receiver")
            else:
                print("Supported notification_service_request_type value is POST")
        else:
            print("Notification service request type must be specified in properties as notification_service_request_type")
    def run(self, state, instance_id):
        if "notification_service_location" in self.properties_fields:
            self.run_notification_service(state, self.properties_fields["notification_service_location"], instance_id)
        return True