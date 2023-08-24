
-- create schema

CREATE SCHEMA IF NOT EXISTS active_monitoring;

-- create api table

CREATE TABLE IF NOT EXISTS active_monitoring.api_names(
    api_id SERIAL PRIMARY KEY,
    api_name varchar(50) UNIQUE,
    api_host varchar(100),
    api_vendor varchar(50),
    api_path varchar(500),
    env_type varchar(20)
);

-- create api metrics table

CREATE TABLE IF NOT EXISTS active_monitoring.api_metrics(
    metrics_id SERIAL PRIMARY KEY,
    api_id INT,
    elapsed_time NUMERIC,
    time_stamp TIMESTAMP
);


-- stored procedure
CREATE OR REPLACE FUNCTION active_monitoring.insert_api_metrics(
	api_name character varying(50),  -- api_name
	api_host character varying(100), -- api_host
	api_path character varying(500), -- api_path
	api_vendor character varying(50),  -- api_vendor
	elapsed_time numeric,                -- elapsed_time
	time_stamp timestamp,              -- time_stamp
	env_type character varying(20)   -- env_type
	)
RETURNS BOOLEAN AS $$
DECLARE passed BOOLEAN;
BEGIN

	with s AS (
    	SELECT api_id FROM active_monitoring.api_names WHERE api_names.api_name = $1 AND api_names.env_type = $7
	), i as (
    	INSERT INTO active_monitoring.api_names(api_name, api_host, api_path, api_vendor, env_type)
    	SELECT $1, $2, $3, $4, $7
    		WHERE NOT EXISTS (SELECT 1 FROM s)
    	RETURNING api_id
	)

	INSERT INTO active_monitoring.api_metrics(api_id, elapsed_time, time_stamp)
	SELECT api_id, $5, $6
	FROM i
		UNION ALL
	SELECT api_id, $5, $6
	FROM s;

	RETURN passed;
END;
$$ LANGUAGE plpgsql;

