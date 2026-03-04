# Facture PDF OFFICIELLE KONIS - Specification Production

## Objectif

Fournir une facture A4 professionnelle en **vrai PDF backend**, stable et exploitable en contexte client/finance.

## Source de verite

- Backend Django uniquement.
- Vue PDF: `ventes.views.facture_pdf` (alias historique: `facture_print`).
- Moteur PDF: `ventes/pdf.py` (ReportLab).
- Modele: `ventes.Facture` + `ventes.LigneFacture`.
- Aucun recalcul frontend pour le document.

## Donnees affichees

- En-tete entreprise:
  - nom entreprise (`facture.lieu.entreprise.nom`)
  - lieu emetteur (`facture.lieu.nom`)
  - adresse lieu (`facture.lieu.adresse`)
  - logo image si configure, sinon logo textuel
- Bloc facture:
  - numero
  - date
  - source role
  - emetteur (`created_by`)
- Bloc client:
  - nom
  - contact
  - notes
- Tableau lignes:
  - description
  - quantite
  - prix unitaire
  - total ligne
- Resume totaux:
  - sous-total produits
  - services mouture (si applicable)
  - total facture

## Regles de coherence montants

- Les montants de lignes proviennent des champs persistes.
- `total_mouture` est derive des lignes de facture dont la description contient `mouture` ou `broyage`.
- `total_produits = somme_lignes - total_mouture`.
- Le total final affiche est `facture.total` (champ persiste).

## Branding / Charte visuelle

- Configuration centralisee: `core/branding.py` (`KONIS_BRAND`).
- Couleur principale: `KONIS_PRIMARY_COLOR` (vert KONIS).
- Couleurs secondaires / bordures / texte configurees via variables du meme fichier.
- Logo: variable `KONIS_LOGO_PATH` (optionnelle).

## Endpoints

- PDF inline: `GET /ventes/facture/<id>/pdf/`
- PDF telechargement: `GET /ventes/facture/<id>/pdf/?download=1`
- Alias historique: `GET /ventes/facture/<id>/print/`

## Impression utilisateur (Chrome / Edge)

- Le frontend ouvre une fenetre dediee avec l'iframe PDF puis declenche `window.print()`.
- La boite d'impression systeme est ouverte (pas d'impression silencieuse).

## Securite

- Controle d'acces strict:
  - admin/comptable: acces global
  - boutique/usine: acces uniquement aux factures de leur `lieu`
- URL forgee vers facture d'un autre lieu -> `404`.

## Reimpression

- PDF genere avec option d'invariance (`invariant=1`) pour obtenir un rendu binaire stable.
- Reimpression = meme document pour les memes donnees en base.
