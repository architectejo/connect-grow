// Préparation des photos avant envoi (CDC 4.2 et 4.5) : redimensionnement, conversion WebP
// et suppression des métadonnées (dont la géolocalisation), puisque le canvas ne les recopie pas.

const MAX_DIMENSION = 1600;
const QUALITY = 0.8;
// HEIC exclu : les navigateurs Android ne savent pas le décoder, donc ni le compresser ni l'afficher
export const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const MAX_SOURCE_SIZE = 15 * 1024 * 1024;

function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Image illisible"));
    };
    img.src = url;
  });
}

const toBlob = (canvas: HTMLCanvasElement, type: string) =>
  new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, type, QUALITY));

/** Renvoie une version compressée de la photo ; en cas d'échec, le fichier d'origine. */
export async function compressImage(file: File): Promise<File> {
  try {
    const img = await loadImage(file);
    const scale = Math.min(1, MAX_DIMENSION / Math.max(img.naturalWidth, img.naturalHeight));
    const width = Math.round(img.naturalWidth * scale);
    const height = Math.round(img.naturalHeight * scale);

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) return file;
    context.drawImage(img, 0, 0, width, height);

    // WebP si le navigateur sait l'encoder, sinon JPEG (anciens Safari)
    let blob = await toBlob(canvas, "image/webp");
    let extension = "webp";
    if (!blob || blob.type !== "image/webp") {
      blob = await toBlob(canvas, "image/jpeg");
      extension = "jpg";
    }
    if (!blob || blob.size >= file.size) return file;

    const baseName = file.name.replace(/\.[^.]+$/, "") || "photo";
    return new File([blob], `${baseName}.${extension}`, { type: blob.type, lastModified: Date.now() });
  } catch {
    return file;
  }
}

/** « 1 234 567 » octets → « 1,2 Mo ». */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} Ko`;
  return `${(bytes / (1024 * 1024)).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mo`;
}
