const withTrailingSlash = (url: string) => (url.endsWith("/") ? url : `${url}/`);

/** Base de l'API REST, ex. http://localhost:8000/api/ */
export const API_URL = withTrailingSlash(import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/");

/** Origine des médias servis par Django (ou le CDN en production), sans / final. */
export const MEDIA_BASE_URL = (import.meta.env.VITE_MEDIA_URL ?? new URL(API_URL).origin).replace(/\/$/, "");
