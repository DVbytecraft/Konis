"""
Migration 0016 — Triggers PostgreSQL pour l'immutabilité DB-level.

Protège contre tout contournement ORM/admin/script/SQL direct :

  A. Journaux soldés immuables
     - BEFORE UPDATE sur finance_journalpayable  : bloque si locked_at IS NOT NULL
     - BEFORE UPDATE sur finance_journalcreance  : idem

  B. Paiements sur journaux soldés impossibles
     - BEFORE INSERT sur finance_paiementpayable : vérifie journal.locked_at
     - BEFORE INSERT sur finance_paiementcreance : vérifie journal.locked_at

  C. AuditLog immuable
     - BEFORE UPDATE/DELETE sur audit_auditlog   : interdit toute modification

Ces triggers fonctionnent indépendamment de Django — protection au niveau DB.
"""
from django.db import migrations


# ── SQL forward ──────────────────────────────────────────────────────────────

_CREATE_TRIGGERS = """
-- ═══════════════════════════════════════════════════════════════════════
-- A. Journaux soldés immuables (UPDATE bloqué si locked_at IS NOT NULL)
-- ═══════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_block_locked_journal_update()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.locked_at IS NOT NULL THEN
        RAISE EXCEPTION
            'Journal #% est soldé et immuable. Aucune modification autorisée.',
            OLD.id
            USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_block_jpayable_locked_update ON finance_journalpayable;
CREATE TRIGGER trg_block_jpayable_locked_update
    BEFORE UPDATE ON finance_journalpayable
    FOR EACH ROW
    EXECUTE FUNCTION fn_block_locked_journal_update();

DROP TRIGGER IF EXISTS trg_block_jcreance_locked_update ON finance_journalcreance;
CREATE TRIGGER trg_block_jcreance_locked_update
    BEFORE UPDATE ON finance_journalcreance
    FOR EACH ROW
    EXECUTE FUNCTION fn_block_locked_journal_update();


-- ═══════════════════════════════════════════════════════════════════════
-- B. Paiements sur journaux soldés impossibles (INSERT bloqué)
-- ═══════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_block_paiement_on_locked_jpayable()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    v_locked_at TIMESTAMPTZ;
BEGIN
    SELECT locked_at INTO v_locked_at
    FROM finance_journalpayable
    WHERE id = NEW.journal_id;

    IF v_locked_at IS NOT NULL THEN
        RAISE EXCEPTION
            'JournalPayable #% est soldé. Aucun paiement ne peut être ajouté.',
            NEW.journal_id
            USING ERRCODE = 'P0002';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_block_paiement_on_locked_jpayable ON finance_paiementpayable;
CREATE TRIGGER trg_block_paiement_on_locked_jpayable
    BEFORE INSERT ON finance_paiementpayable
    FOR EACH ROW
    EXECUTE FUNCTION fn_block_paiement_on_locked_jpayable();


CREATE OR REPLACE FUNCTION fn_block_paiement_on_locked_jcreance()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    v_locked_at TIMESTAMPTZ;
BEGIN
    SELECT locked_at INTO v_locked_at
    FROM finance_journalcreance
    WHERE id = NEW.journal_id;

    IF v_locked_at IS NOT NULL THEN
        RAISE EXCEPTION
            'JournalCreance #% est soldé. Aucun paiement ne peut être ajouté.',
            NEW.journal_id
            USING ERRCODE = 'P0002';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_block_paiement_on_locked_jcreance ON finance_paiementcreance;
CREATE TRIGGER trg_block_paiement_on_locked_jcreance
    BEFORE INSERT ON finance_paiementcreance
    FOR EACH ROW
    EXECUTE FUNCTION fn_block_paiement_on_locked_jcreance();


-- ═══════════════════════════════════════════════════════════════════════
-- C. AuditLog immuable (UPDATE et DELETE bloqués)
-- ═══════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION fn_protect_auditlog()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'Les logs d''audit sont immuables. Toute modification est interdite.'
        USING ERRCODE = 'P0003';
END;
$$;

DROP TRIGGER IF EXISTS trg_protect_auditlog_update ON audit_auditlog;
CREATE TRIGGER trg_protect_auditlog_update
    BEFORE UPDATE ON audit_auditlog
    FOR EACH ROW
    EXECUTE FUNCTION fn_protect_auditlog();

DROP TRIGGER IF EXISTS trg_protect_auditlog_delete ON audit_auditlog;
CREATE TRIGGER trg_protect_auditlog_delete
    BEFORE DELETE ON audit_auditlog
    FOR EACH ROW
    EXECUTE FUNCTION fn_protect_auditlog();
"""

# ── SQL reverse (supprime les triggers + fonctions) ──────────────────────────

_DROP_TRIGGERS = """
DROP TRIGGER IF EXISTS trg_block_jpayable_locked_update   ON finance_journalpayable;
DROP TRIGGER IF EXISTS trg_block_jcreance_locked_update   ON finance_journalcreance;
DROP TRIGGER IF EXISTS trg_block_paiement_on_locked_jpayable ON finance_paiementpayable;
DROP TRIGGER IF EXISTS trg_block_paiement_on_locked_jcreance ON finance_paiementcreance;
DROP TRIGGER IF EXISTS trg_protect_auditlog_update        ON audit_auditlog;
DROP TRIGGER IF EXISTS trg_protect_auditlog_delete        ON audit_auditlog;

DROP FUNCTION IF EXISTS fn_block_locked_journal_update();
DROP FUNCTION IF EXISTS fn_block_paiement_on_locked_jpayable();
DROP FUNCTION IF EXISTS fn_block_paiement_on_locked_jcreance();
DROP FUNCTION IF EXISTS fn_protect_auditlog();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_idempotencykey"),
        # Dépendances explicites pour garantir que les tables cibles existent
        ("finance", "0007_clientfinance_lieu"),
        ("audit",   "0003_alertelog"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_CREATE_TRIGGERS,
            reverse_sql=_DROP_TRIGGERS,
        ),
    ]
