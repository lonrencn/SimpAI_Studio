from enhanced.vlm import vlm


def default_interrogator(img_rgb, *args, **kwargs):
    return vlm.interrogate(img_rgb, *args, **kwargs)


def free_model():
    vlm.free_model()
