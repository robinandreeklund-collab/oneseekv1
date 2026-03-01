"use client";

import { useState, useEffect, useRef } from "react";

/**
 * Smooth character-by-character typing animation using requestAnimationFrame.
 *
 * Designed for debate voice mode: the backend provides `delayPerWord`
 * (seconds/word) derived from actual TTS audio duration.  This hook
 * converts that into a per-character cadence with a small random
 * variance so the text reveal looks natural and stays in sync with
 * the audio.
 *
 * @param incomingText  The full text that should eventually be displayed.
 * @param delayPerWord  Seconds per word from backend (audio_duration / word_count).
 *                      0 or undefined = show text instantly (no animation).
 * @param active        Whether animation is active. When false, returns
 *                      `incomingText` immediately (used for completed cards).
 */
export function useSmoothTyping(
	incomingText: string,
	delayPerWord: number | undefined,
	active: boolean,
) {
	const [displayedText, setDisplayedText] = useState("");
	const queueRef = useRef<string[]>([]);
	const rafRef = useRef<number | null>(null);
	const lastTimeRef = useRef(0);

	// Derive per-character speed from per-word delay.
	// Average Swedish word ≈ 5.5 chars + 1 space = ~6.5 chars.
	const AVG_CHARS_PER_WORD = 6.5;
	const VARIANCE_RATIO = 0.35; // ±35 % jitter for natural feel
	const msPerChar =
		delayPerWord && delayPerWord > 0
			? (delayPerWord * 1000) / AVG_CHARS_PER_WORD
			: 0;

	// When not active or no animation speed, show everything immediately
	useEffect(() => {
		if (!active || msPerChar === 0) {
			setDisplayedText(incomingText);
			queueRef.current = [];
			if (rafRef.current !== null) {
				cancelAnimationFrame(rafRef.current);
				rafRef.current = null;
			}
		}
	}, [active, msPerChar, incomingText]);

	// Queue new characters when incomingText grows
	useEffect(() => {
		if (!active || msPerChar === 0 || !incomingText) return;

		// Only queue characters beyond what we've already queued/displayed
		const currentLen = displayedText.length + queueRef.current.length;
		if (incomingText.length > currentLen) {
			const newChars = incomingText.slice(currentLen).split("");
			queueRef.current.push(...newChars);
		}

		// Start the RAF loop if not already running
		if (rafRef.current === null && queueRef.current.length > 0) {
			lastTimeRef.current = performance.now();
			const animate = (now: number) => {
				const elapsed = now - lastTimeRef.current;
				const variance = msPerChar * VARIANCE_RATIO;
				const threshold = msPerChar + (Math.random() * variance * 2 - variance);

				if (elapsed >= threshold && queueRef.current.length > 0) {
					// Consume multiple chars if we're behind schedule
					const charsToCatchUp = Math.max(1, Math.floor(elapsed / msPerChar));
					const batch = queueRef.current
						.splice(0, Math.min(charsToCatchUp, queueRef.current.length))
						.join("");
					setDisplayedText((prev) => prev + batch);
					lastTimeRef.current = now;
				}

				if (queueRef.current.length > 0) {
					rafRef.current = requestAnimationFrame(animate);
				} else {
					rafRef.current = null;
				}
			};
			rafRef.current = requestAnimationFrame(animate);
		}
	}, [incomingText, active, msPerChar, displayedText.length]);

	// Cleanup on unmount
	useEffect(() => {
		return () => {
			if (rafRef.current !== null) {
				cancelAnimationFrame(rafRef.current);
			}
		};
	}, []);

	// Reset when text changes completely (new round / new participant)
	const prevTextRef = useRef(incomingText);
	useEffect(() => {
		// If the new text doesn't start with what we were showing, reset
		if (incomingText && !incomingText.startsWith(displayedText.slice(0, 20))) {
			setDisplayedText("");
			queueRef.current = [];
			prevTextRef.current = incomingText;
		}
	}, [incomingText, displayedText]);

	return displayedText;
}
