import type { ToolCallMessagePartComponent } from "@assistant-ui/react";
import { CheckIcon, ChevronDownIcon, ChevronUpIcon, XCircleIcon } from "lucide-react";
import Image from "next/image";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SKOLVERKET_TOOL_NAMES = new Set([
	"search_subjects",
	"get_subject_details",
	"get_subject_versions",
	"search_courses",
	"get_course_details",
	"get_course_versions",
	"search_programs",
	"get_program_details",
	"get_program_versions",
	"search_curriculums",
	"get_curriculum_details",
	"get_curriculum_versions",
	"get_school_types",
	"get_types_of_syllabus",
	"get_subject_and_course_codes",
	"get_study_path_codes",
	"get_api_info",
	"search_school_units",
	"get_school_unit_details",
	"get_school_units_by_status",
	"search_school_units_by_name",
	"search_adult_education",
	"get_adult_education_details",
	"filter_adult_education_by_distance",
	"filter_adult_education_by_pace",
	"get_education_areas",
	"get_directions",
	"search_education_events",
	"count_education_events",
	"count_adult_education_events",
	"get_adult_education_areas_v4",
	"search_school_units_v4",
	"get_school_unit_education_events",
	"get_school_types_v4",
	"get_geographical_areas_v4",
	"get_programs_v4",
	"get_school_unit_documents",
	"get_school_unit_statistics",
	"get_national_statistics",
	"get_program_statistics",
	"health_check",
]);

const containsSkolverketMarker = (value: unknown): boolean => {
	if (value === null || value === undefined) return false;
	const normalized = String(value)
		.toLowerCase()
		.replaceAll("å", "a")
		.replaceAll("ä", "a")
		.replaceAll("ö", "o");
	return normalized.includes("skolverket");
};

const isSkolverketResultPayload = (value: unknown): boolean => {
	if (value === null || value === undefined) return false;
	if (containsSkolverketMarker(value)) return true;

	if (typeof value === "string") {
		try {
			const parsed = JSON.parse(value);
			return isSkolverketResultPayload(parsed);
		} catch {
			return false;
		}
	}

	if (typeof value === "object") {
		const payload = value as Record<string, unknown>;
		if (containsSkolverketMarker(payload.source)) return true;
		if (containsSkolverketMarker(payload.skolverket_tool)) return true;
		if (containsSkolverketMarker(payload.skolverket_category)) return true;
	}

	return false;
};

const isSkolverketToolName = (toolName: string | undefined): boolean => {
	if (!toolName) return false;
	if (SKOLVERKET_TOOL_NAMES.has(toolName)) return true;
	return containsSkolverketMarker(toolName);
};

export const ToolFallback: ToolCallMessagePartComponent = ({
	toolName,
	argsText,
	result,
	status,
}) => {
	const [isCollapsed, setIsCollapsed] = useState(true);
	const showSkolverketBranding = isSkolverketToolName(toolName) || isSkolverketResultPayload(result);

	const isCancelled = status?.type === "incomplete" && status.reason === "cancelled";
	const cancelledReason =
		isCancelled && status.error
			? typeof status.error === "string"
				? status.error
				: JSON.stringify(status.error)
			: null;

	return (
		<div
			className={cn(
				"aui-tool-fallback-root mb-4 flex w-full flex-col gap-3 rounded-lg border py-3",
				isCancelled && "border-muted-foreground/30 bg-muted/30"
			)}
		>
			<div className="aui-tool-fallback-header flex items-center gap-2 px-4">
				{isCancelled ? (
					<XCircleIcon className="aui-tool-fallback-icon size-4 text-muted-foreground" />
				) : (
					<CheckIcon className="aui-tool-fallback-icon size-4" />
				)}
				<p
					className={cn(
						"aui-tool-fallback-title grow",
						isCancelled && "text-muted-foreground line-through"
					)}
				>
					{isCancelled ? "Avbrutet verktyg: " : "Använt verktyg: "}
					<b>{toolName}</b>
				</p>
				{showSkolverketBranding && (
					<div className="inline-flex items-center gap-1.5 rounded-full border border-[#005A9C]/30 bg-[#005A9C]/10 px-2 py-0.5 text-[#005A9C]">
						<Image
							src="/connectors/skolverket.svg"
							alt="Skolverket"
							width={12}
							height={12}
							className="h-3 w-3"
						/>
						<span className="text-[11px] font-semibold">Skolverket</span>
					</div>
				)}
				<Button onClick={() => setIsCollapsed(!isCollapsed)}>
					{isCollapsed ? <ChevronUpIcon /> : <ChevronDownIcon />}
				</Button>
			</div>
			{!isCollapsed && (
				<div className="aui-tool-fallback-content flex flex-col gap-2 border-t pt-2">
					{cancelledReason && (
						<div className="aui-tool-fallback-cancelled-root px-4">
							<p className="aui-tool-fallback-cancelled-header font-semibold text-muted-foreground">
								Avbrottsorsak:
							</p>
							<p className="aui-tool-fallback-cancelled-reason text-muted-foreground">
								{cancelledReason}
							</p>
						</div>
					)}
					<div className={cn("aui-tool-fallback-args-root px-4", isCancelled && "opacity-60")}>
						<pre className="aui-tool-fallback-args-value whitespace-pre-wrap">{argsText}</pre>
					</div>
					{!isCancelled && result !== undefined && (
						<div className="aui-tool-fallback-result-root border-t border-dashed px-4 pt-2">
							<p className="aui-tool-fallback-result-header font-semibold">Resultat:</p>
							<pre className="aui-tool-fallback-result-content whitespace-pre-wrap">
								{typeof result === "string" ? result : JSON.stringify(result, null, 2)}
							</pre>
						</div>
					)}
				</div>
			)}
		</div>
	);
};
