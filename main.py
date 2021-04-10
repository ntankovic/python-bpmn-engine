import asyncio
from bpmn_model import BpmnModel
import random


m = BpmnModel("models/model_01.bpmn")
NUM_INSTANCES = 3


def get_workload():
    queues = [asyncio.Queue()] * NUM_INSTANCES
    instances = [m.run(str(i + 1), {}, queues[i]) for i in range(NUM_INSTANCES)]
    return queues, instances


async def simulate_user(queues):
    for q in queues:
        for i in range(3):
            a = random.randint(1, 2)
            await q.put(f"a={a}")
            await asyncio.sleep(0.5)


def run_serial():
    async def serial():
        queues, instances = get_workload()
        for i, (q, p) in enumerate(zip(queues, instances)):
            print(f"Running process {i+1}\n-----------------")
            await asyncio.gather(simulate_user([q]), p)
            print()

    asyncio.run(serial())


def run_parallel():
    async def parallel():
        queues, instances = get_workload()
        await asyncio.gather(simulate_user(queues), *instances)

    print(f"Running processes\n-----------------")
    asyncio.run(parallel())


# run_parallel()
run_serial()