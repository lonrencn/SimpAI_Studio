class SimpAIOptionalTrimAudioDuration:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "start_index": ("FLOAT", {"default": 0.0, "min": -999999999.0, "max": 999999999.0, "step": 0.01}),
                "duration": ("FLOAT", {"default": 60.0, "min": 0.0, "max": 999999999.0, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("AUDIO",)
    FUNCTION = "trim_audio"
    CATEGORY = "SimpAI/audio"

    def trim_audio(self, audio, start_index=0.0, duration=60.0):
        if audio is None:
            return (None,)
        try:
            waveform = audio["waveform"]
            sample_rate = audio["sample_rate"]
        except Exception as err:
            print(f"[SimpAIOptionalTrimAudioDuration] Source audio unavailable; saving video without source audio. {type(err).__name__}: {err}")
            return (None,)

        audio_length = waveform.shape[-1]
        if audio_length == 0:
            return (audio,)

        start_index = float(start_index or 0.0)
        duration = float(duration or 0.0)
        sample_rate = int(sample_rate or 44100)

        if start_index < 0:
            start_frame = audio_length + int(round(start_index * sample_rate))
        else:
            start_frame = int(round(start_index * sample_rate))
        start_frame = max(0, min(start_frame, audio_length))

        end_frame = start_frame + int(round(duration * sample_rate))
        end_frame = max(0, min(end_frame, audio_length))

        if start_frame >= end_frame:
            print("[SimpAIOptionalTrimAudioDuration] Source audio trim range is empty; saving video without source audio.")
            return (None,)

        return ({"waveform": waveform[..., start_frame:end_frame], "sample_rate": sample_rate},)


NODE_CLASS_MAPPINGS = {
    "SimpAIOptionalTrimAudioDuration": SimpAIOptionalTrimAudioDuration,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpAIOptionalTrimAudioDuration": "SimpAI Optional Trim Audio Duration",
}
