High-Level Design — Pull Model Using Adobe Journaling API
Overview

Instead of Adobe Cloud Manager pushing webhook events directly into Jenkins, Jenkins (or a small polling service) periodically pulls deployment-related events from the Adobe I/O Journaling API. Jenkins processes these events, determines which ones are new and relevant, and triggers the correct regression/QA pipelines.

This model avoids exposing Jenkins publicly and allows full control over polling frequency, deduplication, and event filtering.

Phase 1 — Event Collection & Filtering
Step 1 — Adobe Cloud Manager Deployment Produces Events

Each deployment in Cloud Manager (Dev, QA, Stage, Prod) generates multiple internal events.

Adobe I/O consolidates them into a Journaling Endpoint.

Example Journaling API endpoint format:

https://eventsingress.adobe.io/{journal_id}


Access requires an Adobe Developer Console integration with:

Service Account (JWT or OAuth Server-to-Server)

Workspace with Cloud Manager Events enabled

Step 2 — Polling Service Authenticates & Calls Journaling API

A lightweight polling service (Python, Node.js, Cloud Run, or Jenkins scheduled job) calls the Journaling API:

Example:

GET https://eventsingress.adobe.io/{journal_id}?since={cursor}
Authorization: Bearer <access_token>
x-api-key: <client_id>


Corporate whitelisting note:

Only outbound access is required.

The polling service's IP may need to be whitelisted in the corporate network firewall to reach Adobe.

Step 3 — Retrieve Only New Events

Adobe Journaling API supports incremental reads using the “cursor” mechanism.

Each response includes a next cursor.

The polling service stores this cursor (e.g., Cloud Storage bucket, Redis, Jenkins workspace).

Ensures:

No re-reading old events

No duplicate triggers

Efficient reads even if there are hundreds of events

Step 4 — Local Filtering of Relevant Events

The polling service filters for:

Only Cloud Manager events

Only deployment.finished or deployment.started

Only the target environment (dev, qa, etc.)

Only successful deployments

Example event fields used:

event.type
event.environment.name
event.deploymentId
event.pipelineId
event.status

Step 5 — Select Only the Latest Deployment Event

In case multiple deployments occurred:

Group events by environment (e.g., Dev)

Sort by timestamp

Pick the newest event that is not yet processed

Maintain a local “processed deployment IDs” cache (state file, Redis, database)

This ensures:

Tests are only triggered once per deployment

Old or duplicate events are ignored

Phase 2 — Test Execution Triggering
Step 6 — Polling Service Triggers Jenkins

Once a new “latest” deployment event is detected:

Trigger options:

Option A — Call Jenkins REST API
POST https://jenkins.example.com/job/<pipeline>/buildWithParameters

Option B — Use Generic Webhook Trigger plugin
POST https://jenkins.example.com/generic-webhook-trigger/invoke?token=<secure_token>
Content-Type: application/json

{
  "environment": "dev",
  "deploymentId": "abc123",
  "timestamp": "2025-01-20T12:45:00Z",
  "eventType": "dev_deployment_finished"
}


Jenkins remains internal; only outbound access is required.

Step 7 — Jenkins Runs Corresponding Test Pipelines

Depending on the incoming parameters:

Environment	Triggered Jenkins Pipeline
Dev	Basic regression tests
QA	Detailed regression tests
Stage	Performance / load tests

Pipelines can be parameterized based on:

environment

deployment ID

pipeline ID

Step 8 — Decision Point Inside Jenkins Pipeline

Similar to your push model:

IF FAIL:

Jenkins can call Cloud Manager’s API to halt promotions or rollback.

IF PASS:

Jenkins marks the stage “passed” and allows promotion.

(Cloud Manager API calls require the same Adobe service account.)

Phase 3 — State Management & Repeatability
Step 9 — Update Cursor and Processed Events

After successfully triggering tests:

Store the new Journaling cursor

Store processed deployment IDs

Ensures reliable, idempotent behavior.

Step 10 — Idle State Handling

Polling continues even if:

There are no new deployments for days

There are bursty deployments (e.g., 10 in 1 hour)

Polling frequency is typically:

Every 1–5 minutes for near-real-time

Every 10–15 minutes for light load

Adobe Journaling API supports up to 7 days of retention

Security & Access Model
Adobe Service Account Access

To access the Journaling API:

Use a Server-to-Server OAuth client or JWT-based service account created in Adobe Developer Console.

Must be assigned to:

Cloud Manager API

I/O Events

Correct Adobe Org & Project Workspace

Cloud Manager administrators must approve access.

Corporate Controls

Outbound firewall rule: allow traffic from Polling Service → Adobe domain.

No inbound opening required for Jenkins.
