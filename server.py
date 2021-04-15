from aiohttp import web
import asyncio
from bpmn_model import BpmnModel, UserFormMessage
import random
import sys


m = BpmnModel("models/model_01.bpmn")


async def run_with_server(app):
    app["bpmn_queue"] = queue = asyncio.Queue()
    app["bpmn_model"] = m
    app["bpmn_instance"] = asyncio.create_task(m.run("1", {}, queue))


async def handle_form(request):
    post = await request.json()
    task_id = request.match_info.get("id")
    app["bpmn_queue"].put_nowait(UserFormMessage(task_id, post))

    return web.json_response({"status": "OK"})


async def handle_instance(request):
    instance_id = request.match_info.get("instance_id")
    instance = app["bpmn_model"].instances[instance_id]

    print(instance.get_info())
    return web.json_response(instance.get_info())


app = web.Application()
app.on_startup.append(run_with_server)
app.add_routes([web.post("/form/{id}", handle_form)])
app.add_routes([web.get("/info/{instance_id}", handle_instance)])

web.run_app(app)