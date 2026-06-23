import torch
from comfy_api.latest import io


class SimpAISelectVideoKeyframes(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SimpAISelectVideoKeyframes",
            display_name="SimpAI Select Video Keyframes",
            category="image/video",
            description="Select evenly spaced keyframes from an image batch for long-video reference conditioning.",
            inputs=[
                io.Image.Input("images"),
                io.Int.Input("count", default=3, min=1, max=16, step=1),
                io.Int.Input("exclude_tail_frames", default=0, min=0, max=4096, step=1),
            ],
            outputs=[
                io.Image.Output(display_name="keyframes"),
            ],
        )

    @classmethod
    def execute(cls, images, count, exclude_tail_frames) -> io.NodeOutput:
        frame_count = int(images.shape[0])
        if frame_count <= 0:
            return io.NodeOutput(images)

        exclude_tail_frames = max(0, int(exclude_tail_frames))
        effective_frame_count = max(1, frame_count - min(exclude_tail_frames, max(0, frame_count - 1)))
        count = max(1, min(int(count), effective_frame_count))
        if count == 1:
            indices = [0]
        else:
            raw_indices = [int((i * frame_count) // count) for i in range(count)]
            indices = []
            for index in raw_indices:
                index = int(max(0, min(effective_frame_count - 1, index)))
                if index not in indices:
                    indices.append(index)

        index_tensor = torch.tensor(indices, dtype=torch.long, device=images.device)
        return io.NodeOutput(images.index_select(0, index_tensor))


NODE_CLASS_MAPPINGS = {
    "SimpAISelectVideoKeyframes": SimpAISelectVideoKeyframes,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpAISelectVideoKeyframes": "SimpAI Select Video Keyframes",
}
