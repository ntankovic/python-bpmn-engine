class BpmnObject(object):
    def __repr__(self):
        return f"{type(self).__name__}({self.id})"

    def parse(self, element):
        self.id = element.attrib["id"]

    def run(self):
        pass


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