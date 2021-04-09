# A python module for parsing and executing BPMN models in a single process

Supported elements so far:
* Start/end events
* Task (Manual, User, Service) - dummy execution for now
* Gateways (Exclusive, Parallel)
* Sequence flow with conditions

Example BPMN model:
![image](https://user-images.githubusercontent.com/714889/114159824-81c65d80-9926-11eb-8b74-6d5dd9bb82ea.png)

Example execution trace:

```
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
