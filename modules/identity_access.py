import json

from modules.access_mode import normalize_user_access_selection


def admin_did(token):
    try:
        if token is not None and hasattr(token, "get_admin_did"):
            return str(token.get_admin_did() or "").strip()
    except Exception:
        return ""
    return ""


def access_records(token):
    if token is None or not hasattr(token, "get_user_access_list"):
        return []

    current_admin_did = admin_did(token)
    try:
        raw = token.get_user_access_list()
        records = json.loads(raw) if raw else []
    except Exception:
        return []
    if not isinstance(records, list):
        return []

    normalized = []
    for item in records:
        if not isinstance(item, dict):
            continue
        did = str(item.get("did") or "").strip()
        if not did:
            continue
        is_admin_record = bool(current_admin_did and did == current_admin_did)
        normalized.append({
            "did": did,
            "nickname": str(item.get("nickname") or ""),
            "status": "allowed" if is_admin_record else str(item.get("status") or "pending"),
            "can_generate": True if is_admin_record else bool(item.get("can_generate", False)),
            "can_download_models": True if is_admin_record else bool(item.get("can_download_models", False)),
            "is_admin": is_admin_record,
            "updated_at": int(item.get("updated_at") or 0),
        })

    status_rank = {"pending": 0, "allowed": 1, "blocked": 2}
    normalized.sort(key=lambda x: (
        status_rank.get(x["status"], 9),
        -x["updated_at"],
        x["nickname"],
        x["did"],
    ))
    return normalized


def current_user_did(state):
    try:
        user = state.get("user") if isinstance(state, dict) else None
        if user is not None and hasattr(user, "get_did"):
            return str(user.get_did() or "").strip()
    except Exception:
        return ""
    return ""


def state_is_admin(token, state):
    did = current_user_did(state)
    if not did or token is None or not hasattr(token, "is_admin"):
        return False
    try:
        return bool(token.is_admin(did))
    except Exception:
        return False


def can_manage_access(token, state):
    return state_is_admin(token, state)


def can_generate_for(token, selected):
    selected = normalize_user_access_selection(selected)
    if selected and selected == admin_did(token):
        return True
    for record in access_records(token):
        if record["did"] == selected:
            return bool(record.get("can_generate"))
    return False


def can_download_models_for(token, selected, default_user_can_download_models=None):
    selected = normalize_user_access_selection(selected)
    if selected and selected == admin_did(token):
        return True
    for record in access_records(token):
        if record["did"] == selected:
            return bool(record.get("can_download_models"))
    if default_user_can_download_models is None:
        import enhanced.all_parameters as ads
        default_user_can_download_models = ads.get_admin_default("default_user_can_download_models")
    return bool(default_user_can_download_models)


def guest_can_generate(token, default=None):
    try:
        if token is not None and hasattr(token, "get_guest_can_generate"):
            return bool(token.get_guest_can_generate())
    except Exception:
        pass
    if default is None:
        import enhanced.all_parameters as ads
        default = ads.get_admin_default("guest_can_generate")
    return bool(default)


def guest_can_download_models(token, default=None):
    try:
        if token is not None and hasattr(token, "get_guest_can_download_models"):
            return bool(token.get_guest_can_download_models())
    except Exception:
        pass
    if default is None:
        import enhanced.all_parameters as ads
        default = ads.get_admin_default("guest_can_download_models")
    return bool(default)


def set_user_permissions(token, selected, can_generate, can_download_models, manager_state=None):
    selected = normalize_user_access_selection(selected)
    authorized = bool(token is not None and can_manage_access(token, manager_state))
    result = {
        "selected": selected,
        "ok": bool(selected and token is not None and authorized and selected != admin_did(token)),
        "authorized": authorized,
        "generate_result": "missing",
        "download_result": "missing",
        "saved_generate": None,
        "saved_download": None,
        "persisted": False,
    }
    if not result["ok"]:
        if token is not None and selected == admin_did(token):
            result["generate_result"] = "protected_admin"
            result["download_result"] = "protected_admin"
        elif not authorized:
            result["generate_result"] = "unauthorized"
            result["download_result"] = "unauthorized"
        return result

    if hasattr(token, "set_user_can_generate"):
        result["generate_result"] = token.set_user_can_generate(selected, bool(can_generate))
        result["ok"] = result["ok"] and result["generate_result"] == "OK"
    else:
        result["ok"] = False

    if hasattr(token, "set_user_can_download_models"):
        result["download_result"] = token.set_user_can_download_models(selected, bool(can_download_models))
        result["ok"] = result["ok"] and result["download_result"] == "OK"
    else:
        result["ok"] = False

    if result["ok"]:
        result["saved_generate"] = can_generate_for(token, selected)
        result["saved_download"] = can_download_models_for(token, selected)
        result["persisted"] = (
            result["saved_generate"] == bool(can_generate)
            and result["saved_download"] == bool(can_download_models)
        )
    return result


def set_guest_permissions(token, can_generate, can_download_models, manager_state=None):
    authorized = bool(token is not None and can_manage_access(token, manager_state))
    result = {
        "ok": authorized,
        "authorized": authorized,
        "generate_result": "missing",
        "download_result": "missing",
        "saved_generate": None,
        "saved_download": None,
        "persisted": False,
    }
    if not result["ok"]:
        if not authorized:
            result["generate_result"] = "unauthorized"
            result["download_result"] = "unauthorized"
        return result

    if hasattr(token, "set_guest_can_generate"):
        result["generate_result"] = token.set_guest_can_generate(bool(can_generate))
        result["ok"] = result["ok"] and result["generate_result"] == "OK"
    else:
        result["ok"] = False

    if hasattr(token, "set_guest_can_download_models"):
        result["download_result"] = token.set_guest_can_download_models(bool(can_download_models))
        result["ok"] = result["ok"] and result["download_result"] == "OK"
    else:
        result["ok"] = False

    if result["ok"]:
        result["saved_generate"] = guest_can_generate(token)
        result["saved_download"] = guest_can_download_models(token)
        result["persisted"] = (
            result["saved_generate"] == bool(can_generate)
            and result["saved_download"] == bool(can_download_models)
        )
    return result
