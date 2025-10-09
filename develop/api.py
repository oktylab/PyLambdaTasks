import asyncio
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict

from tasks import add_numbers, process_data

api = FastAPI(title="PyLambdaTasks Client API")

class AddPayload(BaseModel):
    a: int
    b: int

class ProcessPayload(BaseModel):
    data: Dict[str, Any]

@api.post("/invoke/add", status_code=202)
async def invoke_add_task(payload: AddPayload):
    # result_handle = await add_numbers.delay(a=payload.a, b=payload.b)
    # return {"message": "Task dispatched.", "task_id": result_handle.task_id}

    result = await add_numbers.invoke(a=payload.a, b=payload.b)
    print(result)
    return result


@api.post("/invoke/concurrent")
async def invoke_add_task(payload: AddPayload):
    CONCURRENT_TASKS = 10
    tasks_to_run = [
        add_numbers.invoke(a=payload.a, b=payload.b)
        for _ in range(CONCURRENT_TASKS)
    ]
    print(f"Dispatching {CONCURRENT_TASKS} concurrent 'ADD_NUMBERS' tasks to the emulator...")
    results = await asyncio.gather(*tasks_to_run)

    print(f"Received {len(results)} results back from the emulator.")

    try:
        total_sum = sum(result['result'] for result in results)
    except (KeyError, TypeError):
        return {"error": "Failed to process results.", "details": results}

    return {
        "message": f"Successfully executed and summed {CONCURRENT_TASKS} tasks.",
        "total_sum": total_sum,
        "individual_results": results
    }




@api.post("/invoke/process", status_code=202)
async def invoke_process_task(payload: ProcessPayload):
    result_handle = await process_data.invoke(data=payload.data)
    return {"message": "Task dispatched.", "task_id": result_handle}


if __name__ == "__main__":
    uvicorn.run(
        "api:api",
        host="0.0.0.0", 
        port=8000,
        reload=True,
    )