import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Camera, ImagePlus, Loader2, Star, X } from "lucide-react";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import type { Uuid } from "@/api/types";
import { mediaUrl } from "@/lib/media";
import { ACCEPTED_IMAGE_TYPES, compressImage, MAX_SOURCE_SIZE } from "@/lib/image";
import { cn } from "@/lib/utils";

// CDC 3.2 : de 1 à 8 photos par annonce
export const MAX_PHOTOS = 8;

/** Photo déjà en ligne (principale ou de galerie) ou nouvelle photo choisie sur l'appareil. */
export type EditorPhoto =
  | { key: string; kind: "existing"; url: string; galleryId: Uuid | null }
  | { key: string; kind: "new"; file: File; preview: string };

export const photoSrc = (photo: EditorPhoto) => (photo.kind === "new" ? photo.preview : mediaUrl(photo.url) ?? "");

let counter = 0;
const newKey = () => `new-${Date.now()}-${counter++}`;

interface PhotoPickerProps {
  photos: EditorPhoto[];
  onChange: (photos: EditorPhoto[]) => void;
  error?: string;
}

export function PhotoPicker({ photos, onChange, error }: PhotoPickerProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [processing, setProcessing] = useState(0);
  const [dragging, setDragging] = useState(false);
  const photosRef = useRef(photos);
  photosRef.current = photos;

  // Libère les aperçus locaux quand le composant disparaît
  useEffect(
    () => () => photosRef.current.forEach((p) => p.kind === "new" && URL.revokeObjectURL(p.preview)),
    [],
  );

  const addFiles = async (fileList: FileList | File[]) => {
    const files = Array.from(fileList);
    const room = MAX_PHOTOS - photos.length;
    if (room <= 0) {
      toast.error(t("photos.max", { max: MAX_PHOTOS }));
      return;
    }
    const accepted = files.filter((file) => {
      if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) {
        toast.error(t("photos.badType", { name: file.name }));
        return false;
      }
      if (file.size > MAX_SOURCE_SIZE) {
        toast.error(t("photos.tooHeavy", { name: file.name, size: MAX_SOURCE_SIZE / (1024 * 1024) }));
        return false;
      }
      return true;
    });
    if (accepted.length > room) toast.info(t("photos.partial", { room, max: MAX_PHOTOS }));
    const toProcess = accepted.slice(0, room);
    if (toProcess.length === 0) return;

    setProcessing(toProcess.length);
    const compressed = await Promise.all(toProcess.map((file) => compressImage(file)));
    setProcessing(0);
    onChange([
      ...photosRef.current,
      ...compressed.map((file) => ({ key: newKey(), kind: "new" as const, file, preview: URL.createObjectURL(file) })),
    ]);
  };

  const remove = (key: string) => {
    const photo = photos.find((p) => p.key === key);
    if (photo?.kind === "new") URL.revokeObjectURL(photo.preview);
    onChange(photos.filter((p) => p.key !== key));
  };

  const move = (index: number, to: number) => {
    if (to < 0 || to >= photos.length) return;
    const next = [...photos];
    const [item] = next.splice(index, 1);
    next.splice(to, 0, item);
    onChange(next);
  };

  const canAdd = photos.length + processing < MAX_PHOTOS;

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(e.dataTransfer.files);
        }}
        className={cn(
          "grid grid-cols-2 gap-3 rounded-2xl sm:grid-cols-3 md:grid-cols-4",
          dragging && "ring-2 ring-primary ring-offset-4 ring-offset-background",
        )}
      >
        {photos.map((photo, index) => (
          <figure
            key={photo.key}
            className={cn(
              "group relative overflow-hidden rounded-xl border bg-muted",
              index === 0 ? "col-span-2 row-span-2 aspect-square sm:aspect-auto" : "aspect-square",
            )}
          >
            <img src={photoSrc(photo)} alt={t("photos.alt", { n: index + 1 })} className="h-full w-full object-cover" />
            {index === 0 && (
              <figcaption className="absolute left-2 top-2 flex items-center gap-1 rounded-full bg-foreground/80 px-2.5 py-1 text-xs font-semibold text-background backdrop-blur-sm">
                <Star className="h-3 w-3 fill-current" aria-hidden /> {t("photos.main")}
              </figcaption>
            )}
            <button
              type="button"
              onClick={() => remove(photo.key)}
              className="absolute right-2 top-2 flex h-8 w-8 items-center justify-center rounded-full bg-background/90 text-foreground shadow-soft backdrop-blur-sm transition-colors hover:bg-destructive hover:text-destructive-foreground"
              aria-label={t("photos.remove", { n: index + 1 })}
            >
              <X className="h-4 w-4" />
            </button>
            {photos.length > 1 && (
              <div className="absolute inset-x-2 bottom-2 flex justify-between gap-1">
                <div className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => move(index, index - 1)}
                    disabled={index === 0}
                    className="flex h-8 w-8 items-center justify-center rounded-full bg-background/90 shadow-soft backdrop-blur-sm disabled:opacity-0"
                    aria-label={t("photos.moveLeft", { n: index + 1 })}
                  >
                    <ArrowLeft className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => move(index, index + 1)}
                    disabled={index === photos.length - 1}
                    className="flex h-8 w-8 items-center justify-center rounded-full bg-background/90 shadow-soft backdrop-blur-sm disabled:opacity-0"
                    aria-label={t("photos.moveRight", { n: index + 1 })}
                  >
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </div>
                {index > 0 && (
                  <button
                    type="button"
                    onClick={() => move(index, 0)}
                    className="rounded-full bg-background/90 px-2.5 text-xs font-semibold shadow-soft backdrop-blur-sm"
                  >
                    {t("photos.makeMain")}
                  </button>
                )}
              </div>
            )}
          </figure>
        ))}

        {Array.from({ length: processing }, (_, i) => (
          <div key={`processing-${i}`} className="flex aspect-square flex-col items-center justify-center gap-2 rounded-xl border bg-muted text-xs text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
            {t("photos.optimizing")}
          </div>
        ))}

        {canAdd && (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className={cn(
              "flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-primary/30 bg-primary/5 p-4 text-center text-primary transition-colors hover:bg-primary/10",
              photos.length === 0 ? "col-span-2 aspect-[2/1] sm:col-span-3 md:col-span-4 md:aspect-[3/1]" : "aspect-square",
            )}
          >
            {photos.length === 0 ? <Camera className="h-8 w-8" aria-hidden /> : <ImagePlus className="h-6 w-6" aria-hidden />}
            <span className="text-sm font-semibold">{photos.length === 0 ? t("photos.addFirst") : t("photos.add")}</span>
            {photos.length === 0 && (
              <span className="text-xs text-primary/70">{t("photos.addHint", { max: MAX_PHOTOS })}</span>
            )}
          </button>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_IMAGE_TYPES.join(",")}
        multiple
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => {
          if (e.target.files) addFiles(e.target.files);
          e.target.value = "";
        }}
      />

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {t("photos.count", { current: photos.length, max: MAX_PHOTOS })}
        </span>
      </div>
      {error && (
        <p role="alert" className="text-sm font-medium text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
