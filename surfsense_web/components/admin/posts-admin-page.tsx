"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogHeader,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
	Plus,
	Pencil,
	Trash2,
	Eye,
	EyeOff,
	ImagePlus,
	Loader2,
	ArrowLeft,
} from "lucide-react";
import { toast } from "sonner";

interface Post {
	id: number;
	type: string;
	title: string;
	slug: string;
	content: string;
	excerpt: string;
	tags: string;
	imageUrl: string;
	published: boolean;
	createdAt: string;
	updatedAt: string;
}

interface PostsAdminPageProps {
	type: "changelog" | "devlog";
	title: string;
	description: string;
}

function slugify(text: string): string {
	return text
		.toLowerCase()
		.replace(/[åä]/g, "a")
		.replace(/ö/g, "o")
		.replace(/[^a-z0-9]+/g, "-")
		.replace(/(^-|-$)/g, "");
}

export function PostsAdminPage({ type, title, description }: PostsAdminPageProps) {
	const [posts, setPosts] = useState<Post[]>([]);
	const [loading, setLoading] = useState(true);
	const [editorOpen, setEditorOpen] = useState(false);
	const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
	const [postToDelete, setPostToDelete] = useState<Post | null>(null);
	const [saving, setSaving] = useState(false);
	const [editingPost, setEditingPost] = useState<Post | null>(null);
	const [uploading, setUploading] = useState(false);

	// Form state
	const [formTitle, setFormTitle] = useState("");
	const [formSlug, setFormSlug] = useState("");
	const [formContent, setFormContent] = useState("");
	const [formExcerpt, setFormExcerpt] = useState("");
	const [formTags, setFormTags] = useState("");
	const [formImageUrl, setFormImageUrl] = useState("");
	const [formPublished, setFormPublished] = useState(false);
	const [autoSlug, setAutoSlug] = useState(true);
	const fileInputRef = useRef<HTMLInputElement>(null);
	const contentImageInputRef = useRef<HTMLInputElement>(null);

	const fetchPosts = useCallback(async () => {
		try {
			setLoading(true);
			const res = await fetch(`/api/posts?type=${type}`);
			const data = await res.json();
			if (data.success) {
				setPosts(data.data);
			}
		} catch {
			toast.error("Kunde inte hämta inlägg");
		} finally {
			setLoading(false);
		}
	}, [type]);

	useEffect(() => {
		fetchPosts();
	}, [fetchPosts]);

	const resetForm = () => {
		setFormTitle("");
		setFormSlug("");
		setFormContent("");
		setFormExcerpt("");
		setFormTags("");
		setFormImageUrl("");
		setFormPublished(false);
		setAutoSlug(true);
		setEditingPost(null);
	};

	const openNewPost = () => {
		resetForm();
		setEditorOpen(true);
	};

	const openEditPost = (post: Post) => {
		setEditingPost(post);
		setFormTitle(post.title);
		setFormSlug(post.slug);
		setFormContent(post.content);
		setFormExcerpt(post.excerpt || "");
		setFormTags(post.tags || "");
		setFormImageUrl(post.imageUrl || "");
		setFormPublished(post.published);
		setAutoSlug(false);
		setEditorOpen(true);
	};

	const handleTitleChange = (value: string) => {
		setFormTitle(value);
		if (autoSlug) {
			setFormSlug(slugify(value));
		}
	};

	const handleUploadImage = async (file: File, setUrl: (url: string) => void) => {
		setUploading(true);
		try {
			const formData = new FormData();
			formData.append("file", file);
			const res = await fetch("/api/upload", { method: "POST", body: formData });
			const data = await res.json();
			if (data.success) {
				setUrl(data.url);
				toast.success("Bild uppladdad");
			} else {
				toast.error(data.message || "Kunde inte ladda upp bild");
			}
		} catch {
			toast.error("Kunde inte ladda upp bild");
		} finally {
			setUploading(false);
		}
	};

	const handleContentImageUpload = async (file: File) => {
		setUploading(true);
		try {
			const formData = new FormData();
			formData.append("file", file);
			const res = await fetch("/api/upload", { method: "POST", body: formData });
			const data = await res.json();
			if (data.success) {
				const markdownImage = `\n![${file.name}](${data.url})\n`;
				setFormContent((prev) => prev + markdownImage);
				toast.success("Bild infogad i innehållet");
			} else {
				toast.error(data.message || "Kunde inte ladda upp bild");
			}
		} catch {
			toast.error("Kunde inte ladda upp bild");
		} finally {
			setUploading(false);
		}
	};

	const handleSave = async () => {
		if (!formTitle.trim() || !formSlug.trim() || !formContent.trim()) {
			toast.error("Titel, slug och innehåll krävs");
			return;
		}

		setSaving(true);
		try {
			const payload = {
				type,
				title: formTitle,
				slug: formSlug,
				content: formContent,
				excerpt: formExcerpt,
				tags: formTags,
				imageUrl: formImageUrl,
				published: formPublished,
			};

			let res: Response;
			if (editingPost) {
				res = await fetch(`/api/posts/${editingPost.id}`, {
					method: "PUT",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify(payload),
				});
			} else {
				res = await fetch("/api/posts", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify(payload),
				});
			}

			const data = await res.json();
			if (data.success) {
				toast.success(editingPost ? "Inlägg uppdaterat" : "Inlägg skapat");
				setEditorOpen(false);
				resetForm();
				fetchPosts();
			} else {
				toast.error(data.message || "Något gick fel");
			}
		} catch {
			toast.error("Kunde inte spara inlägg");
		} finally {
			setSaving(false);
		}
	};

	const handleTogglePublish = async (post: Post) => {
		try {
			const res = await fetch(`/api/posts/${post.id}`, {
				method: "PUT",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ published: !post.published }),
			});
			const data = await res.json();
			if (data.success) {
				toast.success(post.published ? "Inlägg avpublicerat" : "Inlägg publicerat");
				fetchPosts();
			}
		} catch {
			toast.error("Kunde inte ändra publiceringsstatus");
		}
	};

	const handleDelete = async () => {
		if (!postToDelete) return;
		try {
			const res = await fetch(`/api/posts/${postToDelete.id}`, { method: "DELETE" });
			const data = await res.json();
			if (data.success) {
				toast.success("Inlägg borttaget");
				fetchPosts();
			}
		} catch {
			toast.error("Kunde inte ta bort inlägg");
		} finally {
			setDeleteDialogOpen(false);
			setPostToDelete(null);
		}
	};

	const formatDate = (dateStr: string) => {
		return new Date(dateStr).toLocaleDateString("sv-SE", {
			year: "numeric",
			month: "short",
			day: "numeric",
		});
	};

	// Editor view
	if (editorOpen) {
		return (
			<div className="space-y-6">
				<div className="flex items-center gap-4">
					<Button variant="ghost" size="sm" onClick={() => { setEditorOpen(false); resetForm(); }}>
						<ArrowLeft className="h-4 w-4 mr-2" />
						Tillbaka
					</Button>
					<div>
						<h1 className="text-2xl font-bold">
							{editingPost ? "Redigera inlägg" : "Nytt inlägg"}
						</h1>
						<p className="text-muted-foreground text-sm">{title}</p>
					</div>
				</div>

				<div className="grid gap-6 lg:grid-cols-[1fr_300px]">
					{/* Main editor */}
					<div className="space-y-4">
						<Card>
							<CardContent className="pt-6 space-y-4">
								<div className="space-y-2">
									<Label htmlFor="title">Titel</Label>
									<Input
										id="title"
										value={formTitle}
										onChange={(e) => handleTitleChange(e.target.value)}
										placeholder="Titel på inlägget"
									/>
								</div>

								<div className="space-y-2">
									<Label htmlFor="slug">Slug</Label>
									<div className="flex gap-2">
										<Input
											id="slug"
											value={formSlug}
											onChange={(e) => {
												setAutoSlug(false);
												setFormSlug(e.target.value);
											}}
											placeholder="url-slug"
										/>
									</div>
								</div>

								<div className="space-y-2">
									<Label htmlFor="excerpt">Kort beskrivning</Label>
									<Input
										id="excerpt"
										value={formExcerpt}
										onChange={(e) => setFormExcerpt(e.target.value)}
										placeholder="En kort sammanfattning..."
									/>
								</div>

								<Separator />

								<div className="space-y-2">
									<div className="flex items-center justify-between">
										<Label htmlFor="content">Innehåll (Markdown)</Label>
										<Button
											variant="outline"
											size="sm"
											onClick={() => contentImageInputRef.current?.click()}
											disabled={uploading}
										>
											{uploading ? (
												<Loader2 className="h-4 w-4 mr-2 animate-spin" />
											) : (
												<ImagePlus className="h-4 w-4 mr-2" />
											)}
											Infoga bild
										</Button>
										<input
											ref={contentImageInputRef}
											type="file"
											accept="image/*"
											className="hidden"
											onChange={(e) => {
												const file = e.target.files?.[0];
												if (file) handleContentImageUpload(file);
												e.target.value = "";
											}}
										/>
									</div>
									<Textarea
										id="content"
										value={formContent}
										onChange={(e) => setFormContent(e.target.value)}
										placeholder="Skriv ditt innehåll i Markdown-format..."
										className="min-h-[400px] font-mono text-sm"
									/>
								</div>
							</CardContent>
						</Card>
					</div>

					{/* Sidebar */}
					<div className="space-y-4">
						<Card>
							<CardHeader>
								<CardTitle className="text-base">Publicera</CardTitle>
							</CardHeader>
							<CardContent className="space-y-4">
								<div className="flex items-center justify-between">
									<Label htmlFor="published">Publicerad</Label>
									<Switch
										id="published"
										checked={formPublished}
										onCheckedChange={setFormPublished}
									/>
								</div>
								<Button className="w-full" onClick={handleSave} disabled={saving}>
									{saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
									{editingPost ? "Uppdatera" : "Skapa"}
								</Button>
							</CardContent>
						</Card>

						<Card>
							<CardHeader>
								<CardTitle className="text-base">Taggar</CardTitle>
								<CardDescription>Kommaseparerade taggar</CardDescription>
							</CardHeader>
							<CardContent>
								<Input
									value={formTags}
									onChange={(e) => setFormTags(e.target.value)}
									placeholder="feature, fix, improvement"
								/>
							</CardContent>
						</Card>

						<Card>
							<CardHeader>
								<CardTitle className="text-base">Omslagsbild</CardTitle>
							</CardHeader>
							<CardContent className="space-y-3">
								{formImageUrl && (
									<div className="relative aspect-video rounded-lg overflow-hidden border bg-muted">
										<img
											src={formImageUrl}
											alt="Omslagsbild"
											className="object-cover w-full h-full"
										/>
									</div>
								)}
								<Input
									value={formImageUrl}
									onChange={(e) => setFormImageUrl(e.target.value)}
									placeholder="URL till bild eller ladda upp"
								/>
								<Button
									variant="outline"
									size="sm"
									className="w-full"
									onClick={() => fileInputRef.current?.click()}
									disabled={uploading}
								>
									{uploading ? (
										<Loader2 className="h-4 w-4 mr-2 animate-spin" />
									) : (
										<ImagePlus className="h-4 w-4 mr-2" />
									)}
									Ladda upp bild
								</Button>
								<input
									ref={fileInputRef}
									type="file"
									accept="image/*"
									className="hidden"
									onChange={(e) => {
										const file = e.target.files?.[0];
										if (file) handleUploadImage(file, setFormImageUrl);
										e.target.value = "";
									}}
								/>
							</CardContent>
						</Card>
					</div>
				</div>
			</div>
		);
	}

	// List view
	return (
		<div className="space-y-6">
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-3xl font-bold">{title}</h1>
					<p className="text-muted-foreground mt-2">{description}</p>
				</div>
				<Button onClick={openNewPost} className="gap-2">
					<Plus className="h-4 w-4" />
					Nytt inlägg
				</Button>
			</div>

			{loading ? (
				<div className="flex items-center justify-center py-20">
					<Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
				</div>
			) : posts.length === 0 ? (
				<Card>
					<CardContent className="flex flex-col items-center justify-center py-20">
						<p className="text-muted-foreground mb-4">Inga inlägg ännu</p>
						<Button onClick={openNewPost} className="gap-2">
							<Plus className="h-4 w-4" />
							Skapa ditt första inlägg
						</Button>
					</CardContent>
				</Card>
			) : (
				<div className="space-y-3">
					{posts.map((post) => (
						<Card key={post.id} className="hover:shadow-sm transition-shadow">
							<CardContent className="flex items-center gap-4 py-4">
								{post.imageUrl && (
									<div className="w-16 h-16 rounded-lg overflow-hidden border bg-muted shrink-0">
										<img
											src={post.imageUrl}
											alt=""
											className="object-cover w-full h-full"
										/>
									</div>
								)}
								<div className="flex-1 min-w-0">
									<div className="flex items-center gap-2 mb-1">
										<h3 className="font-semibold truncate">{post.title}</h3>
										<Badge variant={post.published ? "default" : "secondary"}>
											{post.published ? "Publicerad" : "Utkast"}
										</Badge>
									</div>
									<p className="text-sm text-muted-foreground truncate">
										{post.excerpt || post.content.substring(0, 120)}
									</p>
									<div className="flex items-center gap-3 mt-1">
										<span className="text-xs text-muted-foreground">
											{formatDate(post.createdAt)}
										</span>
										{post.tags && (
											<div className="flex gap-1">
												{post.tags.split(",").filter(Boolean).slice(0, 3).map((tag) => (
													<Badge key={tag.trim()} variant="outline" className="text-xs py-0">
														{tag.trim()}
													</Badge>
												))}
											</div>
										)}
									</div>
								</div>
								<div className="flex items-center gap-1 shrink-0">
									<Button
										variant="ghost"
										size="icon"
										onClick={() => handleTogglePublish(post)}
										title={post.published ? "Avpublicera" : "Publicera"}
									>
										{post.published ? (
											<EyeOff className="h-4 w-4" />
										) : (
											<Eye className="h-4 w-4" />
										)}
									</Button>
									<Button
										variant="ghost"
										size="icon"
										onClick={() => openEditPost(post)}
										title="Redigera"
									>
										<Pencil className="h-4 w-4" />
									</Button>
									<Button
										variant="ghost"
										size="icon"
										onClick={() => {
											setPostToDelete(post);
											setDeleteDialogOpen(true);
										}}
										title="Ta bort"
									>
										<Trash2 className="h-4 w-4 text-destructive" />
									</Button>
								</div>
							</CardContent>
						</Card>
					))}
				</div>
			)}

			{/* Delete confirmation */}
			<AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
				<AlertDialogContent>
					<AlertDialogHeader>
						<AlertDialogTitle>Ta bort inlägg?</AlertDialogTitle>
						<AlertDialogDescription>
							Är du säker på att du vill ta bort &quot;{postToDelete?.title}&quot;? Detta kan inte ångras.
						</AlertDialogDescription>
					</AlertDialogHeader>
					<AlertDialogFooter>
						<AlertDialogCancel>Avbryt</AlertDialogCancel>
						<AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
							Ta bort
						</AlertDialogAction>
					</AlertDialogFooter>
				</AlertDialogContent>
			</AlertDialog>
		</div>
	);
}
