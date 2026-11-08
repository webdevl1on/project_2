-- Frozen organizational invariants, PostgreSQL 17. Do not derive staffing from tree edits.
-- The application and raw SQL writers use the exact same schema-scoped lock.
CREATE FUNCTION project2_organization_write_guard() RETURNS trigger LANGUAGE plpgsql VOLATILE AS $$
BEGIN
  -- Qualified SQL must still validate the actual table's schema, not a caller's shadow path.
  PERFORM set_config('search_path',quote_ident(TG_TABLE_SCHEMA)||',public',true);
  PERFORM pg_advisory_xact_lock(hashtext(current_schema()),hashtext('project2_organization'));
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'organizational history cannot be deleted' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' AND NEW.id IS DISTINCT FROM OLD.id THEN
    RAISE EXCEPTION 'organizational identity is immutable' USING ERRCODE='23514';
  END IF;
  IF TG_TABLE_NAME='org_unit_states' THEN
    IF TG_OP='UPDATE' AND NEW.org_unit_id IS DISTINCT FROM OLD.org_unit_id THEN
      RAISE EXCEPTION 'organizational state identity is immutable' USING ERRCODE='23514';
    END IF;
    NEW.normalized_name:=project2_norm(NEW.name);
  END IF;
  IF TG_TABLE_NAME='org_operational_subordinations' THEN
    IF TG_OP='UPDATE' AND NEW.org_unit_id IS DISTINCT FROM OLD.org_unit_id THEN
      RAISE EXCEPTION 'operational record identity is immutable' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER org_units_write_guard BEFORE INSERT OR UPDATE OR DELETE ON org_units FOR EACH ROW EXECUTE FUNCTION project2_organization_write_guard();
CREATE TRIGGER org_unit_states_write_guard BEFORE INSERT OR UPDATE OR DELETE ON org_unit_states FOR EACH ROW EXECUTE FUNCTION project2_organization_write_guard();
CREATE TRIGGER org_operational_write_guard BEFORE INSERT OR UPDATE OR DELETE ON org_operational_subordinations FOR EACH ROW EXECUTE FUNCTION project2_organization_write_guard();

CREATE FUNCTION project2_org_audit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'organization audit is append only' USING ERRCODE='23514'; END; $$;
CREATE TRIGGER org_audit_no_update BEFORE UPDATE ON org_audit FOR EACH ROW EXECUTE FUNCTION project2_org_audit_guard();
CREATE TRIGGER org_audit_no_delete BEFORE DELETE ON org_audit FOR EACH ROW EXECUTE FUNCTION project2_org_audit_guard();

-- Keep the same representable full-calendar domain as other project SQL Date fields.
ALTER TABLE org_units ADD CONSTRAINT org_formed_calendar CHECK (formed_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31');
ALTER TABLE org_units ADD CONSTRAINT org_dissolved_calendar CHECK (dissolved_on IS NULL OR dissolved_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31');
ALTER TABLE org_unit_states ADD CONSTRAINT org_state_start_calendar CHECK (valid_from BETWEEN DATE '0001-01-01' AND DATE '9999-12-31');
ALTER TABLE org_unit_states ADD CONSTRAINT org_state_end_calendar CHECK (valid_to IS NULL OR valid_to BETWEEN DATE '0001-01-01' AND DATE '9999-12-31');
ALTER TABLE org_operational_subordinations ADD CONSTRAINT org_operational_start_calendar CHECK (valid_from BETWEEN DATE '0001-01-01' AND DATE '9999-12-31');
ALTER TABLE org_operational_subordinations ADD CONSTRAINT org_operational_end_calendar CHECK (valid_to IS NULL OR valid_to BETWEEN DATE '0001-01-01' AND DATE '9999-12-31');

ALTER TABLE org_unit_states ADD CONSTRAINT org_state_period_exclusion EXCLUDE USING gist
  (org_unit_id WITH =,daterange(valid_from,coalesce(valid_to,DATE '9999-12-31'),'[]') WITH &&)
  DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE org_operational_subordinations ADD CONSTRAINT org_operational_period_exclusion EXCLUDE USING gist
  (org_unit_id WITH =,parent_id WITH =,daterange(valid_from,coalesce(valid_to,DATE '9999-12-31'),'[]') WITH &&)
  DEFERRABLE INITIALLY DEFERRED;

-- A combined state is intentionally validated at transaction end: a rename/reparent
-- closes a previous state and inserts its replacement within one atomic operation.
CREATE FUNCTION project2_organization_validate() RETURNS trigger LANGUAGE plpgsql VOLATILE AS $$
BEGIN
  -- Qualified SQL must still validate the actual table's schema, not a caller's shadow path.
  PERFORM set_config('search_path',quote_ident(TG_TABLE_SCHEMA)||',public',true);
  PERFORM pg_advisory_xact_lock(hashtext(current_schema()),hashtext('project2_organization'));
  IF EXISTS (
    SELECT 1 FROM org_units u
    WHERE u.annulled_at IS NULL AND
      (SELECT range_agg(daterange(s.valid_from,coalesce(s.valid_to,DATE '9999-12-31'),'[]'))
       FROM org_unit_states s WHERE s.org_unit_id=u.id)
      IS DISTINCT FROM datemultirange(daterange(u.formed_on,coalesce(u.dissolved_on,DATE '9999-12-31'),'[]'))
  ) THEN RAISE EXCEPTION 'organizational states must cover exactly the unit lifetime' USING ERRCODE='23514'; END IF;

  IF EXISTS (
    SELECT 1 FROM org_unit_states s JOIN org_units child ON child.id=s.org_unit_id
    LEFT JOIN org_units parent ON parent.id=s.primary_parent_id
    WHERE child.annulled_at IS NULL AND s.primary_parent_id IS NOT NULL
      AND (parent.id IS NULL OR parent.annulled_at IS NOT NULL OR s.valid_from<parent.formed_on
           OR (parent.dissolved_on IS NOT NULL AND (s.valid_to IS NULL OR s.valid_to>parent.dissolved_on)))
  ) THEN RAISE EXCEPTION 'primary parent must exist throughout the child state period' USING ERRCODE='23514'; END IF;

  IF EXISTS (
    SELECT 1 FROM org_unit_states a JOIN org_units ua ON ua.id=a.org_unit_id
    JOIN org_unit_states b ON a.org_unit_id<b.org_unit_id
      AND a.primary_parent_id IS NOT DISTINCT FROM b.primary_parent_id
      AND a.normalized_name=b.normalized_name
      AND daterange(a.valid_from,coalesce(a.valid_to,DATE '9999-12-31'),'[]')
          && daterange(b.valid_from,coalesce(b.valid_to,DATE '9999-12-31'),'[]')
    JOIN org_units ub ON ub.id=b.org_unit_id
    WHERE ua.annulled_at IS NULL AND ub.annulled_at IS NULL
  ) THEN RAISE EXCEPTION 'duplicate effective sibling names' USING ERRCODE='23514'; END IF;

  IF EXISTS (
    WITH RECURSIVE paths(node_id,left_on,right_on,visited,cycle) AS (
      SELECT s.primary_parent_id,s.valid_from,coalesce(s.valid_to,DATE '9999-12-31'),
             ARRAY[s.org_unit_id,s.primary_parent_id],s.org_unit_id=s.primary_parent_id
      FROM org_unit_states s JOIN org_units u ON u.id=s.org_unit_id
      WHERE u.annulled_at IS NULL AND s.primary_parent_id IS NOT NULL
      UNION ALL
      SELECT s.primary_parent_id,greatest(p.left_on,s.valid_from),least(p.right_on,coalesce(s.valid_to,DATE '9999-12-31')),
             p.visited||s.primary_parent_id,s.primary_parent_id=ANY(p.visited)
      FROM paths p JOIN org_unit_states s ON s.org_unit_id=p.node_id
      JOIN org_units u ON u.id=s.org_unit_id
      WHERE NOT p.cycle AND u.annulled_at IS NULL AND s.primary_parent_id IS NOT NULL
        AND greatest(p.left_on,s.valid_from)<=least(p.right_on,coalesce(s.valid_to,DATE '9999-12-31'))
    ) SELECT 1 FROM paths WHERE cycle
  ) THEN RAISE EXCEPTION 'historical primary organization cycle' USING ERRCODE='23514'; END IF;

  IF EXISTS (
    SELECT 1 FROM org_operational_subordinations s JOIN org_units child ON child.id=s.org_unit_id
    LEFT JOIN org_units parent ON parent.id=s.parent_id
    WHERE child.annulled_at IS NULL AND
      (parent.id IS NULL OR parent.annulled_at IS NOT NULL OR s.valid_from<child.formed_on OR s.valid_from<parent.formed_on
       OR (child.dissolved_on IS NOT NULL AND (s.valid_to IS NULL OR s.valid_to>child.dissolved_on))
       OR (parent.dissolved_on IS NOT NULL AND (s.valid_to IS NULL OR s.valid_to>parent.dissolved_on)))
  ) THEN RAISE EXCEPTION 'operational parent and child lifetimes must cover the relation' USING ERRCODE='23514'; END IF;

  IF EXISTS (
    WITH RECURSIVE paths(node_id,left_on,right_on,visited,cycle) AS (
      SELECT s.parent_id,s.valid_from,coalesce(s.valid_to,DATE '9999-12-31'),ARRAY[s.org_unit_id,s.parent_id],s.org_unit_id=s.parent_id
      FROM org_operational_subordinations s JOIN org_units u ON u.id=s.org_unit_id
      WHERE u.annulled_at IS NULL
      UNION ALL
      SELECT s.parent_id,greatest(p.left_on,s.valid_from),least(p.right_on,coalesce(s.valid_to,DATE '9999-12-31')),
             p.visited||s.parent_id,s.parent_id=ANY(p.visited)
      FROM paths p JOIN org_operational_subordinations s ON s.org_unit_id=p.node_id
      JOIN org_units u ON u.id=s.org_unit_id
      WHERE NOT p.cycle AND u.annulled_at IS NULL
        AND greatest(p.left_on,s.valid_from)<=least(p.right_on,coalesce(s.valid_to,DATE '9999-12-31'))
    ) SELECT 1 FROM paths WHERE cycle
  ) THEN RAISE EXCEPTION 'historical operational organization cycle' USING ERRCODE='23514'; END IF;
  RETURN NULL;
END; $$;
CREATE CONSTRAINT TRIGGER org_units_consistent AFTER INSERT OR UPDATE ON org_units DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION project2_organization_validate();
CREATE CONSTRAINT TRIGGER org_states_consistent AFTER INSERT OR UPDATE ON org_unit_states DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION project2_organization_validate();
CREATE CONSTRAINT TRIGGER org_operational_consistent AFTER INSERT OR UPDATE ON org_operational_subordinations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION project2_organization_validate();
