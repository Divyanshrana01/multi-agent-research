# Puts the four endpoint files together into one router.
#
# Every data endpoint lives under /api. That keeps the URL space clear for the
# frontend's own routes (/reports, /settings), which the SPA catch-all in
# app/spa.py hands to react-router.

from fastapi import APIRouter

from app.api import research, reports, evaluation, system

api_router = APIRouter(prefix="/api")
api_router.include_router(research.router)
api_router.include_router(reports.router)
api_router.include_router(evaluation.router)
api_router.include_router(system.router)

# /health sits at the root, not under /api, because the load balancer's health
# check is configured to that path
health_router = system.health_router

__all__ = ["api_router", "health_router"]
