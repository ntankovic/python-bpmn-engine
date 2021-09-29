import aiohttp
import os
from aiohttp import web
from uuid import uuid4
import asyncio
from bpmn_model import BpmnModel, UserFormMessage
import aiohttp_cors
import db_connector
from functools import reduce

# Setup database
db_connector.setup_db()
routes = web.RouteTableDef()

# uuid4 = lambda: 2  # hardcoded for easy testing

m = BpmnModel("strucna_praksa.bpmn")  # hardcoded for now


async def run_with_server(app):
    app["bpmn_model"] = m
    log = db_connector.get_running_instances_log()
    for l in log:
        for key in l:
            instance = await app["bpmn_model"].create_instance(key, {})
            instance = await instance.run_from_log(l[key]["events"])
            asyncio.create_task(instance.run())


@routes.get("/model")
async def get_model(request):
    # model_id = request.match_info.get("model_id")
    return web.FileResponse(path=os.path.join("models", app["bpmn_model"].model_path))


@routes.post("/instance")
async def handle_new_instance(request):
    _id = str(uuid4())
    instance = await app["bpmn_model"].create_instance(_id, {})
    asyncio.create_task(instance.run())
    return web.json_response({"id": _id})


@routes.post("/instance/{instance_id}/task/{task_id}/form")
async def handle_form(request):
    post = await request.json()
    instance_id = request.match_info.get("instance_id")
    task_id = request.match_info.get("task_id")
    app["bpmn_model"].instances[instance_id].in_queue.put_nowait(
        UserFormMessage(task_id, post)
    )

    return web.json_response({"status": "OK"})


@routes.get("/instance")
async def search_instance(request):
    params = request.rel_url.query
    queries = []
    try:
        strip_lower = lambda x: x.strip().lower()
        check_colon = lambda x: x if ":" in x else f":{x}"

        queries = list(
            tuple(
                map(
                    strip_lower,
                    check_colon(q).split(":"),
                )
            )
            for q in params["q"].split(",")
        )
    except:
        return web.json_response({"error": "invalid_query"}, status=400)

    result_ids = []
    for (att, value) in queries:
        ids = []
        for _id, instance in app["bpmn_model"].instances.items():
            search_atts = []
            if not att:
                search_atts = list(instance.variables.keys())
            else:
                for key in instance.variables.keys():
                    if not att or att in key.lower():
                        search_atts.append(key)
            search_atts = filter(
                lambda x: isinstance(instance.variables[x], str), search_atts
            )

            for search_att in search_atts:
                if search_att and value in instance.variables[search_att].lower():
                    # data.append(instance.to_json())
                    ids.append(_id)
        result_ids.append(set(ids))

    ids = reduce(lambda a, x: a.intersection(x), result_ids[:-1], result_ids[0])

    data = []
    for _id in ids:
        data.append(app["bpmn_model"].instances[_id].to_json())

    return web.json_response({"status": "ok", "results": data})


@routes.get("/instance/{instance_id}/task/{task_id}")
async def handle_task_info(request):
    instance_id = request.match_info.get("instance_id")
    task_id = request.match_info.get("task_id")
    if instance_id not in app["bpmn_model"].instances:
        raise aiohttp.web.HTTPNotFound
    instance = app["bpmn_model"].instances[instance_id]
    task = instance.model.elements[task_id]

    return web.json_response(task.get_info())


@routes.get("/instance/{instance_id}")
async def handle_instance_info(request):
    instance_id = request.match_info.get("instance_id")
    if instance_id not in app["bpmn_model"].instances:
        raise aiohttp.web.HTTPNotFound
    instance = app["bpmn_model"].instances[instance_id].to_json()

    return web.json_response(instance)


app = None


def run():
    global app
    app = web.Application()
    app.on_startup.append(run_with_server)
    app.add_routes(routes)

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

    return app


async def serve():
    return run()


if __name__ == "__main__":
    app = run()
    web.run_app(app, port=9000)
