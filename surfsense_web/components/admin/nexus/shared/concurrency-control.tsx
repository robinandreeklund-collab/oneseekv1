"use client";

import { Gauge, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { nexusApiService } from "@/lib/apis/nexus-api.service";

export function ConcurrencyControl() {
	const [maxConcurrency, setMaxConcurrency] = useState<number | null>(null);
	const [activeTasks, setActiveTasks] = useState(0);
	const [peakActive, setPeakActive] = useState(0);
	const [sliderValue, setSliderValue] = useState(12);
	const [saving, setSaving] = useState(false);

	const load = useCallback(() => {
		nexusApiService
			.getConcurrencySettings()
			.then((data) => {
				setMaxConcurrency(data.max_concurrency);
				setSliderValue(data.max_concurrency);
				setActiveTasks(data.active_tasks);
				setPeakActive(data.peak_active);
			})
			.catch(() => {
				/* non-critical */
			});
	}, []);

	useEffect(() => {
		load();
	}, [load]);

	const handleSave = () => {
		if (sliderValue === maxConcurrency) return;
		setSaving(true);
		nexusApiService
			.updateConcurrency(sliderValue)
			.then((data) => {
				setMaxConcurrency(data.max_concurrency);
			})
			.catch(() => {
				/* ignore */
			})
			.finally(() => setSaving(false));
	};

	if (maxConcurrency === null) return null;

	const isDirty = sliderValue !== maxConcurrency;

	return (
		<div className="rounded-lg border bg-card p-4">
			<div className="flex items-center justify-between mb-3">
				<div className="flex items-center gap-2">
					<Gauge className="h-4 w-4 text-muted-foreground" />
					<span className="text-sm font-medium">Max parallella anrop</span>
				</div>
				<div className="flex items-center gap-3 text-xs text-muted-foreground">
					<span>Aktiva: {activeTasks}</span>
					<span>Peak: {peakActive}</span>
				</div>
			</div>
			<div className="flex items-center gap-4">
				<Slider
					min={1}
					max={64}
					step={1}
					value={[sliderValue]}
					onValueChange={([v]) => setSliderValue(v)}
					className="flex-1"
				/>
				<span className="text-sm font-mono font-bold w-8 text-right tabular-nums">
					{sliderValue}
				</span>
				<Button
					size="sm"
					variant={isDirty ? "default" : "outline"}
					disabled={!isDirty || saving}
					onClick={handleSave}
				>
					{saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Spara"}
				</Button>
			</div>
		</div>
	);
}
