--
-- PostgreSQL database dump
--

\restrict DuIiz0F7GJg1hcVhYmoGfdtjHhll3ENgR74QsL6ZrB7LbY6JNdKmdglI19ambKd

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg13+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: items; Type: TABLE DATA; Schema: public; Owner: library
--

COPY public.items (entity_id, barcode, shelfmark, condition, availability_status, notes) FROM stdin;
b147abf8-036b-46cd-b545-5dfaef7e6320	KKU-123456	PL248.D6 S86 2024	good	available	Örnek fiziksel nüsha.
a44cb68a-1001-40d6-ae38-652f732aa8a2	KKU-SOZLUK-0001	PL191 T87 2023	good	available	Türkçe Sözlük örnek fiziksel nüshası.
ada84484-957f-4113-b3c2-41d4a3be7cce	KKU-AKADEMIK-0001	Z665 B55 2025	good	available	LibraryHub örnek katalog nüshası.
8ce02c02-2bd5-4434-a41b-b325c83cd6cf	KKU-COCUK-0001	PZ8 G65 2024	good	available	LibraryHub örnek katalog nüshası.
49d53a7e-57a1-4d5b-a1fa-2e31e73a4bf3	KKU-TEZ-0001	Z701.3 E45 2026	good	available	LibraryHub örnek katalog nüshası.
a619a98d-9688-4079-86a0-b4db5de2a5d1	KKU-ANSIKLOPEDI-SET-0001	DR440 I75	good	available	LibraryHub örnek katalog nüshası.
c09db51f-a320-4c41-8aef-2e6a0aa68e8c	HAC-123456	PL248.D6 S86 2024	good	available	Hacettepe Üniversitesi test nüshası.
27e2540a-ae0e-4a21-a900-738e853a5123	HAC-123457	PL248.D6 S86 2025	good	available	Hacettepe Üniversitesi farklı baskı test nüshası.
1b9a1792-6565-4e97-a3f4-35e91f9366b3	\N	\N	unknown	reference	Том 1. [4], 432 с. Экземпляр Российской государственной библиотеки. НЭБ katalog kaydı ile doğrulanmıştır.
bf1cf4ef-0f87-4fc6-857c-ead7c789c5b9	\N	\N	unknown	reference	Том 2. 435 с. Экземпляр Российской государственной библиотеки. НЭБ katalog kaydı ile doğrulanmıştır.
ede20dc3-576d-40e1-99ae-585879e53c8e	TEST-CANONICAL-ITEM-001	TEST 001	good	available	Canonical Manifestation redirect üzerinden Item testi.
9f72d83f-1860-4e90-9296-ef280511aa8c	TEST-ITEM-REDIRECT-SOURCE	TEST SOURCE	good	available	\N
\.


--
-- Data for Name: item_agent_relation; Type: TABLE DATA; Schema: public; Owner: library
--

COPY public.item_agent_relation (item_entity_id, agent_entity_id, role) FROM stdin;
b147abf8-036b-46cd-b545-5dfaef7e6320	6e788275-09d9-438d-8b2c-fcd25422f602	holding_institution
c09db51f-a320-4c41-8aef-2e6a0aa68e8c	2d1a8810-d745-4727-aef9-6b50d34f49d2	holding_institution
27e2540a-ae0e-4a21-a900-738e853a5123	2d1a8810-d745-4727-aef9-6b50d34f49d2	holding_institution
1b9a1792-6565-4e97-a3f4-35e91f9366b3	da9a0dd0-773e-4b58-8833-cd599f06e4ee	holding_institution
bf1cf4ef-0f87-4fc6-857c-ead7c789c5b9	da9a0dd0-773e-4b58-8833-cd599f06e4ee	holding_institution
\.


--
-- Data for Name: manifestation_item; Type: TABLE DATA; Schema: public; Owner: library
--

COPY public.manifestation_item (manifestation_entity_id, item_entity_id) FROM stdin;
c5e259db-74e9-4cca-ad84-7457d0b032ae	b147abf8-036b-46cd-b545-5dfaef7e6320
624c8c7e-31f7-4658-be89-90fbcae2385c	a44cb68a-1001-40d6-ae38-652f732aa8a2
2229e4a2-2350-4edb-847b-0bbb2c19e449	ada84484-957f-4113-b3c2-41d4a3be7cce
daac5ca1-3b93-4c68-bcaa-32767fc21e7c	8ce02c02-2bd5-4434-a41b-b325c83cd6cf
09584213-8bb5-4bc0-bffd-77835a43150d	49d53a7e-57a1-4d5b-a1fa-2e31e73a4bf3
c94662b7-498c-4ed4-8f0d-cd0584e80d26	a619a98d-9688-4079-86a0-b4db5de2a5d1
c5e259db-74e9-4cca-ad84-7457d0b032ae	c09db51f-a320-4c41-8aef-2e6a0aa68e8c
ce60a37a-81a1-4f87-88f7-b5d1fca60dcc	27e2540a-ae0e-4a21-a900-738e853a5123
bd3c5fe9-29d0-478c-b46c-bb68c7b3e562	1b9a1792-6565-4e97-a3f4-35e91f9366b3
bd3c5fe9-29d0-478c-b46c-bb68c7b3e562	bf1cf4ef-0f87-4fc6-857c-ead7c789c5b9
e3888963-31a5-4c75-899e-e7ca85f0e4f8	ede20dc3-576d-40e1-99ae-585879e53c8e
e3888963-31a5-4c75-899e-e7ca85f0e4f8	9f72d83f-1860-4e90-9296-ef280511aa8c
\.


--
-- PostgreSQL database dump complete
--

\unrestrict DuIiz0F7GJg1hcVhYmoGfdtjHhll3ENgR74QsL6ZrB7LbY6JNdKmdglI19ambKd

