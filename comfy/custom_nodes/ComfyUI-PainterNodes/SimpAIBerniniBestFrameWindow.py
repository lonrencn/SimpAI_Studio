import math

from comfy_api.latest import io


def _align_4n1(value):
    value = max(1, int(round(value)))
    return value + ((1 - value) % 4)


def _best_segment_frames(total_frames, target_frames, force_size, min_frames, max_frames):
    total_frames = max(1, int(total_frames))
    min_frames = _align_4n1(min_frames)
    max_frames = max(min_frames, _align_4n1(max_frames))

    if force_size > 1:
        return max(1, min(_align_4n1(force_size), max_frames))

    if total_frames <= min_frames:
        return _align_4n1(total_frames)

    target_frames = max(min_frames, min(_align_4n1(target_frames), max_frames))
    n_min = math.ceil((min_frames - 1) / 4)
    n_max = math.floor((max_frames - 1) / 4)

    best_frames = target_frames
    best_candidate = None
    for n in range(n_min, n_max + 1):
        frames = 4 * n + 1
        new_frames_per_loop = max(1, frames - 1)
        segments = max(1, math.ceil((total_frames - 1) / new_frames_per_loop))
        generated_frames = 1 + segments * new_frames_per_loop
        extra_frames = generated_frames - total_frames
        candidate = (
            extra_frames,
            abs(frames - target_frames),
            frames > target_frames,
            segments,
        )
        if best_candidate is None or candidate < best_candidate:
            best_candidate = candidate
            best_frames = frames

    return best_frames


class SimpAIBerniniBestFrameWindow(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SimpAIBerniniBestFrameWindow",
            display_name="SimpAI Bernini Best Frame Window",
            category="image/video",
            description="Choose a 4n+1 segment frame count near the user target and reduce short tail segments.",
            inputs=[
                io.Int.Input("total_frames", default=81, min=1, max=100000, step=1),
                io.Int.Input("target_frames", default=81, min=1, max=100000, step=1),
                io.Int.Input("force_size", default=1, min=1, max=1025, step=4),
                io.Int.Input("min_frames", default=45, min=1, max=100000, step=4),
                io.Int.Input("max_frames", default=185, min=1, max=100000, step=4),
            ],
            outputs=[
                io.Int.Output(display_name="segment_frames"),
            ],
        )

    @classmethod
    def execute(cls, total_frames, target_frames, force_size, min_frames, max_frames) -> io.NodeOutput:
        return io.NodeOutput(
            _best_segment_frames(total_frames, target_frames, force_size, min_frames, max_frames)
        )


NODE_CLASS_MAPPINGS = {
    "SimpAIBerniniBestFrameWindow": SimpAIBerniniBestFrameWindow,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpAIBerniniBestFrameWindow": "SimpAI Bernini Best Frame Window",
}
