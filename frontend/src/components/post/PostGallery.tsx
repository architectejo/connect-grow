import { useCallback, useEffect, useState } from "react";
import useEmblaCarousel from "embla-carousel-react";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight, Expand, Package } from "lucide-react";
import type { Post } from "@/api/types";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { ImageWithFallback } from "@/components/common/ImageWithFallback";
import { mediaUrl } from "@/lib/media";
import { cn } from "@/lib/utils";

/** Photo principale puis photos de la galerie, dans l'ordre (CDC 3.2 : 1 à 8 photos). */
export function postPhotos(post: Post): string[] {
  const gallery = [...(post.images ?? [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0)).map((img) => img.image);
  return [post.main_image, ...gallery].filter((src): src is string => !!src);
}

function useCarousel(startIndex = 0) {
  const [emblaRef, emblaApi] = useEmblaCarousel({ startIndex });
  const [selected, setSelected] = useState(startIndex);

  useEffect(() => {
    if (!emblaApi) return;
    const onSelect = () => setSelected(emblaApi.selectedScrollSnap());
    onSelect();
    emblaApi.on("select", onSelect).on("reInit", onSelect);
    return () => {
      emblaApi.off("select", onSelect).off("reInit", onSelect);
    };
  }, [emblaApi]);

  return { emblaRef, emblaApi, selected };
}

const NavButton = ({ direction, onClick, className }: { direction: "prev" | "next"; onClick: () => void; className?: string }) => {
  const { t } = useTranslation();
  const Icon = direction === "prev" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={direction === "prev" ? t("post.gallery.previous") : t("post.gallery.next")}
      className={cn(
        "absolute top-1/2 z-10 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-background/90 text-foreground shadow-card backdrop-blur-sm transition-transform hover:scale-105",
        direction === "prev" ? "left-3" : "right-3",
        className,
      )}
    >
      <Icon className="h-5 w-5" />
    </button>
  );
};

/** Visionneuse plein écran. */
function Lightbox({ photos, title, startIndex, onClose }: { photos: string[]; title: string; startIndex: number; onClose: () => void }) {
  const { t } = useTranslation();
  const { emblaRef, emblaApi, selected } = useCarousel(startIndex);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl border-0 bg-black p-0 text-white sm:rounded-2xl [&>button]:text-white">
        <DialogTitle className="sr-only">{title}</DialogTitle>
        <div className="relative">
          <div className="overflow-hidden" ref={emblaRef}>
            <div className="flex">
              {photos.map((src, i) => (
                <div key={src} className="min-w-0 flex-[0_0_100%]">
                  <img
                    src={mediaUrl(src)}
                    alt={t("post.gallery.photoAlt", { title, n: i + 1 })}
                    className="mx-auto h-[80vh] w-full object-contain"
                  />
                </div>
              ))}
            </div>
          </div>
          {photos.length > 1 && (
            <>
              <NavButton direction="prev" onClick={() => emblaApi?.scrollPrev()} />
              <NavButton direction="next" onClick={() => emblaApi?.scrollNext()} />
              <p className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-white/15 px-3 py-1 text-xs font-semibold tabular-nums">
                {selected + 1} / {photos.length}
              </p>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface PostGalleryProps {
  post: Post;
  className?: string;
}

export function PostGallery({ post, className }: PostGalleryProps) {
  const { t } = useTranslation();
  const photos = postPhotos(post);
  const { emblaRef, emblaApi, selected } = useCarousel();
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const scrollTo = useCallback((index: number) => emblaApi?.scrollTo(index), [emblaApi]);

  if (photos.length === 0) {
    return (
      <ImageWithFallback
        src={null}
        alt={post.title}
        fallbackIcon={Package}
        fallbackLabel={t("post.noImage")}
        wrapperClassName={cn("aspect-[4/3] rounded-2xl border", className)}
      />
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      <div className="group relative overflow-hidden rounded-2xl border bg-muted">
        <div className="overflow-hidden" ref={emblaRef}>
          <div className="flex">
            {photos.map((src, i) => (
              <button
                key={src}
                type="button"
                onClick={() => setLightboxIndex(i)}
                className="relative min-w-0 flex-[0_0_100%] cursor-zoom-in"
                aria-label={t("post.gallery.enlargePhoto", { n: i + 1 })}
              >
                <ImageWithFallback
                  src={src}
                  alt={t("post.gallery.photoAlt", { title: post.title, n: i + 1 })}
                  wrapperClassName="aspect-[4/3]"
                  className="object-contain"
                  // Première photo prioritaire : c'est l'élément principal de la page
                  loading={i === 0 ? "eager" : "lazy"}
                />
              </button>
            ))}
          </div>
        </div>

        {photos.length > 1 && (
          <>
            <NavButton direction="prev" onClick={() => emblaApi?.scrollPrev()} className="hidden opacity-0 transition-opacity group-hover:opacity-100 md:flex" />
            <NavButton direction="next" onClick={() => emblaApi?.scrollNext()} className="hidden opacity-0 transition-opacity group-hover:opacity-100 md:flex" />
            {/* Points de position sur mobile */}
            <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 gap-1.5 md:hidden" aria-hidden>
              {photos.map((src, i) => (
                <span
                  key={src}
                  className={cn("h-1.5 rounded-full bg-white/70 shadow transition-all", i === selected ? "w-5 bg-white" : "w-1.5")}
                />
              ))}
            </div>
          </>
        )}

        <span className="pointer-events-none absolute right-3 top-3 flex items-center gap-1.5 rounded-full bg-foreground/70 px-2.5 py-1 text-xs font-semibold text-background backdrop-blur-sm">
          <Expand className="h-3.5 w-3.5" aria-hidden />
          {photos.length > 1 ? `${selected + 1} / ${photos.length}` : t("post.gallery.enlarge")}
        </span>
      </div>

      {photos.length > 1 && (
        <div className="hidden gap-2 overflow-x-auto scrollbar-none md:flex">
          {photos.map((src, i) => (
            <button
              key={src}
              type="button"
              onClick={() => scrollTo(i)}
              aria-label={t("post.gallery.viewPhoto", { n: i + 1 })}
              aria-current={i === selected}
              className={cn(
                "shrink-0 overflow-hidden rounded-xl border-2 transition-all",
                i === selected ? "border-primary" : "border-transparent opacity-70 hover:opacity-100",
              )}
            >
              <ImageWithFallback src={src} alt="" wrapperClassName="h-16 w-20" />
            </button>
          ))}
        </div>
      )}

      {lightboxIndex !== null && (
        <Lightbox photos={photos} title={post.title} startIndex={lightboxIndex} onClose={() => setLightboxIndex(null)} />
      )}
    </div>
  );
}
