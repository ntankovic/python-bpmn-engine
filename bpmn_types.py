NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "camunda": "http://camunda.org/schema/1.0/bpmn",
}

BPMN_MAPPINGS = {}


def bpmn_tag(tag):
    def wrap(object):
        BPMN_MAPPINGS[tag] = object
        return object

    return wrap


class BpmnObject(object):
    def __repr__(self):
        return f"{type(self).__name__}({self.name or self.id})"

    def parse(self, element):
        self.id = element.attrib["id"]
        self.name = element.attrib["name"] if "name" in element.attrib else None

    def run(self):
        return True


@bpmn_tag("bpmn:sequenceFlow")
class SequenceFlow(BpmnObject):
    def __init__(self):
        self.source = None
        self.target = None
        self.conditions = []

    def parse(self, element):
        super(SequenceFlow, self).parse(element)
        self.source = element.attrib["sourceRef"]
        self.target = element.attrib["targetRef"]
        for c in element.findall("bpmn:conditionExpression", NS):
            self.conditions.append(c.text)

    def __repr__(self):
        conditions = f" w. {len(self.conditions)} con. " if self.conditions else ""
        return f"{type(self).__name__}({self.id}): {self.source} -> {self.target}{conditions}"

    pass


@bpmn_tag("bpmn:task")
class Task(BpmnObject):
    def parse(self, element):
        super(Task, self).parse(element)


@bpmn_tag("bpmn:manualTask")
class ManualTask(Task):
    pass


@bpmn_tag("bpmn:userTask")
class UserTask(Task):
    def __init__(self):
        self.form_fields = {}

    def parse(self, element):
        super(UserTask, self).parse(element)
        for f in element.findall(".//camunda:formField", NS):
            self.form_fields[f.attrib["id"]] = f.attrib["type"]

    def run(self, state, user_input):
        clean_state = {}
        exec(user_input, None, clean_state)
        for k, v in clean_state.items():
            if k in self.form_fields:
                state[k] = v

        return True


@bpmn_tag("bpmn:serviceTask")
class ServiceTask(Task):
    pass


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
    def run(self):
        self.incoming -= 1
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
