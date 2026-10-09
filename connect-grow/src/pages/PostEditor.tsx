import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { Controller, useForm, type FieldPath } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, Loader2, Package, Rocket, Wrench } from "lucide-react";
import { toast } from "sonner";
import apiClient from "@/api/client";
import type { Currency, Post } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/AccountShell";
import { CommuneSelect } from "@/components/common/CommuneSelect";
import { ErrorState, PostCard } from "@/components/common";
import { errorProps, Field, FormAlert } from "@/components/auth/FormFields";
import { MAX_PHOTOS, PhotoPicker, photoSrc, type EditorPhoto } from "@/components/post-editor/PhotoPicker";
import { useAuth } from "@/contexts/AuthContext";
import { marketplaceKeys, useCategories, useCities, usePost } from "@/hooks/use-marketplace";
import { accountKeys } from "@/hooks/use-account";
import { categoryIcon } from "@/lib/category-icons";
import { mediaUrl } from "@/lib/media";
import { clearDraft, readDraft, writeDraft } from "@/lib/draft";
import { apiErrorMessage } from "@/lib/errors";
import { parseApiErrors } from "@/lib/validation";
import { cn } from "@/lib/utils";

// CDC 3.2 : règles de publication
const TITLE_MIN = 10;
const TITLE_MAX = 100;
const DESCRIPTION_MIN = 20;
const DESCRIPTION_MAX = 3000;

const schema = z
  .object({
    post_type: z.enum(["PRODUIT", "SERVICE"]),
    category: z.string().min(1, "Choisissez une catégorie."),
    title: z
      .string()
      .trim()
      .min(TITLE_MIN, `Au moins ${TITLE_MIN} caractères : soyez précis (marque, modèle…).`)
      .max(TITLE_MAX, `${TITLE_MAX} caractères maximum.`),
    description: z
      .string()
      .trim()
      .min(DESCRIPTION_MIN, `Au moins ${DESCRIPTION_MIN} caractères.`)
      .max(DESCRIPTION_MAX, `${DESCRIPTION_MAX} caractères maximum.`),
    condition: z.enum(["", "NEUF", "OCCASION", "RECONDITIONNE"]),
    stock: z.string(),
    price: z
      .string()
      .min(1, "Indiquez un prix.")
      .refine((v) => Number(v.replace(",", ".")) >= 0 && !Number.isNaN(Number(v.replace(",", "."))), "Prix invalide."),
    currency: z.enum(["USD", "CDF"]),
    is_price_negotiable: z.boolean(),
    is_exchangeable: z.boolean(),
    commune: z.string().min(1, "Choisissez la commune où se trouve l'article."),
  })
  .superRefine((values, ctx) => {
    if (values.post_type === "PRODUIT") {
      if (!values.condition) ctx.addIssue({ code: "custom", path: ["condition"], message: "Précisez l'état du produit." });
      const stock = Number(values.stock);
      if (!Number.isInteger(stock) || stock < 1) ctx.addIssue({ code: "custom", path: ["stock"], message: "Au moins 1." });
    }
  });

type FormValues = z.infer<typeof schema>;

const defaultValues: FormValues = {
  post_type: "PRODUIT",
  category: "",
  title: "",
  description: "",
  condition: "OCCASION",
  stock: "1",
  price: "",
  currency: "USD",
  is_price_negotiable: true,
  is_exchangeable: false,
  commune: "",
};

const steps: { title: string; fields: FieldPath<FormValues>[] }[] = [
  { title: "Photos", fields: [] },
  { title: "Description", fields: ["post_type", "category", "title", "description", "condition", "stock"] },
  { title: "Prix et lieu", fields: ["price", "currency", "commune"] },
  { title: "Aperçu", fields: [] },
];

/** Étape où corriger un champ refusé par le serveur. */
const stepOfField = (field: string) => {
  if (field === "main_image" || field === "images") return 0;
  const index = steps.findIndex((step) => step.fields.includes(field as FieldPath<FormValues>));
  return index === -1 ? 3 : index;
};

const conditions = [
  { value: "NEUF", label: "Neuf", hint: "Jamais utilisé, emballage d'origine" },
  { value: "OCCASION", label: "Occasion", hint: "Déjà utilisé, en bon état" },
  { value: "RECONDITIONNE", label: "Reconditionné", hint: "Remis à neuf par un professionnel" },
] as const;

function CharCount({ value, min, max }: { value: string; min: number; max: number }) {
  const length = value.trim().length;
  return (
    <span className={cn("tabular-nums", length > 0 && length < min ? "text-destructive" : "text-muted-foreground")}>
      {length}/{max}
    </span>
  );
}

function StepIndicator({ current, onSelect, maxReached }: { current: number; onSelect: (step: number) => void; maxReached: number }) {
  return (
    <ol className="flex items-center gap-2" aria-label="Étapes de la publication">
      {steps.map((step, index) => {
        const done = index < current;
        const active = index === current;
        const reachable = index <= maxReached;
        return (
          <li key={step.title} className="flex flex-1 items-center gap-2" aria-current={active ? "step" : undefined}>
            <button
              type="button"
              disabled={!reachable}
              onClick={() => onSelect(index)}
              className="flex min-w-0 items-center gap-2 disabled:cursor-default"
            >
              <span
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold transition-colors",
                  done ? "bg-success text-success-foreground" : active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
                )}
              >
                {done ? <Check className="h-4 w-4" aria-hidden /> : index + 1}
              </span>
              <span className={cn("hidden truncate text-sm font-semibold sm:inline", active ? "text-foreground" : "text-muted-foreground")}>
                {step.title}
              </span>
            </button>
            {index < steps.length - 1 && <span className={cn("h-0.5 flex-1 rounded-full", done ? "bg-success" : "bg-border")} aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}

/** Télécharge une photo déjà en ligne pour la renvoyer comme photo principale. */
async function fileFromUrl(url: string): Promise<File> {
  const response = await fetch(mediaUrl(url) ?? url);
  if (!response.ok) throw new Error("Téléchargement impossible");
  const blob = await response.blob();
  return new File([blob], url.split("/").pop() || "photo.webp", { type: blob.type });
}

function PostEditorForm({ post }: { post?: Post }) {
  const isEdit = !!post;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { data: categories = [] } = useCategories();
  const { data: cities = [] } = useCities();

  const originalPhotos = useMemo<EditorPhoto[]>(() => {
    if (!post) return [];
    const main: EditorPhoto[] = post.main_image ? [{ key: "main", kind: "existing", url: post.main_image, galleryId: null }] : [];
    const gallery: EditorPhoto[] = [...(post.images ?? [])]
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
      .map((img) => ({ key: `g-${img.id}`, kind: "existing", url: img.image, galleryId: img.id }));
    return [...main, ...gallery];
  }, [post]);

  const [step, setStep] = useState(0);
  const [maxReached, setMaxReached] = useState(isEdit ? steps.length - 1 : 0);
  const [photos, setPhotos] = useState<EditorPhoto[]>(originalPhotos);
  const [photoError, setPhotoError] = useState<string>();
  const [generalError, setGeneralError] = useState<string>();
  const [isSaving, setIsSaving] = useState(false);
  const topRef = useRef<HTMLDivElement>(null);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: post
      ? {
          post_type: post.post_type,
          category: post.category,
          title: post.title,
          description: post.description,
          condition: post.condition ?? "",
          stock: String(post.stock ?? 1),
          price: String(Number(post.price)),
          currency: post.currency ?? "USD",
          is_price_negotiable: post.is_price_negotiable ?? true,
          is_exchangeable: post.is_exchangeable ?? false,
          commune: post.commune,
        }
      : defaultValues,
    mode: "onTouched",
  });
  const { register, control, watch, trigger, setError, setValue, formState } = form;
  const errors = formState.errors;
  const values = watch();

  // Brouillon (création uniquement) : une coupure réseau ou un onglet fermé ne fait pas tout perdre
  useEffect(() => {
    if (isEdit) return;
    const draft = readDraft<Partial<FormValues>>(user?.id);
    if (draft && (draft.title || draft.description)) {
      form.reset({ ...defaultValues, ...draft });
      toast.info("Brouillon restauré", {
        description: "Vos photos sont à ajouter de nouveau.",
        action: { label: "Effacer", onClick: () => { clearDraft(); form.reset(defaultValues); } },
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restauration quand l'utilisateur est connu (une fois)
  }, [user?.id]);

  useEffect(() => {
    if (isEdit) return;
    const subscription = watch((draft) => {
      writeDraft(user?.id, draft);
    });
    return () => subscription.unsubscribe();
  }, [watch, isEdit, user?.id]);

  const goTo = (index: number) => {
    setStep(index);
    setMaxReached((max) => Math.max(max, index));
    topRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const next = async () => {
    if (step === 0 && photos.length === 0) {
      setPhotoError("Ajoutez au moins une photo : les annonces illustrées sont bien plus consultées.");
      return;
    }
    setPhotoError(undefined);
    const valid = await trigger(steps[step].fields, { shouldFocus: true });
    if (valid) goTo(step + 1);
  };

  const save = async () => {
    const valid = await trigger();
    if (!valid || photos.length === 0) {
      const firstInvalid = Object.keys(form.formState.errors)[0];
      goTo(photos.length === 0 ? 0 : stepOfField(firstInvalid ?? ""));
      return;
    }
    setGeneralError(undefined);
    setIsSaving(true);
    const v = form.getValues();

    const data = new FormData();
    data.append("post_type", v.post_type);
    data.append("category", v.category);
    data.append("title", v.title.trim());
    data.append("description", v.description.trim());
    data.append("price", String(Number(v.price.replace(",", "."))));
    data.append("currency", v.currency);
    data.append("is_price_negotiable", String(v.is_price_negotiable));
    data.append("is_exchangeable", String(v.is_exchangeable));
    data.append("commune", v.commune);
    if (v.post_type === "PRODUIT") {
      data.append("condition", v.condition);
      data.append("stock", v.stock);
    }

    try {
      // Photo principale : envoyée si nouvelle ou si l'ordre a changé
      const main = photos[0];
      const mainChanged = !isEdit || main.key !== originalPhotos[0]?.key;
      if (mainChanged) {
        const file = main.kind === "new" ? main.file : await fileFromUrl(main.url).catch(() => null);
        if (!file) {
          setGeneralError("Impossible de réutiliser cette photo comme principale. Ajoutez-la de nouveau depuis votre appareil.");
          goTo(0);
          return;
        }
        data.append("main_image", file);
      }

      const saved = isEdit
        ? (await apiClient.patch<Post>(`marketplace/posts/${post!.id}/`, data)).data
        : (await apiClient.post<Post>("marketplace/posts/", data)).data;

      // Galerie : suppression des photos retirées (ou devenues principales), puis ajout des nouvelles
      const keptGalleryIds = new Set(
        photos.slice(1).flatMap((p) => (p.kind === "existing" && p.galleryId !== null ? [p.galleryId] : [])),
      );
      const removed = originalPhotos.filter((p) => p.kind === "existing" && p.galleryId !== null && !keptGalleryIds.has(p.galleryId));
      await Promise.all(
        removed.map((p) =>
          apiClient.delete(`marketplace/posts/${saved.id}/images/`, { params: { image_id: p.kind === "existing" ? p.galleryId : undefined } }),
        ),
      );

      const newGalleryFiles = photos.slice(1).flatMap((p) => (p.kind === "new" ? [p.file] : []));
      let galleryFailed = false;
      let galleryMessage: string | undefined;
      if (newGalleryFiles.length > 0) {
        const gallery = new FormData();
        newGalleryFiles.forEach((file) => gallery.append("image", file));
        await apiClient.post(`marketplace/posts/${saved.id}/images/`, gallery).catch((galleryError) => {
          galleryFailed = true;
          galleryMessage = apiErrorMessage(galleryError, "");
        });
      }

      if (!isEdit) clearDraft();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: marketplaceKeys.all }),
        queryClient.invalidateQueries({ queryKey: accountKeys.dashboard }),
      ]);

      if (galleryFailed) {
        toast.warning("Annonce enregistrée, mais certaines photos n'ont pas pu être ajoutées.", { description: galleryMessage || undefined });
      }
      else toast.success(isEdit ? "Annonce mise à jour." : "Votre annonce est en ligne !");
      navigate(`/post/${saved.id}`, { replace: true });
    } catch (error) {
      const { fields, general } = parseApiErrors(error);
      const entries = Object.entries(fields);
      entries.forEach(([field, message]) => {
        if (field in defaultValues) setError(field as FieldPath<FormValues>, { message });
        if (field === "main_image") setPhotoError(message);
      });
      setGeneralError(general ?? (entries.length ? "Certaines informations sont à corriger." : "L'enregistrement a échoué. Réessayez."));
      if (entries.length) goTo(stepOfField(entries[0][0]));
    } finally {
      setIsSaving(false);
    }
  };

  const communeName = cities.flatMap((c) => c.communes).find((c) => c.id === values.commune)?.name;
  const previewPost: Post = {
    id: post?.id ?? "",
    seller: {
      id: user?.id ?? "",
      full_name: user?.full_name ?? "",
      photo: user?.photo,
      user_type: user?.user_type ?? "PARTICULIER",
      business_profile: user?.business_profile,
    },
    category: values.category,
    category_name: categories.find((c) => c.id === values.category)?.name,
    commune: values.commune,
    commune_name: communeName,
    post_type: values.post_type,
    title: values.title || "Titre de votre annonce",
    description: values.description,
    price: values.price.replace(",", ".") || "0",
    currency: values.currency as Currency,
    condition: values.post_type === "PRODUIT" && values.condition ? values.condition : null,
    is_price_negotiable: values.is_price_negotiable,
    is_exchangeable: values.is_exchangeable,
    main_image: photos[0] ? photoSrc(photos[0]) : null,
    views_count: post?.views_count ?? 0,
    likes_count: 0,
    created_at: post?.created_at ?? new Date().toISOString(),
  };

  const isLastStep = step === steps.length - 1;

  return (
    <div ref={topRef} className="mx-auto max-w-3xl scroll-mt-24">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-muted-foreground">{isEdit ? "Modification" : "Nouvelle annonce"}</p>
          <h1 className="text-2xl font-extrabold md:text-3xl">{steps[step].title}</h1>
        </div>
        <Button asChild variant="ghost" size="sm">
          <Link to={isEdit ? `/post/${post!.id}` : "/dashboard"}>Annuler</Link>
        </Button>
      </div>

      <StepIndicator current={step} onSelect={(index) => index <= maxReached && goTo(index)} maxReached={maxReached} />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (isLastStep) save();
          else next();
        }}
        noValidate
        className="mt-8 space-y-6"
      >
        {step === 0 && (
          <section className="space-y-4 rounded-2xl border bg-card p-5 shadow-soft sm:p-6">
            <p className="text-sm text-muted-foreground">
              La première photo apparaît dans les résultats. Montrez l'article en entier, puis les détails et les défauts éventuels.
            </p>
            <PhotoPicker
              photos={photos}
              onChange={(next) => {
                setPhotos(next);
                if (next.length) setPhotoError(undefined);
              }}
              error={photoError}
            />
          </section>
        )}

        {step === 1 && (
          <section className="space-y-6 rounded-2xl border bg-card p-5 shadow-soft sm:p-6">
            <fieldset>
              <legend className="mb-2 text-sm font-semibold">Vous proposez</legend>
              <div role="radiogroup" className="grid grid-cols-2 gap-3">
                {[
                  { value: "PRODUIT" as const, label: "Un produit", icon: Package },
                  { value: "SERVICE" as const, label: "Un service", icon: Wrench },
                ].map(({ value, label, icon: Icon }) => {
                  const selected = values.post_type === value;
                  return (
                    <button
                      key={value}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => setValue("post_type", value, { shouldValidate: true })}
                      className={cn(
                        "flex items-center gap-3 rounded-xl border-2 p-4 text-left font-semibold transition-colors",
                        selected ? "border-primary bg-primary/5 text-primary" : "border-border hover:border-primary/40",
                      )}
                    >
                      <Icon className="h-5 w-5" aria-hidden /> {label}
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <Field label="Catégorie" htmlFor="category" error={errors.category?.message}>
              <Controller
                control={control}
                name="category"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger id="category" className={cn("h-12 rounded-xl bg-card", errors.category && "border-destructive")} {...errorProps("category", errors.category?.message)}>
                      <SelectValue placeholder="Choisissez une catégorie" />
                    </SelectTrigger>
                    <SelectContent className="max-h-80 rounded-xl">
                      {categories.map((category) => {
                        const Icon = categoryIcon(category);
                        return (
                          <SelectItem key={category.id} value={category.id}>
                            <span className="flex items-center gap-2">
                              <Icon className="h-4 w-4 text-muted-foreground" aria-hidden /> {category.name}
                            </span>
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                )}
              />
            </Field>

            <Field
              label="Titre"
              htmlFor="title"
              error={errors.title?.message}
              aside={<CharCount value={values.title} min={TITLE_MIN} max={TITLE_MAX} />}
            >
              <Input
                id="title"
                maxLength={TITLE_MAX}
                placeholder={values.post_type === "SERVICE" ? "Ex. : Plombier, dépannage rapide 7j/7" : "Ex. : iPhone 13 Pro 256 Go, très bon état"}
                className="h-12 rounded-xl bg-card text-base"
                {...errorProps("title", errors.title?.message)}
                {...register("title")}
              />
            </Field>

            <Field
              label="Description"
              htmlFor="description"
              error={errors.description?.message}
              aside={<CharCount value={values.description} min={DESCRIPTION_MIN} max={DESCRIPTION_MAX} />}
              hint="Caractéristiques, état réel, accessoires fournis, disponibilité, lieu de remise…"
            >
              <Textarea
                id="description"
                maxLength={DESCRIPTION_MAX}
                className="min-h-[160px] rounded-xl bg-card text-base"
                {...errorProps("description", errors.description?.message)}
                {...register("description")}
              />
            </Field>

            {values.post_type === "PRODUIT" && (
              <>
                <fieldset>
                  <legend className="mb-2 text-sm font-semibold">État</legend>
                  <div role="radiogroup" className="grid gap-2 sm:grid-cols-3">
                    {conditions.map((condition) => {
                      const selected = values.condition === condition.value;
                      return (
                        <button
                          key={condition.value}
                          type="button"
                          role="radio"
                          aria-checked={selected}
                          onClick={() => setValue("condition", condition.value, { shouldValidate: true })}
                          className={cn(
                            "rounded-xl border-2 p-3 text-left transition-colors",
                            selected ? "border-primary bg-primary/5" : "border-border hover:border-primary/40",
                          )}
                        >
                          <span className="block text-sm font-bold">{condition.label}</span>
                          <span className="block text-xs text-muted-foreground">{condition.hint}</span>
                        </button>
                      );
                    })}
                  </div>
                  {errors.condition && (
                    <p role="alert" className="mt-2 text-sm font-medium text-destructive">
                      {errors.condition.message}
                    </p>
                  )}
                </fieldset>

                <Field label="Quantité disponible" htmlFor="stock" error={errors.stock?.message}>
                  <Input
                    id="stock"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    className="h-12 w-32 rounded-xl bg-card text-base"
                    {...errorProps("stock", errors.stock?.message)}
                    {...register("stock")}
                  />
                </Field>
              </>
            )}
          </section>
        )}

        {step === 2 && (
          <section className="space-y-6 rounded-2xl border bg-card p-5 shadow-soft sm:p-6">
            <Field label="Prix" htmlFor="price" error={errors.price?.message}>
              <div className="flex gap-2">
                <Input
                  id="price"
                  inputMode="decimal"
                  placeholder="0"
                  className="h-12 flex-1 rounded-xl bg-card font-display text-lg font-bold"
                  {...errorProps("price", errors.price?.message)}
                  {...register("price")}
                />
                <div role="radiogroup" aria-label="Devise" className="flex rounded-xl bg-muted p-1">
                  {(["USD", "CDF"] as const).map((currency) => (
                    <button
                      key={currency}
                      type="button"
                      role="radio"
                      aria-checked={values.currency === currency}
                      onClick={() => setValue("currency", currency)}
                      className={cn(
                        "rounded-lg px-4 text-sm font-bold transition-colors",
                        values.currency === currency ? "bg-card text-foreground shadow-soft" : "text-muted-foreground",
                      )}
                    >
                      {currency === "USD" ? "$ USD" : "FC CDF"}
                    </button>
                  ))}
                </div>
              </div>
            </Field>

            <div className="divide-y rounded-xl border">
              {[
                { name: "is_price_negotiable" as const, label: "Prix discutable", hint: "Les acheteurs peuvent vous faire une offre." },
                { name: "is_exchangeable" as const, label: "Ouvert au troc", hint: "Vous acceptez d'échanger contre un autre article." },
              ].map(({ name, label, hint }) => (
                <div key={name} className="flex items-center justify-between gap-4 p-4">
                  <Label htmlFor={name} className="cursor-pointer">
                    <span className="block text-sm font-semibold">{label}</span>
                    <span className="block text-xs font-normal text-muted-foreground">{hint}</span>
                  </Label>
                  <Controller
                    control={control}
                    name={name}
                    render={({ field }) => <Switch id={name} checked={field.value} onCheckedChange={field.onChange} />}
                  />
                </div>
              ))}
            </div>

            <Field label="Commune" htmlFor="commune" error={errors.commune?.message} hint="Seule la commune est affichée, jamais votre adresse.">
              <Controller
                control={control}
                name="commune"
                render={({ field }) => (
                  <CommuneSelect
                    id="commune"
                    value={field.value}
                    onChange={field.onChange}
                    allowAll={false}
                    placeholder="Choisissez une commune"
                    invalid={!!errors.commune}
                    className="h-12 rounded-xl bg-card"
                  />
                )}
              />
            </Field>
          </section>
        )}

        {step === 3 && (
          <section className="grid gap-6 md:grid-cols-[260px_1fr]">
            <div>
              <p className="mb-2 text-sm font-semibold">Dans les résultats</p>
              <PostCard post={previewPost} hideSeller={false} className="pointer-events-none" />
            </div>
            <div className="space-y-4 rounded-2xl border bg-card p-5 shadow-soft">
              <h2 className="font-bold">Récapitulatif</h2>
              <dl className="grid grid-cols-2 gap-3 text-sm">
                {[
                  ["Photos", `${photos.length}/${MAX_PHOTOS}`],
                  ["Catégorie", previewPost.category_name ?? "—"],
                  ["Type", values.post_type === "SERVICE" ? "Service" : "Produit"],
                  ["Commune", communeName ?? "—"],
                  ["Prix discutable", values.is_price_negotiable ? "Oui" : "Non"],
                  ["Troc", values.is_exchangeable ? "Accepté" : "Non"],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl bg-muted/60 p-3">
                    <dt className="text-xs text-muted-foreground">{label}</dt>
                    <dd className="mt-0.5 font-semibold">{value}</dd>
                  </div>
                ))}
              </dl>
              <p className="line-clamp-4 whitespace-pre-line text-sm text-muted-foreground">{values.description}</p>
              <p className="text-xs text-muted-foreground">
                En publiant, vous confirmez que l'article respecte la liste des produits interdits (médicaments, armes, contrefaçons…).
              </p>
            </div>
          </section>
        )}

        <FormAlert message={generalError} />

        {/* Navigation entre étapes : barre collante sur mobile */}
        <div className="fixed inset-x-0 bottom-0 z-40 flex gap-3 border-t bg-background/95 px-4 py-3 pb-safe backdrop-blur-lg md:static md:border-0 md:bg-transparent md:p-0">
          {step > 0 && (
            <Button type="button" variant="outline" size="lg" onClick={() => goTo(step - 1)} disabled={isSaving}>
              <ArrowLeft aria-hidden /> <span className="hidden sm:inline">Précédent</span>
            </Button>
          )}
          <Button type="submit" size="lg" className="flex-1 shadow-glow md:ml-auto md:flex-none md:px-8" disabled={isSaving}>
            {isSaving ? (
              <>
                <Loader2 className="animate-spin" aria-hidden /> Envoi en cours…
              </>
            ) : isLastStep ? (
              <>
                <Rocket aria-hidden /> {isEdit ? "Enregistrer les modifications" : "Publier l'annonce"}
              </>
            ) : (
              <>
                Continuer <ArrowRight aria-hidden />
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}

/** Publication (/create-post) et modification (/edit-post/:id) d'une annonce, en 4 étapes (CDC 3.2). */
const PostEditor = () => {
  const { id } = useParams();
  const { user } = useAuth();
  const { data: post, isLoading, isError, refetch } = usePost(id);

  let content: React.ReactNode;
  if (!id) content = <PostEditorForm />;
  else if (isLoading) content = <div className="flex justify-center py-24"><Loader2 className="h-8 w-8 animate-spin text-primary" aria-label="Chargement" /></div>;
  else if (isError || !post) content = <ErrorState onRetry={() => refetch()} />;
  else if (user && post.seller?.id !== user.id) content = <Navigate to={`/post/${post.id}`} replace />;
  else content = <PostEditorForm key={post.id} post={post} />;

  return (
    <RequireAuth>
      <AppShell withFooter={false}>{content}</AppShell>
    </RequireAuth>
  );
};

export default PostEditor;
