-- TESTING-13 (review 11 M10): after the skeleton e2e, every project.created and
-- workflow.transitioned event is published by the outbox dispatcher and has its audit_log row
-- (AUDIT-02 writes one per event, keyed by source_event_id). Run it as the Postgres superuser
-- once `python -m aip.platform.events.lag --wait ...` has passed:
--
--   docker compose -f infra/docker-compose.yml exec -T postgres \
--     psql -U postgres -d aip -v ON_ERROR_STOP=1 -f - < infra/docker/check_outbox_audited.sql
DO $$
DECLARE
  created int;
  transitioned int;
  unpublished int;
  unaudited int;
BEGIN
  SELECT count(*) FILTER (WHERE event_name = 'project.created'),
         count(*) FILTER (WHERE event_name = 'workflow.transitioned')
    INTO created, transitioned
    FROM domain_events;
  IF created = 0 OR transitioned = 0 THEN
    RAISE EXCEPTION 'expected project.created and workflow.transitioned events from the journeys, found % and %',
      created, transitioned;
  END IF;

  SELECT count(*) INTO unpublished
    FROM domain_events
   WHERE event_name IN ('project.created', 'workflow.transitioned') AND published_at IS NULL;
  IF unpublished > 0 THEN
    RAISE EXCEPTION '% project.created/workflow.transitioned event(s) have no published_at', unpublished;
  END IF;

  SELECT count(*) INTO unaudited
    FROM domain_events d
   WHERE d.event_name IN ('project.created', 'workflow.transitioned')
     AND NOT EXISTS (SELECT 1 FROM audit_log a WHERE a.source_event_id = d.id);
  IF unaudited > 0 THEN
    RAISE EXCEPTION '% published event(s) have no audit_log row', unaudited;
  END IF;

  RAISE NOTICE 'outbox: % project.created and % workflow.transitioned events, all published and audited',
    created, transitioned;
END $$;
