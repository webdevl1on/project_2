-- Frozen Security 1.4 schema, revision 0009.

CREATE TABLE access_templates (
	id SERIAL NOT NULL,
	name VARCHAR(200) NOT NULL,
	is_active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id)
)

;

CREATE TABLE access_audit (
	id SERIAL NOT NULL,
	actor_user_id INTEGER,
	target_user_id INTEGER,
	occurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	operation VARCHAR(40) NOT NULL,
	before JSON NOT NULL,
	after JSON NOT NULL,
	reason VARCHAR(2000) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT access_audit_reason CHECK (length(trim(reason)) BETWEEN 1 AND 2000),
	FOREIGN KEY(actor_user_id) REFERENCES users (id),
	FOREIGN KEY(target_user_id) REFERENCES users (id)
)

;
CREATE INDEX ix_access_audit_target_user_id ON access_audit (target_user_id);

CREATE TABLE access_reviews (
	id SERIAL NOT NULL,
	user_id INTEGER NOT NULL,
	status VARCHAR(10) NOT NULL,
	reason VARCHAR(2000) NOT NULL,
	decision VARCHAR(2000),
	decided_by INTEGER,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT access_review_status CHECK (status IN ('OPEN','RESOLVED')),
	FOREIGN KEY(user_id) REFERENCES users (id),
	FOREIGN KEY(decided_by) REFERENCES users (id)
)

;
CREATE UNIQUE INDEX one_open_access_review ON access_reviews (user_id) WHERE status='OPEN';
CREATE INDEX ix_access_reviews_user_id ON access_reviews (user_id);

CREATE TABLE access_delegations (
	id SERIAL NOT NULL,
	delegator_id INTEGER NOT NULL,
	user_id INTEGER NOT NULL,
	unit_id INTEGER NOT NULL,
	capabilities JSON NOT NULL,
	starts_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	ends_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revoked_at TIMESTAMP WITHOUT TIME ZONE,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT access_delegation_period CHECK (ends_at>starts_at),
	CONSTRAINT access_delegation_not_self CHECK (delegator_id!=user_id),
	FOREIGN KEY(delegator_id) REFERENCES users (id),
	FOREIGN KEY(user_id) REFERENCES users (id),
	FOREIGN KEY(unit_id) REFERENCES org_units (id)
)

;
CREATE INDEX ix_access_delegations_user_id ON access_delegations (user_id);

CREATE TABLE access_template_assignments (
	id SERIAL NOT NULL,
	user_id INTEGER NOT NULL,
	template_id INTEGER NOT NULL,
	unit_id INTEGER NOT NULL,
	starts_at TIMESTAMP WITHOUT TIME ZONE,
	ends_at TIMESTAMP WITHOUT TIME ZONE,
	is_active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT access_template_period CHECK (starts_at IS NULL OR ends_at IS NULL OR ends_at>starts_at),
	FOREIGN KEY(user_id) REFERENCES users (id),
	FOREIGN KEY(template_id) REFERENCES access_templates (id),
	FOREIGN KEY(unit_id) REFERENCES org_units (id)
)

;
CREATE INDEX ix_access_template_assignments_user_id ON access_template_assignments (user_id);

CREATE TABLE position_access_policies (
	id SERIAL NOT NULL,
	position_id INTEGER NOT NULL,
	is_active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (position_id),
	FOREIGN KEY(position_id) REFERENCES positions (position_id)
)

;

CREATE TABLE temporary_access (
	id SERIAL NOT NULL,
	user_id INTEGER NOT NULL,
	position_id INTEGER NOT NULL,
	unit_id INTEGER NOT NULL,
	starts_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	ends_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revoked_at TIMESTAMP WITHOUT TIME ZONE,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT temporary_access_period CHECK (ends_at>starts_at),
	FOREIGN KEY(user_id) REFERENCES users (id),
	FOREIGN KEY(position_id) REFERENCES positions (position_id),
	FOREIGN KEY(unit_id) REFERENCES org_units (id)
)

;
CREATE INDEX ix_temporary_access_user_id ON temporary_access (user_id);

CREATE TABLE access_rules (
	id SERIAL NOT NULL,
	user_id INTEGER,
	template_id INTEGER,
	policy_id INTEGER,
	temporary_id INTEGER,
	scope_type VARCHAR(20) NOT NULL,
	unit_id INTEGER,
	position_id INTEGER,
	person_id INTEGER,
	category VARCHAR(40) NOT NULL,
	action VARCHAR(30) NOT NULL,
	effect VARCHAR(5) NOT NULL,
	starts_at TIMESTAMP WITHOUT TIME ZONE,
	ends_at TIMESTAMP WITHOUT TIME ZONE,
	revoked_at TIMESTAMP WITHOUT TIME ZONE,
	created_by INTEGER NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT access_rule_effect CHECK (effect IN ('ALLOW','DENY')),
	CONSTRAINT access_rule_source CHECK ((CASE WHEN user_id IS NULL THEN 0 ELSE 1 END + CASE WHEN template_id IS NULL THEN 0 ELSE 1 END + CASE WHEN policy_id IS NULL THEN 0 ELSE 1 END + CASE WHEN temporary_id IS NULL THEN 0 ELSE 1 END)=1),
	CONSTRAINT access_rule_scope CHECK ((scope_type IN ('global','relative') AND unit_id IS NULL AND position_id IS NULL AND person_id IS NULL) OR (scope_type='unit' AND unit_id IS NOT NULL AND position_id IS NULL AND person_id IS NULL) OR (scope_type='position' AND position_id IS NOT NULL AND unit_id IS NULL AND person_id IS NULL) OR (scope_type='person' AND person_id IS NOT NULL AND unit_id IS NULL AND position_id IS NULL)),
	CONSTRAINT access_rule_relative CHECK ((scope_type='relative')=(template_id IS NOT NULL OR policy_id IS NOT NULL)),
	CONSTRAINT access_rule_period CHECK (starts_at IS NULL OR ends_at IS NULL OR ends_at>starts_at),
	FOREIGN KEY(user_id) REFERENCES users (id),
	FOREIGN KEY(template_id) REFERENCES access_templates (id),
	FOREIGN KEY(policy_id) REFERENCES position_access_policies (id),
	FOREIGN KEY(temporary_id) REFERENCES temporary_access (id),
	FOREIGN KEY(unit_id) REFERENCES org_units (id),
	FOREIGN KEY(position_id) REFERENCES positions (position_id),
	FOREIGN KEY(person_id) REFERENCES persons (person_id),
	FOREIGN KEY(created_by) REFERENCES users (id)
)

;
CREATE INDEX ix_access_rules_policy_id ON access_rules (policy_id);
CREATE INDEX ix_access_rules_template_id ON access_rules (template_id);
CREATE INDEX ix_access_rules_user_id ON access_rules (user_id);
CREATE INDEX ix_access_rules_temporary_id ON access_rules (temporary_id);
