-- Frozen invariants for organization staffing (revision 0008).
CREATE FUNCTION project2_org_position_period(pid integer, starts date, ends date) RETURNS void LANGUAGE plpgsql AS $$
DECLARE p positions%ROWTYPE; u org_units%ROWTYPE;
BEGIN
 SELECT * INTO p FROM positions WHERE position_id=pid;
 IF EXISTS(SELECT 1 FROM staff_versions WHERE id=p.staff_version_id AND annulled_at IS NOT NULL) THEN RAISE EXCEPTION 'annulled staff version' USING ERRCODE='23514'; END IF;
 IF p.annulled_at IS NOT NULL THEN RAISE EXCEPTION 'annulled staff position' USING ERRCODE='23514'; END IF;
 IF (p.valid_from IS NOT NULL AND starts<p.valid_from) OR (p.valid_to IS NOT NULL AND (ends IS NULL OR ends>p.valid_to)) THEN RAISE EXCEPTION 'assignment outside position period' USING ERRCODE='23514'; END IF;
 IF p.org_unit_id IS NULL THEN RETURN; END IF;
 SELECT * INTO u FROM org_units WHERE id=p.org_unit_id;
 IF u.annulled_at IS NOT NULL OR starts<u.formed_on OR (u.dissolved_on IS NOT NULL AND (ends IS NULL OR ends>u.dissolved_on)) THEN RAISE EXCEPTION 'assignment outside organization lifetime' USING ERRCODE='23514'; END IF;
 IF NOT EXISTS(SELECT 1 FROM org_staff_coverage c WHERE c.org_unit_id=p.org_unit_id AND c.staff_version_id=p.staff_version_id AND c.annulled_at IS NULL AND c.valid_from<=starts AND (c.valid_to IS NULL OR (ends IS NOT NULL AND ends<=c.valid_to))) THEN RAISE EXCEPTION 'assignment outside effective staffing source' USING ERRCODE='23514'; END IF;
END; $$;

CREATE FUNCTION project2_org_staff_before() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM set_config('search_path',quote_ident(TG_TABLE_SCHEMA)||',public',true);
 PERFORM pg_advisory_xact_lock(hashtext(current_schema()),hashtext('project2_organization'));
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'organization staffing history cannot be deleted' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' AND TG_TABLE_NAME='positions' THEN
   IF OLD.org_unit_id IS NOT NULL AND NEW.org_unit_id IS DISTINCT FROM OLD.org_unit_id THEN RAISE EXCEPTION 'historical position organization is immutable' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_TABLE_NAME='staff_structures' AND TG_OP='UPDATE' THEN
   IF OLD.org_unit_id IS NOT NULL AND NEW.org_unit_id IS DISTINCT FROM OLD.org_unit_id THEN RAISE EXCEPTION 'historical structure organization is immutable' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END; $$;

CREATE FUNCTION project2_org_staff_validate() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE coverage_row org_staff_coverage%ROWTYPE; assignment_row person_assignments%ROWTYPE; unit_row org_units%ROWTYPE; structure_row staff_structures%ROWTYPE;
BEGIN
 PERFORM set_config('search_path',quote_ident(TG_TABLE_SCHEMA)||',public',true);
 IF TG_TABLE_NAME='org_staff_coverage' THEN
   SELECT * INTO coverage_row FROM org_staff_coverage WHERE id=NEW.id;
   IF coverage_row.annulled_at IS NULL AND EXISTS(SELECT 1 FROM staff_versions ver JOIN org_units node ON node.id=coverage_row.org_unit_id WHERE ver.id=coverage_row.staff_version_id AND (ver.annulled_at IS NOT NULL OR node.annulled_at IS NOT NULL OR coverage_row.valid_from<node.formed_on OR coverage_row.valid_from<ver.valid_from OR (node.dissolved_on IS NOT NULL AND (coverage_row.valid_to IS NULL OR coverage_row.valid_to>node.dissolved_on)) OR (ver.valid_to IS NOT NULL AND (coverage_row.valid_to IS NULL OR coverage_row.valid_to>ver.valid_to)))) THEN RAISE EXCEPTION 'staff coverage outside version or organization period' USING ERRCODE='23514'; END IF;
   FOR assignment_row IN SELECT assigned.* FROM person_assignments assigned JOIN positions pos ON pos.position_id=assigned.staff_position_id WHERE pos.org_unit_id=coverage_row.org_unit_id AND assigned.annulled_at IS NULL LOOP PERFORM project2_org_position_period(assignment_row.staff_position_id,assignment_row.assigned_from,assignment_row.assigned_to); END LOOP;
 ELSIF TG_TABLE_NAME='person_assignments' THEN
   SELECT * INTO assignment_row FROM person_assignments WHERE id=NEW.id;
   IF assignment_row.annulled_at IS NULL THEN PERFORM project2_org_position_period(assignment_row.staff_position_id,assignment_row.assigned_from,assignment_row.assigned_to); END IF;
 ELSIF TG_TABLE_NAME='positions' THEN
   FOR assignment_row IN SELECT * FROM person_assignments WHERE staff_position_id=NEW.position_id AND annulled_at IS NULL LOOP PERFORM project2_org_position_period(assignment_row.staff_position_id,assignment_row.assigned_from,assignment_row.assigned_to); END LOOP;
 ELSIF TG_TABLE_NAME='staff_versions' THEN
   IF EXISTS(SELECT 1 FROM org_staff_coverage cov JOIN staff_versions ver ON ver.id=cov.staff_version_id WHERE ver.id=NEW.id AND cov.annulled_at IS NULL AND (ver.annulled_at IS NOT NULL OR cov.valid_from<ver.valid_from OR (ver.valid_to IS NOT NULL AND (cov.valid_to IS NULL OR cov.valid_to>ver.valid_to)))) THEN RAISE EXCEPTION 'coverage outside version period' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='org_units' THEN
   SELECT * INTO unit_row FROM org_units WHERE id=NEW.id;
   IF unit_row.kind NOT IN ('unit','regiment','battalion','company') AND EXISTS(SELECT 1 FROM staff_structures WHERE org_unit_id=unit_row.id) THEN RAISE EXCEPTION 'independent staff owner must be company or higher' USING ERRCODE='23514'; END IF;
   IF unit_row.annulled_at IS NOT NULL AND EXISTS(SELECT 1 FROM positions pos WHERE (pos.org_unit_id=unit_row.id OR pos.managed_unit_id=unit_row.id) AND pos.annulled_at IS NULL) THEN RAISE EXCEPTION 'organization has staffing dependencies' USING ERRCODE='23514'; END IF;
   IF EXISTS(SELECT 1 FROM org_staff_coverage cov WHERE cov.org_unit_id=unit_row.id AND cov.annulled_at IS NULL AND (unit_row.annulled_at IS NOT NULL OR cov.valid_from<unit_row.formed_on OR (unit_row.dissolved_on IS NOT NULL AND (cov.valid_to IS NULL OR cov.valid_to>unit_row.dissolved_on)))) THEN RAISE EXCEPTION 'coverage outside organization lifetime' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='staff_structures' THEN
   SELECT * INTO structure_row FROM staff_structures WHERE id=NEW.id;
   IF structure_row.org_unit_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM org_units node WHERE node.id=structure_row.org_unit_id AND node.annulled_at IS NULL AND node.kind IN ('unit','regiment','battalion','company')) THEN RAISE EXCEPTION 'independent staff owner must be company or higher' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NULL;
END; $$;

ALTER TABLE org_staff_coverage ADD CONSTRAINT org_single_effective_source EXCLUDE USING gist (org_unit_id WITH =, daterange(valid_from,coalesce(valid_to,DATE '9999-12-31'),'[]') WITH &&) WHERE (annulled_at IS NULL) DEFERRABLE INITIALLY DEFERRED;
CREATE TRIGGER org_position_link_immutable BEFORE INSERT OR UPDATE ON positions FOR EACH ROW EXECUTE FUNCTION project2_org_staff_before();
CREATE TRIGGER org_structure_link_immutable BEFORE INSERT OR UPDATE ON staff_structures FOR EACH ROW EXECUTE FUNCTION project2_org_staff_before();
CREATE TRIGGER org_coverage_no_delete BEFORE DELETE ON org_staff_coverage FOR EACH ROW EXECUTE FUNCTION project2_org_staff_before();
CREATE TRIGGER org_import_no_delete BEFORE DELETE ON org_staff_imports FOR EACH ROW EXECUTE FUNCTION project2_org_staff_before();
CREATE TRIGGER org_import_row_no_delete BEFORE DELETE ON org_staff_import_rows FOR EACH ROW EXECUTE FUNCTION project2_org_staff_before();
CREATE TRIGGER org_reassignment_no_delete BEFORE DELETE ON org_reassignments FOR EACH ROW EXECUTE FUNCTION project2_org_staff_before();
CREATE CONSTRAINT TRIGGER org_coverage_validate AFTER INSERT OR UPDATE ON org_staff_coverage DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION project2_org_staff_validate();
CREATE CONSTRAINT TRIGGER org_assignment_source_validate AFTER INSERT OR UPDATE ON person_assignments DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION project2_org_staff_validate();
CREATE CONSTRAINT TRIGGER org_position_source_validate AFTER INSERT OR UPDATE ON positions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION project2_org_staff_validate();
CREATE CONSTRAINT TRIGGER org_version_source_validate AFTER UPDATE ON staff_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION project2_org_staff_validate();
CREATE CONSTRAINT TRIGGER org_unit_staff_validate AFTER UPDATE ON org_units DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION project2_org_staff_validate();
CREATE CONSTRAINT TRIGGER org_structure_owner_validate AFTER INSERT OR UPDATE ON staff_structures DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION project2_org_staff_validate();

CREATE TRIGGER org_assignment_write_lock BEFORE INSERT OR UPDATE ON person_assignments FOR EACH ROW EXECUTE FUNCTION project2_org_staff_before();
CREATE TRIGGER org_coverage_write_lock BEFORE INSERT OR UPDATE ON org_staff_coverage FOR EACH ROW EXECUTE FUNCTION project2_org_staff_before();
CREATE TRIGGER org_version_write_lock BEFORE UPDATE ON staff_versions FOR EACH ROW EXECUTE FUNCTION project2_org_staff_before();
CREATE OR REPLACE FUNCTION guard_staff_versions_insert_fn() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.annulled_at IS NULL AND EXISTS(SELECT 1 FROM staff_versions v WHERE v.id!=NEW.id AND v.annulled_at IS NULL AND v.staff_structure_id=NEW.staff_structure_id AND v.valid_from<=coalesce(NEW.valid_to,DATE '9999-12-31') AND NEW.valid_from<=coalesce(v.valid_to,DATE '9999-12-31')) THEN RAISE EXCEPTION 'staff version periods overlap' USING ERRCODE='23514'; END IF;
 IF NEW.annulled_at IS NOT NULL AND EXISTS(SELECT 1 FROM positions p WHERE p.staff_version_id=NEW.id AND p.annulled_at IS NULL) THEN RAISE EXCEPTION 'version has active position dependencies' USING ERRCODE='23514'; END IF;
 IF EXISTS(SELECT 1 FROM person_assignments a JOIN positions p ON p.position_id=a.staff_position_id WHERE p.staff_version_id=NEW.id AND a.annulled_at IS NULL AND (NEW.annulled_at IS NOT NULL OR a.assigned_from<NEW.valid_from OR (NEW.valid_to IS NOT NULL AND (a.assigned_to IS NULL OR a.assigned_to>NEW.valid_to)))) THEN RAISE EXCEPTION 'assignments outside version period' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $$;
CREATE OR REPLACE FUNCTION guard_staff_versions_update_fn() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.annulled_at IS NULL AND EXISTS(SELECT 1 FROM staff_versions v WHERE v.id!=NEW.id AND v.annulled_at IS NULL AND v.staff_structure_id=NEW.staff_structure_id AND v.valid_from<=coalesce(NEW.valid_to,DATE '9999-12-31') AND NEW.valid_from<=coalesce(v.valid_to,DATE '9999-12-31')) THEN RAISE EXCEPTION 'staff version periods overlap' USING ERRCODE='23514'; END IF;
 IF NEW.annulled_at IS NOT NULL AND EXISTS(SELECT 1 FROM positions p WHERE p.staff_version_id=NEW.id AND p.annulled_at IS NULL) THEN RAISE EXCEPTION 'version has active position dependencies' USING ERRCODE='23514'; END IF;
 IF EXISTS(SELECT 1 FROM person_assignments a JOIN positions p ON p.position_id=a.staff_position_id WHERE p.staff_version_id=NEW.id AND a.annulled_at IS NULL AND (NEW.annulled_at IS NOT NULL OR a.assigned_from<NEW.valid_from OR (NEW.valid_to IS NOT NULL AND (a.assigned_to IS NULL OR a.assigned_to>NEW.valid_to)))) THEN RAISE EXCEPTION 'assignments outside version period' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END; $$;
