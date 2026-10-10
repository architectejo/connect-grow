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
import { useAuth } from "@/contexts/AuthContext";
import { messageKeys, useConversationMessages, useConversations, type ConversationItem, type MessageItem } from "@/hooks/use-messages";
import { apiErrorMessage } from "@/lib/errors";
import { formatClockTime } from "@/lib/format";
import { 
    MessageSquare, Send, Search, User as UserIcon, 
    ArrowLeft, MoreVertical, Package, Loader2, Clock
} from "lucide-react";

import { mediaUrl } from "@/lib/media";

const Messages = () => {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const queryClient = useQueryClient();
    const { user } = useAuth();
    const conversationsQuery = useConversations();
    const conversations = conversationsQuery.data ?? [];
    const [activeConv, setActiveConv] = useState<ConversationItem | null>(null);
    const thread = useConversationMessages(activeConv?.id);
    const messages = thread.data ?? [];
    const [newMessage, setNewMessage] = useState("");
    const [isSending, setIsSending] = useState(false);
    const userData = user;
    const isLoading = conversationsQuery.isLoading;
    const scrollRef = useRef<HTMLDivElement>(null);

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
                previous?.map((c) => (c.id === activeConv.id ? { ...c, last_message: { content: newMessage, created_at: new Date() } } : c)),
            );
        } catch (error) {
            // 429 : « Trop de tentatives, réessayez dans N secondes » ; l'envoi n'est pas relancé
            toast.error(apiErrorMessage(error, "Le message n'a pas pu être envoyé."));
        } finally {
            setIsSending(false);
        }
    };

    if (isLoading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <Loader2 className="animate-spin text-primary h-10 w-10" />
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
                            <h2 className="text-xl font-bold flex items-center gap-2 mb-4">
                                <MessageSquare className="text-primary" /> Messages
                            </h2>
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} />
                                <Input placeholder="Rechercher..." className="pl-10 rounded-xl bg-muted/50 border-none" />
                            </div>
                        </div>

                        <ScrollArea className="flex-1">
                            <div className="p-2 space-y-1">
                                {conversations.length > 0 ? (
                                    conversations.map((conv) => (
                                        <div 
                                            key={conv.id}
                                            onClick={() => setActiveConv(conv)}
                                            className={`p-4 rounded-2xl cursor-pointer transition-all flex gap-4 items-center group ${
                                                activeConv?.id === conv.id ? 'bg-primary/10' : 'hover:bg-muted/50'
                                            }`}
                                        >
                                            <div className="relative">
                                                {conv.other_participant?.photo ? (
                                                    <img src={mediaUrl(conv.other_participant.photo)} className="w-12 h-12 rounded-full object-cover" />
                                                ) : (
                                                    <div className="w-12 h-12 rounded-full bg-primary/5 flex items-center justify-center text-primary font-bold">
                                                        {conv.other_participant?.full_name?.charAt(0)}
                                                    </div>
                                                )}
                                                <div className="absolute bottom-0 right-0 w-3 h-3 bg-green-500 border-2 border-card rounded-full" />
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex justify-between items-center mb-1">
                                                    <span className="font-bold text-sm truncate">{conv.other_participant?.full_name}</span>
                                                    <span className="text-[10px] text-muted-foreground">
                                                        {conv.last_message && formatClockTime(conv.last_message.created_at)}
                                                    </span>
                                                </div>
                                                <p className="text-xs text-muted-foreground truncate font-medium">
                                                    {conv.post_title}
                                                </p>
                                                <p className="text-xs text-muted-foreground truncate mt-0.5">
                                                    {conv.last_message?.content || "Commencer la discussion..."}
                                                </p>
                                            </div>
                                        </div>
                                    ))
                                ) : conversationsQuery.isError ? (
                                    <div role="alert" className="p-8 text-center text-muted-foreground">
                                        <p className="text-sm">{t("states.errorTitle")}</p>
                                        <Button variant="outline" className="mt-3" onClick={() => conversationsQuery.refetch()}>
                                            {t("states.retry")}
                                        </Button>
                                    </div>
                                ) : (
                                    <div className="p-8 text-center text-muted-foreground">
                                        <MessageSquare className="mx-auto mb-2 opacity-20" size={40} />
                                        <p className="text-sm">Aucune conversation</p>
                                    </div>
                                )}
                            </div>
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
                                        >
                                            <ArrowLeft size={20} />
                                        </Button>
                                        <div className="flex items-center gap-3">
                                            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold">
                                                {activeConv.other_participant?.full_name?.charAt(0)}
                                            </div>
                                            <div>
                                                <h3 className="font-bold text-sm">{activeConv.other_participant?.full_name}</h3>
                                                <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                                                    <Package size={10} /> {activeConv.post_title}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                    <Button variant="ghost" size="icon"><MoreVertical size={20} /></Button>
                                </div>

                                {/* Messages */}
                                {thread.isPaused && (
                                    <p role="status" className="bg-muted px-4 py-2 text-center text-xs text-muted-foreground">
                                        {t("auth.refreshPaused")}
                                    </p>
                                )}
                                <ScrollArea className="flex-1 p-6">
                                    <div className="space-y-6">
                                        {messages.map((msg, idx) => {
                                            const isMe = msg.sender === userData?.id;
                                            return (
                                                <div key={msg.id} className={`flex ${isMe ? 'justify-end' : 'justify-start'}`}>
                                                    <div className={`max-w-[80%] flex flex-col ${isMe ? 'items-end' : 'items-start'}`}>
                                                        <div className={`p-4 rounded-2xl text-sm shadow-sm ${
                                                            isMe 
                                                            ? 'bg-primary text-white rounded-tr-none' 
                                                            : 'bg-card border border-border rounded-tl-none'
                                                        }`}>
                                                            {msg.content}
                                                        </div>
                                                        <span className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1">
                                                            <Clock size={10} /> {formatClockTime(msg.created_at)}
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
                                            placeholder="Tapez votre message..." 
                                            className="flex-1 h-12 rounded-2xl bg-muted/50 border-none px-6 focus:ring-primary/20"
                                            value={newMessage}
                                            onChange={(e) => setNewMessage(e.target.value)}
                                            disabled={isSending}
                                        />
                                        <Button 
                                            type="submit" 
                                            className="h-12 w-12 rounded-2xl shadow-primary-glow"
                                            disabled={!newMessage.trim() || isSending}
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
                                <h3 className="text-xl font-bold">Vos conversations</h3>
                                <p className="text-muted-foreground mt-2 max-w-xs">
                                    Sélectionnez une discussion à gauche pour commencer à discuter avec d'autres membres.
                                </p>
                            </div>
                        )}
                    </div>

                </div>
            </main>
        </div>
    );
};

export default Messages;
