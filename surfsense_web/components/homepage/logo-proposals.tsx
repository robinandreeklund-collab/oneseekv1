"use client";

/**
 * 10 Oneseek logo proposals — text logotype + compact icon.
 * Inspired by Grok's clean, geometric, minimal aesthetic.
 *
 * Each proposal has:
 *   - Icon: 32x32 compact mark for small spaces
 *   - Wordmark: Icon + "oneseek" text logotype
 *
 * To preview all 10, render <LogoProposalShowcase /> on any page.
 */

/* ──────────────────────────────────────────────────────────────
   1. "Lens" — Clean magnifying glass O with straight handle
   ────────────────────────────────────────────────────────────── */
export const Logo1Icon = ({ size = 32 }: { size?: number }) => (
	<svg width={size} height={size} viewBox="0 0 32 32" fill="none">
		<circle cx="14" cy="14" r="10" stroke="currentColor" strokeWidth="3" />
		<line x1="21.5" y1="21.5" x2="29" y2="29" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
	</svg>
);

export const Logo1Wordmark = ({ size = 28 }: { size?: number }) => (
	<div className="flex items-center gap-2.5">
		<Logo1Icon size={size} />
		<span className="text-xl font-bold tracking-tight" style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}>
			oneseek
		</span>
	</div>
);

/* ──────────────────────────────────────────────────────────────
   2. "Aperture" — Camera aperture / eye with center dot
   ────────────────────────────────────────────────────────────── */
export const Logo2Icon = ({ size = 32 }: { size?: number }) => (
	<svg width={size} height={size} viewBox="0 0 32 32" fill="none">
		<circle cx="16" cy="16" r="13" stroke="currentColor" strokeWidth="2.5" />
		<circle cx="16" cy="16" r="5" stroke="currentColor" strokeWidth="2" />
		<circle cx="16" cy="16" r="1.5" fill="currentColor" />
	</svg>
);

export const Logo2Wordmark = ({ size = 28 }: { size?: number }) => (
	<div className="flex items-center gap-2.5">
		<Logo2Icon size={size} />
		<span className="text-xl font-semibold tracking-tight" style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}>
			oneseek
		</span>
	</div>
);

/* ──────────────────────────────────────────────────────────────
   3. "Signal" — Radio/radar signal emanating from a point
   ────────────────────────────────────────────────────────────── */
export const Logo3Icon = ({ size = 32 }: { size?: number }) => (
	<svg width={size} height={size} viewBox="0 0 32 32" fill="none">
		<circle cx="16" cy="22" r="3" fill="currentColor" />
		<path d="M10 18a8.5 8.5 0 0112 0" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
		<path d="M6 14a14 14 0 0120 0" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
		<path d="M2 10a20 20 0 0128 0" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
	</svg>
);

export const Logo3Wordmark = ({ size = 28 }: { size?: number }) => (
	<div className="flex items-center gap-2.5">
		<Logo3Icon size={size} />
		<span className="text-xl font-bold tracking-tight" style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}>
			oneseek
		</span>
	</div>
);

/* ──────────────────────────────────────────────────────────────
   4. "Convergence" — Three lines converging to a point (seek)
   ────────────────────────────────────────────────────────────── */
export const Logo4Icon = ({ size = 32 }: { size?: number }) => (
	<svg width={size} height={size} viewBox="0 0 32 32" fill="none">
		<path d="M4 4L16 16" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
		<path d="M28 4L16 16" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
		<path d="M16 28L16 16" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
		<circle cx="16" cy="16" r="3.5" fill="currentColor" />
	</svg>
);

export const Logo4Wordmark = ({ size = 28 }: { size?: number }) => (
	<div className="flex items-center gap-2.5">
		<Logo4Icon size={size} />
		<span className="text-xl font-bold tracking-tight" style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}>
			oneseek
		</span>
	</div>
);

/* ──────────────────────────────────────────────────────────────
   5. "Monogram" — Stylized "O" with inner "1" stroke (one+seek)
   ────────────────────────────────────────────────────────────── */
export const Logo5Icon = ({ size = 32 }: { size?: number }) => (
	<svg width={size} height={size} viewBox="0 0 32 32" fill="none">
		<circle cx="16" cy="16" r="13" stroke="currentColor" strokeWidth="2.5" />
		<path d="M16 8V24" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
		<path d="M14 10L16 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
	</svg>
);

export const Logo5Wordmark = ({ size = 28 }: { size?: number }) => (
	<div className="flex items-center gap-2.5">
		<Logo5Icon size={size} />
		<span className="text-xl font-bold tracking-tight" style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}>
			oneseek
		</span>
	</div>
);

/* ──────────────────────────────────────────────────────────────
   6. "Crosshair" — Minimal crosshair/target (precision seeking)
   ────────────────────────────────────────────────────────────── */
export const Logo6Icon = ({ size = 32 }: { size?: number }) => (
	<svg width={size} height={size} viewBox="0 0 32 32" fill="none">
		<circle cx="16" cy="16" r="11" stroke="currentColor" strokeWidth="2.5" />
		<line x1="16" y1="2" x2="16" y2="8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
		<line x1="16" y1="24" x2="16" y2="30" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
		<line x1="2" y1="16" x2="8" y2="16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
		<line x1="24" y1="16" x2="30" y2="16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
		<circle cx="16" cy="16" r="2" fill="currentColor" />
	</svg>
);

export const Logo6Wordmark = ({ size = 28 }: { size?: number }) => (
	<div className="flex items-center gap-2.5">
		<Logo6Icon size={size} />
		<span className="text-xl font-bold tracking-tight" style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}>
			oneseek
		</span>
	</div>
);

/* ──────────────────────────────────────────────────────────────
   7. "Node" — Graph node with 3 connections (AI pipeline)
   ────────────────────────────────────────────────────────────── */
export const Logo7Icon = ({ size = 32 }: { size?: number }) => (
	<svg width={size} height={size} viewBox="0 0 32 32" fill="none">
		<circle cx="16" cy="16" r="5" fill="currentColor" />
		<line x1="16" y1="11" x2="16" y2="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
		<line x1="20" y1="19.5" x2="27" y2="25" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
		<line x1="12" y1="19.5" x2="5" y2="25" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
		<circle cx="16" cy="3" r="2" fill="currentColor" />
		<circle cx="27" cy="25" r="2" fill="currentColor" />
		<circle cx="5" cy="25" r="2" fill="currentColor" />
	</svg>
);

export const Logo7Wordmark = ({ size = 28 }: { size?: number }) => (
	<div className="flex items-center gap-2.5">
		<Logo7Icon size={size} />
		<span className="text-xl font-bold tracking-tight" style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}>
			oneseek
		</span>
	</div>
);

/* ──────────────────────────────────────────────────────────────
   8. "Slash" — Bold "O" with diagonal cut (Grok-inspired)
   ────────────────────────────────────────────────────────────── */
export const Logo8Icon = ({ size = 32 }: { size?: number }) => (
	<svg width={size} height={size} viewBox="0 0 32 32" fill="none">
		<circle cx="16" cy="16" r="13" stroke="currentColor" strokeWidth="3" />
		<line x1="22" y1="6" x2="10" y2="26" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
	</svg>
);

export const Logo8Wordmark = ({ size = 28 }: { size?: number }) => (
	<div className="flex items-center gap-2.5">
		<Logo8Icon size={size} />
		<span className="text-xl font-black tracking-tight" style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}>
			oneseek
		</span>
	</div>
);

/* ──────────────────────────────────────────────────────────────
   9. "Spark" — Abstract asterisk/spark (intelligence/insight)
   ────────────────────────────────────────────────────────────── */
export const Logo9Icon = ({ size = 32 }: { size?: number }) => (
	<svg width={size} height={size} viewBox="0 0 32 32" fill="none">
		<path d="M16 2L16 30" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
		<path d="M2 16L30 16" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
		<path d="M6 6L26 26" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
		<path d="M26 6L6 26" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
		<circle cx="16" cy="16" r="3" fill="currentColor" />
	</svg>
);

export const Logo9Wordmark = ({ size = 28 }: { size?: number }) => (
	<div className="flex items-center gap-2.5">
		<Logo9Icon size={size} />
		<span className="text-xl font-bold tracking-tight" style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}>
			oneseek
		</span>
	</div>
);

/* ──────────────────────────────────────────────────────────────
   10. "Compass" — Compass needle (direction/finding/seeking)
   ────────────────────────────────────────────────────────────── */
export const Logo10Icon = ({ size = 32 }: { size?: number }) => (
	<svg width={size} height={size} viewBox="0 0 32 32" fill="none">
		<circle cx="16" cy="16" r="13" stroke="currentColor" strokeWidth="2" />
		<path d="M16 6L19 16L16 26L13 16Z" fill="currentColor" />
		<circle cx="16" cy="16" r="2" fill="none" stroke="currentColor" strokeWidth="1.5" />
	</svg>
);

export const Logo10Wordmark = ({ size = 28 }: { size?: number }) => (
	<div className="flex items-center gap-2.5">
		<Logo10Icon size={size} />
		<span className="text-xl font-bold tracking-tight" style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}>
			oneseek
		</span>
	</div>
);

/* ──────────────────────────────────────────────────────────────
   Showcase component — render all 10 proposals side by side
   ────────────────────────────────────────────────────────────── */
const PROPOSALS = [
	{ id: 1, name: "Lens", desc: "Ren sökikon — förstoringsglas med rakt handtag", Icon: Logo1Icon, Wordmark: Logo1Wordmark },
	{ id: 2, name: "Aperture", desc: "Kameraöga — koncentriska cirklar med centrumpunkt", Icon: Logo2Icon, Wordmark: Logo2Wordmark },
	{ id: 3, name: "Signal", desc: "Radarsignal — koncentriska bågar med punkt", Icon: Logo3Icon, Wordmark: Logo3Wordmark },
	{ id: 4, name: "Convergence", desc: "Tre linjer som möts — konvergerande insikt", Icon: Logo4Icon, Wordmark: Logo4Wordmark },
	{ id: 5, name: "Monogram", desc: "Stiliserat 'O' med inre '1'-streck — one+seek", Icon: Logo5Icon, Wordmark: Logo5Wordmark },
	{ id: 6, name: "Crosshair", desc: "Siktkorset — precisionssökning", Icon: Logo6Icon, Wordmark: Logo6Wordmark },
	{ id: 7, name: "Node", desc: "Grafnod med 3 kopplingar — AI-pipeline", Icon: Logo7Icon, Wordmark: Logo7Wordmark },
	{ id: 8, name: "Slash", desc: "Fetstil O med diagonal — Grok-inspirerad", Icon: Logo8Icon, Wordmark: Logo8Wordmark },
	{ id: 9, name: "Spark", desc: "Abstrakt asterisk — intelligens och insikt", Icon: Logo9Icon, Wordmark: Logo9Wordmark },
	{ id: 10, name: "Compass", desc: "Kompassnål — riktning och sökning", Icon: Logo10Icon, Wordmark: Logo10Wordmark },
];

export function LogoProposalShowcase() {
	return (
		<section className="py-16 px-6">
			<div className="max-w-6xl mx-auto">
				<h2 className="text-2xl font-bold text-neutral-900 dark:text-white mb-2">
					Oneseek — Logotypförslag
				</h2>
				<p className="text-neutral-500 dark:text-neutral-400 mb-10">
					10 koncept. Minimal, ren estetik inspirerad av Grok.
				</p>

				<div className="grid grid-cols-1 md:grid-cols-2 gap-6">
					{PROPOSALS.map(({ id, name, desc, Icon, Wordmark }) => (
						<div
							key={id}
							className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-6 flex flex-col gap-5"
						>
							{/* Header */}
							<div className="flex items-center justify-between">
								<span className="text-xs font-bold text-neutral-400 uppercase tracking-wider">
									#{id} — {name}
								</span>
							</div>

							{/* Preview row — light bg + dark bg */}
							<div className="flex gap-4">
								{/* Light */}
								<div className="flex-1 rounded-xl bg-white border border-neutral-200 p-5 flex flex-col items-center gap-4 text-neutral-900">
									<Icon size={40} />
									<Wordmark size={32} />
								</div>
								{/* Dark */}
								<div className="flex-1 rounded-xl bg-neutral-950 border border-neutral-800 p-5 flex flex-col items-center gap-4 text-white">
									<Icon size={40} />
									<Wordmark size={32} />
								</div>
							</div>

							{/* Description */}
							<p className="text-sm text-neutral-500 dark:text-neutral-400">
								{desc}
							</p>
						</div>
					))}
				</div>
			</div>
		</section>
	);
}
