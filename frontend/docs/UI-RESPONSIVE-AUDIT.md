# Audit UI / Responsive Desktop — KONIS V0

## 1. Audit P0/P1/P2 (avant corrections)

### P0 (bloquants terrain)
- ~~Scroll horizontal global sur body~~ (corrigé : overflow-x-hidden)
- ~~Police non professionnelle~~ (corrigé : Poppins)

### P1 (importants)
- ~~Tables débordent sur petit laptop (1366px)~~ (corrigé : overflow-x-auto, min-w-0)
- ~~Sidebar fixe 224px pouvant réduire trop l’espace~~ (corrigé : w-52 sm:w-56 shrink-0)
- ~~Contenu main sans min-w-0 → overflow flex~~ (corrigé : min-w-0 sur main, pages)

### P2 (améliorations)
- ~~Pas de cohérence police~~ (corrigé : Poppins + base 16px)
- ~~Espacements variables~~ (harmonisés via container, py-6, px-4 sm:px-6)
- ~~Pas de page test UI~~ (ajouté : /ui-check)

---

## 2. Classes Tailwind ajoutées

| Fichier | Classes ajoutées |
|---------|------------------|
| `layout.tsx` (root) | `overflow-x-hidden` (html), `font-sans text-base`, `--font-poppins` |
| `globals.css` | `overflow-x-hidden` (html), `min-w-0` (body) |
| `(app)/layout.tsx` | `min-w-0 overflow-x-hidden`, `w-52 sm:w-56 shrink-0`, `min-w-0` (main), `max-w-7xl mx-auto px-4 sm:px-6` |
| `admin/page.tsx` | `min-w-0`, `overflow-x-auto -mx-1 min-w-0`, `min-w-[280px]` (tables) |
| `comptable/page.tsx` | `min-w-0`, `overflow-x-auto overflow-y-auto min-w-0 -mx-1`, `min-w-[320px]` (tables) |
| `caisse/page.tsx` | `min-w-0` |
| `login/page.tsx` | `min-w-0 overflow-x-hidden` |
| `tailwind.config.ts` | `fontFamily.sans: Poppins`, `fontSize` base/sm/xs |

---

## 3. Rendu par résolution (après corrections)

| Résolution | Rendu |
|------------|-------|
| **1366x768** | Sidebar 208px (w-52), contenu centré max-w-7xl. Tables scroll horizontal si nécessaire. Caisse : grille 1 col mobile, 2 cols md, 3 cols lg. Aucun scroll horizontal global. |
| **1440x900** | Même layout, sidebar 224px (w-56) à partir de sm. Espace confortable. |
| **1920x1080** | Layout fluide, contenu centré avec marges. KPIs en 4 colonnes, tables lisibles. |
| **2560x1440** | Contenu centré max-w-7xl (1280px) avec marges latérales. Lisibilité optimale. |
| **3440x1440** | Ultra-wide : contenu centré, marges importantes. Pas d’étirement excessif. |

---

## 4. Police Poppins

- **Source** : `next/font/google` (Poppins, weights 400/500/600/700)
- **Fallback** : system-ui, sans-serif
- **Variable CSS** : `--font-poppins`
- **Application** : `font-sans` (Tailwind) sur body

---

## 5. Caisse (POS) — inchangé

- Focus auto sur recherche produit
- Raccourcis : F4 Payer, F2 Nouvelle vente, Entrée ajouter, Flèches sélection
- Mode impression ticket inchangé
