-- Append-only permission audit and durable source history.
CREATE FUNCTION project2_access_no_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'access history is append only' USING ERRCODE='23514'; END; $$;
CREATE TRIGGER access_audit_no_update BEFORE UPDATE ON access_audit FOR EACH ROW EXECUTE FUNCTION project2_access_no_delete();
CREATE TRIGGER access_audit_no_delete BEFORE DELETE ON access_audit FOR EACH ROW EXECUTE FUNCTION project2_access_no_delete();
CREATE TRIGGER access_rules_no_delete BEFORE DELETE ON access_rules FOR EACH ROW EXECUTE FUNCTION project2_access_no_delete();
CREATE TRIGGER access_templates_no_delete BEFORE DELETE ON access_templates FOR EACH ROW EXECUTE FUNCTION project2_access_no_delete();
CREATE TRIGGER access_template_assignments_no_delete BEFORE DELETE ON access_template_assignments FOR EACH ROW EXECUTE FUNCTION project2_access_no_delete();
CREATE TRIGGER position_access_policies_no_delete BEFORE DELETE ON position_access_policies FOR EACH ROW EXECUTE FUNCTION project2_access_no_delete();
CREATE TRIGGER temporary_access_no_delete BEFORE DELETE ON temporary_access FOR EACH ROW EXECUTE FUNCTION project2_access_no_delete();
CREATE TRIGGER access_delegations_no_delete BEFORE DELETE ON access_delegations FOR EACH ROW EXECUTE FUNCTION project2_access_no_delete();
CREATE TRIGGER access_reviews_no_delete BEFORE DELETE ON access_reviews FOR EACH ROW EXECUTE FUNCTION project2_access_no_delete();
