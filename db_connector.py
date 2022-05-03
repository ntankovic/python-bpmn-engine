from pony.orm import *
from datetime import datetime
import env
import os

DB = Database()


class Event(DB.Entity):
    model_name = Required(str)
    instance_id = Required(str)
    activity_id = Required(str)
    timestamp = Required(datetime, precision=6)
    pending = Required(StrArray)
    activity_variables = Required(Json)


class RunningInstance(DB.Entity):
    running = Required(bool)
    ran_as_subprocess = Required(bool)
    instance_id = Required(str, unique=True)
    # maybe need this
    # initiator_instance_id = Optional(str)


def setup_db():
    if not os.path.isdir("database"):
        os.mkdir("database")
    if env.DB["provider"] == "postgres":
        DB.bind(**env.DB)
    else:
        DB.bind(provider="sqlite", filename="database/database.sqlite", create_db=True)
    DB.generate_mapping(create_tables=True)




@db_session
def add_event(
        model_name, instance_id, activity_id, timestamp, pending, activity_variables
):
    Event(
        model_name=model_name,
        instance_id=instance_id,
        activity_id=activity_id,
        timestamp=timestamp,
        pending=pending,
        activity_variables=activity_variables,
    )


@db_session
def add_running_instance(instance_id, ran_as_subprocess=False):
    RunningInstance(instance_id=instance_id, running=True, ran_as_subprocess=ran_as_subprocess)


@db_session
def finish_running_instance(instance):
    finished_instance = RunningInstance.get(instance_id=instance)
    finished_instance.running = False


@db_session
def get_instances_log(running=True):
    log = []
    running_instances = RunningInstance.select(lambda ri: ri.running == running)[:]
    for instance in running_instances:
        instance_dict = {}
        instance_dict[instance.instance_id] = {}
        events = Event.select(lambda e: e.instance_id == instance.instance_id).order_by(
            Event.timestamp
        )[:]
        events_list = []
        for event in events:
            model_path = event.model_name
            event_dict = {}
            event_dict["activity_id"] = event.activity_id
            event_dict["pending"] = event.pending
            event_dict["activity_variables"] = event.activity_variables
            events_list.append(event_dict)

        instance_dict[instance.instance_id]["model_path"] = model_path
        instance_dict[instance.instance_id]["events"] = events_list
        log.append(instance_dict)

    return log
