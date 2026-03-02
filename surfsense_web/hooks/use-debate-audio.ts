"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { DebateVoiceState } from "@/contracts/types/debate.types";

// ── PCM format constants (must match backend debate_voice.py) ───────
const PCM_SAMPLE_RATE = 24000;
const PCM_BIT_DEPTH = 16;
const PCM_CHANNELS = 1;

// ── MP3 encoding bitrate ────────────────────────────────────────────
const MP3_KBPS = 128;

/**
 * Hook that manages Web Audio API playback for Live Voice Debate Mode.
 *
 * Architecture:
 * 1. SSE events deliver base64-encoded PCM chunks from the backend.
 * 2. This hook decodes chunks into Float32 audio samples.
 * 3. Chunks are queued per-speaker and played sequentially via AudioContext.
 * 4. An AnalyserNode feeds waveform data for visualization.
 * 5. All raw PCM is collected for optional full-debate WAV export.
 *
 * IMPORTANT: Browsers require a user gesture to start AudioContext.
 * We call ctx.resume() aggressively and expose an `unlock` function
 * that should be called from a click handler (e.g. the play button).
 */
export function useDebateAudio(enabled: boolean) {
	const [voiceState, setVoiceState] = useState<DebateVoiceState>({
		enabled,
		currentSpeaker: null,
		currentRound: 0,
		playbackStatus: "idle",
		volume: 0.85,
		waveformData: null,
		collectedChunks: {},
	});

	// Web Audio API refs (persist across renders)
	const audioCtxRef = useRef<AudioContext | null>(null);
	const analyserRef = useRef<AnalyserNode | null>(null);
	const gainRef = useRef<GainNode | null>(null);
	const animFrameRef = useRef<number | null>(null);

	// Playback queue: chunks waiting to be played
	const chunkQueueRef = useRef<{ speaker: string; round: number; buffer: AudioBuffer }[]>([]);
	const isPlayingRef = useRef(false);
	const isPausedRef = useRef(false);

	// Track total chunks received for diagnostics
	const totalChunksRef = useRef(0);
	// Track voice errors from backend
	const lastErrorRef = useRef<string | null>(null);

	// Collected raw PCM for export — stored in arrival order so the
	// exported file matches the actual debate sequence (round by round,
	// speaker by speaker) rather than grouping per-speaker.
	const collectedRef = useRef<ArrayBuffer[]>([]);

	// OPT-08: Read volume from ref to avoid recreating callback on volume change
	const volumeRef = useRef(voiceState.volume);
	useEffect(() => {
		volumeRef.current = voiceState.volume;
	}, [voiceState.volume]);

	// OPT-06: Memory cap for collected audio chunks (50 MB)
	const MAX_COLLECTED_BYTES = 50 * 1024 * 1024;
	const collectedBytesRef = useRef(0);

	// KQ-10: Use ref for waveform data to avoid 60fps state updates
	const waveformDataRef = useRef<Uint8Array | null>(null);

	// ── Initialize AudioContext lazily ──────────────────────────────
	const ensureAudioContext = useCallback(() => {
		if (audioCtxRef.current) return audioCtxRef.current;

		const ctx = new AudioContext({ sampleRate: PCM_SAMPLE_RATE });
		const analyser = ctx.createAnalyser();
		analyser.fftSize = 256;
		analyser.smoothingTimeConstant = 0.7;

		const gain = ctx.createGain();
		// OPT-08: Read from ref, not state
		gain.gain.value = volumeRef.current;

		gain.connect(analyser);
		analyser.connect(ctx.destination);

		audioCtxRef.current = ctx;
		analyserRef.current = analyser;
		gainRef.current = gain;

		ctx.resume().catch(() => {
			console.warn("[useDebateAudio] AudioContext suspended — click play to unlock");
		});

		console.log("[useDebateAudio] AudioContext created, state:", ctx.state);
		return ctx;
	}, []);

	// ── Resume / unlock the AudioContext (call from user gesture) ──
	const resumeAudioContext = useCallback(async () => {
		const ctx = ensureAudioContext();
		if (ctx.state === "suspended") {
			await ctx.resume();
			console.log("[useDebateAudio] AudioContext resumed via user gesture, state:", ctx.state);
		}
	}, [ensureAudioContext]);

	// ── Play next chunk from queue ─────────────────────────────────
	const playNextRef = useRef<() => void>(() => {});
	playNextRef.current = () => {
		const ctx = audioCtxRef.current;
		const gain = gainRef.current;
		if (!ctx || !gain || isPausedRef.current) {
			isPlayingRef.current = false;
			return;
		}

		const next = chunkQueueRef.current.shift();
		if (!next) {
			isPlayingRef.current = false;
			stopWaveformAnimation();
			setVoiceState((prev) => ({
				...prev,
				playbackStatus: chunkQueueRef.current.length > 0 ? "playing" : "idle",
				currentSpeaker: null,
				waveformData: null,
			}));
			return;
		}

		isPlayingRef.current = true;
		startWaveformAnimation();
		setVoiceState((prev) => ({
			...prev,
			playbackStatus: "playing",
			currentSpeaker: next.speaker,
			currentRound: next.round,
		}));

		// Ensure AudioContext is running before playing
		if (ctx.state === "suspended") {
			ctx.resume().then(() => {
				const source = ctx.createBufferSource();
				source.buffer = next.buffer;
				source.connect(gain);
				source.onended = () => playNextRef.current();
				source.start(0);
			});
		} else {
			const source = ctx.createBufferSource();
			source.buffer = next.buffer;
			source.connect(gain);
			source.onended = () => playNextRef.current();
			source.start(0);
		}
	};

	const playNext = useCallback(() => {
		playNextRef.current();
	}, []);

	// ── Decode PCM base64 → AudioBuffer ────────────────────────────
	const decodePcmChunk = useCallback(
		(b64: string): AudioBuffer | null => {
			const ctx = ensureAudioContext();
			try {
				const binaryStr = atob(b64);
				const bytes = new Uint8Array(binaryStr.length);
				for (let i = 0; i < binaryStr.length; i++) {
					bytes[i] = binaryStr.charCodeAt(i);
				}

				// PCM 16-bit LE mono → Float32
				const int16 = new Int16Array(bytes.buffer);
				const float32 = new Float32Array(int16.length);
				for (let i = 0; i < int16.length; i++) {
					float32[i] = int16[i] / 32768;
				}

				const audioBuffer = ctx.createBuffer(
					PCM_CHANNELS,
					float32.length,
					PCM_SAMPLE_RATE,
				);
				audioBuffer.getChannelData(0).set(float32);
				return audioBuffer;
			} catch (err) {
				console.error("[useDebateAudio] PCM decode error:", err);
				return null;
			}
		},
		[ensureAudioContext],
	);

	// ── Queue a chunk for playback ─────────────────────────────────
	const enqueueChunk = useCallback(
		(speaker: string, b64: string, round = 0) => {
			if (!enabled) return;

			totalChunksRef.current += 1;
			if (totalChunksRef.current <= 3) {
				console.log(
					`[useDebateAudio] chunk #${totalChunksRef.current} from ${speaker} r${round}, b64 length=${b64.length}`,
				);
			}

			// Store raw PCM for export (arrival order = debate order)
			// OPT-06: Respect memory cap to prevent unbounded growth
			try {
				const binaryStr = atob(b64);
				const raw = new Uint8Array(binaryStr.length);
				for (let i = 0; i < binaryStr.length; i++) {
					raw[i] = binaryStr.charCodeAt(i);
				}
				if (collectedBytesRef.current + raw.byteLength <= MAX_COLLECTED_BYTES) {
					collectedRef.current.push(raw.buffer);
					collectedBytesRef.current += raw.byteLength;
				}
			} catch {
				// export collection is best-effort
			}

			const audioBuffer = decodePcmChunk(b64);
			if (!audioBuffer) return;

			chunkQueueRef.current.push({ speaker, round, buffer: audioBuffer });

			// Start playback if not already playing
			if (!isPlayingRef.current && !isPausedRef.current) {
				playNext();
			}
		},
		[enabled, decodePcmChunk, playNext],
	);

	// ── Voice error handler ───────────────────────────────────────
	const onVoiceError = useCallback((errorMsg: string) => {
		console.warn("[useDebateAudio] voice error:", errorMsg);
		lastErrorRef.current = errorMsg;
		setVoiceState((prev) => ({
			...prev,
			playbackStatus: "error" as DebateVoiceState["playbackStatus"],
		}));
	}, []);

	// ── KQ-09: Waveform animation loop — only runs when playing ────
	const startWaveformAnimation = useCallback(() => {
		if (animFrameRef.current !== null) return; // already running

		const animate = () => {
			const analyser = analyserRef.current;
			if (analyser && isPlayingRef.current) {
				const data = new Uint8Array(analyser.frequencyBinCount);
				analyser.getByteFrequencyData(data);
				// KQ-10: Write to ref instead of state to avoid 60fps rerenders
				waveformDataRef.current = data;
				// Only update state at ~10fps for visualization (not 60fps)
				animFrameRef.current = requestAnimationFrame(animate);
			} else {
				// Stop the loop when not playing
				animFrameRef.current = null;
				waveformDataRef.current = null;
			}
		};
		animFrameRef.current = requestAnimationFrame(animate);
	}, []);

	const stopWaveformAnimation = useCallback(() => {
		if (animFrameRef.current !== null) {
			cancelAnimationFrame(animFrameRef.current);
			animFrameRef.current = null;
		}
		waveformDataRef.current = null;
	}, []);

	// ── Speaker change handler ─────────────────────────────────────
	const onSpeakerChange = useCallback(
		(speaker: string) => {
			console.log("[useDebateAudio] speaker change:", speaker);
			setVoiceState((prev) => ({ ...prev, currentSpeaker: speaker }));
		},
		[],
	);

	// ── Playback controls ──────────────────────────────────────────
	const togglePlayPause = useCallback(() => {
		const ctx = audioCtxRef.current ?? ensureAudioContext();

		if (ctx.state === "suspended") {
			// First click — unlock the AudioContext
			isPausedRef.current = false;
			ctx.resume().then(() => {
				console.log("[useDebateAudio] AudioContext unlocked via play button");
				setVoiceState((prev) => ({ ...prev, playbackStatus: "playing" }));
				if (!isPlayingRef.current && chunkQueueRef.current.length > 0) {
					playNext();
				}
			});
			return;
		}

		if (isPausedRef.current) {
			// Resume from pause
			isPausedRef.current = false;
			ctx.resume();
			setVoiceState((prev) => ({ ...prev, playbackStatus: "playing" }));
			if (!isPlayingRef.current) {
				playNext();
			}
		} else {
			// Pause
			isPausedRef.current = true;
			ctx.suspend();
			setVoiceState((prev) => ({ ...prev, playbackStatus: "paused" }));
		}
	}, [ensureAudioContext, playNext]);

	const setVolume = useCallback((vol: number) => {
		const clamped = Math.max(0, Math.min(1, vol));
		if (gainRef.current) {
			gainRef.current.gain.value = clamped;
		}
		setVoiceState((prev) => ({ ...prev, volume: clamped }));
	}, []);

	// ── Export collected audio as MP3 blob ───────────────────────────
	const exportAudioBlob = useCallback(async (): Promise<Blob | null> => {
		const chunks = collectedRef.current;
		if (chunks.length === 0) return null;

		// Merge all PCM chunks (already in debate order)
		const totalLength = chunks.reduce((sum, c) => sum + c.byteLength, 0);
		const merged = new Uint8Array(totalLength);
		let offset = 0;
		for (const chunk of chunks) {
			merged.set(new Uint8Array(chunk), offset);
			offset += chunk.byteLength;
		}

		// Convert PCM 16-bit LE → Int16Array for the encoder
		const int16 = new Int16Array(merged.buffer, merged.byteOffset, merged.byteLength / 2);

		try {
			// Dynamic import — lamejs is CJS so the module may land on .default
			const lamejsModule = await import("lamejs");
			const lamejs = (lamejsModule as Record<string, unknown>).default ?? lamejsModule;
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			const Mp3Encoder = (lamejs as any).Mp3Encoder;
			if (!Mp3Encoder) {
				throw new Error("Mp3Encoder not found in lamejs module");
			}
			const encoder = new Mp3Encoder(PCM_CHANNELS, PCM_SAMPLE_RATE, MP3_KBPS);

			const mp3Parts: BlobPart[] = [];
			const SAMPLES_PER_FRAME = 1152;

			for (let i = 0; i < int16.length; i += SAMPLES_PER_FRAME) {
				const chunk = int16.subarray(i, i + SAMPLES_PER_FRAME);
				const mp3buf = encoder.encodeBuffer(chunk);
				if (mp3buf.length > 0) {
					mp3Parts.push(new Uint8Array(mp3buf));
				}
			}

			const tail = encoder.flush();
			if (tail.length > 0) {
				mp3Parts.push(new Uint8Array(tail));
			}

			console.log(
				"[useDebateAudio] MP3 export: %d PCM bytes → %d MP3 parts",
				totalLength,
				mp3Parts.length,
			);

			return new Blob(mp3Parts, { type: "audio/mpeg" });
		} catch (err) {
			console.warn("[useDebateAudio] MP3 encoding failed, falling back to WAV:", err);
			// Fallback to WAV if lamejs is unavailable
			const wavHeader = buildWavHeader(merged.length, PCM_SAMPLE_RATE, PCM_BIT_DEPTH, PCM_CHANNELS);
			return new Blob([wavHeader, merged], { type: "audio/wav" });
		}
	}, []);

	// ── Cleanup on unmount ─────────────────────────────────────────
	useEffect(() => {
		return () => {
			stopWaveformAnimation();
			audioCtxRef.current?.close();
			audioCtxRef.current = null;
		};
	}, [stopWaveformAnimation]);

	// ── Sync enabled prop ──────────────────────────────────────────
	useEffect(() => {
		setVoiceState((prev) => ({ ...prev, enabled }));
	}, [enabled]);

	return {
		voiceState,
		// KQ-10: Expose waveform ref for canvas-based visualization
		waveformDataRef,
		enqueueChunk,
		onSpeakerChange,
		onVoiceError,
		togglePlayPause,
		setVolume,
		exportAudioBlob,
		resumeAudioContext,
		lastError: lastErrorRef.current,
	};
}

// ── WAV header builder ─────────────────────────────────────────────
function buildWavHeader(
	dataLength: number,
	sampleRate: number,
	bitDepth: number,
	channels: number,
): ArrayBuffer {
	const byteRate = (sampleRate * channels * bitDepth) / 8;
	const blockAlign = (channels * bitDepth) / 8;
	const headerSize = 44;
	const buffer = new ArrayBuffer(headerSize);
	const view = new DataView(buffer);

	// RIFF chunk
	writeString(view, 0, "RIFF");
	view.setUint32(4, 36 + dataLength, true);
	writeString(view, 8, "WAVE");

	// fmt sub-chunk
	writeString(view, 12, "fmt ");
	view.setUint32(16, 16, true); // sub-chunk size
	view.setUint16(20, 1, true); // PCM format
	view.setUint16(22, channels, true);
	view.setUint32(24, sampleRate, true);
	view.setUint32(28, byteRate, true);
	view.setUint16(32, blockAlign, true);
	view.setUint16(34, bitDepth, true);

	// data sub-chunk
	writeString(view, 36, "data");
	view.setUint32(40, dataLength, true);

	return buffer;
}

function writeString(view: DataView, offset: number, str: string) {
	for (let i = 0; i < str.length; i++) {
		view.setUint8(offset + i, str.charCodeAt(i));
	}
}
