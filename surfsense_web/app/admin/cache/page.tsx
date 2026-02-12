"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertCircle, Trash2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";

export default function AdminCacheRoute() {
	return (
		<div className="space-y-6">
			<div>
				<h1 className="text-3xl font-bold">Cache Management</h1>
				<p className="text-muted-foreground mt-2">
					Hantera och rensa applikationens cache
				</p>
			</div>

			<Alert>
				<AlertCircle className="h-4 w-4" />
				<AlertDescription>
					Cache management-funktioner kommer snart. Denna sida kommer att innehålla
					verktyg för att rensa agent combo cache, tool embeddings, och andra
					cache-lagrade data.
				</AlertDescription>
			</Alert>

			<Card>
				<CardHeader>
					<CardTitle>Agent Combo Cache</CardTitle>
					<CardDescription>
						Cache för agent-kombinationer och routing-beslut
					</CardDescription>
				</CardHeader>
				<CardContent>
					<Button variant="destructive" className="gap-2" disabled>
						<Trash2 className="h-4 w-4" />
						Rensa Agent Cache
					</Button>
					<p className="text-sm text-muted-foreground mt-2">
						Kommer snart...
					</p>
				</CardContent>
			</Card>
		</div>
	);
}
