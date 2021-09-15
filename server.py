import aiohttp
from aiohttp import web
from uuid import uuid4
import asyncio
from bpmn_model import BpmnModel, UserFormMessage
import aiohttp_cors
import db_connector

# Setup database
db_connector.setup_db()

# uuid4 = lambda: 2  # hardcoded for easy testing

m = BpmnModel("models/diagram_1.bpmn")  # hardcoded for now


async def run_with_server(app):
    app["bpmn_model"] = m
    log = db_connector.get_running_instances_log()
    for l in log:
        for key in l:
            instance = await app["bpmn_model"].create_instance(key, {})
            instance = await instance.run_from_log(l[key]["events"])
            asyncio.create_task(instance.run())


async def handle_new_instance(request):
    _id = str(uuid4())
    instance = await app["bpmn_model"].create_instance(_id, {})
    asyncio.create_task(instance.run())
    return web.json_response({"id": _id})


async def handle_form(request):
    post = await request.json()
    instance_id = request.match_info.get("instance_id")
    task_id = request.match_info.get("task_id")
    app["bpmn_model"].instances[instance_id].in_queue.put_nowait(
        UserFormMessage(task_id, post)
    )

    return web.json_response({"status": "OK"})


async def handle_task_info(request):
    instance_id = request.match_info.get("instance_id")
    task_id = request.match_info.get("task_id")
    if instance_id not in app["bpmn_model"].instances:
        raise aiohttp.web.HTTPNotFound
    instance = app["bpmn_model"].instances[instance_id]
    task = instance.model.elements[task_id]
    print(task.get_info())

    return web.json_response(task.get_info())


async def handle_instance_info(request):
    instance_id = request.match_info.get("instance_id")
    if instance_id not in app["bpmn_model"].instances:
        raise aiohttp.web.HTTPNotFound
    instance = app["bpmn_model"].instances[instance_id]

    return web.json_response(instance.get_info())


app = web.Application()
app.on_startup.append(run_with_server)
app.add_routes([web.post("/instance", handle_new_instance)])
app.add_routes([web.post("/instance/{instance_id}/task/{task_id}/form", handle_form)])
app.add_routes([web.get("/instance/{instance_id}/task/{task_id}", handle_task_info)])
app.add_routes([web.get("/instance/{instance_id}", handle_instance_info)])

cors = aiohttp_cors.setup(
    app,
    defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*",
        )
    },
)

for route in list(app.router.routes()):
    cors.add(route)

web.run_app(app)
