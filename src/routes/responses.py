from fastapi import Response


class JSONText(Response):
    # if serialized, serve as is, straight from the cache
    media_type = "application/json"
