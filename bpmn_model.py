from types import SimpleNamespace
import xml.etree.ElementTree as ET
from bpmn_types import *
from pprint import pprint
from copy import deepcopy
from collections import defaultdict, deque
from functools import partial
import asyncio
import db_connector
from datetime import datetime
import os
from uuid import uuid4
import env
from bpmn_types import Task, ServiceTask

instance_models = {}


def get_model_for_instance(iid):
    return instance_models.get(iid, None)


class UserFormMessage:
    def __init__(self, task_id, form_data={}):
        self.task_id = task_id
        self.form_data = form_data


class ReceiveMessage:
    def __init__(self, task_id, data={}):
        self.task_id = task_id
        self.data = data or {}


class BpmnModel:
    def __init__(self, model_path):
        self.pending = []
        self.elements = {}
        self.flow = defaultdict(list)
        self.instances = {}
        self.process_elements = {}
        self.process_pending = defaultdict(list)
        self.main_collaboration_process = None
        self.model_path = model_path
        self.subprocesses = {}
        self.main_process = SimpleNamespace()

        model_tree = ET.parse(os.path.join("models", self.model_path))
        model_root = model_tree.getroot()
        processes = model_root.findall("bpmn:process", NS)
        for process in processes:
            p = BPMN_MAPPINGS["bpmn:process"]()
            p.parse(process)
            self.process_elements[p._id] = {}
            # Check for Collaboration
            if len(processes) > 1 and p.is_main_in_collaboration:
                self.main_collaboration_process = p._id
                self.main_process.name = p.name
                self.main_process.id = p._id
            else:
                self.main_process.name = p.name
                self.main_process.id = p._id
            # Parse all elements in the process
            for tag, _type in BPMN_MAPPINGS.items():
                for e in process.findall(f"{tag}", NS):
                    t = _type()
                    t.parse(e)
                    if isinstance(t, CallActivity):
                        self.subprocesses[t.called_element] = t.deployment
                    if isinstance(t, SequenceFlow):
                        self.flow[t.source].append(t)
                    if isinstance(t, ExclusiveGateway):
                        if t.default:
                            self.elements[t.default].default = True
                    if isinstance(t, StartEvent):
                        self.pending.append(t)
                        self.process_pending[p._id].append(t)
                    self.elements[t._id] = t
                    self.process_elements[p._id][t._id] = t
        # Check if there is single deployement subprocess
        for k, v in self.subprocesses.items():
            if v:
                self.handle_deployment_subprocesses()
                break

    def to_json(self):
        tasks = [x.to_json() for x in self.elements.values() if isinstance(x, UserTask) or isinstance(x, ReceiveTask)]
        return {
            "model_path": self.model_path,
            "main_process": self.main_process.__dict__,
            "tasks": tasks,
            "instances": [i._id for i in self.instances.values()],
        }

    async def create_instance(self, _id, variables, process=None):
        queue = asyncio.Queue()
        if not process:
            if self.main_collaboration_process:
                # If Collaboration diagram
                process = self.main_collaboration_process
            else:
                # If Process diagram
                process = list(self.process_elements)[0]
        instance = BpmnInstance(
            _id, model=self, variables=variables, in_queue=queue, process=process
        )
        self.instances[_id] = instance
        return instance

    # Takes model_path needed for deployed subprocess
    def handle_deployment_subprocesses(self):
        models_directory = self.model_path.split("/")[:-1]
        models_directory = "/".join(models_directory) + "/"

        other_models_list = []

        for m in os.listdir(models_directory):
            if models_directory + m == self.model_path:
                continue
            other_model = BpmnModel(models_directory + m)
            other_models_list.append(other_model)
        for other_model in other_models_list:
            for subprocess_key in self.subprocesses.keys():
                for process_key in other_model.process_elements.keys():
                    if subprocess_key == process_key:
                        self.subprocesses[subprocess_key] = other_model.model_path


class BpmnInstance:
    def __init__(self, _id, model, variables, in_queue, process):
        instance_models[_id] = model
        self._id = _id
        self.model = model
        self.variables = deepcopy(variables)
        self.in_queue = in_queue
        self.state = "initialized"
        self.pending = deepcopy(self.model.process_pending[process])
        self.process = process

    def to_json(self):
        return {
            "id": self._id,
            "variables": self.variables,
            "state": self.state,
            "model": self.model.to_json(),
            "pending": [x._id for x in self.pending],
            "env": env.SYSTEM_VARS,
        }

    @classmethod
    def check_condition(cls, state, condition, log):
        log(f"\t- checking variables={state} with {condition}... ")
        ok = False
        if condition:
            key = condition.partition(":")[0]
            value = condition.partition(":")[2]
            if key in state and state[key] == value:
                ok = True
        log("\t  DONE: Result is", ok)
        return ok

    async def run_from_log(self, log):
        for l in log:
            if l.get("activity_id") in self.model.elements:
                pending_elements_list = []
                for p in l.get("pending"):
                    pending_elements_list.append(self.model.elements[p])
                self.pending = pending_elements_list
                self.variables = {**l.get("activity_variables"), **self.variables}
        return self

    # async def run(self, is_subprocess=False):
    #     import _thread
    #     _thread.start_new_thread(asyncio.run, args=(self._run(is_subprocess=is_subprocess),))
    #     print("thread")

    async def run(self, is_subprocess=False):

        self.state = "running"
        _id = self._id
        prefix = f"\t[{_id}]"

        log = partial(print, prefix)  # if _id == "2" else lambda *x: x

        in_queue = self.in_queue
        # Take only elements of running process
        elements = deepcopy(self.model.process_elements[self.process])
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

            # Helper current dictionary
            current_and_variables_dict = {}

            for idx, current in enumerate(self.pending):
                # Helper variables dict
                before_variables = deepcopy(self.variables)

                if isinstance(current, StartEvent):
                    # Helper variables for DB insert
                    new_variables = {
                        k: self.variables[k]
                        for k in set(self.variables) - set(before_variables)
                    }
                    current_and_variables_dict[current._id] = new_variables
                    # Create new running instance
                    db_connector.add_running_instance(instance_id=self._id, ran_as_subprocess=is_subprocess)

                if isinstance(current, EndEvent):
                    exit = True
                    del self.pending[idx]
                    # Add EndEvent to DB
                    db_connector.add_event(
                        model_name=self.model.model_path,
                        instance_id=self._id,
                        activity_id=current._id,
                        timestamp=datetime.now(),
                        pending=[],
                        activity_variables=self.variables,
                    )
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
                        # Helper variables for DB insert
                        new_variables = {
                            k: self.variables[k]
                            for k in set(self.variables) - set(before_variables)
                        }
                        current_and_variables_dict[current._id] = new_variables

                elif isinstance(current, ServiceTask):
                    log("DOING:", current)

                    can_continue = await current.run(self.variables, _id)
                    # Helper variables for DB insert
                    new_variables = {
                        k: self.variables[k]
                        for k in set(self.variables) - set(before_variables)
                    }
                    current_and_variables_dict[current._id] = new_variables

                elif isinstance(current, SendTask):
                    log("DOING:", current)
                    can_continue = current.run(self.variables, _id)
                    # Helper variables for DB insert
                    new_variables = {
                        k: self.variables[k]
                        for k in set(self.variables) - set(before_variables)
                    }
                    current_and_variables_dict[current._id] = new_variables
                elif isinstance(current, ReceiveTask):
                    if (
                            message
                            and isinstance(message, ReceiveMessage)
                            and message.task_id == current._id
                    ):
                        log("DOING:", current)
                        can_continue = current.run(self.variables, message.data)
                        # Helper variables for DB insert
                        new_variables = {
                            k: self.variables[k]
                            for k in set(self.variables) - set(before_variables)
                        }
                        current_and_variables_dict[current._id] = new_variables

                elif isinstance(current, CallActivity):

                    log("DOING:", current)
                    can_continue = await current.run_subprocess(self.model, current.called_element, self.variables)
                    log("SUBPROCESS DONE WITH VARIABLES\n" + "---> " + str(self.variables))
                    # Helper variables for DB insert
                    new_variables = {
                        k: self.variables[k]
                        for k in set(self.variables) - set(before_variables)
                    }
                    current_and_variables_dict[current._id] = new_variables

                else:
                    if isinstance(current, Task):
                        log("DOING:", current)
                    can_continue = current.run()
                    # Helper variables for DB insert
                    new_variables = {
                        k: self.variables[k]
                        for k in set(self.variables) - set(before_variables)
                    }
                    current_and_variables_dict[current._id] = new_variables

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

                        if sequence.condition:
                            if self.check_condition(
                                    self.variables, sequence.condition, log
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

            # Insert finished events into DB
            for c in current_and_variables_dict:
                # Add each current into DB
                db_connector.add_event(
                    model_name=self.model.model_path,
                    instance_id=self._id,
                    activity_id=c,
                    timestamp=datetime.now(),
                    pending=[pending._id for pending in self.pending],
                    activity_variables=current_and_variables_dict[c],
                )
        if not is_subprocess:
            log("WORKFLOW DONE WITH VARIABLES\n" + "---> " + str(dict(self.variables).keys()))

        self.state = "finished"
        self.pending = []
        # Running instance finished
        db_connector.finish_running_instance(self._id)

        return self.variables
