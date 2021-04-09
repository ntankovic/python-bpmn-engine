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