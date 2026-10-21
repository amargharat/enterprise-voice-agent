-- Generated from design: enterprise-voice-agent-data-design-v1.md (v1)
-- Supporting design: enterprise-voice-agent-system-design-v1.md (v1)
-- Ticket: none
-- Normalize the first seed's policy predicates to the RulesEngine's explicit condition AST.
UPDATE core.policy_rule
SET condition = '{"all":[{"field":"rateType","op":"eq","value":"FLOATING"}]}'::jsonb
WHERE rule_id IN ('PL-PP-004','PL-FC-001') AND version = 1;
