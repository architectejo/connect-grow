import { useState, type ImgHTMLAttributes } from "react";
import { ImageOff, type LucideIcon } from "lucide-react";
import { mediaUrl } from "@/lib/media";
import { cn } from "@/lib/utils";

interface ImageWithFallbackProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, "src"> {
  /** Chemin renvoyé par l'API (/media/...) ou URL absolue. */
  src?: string | null;
  fallbackIcon?: LucideIcon;
  fallbackLabel?: string;
  /** Classes du conteneur ; className s'applique à l'image. */
  wrapperClassName?: string;
}

/**
 * Image chargée en différé, avec fondu à l'apparition et repli si elle est absente ou cassée.
 * Le conteneur garde sa taille pendant le chargement : pas de saut de mise en page.
 */
export function ImageWithFallback({
  src,
  alt,
  fallbackIcon: FallbackIcon = ImageOff,
  fallbackLabel,
  className,
  wrapperClassName,
  ...props
}: ImageWithFallbackProps) {
  const [status, setStatus] = useState<"loading" | "loaded" | "error">("loading");
  const url = mediaUrl(src);

  return (
    <div className={cn("relative overflow-hidden bg-muted", wrapperClassName)}>
      {url && status !== "error" ? (
        <img
          src={url}
          alt={alt}
          loading="lazy"
          decoding="async"
          onLoad={() => setStatus("loaded")}
          onError={() => setStatus("error")}
          className={cn(
            "h-full w-full object-cover transition-opacity duration-500",
            status === "loaded" ? "opacity-100" : "opacity-0",
            className,
          )}
          {...props}
        />
      ) : (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 text-muted-foreground/60">
          <FallbackIcon className="h-8 w-8" aria-hidden />
          {fallbackLabel && <span className="text-xs font-medium">{fallbackLabel}</span>}
        </div>
      )}
    </div>
  );
}
