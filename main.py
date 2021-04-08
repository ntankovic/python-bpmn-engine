import xml.etree.ElementTree as ET
from types import SimpleNamespace
from pprint import pprint


class BpmnObject(object):
    def __repr__(self):
        return f"{type(self).__name__}({self.id})"


class SequenceFlow(BpmnObject):
    pass


class Task(BpmnObject):
    pass


class UserTask(Task):
    pass


class ServiceTask(Task):
    pass


ns = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
tree = ET.parse("models/model_01.bpmn")

root = tree.getroot()

process = root.find("bpmn:process", ns)

task_mappings = {
    "task": Task,
    "userTask": UserTask,
    "serviceTask": ServiceTask,
    "sequenceFlow": SequenceFlow,
}

elements = {}
for tag, _type in task_mappings.items():
    for task in process.findall(f"bpmn:{tag}", ns):
        t = _type()
        t.id = task.attrib["id"]
        elements[t.id] = t

pprint(elements)