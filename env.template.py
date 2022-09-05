SYSTEM_VARS = {"_frontend_url": "http://localhost:9001"}
DB = {
    "provider": "sqlite",
    "user": "postgres",
    "password": "root",
    "host": "localhost",
    "database": "a2",
}
DS = {
    "airtable": {"type": "http-connector", "url": "http://0.0.0.0:8082"},
    "notification": {"type": "http-connector", "url": "http://0.0.0.0:8081"},
    "pdf": {"type": "http-connector", "url": "http://0.0.0.0:8083"},
    "test": {"type": "http-connector", "url": "http://212.183.159.230/"},
    "scraper": {"type": "http-connector", "url": "http://172.17.0.1:60194"},
    "keyword_score_service": {"type": "http-connector", "url": "http://172.17.0.1:19770"},
    "dart_db": {"type": "http-connector", "url": "http://172.17.0.1:60194"},
    "db_connector_python": {"type": "http-connector", "url": "http://172.17.0.1:57881"},
    "meta_desc_gen_service": {"type": "http-connector", "url": "http://172.17.0.1:1307"},
}
# http://212.183.159.230/
