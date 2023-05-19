from fastapi_pagination import add_pagination

from opensensor.collection_apis import *


@app.get("/")
async def root():
    return {"message": "Welcome to OpenSensor.io!  Navigate to /docs for current Alpha API spec."}


add_pagination(app)
