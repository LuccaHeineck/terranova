---
name: architecture
description: Guides architectural decisions, project structure, dependencies, and code organization. Use when designing, reviewing, restructuring, or extending the project architecture.
---

# Architecture Skill

## Purpose

Keep the project architecture simple, understandable, maintainable, and aligned with the actual requirements.

The primary goal is not to create the most sophisticated architecture possible.

The primary goal is to create an architecture that a developer can understand completely.

---

## Core Principles

### 1. Prefer simplicity

Always prefer the simplest architecture that correctly solves the problem.

Do not introduce:

- unnecessary abstractions
- unnecessary interfaces
- unnecessary design patterns
- unnecessary layers
- unnecessary services
- unnecessary factories
- unnecessary dependency injection
- unnecessary wrappers

Every architectural component must have a clear responsibility and reason to exist.

If a simpler solution works, prefer it.

---

### 2. Understand before changing

Before making architectural changes:

1. Inspect the existing code.
2. Identify the responsibilities of the affected components.
3. Identify their dependencies.
4. Understand how data currently flows through the system.
5. Determine what problem the proposed change solves.

Do not restructure code based only on filenames or assumptions.

---

### 3. Separate responsibilities

Keep fundamentally different responsibilities separated.

The project contains several conceptual areas, including:

- API / HTTP communication
- backend/application logic
- simulation
- data processing
- input/output data
- configuration
- testing

Do not mix these responsibilities without a clear reason.

For example:

- API code should deal with requests, responses, validation, and serialization.
- Simulation code should contain simulation logic.
- Data-processing code should handle transformation and preparation of data.
- Application logic should coordinate operations between components.

The exact boundaries should be determined by the actual project.

---

### 4. Keep dependencies understandable

Dependencies should flow in a clear direction.

Avoid circular dependencies.

Before introducing a dependency between two components, ask:

1. Why does the dependency exist?
2. Is it necessary?
3. Could the responsibility be placed somewhere more appropriate?
4. Does this make the architecture harder to understand?

Prefer explicit dependencies over hidden coupling.

---

### 5. Domain logic should remain independent

Core domain and simulation logic should not unnecessarily depend on external concerns such as:

- HTTP
- API frameworks
- databases
- UI
- command-line interfaces
- infrastructure

The core logic should be reusable and testable independently whenever reasonably possible.

Do not enforce this through excessive abstraction.

---

### 6. Avoid premature generalization

Do not design for hypothetical future requirements.

Do not create generic systems because:

> "We might need this later."

Implement what the project actually needs.

Generalize only when there is a demonstrated need.

---

## Project Structure

When designing or modifying the folder structure:

1. Group code according to meaningful responsibilities.
2. Keep related files together.
3. Avoid deeply nested directories unless they improve clarity.
4. Avoid folders containing only one trivial file.
5. Prefer descriptive names.
6. Keep the number of top-level directories reasonable.

Every major directory should have a clear purpose.

When introducing a new directory, explain why it is necessary.

---

## Architecture Decisions

Before making a significant architectural change, explain:

### Problem

What problem are we solving?

### Current situation

How does the current architecture handle this?

### Proposed solution

What should change?

### Reasoning

Why is this solution appropriate?

### Alternatives

What simpler alternatives were considered?

### Trade-offs

What are the advantages and disadvantages?

### Impact

Which components will be affected?

Do not make significant architectural changes silently.

---

## Simulation Architecture

The simulation is a core part of the project.

Keep simulation logic clearly separated from:

- HTTP/API concerns
- request handling
- serialization
- UI
- infrastructure

The simulation should receive well-defined inputs and produce well-defined outputs.

Prefer a flow similar to:

Input data
→ validation
→ preprocessing
→ simulation
→ results
→ postprocessing
→ output

The exact implementation must follow the project's actual requirements.

Do not create additional layers unless they provide a real benefit.

---

## API Architecture

The API should act as a boundary between external clients and the application.

API responsibilities may include:

- receiving requests
- validating input
- converting external representations into internal representations
- invoking application/domain logic
- converting results into responses
- handling API-specific errors

Avoid putting core simulation algorithms directly inside API handlers.

API handlers should remain relatively small and understandable.

---

## Data Architecture

Clearly distinguish between:

- raw input data
- validated data
- processed data
- simulation input
- simulation output
- persisted/application data

Do not duplicate data unnecessarily.

When data is transformed, make the transformation explicit and easy to trace.

---

## Testing Architecture

Tests should reflect architectural boundaries.

Prefer:

- unit tests for isolated logic
- simulation tests for simulation behavior
- integration tests for interactions between components
- API tests for API behavior

Tests should help verify architectural boundaries rather than bypass them.

---

## Documentation

Architectural knowledge should be documented.

When a significant architectural decision is introduced, update the relevant documentation.

Documentation should explain:

- what components exist
- what their responsibilities are
- how they communicate
- where data flows
- why important architectural decisions were made

Documentation should explain the project to a developer who has never seen it before.

---

## When Adding New Code

Before deciding where new code belongs:

1. Identify its responsibility.
2. Find existing code with the same responsibility.
3. Determine whether it belongs in an existing component.
4. Only create a new component if existing components are not appropriate.

Do not create a new folder or abstraction by default.

---

## When Refactoring

Do not refactor unrelated code while implementing a feature.

Keep architectural changes focused.

Before removing or moving code:

- verify that it is unused
- identify dependencies
- check tests
- explain the reason for the change

Preserve working behavior unless the purpose of the change is explicitly to alter it.

---

## Communication Style

When discussing architecture with the developer:

- Explain decisions in simple language.
- Avoid unnecessary jargon.
- Show relationships between components.
- Explain why something belongs where it does.
- Explicitly identify uncertainty.
- Ask before making major architectural changes when requirements are unclear.

The developer should be able to understand the architecture without relying on the AI to remember it.

---

## Important Rule

Do not optimize the architecture for impressiveness.

Optimize it for:

1. Understandability
2. Correctness
3. Maintainability
4. Testability
5. Simplicity

In that order.

If an architectural decision makes the project significantly harder to understand without providing a concrete benefit, do not make that decision.