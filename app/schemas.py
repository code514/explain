from pydantic import BaseModel


class HelloWorldResponse(BaseModel):
    message: str
