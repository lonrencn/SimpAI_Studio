import re

import nodes
from comfy_api.latest import io


_TIMED_PROMPT_RE = re.compile(
    r"(?:^|\n)\s*[\[【(（]\s*"
    r"(\d+(?:\.\d+)?)\s*(?:s|秒)?\s*(?:~|-|–|—|～|至|到)\s*"
    r"(\d+(?:\.\d+)?)\s*(?:s|秒)?\s*"
    r"[\]】)）]\s*"
)

_STAGE_PROMPT_RE = re.compile(
    r"[\[【(（]\s*stage\s*(\d+)\s*[\]】)）]\s*",
    re.IGNORECASE,
)


def _parse_stage_prompt(prompt):
    matches = list(_STAGE_PROMPT_RE.finditer(prompt))
    stages = {}
    for i, match in enumerate(matches):
        stage_number = int(match.group(1))
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(prompt)
        body = prompt[body_start:body_end].strip()
        if body:
            stages[stage_number] = body
    return stages


def _stage_number_from_frame(start_frame, length):
    start_frame = max(0, int(start_frame))
    length = max(1, int(length))
    if start_frame <= 0:
        return 1
    return ((start_frame - 1) // length) + 1


def _parse_timed_prompt(prompt):
    matches = list(_TIMED_PROMPT_RE.finditer(prompt))
    ranges = []
    for i, match in enumerate(matches):
        start = float(match.group(1))
        end = float(match.group(2))
        if end < start:
            start, end = end, start
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(prompt)
        body = prompt[body_start:body_end].strip()
        if body:
            ranges.append((start, end, body))
    return ranges


def _select_timed_prompt(prompt, start_frame, length, fps):
    prompt = (prompt or "").strip()
    stages = _parse_stage_prompt(prompt)
    if stages:
        stage_number = _stage_number_from_frame(start_frame, length)
        if stage_number not in stages:
            available = ", ".join(f"Stage{n}" for n in sorted(stages))
            raise ValueError(f"Missing [Stage{stage_number}] prompt section. Available sections: {available}")
        return stages[stage_number]

    ranges = _parse_timed_prompt(prompt)
    if not ranges:
        return prompt

    fps = max(0.001, float(fps))
    start_sec = max(0.0, int(start_frame) / fps)
    end_sec = start_sec + max(1, int(length)) / fps
    mid_sec = (start_sec + end_sec) * 0.5

    def score(indexed_item):
        _index, start, end, _body = indexed_item
        overlap = max(0.0, min(end_sec, end) - max(start_sec, start))
        contains_mid = 1 if start <= mid_sec < end else 0
        center_distance = abs(((start + end) * 0.5) - mid_sec)
        return (overlap, contains_mid, -center_distance)

    indexed_ranges = [(index, *item) for index, item in enumerate(ranges)]
    _index, _start, _end, body = max(indexed_ranges, key=score)
    return body


class SimpAISelectTimedPrompt(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SimpAISelectTimedPrompt",
            display_name="SimpAI Select Timed Prompt",
            category="conditioning/text",
            description="Select a matching prompt section from text like [0~5s]... for long-video segment generation.",
            inputs=[
                io.String.Input("prompt", multiline=True),
                io.Int.Input("start_frame", default=0, min=0, max=nodes.MAX_RESOLUTION, step=1),
                io.Int.Input("length", default=81, min=1, max=nodes.MAX_RESOLUTION, step=1),
                io.Float.Input("fps", default=16.0, min=0.001, max=240.0, step=0.001),
            ],
            outputs=[
                io.String.Output(display_name="prompt"),
            ],
        )

    @classmethod
    def execute(cls, prompt, start_frame, length, fps) -> io.NodeOutput:
        return io.NodeOutput(_select_timed_prompt(prompt, start_frame, length, fps))


NODE_CLASS_MAPPINGS = {
    "SimpAISelectTimedPrompt": SimpAISelectTimedPrompt,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpAISelectTimedPrompt": "SimpAI Select Timed Prompt",
}
