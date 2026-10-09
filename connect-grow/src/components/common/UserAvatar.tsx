import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { initials } from "@/lib/format";
import { mediaUrl } from "@/lib/media";
import { cn } from "@/lib/utils";

const sizes = {
  xs: "h-7 w-7 text-[10px]",
  sm: "h-9 w-9 text-xs",
  md: "h-12 w-12 text-sm",
  lg: "h-16 w-16 text-lg",
  xl: "h-24 w-24 text-2xl",
} as const;

interface UserAvatarProps {
  src?: string | null;
  name?: string | null;
  size?: keyof typeof sizes;
  /** Carré arrondi pour les logos de boutique, rond pour les personnes. */
  shape?: "circle" | "square";
  className?: string;
}

export function UserAvatar({ src, name, size = "sm", shape = "circle", className }: UserAvatarProps) {
  const radius = shape === "square" ? "rounded-xl" : "rounded-full";
  return (
    <Avatar className={cn(sizes[size], radius, "ring-2 ring-background", className)}>
      <AvatarImage src={mediaUrl(src)} alt={name ?? ""} className="object-cover" />
      <AvatarFallback className={cn(radius, "bg-primary/10 font-bold text-primary")}>{initials(name)}</AvatarFallback>
    </Avatar>
  );
}
