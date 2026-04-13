import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Mail, Lock, Eye, EyeOff, User, Building2 } from "lucide-react";

type UserType = "particulier" | "entreprise";

const Register = () => {
  const [showPassword, setShowPassword] = useState(false);
  const [userType, setUserType] = useState<UserType>("particulier");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // TODO: integrate with Lovable Cloud auth
  };

  return (
    <div className="min-h-screen flex">
      <div className="hidden lg:flex flex-1 gradient-hero items-center justify-center p-12">
        <div className="max-w-md space-y-6">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg gradient-primary flex items-center justify-center">
              <span className="text-primary-foreground font-bold">C+</span>
            </div>
            <span className="text-2xl font-bold text-primary-foreground">Connecte<span className="text-accent">+</span></span>
          </div>
          <h2 className="text-3xl font-bold text-primary-foreground">
            Rejoignez la communauté
          </h2>
          <p className="text-primary-foreground/60">
            Créez votre espace en tant que particulier ou entreprise et commencez à vendre, échanger et vous connecter.
          </p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-md space-y-8">
          <div className="lg:hidden flex items-center gap-2 mb-4">
            <div className="w-8 h-8 rounded-lg gradient-primary flex items-center justify-center">
              <span className="text-primary-foreground font-bold text-sm">C+</span>
            </div>
            <span className="text-xl font-bold text-foreground">Connecte<span className="text-primary">+</span></span>
          </div>

          <div>
            <h1 className="text-2xl font-bold text-foreground">Créer un compte</h1>
            <p className="text-muted-foreground mt-1">Choisissez votre type de compte et commencez</p>
          </div>

          {/* User type selector */}
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => setUserType("particulier")}
              className={`flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all ${
                userType === "particulier"
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-primary/30"
              }`}
            >
              <User size={24} className={userType === "particulier" ? "text-primary" : "text-muted-foreground"} />
              <span className={`text-sm font-medium ${userType === "particulier" ? "text-primary" : "text-muted-foreground"}`}>
                Particulier
              </span>
            </button>
            <button
              type="button"
              onClick={() => setUserType("entreprise")}
              className={`flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all ${
                userType === "entreprise"
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-primary/30"
              }`}
            >
              <Building2 size={24} className={userType === "entreprise" ? "text-primary" : "text-muted-foreground"} />
              <span className={`text-sm font-medium ${userType === "entreprise" ? "text-primary" : "text-muted-foreground"}`}>
                Entreprise
              </span>
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {userType === "particulier" ? (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label>Prénom</Label>
                  <Input placeholder="Jean" />
                </div>
                <div className="space-y-2">
                  <Label>Nom</Label>
                  <Input placeholder="Kabila" />
                </div>
              </div>
            ) : (
              <>
                <div className="space-y-2">
                  <Label>Nom de la société</Label>
                  <Input placeholder="Ma Société SARL" />
                </div>
                <div className="space-y-2">
                  <Label>N° RCCM / ID Nat</Label>
                  <Input placeholder="CD/KIN/RCCM/..." />
                </div>
              </>
            )}

            <div className="space-y-2">
              <Label>Email</Label>
              <div className="relative">
                <Mail size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <Input type="email" placeholder="vous@exemple.com" className="pl-10" />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Mot de passe</Label>
              <div className="relative">
                <Lock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <Input
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  className="pl-10 pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Ville / Commune</Label>
              <Input placeholder="Kinshasa, Gombe" />
            </div>

            <Button type="submit" className="w-full shadow-primary-glow" size="lg">
              Créer mon compte
            </Button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            Déjà un compte ?{" "}
            <Link to="/login" className="text-primary font-medium hover:underline">
              Se connecter
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Register;
