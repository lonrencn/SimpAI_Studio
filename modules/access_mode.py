import json

import shared


def has_admin_identity():
    try:
        token = getattr(shared, "token", None)
        return bool(token and token.get_admin_did())
    except Exception:
        return False


def get_access_mode():
    try:
        token = getattr(shared, "token", None)
        if token is None:
            return "local"

        return "multi-user" if has_admin_identity() else "local"
    except Exception:
        return "local"


def is_local_mode():
    return get_access_mode() == "local"


def is_multi_user_mode():
    return get_access_mode() == "multi-user"


def get_user_access_record(user_did):
    try:
        token = getattr(shared, "token", None)
        if token is None or not user_did or not hasattr(token, "get_user_access_list"):
            return None
        raw = token.get_user_access_list()
        records = json.loads(raw) if raw else []
        if not isinstance(records, list):
            return None
        for record in records:
            if not isinstance(record, dict):
                continue
            if str(record.get("did") or "") == str(user_did):
                return record
    except Exception:
        return None
    return None


def normalize_user_access_selection(selected):
    if isinstance(selected, (list, tuple)) and selected:
        selected = selected[-1]
    selected = str(selected or "").strip()
    if " | " in selected:
        selected = selected.rsplit(" | ", 1)[-1].strip()
    return selected


def _token_bool_method(token, method_name, default=False):
    try:
        if token is not None and hasattr(token, method_name):
            return bool(getattr(token, method_name)())
    except Exception:
        pass
    return bool(default)


def _admin_default_bool(key, default=False):
    try:
        import enhanced.all_parameters as ads
        return bool(ads.get_admin_default(key))
    except Exception:
        return bool(default)


def user_can_generate(user_did):
    if is_local_mode():
        return True

    try:
        token = getattr(shared, "token", None)
        if token is None or not user_did:
            return False
        if token.is_guest(user_did):
            return _token_bool_method(
                token,
                "get_guest_can_generate",
                _admin_default_bool("guest_can_generate", False),
            )
        if token.is_admin(user_did):
            return True
        if hasattr(token, "can_user_generate"):
            return bool(token.can_user_generate(user_did))
        record = get_user_access_record(user_did)
        if record is not None:
            return str(record.get("status") or "") == "allowed" and bool(record.get("can_generate", False))
        return not token.is_guest(user_did)
    except Exception:
        return False


def user_has_full_local_access(user_did):
    return user_can_generate(user_did)


def user_can_download_models(user_did):
    if is_local_mode():
        return True

    try:
        token = getattr(shared, "token", None)
        if token is None or not user_did:
            return False
        if token.is_guest(user_did):
            return _token_bool_method(
                token,
                "get_guest_can_download_models",
                _admin_default_bool("guest_can_download_models", False),
            )
        if token.is_admin(user_did):
            return True
        if hasattr(token, "can_user_download_models"):
            return bool(token.can_user_download_models(user_did))
        record = get_user_access_record(user_did)
        if record is not None:
            return str(record.get("status") or "") == "allowed" and bool(record.get("can_download_models", False))
        return user_has_full_local_access(user_did)
    except Exception:
        return False


def state_has_full_local_access(state):
    try:
        user = state.get("user", None) if isinstance(state, dict) else None
        user_did = user.get_did() if user is not None and hasattr(user, "get_did") else None
    except Exception:
        user_did = None
    return user_has_full_local_access(user_did)


def state_can_generate(state):
    try:
        user = state.get("user", None) if isinstance(state, dict) else None
        user_did = user.get_did() if user is not None and hasattr(user, "get_did") else None
    except Exception:
        user_did = None
    return user_can_generate(user_did)


def state_can_download_models(state):
    try:
        user = state.get("user", None) if isinstance(state, dict) else None
        user_did = user.get_did() if user is not None and hasattr(user, "get_did") else None
    except Exception:
        user_did = None
    return user_can_download_models(user_did)
