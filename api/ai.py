"""AI assistant endpoints.

The browser only talks to these local endpoints; the model API key never leaves
the server.  Write operations are returned as drafts and applied through
``/actions/<id>/confirm`` so the user always sees a confirmation card first.
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from services_ai import (
    apply_action,
    cancel_action,
    create_conversation,
    delete_conversation,
    get_conversation_detail,
    list_conversations,
    migrate_legacy_ai_config,
    public_ai_config,
    run_chat,
    save_ai_config,
    test_ai_connection,
    topology_completion,
)

bp = Blueprint("ai", __name__, url_prefix="/api/ai")


@bp.get("/config")
def get_config():
    migrate_legacy_ai_config()
    return jsonify(public_ai_config())


@bp.put("/config")
def put_config():
    data = request.get_json(silent=True) or {}
    cfg = save_ai_config(data)
    return jsonify(public_ai_config(cfg))


@bp.post("/test")
def test_config():
    data = request.get_json(silent=True) or {}
    draft = data.get("draft") if isinstance(data.get("draft"), dict) else data
    return jsonify(test_ai_connection(draft))


@bp.get("/conversations")
def conversations():
    return jsonify({"items": list_conversations(50)})


@bp.post("/conversations")
def new_conversation():
    data = request.get_json(silent=True) or {}
    return jsonify(create_conversation(data.get("project_id"))), 201


@bp.get("/conversations/<conversation_id>")
def conversation_detail(conversation_id):
    return jsonify(get_conversation_detail(conversation_id))


@bp.delete("/conversations/<conversation_id>")
def remove_conversation(conversation_id):
    return jsonify(delete_conversation(conversation_id))


@bp.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    result = run_chat(
        data.get("conversation_id"),
        data.get("message"),
        data.get("context"),
    )
    return jsonify(result)


@bp.post("/topology")
def topology():
    data = request.get_json(silent=True) or {}
    return Response(
        topology_completion(data.get("messages")),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.post("/actions/<action_id>/confirm")
def confirm_action(action_id):
    data = request.get_json(silent=True) or {}
    values = data.get("values") if isinstance(data.get("values"), dict) else None
    return jsonify({"action": apply_action(action_id, values)})


@bp.post("/actions/<action_id>/cancel")
def cancel(action_id):
    return jsonify({"action": cancel_action(action_id)})
