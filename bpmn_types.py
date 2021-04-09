NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "camunda": "http://camunda.org/schema/1.0/bpmn",
}


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


class Gateway(BpmnObject):
    def parse(self, element):
        self.incoming = len(element.findall("bpmn:incoming", NS))
        self.outgoing = len(element.findall("bpmn:outgoing", NS))
        super(Gateway, self).parse(element)


class ParallelGateway(Gateway):
    def run(self):
        self.incoming -= 1
        return self.incoming == 0


class ExclusiveGateway(Gateway):
    def __init__(self):
        self.default = False
        super(ExclusiveGateway, self).__init__()

    def parse(self, element):
        self.default = (
            element.attrib["default"] if "default" in element.attrib else None
        )
        super(ExclusiveGateway, self).parse(element)


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

BPMN_GATEWAY_MAPPINGS = {
    "parallelGateway": ParallelGateway,
    "exclusiveGateway": ExclusiveGateway,
}
