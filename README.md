# Agentic AI HVAC Bid Intelligence & Compliance Copilot

A human-in-the-loop AI copilot for HVAC bid teams that analyzes tender
requirements, matches supporting evidence, checks technical compliance,
and flags missing or high-risk items for human review.

## Problem

HVAC bid teams manually review complex tender documents, identify
qualification and technical requirements, locate supporting company
materials, compare manufacturer specifications, and verify compliance
before submission.

This process is time-consuming and error-prone. Missing evidence,
misunderstood requirements, or non-compliant technical parameters may
result in lost points or disqualification.

## Proposed Solution

The system will help bid teams:

- Extract structured requirements from tender documents
- Classify qualification, personnel, scoring, technical, and document requirements
- Match requirements with company and manufacturer evidence
- Compare technical parameters using deterministic rules
- Flag missing, uncertain, or non-compliant items
- Escalate high-risk cases for human review

## MVP

The first version will support:

1. Uploading an HVAC tender PDF
2. Extracting structured requirements with source-page references
3. Importing a small set of company/personnel records
4. Reading one manufacturer technical document
5. Matching requirements to supporting evidence
6. Performing deterministic technical-parameter comparisons
7. Displaying:
   - Satisfied
   - Human Review Required
   - Missing
   - Non-Compliant
8. Generating a compliance report

## Non-Goals

The MVP will not automate:

- Final bid pricing
- Electronic signatures
- Final project-manager assignment
- Final bid approval
- Formal bid submission

## Design Principle

> Use AI where interpretation and reasoning are needed, deterministic
> software where correctness can be enforced, and human review where
> business judgment or risk is high.

## Project Status

🚧 Project Design / Early Development

Developed as part of the IBM SkillsBuild AI Experiential Learning Lab,
Fall 2026.

## Development Approach

This project follows an Agile and DevOps workflow using:

- GitHub Issues and ZenHub user stories
- Feature branches
- Pull requests and code review
- Automated testing
- CI with GitHub Actions

## Data Privacy

Only synthetic or anonymized sample data will be stored in this public
repository. Real company bid documents, employee credentials, pricing,
and other sensitive business information will not be committed.
