(function () {
    'use strict';

    function isImageFile(file) {
        if (!file) return false;
        if (file.type && file.type.startsWith('image/')) return true;
        return /\.(png|jpe?g|webp|gif|bmp|avif)$/i.test(file.name || '');
    }

    function isVideoFile(file) {
        if (!file) return false;
        if (file.type && file.type.startsWith('video/')) return true;
        return /\.(mp4|webm|mov|m4v|avi|mkv)$/i.test(file.name || '');
    }

    function isAudioFile(file) {
        if (!file) return false;
        if (file.type && file.type.startsWith('audio/')) return true;
        return /\.(mp3|wav|ogg|flac|m4a|aac|opus)$/i.test(file.name || '');
    }

    function isMediaFile(file) {
        return isImageFile(file) || isVideoFile(file) || isAudioFile(file);
    }

    function readFileAsDataUrl(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onerror = () => reject(new Error('read_failed'));
            reader.onload = () => resolve(String(reader.result || ''));
            reader.readAsDataURL(file);
        });
    }

    function readFileAsText(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onerror = () => reject(new Error('read_failed'));
            reader.onload = () => resolve(String(reader.result || ''));
            reader.readAsText(file, 'utf-8');
        });
    }

    function getImageDimensions(src) {
        return new Promise((resolve) => {
            if (!src) {
                resolve({ width: null, height: null });
                return;
            }
            const image = new Image();
            image.onload = () => resolve({ width: image.naturalWidth || image.width || null, height: image.naturalHeight || image.height || null });
            image.onerror = () => resolve({ width: null, height: null });
            image.src = src;
        });
    }

    function getMediaMetadata(src, type) {
        return new Promise((resolve) => {
            if (!src) {
                resolve({ width: null, height: null, duration: null, fps: null, frame_count: null });
                return;
            }
            const media = document.createElement(type === 'video' ? 'video' : 'audio');
            media.preload = 'metadata';
            media.onloadedmetadata = () => {
                resolve({
                    width: media.videoWidth || null,
                    height: media.videoHeight || null,
                    duration: Number.isFinite(media.duration) ? Math.round(media.duration * 100) / 100 : null,
                    fps: null,
                    frame_count: null
                });
            };
            media.onerror = () => resolve({ width: null, height: null, duration: null, fps: null, frame_count: null });
            media.src = src;
        });
    }

    function createThumbnailDataUrl(src, maxSize) {
        return new Promise((resolve) => {
            if (!src) {
                resolve('');
                return;
            }
            const image = new Image();
            image.onload = () => {
                const width = image.naturalWidth || image.width || 1;
                const height = image.naturalHeight || image.height || 1;
                const scale = Math.min(1, Number(maxSize || 1024) / Math.max(width, height));
                if (scale >= 1 && src.length < 700000) {
                    resolve(src);
                    return;
                }
                const canvas = document.createElement('canvas');
                canvas.width = Math.max(1, Math.round(width * scale));
                canvas.height = Math.max(1, Math.round(height * scale));
                const ctx = canvas.getContext('2d');
                ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
                resolve(canvas.toDataURL('image/jpeg', 0.92));
            };
            image.onerror = () => resolve(src);
            image.src = src;
        });
    }

    function roundMediaTime(value) {
        const num = Number(value || 0);
        if (!Number.isFinite(num)) return 0;
        return Math.round(num * 1000) / 1000;
    }

    function createVideoStoryboardDataUrls(src, duration, count) {
        return new Promise((resolve) => {
            const video = document.createElement('video');
            const frames = [];
            const total = Math.max(0, Number(duration || 0) || 0);
            const frameCount = Math.max(4, Math.min(12, Number(count || 8) || 8));
            let settled = false;
            const finish = () => {
                if (settled) return;
                settled = true;
                video.removeAttribute('src');
                video.load();
                resolve(frames);
            };
            const seekTo = (time) => new Promise((res) => {
                const done = () => {
                    video.removeEventListener('seeked', done);
                    res();
                };
                video.addEventListener('seeked', done, { once: true });
                try {
                    video.currentTime = Math.max(0, time);
                } catch (err) {
                    video.removeEventListener('seeked', done);
                    res();
                }
                setTimeout(done, 1200);
            });
            video.muted = true;
            video.preload = 'auto';
            video.playsInline = true;
            video.onerror = finish;
            video.onloadedmetadata = async () => {
                const mediaDuration = total || (Number.isFinite(video.duration) ? video.duration : 0);
                const width = video.videoWidth || 160;
                const height = video.videoHeight || 90;
                const scale = Math.min(1, 180 / Math.max(width, height));
                const canvas = document.createElement('canvas');
                canvas.width = Math.max(1, Math.round(width * scale));
                canvas.height = Math.max(1, Math.round(height * scale));
                const ctx = canvas.getContext('2d');
                if (!ctx || !mediaDuration) {
                    finish();
                    return;
                }
                for (let i = 0; i < frameCount; i += 1) {
                    const time = mediaDuration * ((i + 0.5) / frameCount);
                    await seekTo(time);
                    try {
                        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                        frames.push({
                            time: roundMediaTime(time),
                            thumb: canvas.toDataURL('image/jpeg', 0.72)
                        });
                    } catch (err) {
                        // Unsupported codecs can still leave the media node usable.
                    }
                }
                finish();
            };
            setTimeout(finish, 12000);
            video.src = src;
        });
    }

    async function createAudioWaveformPeaks(file, bucketCount) {
        if (!file || typeof file.arrayBuffer !== 'function') return [];
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return [];
        let audioCtx = null;
        try {
            const arrayBuffer = await file.arrayBuffer();
            audioCtx = new AudioCtx();
            const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer.slice(0));
            const channels = Math.max(1, audioBuffer.numberOfChannels || 1);
            const samples = audioBuffer.length || 0;
            const buckets = Math.max(48, Math.min(160, Number(bucketCount || 96) || 96));
            const step = Math.max(1, Math.floor(samples / buckets));
            const peaks = [];
            for (let i = 0; i < buckets; i += 1) {
                const start = i * step;
                const end = Math.min(samples, start + step);
                let max = 0;
                for (let ch = 0; ch < channels; ch += 1) {
                    const data = audioBuffer.getChannelData(ch);
                    for (let j = start; j < end; j += 8) {
                        max = Math.max(max, Math.abs(data[j] || 0));
                    }
                }
                peaks.push(Math.round(Math.min(1, max) * 1000) / 1000);
            }
            return peaks;
        } catch (err) {
            console.warn('[SimpAI Canvas] waveform generation skipped:', err);
            return [];
        } finally {
            if (audioCtx && typeof audioCtx.close === 'function') {
                audioCtx.close().catch(() => {});
            }
        }
    }

    window.SimpAICanvasWorkbenchMediaHelpers = {
        isImageFile,
        isVideoFile,
        isAudioFile,
        isMediaFile,
        readFileAsDataUrl,
        readFileAsText,
        getImageDimensions,
        getMediaMetadata,
        createThumbnailDataUrl,
        createVideoStoryboardDataUrls,
        createAudioWaveformPeaks
    };
})();
