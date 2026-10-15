# Traceability

Each product requirement points at the code that implements it and the test that shows it works.
Rows that are not built yet say **TBD**.

Contract rows (CON-*) are the shared data shapes from Step 1. They are not product features.
Product rows use the same IDs as `FEATURES.md`.

| Requirement | Implementation | Acceptance test |
| --- | --- | --- |
| CON-01 Graph schema | `backend/app/schemas/graph.py`, `frontend/src/types/graph.ts` | `backend/tests/test_contracts.py` (`test_node_keeps_an_uncertain_item_instead_of_dropping_it`, `test_edge_round_trip_keeps_evidence_and_rules`, `test_detail_level_is_only_one_to_three`) |
| CON-02 Confidence and thresholds | `backend/app/config.py`, `backend/app/schemas/confidence.py`, `frontend/src/lib/confidence.ts` | `test_confidence_thresholds_are_ordered`, `test_confidence_level_must_match_score`, `test_frontend_thresholds_match_backend` |
| CON-03 Processing stages | `backend/app/schemas/stages.py`, `frontend/src/types/stages.ts` | `test_stage_order_and_timing` |
| CON-04 Error response | `backend/app/schemas/errors.py`, `frontend/src/types/errors.ts` | `test_error_response_requires_a_request_id` |
| CON-05 Tag report row | `backend/app/schemas/reports.py`, `frontend/src/types/reports.ts` | `test_tag_and_connection_reports_use_public_json_names` |
| CON-06 Connection report row | `backend/app/schemas/reports.py`, `frontend/src/types/reports.ts` | `test_tag_and_connection_reports_use_public_json_names` |
| CON-07 Verification result | `backend/app/schemas/verification.py`, `frontend/src/types/verification.ts` | `test_verified_is_true_only_when_every_defined_check_passes` |
| CON-08 Job and version | `backend/app/schemas/job.py`, `frontend/src/types/job.ts` | `test_version_zero_is_original_and_later_versions_need_a_parent` |
| CON-09 Export metadata | `backend/app/schemas/export.py`, `frontend/src/types/export.ts` | `test_export_metadata_and_answer_key_json` |
| CON-10 Answer key | `backend/app/schemas/answer_key.py`, `frontend/src/types/answerKey.ts` | `test_export_metadata_and_answer_key_json` |
| API-01 Health check | `backend/app/api/health.py`, `backend/app/database.py` | `backend/tests/test_api.py` (`test_health_returns_ok_and_a_request_id`, `test_broken_database_url_reports_failed_without_crashing`) |
| API-02 Error body and request id | `backend/app/api/errors.py`, `backend/app/api/middleware.py` | `test_unknown_route_uses_the_error_schema`, `test_validation_error_uses_the_error_schema`, `test_unexpected_error_uses_the_error_schema` |
| API-03 Jobs and versions tables | `backend/app/models/tables.py`, `backend/app/database.py` | `test_database_tables_are_created_at_startup`, `test_version_zero_is_never_overwritten` |
| SCRIPT-01 PDF vector or scanned verdict | `backend/app/services/pdf_inspect.py`, `scripts/pdf_verdict.py`, `scripts/inspect_pdf.py` | `backend/tests/test_inspect.py` (`test_vector_pdf_is_vector`, `test_embedded_image_pdf_is_scanned`) |
| SCRIPT-02 Excel tag problems | `scripts/excel_checks.py`, `scripts/inspect_excel.py` | `test_excel_reports_empty_and_duplicate_tags` |
| SCRIPT-03 Answer-key template | `data/answer_keys/TEMPLATE.json` | `test_answer_key_template_matches_the_contract` |
| API-04 Project upload and intake | `backend/app/api/jobs.py`, `backend/app/services/uploads.py` | `backend/tests/test_jobs.py` (`test_valid_upload_stores_safe_names_and_intake`, `test_corrupt_pdf_leaves_no_job`, `test_unknown_job_uses_the_standard_error`) |
| T1-01 | `backend/app/api/jobs.py`, `frontend/src/pages/NewProjectPage.tsx` | `backend/tests/test_jobs.py` |
| T1-02 | `backend/app/services/pdf_inspect.py` | `test_vector_pdf_is_vector`, `test_embedded_image_pdf_is_scanned`, `test_scanned_pdf_records_a_warning` |
| T1-03 | TBD | TBD |
| T1-04 | TBD | TBD |
| T1-05 | TBD | TBD |
| T1-06 | TBD | TBD |
| T1-07 | TBD | TBD |
| T1-08 | TBD | TBD |
| T2-01 | TBD | TBD |
| T2-02 | TBD | TBD |
| T2-03 | TBD | TBD |
| T2-04 | TBD | TBD |
| T2-05 | TBD | TBD |
| T2-06 | TBD | TBD |
| T2-07 | TBD | TBD |
| C1 | TBD | TBD |
| C2 | TBD | TBD |
| C3 | TBD | TBD |
| A1 | TBD | TBD |
| A2 | TBD | TBD |
| A3 | TBD | TBD |
| A4 | TBD | TBD |
| C9 | TBD | TBD |
| C5 | TBD | TBD |
| C6 | TBD | TBD |
| C7 | TBD | TBD |
| C8 | TBD | TBD |
| C4 | TBD | TBD |
| B1 | TBD | TBD |
| B2 | TBD | TBD |
| B3 | TBD | TBD |
| B4 | TBD | TBD |
| B5 | TBD | TBD |
| S1 | TBD | TBD |
| S2 | TBD | TBD |
| S3 | TBD | TBD |
| S4 | TBD | TBD |
| S5 | TBD | TBD |
| FUT-01 | TBD | TBD |
| FUT-02 | TBD | TBD |
| FUT-03 | TBD | TBD |
| FUT-04 | TBD | TBD |
