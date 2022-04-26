from types import SimpleNamespace
import sys
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

instance_models = {}


def get_model_for_instance(iid):
    return instance_models.get(iid, None)


class UserFormMessage:
    def __init__(self, task_id, form_data={}):
        self.task_id = task_id
        self.form_data = form_data

class RegularMessage():
    def __init__(self, task_id, message_data={}):
        self.task_id = task_id
        self.message_data = message_data


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
        self.collaboration_mapping = {}
        self.main_process = SimpleNamespace()

        models_directory = os.path.dirname(__file__)+"/models"

        model_tree = ET.parse(os.path.join(models_directory, self.model_path))
        model_root = model_tree.getroot()
        processes = model_root.findall("bpmn:process", NS)

        self._parse_model(processes)
        
        business_errors = model_root.findall("bpmn:error", NS)
        
        self._parse_business_errors(business_errors)

        # Check if there is single deployement subprocess
        for _, subprocess_from_other_diagram in self.subprocesses.items():
            if subprocess_from_other_diagram:
                self._handle_subprocesses_deployment()
                break

    def _parse_model(self, processes):
        # Start parsing model
        for process in processes:
            process_object = BPMN_MAPPINGS["bpmn:process"]()
            process_object.parse(process)
            self.process_elements[process_object._id] = {}
            # Check for Collaboration
            if len(processes) > 1 and process_object.is_main_in_collaboration:
                self.main_collaboration_process = process_object._id
                self.main_process.name = process_object.name
                self.main_process.id = process_object._id
            else:
                self.main_process.name = process_object.name
                self.main_process.id = process_object._id
            
            self._parse_process(process, process_object)


    def _parse_process(self, process, process_object):
        #Local mapping for boundary events
        task_event_mapping = {}
        # Parse all elements in the process
        for tag, _type in BPMN_MAPPINGS.items():
            for e in process.findall(f"{tag}", NS):
                t = _type()
                t.parse(e)
                if isinstance(t, BoundaryEvent):
                    try:
                        task_event_mapping[t.attached_to].append(t._id)
                    except:
                        task_event_mapping[t.attached_to] = []
                        task_event_mapping[t.attached_to].append(t._id)
                if isinstance(t, SubProcess):
                    # Register subprocess as additional process
                    self.process_elements[t._id] = {}
                    # Parse all elements from subprocess
                    self._parse_process(e, t)
                    # Subprocess is always part of current model
                    self.subprocesses[t._id] = False
                if isinstance(t, CallActivity):
                    self.subprocesses[t.called_element] = t.deployment
                if isinstance(t, SequenceFlow):
                    self.flow[t.source].append(t)
                if isinstance(t, ExclusiveGateway):
                    if t.default:
                        self.elements[t.default].default = True
                if isinstance(t, StartEvent):
                    self.pending.append(t)
                    self.process_pending[process_object._id].append(t)
                self.elements[t._id] = t
                self.process_elements[process_object._id][t._id] = t
        # Check for boundry events in the process
        for task in task_event_mapping:
            self.elements[task].attached_events = task_event_mapping[task]

    def _parse_business_errors(self, errors):
        for err in errors:
            err_id = err.attrib["id"]
            for _, e in self.elements.items():
                if (isinstance(e, Event) and isinstance(e.subtype,ErrorEvent) and e.subtype.error_ref == err_id):
                    if f"{{{NS['camunda']}}}errorMessage" in err.attrib: 
                        e.subtype.error_message = err.attrib[f"{{{NS['camunda']}}}errorMessage"] 

    def to_json(self):
        return {
            "model_path": self.model_path,
            "main_process": self.main_process.__dict__,
            "user_tasks": [
                x.to_json() for x in self.elements.values() if isinstance(x, UserTask)
            ],
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

    # Take model_path needed for deployed subprocess
    def _handle_subprocesses_deployment(self):
        models_directory = os.path.dirname(__file__)+"/models"

        other_models_list = []

        for m in os.listdir(models_directory):
            # Skip current model
            if m == self.model_path:
                continue
            other_model = BpmnModel(m)
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
            "event_types":{k._id:k.get_info() for k in self.pending if isinstance(k,Event)},
            "env": env.SYSTEM_VARS,
        }

    @classmethod
    def check_condition(cls, variables, condition, log):
        log(f"\t- checking variables={variables} with {condition}... ")
        ok = False
        if condition:
            key = condition.split(":")[0]
            value = condition.split(":")[1]
            if key in variables and variables[key] == value:
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

    async def _run_subprocess(self, process_id, variables={}, events=None):
        new_subproces_instance_id = str(uuid4())

        if self.model.subprocesses[process_id]:
            subprocess_model = BpmnModel(self.model.subprocesses[process_id])
        else:
            subprocess_model = self.model
        new_subproces_instance = await subprocess_model.create_instance(
            new_subproces_instance_id, variables, process_id
        )
        try:
            finished_subprocess = await new_subproces_instance.run(events)
            return finished_subprocess
        except asyncio.CancelledError:
            db_connector.finish_running_instance(new_subproces_instance_id)
            raise 


    async def run(self, boundary_events = None):
        self.state = "running"
        _id = self._id
        prefix = f"\t[{_id}]"
        log = partial(print, prefix)  # if _id == "2" else lambda *x: x

        in_queue = self.in_queue
        # Take only elements of running process
        elements = deepcopy(self.model.process_elements[self.process])
        flow = deepcopy(self.model.flow)
        queue = deque()
        
        #Merge boundary events with pending
        if boundary_events is not None:
            self.pending = [*self.pending, *boundary_events]

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
    
                print([x.get_name() for x in asyncio.all_tasks()])

                if isinstance(current, StartEvent):
                    if isinstance(current.subtype, MessageEvent):
                        if not (
                            message
                            and isinstance(message, RegularMessage)
                            and message.task_id == current._id
                        ):
                            start_message_task = asyncio.create_task(current.run(), name=current._id)
                        if start_message_task.done():
                            log("DOING:", current)
                            print(start_message_task.result())
                            can_continue = start_message_task.result()
                            # Helper variables for DB insert
                            new_variables = {
                                k: self.variables[k]
                                for k in set(self.variables) - set(before_variables)
                            }
                            current_and_variables_dict[current._id] = new_variables
                            # Create new running instance
                            db_connector.add_running_instance(instance_id=self._id)
                    elif (current.subtype, TimerEvent):
                        log("DOING:", current)
                        await current.run()
                        can_continue = True
                        # Helper variables for DB insert
                        new_variables = {
                            k: self.variables[k]
                            for k in set(self.variables) - set(before_variables)
                        }
                        current_and_variables_dict[current._id] = new_variables
                        # Create new running instance
                        db_connector.add_running_instance(instance_id=self._id)
                    else:
                        log("DOING:", current)
                        can_continue = True
                        # Helper variables for DB insert
                        new_variables = {
                            k: self.variables[k]
                            for k in set(self.variables) - set(before_variables)
                        }
                        current_and_variables_dict[current._id] = new_variables
                        # Create new running instance
                        db_connector.add_running_instance(instance_id=self._id)

                elif isinstance(current, EndEvent):
                    can_continue = True
                    # Add EndEvent to DB
                    db_connector.add_event(
                        model_name=self.model.model_path,
                        instance_id=self._id,
                        activity_id=current._id,
                        timestamp=datetime.now(),
                        pending=[],
                        activity_variables={},
                    )

                    if isinstance(current.subtype, ErrorEvent):
                        self.pending = []
                        res = self._handle_business_error(current.subtype)
                        if res is not None:
                            res.cancel()
                        exit = True
                        break

                    elif isinstance(current.subtype, TerminateEvent):
                        # Remove all tokens from the process
                        log("DOING:", current)
                        exit = True
                        self.pending = []
                        break

                elif isinstance(current, IntermediateCatchEvent):
                    if isinstance(current.subtype, MessageEvent):
                        if not (
                            message
                            and isinstance(message, RegularMessage)
                            and message.task_id == current._id
                        ):
                            start_message_task = asyncio.create_task(current.run(), name=current._id)
                        if start_message_task.done():
                            log("DOING:", current)
                            can_continue = start_message_task.result()
                            # Helper variables for DB insert
                            new_variables = {
                                k: self.variables[k]
                                for k in set(self.variables) - set(before_variables)
                            }
                            current_and_variables_dict[current._id] = new_variables
                    elif (current.subtype, TimerEvent):
                        log("DOING:", current)
                        await current.run()
                        can_continue = True
                        # Helper variables for DB insert
                        new_variables = {
                            k: self.variables[k]
                            for k in set(self.variables) - set(before_variables)
                        }
                        current_and_variables_dict[current._id] = new_variables

                elif isinstance(current, BoundaryEvent):
                    pass

                elif isinstance(current, UserTask):
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

                elif isinstance(current, SendTask):
                    log("DOING:", current)
                    can_continue = True

                    # Schedule SendTask coroutine
                    asyncio.create_task(current.run(self.variables,_id))

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

                elif isinstance(current, SubProcess):
                    log("DOING:", current)

                    if len(current.attached_events)>0:
                        done, new_current = await self._run_task_with_boundary_events(current)
                        subprocess_variables = done.result()
                        if current != new_current:
                            current = new_current
                            log("DOING:", current)
                    else:
                        subprocess_variables = await self._run_subprocess(current._id, self.variables)

                    if isinstance(subprocess_variables,dict):
                        # Merge subprocess variables with the main process variables
                        self.variables = {**self.variables, **subprocess_variables}

                    # Helper variables for DB insert
                    new_variables = {
                        k: self.variables[k]
                        for k in set(self.variables) - set(before_variables)
                    }
                    current_and_variables_dict[current._id] = new_variables
                    can_continue = True

                elif isinstance(current, CallActivity): 
                    # TODO implement Variables tab CallActivity
                    log("DOING:", current)
                    
                    if len(current.attached_events)>0:
                        done, new_current = await self._run_task_with_boundary_events(current)
                        subprocess_variables = done.result()
                        if current != new_current:
                            current = new_current
                            log("DOING:", current)
                    else:
                        subprocess_variables = await self._run_subprocess(current.called_element)

                    if isinstance(subprocess_variables,dict):
                        # Merge subprocess variables with the main process variables
                        self.variables = {**self.variables, **subprocess_variables}

                    # Helper variables for DB insert
                    new_variables = {
                        k: self.variables[k]
                        for k in set(self.variables) - set(before_variables)
                    }
                    current_and_variables_dict[current._id] = new_variables
                    can_continue = True

                else:
                    if isinstance(current, Task) or isinstance(current, Event):
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

        log("DONE")
        self.state = "finished"
        self.pending = []
        # Running instance finished
        db_connector.finish_running_instance(self._id)
        return self.variables

    async def _run_task_with_boundary_events(self, current):
        async_task_list = []
        async_mapping = {}
        attached = []
        for e in current.attached_events:
            task_element = self.model.elements[e]
            attached.append(task_element)
            async_task = asyncio.create_task(task_element.run(),name=task_element._id)
            async_mapping[async_task.get_name()] = task_element
            async_task_list.append(async_task)
        
        if isinstance(current, SubProcess):
            async_task = asyncio.create_task(self._run_subprocess(current._id, self.variables, attached), name=current._id)
        elif isinstance(current, CallActivity):
            async_task = asyncio.create_task(self._run_subprocess(current.called_element, events=attached), name=current._id)
        else:
            self.pending = [*self.pending, *attached]
            async_task = asyncio.create_task(current.run(), name=current._id)

        async_mapping[async_task.get_name()] = current
        async_task_list.append(async_task)
        done, pend = await asyncio.wait(async_task_list, return_when=asyncio.FIRST_COMPLETED)

        for t in pend:
            t.cancel()
            # Gather canceled Tasks for event loop.
            # Otherwise they won't be canceled until engine shutdowns and will 
            # stay in the loop.
            await asyncio.gather(t, return_exceptions=True)

        done = done.pop()
        return (done, async_mapping[done.get_name()])

    def _handle_business_error(self, err):
        running_coros = asyncio.all_tasks()
        for x in running_coros:
            if x.get_name() in self.model.elements:
                element = self.model.elements[x.get_name()]
                if isinstance(element, BoundaryEvent):
                    if isinstance(element.subtype, ErrorEvent):
                        b_err = element.subtype
                        if err.error_message == b_err.error_message_variable:
                            return x
        return None

    async def handle_regular_message(self, message):
        prefix = f"\t[{self._id}]"
        log = partial(print, prefix)
        user_action = message.message_data
        running_coros = asyncio.all_tasks()

        try:
            event_to_finish = [x for x in running_coros if x.get_name() == message.task_id][0]
        except Exception:
            event_to_finish = False
        
        if event_to_finish:
            event_to_finish.cancel()
            if user_action:
                log("\t- user sent:", user_action)
            self.in_queue.put_nowait(message)
            return True

        return False
        
