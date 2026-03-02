import { boolean, integer, pgTable, text, timestamp, varchar } from "drizzle-orm/pg-core";

export const usersTable = pgTable("users", {
	id: integer().primaryKey().generatedAlwaysAsIdentity(),
	name: varchar({ length: 255 }).notNull(),
	email: varchar({ length: 255 }).notNull().unique(),
	company: varchar({ length: 255 }).notNull(),
	message: text().default(""),
});

export const postsTable = pgTable("posts", {
	id: integer().primaryKey().generatedAlwaysAsIdentity(),
	type: varchar({ length: 50 }).notNull(), // "changelog" or "devlog"
	title: varchar({ length: 500 }).notNull(),
	slug: varchar({ length: 500 }).notNull().unique(),
	content: text().notNull(), // markdown content
	excerpt: text().default(""),
	tags: text().default(""), // comma-separated tags
	imageUrl: text("image_url").default(""),
	published: boolean().default(false),
	createdAt: timestamp("created_at").defaultNow().notNull(),
	updatedAt: timestamp("updated_at").defaultNow().notNull(),
});
