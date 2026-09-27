import hashlib
from functools import cache

from pydantic import BaseModel
from pydantic import TypeAdapter


@cache
def adapter[T](shape: type[T]) -> TypeAdapter[T]:
    return TypeAdapter(shape)


def params_key(prefix: str, params: BaseModel | None = None) -> str:
    if params is None:
        return prefix

    digest = hashlib.blake2b(params.model_dump_json().encode(), digest_size=8)

    return f"{prefix}:{digest.hexdigest()}"
