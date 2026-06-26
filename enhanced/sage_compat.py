import os
import logging

_logger = logging.getLogger("sage_compat")

_SAGE_MODE = os.environ.get("SIMPAI_SAGE_MODE", "").lower()

_known_cuda_funcs = (
    "sageattn_qk_int8_pv_fp16_cuda",
    "sageattn_qk_int8_pv_fp16_triton",
    "sageattn_qk_int8_pv_fp8_cuda",
)


def _sdp_fallback(q, k, v, is_causal=False, attn_mask=None,
                  pv_accum_dtype="fp32", tensor_layout="NHD",
                  sm_scale=None, **kwargs):
    import torch.nn.functional as F
    if tensor_layout == "NHD":
        q = q.transpose(1, 2)
        k = k.transpose(1, 2)
        v = v.transpose(1, 2)
    out = F.scaled_dot_product_attention(q, k, v, is_causal=is_causal)
    if tensor_layout == "NHD":
        out = out.transpose(1, 2)
    return out


def _has_real_cuda_kernels(mod):
    import inspect
    for name in _known_cuda_funcs:
        fn = getattr(mod, name, None)
        if fn is None:
            return False
        try:
            src_file = inspect.getfile(fn)
        except (TypeError, OSError):
            continue
        if "sage_compat" in src_file or "sageattention/__init__" in src_file:
            return False
    return True


def _install_dynamic_getattr(mod):
    if getattr(mod, "_sage_compat_dynamic", False):
        return

    def _module_getattr(name):
        if name.startswith("sageattn"):
            _logger.warning("sage_compat: dynamic SDP fallback for '%s'", name)
            return _sdp_fallback
        raise AttributeError(f"module 'sageattention' has no attribute '{name}'")

    mod.__getattr__ = _module_getattr
    mod._sage_compat_dynamic = True


def apply():
    try:
        import sageattention
    except ImportError:
        return

    if _has_real_cuda_kernels(sageattention):
        _logger.info("sage_compat: real CUDA kernels detected, skipping")
        return

    if _SAGE_MODE == "sdp":
        _logger.info("sage_compat: SIMPAI_SAGE_MODE=sdp, forcing all SDP")
        if hasattr(sageattention, "sageattn"):
            sageattention.sageattn = _sdp_fallback
        if hasattr(sageattention, "sageattn_varlen"):
            sageattention.sageattn_varlen = _sdp_fallback

    patched = []
    for name in _known_cuda_funcs:
        if not hasattr(sageattention, name):
            setattr(sageattention, name, _sdp_fallback)
            patched.append(name)

    _install_dynamic_getattr(sageattention)

    if patched:
        _logger.info("sage_compat: SDP fallbacks for %s", patched)
