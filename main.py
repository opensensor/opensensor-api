from fastapi_pagination import add_pagination

from opensensor.app import app
from opensensor.collection_apis import router as collection_apis_router


@app.get("/")
async def root():
    return {"message": "Welcome to OpenSensor.io!  Navigate to /docs for current Alpha API spec."}


add_pagination(app)
app.include_router(collection_apis_router)
