import { z } from "zod";

/**
 * Schéma de validation Zod pour les données utilisateur renvoyées par /api/auth/me.
 * Source unique de vérité — le type User est inféré depuis ce schéma.
 * Si le backend change la structure, la validation échoue explicitement
 * plutôt que de laisser des données corrompues circuler silencieusement.
 */
export const userSchema = z.object({
  id: z.number(),
  username: z.string().min(1),
  first_name: z.string(),
  last_name: z.string(),
  role: z.string().min(1),
  role_display: z.string(),
  is_factory: z.boolean().optional(),
  role_normalized: z.string().optional(),
  lieu: z
    .object({
      id: z.number(),
      nom: z.string(),
      type_lieu: z.string(),
      mouture_enabled: z.boolean().optional(),
      prix_mouture_defaut: z.union([z.string(), z.number()]).nullable().optional(),
      prix_mouture_max: z.union([z.string(), z.number()]).nullable().optional(),
    })
    .nullable()
    .optional(),
  entreprise: z.number().nullable().optional(),
});

export type User = z.infer<typeof userSchema>;
