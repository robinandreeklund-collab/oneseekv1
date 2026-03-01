"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { DebateVoiceState } from "@/contracts/types/debate.types";

// ── PCM format constants (must match backend debate_voice.py) ───────
const PCM_SAMPLE_RATE = 24000;
const PCM_BIT_DEPTH = 16;
const PCM_CHANNELS = 1;

/**
 * Hook that manages Web Audio API playback for Live Voice Debate Mode.
 *
 * Architecture:
 * 1. SSE events deliver base64-encoded PCM chunks from the backend.
 * 2. This hook decodes chunks into Float32 audio samples.
 * 3. Chunks are queued per-speaker and played sequentially via AudioContext.
 * 4. An AnalyserNode feeds waveform data for visualization.
 * 5. All raw PCM is collected for optional full-debate MP3 export.
 */
export function useDebateAudio(enabled: boolean) {
	const [voiceState, setVoiceState] = useState<DebateVoiceState>({
		enabled,
		currentSpeaker: null,
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
	const chunkQueueRef = useRef<{ speaker: string; buffer: AudioBuffer }[]>([]);
	const isPlayingRef = useRef(false);
	const isPausedRef = useRef(false);

	// Collected raw PCM for export (speaker → ArrayBuffer[])
	const collectedRef = useRef<Record<string, ArrayBuffer[]>>({});

	// ── Initialize AudioContext lazily ──────────────────────────────
	const ensureAudioContext = useCallback(() => {
		if (audioCtxRef.current) return audioCtxRef.current;

		const ctx = new AudioContext({ sampleRate: PCM_SAMPLE_RATE });
		const analyser = ctx.createAnalyser();
		analyser.fftSize = 256;
		analyser.smoothingTimeConstant = 0.7;

		const gain = ctx.createGain();
		gain.gain.value = voiceState.volume;

		gain.connect(analyser);
		analyser.connect(ctx.destination);

		audioCtxRef.current = ctx;
		analyserRef.current = analyser;
		gainRef.current = gain;

		return ctx;
	}, [voiceState.volume]);

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
		(speaker: string, b64: string) => {
			if (!enabled) return;

			// Store raw PCM for export
			const binaryStr = atob(b64);
			const raw = new Uint8Array(binaryStr.length);
			for (let i = 0; i < binaryStr.length; i++) {
				raw[i] = binaryStr.charCodeAt(i);
			}
			if (!collectedRef.current[speaker]) {
				collectedRef.current[speaker] = [];
			}
			collectedRef.current[speaker].push(raw.buffer);

			const audioBuffer = decodePcmChunk(b64);
			if (!audioBuffer) return;

			chunkQueueRef.current.push({ speaker, buffer: audioBuffer });

			// Start playback if not already playing
			if (!isPlayingRef.current && !isPausedRef.current) {
				playNext();
			}
		},
		[enabled, decodePcmChunk],
	);

	// ── Play next chunk from queue ─────────────────────────────────
	const playNext = useCallback(() => {
		const ctx = audioCtxRef.current;
		const gain = gainRef.current;
		if (!ctx || !gain || isPausedRef.current) {
			isPlayingRef.current = false;
			return;
		}

		const next = chunkQueueRef.current.shift();
		if (!next) {
			isPlayingRef.current = false;
			setVoiceState((prev) => ({
				...prev,
				playbackStatus: "idle",
				currentSpeaker: null,
			}));
			return;
		}

		isPlayingRef.current = true;
		setVoiceState((prev) => ({
			...prev,
			playbackStatus: "playing",
			currentSpeaker: next.speaker,
		}));

		const source = ctx.createBufferSource();
		source.buffer = next.buffer;
		source.connect(gain);
		source.onended = () => {
			playNext();
		};
		source.start(0);
	}, []);

	// ── Waveform animation loop ────────────────────────────────────
	useEffect(() => {
		if (!enabled) return;

		const animate = () => {
			const analyser = analyserRef.current;
			if (analyser && isPlayingRef.current) {
				const data = new Uint8Array(analyser.frequencyBinCount);
				analyser.getByteFrequencyData(data);
				setVoiceState((prev) => ({ ...prev, waveformData: data }));
			}
			animFrameRef.current = requestAnimationFrame(animate);
		};
		animFrameRef.current = requestAnimationFrame(animate);

		return () => {
			if (animFrameRef.current !== null) {
				cancelAnimationFrame(animFrameRef.current);
			}
		};
	}, [enabled]);

	// ── Speaker change handler ─────────────────────────────────────
	const onSpeakerChange = useCallback(
		(speaker: string) => {
			setVoiceState((prev) => ({ ...prev, currentSpeaker: speaker }));
		},
		[],
	);

	// ── Playback controls ──────────────────────────────────────────
	const togglePlayPause = useCallback(() => {
		const ctx = audioCtxRef.current;
		if (!ctx) return;

		if (isPausedRef.current) {
			// Resume
			isPausedRef.current = false;
			ctx.resume();
			setVoiceState((prev) => ({ ...prev, playbackStatus: "playing" }));
			playNext();
		} else {
			// Pause
			isPausedRef.current = true;
			ctx.suspend();
			setVoiceState((prev) => ({ ...prev, playbackStatus: "paused" }));
		}
	}, [playNext]);

	const setVolume = useCallback((vol: number) => {
		const clamped = Math.max(0, Math.min(1, vol));
		if (gainRef.current) {
			gainRef.current.gain.value = clamped;
		}
		setVoiceState((prev) => ({ ...prev, volume: clamped }));
	}, []);

	// ── Export collected audio as WAV blob ──────────────────────────
	const exportAudioBlob = useCallback((): Blob | null => {
		const all = collectedRef.current;
		const keys = Object.keys(all);
		if (keys.length === 0) return null;

		// Merge all speakers' PCM in order
		const allChunks: ArrayBuffer[] = [];
		for (const speaker of keys) {
			for (const chunk of all[speaker]) {
				allChunks.push(chunk);
			}
		}

		const totalLength = allChunks.reduce((sum, c) => sum + c.byteLength, 0);
		const merged = new Uint8Array(totalLength);
		let offset = 0;
		for (const chunk of allChunks) {
			merged.set(new Uint8Array(chunk), offset);
			offset += chunk.byteLength;
		}

		// Build WAV header
		const wavHeader = buildWavHeader(merged.length, PCM_SAMPLE_RATE, PCM_BIT_DEPTH, PCM_CHANNELS);
		return new Blob([wavHeader, merged], { type: "audio/wav" });
	}, []);

	// ── Cleanup on unmount ─────────────────────────────────────────
	useEffect(() => {
		return () => {
			if (animFrameRef.current !== null) {
				cancelAnimationFrame(animFrameRef.current);
			}
			audioCtxRef.current?.close();
			audioCtxRef.current = null;
		};
	}, []);

	// ── Sync enabled prop ──────────────────────────────────────────
	useEffect(() => {
		setVoiceState((prev) => ({ ...prev, enabled }));
	}, [enabled]);

	return {
		voiceState,
		enqueueChunk,
		onSpeakerChange,
		togglePlayPause,
		setVolume,
		exportAudioBlob,
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
