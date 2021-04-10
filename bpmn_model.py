import xml.etree.ElementTree as ET
from bpmn_types import *
from pprint import pprint
from copy import deepcopy
from collections import defaultdict
from functools import partial
import asyncio


class BpmnModel:
    def __init__(self, model_path):
        self.pending = []
        self.elements = {}
        self.flow = defaultdict(list)

        model_tree = ET.parse(model_path)
        model_root = model_tree.getroot()
        process = model_root.find("bpmn:process", NS)

        for tag, _type in BPMN_MAPPINGS.items():
            for e in process.findall(f"{tag}", NS):
                t = _type()
                t.parse(e)

                if isinstance(t, SequenceFlow):
                    self.flow[t.source].append(t)

                if isinstance(t, ExclusiveGateway):
                    if t.default:
                        self.elements[t.default].default = True

                self.elements[t.id] = t

                if isinstance(t, StartEvent):
                    self.pending.append(t)

    def check_conditions(self, state, conditions):
        self.log(f"\t- checking variables={state} with {conditions}... ", end="")
        ok = False
        try:
            ok = all(eval(c, state, None) for c in conditions)
        except Exception as e:
            pass
        print("DONE: Result is", ok)

    async def run(self, id, variables, in_queue):

        prefix = f"\t[{id}]"
        self.log = log = partial(print, prefix)

        pending = deepcopy(self.pending)
        elements = deepcopy(self.elements)
        variables = deepcopy(variables)
        flow = deepcopy(self.flow)

        while len(pending) > 0:
            await asyncio.sleep(0.05)
            current = pending.pop()

            if isinstance(current, EndEvent):
                break

            if isinstance(current, Task):
                log("DOING:", current)

            default = current.default if isinstance(current, ExclusiveGateway) else None

            if isinstance(current, UserTask):
                user_action = await in_queue.get()
                log("\t- user sent:", user_action)
                can_continue = current.run(variables, user_action)
                in_queue.task_done()
            else:
                can_continue = current.run()
            if not can_continue:
                log("\t- waiting for all processes in gate.")

            if can_continue:
                next_tasks = []
                if current.id in flow:
                    default_fallback = None
                    for sequence in flow[current.id]:
                        if sequence.id == default:
                            default_fallback = elements[sequence.target]
                            continue
                        if sequence.conditions:
                            if self.check_conditions(variables, sequence.conditions):
                                next_tasks.append(elements[sequence.target])
                        else:
                            next_tasks.append(elements[sequence.target])

                    if not next_tasks and default_fallback:
                        log("\t- going down default path...")
                        next_tasks.append(default_fallback)

                pending += next_tasks
        log("DONE")