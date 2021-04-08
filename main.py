import xml.etree.ElementTree as ET
from bpmn_types import *
from pprint import pprint
import time


ns = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
tree = ET.parse("models/model_01.bpmn")

root = tree.getroot()

process = root.find("bpmn:process", ns)

pending = []

elements = {}
flow = {}

for tag, _type in {
    **BPMN_TASK_MAPPINGS,
    **BPMN_FLOW_MAPPINGS,
    **BPMN_EVENT_MAPPINGS,
}.items():
    for e in process.findall(f"bpmn:{tag}", ns):
        t = _type()
        t.parse(e)

        if isinstance(t, SequenceFlow):
            flow[t.source] = t.target

        elements[t.id] = t

        if isinstance(t, StartEvent):
            pending.append(t)


def get_by_id(_id):
    return elements[_id]


while len(pending) > 0:
    time.sleep(1)
    current = pending.pop()
    print("DOING:", current)
    current.run()

    if current.id in flow:
        pending.append(elements[flow[current.id]])

print(pending)