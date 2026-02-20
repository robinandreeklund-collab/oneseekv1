export class AppError extends Error {
	status?: number;
	statusText?: string;
	details?: unknown;
	constructor(message: string, status?: number, statusText?: string, details?: unknown) {
		super(message);
		this.name = this.constructor.name; // User friendly
		this.status = status;
		this.statusText = statusText; // Dev friendly
		this.details = details;
	}
}

export class NetworkError extends AppError {
	constructor(message: string, status?: number, statusText?: string, details?: unknown) {
		super(message, status, statusText, details);
	}
}

export class ValidationError extends AppError {
	constructor(message: string, status?: number, statusText?: string, details?: unknown) {
		super(message, status, statusText, details);
	}
}

export class AuthenticationError extends AppError {
	constructor(message: string, status?: number, statusText?: string, details?: unknown) {
		super(message, status, statusText, details);
	}
}

export class AuthorizationError extends AppError {
	constructor(message: string, status?: number, statusText?: string, details?: unknown) {
		super(message, status, statusText, details);
	}
}

export class NotFoundError extends AppError {
	constructor(message: string, status?: number, statusText?: string, details?: unknown) {
		super(message, status, statusText, details);
	}
}
