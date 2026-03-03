import type {
	ToolApiInputEvaluationTestCase,
	ToolEvaluationTestCase,
} from "@/contracts/types/admin-tool-settings.types";

type EvalExportFormat = "json" | "yaml";

export function downloadTextFile(content: string, fileName: string, mimeType: string) {
	const blob = new Blob([content], { type: mimeType });
	const blobUrl = URL.createObjectURL(blob);
	const anchor = document.createElement("a");
	anchor.href = blobUrl;
	anchor.download = fileName;
	document.body.appendChild(anchor);
	anchor.click();
	anchor.remove();
	URL.revokeObjectURL(blobUrl);
}

export function buildEvalExportFileName(
	evalKind: "tool_selection" | "api_input",
	jobId: string,
	format: EvalExportFormat,
) {
	const normalizedJob = String(jobId || "unknown")
		.replace(/[^a-zA-Z0-9_-]+/g, "")
		.slice(0, 14);
	const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
	const prefix = evalKind === "api_input" ? "api-input-eval-run" : "tool-eval-run";
	return `${prefix}-${normalizedJob || "unknown"}-${timestamp}.${format}`;
}

export function parseEvalTestCases(rawInput: string): {
	ok: true;
	eval_name?: string;
	target_success_rate?: number;
	tests: ToolEvaluationTestCase[];
} | { ok: false; error: string } {
	const trimmed = rawInput.trim();
	if (!trimmed) return { ok: false, error: "Klistra in eval-JSON innan du kör." };

	try {
		const parsed = JSON.parse(trimmed);
		const envelope = Array.isArray(parsed) ? { tests: parsed } : parsed;
		if (!envelope || !Array.isArray(envelope.tests)) {
			return { ok: false, error: "JSON måste innehålla en tests-array." };
		}
		const tests: ToolEvaluationTestCase[] = envelope.tests.map(
			(item: any, index: number) => ({
				id: String(item.id ?? `case-${index + 1}`),
				question: String(item.question ?? ""),
				difficulty:
					typeof item.difficulty === "string" ? item.difficulty : undefined,
				expected:
					item.expected ||
					item.expected_tool ||
					item.expected_category ||
					item.expected_agent ||
					item.expected_route ||
					item.expected_sub_route ||
					item.plan_requirements
						? {
								tool: item.expected?.tool ?? item.expected_tool ?? null,
								category: item.expected?.category ?? item.expected_category ?? null,
								agent: item.expected?.agent ?? item.expected_agent ?? null,
								route: item.expected?.route ?? item.expected_route ?? null,
								sub_route: item.expected?.sub_route ?? item.expected_sub_route ?? null,
								plan_requirements: Array.isArray(
									item.expected?.plan_requirements ?? item.plan_requirements,
								)
									? (
											item.expected?.plan_requirements ?? item.plan_requirements
										).map((value: unknown) => String(value))
									: [],
							}
						: undefined,
				allowed_tools: Array.isArray(item.allowed_tools)
					? item.allowed_tools.map((value: unknown) => String(value))
					: [],
			}),
		);
		const invalidCase = tests.find((test) => !test.question.trim());
		if (invalidCase) {
			return { ok: false, error: `Test ${invalidCase.id} saknar question.` };
		}
		return {
			ok: true,
			eval_name: typeof envelope.eval_name === "string" ? envelope.eval_name : undefined,
			target_success_rate:
				typeof envelope.target_success_rate === "number"
					? envelope.target_success_rate
					: undefined,
			tests,
		};
	} catch (_error) {
		return { ok: false, error: "Ogiltig JSON. Kontrollera formatet och försök igen." };
	}
}

export function parseApiInputCaseList(items: any[]): ToolApiInputEvaluationTestCase[] {
	return items.map((item: any, index: number) => ({
		id: String(item.id ?? `case-${index + 1}`),
		question: String(item.question ?? ""),
		difficulty: typeof item.difficulty === "string" ? item.difficulty : undefined,
		expected:
			item.expected ||
			item.expected_tool ||
			item.expected_category ||
			item.expected_agent ||
			item.expected_route ||
			item.expected_sub_route ||
			item.plan_requirements ||
			item.required_fields ||
			item.field_values ||
			typeof item.allow_clarification === "boolean"
				? {
						tool: item.expected?.tool ?? item.expected_tool ?? null,
						category: item.expected?.category ?? item.expected_category ?? null,
						agent: item.expected?.agent ?? item.expected_agent ?? null,
						route: item.expected?.route ?? item.expected_route ?? null,
						sub_route: item.expected?.sub_route ?? item.expected_sub_route ?? null,
						plan_requirements: Array.isArray(
							item.expected?.plan_requirements ?? item.plan_requirements,
						)
							? (
									item.expected?.plan_requirements ?? item.plan_requirements
								).map((value: unknown) => String(value))
							: [],
						required_fields: Array.isArray(
							item.expected?.required_fields ?? item.required_fields,
						)
							? (item.expected?.required_fields ?? item.required_fields).map(
									(value: unknown) => String(value),
								)
							: [],
						field_values:
							typeof (item.expected?.field_values ?? item.field_values) ===
								"object" &&
							(item.expected?.field_values ?? item.field_values) !== null
								? (item.expected?.field_values ?? item.field_values)
								: {},
						allow_clarification:
							typeof (item.expected?.allow_clarification ??
								item.allow_clarification) === "boolean"
								? (item.expected?.allow_clarification ?? item.allow_clarification)
								: undefined,
					}
				: undefined,
		allowed_tools: Array.isArray(item.allowed_tools)
			? item.allowed_tools.map((value: unknown) => String(value))
			: [],
	})) as ToolApiInputEvaluationTestCase[];
}

export function parseApiInputEvalInput(
	evalInput: string,
	holdoutInput: string,
	useHoldoutSuite: boolean,
): {
	ok: true;
	eval_name?: string;
	target_success_rate?: number;
	tests: ToolApiInputEvaluationTestCase[];
	holdout_tests: ToolApiInputEvaluationTestCase[];
} | { ok: false; error: string } {
	const trimmed = evalInput.trim();
	if (!trimmed) return { ok: false, error: "Klistra in eval-JSON innan du kör." };

	try {
		const parsed = JSON.parse(trimmed);
		const envelope = Array.isArray(parsed) ? { tests: parsed } : parsed;
		if (!envelope || !Array.isArray(envelope.tests)) {
			return { ok: false, error: "JSON måste innehålla en tests-array." };
		}
		const tests = parseApiInputCaseList(envelope.tests);
		const invalidCase = tests.find((test) => !test.question.trim());
		if (invalidCase) {
			return { ok: false, error: `Test ${invalidCase.id} saknar question.` };
		}
		let holdoutTestsRaw: any[] = [];
		if (useHoldoutSuite) {
			holdoutTestsRaw = Array.isArray(envelope.holdout_tests)
				? envelope.holdout_tests
				: [];
			const holdoutTrimmed = holdoutInput.trim();
			if (holdoutTrimmed) {
				let parsedHoldout: any;
				try {
					parsedHoldout = JSON.parse(holdoutTrimmed);
				} catch (_error) {
					return { ok: false, error: "Ogiltig holdout-JSON. Kontrollera formatet." };
				}
				const extractedHoldoutTests = Array.isArray(parsedHoldout)
					? parsedHoldout
					: Array.isArray(parsedHoldout?.tests)
						? parsedHoldout.tests
						: Array.isArray(parsedHoldout?.holdout_tests)
							? parsedHoldout.holdout_tests
							: null;
				if (!extractedHoldoutTests) {
					return {
						ok: false,
						error: "Holdout-JSON måste innehålla en tests-array (eller holdout_tests).",
					};
				}
				holdoutTestsRaw = extractedHoldoutTests;
			}
		}
		const holdoutTests = parseApiInputCaseList(holdoutTestsRaw);
		const invalidHoldoutCase = holdoutTests.find((test) => !test.question.trim());
		if (invalidHoldoutCase) {
			return { ok: false, error: `Holdout test ${invalidHoldoutCase.id} saknar question.` };
		}
		if (useHoldoutSuite && holdoutTests.length === 0) {
			return {
				ok: false,
				error: "Aktiverad holdout-suite men inga holdout tests hittades. Lägg till holdout-JSON eller holdout_tests i huvud-JSON.",
			};
		}
		return {
			ok: true,
			eval_name: typeof envelope.eval_name === "string" ? envelope.eval_name : undefined,
			target_success_rate:
				typeof envelope.target_success_rate === "number"
					? envelope.target_success_rate
					: undefined,
			tests,
			holdout_tests: holdoutTests,
		};
	} catch (_error) {
		return { ok: false, error: "Ogiltig JSON. Kontrollera formatet och försök igen." };
	}
}

export function formatPercent(value: number | null | undefined) {
	if (value == null || Number.isNaN(value)) return "-";
	return `${(value * 100).toFixed(1)}%`;
}

export function formatSignedPercent(value: number | null | undefined) {
	if (value == null || Number.isNaN(value)) return "-";
	const sign = value > 0 ? "+" : "";
	return `${sign}${(value * 100).toFixed(1)}%`;
}

export function formatAutoLoopStopReason(reason: string | null | undefined) {
	const normalized = String(reason ?? "").trim().toLowerCase();
	if (!normalized) return "Okänd stop-orsak";
	if (normalized === "target_reached") return "Målnivå uppnådd";
	if (normalized === "no_improvement") return "Avbruten p.g.a. utebliven förbättring";
	if (normalized === "max_iterations_reached") return "Max antal iterationer uppnåddes";
	return reason ?? "Okänd stop-orsak";
}
