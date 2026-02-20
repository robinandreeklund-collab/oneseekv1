import type { ZodType } from "zod";
import { getBearerToken, handleUnauthorized } from "../auth-utils";
import {
	AppError,
	AuthenticationError,
	AuthorizationError,
	NetworkError,
	NotFoundError,
} from "../error";

enum ResponseType {
	JSON = "json",
	TEXT = "text",
	BLOB = "blob",
	ARRAY_BUFFER = "arrayBuffer",
	// Add more response types as needed
}

function _formatApiErrorDetail(detail: unknown): string {
	if (typeof detail === "string") {
		return detail;
	}
	if (Array.isArray(detail)) {
		const first = detail[0];
		if (typeof first === "string") {
			return first;
		}
		try {
			return JSON.stringify(detail);
		} catch {
			return "Request failed";
		}
	}
	if (detail && typeof detail === "object") {
		const payload = detail as Record<string, unknown>;
		const message =
			typeof payload.message === "string" && payload.message.trim().length > 0
				? payload.message
				: "";
		const conflicts = Array.isArray(payload.conflicts) ? payload.conflicts : [];
		if (message && conflicts.length > 0) {
			const first = conflicts[0];
			if (first && typeof first === "object") {
				const row = first as Record<string, unknown>;
				const layer = typeof row.layer === "string" ? row.layer : "?";
				const item =
					typeof row.item_label === "string"
						? row.item_label
						: typeof row.item_id === "string"
							? row.item_id
							: "?";
				const competitor =
					typeof row.competitor_label === "string"
						? row.competitor_label
						: typeof row.competitor_id === "string"
							? row.competitor_id
							: "?";
				const similarity =
					typeof row.similarity === "number" || typeof row.similarity === "string"
						? String(row.similarity)
						: "?";
				const maxSimilarity =
					typeof row.max_similarity === "number" || typeof row.max_similarity === "string"
						? String(row.max_similarity)
						: "?";
				return `${message} [${layer}] ${item} -> ${competitor} (${similarity} > ${maxSimilarity})`;
			}
		}
		if (message) {
			return message;
		}
		try {
			return JSON.stringify(detail);
		} catch {
			return "Request failed";
		}
	}
	return "Request failed";
}

export type RequestOptions = {
	method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
	headers?: Record<string, string>;
	contentType?: "application/json" | "application/x-www-form-urlencoded";
	signal?: AbortSignal;
	body?: any;
	responseType?: ResponseType;
	// Add more options as needed
};

class BaseApiService {
	baseUrl: string;

	noAuthEndpoints: string[] = ["/auth/jwt/login", "/auth/register", "/auth/refresh"];

	// Prefixes that don't require auth (checked with startsWith)
	noAuthPrefixes: string[] = ["/api/v1/public/"];

	// Use a getter to always read fresh token from localStorage
	// This ensures the token is always up-to-date after login/logout
	get bearerToken(): string {
		return typeof window !== "undefined" ? getBearerToken() || "" : "";
	}

	constructor(baseUrl: string) {
		this.baseUrl = baseUrl;
	}

	// Keep for backward compatibility, but token is now always read from localStorage
	setBearerToken(_bearerToken: string) {
		// No-op: token is now always read fresh from localStorage via the getter
	}

	async request<T, R extends ResponseType = ResponseType.JSON>(
		url: string,
		responseSchema?: ZodType<T>,
		options?: RequestOptions & { responseType?: R }
	): Promise<
		R extends ResponseType.JSON
			? T
			: R extends ResponseType.TEXT
				? string
				: R extends ResponseType.BLOB
					? Blob
					: R extends ResponseType.ARRAY_BUFFER
						? ArrayBuffer
						: unknown
	> {
		try {
			/**
			 * ----------
			 * REQUEST
			 * ----------
			 */
			const defaultOptions: RequestOptions = {
				headers: {
					Authorization: `Bearer ${this.bearerToken || ""}`,
				},
				method: "GET",
				responseType: ResponseType.JSON,
			};

			const mergedOptions: RequestOptions = {
				...defaultOptions,
				...(options ?? {}),
				headers: {
					...defaultOptions.headers,
					...(options?.headers ?? {}),
				},
			};

			// Validate the base URL
			if (!this.baseUrl) {
				throw new AppError("Base URL is not set.");
			}

			// Validate the bearer token
			const isNoAuthEndpoint =
				this.noAuthEndpoints.includes(url) ||
				this.noAuthPrefixes.some((prefix) => url.startsWith(prefix));
			if (!this.bearerToken && !isNoAuthEndpoint) {
				throw new AuthenticationError("You are not authenticated. Please login again.");
			}

			// Construct the full URL
			const fullUrl = new URL(url, this.baseUrl).toString();

			// Prepare fetch options
			const fetchOptions: RequestInit = {
				method: mergedOptions.method,
				headers: mergedOptions.headers,
				signal: mergedOptions.signal,
			};

			// Automatically stringify body if Content-Type is application/json and body is an object
			if (mergedOptions.body !== undefined) {
				const contentType = mergedOptions.headers?.["Content-Type"];
				if (contentType === "application/json" && typeof mergedOptions.body === "object") {
					fetchOptions.body = JSON.stringify(mergedOptions.body);
				} else {
					// Pass body as-is for other content types (e.g., form data, already stringified)
					fetchOptions.body = mergedOptions.body;
				}
			}

			let response: Response | null = null;
			let fallbackUrl: string | null = null;
			if (typeof window !== "undefined") {
				try {
					const backendUrl = new URL(fullUrl);
					const backendHost = backendUrl.hostname.toLocaleLowerCase();
					const frontendHost = window.location.hostname.toLocaleLowerCase();
					const localBackendHosts = new Set(["localhost", "127.0.0.1", "::1"]);
					const backendLooksLocal = localBackendHosts.has(backendHost);
					const frontendIsDifferentHost = !localBackendHosts.has(frontendHost);
					if (backendLooksLocal && frontendIsDifferentHost && url.startsWith("/")) {
						// Fallback for cloud/container setups where browser cannot reach localhost:PORT.
						fallbackUrl = url;
					}
				} catch {
					fallbackUrl = null;
				}
			}
			try {
				response = await fetch(fullUrl, fetchOptions);
			} catch (fetchError) {
				// Browsers throw TypeError for DNS/CORS/connection failures.
				if (!(fetchError instanceof TypeError)) {
					throw fetchError;
				}
				if (!fallbackUrl) {
					throw new NetworkError(
						`Could not reach backend (${fullUrl}). Check NEXT_PUBLIC_FASTAPI_BACKEND_URL, backend status, and CORS.`,
						0,
						"NETWORK_ERROR"
					);
				}
				try {
					response = await fetch(fallbackUrl, fetchOptions);
				} catch (fallbackError) {
					if (fallbackError instanceof TypeError) {
						throw new NetworkError(
							`Could not reach backend (${fullUrl}) and fallback (${fallbackUrl}). Check NEXT_PUBLIC_FASTAPI_BACKEND_URL, backend status, and CORS.`,
							0,
							"NETWORK_ERROR"
						);
					}
					throw fallbackError;
				}
			}
			if (!response) {
				throw new NetworkError(
					`Could not reach backend (${fullUrl}). Check NEXT_PUBLIC_FASTAPI_BACKEND_URL, backend status, and CORS.`,
					0,
					"NETWORK_ERROR"
				);
			}

			/**
			 * ----------
			 * RESPONSE
			 * ----------
			 */

			// Handle errors
			if (!response.ok) {
				// biome-ignore lint/suspicious: Unknown
				let data;

				try {
					data = await response.json();
				} catch (error) {
					console.error("Failed to parse response as JSON: ", JSON.stringify(error));
					throw new AppError("Failed to parse response", response.status, response.statusText);
				}

				// Handle 401 first before other error handling - ensures token is cleared and user redirected
				if (response.status === 401) {
					handleUnauthorized();
					throw new AuthenticationError(
						typeof data === "object" && data && "detail" in data
							? _formatApiErrorDetail(data.detail)
							: "You are not authenticated. Please login again.",
						response.status,
						response.statusText
					);
				}

				// For fastapi errors response
				if (typeof data === "object" && data && "detail" in data) {
					throw new AppError(
						_formatApiErrorDetail(data.detail),
						response.status,
						response.statusText
					);
				}

				switch (response.status) {
					case 403:
						throw new AuthorizationError(
							"You don't have permission to access this resource.",
							response.status,
							response.statusText
						);
					case 404:
						throw new NotFoundError("Resource not found", response.status, response.statusText);
					//  Add more cases as needed
					default:
						throw new AppError("Something went wrong", response.status, response.statusText);
				}
			}

			// biome-ignore lint/suspicious: Unknown
			let data;
			const responseType = mergedOptions.responseType;

			try {
				switch (responseType) {
					case ResponseType.JSON:
						data = await response.json();
						break;
					case ResponseType.TEXT:
						data = await response.text();
						break;
					case ResponseType.BLOB:
						data = await response.blob();
						break;
					case ResponseType.ARRAY_BUFFER:
						data = await response.arrayBuffer();
						break;
					//  Add more cases as needed
					default:
						data = await response.json();
				}
			} catch (error) {
				console.error("Failed to parse response as JSON:", error);
				throw new AppError("Failed to parse response", response.status, response.statusText);
			}

			// Validate response
			if (responseType === ResponseType.JSON) {
				if (!responseSchema) {
					return data;
				}
				const parsedData = responseSchema.safeParse(data);

				if (!parsedData.success) {
					/** The request was successful, but the response data does not match the expected schema.
					 * 	This is a client side error, and should be fixed by updating the responseSchema to keep things typed.
					 *  This error should not be shown to the user , it is for dev only.
					 */
					console.error(`Invalid API response schema - ${url} :`, JSON.stringify(parsedData.error));
				}

				return data;
			}

			return data;
		} catch (error) {
			console.error("Request failed:", error);
			if (error instanceof Error) {
				console.error("Request failed message:", error.message);
			}
			throw error;
		}
	}

	async get<T>(
		url: string,
		responseSchema?: ZodType<T>,
		options?: Omit<RequestOptions, "method" | "responseType">
	) {
		return this.request(url, responseSchema, {
			method: "GET",
			headers: {
				"Content-Type": "application/json",
			},
			...options,
			responseType: ResponseType.JSON,
		});
	}

	async post<T>(
		url: string,
		responseSchema?: ZodType<T>,
		options?: Omit<RequestOptions, "method" | "responseType">
	) {
		return this.request(url, responseSchema, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
			},
			...options,
			responseType: ResponseType.JSON,
		});
	}

	async put<T>(
		url: string,
		responseSchema?: ZodType<T>,
		options?: Omit<RequestOptions, "method" | "responseType">
	) {
		return this.request(url, responseSchema, {
			method: "PUT",
			headers: {
				"Content-Type": "application/json",
			},
			...options,
			responseType: ResponseType.JSON,
		});
	}

	async delete<T>(
		url: string,
		responseSchema?: ZodType<T>,
		options?: Omit<RequestOptions, "method" | "responseType">
	) {
		return this.request(url, responseSchema, {
			method: "DELETE",
			headers: {
				"Content-Type": "application/json",
			},
			...options,
			responseType: ResponseType.JSON,
		});
	}

	async patch<T>(
		url: string,
		responseSchema?: ZodType<T>,
		options?: Omit<RequestOptions, "method" | "responseType">
	) {
		return this.request(url, responseSchema, {
			method: "PATCH",
			headers: {
				"Content-Type": "application/json",
			},
			...options,
			responseType: ResponseType.JSON,
		});
	}

	async getBlob(url: string, options?: Omit<RequestOptions, "method" | "responseType">) {
		return this.request(url, undefined, {
			...options,
			method: "GET",
			responseType: ResponseType.BLOB,
		});
	}

	async postFormData<T>(
		url: string,
		responseSchema?: ZodType<T>,
		options?: Omit<RequestOptions, "method" | "responseType" | "body"> & { body: FormData }
	) {
		// Remove Content-Type from options headers if present
		const { "Content-Type": _, ...headersWithoutContentType } = options?.headers ?? {};

		return this.request(url, responseSchema, {
			method: "POST",
			...options,
			headers: {
				// Don't set Content-Type - let browser set it with multipart boundary
				Authorization: `Bearer ${this.bearerToken}`,
				...headersWithoutContentType,
			},
			responseType: ResponseType.JSON,
		});
	}
}

export const baseApiService = new BaseApiService(process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL || "");
