import xml.etree.ElementTree as ET
from bpmn_types import *
from pprint import pprint
from copy import deepcopy
from collections import defaultdict, deque
from functools import partial
import asyncio


class UserFormMessage:
    def __init__(self, task_id, form_data={}):
        self.task_id = task_id
        self.form_data = form_data


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
        return ok

    async def run(self, id, variables, in_queue):

        prefix = f"\t[{id}]"
        self.log = log = partial(print, prefix)

        pending = deepcopy(self.pending)
        elements = deepcopy(self.elements)
        variables = deepcopy(variables)
        flow = deepcopy(self.flow)
        queue = deque([])

        while len(pending) > 0:

            # process incoming messages
            if not in_queue.empty():
                queue.append(in_queue.get_nowait())

            exit = False
            can_continue = False
            for idx, current in enumerate(pending):

                if isinstance(current, EndEvent):
                    exit = True
                    break

                if isinstance(current, UserTask):
                    if len(queue):
                        message = queue.pop()
                        # print("\t\t\t", message.task_id)
                        if (
                            isinstance(message, UserFormMessage)
                            and message.task_id == current.id
                        ):
                            user_action = message.form_data

                            log("DOING:", current)
                            log("\t- user sent:", user_action)
                            can_continue = current.run(variables, user_action)
                        else:
                            queue.append(message)
                            # print("Discarding", message.task_id)

                    else:
                        pass
                        # queue.appendleft(message)
                else:
                    if isinstance(current, Task):
                        log("DOING:", current)
                    can_continue = current.run()

                if can_continue:
                    del pending[idx]
                    break

            if exit:
                break

            default = current.default if isinstance(current, ExclusiveGateway) else None

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

                for next_task in next_tasks:
                    if next_task not in pending:
                        pending.append(next_task)
                        # log("-----> Adding", next_task)
                    # log("n", next_task)
                    if isinstance(next_task, ParallelGateway):
                        next_task.add_token()
            else:
                log("Waiting for user...", pending)
                queue.append(await in_queue.get())

        log("DONE")
        return variables