-- Additive hierarchy rules. Original 0008 functions remain frozen in their source files.
CREATE FUNCTION project2_org_level(kind text, explicit integer) RETURNS integer LANGUAGE sql IMMUTABLE AS $$
 SELECT CASE kind WHEN 'unit' THEN 1 WHEN 'regiment' THEN 2 WHEN 'battalion' THEN 3 WHEN 'detachment' THEN 3
 WHEN 'company' THEN 4 WHEN 'battery' THEN 4 WHEN 'platoon' THEN 5 WHEN 'squad' THEN 6
 WHEN 'team' THEN 7 WHEN 'crew' THEN 7 WHEN 'other' THEN explicit END;
$$;
-- Fail safely on known invalid legacy edges; never reparent/reclassify records silently.
DO $$ DECLARE invalid_child integer; BEGIN
 SELECT c.id INTO invalid_child FROM org_unit_states s JOIN org_units c ON c.id=s.org_unit_id JOIN org_units p ON p.id=s.primary_parent_id
 WHERE c.annulled_at IS NULL AND p.annulled_at IS NULL AND project2_org_level(c.kind,c.hierarchy_level)<=project2_org_level(p.kind,p.hierarchy_level) LIMIT 1;
 IF invalid_child IS NOT NULL THEN RAISE EXCEPTION 'Correct legacy primary hierarchy for unit ID % before migration; no data were changed',invalid_child; END IF;
END; $$;
CREATE FUNCTION project2_org_level_input() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE child org_units%ROWTYPE; parent org_units%ROWTYPE;
BEGIN
 PERFORM set_config('search_path',quote_ident(TG_TABLE_SCHEMA)||',public',true);
 PERFORM pg_advisory_xact_lock(hashtext(current_schema()),hashtext('project2_organization'));
 IF TG_TABLE_NAME='org_units' THEN
  IF NEW.kind='other' AND NEW.hierarchy_level IS NULL AND (TG_OP='INSERT' OR OLD.hierarchy_level IS NOT NULL OR OLD.kind!='other') THEN
   RAISE EXCEPTION 'other organization requires explicit hierarchy level' USING ERRCODE='23514';
  END IF;
 ELSE
  IF NEW.primary_parent_id IS NOT NULL AND (TG_OP='INSERT' OR NEW.primary_parent_id IS DISTINCT FROM OLD.primary_parent_id) THEN
   SELECT * INTO child FROM org_units WHERE id=NEW.org_unit_id;
   SELECT * INTO parent FROM org_units WHERE id=NEW.primary_parent_id;
   IF project2_org_level(child.kind,child.hierarchy_level) IS NULL OR project2_org_level(parent.kind,parent.hierarchy_level) IS NULL THEN
    RAISE EXCEPTION 'explicit hierarchy levels required for new primary relation' USING ERRCODE='23514';
   END IF;
  END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER org_level_unit_input BEFORE INSERT OR UPDATE ON org_units FOR EACH ROW EXECUTE FUNCTION project2_org_level_input();
CREATE TRIGGER org_level_state_input BEFORE INSERT OR UPDATE ON org_unit_states FOR EACH ROW EXECUTE FUNCTION project2_org_level_input();
CREATE FUNCTION project2_org_hierarchy_validate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM set_config('search_path',quote_ident(TG_TABLE_SCHEMA)||',public',true);
 PERFORM pg_advisory_xact_lock(hashtext(current_schema()),hashtext('project2_organization'));
 IF EXISTS(SELECT 1 FROM org_unit_states s JOIN org_units c ON c.id=s.org_unit_id JOIN org_units p ON p.id=s.primary_parent_id
   WHERE c.annulled_at IS NULL AND p.annulled_at IS NULL AND project2_org_level(c.kind,c.hierarchy_level)<=project2_org_level(p.kind,p.hierarchy_level)) THEN
  RAISE EXCEPTION 'primary organization hierarchy is reversed or equal' USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END; $$;
CREATE CONSTRAINT TRIGGER org_level_unit_check AFTER INSERT OR UPDATE ON org_units DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION project2_org_hierarchy_validate();
CREATE CONSTRAINT TRIGGER org_level_state_check AFTER INSERT OR UPDATE ON org_unit_states DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION project2_org_hierarchy_validate();

CREATE OR REPLACE FUNCTION project2_org_staff_validate() RETURNS trigger LANGUAGE plpgsql AS $$
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
   IF unit_row.kind NOT IN ('unit','regiment','battalion','detachment','company','battery') AND EXISTS(SELECT 1 FROM staff_structures WHERE org_unit_id=unit_row.id) THEN RAISE EXCEPTION 'independent staff owner must be company or higher' USING ERRCODE='23514'; END IF;
   IF unit_row.annulled_at IS NOT NULL AND EXISTS(SELECT 1 FROM positions pos WHERE (pos.org_unit_id=unit_row.id OR pos.managed_unit_id=unit_row.id) AND pos.annulled_at IS NULL) THEN RAISE EXCEPTION 'organization has staffing dependencies' USING ERRCODE='23514'; END IF;
   IF EXISTS(SELECT 1 FROM org_staff_coverage cov WHERE cov.org_unit_id=unit_row.id AND cov.annulled_at IS NULL AND (unit_row.annulled_at IS NOT NULL OR cov.valid_from<unit_row.formed_on OR (unit_row.dissolved_on IS NOT NULL AND (cov.valid_to IS NULL OR cov.valid_to>unit_row.dissolved_on)))) THEN RAISE EXCEPTION 'coverage outside organization lifetime' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='staff_structures' THEN
   SELECT * INTO structure_row FROM staff_structures WHERE id=NEW.id;
   IF structure_row.org_unit_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM org_units node WHERE node.id=structure_row.org_unit_id AND node.annulled_at IS NULL AND node.kind IN ('unit','regiment','battalion','detachment','company','battery')) THEN RAISE EXCEPTION 'independent staff owner must be company or higher' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NULL;
END; $$;
