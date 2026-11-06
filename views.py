"""
CRM Views module for All of Us platform.
Handles customer management endpoints, including adding new customers via the CRM modal.
Compatible with both FastAPI/Starlette routing and Django-style view calling conventions.
"""
from typing import Annotated, Any, Dict, Optional
import functools
from datetime import datetime

from starlette.requests import Request
from starlette.responses import RedirectResponse, JSONResponse
from starlette import status
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

import main
from main import (
    Customer,
    User,
    CustomerInteraction,
    require_admin,
    get_db,
    verify_crm_token,
    create_activity_log,
    require_POST,
    add_customer_view,
)

__all__ = ["Customer", "require_POST", "add_customer_view"]

