import asyncio
from bpmn_model import BpmnModel, UserFormMessage
import random
import sys


m = BpmnModel("models/model_01.bpmn")
NUM_INSTANCES = 1


def get_workload():
    queues = [asyncio.Queue() for i in range(NUM_INSTANCES)]
    instances = [m.run(str(i + 1), {}, queues[i]) for i in range(NUM_INSTANCES)]
    return queues, instances


async def simulate_user(queues):
    WAIT = 0.01

    def auto(text):
        return ""

    def ask(text):
        return auto(text)
        sys.stdout.write(f"\t[?] {text}")
        sys.stdout.flush()
        return sys.stdin.readline().strip()

    for i, q in enumerate(queues):
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


def run_serial():
    async def serial():
        queues, instances = get_workload()
        for i, (q, p) in enumerate(zip(queues, instances)):
            print(f"Running process {i+1}\n-----------------")
            await asyncio.gather(simulate_user([q]), p)

    asyncio.run(serial())


def run_parallel():
    async def parallel():
        queues, instances = get_workload()
        await asyncio.gather(simulate_user(queues), *instances)

    print(f"Running processes\n-----------------")
    asyncio.run(parallel())


# run_parallel()
run_serial()
print("END")