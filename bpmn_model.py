from asyncio import queues
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
        self.instances = {}

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

                self.elements[t._id] = t

                if isinstance(t, StartEvent):
                    self.pending.append(t)

    async def create_instance(self, _id, variables):
        queue = asyncio.Queue()
        instance = BpmnInstance(_id, model=self, variables=variables, in_queue=queue)
        self.instances[_id] = instance
        return instance


class BpmnInstance:
    def __init__(self, _id, model, variables, in_queue):
        self._id = _id
        self.model = model
        self.variables = deepcopy(variables)
        self.in_queue = in_queue
        self.state = "initialized"
        self.pending = deepcopy(self.model.pending)

    def get_info(self):
        return {
            "state": self.state,
            "variables": self.variables,
            "id": self._id,
            "pending": [x._id for x in self.pending],
        }

    @classmethod
    def check_conditions(cls, state, conditions, log):
        log(f"\t- checking variables={state} with {conditions}... ")
        ok = False
        try:
            ok = all(eval(c, deepcopy(state), None) for c in conditions)
        except Exception as e:
            pass
        log("\t  DONE: Result is", ok)
        return ok

    async def run(self):

        self.state = "running"
        _id = self._id
        prefix = f"\t[{_id}]"
        log = partial(print, prefix)  # if _id == "2" else lambda *x: x

        in_queue = self.in_queue
        self.pending = deepcopy(self.model.pending)
        elements = deepcopy(self.model.elements)
        flow = deepcopy(self.model.flow)
        queue = deque()

        while len(self.pending) > 0:

            # process incoming messages
            if not in_queue.empty():
                queue.append(in_queue.get_nowait())
            # print("Check", _id, id(queue), id(in_queue))

            exit = False
            can_continue = False

            message = queue.pop() if len(queue) else None
            if message:
                log("--> msg in:", message and message.task_id)

            for idx, current in enumerate(self.pending):
                if isinstance(current, EndEvent):
                    exit = True
                    break

                if isinstance(current, UserTask):
                    if (
                        message
                        and isinstance(message, UserFormMessage)
                        and message.task_id == current._id
                    ):
                        user_action = message.form_data

                        log("DOING:", current)
                        if user_action:
                            log("\t- user sent:", user_action)
                        can_continue = current.run(self.variables, user_action)
                else:
                    if isinstance(current, Task):
                        log("DOING:", current)
                    can_continue = current.run()

                if can_continue:
                    del self.pending[idx]
                    break

            if exit:
                break

            default = current.default if isinstance(current, ExclusiveGateway) else None

            if can_continue:
                next_tasks = []
                if current._id in flow:
                    default_fallback = None
                    for sequence in flow[current._id]:
                        if sequence._id == default:
                            default_fallback = elements[sequence.target]
                            continue

                        if sequence.conditions:
                            if self.check_conditions(
                                self.variables, sequence.conditions, log
                            ):
                                next_tasks.append(elements[sequence.target])
                        else:
                            next_tasks.append(elements[sequence.target])

                    if not next_tasks and default_fallback:
                        log("\t- going down default path...")
                        next_tasks.append(default_fallback)

                for next_task in next_tasks:
                    if next_task not in self.pending:
                        self.pending.append(next_task)
                        # log("-----> Adding", next_task)
                    # log("n", next_task)
                    if isinstance(next_task, ParallelGateway):
                        next_task.add_token()
            else:
                log("Waiting for user...", self.pending)
                queue.append(await in_queue.get())

        log("DONE")
        self.state = "finished"
        self.pending = []
        return self.variables