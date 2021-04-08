import xml.etree.ElementTree as ET
from collections import defaultdict
from bpmn_types import *
from pprint import pprint
import time


ns = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
tree = ET.parse("models/model_01.bpmn")

root = tree.getroot()

process = root.find("bpmn:process", ns)

pending = []

elements = {}
flow = defaultdict(list)

for tag, _type in {
    **BPMN_TASK_MAPPINGS,
    **BPMN_FLOW_MAPPINGS,
    **BPMN_EVENT_MAPPINGS,
    **BPMN_GATEWAY_MAPPINGS,
}.items():
    for e in process.findall(f"bpmn:{tag}", ns):
        t = _type()
        t.parse(e)

        if isinstance(t, SequenceFlow):
            flow[t.source].append(t.target)

        elements[t.id] = t

        if isinstance(t, StartEvent):
            pending.append(t)


while len(pending) > 0:
    time.sleep(1)
    current = pending.pop()
    print("DOING:", current)
    can_continue = current.run()
    if not can_continue:
        print("\t- waiting for all processes in gate.")

    if can_continue:
        if current.id in flow:
            for next in flow[current.id]:
                pending.append(elements[next])

print(pending)