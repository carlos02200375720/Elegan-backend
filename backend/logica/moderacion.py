from datetime import datetime, timezone
from typing import Any
import uuid

from fastapi import HTTPException
from pymongo import DESCENDING


def inicializar_indices_moderacion(db: Any) -> None:
    db["comment_reports"].create_index(
        [("commentId", 1), ("reporterId", 1)], unique=True,
        name="uq_comment_reporter"
    )
    db["comment_reports"].create_index(
        [("status", 1), ("createdAt", DESCENDING)],
        name="idx_comment_reports_status_created"
    )
    db["blocked_users"].create_index(
        [("userId", 1), ("blockedUserId", 1)], unique=True,
        name="uq_user_blocked_user"
    )


def reportar_comentario(db: Any, user: dict, comment_id: str, reason: str) -> dict:
    comentario = db["comments"].find_one({"_id": comment_id}, {"_id": 1, "userId": 1, "productId": 1})
    if not comentario:
        raise HTTPException(status_code=404, detail="COMMENT_NOT_FOUND")
    reporter_id = str(user["_id"])
    if reporter_id == str(comentario.get("userId", "")):
        raise HTTPException(status_code=400, detail="CANNOT_REPORT_OWN_COMMENT")
    now = datetime.now(timezone.utc)
    try:
        db["comment_reports"].insert_one({
            "_id": str(uuid.uuid4()),
            "commentId": comment_id,
            "productId": str(comentario.get("productId", "")),
            "reportedUserId": str(comentario.get("userId", "")),
            "reporterId": reporter_id,
            "reason": reason.strip()[:500],
            "status": "pending",
            "createdAt": now,
            "updatedAt": now,
        })
    except Exception as error:
        if getattr(error, "code", None) == 11000:
            raise HTTPException(status_code=409, detail="COMMENT_ALREADY_REPORTED")
        raise
    return {"success": True, "status": "pending"}


def bloquear_usuario(db: Any, user: dict, blocked_user_id: str) -> dict:
    owner_id = str(user["_id"])
    target_id = blocked_user_id.strip()
    if not target_id or target_id == owner_id:
        raise HTTPException(status_code=400, detail="INVALID_BLOCK_TARGET")
    if db["users"].find_one({"_id": target_id}, {"_id": 1}) is None:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    db["blocked_users"].update_one(
        {"userId": owner_id, "blockedUserId": target_id},
        {"$setOnInsert": {
            "_id": str(uuid.uuid4()),
            "userId": owner_id,
            "blockedUserId": target_id,
            "createdAt": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    return {"success": True, "blockedUserId": target_id}


def listar_reportes(db: Any, status: str = "pending") -> dict:
    filtro = {} if status == "all" else {"status": status}
    items = []
    for item in db["comment_reports"].find(filtro).sort("createdAt", DESCENDING).limit(500):
        comment = db["comments"].find_one({"_id": item.get("commentId")}) or {}
        items.append({
            "id": str(item.get("_id", "")),
            "commentId": str(item.get("commentId", "")),
            "productId": str(item.get("productId", "")),
            "reportedUserId": str(item.get("reportedUserId", "")),
            "reporterId": str(item.get("reporterId", "")),
            "reason": str(item.get("reason", "")),
            "status": str(item.get("status", "pending")),
            "commentText": str(comment.get("text", "")),
            "createdAt": item.get("createdAt"),
        })
    return {"items": items}


def actualizar_reporte(db: Any, report_id: str, status: str) -> dict:
    if status not in {"reviewed", "dismissed"}:
        raise HTTPException(status_code=400, detail="INVALID_REPORT_STATUS")
    result = db["comment_reports"].update_one(
        {"_id": report_id},
        {"$set": {"status": status, "updatedAt": datetime.now(timezone.utc)}},
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="REPORT_NOT_FOUND")
    return {"success": True, "status": status}
