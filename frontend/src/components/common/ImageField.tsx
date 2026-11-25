import { useEffect, useRef, type ReactNode } from "react";
import { Camera } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { compressImage } from "@/lib/image";
import { UserAvatar } from "./UserAvatar";

interface ImageFieldProps {
  label: string;
  src?: string | null;
  name?: string;
  shape: "circle" | "square";
  onSelect: (file: File, preview: string) => void;
  /** Action secondaire (ex. « Retirer le logo »). */
  extra?: ReactNode;
  disabled?: boolean;
}

/** Choix d'image (photo, logo) avec aperçu local, compression avant envoi et libération de l'aperçu. */
export function ImageField({ label, src, name, shape, onSelect, extra, disabled }: ImageFieldProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const previews = useRef<string[]>([]);

  // Les aperçus (URL d'objet) sont libérés au démontage
  useEffect(
    () => () => {
      previews.current.forEach((url) => URL.revokeObjectURL(url));
      previews.current = [];
    },
    [],
  );

  return (
    <div className="flex items-center gap-4">
      <UserAvatar src={src} name={name} size="xl" shape={shape} />
      <div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" disabled={disabled} onClick={() => inputRef.current?.click()}>
            <Camera aria-hidden /> {label}
          </Button>
          {extra}
        </div>
        <p className="mt-1.5 text-xs text-muted-foreground">{t("imageField.hint")}</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="sr-only"
        tabIndex={-1}
        aria-label={label}
        onChange={async (e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          const compressed = await compressImage(file);
          const preview = URL.createObjectURL(compressed);
          previews.current.push(preview);
          onSelect(compressed, preview);
        }}
      />
    </div>
  );
}
