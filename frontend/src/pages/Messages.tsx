import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import Navbar from "@/components/landing/Navbar";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import apiClient from "@/api/client";
import { AccessDenied } from "@/components/common";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/AccountShell";
import { useActiveContext } from "@/contexts/ActiveContextContext";
import { messageKeys, useConversationMessages, useConversations, type ConversationItem, type MessageItem } from "@/hooks/use-messages";
import { organizationDeniedKey } from "@/lib/api-errors";
import { httpStatus } from "@/lib/errors";
import { formatClockTime } from "@/lib/format";
import { conversationBadge, filterConversations, isConversationNotFound, participantName, sendMessageErrorMessage } from "@/lib/messages";
import { Badge } from "@/components/ui/badge";
import { 
    MessageSquare, Send, Search,
    ArrowLeft, Package, Loader2, Clock
} from "lucide-react";

import { mediaUrl } from "@/lib/media";

const Messages = () => {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const queryClient = useQueryClient();
    const { active } = useActiveContext();
    // Messages d'une organisation : propriétaire et administrateurs (`message.reply`). Capacités inconnues : on ne masque rien.
    const canReply = !active.confirmed || active.capabilities.includes("message.reply");
    const conversationsQuery = useConversations(canReply);
    const conversations = conversationsQuery.data ?? [];
    const [activeConv, setActiveConv] = useState<ConversationItem | null>(null);
    const thread = useConversationMessages(activeConv?.id);
    const messages = thread.data ?? [];
    const [newMessage, setNewMessage] = useState("");
    const [isSending, setIsSending] = useState(false);
    const [search, setSearch] = useState("");
    const visibleConversations = filterConversations(conversations, search);
    const isLoading = conversationsQuery.isLoading;
    const scrollRef = useRef<HTMLDivElement>(null);

    // Changement de profil : la conversation ouverte appartient à l'ancienne boîte de messages
    useEffect(() => {
        setActiveConv(null);
        setSearch("");
    }, [active.type, active.id]);

    // Scroll to bottom when messages change
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, [thread.data]);

    const handleSendMessage = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!newMessage.trim() || !activeConv || isSending) return;

        setIsSending(true);
        try {
            const res = await apiClient.post<MessageItem>("interactions/messages/", {
                conversation: activeConv.id,
                content: newMessage
            });
            queryClient.setQueryData<MessageItem[]>(messageKeys.thread(activeConv.id), (previous) => [...(previous ?? []), res.data]);
            setNewMessage("");

            // Mettre à jour l'aperçu dans la liste des conversations
            queryClient.setQueryData<ConversationItem[]>(messageKeys.conversations, (previous) =>
                previous?.map((c) =>
                    c.id === activeConv.id
                        ? { ...c, last_message: { content: newMessage, created_at: res.data.created_at, is_read: false, sender_id: res.data.sender ?? undefined } }
                        : c,
                ),
            );
        } catch (error) {
            // 429 : « Trop de tentatives, réessayez dans N secondes » ; refus DENY_* : organisation suspendue, rôle retiré ; l'envoi n'est pas relancé
            toast.error(sendMessageErrorMessage(error, active.type === "ORGANIZATION"));
            if (isConversationNotFound(error)) {
                // Conversation retirée ou accès révoqué : on revient à la liste, rechargée
                setActiveConv(null);
                void conversationsQuery.refetch();
            }
        } finally {
            setIsSending(false);
        }
    };

    const deniedText = (error: unknown) => {
        const key = httpStatus(error) === 403 ? organizationDeniedKey(error) : null;
        return key ? t(key) : null;
    };
    const listErrorText = deniedText(conversationsQuery.error) ?? t("messages.errors.listLoad");
    const threadErrorText = deniedText(thread.error) ?? t("messages.errors.threadLoad");
    const activeBadge = activeConv ? conversationBadge(activeConv, active) : null;

    if (!canReply) {
        return (
            <RequireAuth>
                <AppShell withFooter={false}>
                    <AccessDenied description={t("scope.messagesDenied")} />
                </AppShell>
            </RequireAuth>
        );
    }

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <Loader2 role="status" aria-label={t("states.loading")} className="animate-spin text-primary h-10 w-10" />
            </div>
        );
    }

    return (
        <div className="h-screen flex flex-col bg-background">
            <Navbar />
            
            <main className="flex-1 container mx-auto px-4 pt-24 pb-6 overflow-hidden">
                <div className="bg-card border border-border rounded-3xl shadow-xl h-full flex overflow-hidden">
                    
                    {/* LISTE DES CONVERSATIONS */}
                    <div className={`w-full lg:w-[380px] border-r border-border flex flex-col ${activeConv ? 'hidden lg:flex' : 'flex'}`}>
                        <div className="p-6 border-b border-border">
                            <h1 className="text-xl font-bold flex items-center gap-2 mb-1">
                                <MessageSquare className="text-primary" aria-hidden /> {t("messages.title")}
                            </h1>
                            {active.type !== "USER" && <p className="mb-3 text-xs text-muted-foreground">{t("messages.inboxOf", { name: active.name })}</p>}
                            <div className={`relative ${active.type === "USER" ? "mt-3" : ""}`}>
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} aria-hidden />
                                <Input
                                    type="search"
                                    aria-label={t("messages.searchLabel")}
                                    placeholder={t("messages.searchPlaceholder")}
                                    value={search}
                                    onChange={(e) => setSearch(e.target.value)}
                                    className="pl-10 rounded-xl bg-muted/50 border-none"
                                />
                            </div>
                        </div>

                        <ScrollArea className="flex-1">
                            <ul aria-label={t("messages.listLabel")} className="p-2 space-y-1">
                                {visibleConversations.map((conv) => {
                                    const badge = conversationBadge(conv, active);
                                    const name = participantName(conv);
                                    return (
                                        <li key={conv.id}>
                                            <button
                                                type="button"
                                                onClick={() => setActiveConv(conv)}
                                                aria-current={activeConv?.id === conv.id ? "true" : undefined}
                                                className={`w-full text-left p-4 rounded-2xl cursor-pointer transition-all flex gap-4 items-center group ${
                                                    activeConv?.id === conv.id ? 'bg-primary/10' : 'hover:bg-muted/50'
                                                }`}
                                            >
                                                <div className="relative shrink-0">
                                                    {conv.other_participant?.photo ? (
                                                        <img
                                                            src={mediaUrl(conv.other_participant.photo)}
                                                            alt={t("messages.avatarAlt", { name })}
                                                            loading="lazy"
                                                            className="w-12 h-12 rounded-full object-cover"
                                                        />
                                                    ) : (
                                                        <div aria-hidden className="w-12 h-12 rounded-full bg-primary/5 flex items-center justify-center text-primary font-bold">
                                                            {name.charAt(0)}
                                                        </div>
                                                    )}
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex justify-between items-center mb-1 gap-2">
                                                        <span className="font-bold text-sm truncate">{name}</span>
                                                        <span className="text-[10px] text-muted-foreground shrink-0">
                                                            {conv.last_message && formatClockTime(conv.last_message.created_at)}
                                                        </span>
                                                    </div>
                                                    {badge && (
                                                        <Badge variant="outline" className="mb-1 max-w-full" data-testid="conversation-badge">
                                                            <span className="truncate">{badge.kind === "team" ? t("messages.badge.team", { name: badge.name }) : t(`messages.badge.${badge.kind}`)}</span>
                                                        </Badge>
                                                    )}
                                                    <p className="text-xs text-muted-foreground truncate font-medium">
                                                        {conv.post_title}
                                                    </p>
                                                    <p className="text-xs text-muted-foreground truncate mt-0.5">
                                                        {conv.last_message?.content || t("messages.startDiscussion")}
                                                    </p>
                                                </div>
                                            </button>
                                        </li>
                                    );
                                })}
                                {visibleConversations.length === 0 && conversationsQuery.isError && (
                                    <li role="alert" className="p-8 text-center text-muted-foreground list-none">
                                        <p className="text-sm">
                                            {listErrorText}
                                        </p>
                                        <Button variant="outline" className="mt-3" onClick={() => conversationsQuery.refetch()}>
                                            {t("states.retry")}
                                        </Button>
                                    </li>
                                )}
                                {visibleConversations.length === 0 && !conversationsQuery.isError && (
                                    <li className="p-8 text-center text-muted-foreground list-none">
                                        <MessageSquare className="mx-auto mb-2 opacity-20" size={40} aria-hidden />
                                        <p className="text-sm">{conversations.length === 0 ? t("messages.none") : t("messages.noMatch")}</p>
                                    </li>
                                )}
                            </ul>
                        </ScrollArea>
                    </div>

                    {/* ZONE DE CHAT */}
                    <div className={`flex-1 flex flex-col bg-muted/5 ${!activeConv ? 'hidden lg:flex' : 'flex'}`}>
                        {activeConv ? (
                            <>
                                {/* Header du Chat */}
                                <div className="p-4 border-b border-border bg-card flex items-center justify-between">
                                    <div className="flex items-center gap-4">
                                        <Button 
                                            variant="ghost" 
                                            size="icon" 
                                            className="lg:hidden" 
                                            onClick={() => setActiveConv(null)}
                                            aria-label={t("messages.back")}
                                        >
                                            <ArrowLeft size={20} aria-hidden />
                                        </Button>
                                        <div className="flex items-center gap-3">
                                            <div aria-hidden className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold">
                                                {participantName(activeConv).charAt(0)}
                                            </div>
                                            <div>
                                                <h2 className="font-bold text-sm">{participantName(activeConv)}</h2>
                                                <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                                                    <Package size={10} aria-hidden /> {activeConv.post_title}
                                                </div>
                                                {activeBadge && (
                                                    <Badge variant="outline" className="mt-1">
                                                        {activeBadge.kind === "team" ? t("messages.badge.team", { name: activeBadge.name }) : t(`messages.badge.${activeBadge.kind}`)}
                                                    </Badge>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Messages */}
                                {thread.isPaused && (
                                    <p role="status" className="bg-muted px-4 py-2 text-center text-xs text-muted-foreground">
                                        {t("auth.refreshPaused")}
                                    </p>
                                )}
                                {thread.isError && !thread.isPaused && (
                                    <div role="alert" className="flex items-center justify-between gap-3 bg-destructive/10 px-4 py-2 text-xs text-destructive">
                                        <span>{threadErrorText}</span>
                                        <Button size="sm" variant="outline" onClick={() => thread.refetch()}>
                                            {t("states.retry")}
                                        </Button>
                                    </div>
                                )}
                                <ScrollArea className="flex-1 p-6" aria-label={t("messages.threadLabel")}>
                                    <div className="space-y-6">
                                        {messages.map((msg) => {
                                            // `is_me` vient du serveur : moi, ou mon organisation quand je réponds en son nom
                                            const isMe = msg.is_me;
                                            return (
                                                <div key={msg.id} className={`flex ${isMe ? 'justify-end' : 'justify-start'}`}>
                                                    <div className={`max-w-[80%] flex flex-col ${isMe ? 'items-end' : 'items-start'}`}>
                                                        {(!isMe || msg.sender_context) && msg.sender_name && (
                                                            <span className="mb-1 text-[11px] font-semibold text-muted-foreground" data-testid="message-sender">
                                                                {msg.sender_name}
                                                            </span>
                                                        )}
                                                        <div className={`p-4 rounded-2xl text-sm shadow-sm ${
                                                            isMe 
                                                            ? 'bg-primary text-white rounded-tr-none' 
                                                            : 'bg-card border border-border rounded-tl-none'
                                                        }`}>
                                                            {msg.content}
                                                        </div>
                                                        <span className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1">
                                                            <Clock size={10} aria-hidden /> {formatClockTime(msg.created_at)}
                                                        </span>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                        <div ref={scrollRef} />
                                    </div>
                                </ScrollArea>

                                {/* Input */}
                                <div className="p-4 bg-card border-t border-border">
                                    <form onSubmit={handleSendMessage} className="flex gap-3">
                                        <Input 
                                            aria-label={t("messages.composerLabel")}
                                            placeholder={t("messages.composerPlaceholder")}
                                            className="flex-1 h-12 rounded-2xl bg-muted/50 border-none px-6 focus:ring-primary/20"
                                            value={newMessage}
                                            onChange={(e) => setNewMessage(e.target.value)}
                                            disabled={isSending}
                                        />
                                        <Button 
                                            type="submit" 
                                            className="h-12 w-12 rounded-2xl shadow-primary-glow"
                                            disabled={!newMessage.trim() || isSending}
                                            aria-label={t("messages.send")}
                                        >
                                            {isSending ? <Loader2 className="animate-spin" /> : <Send size={20} />}
                                        </Button>
                                    </form>
                                </div>
                            </>
                        ) : (
                            <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
                                <div className="w-20 h-20 rounded-full bg-primary/5 flex items-center justify-center text-primary mb-4">
                                    <MessageSquare size={40} />
                                </div>
                                <h2 className="text-xl font-bold">{t("messages.selectTitle")}</h2>
                                <p className="text-muted-foreground mt-2 max-w-xs">{t("messages.selectHint")}</p>
                            </div>
                        )}
                    </div>

                </div>
            </main>
        </div>
    );
};

export default Messages;
