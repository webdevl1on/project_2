CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;
ALTER TABLE staff_versions ADD CONSTRAINT version_period_exclusion EXCLUDE USING gist (staff_structure_id WITH =, daterange(valid_from,coalesce(valid_to,DATE '9999-12-31'),'[]') WITH &&);
ALTER TABLE person_assignments ADD CONSTRAINT person_period_exclusion EXCLUDE USING gist (person_id WITH =, daterange(assigned_from,coalesce(assigned_to,DATE '9999-12-31'),'[]') WITH &&);
ALTER TABLE person_assignments ADD CONSTRAINT position_period_exclusion EXCLUDE USING gist (staff_position_id WITH =, daterange(assigned_from,coalesce(assigned_to,DATE '9999-12-31'),'[]') WITH &&);
CREATE FUNCTION guard_staff_versions_insert_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF EXISTS (
   SELECT 1 FROM staff_versions v WHERE v.id != NEW.id
   AND v.staff_structure_id=NEW.staff_structure_id
   AND v.valid_from<=coalesce(NEW.valid_to,'9999-12-31')
   AND NEW.valid_from<=coalesce(v.valid_to,'9999-12-31')
 ) THEN RAISE EXCEPTION 'staff version periods overlap' USING ERRCODE='23514'; END IF;
IF EXISTS (
   SELECT 1 FROM person_assignments a JOIN positions p ON p.position_id=a.staff_position_id
   WHERE p.staff_version_id=NEW.id AND (a.assigned_from<NEW.valid_from OR
     (NEW.valid_to IS NOT NULL AND (a.assigned_to IS NULL OR a.assigned_to>NEW.valid_to)))
 ) THEN RAISE EXCEPTION 'assignments outside version period' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER guard_staff_versions_insert BEFORE INSERT ON staff_versions FOR EACH ROW EXECUTE FUNCTION guard_staff_versions_insert_fn();
CREATE FUNCTION guard_staff_versions_update_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF EXISTS (
   SELECT 1 FROM staff_versions v WHERE v.id != NEW.id
   AND v.staff_structure_id=NEW.staff_structure_id
   AND v.valid_from<=coalesce(NEW.valid_to,'9999-12-31')
   AND NEW.valid_from<=coalesce(v.valid_to,'9999-12-31')
 ) THEN RAISE EXCEPTION 'staff version periods overlap' USING ERRCODE='23514'; END IF;
IF EXISTS (
   SELECT 1 FROM person_assignments a JOIN positions p ON p.position_id=a.staff_position_id
   WHERE p.staff_version_id=NEW.id AND (a.assigned_from<NEW.valid_from OR
     (NEW.valid_to IS NOT NULL AND (a.assigned_to IS NULL OR a.assigned_to>NEW.valid_to)))
 ) THEN RAISE EXCEPTION 'assignments outside version period' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER guard_staff_versions_update BEFORE UPDATE ON staff_versions FOR EACH ROW EXECUTE FUNCTION guard_staff_versions_update_fn();
CREATE FUNCTION guard_staff_versions_delete_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF TRUE THEN RAISE EXCEPTION 'historical records cannot be deleted' USING ERRCODE='23514'; END IF; RETURN OLD; END $guard$;
CREATE TRIGGER guard_staff_versions_delete BEFORE DELETE ON staff_versions FOR EACH ROW EXECUTE FUNCTION guard_staff_versions_delete_fn();
CREATE FUNCTION guard_person_assignments_insert_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN PERFORM 1 FROM staff_versions v JOIN positions p ON p.staff_version_id=v.id WHERE p.position_id=NEW.staff_position_id FOR SHARE OF v; IF NOT EXISTS (
   SELECT 1 FROM positions p JOIN staff_versions v ON v.id=p.staff_version_id
   WHERE p.position_id=NEW.staff_position_id AND NEW.assigned_from>=v.valid_from
   AND (v.valid_to IS NULL OR (NEW.assigned_to IS NOT NULL AND NEW.assigned_to<=v.valid_to))
 ) THEN RAISE EXCEPTION 'assignment outside version period' USING ERRCODE='23514'; END IF;
IF EXISTS (
   SELECT 1 FROM person_assignments a WHERE a.id != NEW.id
   AND (a.person_id=NEW.person_id OR a.staff_position_id=NEW.staff_position_id)
   AND a.assigned_from<=coalesce(NEW.assigned_to,'9999-12-31')
   AND NEW.assigned_from<=coalesce(a.assigned_to,'9999-12-31')
 ) THEN RAISE EXCEPTION 'assignment periods overlap' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER guard_person_assignments_insert BEFORE INSERT ON person_assignments FOR EACH ROW EXECUTE FUNCTION guard_person_assignments_insert_fn();
CREATE FUNCTION guard_person_assignments_update_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN PERFORM 1 FROM staff_versions v JOIN positions p ON p.staff_version_id=v.id WHERE p.position_id=NEW.staff_position_id FOR SHARE OF v; IF NOT EXISTS (
   SELECT 1 FROM positions p JOIN staff_versions v ON v.id=p.staff_version_id
   WHERE p.position_id=NEW.staff_position_id AND NEW.assigned_from>=v.valid_from
   AND (v.valid_to IS NULL OR (NEW.assigned_to IS NOT NULL AND NEW.assigned_to<=v.valid_to))
 ) THEN RAISE EXCEPTION 'assignment outside version period' USING ERRCODE='23514'; END IF;
IF EXISTS (
   SELECT 1 FROM person_assignments a WHERE a.id != NEW.id
   AND (a.person_id=NEW.person_id OR a.staff_position_id=NEW.staff_position_id)
   AND a.assigned_from<=coalesce(NEW.assigned_to,'9999-12-31')
   AND NEW.assigned_from<=coalesce(a.assigned_to,'9999-12-31')
 ) THEN RAISE EXCEPTION 'assignment periods overlap' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER guard_person_assignments_update BEFORE UPDATE ON person_assignments FOR EACH ROW EXECUTE FUNCTION guard_person_assignments_update_fn();
CREATE FUNCTION guard_person_assignments_delete_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF TRUE THEN RAISE EXCEPTION 'historical records cannot be deleted' USING ERRCODE='23514'; END IF; RETURN OLD; END $guard$;
CREATE TRIGGER guard_person_assignments_delete BEFORE DELETE ON person_assignments FOR EACH ROW EXECUTE FUNCTION guard_person_assignments_delete_fn();
CREATE FUNCTION guard_position_version_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF OLD.staff_version_id != NEW.staff_version_id THEN RAISE EXCEPTION 'position version is immutable' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER guard_position_version BEFORE UPDATE OF staff_version_id ON positions FOR EACH ROW EXECUTE FUNCTION guard_position_version_fn();
CREATE FUNCTION guard_position_delete_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF TRUE THEN RAISE EXCEPTION 'historical positions cannot be deleted' USING ERRCODE='23514'; END IF; RETURN OLD; END $guard$;
CREATE TRIGGER guard_position_delete BEFORE DELETE ON positions FOR EACH ROW EXECUTE FUNCTION guard_position_delete_fn();
CREATE FUNCTION document_owner_insert_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF (NEW.passport_id IS NOT NULL AND ((SELECT code FROM document_types WHERE id=NEW.document_type_id)!='passport'
        OR NOT EXISTS (SELECT 1 FROM passports p WHERE p.passport_id=NEW.passport_id AND p.person_id=NEW.person_id)))
        OR (NEW.replaces_id IS NOT NULL AND (NEW.replaces_id=NEW.id OR NOT EXISTS
        (SELECT 1 FROM person_documents d WHERE d.id=NEW.replaces_id AND d.person_id=NEW.person_id AND d.document_type_id=NEW.document_type_id))) THEN RAISE EXCEPTION 'document source or replacement belongs to another person/type' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER document_owner_insert BEFORE INSERT ON person_documents FOR EACH ROW EXECUTE FUNCTION document_owner_insert_fn();
CREATE FUNCTION document_presence_insert_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF NEW.presence='NEVER_OBTAINED'
        AND (SELECT is_primary FROM document_types WHERE id=NEW.document_type_id) = true THEN RAISE EXCEPTION 'primary document cannot be never obtained' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER document_presence_insert BEFORE INSERT ON person_document_states FOR EACH ROW EXECUTE FUNCTION document_presence_insert_fn();
CREATE FUNCTION document_details_source_insert_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF EXISTS (SELECT 1 FROM person_documents d JOIN document_types t
        ON t.id=d.document_type_id WHERE d.id=NEW.document_id AND t.code IN ('passport','tax_number')) THEN RAISE EXCEPTION 'use canonical passport or person tax number' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER document_details_source_insert BEFORE INSERT ON document_details FOR EACH ROW EXECUTE FUNCTION document_details_source_insert_fn();
CREATE FUNCTION document_owner_update_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF (NEW.passport_id IS NOT NULL AND ((SELECT code FROM document_types WHERE id=NEW.document_type_id)!='passport'
        OR NOT EXISTS (SELECT 1 FROM passports p WHERE p.passport_id=NEW.passport_id AND p.person_id=NEW.person_id)))
        OR (NEW.replaces_id IS NOT NULL AND (NEW.replaces_id=NEW.id OR NOT EXISTS
        (SELECT 1 FROM person_documents d WHERE d.id=NEW.replaces_id AND d.person_id=NEW.person_id AND d.document_type_id=NEW.document_type_id))) THEN RAISE EXCEPTION 'document source or replacement belongs to another person/type' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER document_owner_update BEFORE UPDATE ON person_documents FOR EACH ROW EXECUTE FUNCTION document_owner_update_fn();
CREATE FUNCTION document_presence_update_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF NEW.presence='NEVER_OBTAINED'
        AND (SELECT is_primary FROM document_types WHERE id=NEW.document_type_id) = true THEN RAISE EXCEPTION 'primary document cannot be never obtained' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER document_presence_update BEFORE UPDATE ON person_document_states FOR EACH ROW EXECUTE FUNCTION document_presence_update_fn();
CREATE FUNCTION document_details_source_update_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF EXISTS (SELECT 1 FROM person_documents d JOIN document_types t
        ON t.id=d.document_type_id WHERE d.id=NEW.document_id AND t.code IN ('passport','tax_number')) THEN RAISE EXCEPTION 'use canonical passport or person tax number' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER document_details_source_update BEFORE UPDATE ON document_details FOR EACH ROW EXECUTE FUNCTION document_details_source_update_fn();
CREATE FUNCTION document_audit_no_update_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF TRUE THEN RAISE EXCEPTION 'document audit is append only' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER document_audit_no_update BEFORE UPDATE ON document_audit FOR EACH ROW EXECUTE FUNCTION document_audit_no_update_fn();
CREATE FUNCTION document_audit_no_delete_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF TRUE THEN RAISE EXCEPTION 'document audit is append only' USING ERRCODE='23514'; END IF; RETURN OLD; END $guard$;
CREATE TRIGGER document_audit_no_delete BEFORE DELETE ON document_audit FOR EACH ROW EXECUTE FUNCTION document_audit_no_delete_fn();
CREATE FUNCTION document_type_presence_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF NEW.is_primary = true AND EXISTS (SELECT 1 FROM person_document_states s WHERE s.document_type_id=NEW.id AND s.presence='NEVER_OBTAINED') THEN RAISE EXCEPTION 'primary document cannot be never obtained' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER document_type_presence BEFORE UPDATE ON document_types FOR EACH ROW EXECUTE FUNCTION document_type_presence_fn();
CREATE FUNCTION medical_exam_owner_insert_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF NEW.injury_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_injuries i WHERE i.id=NEW.injury_id AND i.person_id=NEW.person_id) THEN RAISE EXCEPTION 'invalid medical owner or active selection' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER medical_exam_owner_insert BEFORE INSERT ON person_medical_exams FOR EACH ROW EXECUTE FUNCTION medical_exam_owner_insert_fn();
CREATE FUNCTION medical_exam_owner_update_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF NEW.injury_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_injuries i WHERE i.id=NEW.injury_id AND i.person_id=NEW.person_id) THEN RAISE EXCEPTION 'invalid medical owner or active selection' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER medical_exam_owner_update BEFORE UPDATE ON person_medical_exams FOR EACH ROW EXECUTE FUNCTION medical_exam_owner_update_fn();
CREATE FUNCTION medical_award_owner_insert_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF NEW.injury_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_injuries i WHERE i.id=NEW.injury_id AND i.person_id=NEW.person_id) THEN RAISE EXCEPTION 'invalid medical owner or active selection' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER medical_award_owner_insert BEFORE INSERT ON person_awards FOR EACH ROW EXECUTE FUNCTION medical_award_owner_insert_fn();
CREATE FUNCTION medical_award_owner_update_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF NEW.injury_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_injuries i WHERE i.id=NEW.injury_id AND i.person_id=NEW.person_id) THEN RAISE EXCEPTION 'invalid medical owner or active selection' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER medical_award_owner_update BEFORE UPDATE ON person_awards FOR EACH ROW EXECUTE FUNCTION medical_award_owner_update_fn();
CREATE FUNCTION medical_task_owner_insert_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF (NEW.exam_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_medical_exams e WHERE e.id=NEW.exam_id AND e.person_id=NEW.person_id)) OR (NEW.injury_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_injuries i WHERE i.id=NEW.injury_id AND i.person_id=NEW.person_id)) OR (NEW.award_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_awards a WHERE a.id=NEW.award_id AND a.person_id=NEW.person_id)) THEN RAISE EXCEPTION 'invalid medical owner or active selection' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER medical_task_owner_insert BEFORE INSERT ON personnel_tasks FOR EACH ROW EXECUTE FUNCTION medical_task_owner_insert_fn();
CREATE FUNCTION medical_task_owner_update_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF (NEW.exam_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_medical_exams e WHERE e.id=NEW.exam_id AND e.person_id=NEW.person_id)) OR (NEW.injury_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_injuries i WHERE i.id=NEW.injury_id AND i.person_id=NEW.person_id)) OR (NEW.award_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_awards a WHERE a.id=NEW.award_id AND a.person_id=NEW.person_id)) THEN RAISE EXCEPTION 'invalid medical owner or active selection' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER medical_task_owner_update BEFORE UPDATE ON personnel_tasks FOR EACH ROW EXECUTE FUNCTION medical_task_owner_update_fn();
CREATE FUNCTION medical_selection_insert_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN PERFORM 1 FROM person_medical_exams WHERE id=NEW.exam_id FOR SHARE; IF NEW.exam_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_medical_exams e WHERE e.id=NEW.exam_id AND e.person_id=NEW.person_id AND e.status='COMPLETED') THEN RAISE EXCEPTION 'invalid medical owner or active selection' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER medical_selection_insert BEFORE INSERT ON person_medical_selections FOR EACH ROW EXECUTE FUNCTION medical_selection_insert_fn();
CREATE FUNCTION medical_selection_update_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN PERFORM 1 FROM person_medical_exams WHERE id=NEW.exam_id FOR SHARE; IF NEW.exam_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_medical_exams e WHERE e.id=NEW.exam_id AND e.person_id=NEW.person_id AND e.status='COMPLETED') THEN RAISE EXCEPTION 'invalid medical owner or active selection' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER medical_selection_update BEFORE UPDATE ON person_medical_selections FOR EACH ROW EXECUTE FUNCTION medical_selection_update_fn();
CREATE FUNCTION medical_link_insert_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF (NEW.exam_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_medical_exams r JOIN person_documents d ON d.person_id=r.person_id WHERE r.id=NEW.exam_id AND d.id=NEW.document_id)) OR (NEW.injury_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_injuries r JOIN person_documents d ON d.person_id=r.person_id WHERE r.id=NEW.injury_id AND d.id=NEW.document_id)) OR (NEW.award_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_awards r JOIN person_documents d ON d.person_id=r.person_id WHERE r.id=NEW.award_id AND d.id=NEW.document_id)) THEN RAISE EXCEPTION 'invalid medical owner or active selection' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER medical_link_insert BEFORE INSERT ON medical_document_links FOR EACH ROW EXECUTE FUNCTION medical_link_insert_fn();
CREATE FUNCTION medical_link_update_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF (NEW.exam_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_medical_exams r JOIN person_documents d ON d.person_id=r.person_id WHERE r.id=NEW.exam_id AND d.id=NEW.document_id)) OR (NEW.injury_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_injuries r JOIN person_documents d ON d.person_id=r.person_id WHERE r.id=NEW.injury_id AND d.id=NEW.document_id)) OR (NEW.award_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_awards r JOIN person_documents d ON d.person_id=r.person_id WHERE r.id=NEW.award_id AND d.id=NEW.document_id)) THEN RAISE EXCEPTION 'invalid medical owner or active selection' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER medical_link_update BEFORE UPDATE ON medical_document_links FOR EACH ROW EXECUTE FUNCTION medical_link_update_fn();
CREATE FUNCTION personnel_audit_no_update_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF TRUE THEN RAISE EXCEPTION 'personnel audit is append only' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER personnel_audit_no_update BEFORE UPDATE ON personnel_audit FOR EACH ROW EXECUTE FUNCTION personnel_audit_no_update_fn();
CREATE FUNCTION personnel_audit_no_delete_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF TRUE THEN RAISE EXCEPTION 'personnel audit is append only' USING ERRCODE='23514'; END IF; RETURN OLD; END $guard$;
CREATE TRIGGER personnel_audit_no_delete BEFORE DELETE ON personnel_audit FOR EACH ROW EXECUTE FUNCTION personnel_audit_no_delete_fn();
CREATE FUNCTION medical_exam_no_new_interrupted_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF NEW.status='INTERRUPTED' THEN RAISE EXCEPTION 'plan the exam before interruption' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER medical_exam_no_new_interrupted BEFORE INSERT ON person_medical_exams FOR EACH ROW EXECUTE FUNCTION medical_exam_no_new_interrupted_fn();
CREATE FUNCTION medical_exam_interrupted_history_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF OLD.status='INTERRUPTED' AND NEW.status!='INTERRUPTED' THEN RAISE EXCEPTION 'create a new exam after interruption' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER medical_exam_interrupted_history BEFORE UPDATE ON person_medical_exams FOR EACH ROW EXECUTE FUNCTION medical_exam_interrupted_history_fn();
CREATE FUNCTION medical_selected_exam_update_fn() RETURNS trigger LANGUAGE plpgsql AS $guard$ BEGIN  IF NEW.status!='COMPLETED' AND EXISTS (SELECT 1 FROM person_medical_selections s WHERE s.exam_id=NEW.id) THEN RAISE EXCEPTION 'clear manual selection first' USING ERRCODE='23514'; END IF; RETURN NEW; END $guard$;
CREATE TRIGGER medical_selected_exam_update BEFORE UPDATE ON person_medical_exams FOR EACH ROW EXECUTE FUNCTION medical_selected_exam_update_fn();
ALTER TABLE passports ADD CONSTRAINT pg_date_passport_issued_date CHECK (passport_issued_date IS NULL OR (passport_issued_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE passports ADD CONSTRAINT pg_date_passport_expire_date CHECK (passport_expire_date IS NULL OR (passport_expire_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_addresses ADD CONSTRAINT pg_date_date_start CHECK (date_start IS NULL OR (date_start BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_addresses ADD CONSTRAINT pg_date_date_end CHECK (date_end IS NULL OR (date_end BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_directives ADD CONSTRAINT pg_date_issued_on CHECK (issued_on IS NULL OR (issued_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_dna_samples ADD CONSTRAINT pg_date_collected_on CHECK (collected_on IS NULL OR (collected_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_education ADD CONSTRAINT pg_date_started_on CHECK (started_on IS NULL OR (started_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_education ADD CONSTRAINT pg_date_ended_on CHECK (ended_on IS NULL OR (ended_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_family_members ADD CONSTRAINT pg_date_birth_on CHECK (birth_on IS NULL OR (birth_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_family_members ADD CONSTRAINT pg_date_death_on CHECK (death_on IS NULL OR (death_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_injuries ADD CONSTRAINT pg_date_occurred_on CHECK (occurred_on IS NULL OR (occurred_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_injuries ADD CONSTRAINT pg_date_certificate_on CHECK (certificate_on IS NULL OR (certificate_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_ranks ADD CONSTRAINT pg_date_rank_order_date CHECK (rank_order_date IS NULL OR (rank_order_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_service_bases ADD CONSTRAINT pg_date_mobilization_date CHECK (mobilization_date IS NULL OR (mobilization_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_service_bases ADD CONSTRAINT pg_date_contract_signed_date CHECK (contract_signed_date IS NULL OR (contract_signed_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_service_bases ADD CONSTRAINT pg_date_contract_start_date CHECK (contract_start_date IS NULL OR (contract_start_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_service_bases ADD CONSTRAINT pg_date_enlistment_order_date CHECK (enlistment_order_date IS NULL OR (enlistment_order_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_service_history ADD CONSTRAINT pg_date_position_date CHECK (position_date IS NULL OR (position_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_service_history ADD CONSTRAINT pg_date_order_date CHECK (order_date IS NULL OR (order_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_service_history ADD CONSTRAINT pg_date_end_date CHECK (end_date IS NULL OR (end_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE staff_versions ADD CONSTRAINT pg_date_valid_from CHECK (valid_from IS NULL OR (valid_from BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE staff_versions ADD CONSTRAINT pg_date_valid_to CHECK (valid_to IS NULL OR (valid_to BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_awards ADD CONSTRAINT pg_date_submission_on CHECK (submission_on IS NULL OR (submission_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_awards ADD CONSTRAINT pg_date_refusal_on CHECK (refusal_on IS NULL OR (refusal_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_awards ADD CONSTRAINT pg_date_awarded_on CHECK (awarded_on IS NULL OR (awarded_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_awards ADD CONSTRAINT pg_date_order_on CHECK (order_on IS NULL OR (order_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_events ADD CONSTRAINT pg_date_date_start CHECK (date_start IS NULL OR (date_start BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_events ADD CONSTRAINT pg_date_date_end CHECK (date_end IS NULL OR (date_end BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_events ADD CONSTRAINT pg_date_order_date CHECK (order_date IS NULL OR (order_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_medical_exams ADD CONSTRAINT pg_date_planned_on CHECK (planned_on IS NULL OR (planned_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_medical_exams ADD CONSTRAINT pg_date_issued_on CHECK (issued_on IS NULL OR (issued_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_medical_exams ADD CONSTRAINT pg_date_ended_on CHECK (ended_on IS NULL OR (ended_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_medical_exams ADD CONSTRAINT pg_date_interrupted_on CHECK (interrupted_on IS NULL OR (interrupted_on BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_assignments ADD CONSTRAINT pg_date_assigned_from CHECK (assigned_from IS NULL OR (assigned_from BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_assignments ADD CONSTRAINT pg_date_assigned_to CHECK (assigned_to IS NULL OR (assigned_to BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_assignments ADD CONSTRAINT pg_date_assignment_order_date CHECK (assignment_order_date IS NULL OR (assignment_order_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_assignments ADD CONSTRAINT pg_date_release_order_date CHECK (release_order_date IS NULL OR (release_order_date BETWEEN DATE '0001-01-01' AND DATE '9999-12-31'));
ALTER TABLE person_events ADD CONSTRAINT pg_event_period CHECK(date_end IS NULL OR date_end>=date_start);
CREATE FUNCTION project2_components(d integer,m integer,y integer,partial boolean) RETURNS boolean IMMUTABLE LANGUAGE plpgsql AS $$
BEGIN
 IF d IS NOT NULL AND (d<1 OR d>31) OR m IS NOT NULL AND (m<1 OR m>12) OR y IS NOT NULL AND (y<1 OR y>9999) THEN RETURN FALSE; END IF;
 IF NOT partial AND num_nonnulls(d,m,y) NOT IN (0,3) THEN RETURN FALSE; END IF;
 IF d IS NOT NULL AND m IS NOT NULL THEN PERFORM make_date(coalesce(y,2000),m,d); END IF;
 RETURN TRUE; EXCEPTION WHEN datetime_field_overflow THEN RETURN FALSE; END $$;
ALTER TABLE persons ADD CONSTRAINT pg_parts_birth CHECK(project2_components(birth_day,birth_month,birth_year,true));
ALTER TABLE passports ADD CONSTRAINT pg_parts_passport_issued CHECK(project2_components(passport_issued_day,passport_issued_month,passport_issued_year,true));
ALTER TABLE passports ADD CONSTRAINT pg_parts_passport_expire CHECK(project2_components(passport_expire_day,passport_expire_month,passport_expire_year,true));
ALTER TABLE person_ranks ADD CONSTRAINT pg_parts_rank_order CHECK(project2_components(rank_order_day,rank_order_month,rank_order_year,true));
ALTER TABLE person_service_history ADD CONSTRAINT pg_parts_position CHECK(project2_components(position_day,position_month,position_year,true));
ALTER TABLE person_service_history ADD CONSTRAINT pg_parts_order CHECK(project2_components(order_day,order_month,order_year,true));
ALTER TABLE person_service_history ADD CONSTRAINT pg_parts_end CHECK(project2_components(end_day,end_month,end_year,true));
ALTER TABLE document_details ADD CONSTRAINT pg_parts_issued CHECK(project2_components(issued_day,issued_month,issued_year,false));
ALTER TABLE document_details ADD CONSTRAINT pg_parts_expire CHECK(project2_components(expire_day,expire_month,expire_year,false));
ALTER TABLE document_driving_categories ADD CONSTRAINT pg_parts_start CHECK(project2_components(start_day,start_month,start_year,false));
ALTER TABLE document_driving_categories ADD CONSTRAINT pg_parts_expire CHECK(project2_components(expire_day,expire_month,expire_year,false));
ALTER TABLE passports ADD CONSTRAINT pg_projection_passport_issued CHECK (passport_issued_date IS NOT DISTINCT FROM CASE WHEN num_nonnulls(passport_issued_day,passport_issued_month,passport_issued_year)=3 THEN make_date(passport_issued_year,passport_issued_month,passport_issued_day) ELSE NULL END);
ALTER TABLE passports ADD CONSTRAINT pg_projection_passport_expire CHECK (passport_expire_date IS NOT DISTINCT FROM CASE WHEN num_nonnulls(passport_expire_day,passport_expire_month,passport_expire_year)=3 THEN make_date(passport_expire_year,passport_expire_month,passport_expire_day) ELSE NULL END);
ALTER TABLE person_ranks ADD CONSTRAINT pg_projection_rank_order CHECK (rank_order_date IS NOT DISTINCT FROM CASE WHEN num_nonnulls(rank_order_day,rank_order_month,rank_order_year)=3 THEN make_date(rank_order_year,rank_order_month,rank_order_day) ELSE NULL END);
ALTER TABLE person_service_history ADD CONSTRAINT pg_projection_position CHECK (position_date IS NOT DISTINCT FROM CASE WHEN num_nonnulls(position_day,position_month,position_year)=3 THEN make_date(position_year,position_month,position_day) ELSE NULL END);
ALTER TABLE person_service_history ADD CONSTRAINT pg_projection_order CHECK (order_date IS NOT DISTINCT FROM CASE WHEN num_nonnulls(order_day,order_month,order_year)=3 THEN make_date(order_year,order_month,order_day) ELSE NULL END);
ALTER TABLE person_service_history ADD CONSTRAINT pg_projection_end CHECK (end_date IS NOT DISTINCT FROM CASE WHEN num_nonnulls(end_day,end_month,end_year)=3 THEN make_date(end_year,end_month,end_day) ELSE NULL END);