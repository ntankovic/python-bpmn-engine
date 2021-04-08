ns = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}


class BpmnObject(object):
    def __repr__(self):
        return f"{type(self).__name__}({self.name or self.id})"

    def parse(self, element):
        self.id = element.attrib["id"]
        self.name = element.attrib["name"] if "name" in element.attrib else None

    def run(self):
        return True


class SequenceFlow(BpmnObject):
    def __init__(self):
        self.source = None
        self.target = None

    def parse(self, element):
        super(SequenceFlow, self).parse(element)
        self.source = element.attrib["sourceRef"]
        self.target = element.attrib["targetRef"]

    def __repr__(self):
        return f"{type(self).__name__}({self.id}): {self.source} -> {self.target}"

    pass


class Task(BpmnObject):
    def parse(self, element):
        super(Task, self).parse(element)


class UserTask(Task):
    pass


class ServiceTask(Task):
    pass


class Event(BpmnObject):
    pass


class StartEvent(Event):
    pass


class EndEvent(Event):
    pass


class ExclusiveGateway(BpmnObject):
    def parse(self, element):
        self.incoming = len(element.findall("bpmn:incoming", ns))
        self.outgoing = len(element.findall("bpmn:outgoing", ns))
        super(ExclusiveGateway, self).parse(element)

    def run(self):
        self.incoming -= 1
        return self.incoming == 0


BPMN_TASK_MAPPINGS = {
    "task": Task,
    "userTask": UserTask,
    "serviceTask": ServiceTask,
}

BPMN_FLOW_MAPPINGS = {
    "sequenceFlow": SequenceFlow,
}

BPMN_EVENT_MAPPINGS = {
    "startEvent": StartEvent,
    "endEvent": EndEvent,
}

BPMN_GATEWAY_MAPPINGS = {"exclusiveGateway": ExclusiveGateway}
