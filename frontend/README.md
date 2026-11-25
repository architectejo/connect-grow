# Connecte+ : front (dossier `frontend/`)

React 18, TypeScript, Vite, Tailwind, shadcn/ui, React Query, react-i18next, PWA.

```bash
npm install
cp .env.example .env     # VITE_API_URL=http://localhost:8000/api/v1/
npm run dev              # http://localhost:8080
npm run lint && npm run test && npm run build
```

## Variables d'environnement

- `VITE_API_URL` : base de l'API REST, préfixe unique `/api/v1/` (l'ancien `/api/` répond 404). Le `/` final est ajouté si absent.
- `VITE_MEDIA_URL` (facultative) : origine des médias ; par défaut l'origine de `VITE_API_URL` (le suffixe `/api/v1/` n'en fait pas partie).
- Pagination : le serveur plafonne `page_size` à 100 (défaut 20) ; le front n'envoie pas `page_size`.
