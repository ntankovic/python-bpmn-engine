# A python module for parsing and executing BPMN models

Supported elements so far:

-   Start/end events
-   Task (Manual, User, Service) - dummy execution for now
-   Gateways (Exclusive, Parallel)
-   Sequence flow with conditions

Soon:
-   full fledged REST API
-   process instance persistence

Example BPMN model:
![image](https://user-images.githubusercontent.com/714889/114159824-81c65d80-9926-11eb-8b74-6d5dd9bb82ea.png)

Usage with an REST API: see `server.py` 

Example usage:

```python
import asyncio
from bpmn_model import BpmnModel


m = BpmnModel("models/model_01.bpmn")

p1 = m.run("1", {"a": 1})
p2 = m.run("2", {"a": 2})

run = [p1, p2]


def run_serial():
    for i, p in enumerate(run):
        print(f"Running process {i+1}\n-----------------")
        asyncio.run(p)
        print()


def run_parallel():
    async def parallel():
        await asyncio.gather(p1, p2)

    print(f"Running processes\n-----------------")
    asyncio.run(parallel())


# run_parallel()
run_serial()
```

Example execution trace:

```python
Running process 1
-----------------
        [1] DOING: UserTask(Task 1)
        [1] DOING: Task(DOWN)
        [1]     - waiting for all processes in gate.
        [1] DOING: Task(UP)
        [1] DOING: ManualTask(Manual Task 2)
        [1] DOING: ServiceTask(Task 3)
        [1]     - checking variables={'a': 1} with ['a==1']...  [1] DONE: Result is True
        [1]     - going down default path...
        [1] DOING: Task(Task down)
        [1] DONE

Running process 2
-----------------
        [2] DOING: UserTask(Task 1)
        [2] DOING: Task(DOWN)
        [2]     - waiting for all processes in gate.
        [2] DOING: Task(UP)
        [2] DOING: ManualTask(Manual Task 2)
        [2] DOING: ServiceTask(Task 3)
        [2]     - checking variables={'a': 2} with ['a==1']...  [2] DONE: Result is False
        [2]     - going down default path...
        [2] DOING: Task(Task down)
        [2] DONE
```
