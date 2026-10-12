"""Routes for the ACCESS-01 fixture module (none; the manifest is what fails)."""

from fastapi import APIRouter

router = APIRouter(prefix="/fixture", tags=["fixture"])
