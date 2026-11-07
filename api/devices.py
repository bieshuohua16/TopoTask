"""Device list (BOM) endpoints and diagram-node device links."""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from db import ApiError, get_db
from services import nodes_with_links, text
from services_devices import (
    create_device_and_link,
    create_device_record,
    create_device_template,
    delete_device_record,
    delete_device_template,
    device_dict,
    device_summary,
    export_devices_csv,
    export_filename_header,
    import_template_csv,
    link_device_to_node,
    list_device_templates,
    list_devices,
    preview_template_csv,
    template_sample_csv,
    unlink_device_from_node,
    update_device_record,
    update_device_template,
)

bp = Blueprint("devices", __name__, url_prefix="/api")


def _node_payload(diagram_id: str, node_key: str) -> dict:
    node = next(
        (item for item in nodes_with_links(diagram_id) if item["node_key"] == node_key),
        None,
    )
    if not node:
        raise ApiError("节点不存在", 404, "node_not_found")
    return node


@bp.get("/devices")
def get_devices():
    project_id = text(request.args.get("project_id"))
    if not project_id:
        raise ApiError("缺少 project_id", 400, "project_required")
    return jsonify(
        list_devices(
            project_id,
            category=request.args.get("category"),
            status=request.args.get("status"),
            q=request.args.get("q"),
            linked=request.args.get("linked"),
        )
    )


@bp.post("/devices")
def create_device():
    data = request.get_json(silent=True) or {}
    project_id = text(data.get("project_id"))
    if not project_id:
        raise ApiError("缺少 project_id", 400, "project_required")
    device_id = create_device_record(project_id, data)
    get_db().commit()
    return jsonify(device_dict(device_id)), 201


@bp.get("/devices/<device_id>")
def get_device(device_id):
    return jsonify(device_dict(device_id))


@bp.patch("/devices/<device_id>")
def patch_device(device_id):
    data = request.get_json(silent=True) or {}
    device = update_device_record(device_id, data)
    get_db().commit()
    return jsonify(device)


@bp.delete("/devices/<device_id>")
def delete_device(device_id):
    result = delete_device_record(device_id)
    get_db().commit()
    return jsonify(result)


@bp.get("/projects/<project_id>/devices/summary")
def project_device_summary(project_id):
    return jsonify(device_summary(project_id))


@bp.get("/projects/<project_id>/devices/export.csv")
def export_devices(project_id):
    filename, body = export_devices_csv(project_id)
    return Response(
        body,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": export_filename_header(filename)},
    )


# ---------------------------------------------------------------------------
# Global device templates
# ---------------------------------------------------------------------------
@bp.get("/device-templates")
def get_device_templates():
    return jsonify(
        list_device_templates(
            category=request.args.get("category"),
            q=request.args.get("q"),
            brand=request.args.get("brand"),
        )
    )


@bp.get("/device-templates/sample.csv")
def download_template_sample():
    filename, body = template_sample_csv()
    return Response(
        body,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": export_filename_header(filename)},
    )


@bp.post("/device-templates")
def create_template():
    data = request.get_json(silent=True) or {}
    template = create_device_template(data)
    get_db().commit()
    return jsonify(template), 201


@bp.get("/device-templates/<template_id>")
def get_template(template_id):
    from services_devices import _template_dict, _template_row

    return jsonify(_template_dict(_template_row(template_id)))


@bp.patch("/device-templates/<template_id>")
def patch_template(template_id):
    data = request.get_json(silent=True) or {}
    template = update_device_template(template_id, data)
    get_db().commit()
    return jsonify(template)


@bp.delete("/device-templates/<template_id>")
def delete_template(template_id):
    result = delete_device_template(template_id)
    get_db().commit()
    return jsonify(result)


@bp.post("/device-templates/import")
def import_templates():
    upload = request.files.get("file")
    if upload is not None:
        raw = upload.read()
    else:
        data = request.get_json(silent=True) or {}
        raw = text(data.get("text")).encode("utf-8")
    if not raw:
        raise ApiError("请选择要导入的 CSV 文件", 400, "file_required")
    if len(raw) > 2 * 1024 * 1024:
        raise ApiError("CSV 文件不能超过 2 MB", 400, "file_too_large")
    dry_run = (request.form.get("dry_run") or "").lower() in ("1", "true", "yes")
    mode = request.form.get("mode") or "skip"
    if not request.form and request.is_json:
        data = request.get_json(silent=True) or {}
        dry_run = bool(data.get("dry_run"))
        mode = text(data.get("mode")) or "skip"
    if dry_run:
        return jsonify(preview_template_csv(raw))
    result = import_template_csv(raw, mode=mode)
    get_db().commit()
    return jsonify(result)


# ---------------------------------------------------------------------------
# Device -> node (device-centric)
# ---------------------------------------------------------------------------
@bp.post("/devices/<device_id>/nodes")
def link_node(device_id):
    data = request.get_json(silent=True) or {}
    diagram_id = text(data.get("diagram_id"))
    node_key = text(data.get("node_key"))
    if not diagram_id or not node_key:
        raise ApiError("缺少 diagram_id / node_key", 400, "node_required")
    device = link_device_to_node(
        device_id, diagram_id, node_key,
        quantity=data.get("quantity"),
        note=text(data.get("note")),
    )
    get_db().commit()
    return jsonify(device), 201


@bp.delete("/devices/<device_id>/nodes/<diagram_id>/<node_key>")
def unlink_node(device_id, diagram_id, node_key):
    device = unlink_device_from_node(device_id, diagram_id, node_key)
    get_db().commit()
    return jsonify(device)


# ---------------------------------------------------------------------------
# Diagram node -> device (topology-centric)
# ---------------------------------------------------------------------------
@bp.post("/diagrams/<diagram_id>/nodes/<node_key>/devices")
def node_link_device(diagram_id, node_key):
    data = request.get_json(silent=True) or {}
    create = data.get("create_device")
    if isinstance(create, dict):
        device_id = create_device_and_link(diagram_id, node_key, create)
    else:
        device_id = text(data.get("device_id"))
        if not device_id:
            raise ApiError("缺少 device_id", 400, "device_required")
        link_device_to_node(
            device_id, diagram_id, node_key,
            quantity=data.get("quantity"),
            note=text(data.get("note")),
        )
    get_db().commit()
    return jsonify(
        {
            "node": _node_payload(diagram_id, node_key),
            "device": device_dict(device_id),
        }
    ), 201


@bp.delete("/diagrams/<diagram_id>/nodes/<node_key>/devices/<device_id>")
def node_unlink_device(diagram_id, node_key, device_id):
    unlink_device_from_node(device_id, diagram_id, node_key)
    get_db().commit()
    return jsonify(
        {
            "node": _node_payload(diagram_id, node_key),
            "device": device_dict(device_id),
        }
    )
