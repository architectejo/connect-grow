import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Menu, X } from "lucide-react";

const Navbar = () => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 glass">
      <div className="container mx-auto flex items-center justify-between h-16 px-4">
        <Link to="/" className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg gradient-primary flex items-center justify-center">
            <span className="text-primary-foreground font-bold text-sm">C+</span>
          </div>
          <span className="text-xl font-bold text-foreground">Connecte<span className="text-primary">+</span></span>
        </Link>

        <div className="hidden md:flex items-center gap-8">
          <a href="#features" className="text-sm text-muted-foreground hover:text-foreground transition-colors">Fonctionnalités</a>
          <a href="#how-it-works" className="text-sm text-muted-foreground hover:text-foreground transition-colors">Comment ça marche</a>
          <a href="#categories" className="text-sm text-muted-foreground hover:text-foreground transition-colors">Catégories</a>
        </div>

        <div className="hidden md:flex items-center gap-3">
          <Button variant="ghost" asChild>
            <Link to="/login">Se connecter</Link>
          </Button>
          <Button asChild className="shadow-primary-glow">
            <Link to="/register">Créer un compte</Link>
          </Button>
        </div>

        <button className="md:hidden text-foreground" onClick={() => setIsOpen(!isOpen)}>
          {isOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {isOpen && (
        <div className="md:hidden border-t border-border bg-card px-4 py-4 space-y-3">
          <a href="#features" className="block text-sm text-muted-foreground hover:text-foreground">Fonctionnalités</a>
          <a href="#how-it-works" className="block text-sm text-muted-foreground hover:text-foreground">Comment ça marche</a>
          <a href="#categories" className="block text-sm text-muted-foreground hover:text-foreground">Catégories</a>
          <div className="flex gap-3 pt-2">
            <Button variant="ghost" asChild className="flex-1">
              <Link to="/login">Se connecter</Link>
            </Button>
            <Button asChild className="flex-1">
              <Link to="/register">Créer un compte</Link>
            </Button>
          </div>
        </div>
      )}
    </nav>
  );
};

export default Navbar;
