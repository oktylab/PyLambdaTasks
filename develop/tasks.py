from typing import Annotated, Dict, Any
from pylambdatasks import Depends
from pylambdatasks.state import StateManager
from handler import app
import asyncio

def get_user_context() -> Dict[str, str]:
    """A simple dependency providing a mock user context."""
    return {"user_id": "user-123", "role": "admin"}

UserContext = Annotated[Dict[str, str], Depends(get_user_context)]


@app.task(name="ADD_NUMBERS")
async def add_numbers(
    self: StateManager, 
    a: int, 
    b: int
):
    print(f"Executing ADD_NUMBERS task: {a} + {b}")
    return {"result": a + b}


@app.task(name="PROCESS_DATA")
async def process_data(
    self: StateManager, 
    data: Dict[str, Any], 
    context: UserContext
):
    print(f"Executing PROCESS_DATA task for user {context['user_id']}")
    
    processed_data = {key.upper(): value for key, value in data.items()}


    CONCURRENT_TASKS = 10
    tasks_to_run = [
        add_numbers.invoke(a=5, b=10)
        for _ in range(CONCURRENT_TASKS)
    ]
    print(f"Dispatching {CONCURRENT_TASKS} concurrent 'ADD_NUMBERS' tasks to the emulator...")
    results = await asyncio.gather(*tasks_to_run)
    print(results)



    # Use the injected state manager to add custom metadata to the task record
    await self.update_metadata({
        "processed_keys": list(processed_data.keys()),
        "processed_by": context['user_id'],
        "result": results
    })
    
    return {
        "processed_data": processed_data,
        "results": results
    }