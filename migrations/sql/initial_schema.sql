
CREATE TABLE document_types (
	id SERIAL NOT NULL,
	code VARCHAR(50) NOT NULL,
	name VARCHAR(200) NOT NULL,
	is_primary BOOLEAN NOT NULL,
	schema_key VARCHAR(50) NOT NULL,
	is_active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (code NOT IN ('passport','tax_number','military','birth_certificate') OR is_primary = true),
	UNIQUE (code)
)

;

CREATE TABLE event_types (
	event_type_id SERIAL NOT NULL,
	event_type VARCHAR NOT NULL,
	event_name VARCHAR NOT NULL,
	event_color VARCHAR,
	event_is_active BOOLEAN,
	event_exclusive BOOLEAN,
	PRIMARY KEY (event_type_id)
)

;

CREATE TABLE geo_sources (
	id VARCHAR(100) NOT NULL,
	metadata_json JSON NOT NULL,
	PRIMARY KEY (id)
)

;

CREATE TABLE geo_units (
	id SERIAL NOT NULL,
	kind VARCHAR(20) NOT NULL,
	name VARCHAR(250) NOT NULL,
	normalized_name VARCHAR(250) NOT NULL,
	parent_id INTEGER,
	iso_code VARCHAR(3),
	katottg_code VARCHAR(25),
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (kind IN ('country','region','district','community','settlement','street')),
	FOREIGN KEY(parent_id) REFERENCES geo_units (id)
)

;
CREATE INDEX ix_geo_units_iso_code ON geo_units (iso_code);
CREATE INDEX ix_geo_units_katottg_code ON geo_units (katottg_code);
CREATE INDEX ix_geo_units_kind ON geo_units (kind);
CREATE INDEX ix_geo_units_normalized_name ON geo_units (normalized_name);
CREATE INDEX ix_geo_units_parent_id ON geo_units (parent_id);

CREATE TABLE name_dictionaries (
	id SERIAL NOT NULL,
	kind VARCHAR(20) NOT NULL,
	sex VARCHAR(6) NOT NULL,
	base_form VARCHAR(100) NOT NULL,
	normalized_key VARCHAR(100) NOT NULL,
	is_verified BOOLEAN NOT NULL,
	nominative VARCHAR(100),
	genitive VARCHAR(100),
	dative VARCHAR(100),
	accusative VARCHAR(100),
	instrumental VARCHAR(100),
	locative VARCHAR(100),
	vocative VARCHAR(100),
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (kind, sex, normalized_key),
	CHECK (kind IN ('surname','name','patronymic')),
	CHECK (sex IN ('male','female'))
)

;
CREATE INDEX ix_name_dictionaries_normalized_key ON name_dictionaries (normalized_key);

CREATE TABLE name_dictionary_imports (
	id VARCHAR(64) NOT NULL,
	digest VARCHAR(64) NOT NULL,
	mode VARCHAR(20) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id)
)

;

CREATE TABLE persons (
	person_id SERIAL NOT NULL,
	sex VARCHAR(6) CHECK (sex IS NULL OR sex IN ('male','female')),
	personal_number VARCHAR(100),
	tax_number VARCHAR,
	birth_day INTEGER,
	birth_month INTEGER,
	birth_year INTEGER,
	PRIMARY KEY (person_id),
	UNIQUE (tax_number)
)

;

CREATE TABLE ranks (
	rank_id SERIAL NOT NULL,
	code VARCHAR NOT NULL,
	nominative VARCHAR NOT NULL,
	genitive VARCHAR NOT NULL,
	dative VARCHAR NOT NULL,
	accusative VARCHAR NOT NULL,
	instrumental VARCHAR NOT NULL,
	locative VARCHAR NOT NULL,
	vocative VARCHAR NOT NULL,
	PRIMARY KEY (rank_id),
	UNIQUE (code)
)

;

CREATE TABLE staff_structures (
	id SERIAL NOT NULL,
	code VARCHAR NOT NULL,
	name VARCHAR NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (code)
)

;

CREATE TABLE tcc_imports (
	id VARCHAR(64) NOT NULL,
	digest VARCHAR(64) NOT NULL,
	mode VARCHAR(10) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id)
)

;

CREATE TABLE tcc_offices (
	id SERIAL NOT NULL,
	official_name VARCHAR(500) NOT NULL,
	normalized_name VARCHAR(500) NOT NULL,
	type VARCHAR(30) NOT NULL,
	region VARCHAR(250),
	settlement VARCHAR(250),
	normalized_region VARCHAR(250) NOT NULL,
	normalized_settlement VARCHAR(250) NOT NULL,
	parent_tcc_id INTEGER,
	is_active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT unique_tcc_identity UNIQUE (normalized_name, normalized_region, normalized_settlement),
	CHECK (type IN ('regional','city','district','united_district','department')),
	CHECK (parent_tcc_id IS NULL OR parent_tcc_id != id),
	CHECK (is_active IN (false,true)),
	CHECK (length(trim(official_name)) BETWEEN 1 AND 500),
	CHECK (region IS NULL OR length(region) <= 250),
	CHECK (settlement IS NULL OR length(settlement) <= 250),
	FOREIGN KEY(parent_tcc_id) REFERENCES tcc_offices (id)
)

;

CREATE TABLE users (
	id SERIAL NOT NULL,
	username VARCHAR(100) NOT NULL,
	display_name VARCHAR(200) NOT NULL,
	password_hash VARCHAR(300) NOT NULL,
	role VARCHAR(20) NOT NULL,
	is_active BOOLEAN NOT NULL,
	failed_attempts INTEGER NOT NULL,
	locked_until TIMESTAMP WITHOUT TIME ZONE,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (role IN ('admin','editor','viewer')),
	UNIQUE (username)
)

;

CREATE TABLE event_subtypes (
	event_subtype_id SERIAL NOT NULL,
	event_type_id INTEGER NOT NULL,
	event_subtype VARCHAR NOT NULL,
	event_subtype_name VARCHAR NOT NULL,
	event_subtype_is_active BOOLEAN,
	PRIMARY KEY (event_subtype_id),
	FOREIGN KEY(event_type_id) REFERENCES event_types (event_type_id)
)

;

CREATE TABLE geo_aliases (
	id SERIAL NOT NULL,
	unit_id INTEGER NOT NULL,
	name VARCHAR(250) NOT NULL,
	normalized_name VARCHAR(250) NOT NULL,
	historical BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(unit_id) REFERENCES geo_units (id)
)

;
CREATE INDEX ix_geo_aliases_normalized_name ON geo_aliases (normalized_name);
CREATE INDEX ix_geo_aliases_unit_id ON geo_aliases (unit_id);

CREATE TABLE geo_city_districts (
	id SERIAL NOT NULL,
	external_id VARCHAR(36) NOT NULL,
	name VARCHAR(250) NOT NULL,
	katottg_code VARCHAR(25) NOT NULL,
	settlement_id INTEGER NOT NULL,
	source_id VARCHAR(100) NOT NULL,
	source_version VARCHAR(30) NOT NULL,
	package_digest VARCHAR(64) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (external_id),
	UNIQUE (katottg_code),
	FOREIGN KEY(settlement_id) REFERENCES geo_units (id),
	FOREIGN KEY(source_id) REFERENCES geo_sources (id)
)

;
CREATE INDEX ix_geo_city_districts_settlement_id ON geo_city_districts (settlement_id);

CREATE TABLE geo_import_links (
	id SERIAL NOT NULL,
	kind VARCHAR(20) NOT NULL,
	external_id VARCHAR(36) NOT NULL,
	unit_id INTEGER NOT NULL,
	source_id VARCHAR(100) NOT NULL,
	source_version VARCHAR(30) NOT NULL,
	package_digest VARCHAR(64) NOT NULL,
	details JSON NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (kind, external_id),
	FOREIGN KEY(unit_id) REFERENCES geo_units (id),
	FOREIGN KEY(source_id) REFERENCES geo_sources (id)
)

;
CREATE INDEX ix_geo_import_links_unit_id ON geo_import_links (unit_id);

CREATE TABLE passports (
	passport_id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	passport_type VARCHAR,
	passport_series VARCHAR,
	passport_number VARCHAR,
	passport_issued_by VARCHAR,
	passport_issued_day INTEGER,
	passport_issued_month INTEGER,
	passport_issued_year INTEGER,
	passport_expire_day INTEGER,
	passport_expire_month INTEGER,
	passport_expire_year INTEGER,
	passport_issued_date DATE,
	passport_expire_date DATE,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	is_active BOOLEAN NOT NULL,
	PRIMARY KEY (passport_id),
	FOREIGN KEY(person_id) REFERENCES persons (person_id)
)

;
CREATE INDEX ix_passports_person_id ON passports (person_id);

CREATE TABLE person_addresses (
	id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	kind VARCHAR(20) NOT NULL,
	is_active BOOLEAN NOT NULL,
	date_start DATE,
	date_end DATE,
	street_id INTEGER,
	street VARCHAR(250),
	street_type VARCHAR(250),
	house VARCHAR(250),
	corps VARCHAR(250),
	building VARCHAR(250),
	apartment VARCHAR(250),
	room VARCHAR(250),
	postal_code VARCHAR(250),
	note VARCHAR(1000),
	country VARCHAR(250),
	country_id INTEGER,
	region VARCHAR(250),
	region_id INTEGER,
	district VARCHAR(250),
	district_id INTEGER,
	community VARCHAR(250),
	community_id INTEGER,
	settlement VARCHAR(250),
	settlement_id INTEGER,
	settlement_type VARCHAR(60),
	validation_status VARCHAR(10) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (kind IN ('registration','actual','correspondence')),
	CHECK (date_end IS NULL OR date_start IS NULL OR date_end >= date_start),
	FOREIGN KEY(person_id) REFERENCES persons (person_id),
	FOREIGN KEY(street_id) REFERENCES geo_units (id) ON DELETE SET NULL,
	FOREIGN KEY(country_id) REFERENCES geo_units (id) ON DELETE SET NULL,
	FOREIGN KEY(region_id) REFERENCES geo_units (id) ON DELETE SET NULL,
	FOREIGN KEY(district_id) REFERENCES geo_units (id) ON DELETE SET NULL,
	FOREIGN KEY(community_id) REFERENCES geo_units (id) ON DELETE SET NULL,
	FOREIGN KEY(settlement_id) REFERENCES geo_units (id) ON DELETE SET NULL
)

;
CREATE INDEX ix_person_addresses_person_id ON person_addresses (person_id);
CREATE UNIQUE INDEX one_active_address ON person_addresses (person_id, kind) WHERE is_active = true;

CREATE TABLE person_birthplaces (
	id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	country VARCHAR(250),
	country_id INTEGER,
	region VARCHAR(250),
	region_id INTEGER,
	district VARCHAR(250),
	district_id INTEGER,
	community VARCHAR(250),
	community_id INTEGER,
	settlement VARCHAR(250),
	settlement_id INTEGER,
	settlement_type VARCHAR(60),
	validation_status VARCHAR(10) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (person_id),
	FOREIGN KEY(person_id) REFERENCES persons (person_id),
	FOREIGN KEY(country_id) REFERENCES geo_units (id) ON DELETE SET NULL,
	FOREIGN KEY(region_id) REFERENCES geo_units (id) ON DELETE SET NULL,
	FOREIGN KEY(district_id) REFERENCES geo_units (id) ON DELETE SET NULL,
	FOREIGN KEY(community_id) REFERENCES geo_units (id) ON DELETE SET NULL,
	FOREIGN KEY(settlement_id) REFERENCES geo_units (id) ON DELETE SET NULL
)

;

CREATE TABLE person_contacts (
	id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	contact_type VARCHAR(10) NOT NULL,
	value VARCHAR(320) NOT NULL,
	normalized_value VARCHAR(320) NOT NULL,
	label VARCHAR(100),
	note VARCHAR(1000),
	is_primary BOOLEAN NOT NULL,
	is_active BOOLEAN NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (contact_type IN ('phone','email')),
	CHECK (length(trim(value)) > 0 AND length(normalized_value) > 0),
	CHECK (NOT is_primary OR is_active),
	CHECK (is_primary IN (false,true) AND is_active IN (false,true)),
	FOREIGN KEY(person_id) REFERENCES persons (person_id)
)

;
CREATE INDEX ix_person_contacts_person_id ON person_contacts (person_id);
CREATE UNIQUE INDEX one_primary_contact ON person_contacts (person_id, contact_type) WHERE is_active = true AND is_primary = true;
CREATE UNIQUE INDEX unique_active_contact ON person_contacts (person_id, contact_type, normalized_value) WHERE is_active = true;

CREATE TABLE person_directives (
	id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	number VARCHAR(300),
	issued_on DATE,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (number IS NULL OR length(number) <= 300),
	CHECK (issued_on IS NOT NULL OR (number IS NOT NULL AND length(trim(number)) > 0)),
	FOREIGN KEY(person_id) REFERENCES persons (person_id)
)

;
CREATE INDEX ix_person_directives_person_id ON person_directives (person_id);

CREATE TABLE person_dna_samples (
	envelope_number VARCHAR(150),
	collected_on DATE NOT NULL,
	storage_unit VARCHAR(250),
	person_id INTEGER NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(person_id) REFERENCES persons (person_id)
)

;
CREATE INDEX ix_person_dna_samples_person_id ON person_dna_samples (person_id);

CREATE TABLE person_document_states (
	id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	document_type_id INTEGER NOT NULL,
	presence VARCHAR(20) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (person_id, document_type_id),
	CHECK (presence IN ('PRESENT','NEVER_OBTAINED','UNKNOWN')),
	FOREIGN KEY(person_id) REFERENCES persons (person_id),
	FOREIGN KEY(document_type_id) REFERENCES document_types (id)
)

;

CREATE TABLE person_education (
	id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	level_code VARCHAR(40) NOT NULL,
	started_on DATE,
	ended_on DATE,
	institution VARCHAR(500),
	faculty VARCHAR(500),
	specialty VARCHAR(500),
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (length(trim(level_code)) > 0),
	CHECK (ended_on IS NULL OR started_on IS NULL OR ended_on >= started_on),
	FOREIGN KEY(person_id) REFERENCES persons (person_id)
)

;
CREATE INDEX ix_person_education_person_id ON person_education (person_id);

CREATE TABLE person_family_members (
	id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	kinship VARCHAR(30) NOT NULL,
	full_name VARCHAR(500) NOT NULL,
	birth_on DATE,
	death_on DATE,
	phone VARCHAR(100),
	address_text VARCHAR(2000),
	street_id INTEGER,
	street VARCHAR(250),
	street_type VARCHAR(250),
	house VARCHAR(250),
	corps VARCHAR(250),
	building VARCHAR(250),
	apartment VARCHAR(250),
	room VARCHAR(250),
	country VARCHAR(250),
	country_id INTEGER,
	region VARCHAR(250),
	region_id INTEGER,
	district VARCHAR(250),
	district_id INTEGER,
	community VARCHAR(250),
	community_id INTEGER,
	settlement VARCHAR(250),
	settlement_id INTEGER,
	settlement_type VARCHAR(60),
	validation_status VARCHAR(10) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (length(trim(full_name)) > 0),
	CHECK (length(trim(kinship)) > 0),
	CHECK (validation_status IN ('matched','mismatch','unknown')),
	CHECK (death_on IS NULL OR birth_on IS NULL OR death_on >= birth_on),
	FOREIGN KEY(person_id) REFERENCES persons (person_id),
	FOREIGN KEY(street_id) REFERENCES geo_units (id) ON DELETE SET NULL,
	FOREIGN KEY(country_id) REFERENCES geo_units (id) ON DELETE SET NULL,
	FOREIGN KEY(region_id) REFERENCES geo_units (id) ON DELETE SET NULL,
	FOREIGN KEY(district_id) REFERENCES geo_units (id) ON DELETE SET NULL,
	FOREIGN KEY(community_id) REFERENCES geo_units (id) ON DELETE SET NULL,
	FOREIGN KEY(settlement_id) REFERENCES geo_units (id) ON DELETE SET NULL
)

;
CREATE INDEX ix_person_family_members_person_id ON person_family_members (person_id);

CREATE TABLE person_injuries (
	occurred_on DATE,
	description VARCHAR(200),
	area VARCHAR(1000),
	circumstances VARCHAR(2000),
	certificate_number VARCHAR(150),
	certificate_on DATE,
	exam_not_needed BOOLEAN NOT NULL,
	person_id INTEGER NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(person_id) REFERENCES persons (person_id)
)

;
CREATE INDEX ix_person_injuries_person_id ON person_injuries (person_id);

CREATE TABLE person_names (
	person_name_id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	surname VARCHAR NOT NULL,
	name VARCHAR NOT NULL,
	patronymic VARCHAR,
	surname_latin VARCHAR,
	name_latin VARCHAR,
	patronymic_latin VARCHAR,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	is_active BOOLEAN NOT NULL,
	PRIMARY KEY (person_name_id),
	FOREIGN KEY(person_id) REFERENCES persons (person_id)
)

;
CREATE INDEX ix_person_names_person_id ON person_names (person_id);

CREATE TABLE person_ranks (
	person_rank_id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	rank_id INTEGER NOT NULL,
	rank_order_number VARCHAR,
	rank_order_day INTEGER,
	rank_order_month INTEGER,
	rank_order_year INTEGER,
	rank_order_date DATE,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	is_active BOOLEAN NOT NULL,
	PRIMARY KEY (person_rank_id),
	FOREIGN KEY(person_id) REFERENCES persons (person_id),
	FOREIGN KEY(rank_id) REFERENCES ranks (rank_id)
)

;
CREATE INDEX ix_person_ranks_person_id ON person_ranks (person_id);

CREATE TABLE person_service_bases (
	id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	service_type VARCHAR(20) NOT NULL,
	is_current BOOLEAN NOT NULL,
	mobilization_date DATE,
	region VARCHAR(250),
	settlement VARCHAR(250),
	document_tcc_name VARCHAR(500),
	tcc_office_id INTEGER,
	match_status VARCHAR(10) NOT NULL,
	document_verified BOOLEAN NOT NULL,
	contract_signed_date DATE,
	contract_start_date DATE,
	enlistment_order_date DATE,
	enlistment_order_number VARCHAR(100),
	contract_unit VARCHAR(250),
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (service_type IN ('mobilization','contract')),
	CHECK (match_status IN ('matched','mismatch','unknown')),
	CHECK (is_current IN (false,true) AND document_verified IN (false,true)),
	CHECK (document_tcc_name IS NULL OR length(document_tcc_name) <= 500),
	CHECK (region IS NULL OR length(region) <= 250),
	CHECK (settlement IS NULL OR length(settlement) <= 250),
	CHECK (enlistment_order_number IS NULL OR length(enlistment_order_number) <= 100),
	CHECK (contract_unit IS NULL OR length(contract_unit) <= 250),
	CHECK (service_type != 'contract' OR (mobilization_date IS NULL AND region IS NULL AND settlement IS NULL AND document_tcc_name IS NULL AND tcc_office_id IS NULL)),
	CHECK (service_type != 'mobilization' OR (contract_signed_date IS NULL AND contract_start_date IS NULL AND enlistment_order_date IS NULL AND enlistment_order_number IS NULL AND contract_unit IS NULL)),
	FOREIGN KEY(person_id) REFERENCES persons (person_id),
	FOREIGN KEY(tcc_office_id) REFERENCES tcc_offices (id)
)

;
CREATE INDEX ix_person_service_bases_person_id ON person_service_bases (person_id);
CREATE UNIQUE INDEX one_current_service_basis ON person_service_bases (person_id) WHERE is_current = true;

CREATE TABLE person_service_history (
	person_service_history_id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	service_type VARCHAR,
	military_unit VARCHAR,
	position VARCHAR,
	position_day INTEGER,
	position_month INTEGER,
	position_year INTEGER,
	position_date DATE,
	order_number VARCHAR,
	order_day INTEGER,
	order_month INTEGER,
	order_year INTEGER,
	order_date DATE,
	end_day INTEGER,
	end_month INTEGER,
	end_year INTEGER,
	end_date DATE,
	note VARCHAR(1000),
	revision INTEGER NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	is_active BOOLEAN NOT NULL,
	PRIMARY KEY (person_service_history_id),
	FOREIGN KEY(person_id) REFERENCES persons (person_id)
)

;
CREATE INDEX ix_person_service_history_person_id ON person_service_history (person_id);

CREATE TABLE personnel_audit (
	id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	actor_id INTEGER NOT NULL,
	occurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	entity VARCHAR(50) NOT NULL,
	entity_id INTEGER NOT NULL,
	operation VARCHAR(50) NOT NULL,
	changes JSON NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(person_id) REFERENCES persons (person_id),
	FOREIGN KEY(actor_id) REFERENCES users (id)
)

;
CREATE INDEX ix_personnel_audit_person_id ON personnel_audit (person_id);

CREATE TABLE staff_versions (
	id SERIAL NOT NULL,
	staff_structure_id INTEGER NOT NULL,
	name VARCHAR NOT NULL,
	valid_from DATE NOT NULL,
	valid_to DATE,
	import_key VARCHAR,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (valid_to IS NULL OR valid_to >= valid_from),
	UNIQUE (staff_structure_id, name),
	FOREIGN KEY(staff_structure_id) REFERENCES staff_structures (id),
	UNIQUE (import_key)
)

;
CREATE INDEX ix_staff_versions_staff_structure_id ON staff_versions (staff_structure_id);

CREATE TABLE user_sessions (
	token_hash VARCHAR(64) NOT NULL,
	user_id INTEGER NOT NULL,
	csrf_token VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (token_hash),
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;
CREATE INDEX ix_user_sessions_user_id ON user_sessions (user_id);

CREATE TABLE person_awards (
	name VARCHAR(250),
	status VARCHAR(30) NOT NULL,
	injury_id INTEGER,
	submission_on DATE,
	submission_number VARCHAR(150),
	submission_confirmed BOOLEAN NOT NULL,
	refusal_on DATE,
	refusal_number VARCHAR(150),
	refusal_reason VARCHAR(1000),
	refusal_confirmed BOOLEAN NOT NULL,
	awarded_on DATE,
	order_number VARCHAR(150),
	order_on DATE,
	person_id INTEGER NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (status IN ('NOT_PROCESSED','SUBMITTED','WAITING','AWARDED','NOT_APPROPRIATE')),
	CHECK (submission_confirmed = false OR (submission_on IS NOT NULL AND coalesce(length(trim(submission_number)),0)>0)),
	CHECK (refusal_confirmed = false OR (refusal_on IS NOT NULL AND coalesce(length(trim(refusal_number)),0)>0 AND coalesce(length(trim(refusal_reason)),0)>0)),
	FOREIGN KEY(injury_id) REFERENCES person_injuries (id),
	FOREIGN KEY(person_id) REFERENCES persons (person_id)
)

;
CREATE INDEX ix_person_awards_person_id ON person_awards (person_id);

CREATE TABLE person_documents (
	id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	document_type_id INTEGER NOT NULL,
	is_current BOOLEAN NOT NULL,
	passport_id INTEGER,
	replaces_id INTEGER,
	override_status VARCHAR(30),
	override_reason VARCHAR(1000),
	override_user_id INTEGER,
	override_fingerprint VARCHAR(64),
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (is_current IN (false,true)),
	CHECK (override_status IS NULL OR override_status IN ('NOT_FILLED','PARTIALLY_FILLED','FILLED')),
	CHECK (override_status IS NULL OR (length(trim(override_reason)) > 0 AND override_user_id IS NOT NULL)),
	FOREIGN KEY(person_id) REFERENCES persons (person_id),
	FOREIGN KEY(document_type_id) REFERENCES document_types (id),
	UNIQUE (passport_id),
	FOREIGN KEY(passport_id) REFERENCES passports (passport_id),
	UNIQUE (replaces_id),
	FOREIGN KEY(replaces_id) REFERENCES person_documents (id),
	FOREIGN KEY(override_user_id) REFERENCES users (id)
)

;
CREATE INDEX ix_person_documents_document_type_id ON person_documents (document_type_id);
CREATE INDEX ix_person_documents_person_id ON person_documents (person_id);
CREATE UNIQUE INDEX one_current_document ON person_documents (person_id, document_type_id) WHERE is_current = true;

CREATE TABLE person_events (
	event_id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	event_type_id INTEGER NOT NULL,
	event_subtype_id INTEGER,
	date_start DATE NOT NULL,
	duration INTEGER,
	date_end DATE,
	order_date DATE,
	order_number VARCHAR,
	purpose VARCHAR,
	location TEXT,
	note TEXT,
	event_status VARCHAR,
	PRIMARY KEY (event_id),
	FOREIGN KEY(person_id) REFERENCES persons (person_id),
	FOREIGN KEY(event_type_id) REFERENCES event_types (event_type_id),
	FOREIGN KEY(event_subtype_id) REFERENCES event_subtypes (event_subtype_id)
)

;
CREATE INDEX ix_person_events_date_start ON person_events (date_start);
CREATE INDEX ix_person_events_event_subtype_id ON person_events (event_subtype_id);
CREATE INDEX ix_person_events_event_type_id ON person_events (event_type_id);
CREATE INDEX ix_person_events_person_id ON person_events (person_id);

CREATE TABLE person_medical_exams (
	status VARCHAR(20) NOT NULL,
	basis VARCHAR(20) NOT NULL,
	basis_note VARCHAR(2000),
	injury_id INTEGER,
	planned_on DATE,
	issued_on DATE,
	ended_on DATE,
	interrupted_on DATE,
	interruption_reason VARCHAR(2000),
	number VARCHAR(150),
	institution VARCHAR(1000),
	diagnosis VARCHAR(2000),
	fitness VARCHAR(20),
	person_id INTEGER NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (status IN ('NEEDS_EXAM','PLANNED','COMPLETED','INTERRUPTED')),
	CHECK (basis IN ('INJURY','ILLNESS','OTHER')),
	CHECK (fitness IS NULL OR fitness IN ('FIT','FIT_SUPPORT','UNFIT')),
	CHECK (injury_id IS NULL OR basis='INJURY'),
	FOREIGN KEY(injury_id) REFERENCES person_injuries (id),
	FOREIGN KEY(person_id) REFERENCES persons (person_id)
)

;
CREATE INDEX ix_person_medical_exams_person_id ON person_medical_exams (person_id);

CREATE TABLE person_name_cases (
	id SERIAL NOT NULL,
	person_name_id INTEGER NOT NULL,
	kind VARCHAR(20) NOT NULL,
	base_form VARCHAR(100) NOT NULL,
	sex VARCHAR(6),
	is_verified BOOLEAN NOT NULL,
	nominative VARCHAR(100),
	genitive VARCHAR(100),
	dative VARCHAR(100),
	accusative VARCHAR(100),
	instrumental VARCHAR(100),
	locative VARCHAR(100),
	vocative VARCHAR(100),
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (person_name_id, kind),
	CHECK (kind IN ('surname','name','patronymic')),
	CHECK (sex IS NULL OR sex IN ('male','female')),
	FOREIGN KEY(person_name_id) REFERENCES person_names (person_name_id) ON DELETE CASCADE
)

;
CREATE INDEX ix_person_name_cases_person_name_id ON person_name_cases (person_name_id);

CREATE TABLE positions (
	staff_version_id INTEGER NOT NULL,
	position_id SERIAL NOT NULL,
	position_number INTEGER NOT NULL,
	code VARCHAR NOT NULL,
	unit_short VARCHAR NOT NULL,
	name_short VARCHAR NOT NULL,
	name_nominative VARCHAR NOT NULL,
	name_genitive VARCHAR NOT NULL,
	name_dative VARCHAR NOT NULL,
	name_accusative VARCHAR NOT NULL,
	name_instrumental VARCHAR NOT NULL,
	name_locative VARCHAR NOT NULL,
	name_vocative VARCHAR NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (position_id),
	UNIQUE (staff_version_id, position_number),
	FOREIGN KEY(staff_version_id) REFERENCES staff_versions (id)
)

;
CREATE INDEX ix_positions_staff_version_id ON positions (staff_version_id);

CREATE TABLE document_details (
	document_id INTEGER NOT NULL,
	series VARCHAR(100),
	number VARCHAR(100),
	issued_by VARCHAR(500),
	subtype VARCHAR(100),
	issued_day INTEGER,
	issued_month INTEGER,
	issued_year INTEGER,
	expire_day INTEGER,
	expire_month INTEGER,
	expire_year INTEGER,
	expiry_mode VARCHAR(20) NOT NULL,
	extra JSON NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (document_id),
	CHECK (expiry_mode IN ('unknown','date','unlimited')),
	FOREIGN KEY(document_id) REFERENCES person_documents (id)
)

;

CREATE TABLE document_driving_categories (
	id SERIAL NOT NULL,
	document_id INTEGER NOT NULL,
	category VARCHAR(10) NOT NULL,
	start_day INTEGER,
	start_month INTEGER,
	start_year INTEGER,
	expire_day INTEGER,
	expire_month INTEGER,
	expire_year INTEGER,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (document_id, category),
	FOREIGN KEY(document_id) REFERENCES person_documents (id)
)

;
CREATE INDEX ix_document_driving_categories_document_id ON document_driving_categories (document_id);

CREATE TABLE document_files (
	id SERIAL NOT NULL,
	document_id INTEGER NOT NULL,
	storage_key VARCHAR(64) NOT NULL,
	original_name VARCHAR(250) NOT NULL,
	content_type VARCHAR(100) NOT NULL,
	size INTEGER NOT NULL,
	sha256 VARCHAR(64) NOT NULL,
	side VARCHAR(20) NOT NULL,
	sort_order INTEGER DEFAULT '0' NOT NULL,
	is_removed BOOLEAN NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (side IN ('front','back','page','other')),
	CHECK (size > 0),
	CHECK (sort_order >= 0),
	FOREIGN KEY(document_id) REFERENCES person_documents (id),
	UNIQUE (storage_key)
)

;
CREATE INDEX document_file_order ON document_files (document_id, sort_order, id);
CREATE INDEX ix_document_files_document_id ON document_files (document_id);

CREATE TABLE medical_document_links (
	id SERIAL NOT NULL,
	document_id INTEGER NOT NULL,
	exam_id INTEGER,
	injury_id INTEGER,
	award_id INTEGER,
	category VARCHAR(50) NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK ((CASE WHEN exam_id IS NOT NULL THEN 1 ELSE 0 END)+(CASE WHEN injury_id IS NOT NULL THEN 1 ELSE 0 END)+(CASE WHEN award_id IS NOT NULL THEN 1 ELSE 0 END)=1),
	UNIQUE (document_id, exam_id, category),
	UNIQUE (document_id, injury_id, category),
	UNIQUE (document_id, award_id, category),
	FOREIGN KEY(document_id) REFERENCES person_documents (id),
	FOREIGN KEY(exam_id) REFERENCES person_medical_exams (id),
	FOREIGN KEY(injury_id) REFERENCES person_injuries (id),
	FOREIGN KEY(award_id) REFERENCES person_awards (id)
)

;
CREATE INDEX ix_medical_document_links_document_id ON medical_document_links (document_id);

CREATE TABLE person_assignments (
	id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	staff_position_id INTEGER NOT NULL,
	assigned_from DATE NOT NULL,
	assigned_to DATE,
	assignment_order_number VARCHAR(100),
	assignment_order_date DATE,
	release_order_number VARCHAR(100),
	release_order_date DATE,
	completion_reason VARCHAR(30),
	completion_note VARCHAR(1000),
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (assigned_to IS NULL OR assigned_to >= assigned_from),
	FOREIGN KEY(person_id) REFERENCES persons (person_id),
	FOREIGN KEY(staff_position_id) REFERENCES positions (position_id)
)

;
CREATE INDEX ix_assignment_person_period ON person_assignments (person_id, assigned_from, assigned_to);
CREATE INDEX ix_assignment_position_period ON person_assignments (staff_position_id, assigned_from, assigned_to);
CREATE INDEX ix_person_assignments_person_id ON person_assignments (person_id);
CREATE INDEX ix_person_assignments_staff_position_id ON person_assignments (staff_position_id);

CREATE TABLE person_medical_selections (
	person_id INTEGER NOT NULL,
	exam_id INTEGER,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (person_id),
	FOREIGN KEY(person_id) REFERENCES persons (person_id),
	FOREIGN KEY(exam_id) REFERENCES person_medical_exams (id)
)

;

CREATE TABLE personnel_tasks (
	kind VARCHAR(100) NOT NULL,
	exam_id INTEGER,
	injury_id INTEGER,
	award_id INTEGER,
	title VARCHAR(250) NOT NULL,
	responsible VARCHAR(500),
	note VARCHAR(2000),
	status VARCHAR(20) NOT NULL,
	manual_decision BOOLEAN NOT NULL,
	decision_reason VARCHAR(1000),
	person_id INTEGER NOT NULL,
	id SERIAL NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (status IN ('OPEN','COMPLETED','CANCELLED')),
	CHECK (kind!='injury_award' OR injury_id IS NOT NULL),
	FOREIGN KEY(exam_id) REFERENCES person_medical_exams (id),
	FOREIGN KEY(injury_id) REFERENCES person_injuries (id),
	FOREIGN KEY(award_id) REFERENCES person_awards (id),
	FOREIGN KEY(person_id) REFERENCES persons (person_id)
)

;
CREATE INDEX ix_personnel_tasks_person_id ON personnel_tasks (person_id);
CREATE UNIQUE INDEX one_exam_control_task ON personnel_tasks (exam_id) WHERE kind IN ('injury_vlk','exam_vlk') AND status!='CANCELLED' AND exam_id IS NOT NULL;
CREATE UNIQUE INDEX one_injury_award_task ON personnel_tasks (injury_id) WHERE kind='injury_award';
CREATE UNIQUE INDEX one_injury_vlk_task ON personnel_tasks (injury_id) WHERE kind='injury_vlk';

CREATE TABLE document_audit (
	id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	document_id INTEGER,
	document_type_id INTEGER NOT NULL,
	file_id INTEGER,
	actor_id INTEGER,
	actor_kind VARCHAR(20) NOT NULL,
	occurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	operation VARCHAR(50) NOT NULL,
	changes JSON NOT NULL,
	reason VARCHAR(1000),
	PRIMARY KEY (id),
	CHECK ((actor_kind='user' AND actor_id IS NOT NULL) OR (actor_kind='migration' AND actor_id IS NULL)),
	FOREIGN KEY(person_id) REFERENCES persons (person_id),
	FOREIGN KEY(document_id) REFERENCES person_documents (id),
	FOREIGN KEY(document_type_id) REFERENCES document_types (id),
	FOREIGN KEY(file_id) REFERENCES document_files (id),
	FOREIGN KEY(actor_id) REFERENCES users (id)
)

;
CREATE INDEX ix_document_audit_document_id ON document_audit (document_id);
CREATE INDEX ix_document_audit_person_id ON document_audit (person_id);

CREATE TABLE person_position_mirages (
	id SERIAL NOT NULL,
	person_id INTEGER NOT NULL,
	staff_position_id INTEGER NOT NULL,
	status VARCHAR(20) NOT NULL,
	note VARCHAR(1000),
	cancel_reason VARCHAR(1000),
	converted_assignment_id INTEGER,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	PRIMARY KEY (id),
	CHECK (status IN ('waiting','converted','cancelled')),
	CHECK (status != 'converted' OR converted_assignment_id IS NOT NULL),
	FOREIGN KEY(person_id) REFERENCES persons (person_id),
	FOREIGN KEY(staff_position_id) REFERENCES positions (position_id),
	FOREIGN KEY(converted_assignment_id) REFERENCES person_assignments (id)
)

;
CREATE INDEX ix_person_position_mirages_person_id ON person_position_mirages (person_id);
CREATE INDEX ix_person_position_mirages_staff_position_id ON person_position_mirages (staff_position_id);
CREATE UNIQUE INDEX one_waiting_mirage_per_person ON person_position_mirages (person_id) WHERE status='waiting';
