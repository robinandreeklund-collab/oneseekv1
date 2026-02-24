"use client";

import { useState } from "react";
import {
	X,
	Zap,
	Bot,
	Wrench,
	Tag,
	FileText,
	Hash,
	ArrowRight,
	Save,
	ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import Link from "next/link";
import type {
	FlowIntentNode,
	FlowAgentNode,
	FlowToolNode,
	PipelineNode,
} from "@/contracts/types/admin-flow-graph.types";

type SelectedNodeData =
	| { type: "intent"; data: FlowIntentNode }
	| { type: "agent"; data: FlowAgentNode }
	| { type: "tool"; data: FlowToolNode }
	| { type: "pipeline"; data: PipelineNode };

interface FlowDetailPanelProps {
	selectedNode: SelectedNodeData;
	connectionCounts: {
		agentsPerIntent: Record<string, number>;
		toolsPerAgent: Record<string, number>;
	};
	onClose: () => void;
}

function IntentDetail({
	intent,
	agentCount,
}: {
	intent: FlowIntentNode;
	agentCount: number;
}) {
	const [editing, setEditing] = useState(false);
	const [description, setDescription] = useState(intent.description);

	return (
		<div className="space-y-4">
			{/* Header */}
			<div className="flex items-center gap-3">
				<div className="flex items-center justify-center h-10 w-10 rounded-lg bg-violet-500/10">
					<Zap className="h-5 w-5 text-violet-500" />
				</div>
				<div>
					<h3 className="text-base font-semibold">{intent.label}</h3>
					<p className="text-xs text-muted-foreground">Intent</p>
				</div>
			</div>

			<Separator />

			{/* Properties */}
			<div className="space-y-3">
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Route</span>
					<Badge variant="secondary" className="text-xs">{intent.route}</Badge>
				</div>
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Priority</span>
					<span className="text-xs font-mono">{intent.priority}</span>
				</div>
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Status</span>
					<Badge variant={intent.enabled ? "default" : "destructive"} className="text-xs">
						{intent.enabled ? "Aktiv" : "Inaktiv"}
					</Badge>
				</div>
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Kopplade agenter</span>
					<span className="text-xs font-mono">{agentCount}</span>
				</div>
			</div>

			<Separator />

			{/* Description */}
			<div className="space-y-2">
				<div className="flex items-center justify-between">
					<Label className="text-xs flex items-center gap-1.5">
						<FileText className="h-3 w-3" /> Beskrivning
					</Label>
					<Button
						variant="ghost"
						size="sm"
						className="h-6 text-xs px-2"
						onClick={() => setEditing(!editing)}
					>
						{editing ? "Avbryt" : "Redigera"}
					</Button>
				</div>
				{editing ? (
					<div className="space-y-2">
						<Textarea
							value={description}
							onChange={(e) => setDescription(e.target.value)}
							className="text-xs min-h-[60px]"
						/>
						<Button size="sm" className="h-7 text-xs">
							<Save className="h-3 w-3 mr-1.5" /> Spara
						</Button>
					</div>
				) : (
					<p className="text-xs text-muted-foreground">{intent.description || "Ingen beskrivning"}</p>
				)}
			</div>

			<Separator />

			{/* Keywords */}
			<div className="space-y-2">
				<Label className="text-xs flex items-center gap-1.5">
					<Tag className="h-3 w-3" /> Nyckelord
				</Label>
				<div className="flex flex-wrap gap-1">
					{intent.keywords.map((kw) => (
						<Badge key={kw} variant="outline" className="text-[10px] px-1.5 py-0">
							{kw}
						</Badge>
					))}
				</div>
			</div>

			<Separator />

			{/* Quick link */}
			<Link href="/admin/prompts" className="flex items-center gap-2 text-xs text-primary hover:underline">
				<ExternalLink className="h-3 w-3" /> Redigera intent i detalj
			</Link>
		</div>
	);
}

function AgentDetail({
	agent,
	toolCount,
}: {
	agent: FlowAgentNode;
	toolCount: number;
}) {
	const [editing, setEditing] = useState(false);
	const [description, setDescription] = useState(agent.description);

	return (
		<div className="space-y-4">
			{/* Header */}
			<div className="flex items-center gap-3">
				<div className="flex items-center justify-center h-10 w-10 rounded-lg bg-blue-500/10">
					<Bot className="h-5 w-5 text-blue-500" />
				</div>
				<div>
					<h3 className="text-base font-semibold">{agent.label}</h3>
					<p className="text-xs text-muted-foreground">Agent</p>
				</div>
			</div>

			<Separator />

			{/* Properties */}
			<div className="space-y-3">
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Agent ID</span>
					<span className="text-xs font-mono">{agent.agent_id}</span>
				</div>
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Prompt Key</span>
					<Badge variant="secondary" className="text-xs">{agent.prompt_key}</Badge>
				</div>
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Namespace</span>
					<span className="text-xs font-mono">{agent.namespace.join("/")}</span>
				</div>
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Kopplade verktyg</span>
					<span className="text-xs font-mono">{toolCount}</span>
				</div>
			</div>

			<Separator />

			{/* Description */}
			<div className="space-y-2">
				<div className="flex items-center justify-between">
					<Label className="text-xs flex items-center gap-1.5">
						<FileText className="h-3 w-3" /> Beskrivning
					</Label>
					<Button
						variant="ghost"
						size="sm"
						className="h-6 text-xs px-2"
						onClick={() => setEditing(!editing)}
					>
						{editing ? "Avbryt" : "Redigera"}
					</Button>
				</div>
				{editing ? (
					<div className="space-y-2">
						<Textarea
							value={description}
							onChange={(e) => setDescription(e.target.value)}
							className="text-xs min-h-[60px]"
						/>
						<Button size="sm" className="h-7 text-xs">
							<Save className="h-3 w-3 mr-1.5" /> Spara
						</Button>
					</div>
				) : (
					<p className="text-xs text-muted-foreground">{agent.description || "Ingen beskrivning"}</p>
				)}
			</div>

			<Separator />

			{/* Keywords */}
			<div className="space-y-2">
				<Label className="text-xs flex items-center gap-1.5">
					<Tag className="h-3 w-3" /> Nyckelord
				</Label>
				<div className="flex flex-wrap gap-1">
					{agent.keywords.map((kw) => (
						<Badge key={kw} variant="outline" className="text-[10px] px-1.5 py-0">
							{kw}
						</Badge>
					))}
				</div>
			</div>

			<Separator />

			{/* Quick links */}
			<div className="space-y-1.5">
				<Link href="/admin/prompts" className="flex items-center gap-2 text-xs text-primary hover:underline">
					<ExternalLink className="h-3 w-3" /> Redigera agent-prompt
				</Link>
				<Link href="/admin/tools" className="flex items-center gap-2 text-xs text-primary hover:underline">
					<ExternalLink className="h-3 w-3" /> Hantera verktyg
				</Link>
			</div>
		</div>
	);
}

function ToolDetail({ tool }: { tool: FlowToolNode }) {
	return (
		<div className="space-y-4">
			{/* Header */}
			<div className="flex items-center gap-3">
				<div className="flex items-center justify-center h-10 w-10 rounded-lg bg-emerald-500/10">
					<Wrench className="h-5 w-5 text-emerald-500" />
				</div>
				<div>
					<h3 className="text-base font-semibold">{tool.label}</h3>
					<p className="text-xs text-muted-foreground">Verktyg</p>
				</div>
			</div>

			<Separator />

			{/* Properties */}
			<div className="space-y-3">
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Tool ID</span>
					<span className="text-xs font-mono">{tool.tool_id}</span>
				</div>
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Agent</span>
					<div className="flex items-center gap-1">
						<Badge variant="secondary" className="text-xs">{tool.agent_id}</Badge>
					</div>
				</div>
			</div>

			<Separator />

			{/* Quick links */}
			<div className="space-y-1.5">
				<Link href="/admin/tools" className="flex items-center gap-2 text-xs text-primary hover:underline">
					<ExternalLink className="h-3 w-3" /> Redigera metadata
				</Link>
				<Link href="/admin/lifecycle" className="flex items-center gap-2 text-xs text-primary hover:underline">
					<ExternalLink className="h-3 w-3" /> Lifecycle-status
				</Link>
			</div>
		</div>
	);
}

function PipelineDetail({ node }: { node: PipelineNode }) {
	return (
		<div className="space-y-4">
			<div className="flex items-center gap-3">
				<div className="flex items-center justify-center h-10 w-10 rounded-lg bg-primary/10">
					<Hash className="h-5 w-5 text-primary" />
				</div>
				<div>
					<h3 className="text-base font-semibold">{node.label}</h3>
					<p className="text-xs text-muted-foreground">Pipeline-nod</p>
				</div>
			</div>

			<Separator />

			<div className="space-y-3">
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Nod-ID</span>
					<span className="text-xs font-mono">{node.id.replace("node:", "")}</span>
				</div>
				<div className="flex items-center justify-between">
					<span className="text-xs text-muted-foreground">Steg</span>
					<Badge variant="secondary" className="text-xs">{node.stage}</Badge>
				</div>
			</div>

			<Separator />

			<div className="space-y-2">
				<Label className="text-xs flex items-center gap-1.5">
					<FileText className="h-3 w-3" /> Beskrivning
				</Label>
				<p className="text-xs text-muted-foreground">{node.description || "Ingen beskrivning"}</p>
			</div>

			<Separator />

			<Link href="/admin/prompts" className="flex items-center gap-2 text-xs text-primary hover:underline">
				<ExternalLink className="h-3 w-3" /> Redigera nod-prompt
			</Link>
		</div>
	);
}

export function FlowDetailPanel({
	selectedNode,
	connectionCounts,
	onClose,
}: FlowDetailPanelProps) {
	return (
		<div className="w-80 border-l bg-background overflow-y-auto">
			<div className="p-4">
				<div className="flex items-center justify-between mb-4">
					<h3 className="text-sm font-semibold text-muted-foreground">Detaljer</h3>
					<Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={onClose}>
						<X className="h-4 w-4" />
					</Button>
				</div>

				{selectedNode.type === "intent" && (
					<IntentDetail
						intent={selectedNode.data}
						agentCount={connectionCounts.agentsPerIntent[selectedNode.data.id] ?? 0}
					/>
				)}
				{selectedNode.type === "agent" && (
					<AgentDetail
						agent={selectedNode.data}
						toolCount={connectionCounts.toolsPerAgent[selectedNode.data.id] ?? 0}
					/>
				)}
				{selectedNode.type === "tool" && <ToolDetail tool={selectedNode.data} />}
				{selectedNode.type === "pipeline" && <PipelineDetail node={selectedNode.data} />}
			</div>
		</div>
	);
}
