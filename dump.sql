-- Adminer 5.3.0 PostgreSQL 17.5 dump

DROP TABLE IF EXISTS "outbox";
CREATE TABLE "public"."outbox" (
    "id" uuid DEFAULT gen_random_uuid() NOT NULL,
    "destination" character varying(255) NOT NULL,
    "payload" jsonb NOT NULL,
    "publish_at" timestamptz DEFAULT now() NOT NULL,
    "created_at" timestamptz DEFAULT now(),
    "processed_at" timestamptz,
    CONSTRAINT "outbox_pkey" PRIMARY KEY ("id")
)
WITH (oids = false);

CREATE INDEX idx_outbox_unprocessed ON public.outbox USING btree (processed_at) WHERE (processed_at IS NULL);

INSERT INTO "outbox" ("id", "destination", "payload", "publish_at", "created_at", "processed_at") VALUES
('e3589e72-a173-4221-992c-9dbbc15d913e',	'orchestration_queue',	'{"type": "START_WORKFLOW", "instance_id": "9bae147e-8e22-42bf-bf94-4df5d36a82a8"}',	'2025-08-14 10:59:21.667419+00',	'2025-08-14 10:59:21.667419+00',	'2025-08-14 10:59:22.395577+00'),
('91e0c43b-e691-4729-94f5-eaca92d620b7',	'actions_queue',	'{"action": "fetch_invoice", "instance_id": "9bae147e-8e22-42bf-bf94-4df5d36a82a8"}',	'2025-08-14 10:59:22.90554+00',	'2025-08-14 10:59:22.898581+00',	'2025-08-14 10:59:23.887905+00'),
('98794ee9-3a40-4b3d-996e-43a87b1e1e10',	'orchestration_queue',	'{"step": "fetch_invoice", "type": "STEP_COMPLETE", "instance_id": "9bae147e-8e22-42bf-bf94-4df5d36a82a8"}',	'2025-08-14 10:59:23.91268+00',	'2025-08-14 10:59:23.91268+00',	'2025-08-14 10:59:25.937098+00'),
('bf210878-e500-4474-bab2-8bc1c5586fc8',	'actions_queue',	'{"action": "validate_invoice", "instance_id": "9bae147e-8e22-42bf-bf94-4df5d36a82a8"}',	'2025-08-14 10:59:25.988976+00',	'2025-08-14 10:59:25.960336+00',	'2025-08-14 10:59:26.981216+00'),
('d1215898-9a6c-4c7c-8dbd-3dd4cadce33b',	'orchestration_queue',	'{"step": "validate_invoice", "type": "STEP_FAILED", "instance_id": "9bae147e-8e22-42bf-bf94-4df5d36a82a8"}',	'2025-08-14 10:59:27.011275+00',	'2025-08-14 10:59:27.011275+00',	'2025-08-14 10:59:28.022568+00'),
('ccc0c8d9-c0d1-42b5-badb-51634fef50d7',	'actions_queue',	'{"action": "validate_invoice", "instance_id": "9bae147e-8e22-42bf-bf94-4df5d36a82a8"}',	'2025-08-14 10:59:38.042545+00',	'2025-08-14 10:59:28.039347+00',	'2025-08-14 10:59:38.15472+00'),
('335d096e-87ea-42c1-8be7-fd79e076eb04',	'orchestration_queue',	'{"step": "validate_invoice", "type": "STEP_FAILED", "instance_id": "9bae147e-8e22-42bf-bf94-4df5d36a82a8"}',	'2025-08-14 10:59:38.165878+00',	'2025-08-14 10:59:38.165878+00',	'2025-08-14 10:59:38.175254+00'),
('75302e6b-a9ab-4af0-8bf6-b81b5baf18a0',	'orchestration_queue',	'{"type": "START_WORKFLOW", "instance_id": "74990005-e909-4af2-bcc0-fd41480df2bf"}',	'2025-08-14 11:00:03.666214+00',	'2025-08-14 11:00:03.666214+00',	'2025-08-14 11:00:04.486759+00'),
('5c48a71a-702b-43e5-b764-e8dbfaf1936e',	'actions_queue',	'{"action": "fetch_invoice", "instance_id": "74990005-e909-4af2-bcc0-fd41480df2bf"}',	'2025-08-14 11:00:04.514115+00',	'2025-08-14 11:00:04.511006+00',	'2025-08-14 11:00:04.523457+00'),
('974bb314-fcec-441f-b1ad-ec5b107af3e1',	'orchestration_queue',	'{"step": "fetch_invoice", "type": "STEP_COMPLETE", "instance_id": "74990005-e909-4af2-bcc0-fd41480df2bf"}',	'2025-08-14 11:00:04.548508+00',	'2025-08-14 11:00:04.548508+00',	'2025-08-14 11:00:06.572606+00'),
('9f86d1c5-713d-4058-819b-b1cff2a42741',	'actions_queue',	'{"action": "validate_invoice", "instance_id": "74990005-e909-4af2-bcc0-fd41480df2bf"}',	'2025-08-14 11:00:06.589796+00',	'2025-08-14 11:00:06.587784+00',	'2025-08-14 11:00:07.600256+00'),
('f3f48b03-696c-4371-bdd2-7f4ce8da37d4',	'orchestration_queue',	'{"step": "validate_invoice", "type": "STEP_COMPLETE", "instance_id": "74990005-e909-4af2-bcc0-fd41480df2bf"}',	'2025-08-14 11:00:07.620936+00',	'2025-08-14 11:00:07.620936+00',	'2025-08-14 11:00:08.636293+00'),
('54cc0510-ba1e-43bf-a97c-e8338c02e076',	'actions_queue',	'{"action": "generate_report", "instance_id": "74990005-e909-4af2-bcc0-fd41480df2bf"}',	'2025-08-14 11:00:08.65205+00',	'2025-08-14 11:00:08.64954+00',	'2025-08-14 11:00:08.65894+00'),
('4ae15fcd-509a-4232-abfb-8a7f1064c00f',	'orchestration_queue',	'{"step": "generate_report", "type": "STEP_COMPLETE", "instance_id": "74990005-e909-4af2-bcc0-fd41480df2bf"}',	'2025-08-14 11:00:08.673839+00',	'2025-08-14 11:00:08.673839+00',	'2025-08-14 11:00:09.692677+00'),
('a9362939-6747-4647-8628-ffa3f1f6623e',	'actions_queue',	'{"action": "archive_report", "instance_id": "74990005-e909-4af2-bcc0-fd41480df2bf"}',	'2025-08-14 11:00:09.715391+00',	'2025-08-14 11:00:09.712347+00',	'2025-08-14 11:00:09.723989+00'),
('3e94401e-c0f5-4f34-9be3-823c542d4cc2',	'orchestration_queue',	'{"step": "archive_report", "type": "STEP_COMPLETE", "instance_id": "74990005-e909-4af2-bcc0-fd41480df2bf"}',	'2025-08-14 11:00:11.814453+00',	'2025-08-14 11:00:11.814453+00',	'2025-08-14 11:00:14.803751+00'),
('90c4e856-45b1-404f-afe0-aa719eae82e4',	'orchestration_queue',	'{"type": "START_WORKFLOW", "instance_id": "c3627749-0171-4ce7-a3d0-e40f6bd5a64c"}',	'2025-08-14 12:09:17.579566+00',	'2025-08-14 12:09:17.579566+00',	'2025-08-14 12:09:18.184837+00'),
('7fd6871e-20aa-4bdc-94b4-54a8b7c15e6a',	'actions_queue',	'{"action": "initial_step", "instance_id": "c3627749-0171-4ce7-a3d0-e40f6bd5a64c"}',	'2025-08-14 12:09:18.720247+00',	'2025-08-14 12:09:18.713185+00',	'2025-08-14 12:09:19.691068+00'),
('c1bf465c-98f0-43b4-acf7-a770f84372fb',	'orchestration_queue',	'{"type": "START_WORKFLOW", "instance_id": "15617692-84c4-425d-8341-546d86200170"}',	'2025-08-14 12:12:48.428999+00',	'2025-08-14 12:12:48.428999+00',	'2025-08-14 12:12:48.822364+00'),
('bfd0ec43-f1a3-4815-a1a6-0c2a8d35ffb7',	'actions_queue',	'{"action": "initial_step", "instance_id": "15617692-84c4-425d-8341-546d86200170"}',	'2025-08-14 12:12:49.357341+00',	'2025-08-14 12:12:49.354297+00',	'2025-08-14 12:12:50.352215+00'),
('a27fc798-0ffb-4c53-a127-8a814b31c91f',	'orchestration_queue',	'{"type": "START_WORKFLOW", "instance_id": "9d9f9eb5-0653-4ccd-806c-b230e7dfb476"}',	'2025-08-14 12:24:56.801574+00',	'2025-08-14 12:24:56.801574+00',	'2025-08-14 12:24:57.442391+00'),
('a7e6d2f6-83cf-4a59-9f22-2e05bf09e836',	'actions_queue',	'{"action": "initial_step", "instance_id": "9d9f9eb5-0653-4ccd-806c-b230e7dfb476"}',	'2025-08-14 12:24:58.127324+00',	'2025-08-14 12:24:58.123359+00',	'2025-08-14 12:24:59.114402+00'),
('ffa22ff5-d056-400b-a346-44fdc5190d35',	'orchestration_queue',	'{"step": "initial_step", "type": "STEP_COMPLETE", "instance_id": "9d9f9eb5-0653-4ccd-806c-b230e7dfb476"}',	'2025-08-14 12:24:59.151471+00',	'2025-08-14 12:24:59.151471+00',	'2025-08-14 12:25:00.162814+00'),
('93f55fc1-e8b5-4dff-ad89-3147ce903eb8',	'actions_queue',	'{"action": "wait_15_seconds", "instance_id": "9d9f9eb5-0653-4ccd-806c-b230e7dfb476"}',	'2025-08-14 12:25:00.198962+00',	'2025-08-14 12:25:00.195266+00',	'2025-08-14 12:25:01.213292+00'),
('d844db3b-0c3e-4f78-ad90-018c1369a812',	'orchestration_queue',	'{"type": "STEP_COMPLETE", "instance_id": "9d9f9eb5-0653-4ccd-806c-b230e7dfb476"}',	'2025-08-14 12:25:16.259534+00',	'2025-08-14 12:25:01.276042+00',	'2025-08-14 12:25:16.514604+00'),
('403e7b55-c565-4211-83d6-7da29b0d7726',	'actions_queue',	'{"action": "final_step", "instance_id": "9d9f9eb5-0653-4ccd-806c-b230e7dfb476"}',	'2025-08-14 12:25:16.540524+00',	'2025-08-14 12:25:16.537359+00',	'2025-08-14 12:25:16.543378+00'),
('082916c2-7b27-4262-afb4-f2fd10790706',	'orchestration_queue',	'{"step": "final_step", "type": "STEP_COMPLETE", "instance_id": "9d9f9eb5-0653-4ccd-806c-b230e7dfb476"}',	'2025-08-14 12:25:16.56574+00',	'2025-08-14 12:25:16.56574+00',	'2025-08-14 12:25:17.582626+00'),
('a7762117-1074-4e82-a877-27b800c3546a',	'orchestration_queue',	'{"type": "START_WORKFLOW", "instance_id": "d6e5b679-7f91-4ea5-ba24-f4a4a5b8c0e3"}',	'2025-08-14 16:11:00.575485+00',	'2025-08-14 16:11:00.575485+00',	'2025-08-14 16:11:01.534005+00'),
('51fc5e20-b885-476a-aace-063c467f8569',	'actions_queue',	'{"action": "initial_step", "instance_id": "d6e5b679-7f91-4ea5-ba24-f4a4a5b8c0e3"}',	'2025-08-14 16:11:02.436978+00',	'2025-08-14 16:11:02.433443+00',	'2025-08-14 16:11:03.433825+00'),
('52ccf05c-5452-42ec-a6c9-1497e7c25293',	'orchestration_queue',	'{"step": "initial_step", "type": "STEP_COMPLETE", "instance_id": "d6e5b679-7f91-4ea5-ba24-f4a4a5b8c0e3"}',	'2025-08-14 16:11:03.46883+00',	'2025-08-14 16:11:03.46883+00',	'2025-08-14 16:11:04.46974+00'),
('6c0f4cb8-0b1e-49d2-bfc4-cba99f135ec1',	'actions_queue',	'{"action": "wait_15_seconds", "instance_id": "d6e5b679-7f91-4ea5-ba24-f4a4a5b8c0e3"}',	'2025-08-14 16:11:04.493428+00',	'2025-08-14 16:11:04.49025+00',	'2025-08-14 16:11:05.503619+00'),
('0b14f52b-284b-40d4-adb5-b6f087552884',	'orchestration_queue',	'{"type": "STEP_COMPLETE", "instance_id": "d6e5b679-7f91-4ea5-ba24-f4a4a5b8c0e3"}',	'2025-08-14 16:11:20.529653+00',	'2025-08-14 16:11:05.539757+00',	'2025-08-14 16:11:20.722683+00'),
('5fc69c13-7f02-427d-9924-51bd45679b1c',	'actions_queue',	'{"action": "final_step", "instance_id": "d6e5b679-7f91-4ea5-ba24-f4a4a5b8c0e3"}',	'2025-08-14 16:11:20.741899+00',	'2025-08-14 16:11:20.739726+00',	'2025-08-14 16:11:21.754607+00'),
('a1fcbfdb-42a9-49a3-9dff-8b7f110c273c',	'orchestration_queue',	'{"step": "final_step", "type": "STEP_COMPLETE", "instance_id": "d6e5b679-7f91-4ea5-ba24-f4a4a5b8c0e3"}',	'2025-08-14 16:11:21.76997+00',	'2025-08-14 16:11:21.76997+00',	'2025-08-14 16:11:22.785373+00'),
('6c4ab199-870e-446d-a63c-c1386ab5903d',	'orchestration_queue',	'{"type": "START_WORKFLOW", "instance_id": "4b9ae271-e48f-4fce-aae7-dd26327a3cc0"}',	'2025-08-14 18:29:01.809781+00',	'2025-08-14 18:29:01.809781+00',	'2025-08-14 18:29:02.605174+00'),
('55b25271-b3c5-4614-b15c-a45ad11fe2c9',	'actions_queue',	'{"action": "initial_step", "instance_id": "4b9ae271-e48f-4fce-aae7-dd26327a3cc0"}',	'2025-08-14 18:29:02.909999+00',	'2025-08-14 18:29:02.906525+00',	'2025-08-14 18:29:03.895164+00'),
('92da9275-91fb-4989-bb14-5150374eec6e',	'orchestration_queue',	'{"step": "initial_step", "type": "STEP_COMPLETE", "instance_id": "4b9ae271-e48f-4fce-aae7-dd26327a3cc0"}',	'2025-08-14 18:29:03.92523+00',	'2025-08-14 18:29:03.92523+00',	'2025-08-14 18:29:04.938972+00'),
('d4f2cc28-c20f-488b-8ac4-ac61dd0c939e',	'actions_queue',	'{"action": "wait_15_seconds", "instance_id": "4b9ae271-e48f-4fce-aae7-dd26327a3cc0"}',	'2025-08-14 18:29:04.963441+00',	'2025-08-14 18:29:04.96033+00',	'2025-08-14 18:29:05.978407+00'),
('1c8e06b4-246c-4c1e-962a-ad27cb322715',	'orchestration_queue',	'{"type": "STEP_COMPLETE", "instance_id": "4b9ae271-e48f-4fce-aae7-dd26327a3cc0"}',	'2025-08-14 18:29:21.008306+00',	'2025-08-14 18:29:06.03412+00',	'2025-08-14 18:29:21.233875+00'),
('fc44d7ce-9325-408a-a224-0d00e293da8f',	'actions_queue',	'{"action": "final_step", "instance_id": "4b9ae271-e48f-4fce-aae7-dd26327a3cc0"}',	'2025-08-14 18:29:21.259618+00',	'2025-08-14 18:29:21.25624+00',	'2025-08-14 18:29:22.272098+00'),
('0268580a-291e-4bf9-9c25-95aa64a5d384',	'orchestration_queue',	'{"step": "final_step", "type": "STEP_COMPLETE", "instance_id": "4b9ae271-e48f-4fce-aae7-dd26327a3cc0"}',	'2025-08-14 18:29:22.296549+00',	'2025-08-14 18:29:22.296549+00',	'2025-08-14 18:29:22.307347+00'),
('eebd7c52-98c8-4b36-97c4-6c83e5f3b05a',	'orchestration_queue',	'{"type": "START_WORKFLOW", "instance_id": "ec2a94fd-f789-41b8-ab38-4e3612219ce7"}',	'2025-08-14 18:46:53.341962+00',	'2025-08-14 18:46:53.341962+00',	'2025-08-14 18:46:53.98968+00'),
('96856938-91f1-4e87-a3f8-178bf668bab6',	'actions_queue',	'{"action": "fetch_invoice", "instance_id": "ec2a94fd-f789-41b8-ab38-4e3612219ce7"}',	'2025-08-14 18:46:54.221771+00',	'2025-08-14 18:46:54.218094+00',	'2025-08-14 18:46:55.22099+00'),
('0ffcf634-52c4-4d2c-bf7c-6047bb9fc0fb',	'orchestration_queue',	'{"step": "fetch_invoice", "type": "STEP_COMPLETE", "instance_id": "ec2a94fd-f789-41b8-ab38-4e3612219ce7"}',	'2025-08-14 18:46:55.245992+00',	'2025-08-14 18:46:55.245992+00',	'2025-08-14 18:46:58.368148+00'),
('c832ccc8-5b22-4b85-b3d4-7bb8bac7ef82',	'actions_queue',	'{"action": "validate_invoice", "instance_id": "ec2a94fd-f789-41b8-ab38-4e3612219ce7"}',	'2025-08-14 18:46:58.400408+00',	'2025-08-14 18:46:58.397072+00',	'2025-08-14 18:46:59.540739+00'),
('da4c23aa-91f2-4203-b1d5-5dbe2bca0204',	'orchestration_queue',	'{"step": "validate_invoice", "type": "STEP_COMPLETE", "instance_id": "ec2a94fd-f789-41b8-ab38-4e3612219ce7"}',	'2025-08-14 18:46:59.607237+00',	'2025-08-14 18:46:59.607237+00',	'2025-08-14 18:47:00.813298+00'),
('69ca0c46-97fe-42c6-a19e-b939b5682ef8',	'actions_queue',	'{"action": "generate_report", "instance_id": "ec2a94fd-f789-41b8-ab38-4e3612219ce7"}',	'2025-08-14 18:47:00.972541+00',	'2025-08-14 18:47:00.96865+00',	'2025-08-14 18:47:02.069113+00'),
('481e511a-8ab6-47d1-8f8f-de193312d6a3',	'orchestration_queue',	'{"step": "generate_report", "type": "STEP_COMPLETE", "instance_id": "ec2a94fd-f789-41b8-ab38-4e3612219ce7"}',	'2025-08-14 18:47:02.101458+00',	'2025-08-14 18:47:02.101458+00',	'2025-08-14 18:47:03.237803+00'),
('3f497739-dbce-449c-93ee-5b4e38488b97',	'actions_queue',	'{"action": "archive_report", "instance_id": "ec2a94fd-f789-41b8-ab38-4e3612219ce7"}',	'2025-08-14 18:47:04.275658+00',	'2025-08-14 18:47:04.271826+00',	'2025-08-14 18:47:05.429232+00'),
('ac3a15a8-7383-4094-be67-c7a2efaca694',	'orchestration_queue',	'{"step": "archive_report", "type": "STEP_COMPLETE", "instance_id": "ec2a94fd-f789-41b8-ab38-4e3612219ce7"}',	'2025-08-14 18:47:07.088949+00',	'2025-08-14 18:47:07.088949+00',	'2025-08-14 18:47:09.958877+00');

DROP TABLE IF EXISTS "workflow_definitions";
DROP SEQUENCE IF EXISTS workflow_definitions_id_seq;
CREATE SEQUENCE workflow_definitions_id_seq INCREMENT 1 MINVALUE 1 MAXVALUE 2147483647 CACHE 1;

CREATE TABLE "public"."workflow_definitions" (
    "id" integer DEFAULT nextval('workflow_definitions_id_seq') NOT NULL,
    "name" character varying(255) NOT NULL,
    "definition" jsonb NOT NULL,
    "is_active" boolean DEFAULT true,
    CONSTRAINT "workflow_definitions_pkey" PRIMARY KEY ("id")
)
WITH (oids = false);

CREATE UNIQUE INDEX workflow_definitions_name_key ON public.workflow_definitions USING btree (name);

INSERT INTO "workflow_definitions" ("id", "name", "definition", "is_active") VALUES
(1,	'invoice_approval',	'{"steps": {"fetch_invoice": {"next": "validate_invoice"}, "archive_report": {"next": "end", "retry": {"max_attempts": 3, "delay_seconds": 5}}, "generate_report": {"next": "archive_report"}, "validate_invoice": {"next": "generate_report", "retry": {"max_attempts": 2, "delay_seconds": 10}}}, "start_at": "fetch_invoice", "description": "A simple invoice approval flow."}',	'1'),
(2,	'short_delay',	'{"steps": {"final_step": {"next": "end"}, "initial_step": {"next": "wait_15_seconds"}, "wait_15_seconds": {"next": "final_step", "type": "delay", "duration_seconds": 15}}, "start_at": "initial_step", "description": "A flow for testing a short delay."}',	'1');

DROP TABLE IF EXISTS "workflow_instances";
CREATE TABLE "public"."workflow_instances" (
    "id" uuid DEFAULT gen_random_uuid() NOT NULL,
    "definition_id" integer,
    "status" character varying(50) NOT NULL,
    "current_step" character varying(100),
    "current_step_attempts" integer DEFAULT '0',
    "data" jsonb,
    "history" jsonb,
    "created_at" timestamptz DEFAULT now(),
    "updated_at" timestamptz DEFAULT now(),
    CONSTRAINT "workflow_instances_pkey" PRIMARY KEY ("id")
)
WITH (oids = false);

INSERT INTO "workflow_instances" ("id", "definition_id", "status", "current_step", "current_step_attempts", "data", "history", "created_at", "updated_at") VALUES
('74990005-e909-4af2-bcc0-fd41480df2bf',	1,	'SUCCEEDED',	'archive_report',	1,	'{"is_valid": true, "invoice_details": {"amount": 1200, "customer": "Big Corp"}, "source_invoice_id": "inv-retry-path", "report_archive_path": "s3://bucket/74990005-e909-4af2-bcc0-fd41480df2bf/report.txt"}',	'[{"step": "fetch_invoice", "status": "succeeded", "timestamp": 1755169206.5514202}, {"step": "validate_invoice", "status": "succeeded", "timestamp": 1755169207.6239097}, {"step": "generate_report", "status": "succeeded", "timestamp": 1755169208.6759498}, {"step": "archive_report", "status": "succeeded", "timestamp": 1755169213.8168771}]',	'2025-08-14 11:00:03.666214+00',	'2025-08-14 11:00:14.824779+00'),
('ec2a94fd-f789-41b8-ab38-4e3612219ce7',	1,	'SUCCEEDED',	'archive_report',	1,	'{"is_valid": true, "invoice_details": {"amount": 1200, "customer": "Big Corp"}, "source_invoice_id": "inv-test-path", "report_archive_path": "s3://bucket/ec2a94fd-f789-41b8-ab38-4e3612219ce7/report.txt"}',	'[{"step": "fetch_invoice", "status": "succeeded", "timestamp": 1755197217.249901}, {"step": "validate_invoice", "status": "succeeded", "timestamp": 1755197219.6112747}, {"step": "generate_report", "status": "succeeded", "timestamp": 1755197222.104815}, {"step": "archive_report", "status": "succeeded", "timestamp": 1755197229.0917907}]',	'2025-08-14 18:46:53.341962+00',	'2025-08-14 18:47:09.982813+00'),
('9bae147e-8e22-42bf-bf94-4df5d36a82a8',	1,	'FAILED',	'validate_invoice',	2,	'{"error": "Invoice amount is too low for this test.", "is_valid": false, "invoice_details": {"amount": 500, "customer": "Big Corp"}, "source_invoice_id": "inv-business-error-path"}',	'[{"step": "fetch_invoice", "status": "succeeded", "timestamp": 1755169165.9167016}, {"step": "validate_invoice", "status": "failed", "timestamp": 1755169167.0174632}, {"step": "validate_invoice", "status": "failed", "timestamp": 1755169178.1676512}]',	'2025-08-14 10:59:21.667419+00',	'2025-08-14 10:59:38.165878+00'),
('4b9ae271-e48f-4fce-aae7-dd26327a3cc0',	2,	'SUCCEEDED',	'final_step',	1,	'{"final_step_done": true, "initial_step_done": true}',	'[{"step": "initial_step", "status": "succeeded", "timestamp": 1755196143.928518}, {"step": "wait_15_seconds", "status": "succeeded", "resumed_at": "2025-08-14T18:29:21.008306"}, {"step": "final_step", "status": "succeeded", "timestamp": 1755196162.3010824}]',	'2025-08-14 18:29:01.809781+00',	'2025-08-14 18:29:22.360245+00'),
('9d9f9eb5-0653-4ccd-806c-b230e7dfb476',	2,	'SUCCEEDED',	'final_step',	1,	'{"final_step_done": true, "initial_step_done": true}',	'[{"step": "initial_step", "status": "succeeded", "timestamp": 1755174299.1560166}, {"step": "wait_15_seconds", "status": "succeeded", "resumed_at": "2025-08-14T12:25:16.259534"}, {"step": "final_step", "status": "succeeded", "timestamp": 1755174316.5684297}]',	'2025-08-14 12:24:56.801574+00',	'2025-08-14 12:25:17.613356+00'),
('d6e5b679-7f91-4ea5-ba24-f4a4a5b8c0e3',	2,	'SUCCEEDED',	'final_step',	1,	'{"final_step_done": true, "initial_step_done": true}',	'[{"step": "initial_step", "status": "succeeded", "timestamp": 1755187863.473457}, {"step": "wait_15_seconds", "status": "succeeded", "resumed_at": "2025-08-14T16:11:20.529653"}, {"step": "final_step", "status": "succeeded", "timestamp": 1755187881.7725844}]',	'2025-08-14 16:11:00.575485+00',	'2025-08-14 16:11:22.805124+00');

ALTER TABLE ONLY "public"."workflow_instances" ADD CONSTRAINT "workflow_instances_definition_id_fkey" FOREIGN KEY (definition_id) REFERENCES workflow_definitions(id) NOT DEFERRABLE;

-- 2025-08-15 10:20:27 UTC