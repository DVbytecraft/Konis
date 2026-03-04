# Réglage impression ticket 58mm (XPrinter / Chrome)

## Page dédiée

- **URL** : `/ventes/ticket/<id>/print/`
- **Template** : `templates/ticket_print.html`
- **Exemple** : `http://localhost:8000/ventes/ticket/1/print/`

## CSS print (58mm)

Le template utilise :

- **Largeur** : `58mm` (body et @page)
- **Marges** : `2mm` (page), `2mm 3mm` (body)
- **Police** : `Courier New`, `11px` (corps), `12px` (titre/total)
- **Ligne** : `1.3`

## Réglage Chrome + XPrinter 58mm

1. **Ouvrir** la page ticket dans Chrome (`/ventes/ticket/<id>/print/` ou depuis la caisse).
2. **Ctrl+P** (ou Cmd+P sur Mac).
3. **Destination** : sélectionner l’imprimante XPrinter (ou imprimante thermique 58mm).
4. **Paramètres** :
   - **Marges** : Aucune
   - **Échelle** : 100 %
   - **En-têtes et pieds de page** : désactivés
   - Format papier : **Personnalisé** ou **58mm**
   - Arrière-plan graphique : **Coché** (si bordure)
5. **Imprimer**.

## Raccourci frontend

Pour ouvrir l’impression depuis l’appli boutique :

```javascript
// Après création d'une vente, ouvrir la page d'impression
const ticketId = response.data.id;
window.open(`/ventes/ticket/${ticketId}/print/`, '_blank', 'width=200,height=400');
// L'utilisateur fait Ctrl+P pour imprimer
```

Ou ouvrir en popup et déclencher l’impression automatiquement :

```javascript
const printWindow = window.open(`/ventes/ticket/${ticketId}/print/`, '_blank');
printWindow.onload = () => printWindow.print();
```

## Notes

- L’impression 58mm suppose une imprimante thermique compatible (XPrinter, Epson TM, etc.).
- En local, utiliser "Enregistrer en PDF" pour vérifier le rendu.
