from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path


def _default_user_base_dir() -> str:
    try:
        import args_manager

        path = str(getattr(args_manager.args, "userhome_path", "") or "").strip()
        if path:
            return os.path.abspath(path)
    except Exception:
        pass
    env_path = str(os.environ.get("simpleai_userhome") or "").strip()
    if env_path:
        return os.path.abspath(env_path)
    return str(Path(__file__).resolve().parents[3] / "users")


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def enable_forge_neo_read_only_user_config() -> None:
    try:
        import args_manager

        args = getattr(args_manager, "args", None)
        if args is not None:
            args.forge_neo_read_only_user_config = True
    except Exception:
        pass


class _ForgeNeoUserContext:
    def __init__(self, did: str, nickname: str, sys_did: str) -> None:
        self.did = did
        self.nickname = nickname
        self.sys_did = sys_did

    def get_did(self) -> str:
        return self.did

    def get_nickname(self) -> str:
        return self.nickname

    def get_sys_did(self) -> str:
        return self.sys_did


class _ForgeNeoSysInfo:
    def to_json(self) -> str:
        return json.dumps({"location": "CN", "mode": "forge_neo_local"}, ensure_ascii=False)


class _ForgeNeoTokenStub:
    def __init__(self) -> None:
        self.base_dir = _default_user_base_dir()
        self._guest_did = "forge_neo_guest"
        self._workspace_did = "forge_neo_local"
        self._sys_did = "forge_neo_sys"
        self.skip_default_outputs_init = True
        self.read_only_user_config = True
        self._local_vars: dict[tuple[str, str, str], str] = {}
        self._local_admin_vars: dict[str, str] = {}
        self._sessions: dict[str, str] = {}

    def set_user_base_dir(self, path: str) -> None:
        self.base_dir = os.path.abspath(path) if path else _default_user_base_dir()

    def get_default_workspace_did(self) -> str:
        return self._workspace_did

    def get_local_did(self) -> str:
        return self._workspace_did

    def get_guest_did(self) -> str:
        return self._guest_did

    def get_admin_did(self) -> str:
        return ""

    def get_sys_did(self) -> str:
        return self._sys_did

    def get_node_mode(self) -> str:
        return "local"

    def get_path_in_user_dir(self, user_did: str, catalog: str) -> str:
        catalog_name = str(catalog or "")
        if catalog_name == "outputs":
            return str(Path(self.base_dir) / "ForgeNeo")
        return str(Path(self.base_dir) / str(user_did or self.get_guest_did()) / catalog_name)

    def _session_token(self, did: str, ua_hash: str) -> str:
        digest = hashlib.sha256(f"{did}:{ua_hash or ''}".encode("utf-8")).hexdigest()[:24]
        token = f"forge_neo_{digest}"
        self._sessions[token] = did
        return token

    def get_guest_sstoken(self, ua_hash: str) -> str:
        return self._session_token(self._guest_did, ua_hash)

    def get_user_sstoken(self, user_did: str, ua_hash: str) -> str:
        return self._session_token(user_did or self._guest_did, ua_hash)

    def check_sstoken_and_get_did(self, session: str, ua_hash: str) -> str:
        if session in self._sessions:
            return self._sessions[session]
        if str(session or "").startswith("forge_neo_"):
            return self._guest_did
        return "Unknown"

    def get_guest_user_context(self) -> _ForgeNeoUserContext:
        return self.get_user_context(self._guest_did)

    def get_user_context(self, user_did: str) -> _ForgeNeoUserContext:
        did = user_did or self._guest_did
        nickname = "guest_forge_neo" if self.is_guest(did) else did
        return _ForgeNeoUserContext(did, nickname, self._sys_did)

    def get_user_context_with_phrase(self, nick: str, tele: str, user_did: str, phrase: str) -> _ForgeNeoUserContext:
        return self.get_guest_user_context()

    def set_phrase_and_get_context(self, nick: str, tele: str, phrase: str) -> _ForgeNeoUserContext:
        return self.get_guest_user_context()

    def unbind_and_return_guest(self, user_did: str, phrase: str) -> _ForgeNeoUserContext:
        return self.get_guest_user_context()

    def is_guest(self, user_did: str) -> bool:
        return not user_did or str(user_did) == self._guest_did

    def is_admin(self, user_did: str) -> bool:
        return False

    def can_user_generate(self, user_did: str) -> bool:
        return True

    def can_user_download_models(self, user_did: str) -> bool:
        return True

    def get_guest_can_generate(self) -> bool:
        return True

    def get_guest_can_download_models(self) -> bool:
        return True

    def get_user_access_list(self) -> str:
        return "[]"

    def set_user_can_generate(self, user_did: str, value: bool) -> str:
        return "OK"

    def set_user_can_download_models(self, user_did: str, value: bool) -> str:
        return "OK"

    def set_guest_can_generate(self, value: bool) -> str:
        return "OK"

    def set_guest_can_download_models(self, value: bool) -> str:
        return "OK"

    def get_local_vars(self, key: str, default: str = "None", user_session: str = "", ua_hash: str = "") -> str:
        return self._local_vars.get((str(user_session or ""), str(ua_hash or ""), str(key)), default)

    def set_local_vars(self, key: str, value: str, user_session: str = "", ua_hash: str = "") -> str:
        self._local_vars[(str(user_session or ""), str(ua_hash or ""), str(key))] = str(value)
        return "OK"

    def set_local_vars_for_guest(self, key: str, value: str, user_session: str = "", ua_hash: str = "") -> str:
        return self.set_local_vars(key, value, user_session, ua_hash)

    def get_local_admin_vars(self, key: str) -> str:
        return self._local_admin_vars.get(str(key), "None")

    def set_local_admin_vars(self, key: str, value: str, user_session: str = "", ua_hash: str = "") -> str:
        self._local_admin_vars[str(key)] = str(value)
        return "OK"

    def log_register(self, session: str) -> None:
        return None

    def check_local_user_token(self, nick: str, tele: str) -> str:
        return "isolated"

    def check_user_verify_code(self, nick: str, tele: str, vcode: str) -> str:
        return "error:0"

    def get_register_cert(self, user_did: str) -> str:
        return ""

    def get_sysinfo(self) -> _ForgeNeoSysInfo:
        return _ForgeNeoSysInfo()

    def get_p2p_address(self) -> str:
        return ""

    def get_p2p_upstream_did(self) -> str:
        return ""

    def p2p_start(self) -> str:
        return ""

    def p2p_stop(self) -> str:
        return ""


def ensure_shared_token(*, test_stub: bool = False) -> None:
    import shared

    if getattr(shared, "token", None) is not None:
        return

    if (
        test_stub
        or _env_flag("FORGE_NEO_TEST_TOKEN_STUB")
        or _env_flag("FORGE_NEO_TOKEN_STUB")
        or _env_flag("FORGE_NEO_DISABLE_SIMPLEAI_BASE")
        or not _env_flag("FORGE_NEO_USE_SIMPLEAI_BASE")
    ):
        shared.token = _ForgeNeoTokenStub()
        return

    from simpleai_base import simpleai_base

    shared.token = simpleai_base.init_local()


def ensure_config(*, test_stub: bool = False):
    enable_forge_neo_read_only_user_config()
    ensure_shared_token(test_stub=test_stub)
    return importlib.import_module("modules.config")
