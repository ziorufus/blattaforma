"""Example module: hello-world.

Demonstrates the module contract described in app/module_loader.py. Two
roles are available: "standard" (sees "Hello world") and "premium" (sees
"Hello wonderful world"). Admins always get the best available message.
"""

from fastapi import APIRouter, Depends

from ..deps import require_module_role

MODULE_NAME = "hello-world"
MODULE_LABEL = "Hello world"
MODULE_ROLES = ["standard", "premium"]

router = APIRouter()


@router.get("/greeting")
def get_greeting(roles: list[str] = Depends(require_module_role(MODULE_NAME))):
    message = "Hello wonderful world" if "premium" in roles else "Hello world"
    return {"message": message, "roles": roles}
