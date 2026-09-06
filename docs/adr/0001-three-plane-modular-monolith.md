# ADR-0001: Three-plane modular monolith

Status: Accepted

Date: 2026-08-30

## Decision

Use a modular control-plane monolith with independently deployed worker, Edge Hub, outbox dispatcher, Edge Gateway, Web, Studio, Companion, and optional DPC. Device access is isolated behind the outbound Edge plane. Shared contracts prevent cloud code from depending on LAMDA types.

## Consequences

The first release has fewer distributed business services while retaining explicit package, database, event, and deployment boundaries. Device safety and publish reliability are enforced at every plane rather than delegated to a single process.

