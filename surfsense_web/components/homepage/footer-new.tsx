"use client";

import {
	IconBrandDiscord,
	IconBrandGithub,
	IconBrandLinkedin,
	IconBrandTwitter,
} from "@tabler/icons-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Logo, OneseekWordmark } from "@/components/Logo";

export function FooterNew() {
	const tNav = useTranslations("navigation");
	const tAuth = useTranslations("auth");
	const tFooter = useTranslations("footer");

	const pages = [
		// {
		//   title: "All Products",
		//   href: "#",
		// },
		// {
		//   title: "Studio",
		//   href: "#",
		// },
		// {
		//   title: "Clients",
		//   href: "#",
		// },
		// Hidden per requirements
		// {
		// 	title: tNav("pricing"),
		// 	href: "/pricing",
		// },
		{
			title: tNav("docs"),
			href: "/docs",
		},
		{
			title: tNav("contact"),
			href: "/contact",
		},
	];

	// Social icons hidden per requirements
	const socials: Array<{
		title: string;
		href: string;
		icon: any;
	}> = [
		// {
		// 	title: "Twitter",
		// 	href: "https://x.com/mod_setter",
		// 	icon: IconBrandTwitter,
		// },
		// {
		// 	title: "LinkedIn",
		// 	href: "https://www.linkedin.com/in/rohan-verma-sde/",
		// 	icon: IconBrandLinkedin,
		// },
		// {
		// 	title: "GitHub",
		// 	href: "https://github.com/MODSetter",
		// 	icon: IconBrandGithub,
		// },
		// {
		// 	title: "Discord",
		// 	href: "https://discord.gg/ejRNvftDp9",
		// 	icon: IconBrandDiscord,
		// },
	];
	// Legal links hidden per requirements
	const legals: Array<{
		title: string;
		href: string;
	}> = [
		// {
		// 	title: tAuth("privacy_policy"),
		// 	href: "/privacy",
		// },
		// {
		// 	title: tAuth("terms_of_service"),
		// 	href: "/terms",
		// },
		// {
		//   title: "Cookie Policy",
		//   href: "#",
		// },
	];

	const signups = [
		{
			title: tAuth("sign_in"),
			href: "/login",
		},
		// {
		//   title: "Login",
		//   href: "#",
		// },
		// {
		//   title: "Forgot Password",
		//   href: "#",
		// },
	];
	return (
		<div className="border-t border-neutral-100 dark:border-white/[0.1] px-8 py-20 bg-white dark:bg-neutral-950 w-full relative overflow-hidden">
			<div className="max-w-7xl mx-auto text-sm text-neutral-500 flex sm:flex-row flex-col justify-between items-start  md:px-8">
				<div>
					<div className="mr-0 md:mr-4 md:flex mb-4">
						<OneseekWordmark iconSize={24} />
					</div>

					<div className="mt-2 ml-2">{tFooter("rights_reserved", { year: new Date().getFullYear() })}</div>
				</div>
				<div className="grid grid-cols-2 lg:grid-cols-4 gap-10 items-start mt-10 sm:mt-0 md:mt-0">
					{pages.length > 0 && (
						<div className="flex justify-center space-y-4 flex-col w-full">
							<p className="transition-colors hover:text-text-neutral-800 text-neutral-600 dark:text-neutral-300 font-bold">
								{tFooter("pages")}
							</p>
							<ul className="transition-colors hover:text-text-neutral-800 text-neutral-600 dark:text-neutral-300 list-none space-y-4">
								{pages.map((page, idx) => (
									<li key={"pages" + idx} className="list-none">
										<Link className="transition-colors hover:text-text-neutral-800 " href={page.href}>
											{page.title}
										</Link>
									</li>
								))}
							</ul>
						</div>
					)}

					{socials.length > 0 && (
						<div className="flex justify-center space-y-4 flex-col">
							<p className="transition-colors hover:text-text-neutral-800 text-neutral-600 dark:text-neutral-300 font-bold">
								{tFooter("socials")}
							</p>
							<ul className="transition-colors hover:text-text-neutral-800 text-neutral-600 dark:text-neutral-300 list-none space-y-4">
								{socials.map((social, idx) => {
									const Icon = social.icon;
									return (
										<li key={"social" + idx} className="list-none">
											<Link
												className="transition-colors hover:text-text-neutral-800 flex items-center gap-2"
												href={social.href}
												target="_blank"
												rel="noopener noreferrer"
											>
												<Icon className="h-5 w-5" />
												{social.title}
											</Link>
										</li>
									);
								})}
							</ul>
						</div>
					)}

					{legals.length > 0 && (
						<div className="flex justify-center space-y-4 flex-col">
							<p className="transition-colors hover:text-text-neutral-800 text-neutral-600 dark:text-neutral-300 font-bold">
								{tFooter("legal")}
							</p>
							<ul className="transition-colors hover:text-text-neutral-800 text-neutral-600 dark:text-neutral-300 list-none space-y-4">
								{legals.map((legal, idx) => (
									<li key={"legal" + idx} className="list-none">
										<Link
											className="transition-colors hover:text-text-neutral-800 "
											href={legal.href}
										>
											{legal.title}
										</Link>
									</li>
								))}
							</ul>
						</div>
					)}
					<div className="flex justify-center space-y-4 flex-col">
						<p className="transition-colors hover:text-text-neutral-800 text-neutral-600 dark:text-neutral-300 font-bold">
							{tFooter("register")}
						</p>
						<ul className="transition-colors hover:text-text-neutral-800 text-neutral-600 dark:text-neutral-300 list-none space-y-4">
							{signups.map((auth, idx) => (
								<li key={"auth" + idx} className="list-none">
									<Link className="transition-colors hover:text-text-neutral-800 " href={auth.href}>
										{auth.title}
									</Link>
								</li>
							))}
						</ul>
					</div>
				</div>
			</div>
			<p className="text-center mt-20 text-5xl md:text-9xl lg:text-[12rem] xl:text-[13rem] font-bold bg-clip-text text-transparent bg-gradient-to-b from-neutral-50 dark:from-neutral-950 to-neutral-200 dark:to-neutral-800 inset-x-0">
				Oneseek
			</p>
		</div>
	);
}
