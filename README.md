# A python module for parsing and executing BPMN models in a single process

Supported elements so far:

-   Start/end events
-   Task (Manual, User, Service) - dummy execution for now
-   Gateways (Exclusive, Parallel)
-   Sequence flow with conditions

Example BPMN model:
![image](https://user-images.githubusercontent.com/714889/114159824-81c65d80-9926-11eb-8b74-6d5dd9bb82ea.png)

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
DOING: UserTask(Task 1)
DOING: Task(DOWN)
	- waiting for all processes in gate.
DOING: Task(UP)
DOING: UserTask(Task 2)
DOING: ServiceTask(Task 3)
	- checking variables={} with ['a==1']... DONE: Result is False
	- going down default path...
DOING: Task(Task down)
DONE
```
