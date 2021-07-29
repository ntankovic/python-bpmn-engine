# A python module for parsing and executing BPMN models

Supported BPMN elements so far:

-   Start/end events
-   Task (Manual, User, Service, Send) - dummy execution for now
    - Service Task - keywords must be specified with Extension/Property
        - Database keywords : db_location,db_parametars,db_request_type,db_key
        - Web service keywords : web_service_location,web_service_request_type,web_service_parametars,web_service_response
    - Send Task - keywords must be specified with Extension/Property
        - Notification service keywords : notification_service_location, notification_service_request_type,
        notification_service_parametars,
        notification_service_receiver
-   Gateways (Exclusive, Parallel)
-   Sequence flow with conditions - condition must be in key:value format, currently string values are supported

Pending features:

-   full fledged REST API
-   process instance persistence

Example BPMN model used for demo:
![image](https://user-images.githubusercontent.com/714889/114159824-81c65d80-9926-11eb-8b74-6d5dd9bb82ea.png)

The package can be used as a embedded bpmn-server (see `main.py`) or
as a standalone server exposing a REST API (see `server.py`)

Example usage:

```python
import asyncio
from bpmn_model import BpmnModel, UserFormMessage
import random
import sys


m = BpmnModel("models/model_01.bpmn")
NUM_INSTANCES = 2


async def get_workload():
    return [await m.create_instance(str(i + 1), {}) for i in range(NUM_INSTANCES)]


async def simulate_user(q):
    WAIT = 0.01

    def ask(text):
        sys.stdout.write(f"\t[?] {text}")
        sys.stdout.flush()
        text = sys.stdin.readline().strip()
        return (
            {
                key: value
                for statement in (text.split(",") if "," in text else [text])
                for key, value in statement.split("=")
            }
            if text
            else {}
        )

    q.put_nowait(UserFormMessage("t_wrong", "null"))  # Wrong message
    await asyncio.sleep(WAIT)

    a = random.randint(1, 2)
    default = f"option={a}"
    data = ask(f"Form input: [{default}]")
    q.put_nowait(UserFormMessage("t0", data if data != "" else default))
    await asyncio.sleep(WAIT)

    q.put_nowait(UserFormMessage("tup", ask("Form input [tup]: ")))
    await asyncio.sleep(WAIT)

    q.put_nowait(UserFormMessage("t_wrong", "null"))  # Wrong message
    await asyncio.sleep(WAIT)

    q.put_nowait(UserFormMessage("tdown", ask("Form input [tdown]: ")))
    await asyncio.sleep(WAIT)

    q.put_nowait(UserFormMessage("t_wrong", "null"))  # Wrong message
    await asyncio.sleep(WAIT)

    q.put_nowait(UserFormMessage("tup2", ask("Form input [tup2]: ")))
    await asyncio.sleep(WAIT)

    q.put_nowait(UserFormMessage("t_wrong", "null"))  # Wrong message
    await asyncio.sleep(WAIT)

    q.put_nowait(UserFormMessage("tdown2", ask("Form input [tdown2]: ")))
    await asyncio.sleep(WAIT)


def run_parallel():
    async def parallel():
        instances = await get_workload()
        users = [simulate_user(i.in_queue) for i in instances]
        processes = [p.run() for p in instances]
        await asyncio.gather(*users, *processes)

    print(f"Running processes\n-----------------")
    asyncio.run(parallel())


run_parallel()
```

Example execution trace:

```python
Running process 1
-----------------
        [1] --> msg in: t_wrong
        [1] Waiting for user... [UserTask(Which option?)]
        [1] --> msg in: t0
        [1] DOING: UserTask(Which option?)
        [1] Waiting for user... [UserTask(Down), UserTask(Up)]
        [1] --> msg in: tup
        [1] DOING: UserTask(Up)
        [1] Waiting for user... [UserTask(Down), ParallelGateway(ParallelGateway_0vffee4)]
        [1] --> msg in: t_wrong
        [1] Waiting for user... [UserTask(Down), ParallelGateway(ParallelGateway_0vffee4)]
        [1] --> msg in: tdown
        [1] DOING: UserTask(Down)
        [1] DOING: ManualTask(Manual Task 2)
        [1] DOING: ServiceTask(Task 3)
        [1]     - checking variables={} with ['option==1']...
        [1]       DONE: Result is False
        [1]     - going down default path...
        [1] Waiting for user... [UserTask(Task down)]
        [1] --> msg in: t_wrong
        [1] Waiting for user... [UserTask(Task down)]
        [1] --> msg in: tup2
        [1] Waiting for user... [UserTask(Task down)]
        [1] --> msg in: t_wrong
        [1] Waiting for user... [UserTask(Task down)]
        [1] --> msg in: tdown2
        [1] DOING: UserTask(Task down)
        [1] DONE
Running process 2
-----------------
        [2] --> msg in: t_wrong
        [2] Waiting for user... [UserTask(Which option?)]
        [2] --> msg in: t0
        [2] DOING: UserTask(Which option?)
        [2] Waiting for user... [UserTask(Down), UserTask(Up)]
        [2] --> msg in: tup
        [2] DOING: UserTask(Up)
        [2] Waiting for user... [UserTask(Down), ParallelGateway(ParallelGateway_0vffee4)]
        [2] --> msg in: t_wrong
        [2] Waiting for user... [UserTask(Down), ParallelGateway(ParallelGateway_0vffee4)]
        [2] --> msg in: tdown
        [2] DOING: UserTask(Down)
        [2] DOING: ManualTask(Manual Task 2)
        [2] DOING: ServiceTask(Task 3)
        [2]     - checking variables={} with ['option==1']...
        [2]       DONE: Result is False
        [2]     - going down default path...
        [2] Waiting for user... [UserTask(Task down)]
        [2] --> msg in: t_wrong
        [2] Waiting for user... [UserTask(Task down)]
        [2] --> msg in: tup2
        [2] Waiting for user... [UserTask(Task down)]
        [2] --> msg in: t_wrong
        [2] Waiting for user... [UserTask(Task down)]
        [2] --> msg in: tdown2
        [2] DOING: UserTask(Task down)
        [2] DONE
```
