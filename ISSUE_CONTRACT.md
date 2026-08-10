# Issue contract — Creative Provenance Gate

## Problem
Orchestrating workflows across creative applications and models while retaining editable structure, provenance, and brand control.

## Desired outcome
A bounded, open, testable implementation of **Creative Provenance Gate** that demonstrates Bind each creative export to a content-addressed provenance receipt (source mix, model id, rights claim, transform chain) and refuse silent mutation.

## Non-goals
- Adobe affiliation or proprietary integration
- Portfolio-wide scale/performance claims
- UI marketing site

## Acceptance
1. Mechanism module implements allow + refuse with structured receipts
2. pytest behavioral suite green
3. operate.py cold-start produces JSON receipt
4. Non-affiliation disclaimer preserved
